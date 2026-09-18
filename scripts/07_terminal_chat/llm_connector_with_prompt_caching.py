"""Bosch Model Farm multimodal connector with optional sticky-session headers.

Reconstructed from the supplied working version.  Secrets belong in .env, never here.
"""
import base64
import io
import json
import logging
import os
import time
import uuid
from pathlib import Path

import requests

try:
    from openai import OpenAI
    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False

try:
    import fitz  # PyMuPDF
    _FITZ_AVAILABLE = True
except ImportError:
    _FITZ_AVAILABLE = False

FARM_BASE = os.getenv("BOSCH_FARM_BASE_URL", "https://aoai-farm.bosch-temp.com/api").rstrip("/")
MIME_MAP = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


class LLMConnector:
    """One small interface for Bosch Farm Gemini, Claude and OpenAI-style models."""

    def __init__(self, model_name: str, api_key: str, session_id: str | None = None):
        self.model_name = model_name
        self.api_key = api_key
        self.session_id = session_id
        self.last_usage = None
        self.last_reasoning = ""
        self.last_response_model = None
        self._stream_rejected = False
        self._family = self._detect_family(model_name)
        logging.info("LLMConnector ready: model=%s, family=%s, session_id=%s", model_name, self._family, session_id)

    @staticmethod
    def _detect_family(model_name: str) -> str:
        name = model_name.lower()
        if name.startswith("gemini") or "gemini" in name:
            return "gemini"
        if name.startswith("claude") or "claude" in name:
            return "claude"
        if (name.startswith(("gpt", "o1", "o3", "llama", "glm", "deepseek")) or "openai-" in name):
            return "openai"
        raise ValueError("Cannot determine model family from %r. Supported: gemini, claude, gpt, o1, o3, llama, glm, deepseek." % model_name)

    def analyze_documents(self, file_paths: list, user_prompt: str, system_prompt: str | None = None,
                          generation_config: dict | None = None, *, stream: bool = False,
                          event_handler=None, thinking: str = "auto") -> str:
        self.last_usage = None
        self.last_reasoning = ""
        self.last_response_model = None
        if self._family == "openai":
            return self._call_openai(file_paths, user_prompt, system_prompt, generation_config,
                                     stream=stream, event_handler=event_handler, thinking=thinking)
        if stream and event_handler:
            event_handler("notice", "当前模型的连接器使用非流式输出，步骤进度仍会显示。")
        return {"gemini": self._call_gemini, "claude": self._call_claude, "openai": self._call_openai}[self._family](
            file_paths, user_prompt, system_prompt, generation_config
        )

    def ask_about_files(self, file_paths: list, question: str, system_prompt: str | None = None,
                        generation_config: dict | None = None, *, stream: bool = False,
                        event_handler=None, thinking: str = "auto") -> str:
        return self.analyze_documents(file_paths, question, system_prompt, generation_config,
                                      stream=stream, event_handler=event_handler, thinking=thinking)

    def get_last_token_usage(self) -> dict | None:
        return self.last_usage

    def _get_common_headers(self) -> dict:
        return {"X-Session-ID": str(self.session_id)} if self.session_id else {}

    def _call_gemini(self, file_paths, user_prompt, system_prompt, generation_config):
        url = f"{FARM_BASE}/google/v1/publishers/google/models/{self.model_name}:generateContent"
        headers = self._get_common_headers()
        headers.update({"genaiplatform-farm-subscription-key": self.api_key, "Content-Type": "application/json"})
        parts = [p for fp in file_paths for p in [self._file_to_gemini_part(fp)] if p]
        parts.append({"text": user_prompt})
        payload = {"contents": [{"role": "user", "parts": parts}]}
        if system_prompt:
            payload["system_instruction"] = {"parts": [{"text": system_prompt}]}
        if generation_config:
            payload["generationConfig"] = generation_config
        return self._http_post(url, headers, payload, self._extract_gemini_text)

    @staticmethod
    def _extract_gemini_text(reply: dict) -> str:
        candidates = reply.get("candidates", [])
        if candidates:
            for part in candidates[0].get("content", {}).get("parts", []):
                if "text" in part:
                    return part["text"]
        reason = (candidates or [{}])[0].get("finishReason", "unknown")
        return f"(no text content, finishReason={reason})"

    def _call_claude(self, file_paths, user_prompt, system_prompt, generation_config):
        url = f"{FARM_BASE}/google/v1/publishers/anthropic/models/{self.model_name}:rawPredict"
        session = self.session_id or f"caching_session_{uuid.uuid4().hex[:12]}"
        self.session_id = session
        headers = self._get_common_headers()
        headers.update({"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})
        content = []
        for fp in file_paths:
            block = self._file_to_claude_block(fp)
            if isinstance(block, list):
                content.extend(block)
            elif block:
                content.append(block)
        content.append({"type": "text", "text": user_prompt})
        config = generation_config or {}
        max_tokens = min(int(config.get("maxOutputTokens", 8192)), 32000)
        thinking = self.model_name.lower().startswith(("claude-opus-4", "claude-sonnet-4", "claude-sonnet-5"))
        payload = {"anthropic_version": "vertex-2023-10-16", "max_tokens": max_tokens,
                   "messages": [{"role": "user", "content": content}]}
        if system_prompt:
            payload["system"] = [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}]
        temperature = config.get("temperature")
        if temperature is not None and not thinking:
            try:
                if float(temperature) > 0:
                    payload["temperature"] = float(temperature)
            except (TypeError, ValueError):
                pass
        return self._http_post(url, headers, payload, self._extract_claude_text)

    def _extract_claude_text(self, reply: dict) -> str:
        usage = reply.get("usage", {})
        if usage:
            self.last_usage = usage
            logging.info("BMF usage: input=%s output=%s cache-write=%s cache-read=%s", usage.get("input_tokens", 0), usage.get("output_tokens", 0), usage.get("cache_creation_input_tokens", 0), usage.get("cache_read_input_tokens", 0))
        content = reply.get("content", [])
        return content[0].get("text", "(no text content)") if content else "(no text content)"

    def _call_openai(self, file_paths, user_prompt, system_prompt, generation_config, *,
                     stream=False, event_handler=None, thinking="auto"):
        if not _OPENAI_AVAILABLE:
            return "Error: openai package must be installed — run: pip install openai"
        name = self.model_name.lower()
        base_url = (f"{FARM_BASE}/google/v1/endpoints/{self.model_name}/openai" if ("glm" in name or "-oss" in name)
                    else f"{FARM_BASE}/openai/deployments/{self.model_name}")
        headers = self._get_common_headers()
        headers["genaiplatform-farm-subscription-key"] = self.api_key
        client = OpenAI(api_key="dummy-key", base_url=base_url, default_headers=headers)
        content = [{"type": "text", "text": user_prompt}]
        for fp in file_paths:
            for b64 in self._file_to_openai_images(fp):
                content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": content})
        config = generation_config or {}
        reasoning = name.startswith(("gpt-5", "o1", "o3", "deepseek-r1"))
        tokens = int(config.get("maxOutputTokens", 4096))
        kwargs = {"model": self.model_name, "messages": messages, "timeout": 300,
                  "extra_query": {"api-version": "2024-08-01-preview"} if "openai" in base_url else {}}
        kwargs["max_completion_tokens" if reasoning else "max_tokens"] = tokens
        if config.get("temperature") is not None and not reasoning:
            kwargs["temperature"] = config["temperature"]
        if thinking not in {"auto", "enabled", "disabled"}:
            client.close()
            raise ValueError("thinking must be auto, enabled or disabled")
        # Bosch Farm may not forward this DeepSeek-specific extension.  Only
        # send it when explicitly requested; auto preserves deployment defaults.
        if name.startswith("deepseek") and thinking != "auto":
            kwargs["extra_body"] = {"thinking": {"type": thinking}}
        if name.startswith("deepseek") and thinking != "disabled":
            kwargs.pop("temperature", None)
        use_stream = bool(stream and not self._stream_rejected)
        if use_stream:
            kwargs["stream"] = True

        def emit(kind, text):
            if event_handler and text:
                event_handler(kind, text)

        def capture_metadata(response):
            model = getattr(response, "model", None)
            if model:
                self.last_response_model = model
            usage = getattr(response, "usage", None)
            if usage is not None:
                self.last_usage = usage.model_dump() if hasattr(usage, "model_dump") else usage

        response_stream = None
        try:
            try:
                result = client.chat.completions.create(**kwargs)
            except Exception as exc:
                # Fall back only for an explicit rejection of streaming, before
                # receiving any content. Never replay a partially received answer.
                error = str(exc).lower()
                unsupported = getattr(exc, "status_code", None) in {400, 422, 501} and "stream" in error and any(
                    term in error for term in ("not supported", "unsupported", "not allowed", "unknown", "unrecognized", "not implemented", "unexpected", "extra inputs")
                )
                if not use_stream or not unsupported:
                    raise
                self._stream_rejected = True
                use_stream = False
                kwargs.pop("stream", None)
                emit("notice", "Farm 拒绝流式输出，本次连接改用完整响应；仍显示等待耗时。")
                result = client.chat.completions.create(**kwargs)
            if not use_stream:
                capture_metadata(result)
                message = result.choices[0].message
                self.last_reasoning = getattr(message, "reasoning_content", None) or ""
                emit("reasoning", self.last_reasoning)
                text = message.content or ""
                if not text.strip():
                    raise ValueError("接口未返回最终正文；可能只返回了思考文本或输出预算耗尽。")
                emit("content", text)
                return text.strip()
            response_stream = result
            texts, thoughts = [], []
            finish_reason = None
            for chunk in result:
                capture_metadata(chunk)
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                finish_reason = choice.finish_reason or finish_reason
                delta = choice.delta
                thought = getattr(delta, "reasoning_content", None) or ""
                content_delta = getattr(delta, "content", None) or ""
                if thought:
                    thoughts.append(thought)
                    emit("reasoning", thought)
                if content_delta:
                    texts.append(content_delta)
                    emit("content", content_delta)
            self.last_reasoning = "".join(thoughts)
            if finish_reason is None:
                raise ValueError("流式连接提前结束，未收到完成标记；本轮不执行工具。")
            text = "".join(texts).strip()
            if not text:
                raise ValueError(f"接口未返回最终正文（finish_reason={finish_reason}）；可能输出预算耗尽。")
            return text
        except Exception as exc:
            logging.exception("OpenAI call failed")
            return f"Error: {exc}"
        finally:
            if response_stream is not None:
                response_stream.close()
            client.close()

    @staticmethod
    def _mime(path: str) -> str:
        return MIME_MAP.get(Path(path).suffix.lower(), "")

    def _read_and_optimize_file(self, file_path: str) -> tuple[bytes, str]:
        path = Path(file_path)
        if not path.exists():
            logging.error("File not found: %s", path)
            return b"", ""
        try:
            if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}:
                try:
                    from PIL import Image
                    with Image.open(path) as image:
                        if image.mode != "RGB":
                            image = image.convert("RGB")
                        image.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
                        buffer = io.BytesIO(); image.save(buffer, format="JPEG", quality=85)
                        return buffer.getvalue(), "image/jpeg"
                except Exception as exc:
                    logging.warning("Image compression failed for %s: %s", path.name, exc)
            return path.read_bytes(), self._mime(str(path))
        except OSError as exc:
            logging.error("Cannot read %s: %s", path, exc)
            return b"", ""

    def _file_to_gemini_part(self, file_path: str) -> dict | None:
        data, mime = self._read_and_optimize_file(file_path)
        return {"inlineData": {"mimeType": mime, "data": base64.b64encode(data).decode("utf-8")}} if data and mime else None

    def _file_to_claude_block(self, file_path: str) -> dict | None:
        path = Path(file_path)
        if not path.exists():
            return None
        ext = path.suffix.lower()
        if ext == ".pdf":
            data = path.read_bytes()
            if len(data) > 4 * 1024 * 1024 and _FITZ_AVAILABLE:
                try:
                    doc = fitz.open(path); clipped = fitz.open(); limit = int(5.5 * 1024 * 1024)
                    for page in doc:
                        if clipped.page_count >= 4: break
                        clipped.insert_pdf(doc, from_page=page.number, to_page=page.number)
                        if len(base64.b64encode(clipped.write())) > limit:
                            if clipped.page_count > 1: clipped.delete_page(clipped.page_count - 1)
                            else:
                                clipped.close(); doc.close(); return self._fallback_single_page_to_image(str(path))
                            break
                    data = clipped.write(); clipped.close(); doc.close()
                except Exception as exc:
                    logging.warning("PDF clipping failed: %s", exc)
            return {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": base64.b64encode(data).decode()}}
        data, mime = self._read_and_optimize_file(str(path))
        return {"type": "image", "source": {"type": "base64", "media_type": mime, "data": base64.b64encode(data).decode()}} if data and mime else None

    def _fallback_single_page_to_image(self, file_path: str, page_idx: int = 0) -> dict | None:
        try:
            doc = fitz.open(file_path); pix = doc[page_idx].get_pixmap(matrix=fitz.Matrix(150 / 72, 150 / 72)); doc.close()
            return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(pix.tobytes("jpeg")).decode()}}
        except Exception as exc:
            logging.error("PDF image fallback failed: %s", exc)
            return None

    def _file_to_openai_images(self, file_path: str) -> list[str]:
        path = Path(file_path)
        if path.suffix.lower() == ".pdf":
            if not _FITZ_AVAILABLE:
                logging.warning("PyMuPDF is required to send PDFs to GPT.")
                return []
            try:
                doc = fitz.open(path); images = []
                for i, page in enumerate(doc):
                    if i >= 4: break
                    pix = page.get_pixmap(matrix=fitz.Matrix(150 / 72, 150 / 72))
                    images.append(base64.b64encode(pix.tobytes("jpeg")).decode())
                doc.close(); return images
            except Exception as exc:
                logging.error("PDF-to-image conversion failed: %s", exc); return []
        data, _ = self._read_and_optimize_file(str(path))
        return [base64.b64encode(data).decode()] if data else []

    def _http_post(self, url: str, headers: dict, payload: dict, extractor) -> str:
        retryable = {429, 500, 502, 503, 504}
        for attempt in range(1, 4):
            try:
                response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=300)
                if response.ok:
                    reply = response.json()
                    if "usageMetadata" in reply:
                        self.last_usage = reply["usageMetadata"]
                    return extractor(reply)
                if response.status_code in retryable and attempt < 3:
                    time.sleep(2 ** attempt); continue
                logging.error("HTTP %s: %s", response.status_code, response.text)
                return f"HTTP error {response.status_code}"
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
                if attempt == 3: return f"Error after 3 attempts: {exc}"
                time.sleep(2 ** attempt)
            except Exception as exc:
                logging.exception("Unexpected request error")
                return f"Error: {exc}"
        return "Error: retries exhausted"


# Run from the downloaded standalone folder; keep .env in the same folder.
# 1) python -m pip install -r requirements.txt
# 2) python excel_chat_agent.py --model deepseek-v4-flash-2026-04-23 --session workshop
# 3) Display reasoning_content when Farm returns it (also requests streaming):
#    python excel_chat_agent.py --model deepseek-v4-flash-2026-04-23 --session workshop --show-reasoning
# 4) If Farm does not support streaming, keep progress and use a full response:
#    python excel_chat_agent.py --model deepseek-v4-flash-2026-04-23 --session workshop --show-reasoning --no-stream
# 5) Optionally request DeepSeek thinking explicitly, only if Farm supports it:
#    python excel_chat_agent.py --model deepseek-v4-flash-2026-04-23 --session workshop --show-reasoning --thinking enabled
