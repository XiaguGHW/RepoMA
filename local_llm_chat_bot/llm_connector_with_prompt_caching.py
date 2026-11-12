"""Bosch Model Farm multimodal connector with optional sticky-session headers.

Reconstructed from the supplied working version.  Secrets belong in .env, never here.
"""
import base64
import io
import json
import time
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any, Callable

import requests
from request_runtime import RequestControl, RequestStopped, ResponseLimitExceeded
from workbench_i18n import UIMessage
from release_safety import PROMPT_CACHE_BREAK

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

DEFAULT_FARM_BASE = "https://aoai-farm.bosch-temp.com/api"


def farm_base_url() -> str:
    """Read the endpoint lazily so a local .env loaded by the GUI takes effect.

    The workbench imports this module before its setup endpoint calls
    ``load_dotenv``.  Resolving the value per request keeps custom Bosch Farm
    endpoints functional without requiring users to export an environment
    variable before launching Python.
    """
    value = os.getenv("BOSCH_FARM_BASE_URL", DEFAULT_FARM_BASE).strip().rstrip("/")
    from urllib.parse import urlsplit
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("BOSCH_FARM_BASE_URL must be an HTTP(S) URL without embedded credentials")
    return value


MIME_MAP = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def connection_setup_timeout(error: BaseException, elapsed: float, connect_timeout: float, read_timeout: float) -> bool:
    """True only when a timeout provably fired before the request was sent.

    The socket uses the connect timeout until the connection (and any proxy
    tunnel) is established and the read timeout afterwards.  Through a proxy,
    urllib3 reports a slow tunnel as "Read timed out. (read timeout=<connect
    timeout>)".  Both the reported value and the elapsed time must point to
    the setup phase; otherwise the provider may already be generating (and
    billing), so the caller must not send the request again.
    """
    margin = 1.5
    match = re.search(r"read timeout=([0-9.]+)", str(error))
    if not match or read_timeout <= connect_timeout + margin:
        return False
    try:
        reported = float(match.group(1))
    except ValueError:
        return False
    return abs(reported - connect_timeout) < 0.01 and elapsed < connect_timeout + margin


class LLMConnector:
    """One small interface for Bosch Farm Gemini, Claude and OpenAI-style models."""

    def __init__(self, model_name: str, api_key: str, session_id: str | None = None):
        model_name = str(model_name).strip()
        if not model_name or any(c.isspace() for c in model_name) or any(c in model_name for c in "?#\\"):
            raise ValueError("Enter one exact Bosch Farm model ID without spaces")
        self.model_name = model_name
        self.api_key = api_key
        self.session_id = session_id
        self.last_usage = None
        self.last_reasoning = ""
        self.last_response_model = None
        self.usage_attempts: list[dict] = []
        self.request_control = None
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
        self.usage_attempts = []
        self._control = self.request_control or RequestControl()
        self._control.check()
        if self._family != "claude":  # Only Claude needs an explicit cache mark.
            user_prompt = user_prompt.replace(PROMPT_CACHE_BREAK, "\n\n")
        if self._family == "openai":
            return self._call_openai(file_paths, user_prompt, system_prompt, generation_config,
                                     stream=stream, event_handler=event_handler, thinking=thinking)
        if stream and event_handler:
            event_handler("notice", UIMessage('notice.nonstream'))
        handlers: dict[str, Callable[..., str]] = {
            "gemini": self._call_gemini,
            "claude": self._call_claude,
            "openai": self._call_openai,
        }
        return handlers[self._family](
            file_paths, user_prompt, system_prompt, generation_config
        )

    def ask_about_files(self, file_paths: list, question: str, system_prompt: str | None = None,
                        generation_config: dict | None = None, *, stream: bool = False,
                        event_handler=None, thinking: str = "auto") -> str:
        return self.analyze_documents(file_paths, question, system_prompt, generation_config,
                                      stream=stream, event_handler=event_handler, thinking=thinking)

    def get_last_token_usage(self) -> dict | None:
        return self.last_usage

    def _begin_usage_attempt(self):
        """One ledger entry per dispatched request, even without returned usage."""
        self._control.check()
        self.last_usage = None
        self.last_response_model = None
        self.usage_attempts.append({"usage": {}, "model": self.model_name})

    def _record_usage(self, usage) -> None:
        """Store raw provider usage plus a common input/output/total schema."""
        if usage is None:
            return
        if hasattr(usage, "model_dump"):
            raw = usage.model_dump()
        elif hasattr(usage, "dict"):
            raw = usage.dict()
        elif isinstance(usage, dict):
            raw = dict(usage)
        else:
            raw = vars(usage) if hasattr(usage, "__dict__") else {}
        if not isinstance(raw, dict):
            return

        from release_safety import normalize_usage
        self.last_usage = normalize_usage(raw)
        if self.usage_attempts:
            self.usage_attempts[-1].update(usage=self.last_usage, model=self.last_response_model or self.model_name)

    def _record_error_usage(self, error):
        body = getattr(error, "body", None)
        response = getattr(error, "response", None)
        if response is not None:
            try:
                body = response.json()
            except (ValueError, AttributeError):
                pass
        if isinstance(body, dict) and isinstance(body.get("usage"), dict):
            self._record_usage(body["usage"])

    def _get_common_headers(self) -> dict:
        return {"X-Session-ID": str(self.session_id)} if self.session_id else {}

    def _call_gemini(self, file_paths, user_prompt, system_prompt, generation_config):
        url = f"{farm_base_url()}/google/v1/publishers/google/models/{self.model_name}:generateContent"
        headers = self._get_common_headers()
        headers.update({"genaiplatform-farm-subscription-key": self.api_key, "Content-Type": "application/json"})
        parts = [p for fp in file_paths for p in [self._file_to_gemini_part(fp)] if p]
        parts.append({"text": user_prompt})
        payload: dict[str, Any] = {"contents": [{"role": "user", "parts": parts}]}
        if system_prompt:
            payload["system_instruction"] = {"parts": [{"text": system_prompt}]}
        if generation_config:
            payload["generationConfig"] = generation_config
        return self._http_post(url, headers, payload, self._extract_gemini_text)

    @staticmethod
    def _extract_gemini_text(reply: dict) -> str:
        candidates = reply.get("candidates", [])
        candidate = candidates[0] if candidates else {}
        reason = candidate.get("finishReason", "unknown")
        if reason not in {"STOP", "unknown"}:
            return f"Error: incomplete Gemini response ({reason})"
        texts = [p["text"] for p in candidate.get("content", {}).get("parts", []) if isinstance(p, dict) and isinstance(p.get("text"), str) and not p.get("thought")]
        return "".join(texts) or f"(no text content, finishReason={reason})"

    def _call_claude(self, file_paths, user_prompt, system_prompt, generation_config):
        url = f"{farm_base_url()}/google/v1/publishers/anthropic/models/{self.model_name}:rawPredict"
        session = self.session_id or f"caching_session_{uuid.uuid4().hex[:12]}"
        self.session_id = session
        headers = self._get_common_headers()
        headers.update({"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})
        content = []
        stable, marker, user_prompt = user_prompt.partition(PROMPT_CACHE_BREAK)
        if not marker:
            stable, user_prompt = "", stable
        if stable:  # Same in every turn: cached (read at the cache price later).
            content.append({"type": "text", "text": stable, "cache_control": {"type": "ephemeral"}})
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
            self._record_usage(usage)
            logging.info("BMF Claude cache: write=%s read=%s", usage.get("cache_creation_input_tokens", 0), usage.get("cache_read_input_tokens", 0))
        content = reply.get("content", [])
        if reply.get("stop_reason") not in {None, "end_turn", "stop_sequence"}:
            return f"Error: incomplete Claude response ({reply.get('stop_reason')})"
        return "".join(block["text"] for block in content if isinstance(block, dict) and isinstance(block.get("text"), str) and block.get("type", "text") == "text") or "(no text content)"

    def _call_openai(self, file_paths, user_prompt, system_prompt, generation_config, *,
                     stream=False, event_handler=None, thinking="auto"):
        if not _OPENAI_AVAILABLE:
            return "Error: openai package must be installed — run: pip install openai"
        name = self.model_name.lower()
        base = farm_base_url()
        base_url = (f"{base}/google/v1/endpoints/{self.model_name}/openai" if ("glm" in name or "-oss" in name)
                    else f"{base}/openai/deployments/{self.model_name}")
        headers = self._get_common_headers()
        headers["genaiplatform-farm-subscription-key"] = self.api_key
        # SDK-hidden retries cannot be reconciled with the request ledger.
        client = OpenAI(api_key="dummy-key", base_url=base_url, default_headers=headers, max_retries=0)
        content = [{"type": "text", "text": user_prompt}]
        for fp in file_paths:
            for b64 in self._file_to_openai_images(fp):
                content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": content})
        config = generation_config or {}
        reasoning = name.startswith(("gpt-5", "gpt-6", "o1", "o3", "deepseek-r1"))
        tokens = int(config.get("maxOutputTokens", 8192))
        from openai import _base_client
        transport = getattr(_base_client, "httpx2", None) or _base_client.httpx
        control = self._control

        def bound_response(response):
            original = response.stream
            stream_base: Any = transport.SyncByteStream

            class BoundedStream(stream_base):
                def __iter__(self):
                    size = 0
                    for chunk in original:
                        control.check()
                        size += len(chunk)
                        if size > control.policy.max_response_chars * 4:
                            control.cancel('limit')
                            control.check()
                        yield chunk

                def close(self):
                    original.close()

            # Bound raw bytes before the SDK's SSE line decoder: a provider
            # dripping an unfinished event must not bypass the whole deadline.
            response.stream = BoundedStream()

        client._client.event_hooks.setdefault('response', []).append(bound_response)
        use_stream = bool(stream and not self._stream_rejected)
        # Streams are bounded by chunk silence; a full response by its total wait.
        connect, read = self._control.timeouts(complete=not use_stream)
        kwargs = {"model": self.model_name, "messages": messages, "timeout": transport.Timeout(read, connect=connect),
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
        if use_stream:
            # OpenAI-compatible Chat Completions only sends final token usage
            # in streaming mode when this option is requested.
            kwargs["stream"] = True
            kwargs["stream_options"] = {"include_usage": True}

        def emit(kind, text):
            self._control.check()
            if event_handler and text:
                event_handler(kind, text)

        def capture_metadata(response):
            model = getattr(response, "model", None)
            if model:
                self.last_response_model = model
            usage = getattr(response, "usage", None)
            if usage is not None:
                self._record_usage(usage)

        response_stream = None
        try:
            try:
                self._begin_usage_attempt()
                result = client.chat.completions.create(**kwargs)
            except Exception as exc:
                # Fall back only for an explicit rejection of streaming, before
                # receiving any content. Never replay a partially received answer.
                self._record_error_usage(exc)
                error = str(exc).lower()
                unsupported = getattr(exc, "status_code", None) in {400, 422, 501} and "stream" in error and any(
                    term in error for term in ("not supported", "unsupported", "not allowed", "unknown", "unrecognized", "not implemented", "unexpected", "extra inputs")
                )
                if not use_stream or not unsupported or self._control.policy.attempts < 2:
                    raise
                self._stream_rejected = True
                use_stream = False
                kwargs.pop("stream", None)
                kwargs.pop("stream_options", None)
                emit("notice", UIMessage('notice.stream_fallback'))
                connect, read = self._control.timeouts(complete=True)
                kwargs["timeout"] = transport.Timeout(read, connect=connect)
                self._begin_usage_attempt()
                result = client.chat.completions.create(**kwargs)
            if not use_stream:
                capture_metadata(result)
                if not result.choices or result.choices[0].finish_reason not in {None, "stop"}:
                    reason = result.choices[0].finish_reason if result.choices else "no choices"
                    raise ValueError(f"Incomplete or blocked model response ({reason})")
                message = result.choices[0].message
                self.last_reasoning = getattr(message, "reasoning_content", None) or ""
                emit("reasoning", self.last_reasoning)
                text = message.content or ""
                self._control.limit(len(text) + len(self.last_reasoning))
                if not text.strip():
                    raise ValueError("接口未返回最终正文；可能只返回了思考文本或输出预算耗尽。")
                emit("content", text)
                return text.strip()
            response_stream = result
            texts, thoughts = [], []
            received_chars = 0
            finish_reason = None
            for chunk in result:
                self._control.check()
                capture_metadata(chunk)
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                finish_reason = choice.finish_reason or finish_reason
                delta = choice.delta
                thought = getattr(delta, "reasoning_content", None) or ""
                content_delta = getattr(delta, "content", None) or ""
                received_chars += len(thought) + len(content_delta)
                self._control.limit(received_chars)
                if thought:
                    thoughts.append(thought)
                    emit("reasoning", thought)
                if content_delta:
                    texts.append(content_delta)
                    emit("content", content_delta)
            self.last_reasoning = "".join(thoughts)
            if finish_reason not in {None, "stop"}:
                raise ValueError(f"Incomplete stream ({finish_reason})")
            if finish_reason is None:
                raise ValueError("流式连接提前结束，未收到完成标记；本轮不执行工具。")
            text = "".join(texts).strip()
            if not text:
                raise ValueError(f"接口未返回最终正文（finish_reason={finish_reason}）；可能输出预算耗尽。")
            return text
        except RequestStopped:
            raise
        except Exception as exc:
            from release_safety import safe_error
            self._record_error_usage(exc)
            self._control.check()
            logging.error("OpenAI request failed: %s", type(exc).__name__)
            return "Error: " + safe_error(exc, self.api_key)
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
                        buffer = io.BytesIO()
                        image.save(buffer, format="JPEG", quality=85)
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
                    doc = fitz.open(path)
                    clipped = fitz.open()
                    limit = int(5.5 * 1024 * 1024)
                    for page in doc:
                        if clipped.page_count >= 4:
                            break
                        clipped.insert_pdf(doc, from_page=page.number, to_page=page.number)
                        if len(base64.b64encode(clipped.write())) > limit:
                            if clipped.page_count > 1:
                                clipped.delete_page(clipped.page_count - 1)
                            else:
                                clipped.close()
                                doc.close()
                                return self._fallback_single_page_to_image(str(path))
                            break
                    data = clipped.write()
                    clipped.close()
                    doc.close()
                except Exception as exc:
                    logging.warning("PDF clipping failed: %s", exc)
            return {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": base64.b64encode(data).decode()}}
        data, mime = self._read_and_optimize_file(str(path))
        return {"type": "image", "source": {"type": "base64", "media_type": mime, "data": base64.b64encode(data).decode()}} if data and mime else None

    def _fallback_single_page_to_image(self, file_path: str, page_idx: int = 0) -> dict | None:
        try:
            doc = fitz.open(file_path)
            pix = doc[page_idx].get_pixmap(matrix=fitz.Matrix(150 / 72, 150 / 72))
            doc.close()
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
                doc = fitz.open(path)
                images = []
                for i, page in enumerate(doc):
                    if i >= 4:
                        break
                    pix = page.get_pixmap(matrix=fitz.Matrix(150 / 72, 150 / 72))
                    images.append(base64.b64encode(pix.tobytes("jpeg")).decode())
                doc.close()
                return images
            except Exception as exc:
                logging.error("PDF-to-image conversion failed: %s", exc)
                return []
        data, _ = self._read_and_optimize_file(str(path))
        return [base64.b64encode(data).decode()] if data else []

    def _http_post(self, url: str, headers: dict, payload: dict, extractor) -> str:
        retryable = {429, 500, 502, 503, 504}
        attempts = self._control.policy.attempts
        for attempt in range(1, attempts + 1):
            response = None
            started = time.monotonic()
            connect_timeout, read_timeout = 0.0, 0.0
            try:
                self._begin_usage_attempt()
                # Gemini/Claude return nothing until generation has finished:
                # wait for a complete response, not for a streaming chunk gap.
                connect_timeout, read_timeout = self._control.timeouts(complete=True)
                response = requests.post(url, headers=headers, data=json.dumps(payload),
                                         timeout=(connect_timeout, read_timeout), stream=True)
                try:
                    if hasattr(response, 'raw') and hasattr(response.raw, 'read1'):
                        chunks, size = [], 0
                        while True:
                            self._control.check()
                            chunk = response.raw.read1(8192, decode_content=True)
                            if not chunk:
                                break
                            size += len(chunk)
                            if size > self._control.policy.max_response_chars * 4:
                                raise ResponseLimitExceeded('Provider response exceeds the configured size limit')
                            chunks.append(chunk)
                        reply = json.loads(b''.join(chunks))
                    else:
                        reply = response.json()  # Small custom/mock transports.
                except (ValueError, AttributeError):
                    reply = {}
                self._control.check()
                if isinstance(reply, dict):
                    self.last_response_model = reply.get("modelVersion") or reply.get("model")
                    if "usageMetadata" in reply or "usage" in reply:
                        self._record_usage(reply.get("usageMetadata", reply.get("usage")))
                if response.ok:
                    answer = extractor(reply)
                    self._control.limit(len(answer))
                    return answer
                if response.status_code in retryable and attempt < attempts:
                    self._control.pause(self._control.policy.backoff * 2 ** (attempt - 1))
                    continue
                logging.error("HTTP %s", response.status_code)
                return f"HTTP error {response.status_code}"
            except requests.exceptions.ConnectionError as exc:
                # Includes ConnectTimeout: the provider never received the request.
                self._control.check()
                if attempt == attempts:
                    return f"Error after {attempts} attempts: {type(exc).__name__}"
                self._control.pause(self._control.policy.backoff * 2 ** (attempt - 1))
            except requests.exceptions.Timeout as exc:
                self._control.check()
                elapsed = time.monotonic() - started
                if connection_setup_timeout(exc, elapsed, connect_timeout, read_timeout):
                    # Through an HTTP(S) proxy, a slow CONNECT tunnel is raised
                    # as ReadTimeout after the *connect* timeout.  The request
                    # was never sent, so it is retried like a connection error.
                    if attempt == attempts:
                        return (f"Error after {attempts} attempts: ConnectTimeout (connection or proxy tunnel "
                                f"setup took longer than {connect_timeout:g} s). Increase "
                                "WORKBENCH_CONNECT_TIMEOUT_SECONDS if the network proxy is slow.")
                    self._control.pause(self._control.policy.backoff * 2 ** (attempt - 1))
                    continue
                # A read timeout means the provider may still be generating and
                # billing this request. Never start a second paid generation.
                return (f"Error: no complete response within {read_timeout:g} s "
                        f"({type(exc).__name__}); not retried automatically. Increase "
                        "WORKBENCH_RESPONSE_TIMEOUT_SECONDS if this model needs longer.")
            except RequestStopped:
                raise
            except Exception as exc:
                logging.error("Unexpected request error: %s", type(exc).__name__)
                return f"Error: invalid provider response ({type(exc).__name__})"
            finally:
                if response is not None and hasattr(response, 'close'):
                    response.close()
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

