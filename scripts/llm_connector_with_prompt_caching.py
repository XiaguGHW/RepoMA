"""Bosch Model Farm connector with prompt caching and safe file handling.

Supports Gemini, Claude, GPT/OpenAI-compatible, DeepSeek and Llama model IDs.
The class exposes the interface used by the Task 3 scripts:

    LLMConnector(model_name, api_key).ask_about_files(...)

It is reconstructed from the current company-PC connector and includes the
missing ``_get_mime_type`` helper that caused PDF upload failures.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import requests

try:
    from openai import OpenAI
    _OPENAI_AVAILABLE = True
except ImportError:  # pragma: no cover - only used by GPT-compatible models
    OpenAI = None
    _OPENAI_AVAILABLE = False

try:
    import fitz
    _FITZ_AVAILABLE = True
except ImportError:  # pragma: no cover - PDF conversion has a clear warning
    fitz = None
    _FITZ_AVAILABLE = False

try:
    from PIL import Image
    _PIL_AVAILABLE = True
except ImportError:  # pragma: no cover - images are simply sent unchanged
    Image = None
    _PIL_AVAILABLE = False


FARM_BASE = "https://aoai-farm.bosch-temp.com/api"
MIME_MAP = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


class LLMConnector:
    """Universal Bosch Model Farm connector with Claude prompt caching."""

    def __init__(self, model_name: str, api_key: str, session_id: str | None = None):
        self.model_name = model_name
        self.api_key = api_key
        self.session_id = session_id
        self.last_usage: dict[str, Any] | None = None
        self._family = self._detect_family(model_name)
        logging.info(
            "LLMConnector (with caching) ready — model=%r, family=%r, session_id=%r",
            model_name, self._family, self.session_id,
        )

    @staticmethod
    def _detect_family(model_name: str) -> str:
        name = model_name.casefold()
        if name.startswith("gemini") or "gemini" in name:
            return "gemini"
        if name.startswith("claude") or "claude" in name:
            return "claude"
        if (
            name.startswith(("gpt", "o1", "o3", "llama", "glm", "deepseek"))
            or "openai-" in name
            or "llama" in name
            or "glm" in name
            or "deepseek" in name
        ):
            return "openai"
        raise ValueError(
            f"Cannot determine model family from {model_name!r}. "
            "Supported prefixes: gemini-, claude-, gpt-, o1-, o3-, llama-, glm-, deepseek-."
        )

    def analyze_documents(
        self,
        file_paths: list[str],
        user_prompt: str,
        system_prompt: str | None = None,
        generation_config: dict[str, Any] | None = None,
    ) -> str:
        dispatch = {
            "gemini": self._call_gemini,
            "claude": self._call_claude,
            "openai": self._call_openai,
        }
        return dispatch[self._family](file_paths, user_prompt, system_prompt, generation_config or {})

    def ask_about_files(
        self,
        file_paths: list[str],
        question: str,
        system_prompt: str | None = None,
        generation_config: dict[str, Any] | None = None,
    ) -> str:
        return self.analyze_documents(file_paths, question, system_prompt, generation_config)

    def get_last_token_usage(self) -> dict[str, Any] | None:
        return self.last_usage

    def _get_common_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.session_id:
            headers["X-SESSION-ID"] = str(self.session_id)
        return headers

    @staticmethod
    def _get_mime_type(file_path: str) -> str:
        """Return a safe MIME type for all attachment helpers.

        This method intentionally exists separately from ``MIME_MAP`` because
        the prior connector called it from ``_read_and_optimize_file`` but did
        not define it, causing AttributeError for every PDF upload.
        """
        return MIME_MAP.get(Path(file_path).suffix.casefold(), "application/octet-stream")

    def _call_gemini(
        self, file_paths: list[str], user_prompt: str, system_prompt: str | None,
        generation_config: dict[str, Any],
    ) -> str:
        url = f"{FARM_BASE}/google/v1/publishers/google/models/{self.model_name}:generateContent"
        headers = self._get_common_headers()
        headers.update({
            "genaiplatform-farm-subscription-key": self.api_key,
            "Content-Type": "application/json",
        })
        parts = []
        for file_path in file_paths:
            part = self._file_to_gemini_part(file_path)
            if part:
                parts.append(part)
        parts.append({"text": user_prompt})
        payload: dict[str, Any] = {"contents": [{"role": "user", "parts": parts}]}
        if system_prompt:
            payload["system_instruction"] = {"parts": [{"text": system_prompt}]}
        if generation_config:
            payload["generationConfig"] = generation_config
            logging.info("generationConfig: %s", generation_config)
        return self._http_post(url, headers, payload, self._extract_gemini_text)

    @staticmethod
    def _extract_gemini_text(response_json: dict[str, Any]) -> str:
        candidates = response_json.get("candidates", [])
        if candidates and candidates[0].get("content", {}).get("parts"):
            for part in candidates[0]["content"]["parts"]:
                if "text" in part:
                    return str(part["text"])
        reason = (candidates or [{}])[0].get("finishReason", "unknown")
        return f"(no text content, finishReason={reason})"

    def _call_claude(
        self, file_paths: list[str], user_prompt: str, system_prompt: str | None,
        generation_config: dict[str, Any],
    ) -> str:
        url = f"{FARM_BASE}/google/v1/publishers/anthropic/models/{self.model_name}:rawPredict"
        current_session = self.session_id or f"caching_session_{uuid.uuid4().hex[:12]}"
        self.session_id = current_session
        headers = self._get_common_headers()
        headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-SESSION-ID": current_session,
        })
        content: list[dict[str, Any]] = []
        for file_path in file_paths:
            block = self._file_to_claude_block(file_path)
            if isinstance(block, list):
                content.extend(block)
            elif block:
                content.append(block)
        content.append({"type": "text", "text": user_prompt})

        max_tokens = min(int(generation_config.get("maxOutputTokens", 8192)), 32000)
        payload: dict[str, Any] = {
            "anthropic_version": "vertex-2023-10-16",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": content}],
        }
        if system_prompt:
            payload["system"] = [{
                "type": "text", "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }]
        thinking_prefixes = ("claude-opus-4", "claude-sonnet-4", "claude-sonnet-5")
        is_thinking_model = self.model_name.casefold().startswith(thinking_prefixes)
        temperature = generation_config.get("temperature")
        if temperature is not None and not is_thinking_model:
            try:
                temperature_value = float(temperature)
            except (TypeError, ValueError):
                temperature_value = 0.0
            if temperature_value > 0:
                payload["temperature"] = temperature_value
            else:
                logging.info("Claude temperature=0/default: omitting field to avoid Farm 400.")
        return self._http_post(url, headers, payload, self._extract_claude_text_with_usage)

    def _extract_claude_text_with_usage(self, response_json: dict[str, Any]) -> str:
        usage = response_json.get("usage", {}) or {}
        self.last_usage = {
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "cache_creation_input_tokens": usage.get("cache_creation_input_tokens", 0) or 0,
            "cache_read_input_tokens": usage.get("cache_read_input_tokens", 0) or 0,
        }
        logging.info(
            "[BMF Caching Monitor] Input Tokens: %s | Output Tokens: %s | New Write: %s | Cache Read: %s",
            self.last_usage["input_tokens"], self.last_usage["output_tokens"],
            self.last_usage["cache_creation_input_tokens"], self.last_usage["cache_read_input_tokens"],
        )
        return self._extract_claude_text(response_json)

    @staticmethod
    def _extract_claude_text(response_json: dict[str, Any]) -> str:
        for item in response_json.get("content", []) or []:
            if item.get("type") == "text" and "text" in item:
                return str(item["text"])
        return "(no text content)"

    def _call_openai(
        self, file_paths: list[str], user_prompt: str, system_prompt: str | None,
        generation_config: dict[str, Any],
    ) -> str:
        if not _OPENAI_AVAILABLE:
            return "Error: openai package must be installed — run: pip install openai"
        name = self.model_name.casefold()
        if "glm" in name or "openai-" in name:
            base_url = f"{FARM_BASE}/google/v1/endpoints/{self.model_name}/openai"
        else:
            base_url = f"{FARM_BASE}/openai/deployments/{self.model_name}"
        headers = self._get_common_headers()
        headers["genaiplatform-farm-subscription-key"] = self.api_key
        client = OpenAI(api_key="dummy-key", base_url=base_url, default_headers=headers)

        content: list[dict[str, Any]] = [{"type": "text", "text": user_prompt}]
        for file_path in file_paths:
            for encoded_image in self._file_to_openai_images(file_path):
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{encoded_image}"},
                })
        messages: list[dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": content})

        max_tokens = int(generation_config.get("maxOutputTokens", 4096))
        is_reasoning_model = self.model_name.casefold().startswith(("gpt-5", "o1", "o3", "deepseek-r1"))
        request: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "timeout": 300,
            "extra_query": {"api-version": "2024-08-01-preview"} if "openai" in base_url else {},
        }
        if is_reasoning_model:
            request["max_completion_tokens"] = max_tokens
        else:
            request["max_tokens"] = max_tokens
            if generation_config.get("temperature") is not None:
                request["temperature"] = generation_config["temperature"]
        try:
            response = client.chat.completions.create(**request)
            usage = getattr(response, "usage", None)
            self.last_usage = {
                "input_tokens": getattr(usage, "prompt_tokens", None),
                "output_tokens": getattr(usage, "completion_tokens", None),
            } if usage else None
            return (response.choices[0].message.content or "").strip()
        except Exception as error:
            logging.error("OpenAI call failed: %s", error)
            return f"Error: {error}"

    def _read_b64(self, file_path: str) -> tuple[str, str]:
        mime_type = self._get_mime_type(file_path)
        if mime_type == "application/octet-stream":
            logging.warning("Unsupported file type %r — skipping: %s", Path(file_path).suffix, file_path)
            return "", ""
        try:
            with open(file_path, "rb") as handle:
                return base64.b64encode(handle.read()).decode("utf-8"), mime_type
        except OSError as error:
            logging.error("Cannot read %s: %s", file_path, error)
            return "", ""

    def _read_and_optimize_file(self, file_path: str) -> tuple[bytes, str]:
        """Compress image attachments, but preserve PDFs unchanged with a correct MIME type."""
        path = Path(file_path)
        if not path.is_file():
            logging.error("File not found — skipping: %s", file_path)
            return b"", ""
        original_size = path.stat().st_size
        extension = path.suffix.casefold()
        if extension in IMAGE_EXTENSIONS and _PIL_AVAILABLE:
            try:
                with Image.open(path) as image:
                    if image.mode != "RGB":
                        image = image.convert("RGB")
                    if image.width > 2048 or image.height > 2048:
                        image.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
                    buffer = io.BytesIO()
                    image.save(buffer, format="JPEG", quality=85)
                    optimized = buffer.getvalue()
                    logging.info(
                        "Compressed %r: %.1f KB -> %.1f KB",
                        path.name, original_size / 1024, len(optimized) / 1024,
                    )
                    return optimized, "image/jpeg"
            except Exception as error:
                logging.warning("Image compression failed for %s: %s. Sending raw.", path.name, error)
        try:
            data = path.read_bytes()
            logging.info("Sending raw file %r: %.1f KB", path.name, original_size / 1024)
            return data, self._get_mime_type(file_path)
        except OSError as error:
            logging.error("Cannot read %s: %s", file_path, error)
            return b"", ""

    def _file_to_gemini_part(self, file_path: str) -> dict[str, Any] | None:
        data, mime_type = self._read_and_optimize_file(file_path)
        if not data or not mime_type:
            return None
        return {"inlineData": {"mimeType": mime_type, "data": base64.b64encode(data).decode("utf-8")}}

    def _file_to_claude_block(self, file_path: str) -> dict[str, Any] | list[dict[str, Any]] | None:
        path = Path(file_path)
        extension = path.suffix.casefold()
        if extension == ".pdf":
            if not path.is_file():
                logging.error("File not found: %s", path)
                return None
            size_mib = path.stat().st_size / (1024 * 1024)
            if size_mib < 4:
                encoded, mime_type = self._read_b64(str(path))
                return {"type": "document", "source": {"type": "base64", "media_type": mime_type, "data": encoded}} if encoded else None
            return self._large_pdf_to_claude_block(path)
        data, mime_type = self._read_and_optimize_file(str(path))
        if not data:
            return None
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": mime_type, "data": base64.b64encode(data).decode("utf-8")},
        }

    def _large_pdf_to_claude_block(self, path: Path) -> dict[str, Any] | None:
        if not _FITZ_AVAILABLE:
            logging.warning("PyMuPDF unavailable; sending large PDF raw: %s", path)
            encoded, mime_type = self._read_b64(str(path))
            return {"type": "document", "source": {"type": "base64", "media_type": mime_type, "data": encoded}} if encoded else None
        try:
            document = fitz.open(path)
            shortened = fitz.open()
            safe_b64_limit = int(5.5 * 1024 * 1024)
            pages_added = 0
            for index in range(min(4, len(document))):
                shortened.insert_pdf(document, from_page=index, to_page=index)
                encoded_length = len(base64.b64encode(shortened.write()))
                if encoded_length > safe_b64_limit:
                    if shortened.page_count > 1:
                        shortened.delete_page(shortened.page_count - 1)
                    else:
                        shortened.close()
                        document.close()
                        return self._pdf_page_as_claude_image(path, 0)
                    break
                pages_added += 1
            pdf_bytes = shortened.write()
            shortened.close()
            document.close()
            logging.info("Large PDF trimmed: %r kept %d page(s)", path.name, pages_added)
            return {
                "type": "document",
                "source": {"type": "base64", "media_type": "application/pdf", "data": base64.b64encode(pdf_bytes).decode("utf-8")},
            }
        except Exception as error:
            logging.error("Large PDF processing failed for %s: %s", path, error)
            encoded, mime_type = self._read_b64(str(path))
            return {"type": "document", "source": {"type": "base64", "media_type": mime_type, "data": encoded}} if encoded else None

    def _pdf_page_as_claude_image(self, path: Path, page_index: int = 0) -> dict[str, Any] | None:
        try:
            document = fitz.open(path)
            page = document[page_index]
            pixmap = page.get_pixmap(matrix=fitz.Matrix(150 / 72, 150 / 72), alpha=False)
            document.close()
            return {
                "type": "image",
                "source": {
                    "type": "base64", "media_type": "image/jpeg",
                    "data": base64.b64encode(pixmap.tobytes("jpeg")).decode("utf-8"),
                },
            }
        except Exception as error:
            logging.error("PDF image fallback failed for %s: %s", path, error)
            return None

    def _file_to_openai_images(self, file_path: str) -> list[str]:
        path = Path(file_path)
        extension = path.suffix.casefold()
        if extension == ".pdf":
            if not _FITZ_AVAILABLE:
                logging.warning("PyMuPDF (fitz) not installed — PDF skipped. Run: pip install pymupdf")
                return []
            images: list[str] = []
            try:
                document = fitz.open(path)
                for index, page in enumerate(document):
                    if index >= 4:
                        break
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(150 / 72, 150 / 72), alpha=False)
                    images.append(base64.b64encode(pixmap.tobytes("jpeg")).decode("utf-8"))
                document.close()
            except Exception as error:
                logging.error("PDF->image conversion failed for %s: %s", path, error)
            return images
        if extension in IMAGE_EXTENSIONS:
            data, _ = self._read_and_optimize_file(str(path))
            return [base64.b64encode(data).decode("utf-8")] if data else []
        logging.warning("Unsupported OpenAI attachment type %s: %s", extension, path)
        return []

    # Backward-compatible public spelling used by older Task 3 scripts.
    file_to_openai_images = _file_to_openai_images

    def _http_post(
        self, url: str, headers: dict[str, str], payload: dict[str, Any],
        extractor: Callable[[dict[str, Any]], str],
    ) -> str:
        logging.info("POST -> %s (Session: %s)", url, self.session_id)
        retryable_status_codes = {429, 500, 502, 503, 504}
        max_attempts = 4
        for attempt in range(1, max_attempts + 1):
            try:
                response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=300)
                if not response.ok:
                    if response.status_code in retryable_status_codes and attempt < max_attempts:
                        wait_seconds = 2 ** attempt
                        logging.warning(
                            "HTTP %s on attempt %s/%s. Retry in %s s.",
                            response.status_code, attempt, max_attempts, wait_seconds,
                        )
                        time.sleep(wait_seconds)
                        continue
                    logging.error("HTTP request failed, final status code: %s", response.status_code)
                    try:
                        logging.error("BMF response details: %s", json.dumps(response.json(), indent=2, ensure_ascii=False))
                    except ValueError:
                        logging.error("BMF raw error response: %s", response.text)
                    return f"HTTP error {response.status_code}"
                response_json = response.json()
                self.last_usage = response_json.get("usageMetadata", self.last_usage)
                return extractor(response_json)
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as error:
                if attempt == max_attempts:
                    logging.error("Request failed after %s attempts: %s", max_attempts, error)
                    return f"Error after {max_attempts} attempts: {error}"
                wait_seconds = 2 ** attempt
                logging.warning("Connection error on attempt %s/%s: %s. Retry in %s s.", attempt, max_attempts, error, wait_seconds)
                time.sleep(wait_seconds)
            except Exception as error:
                logging.exception("Unexpected connector error")
                return f"Error: {error}"
        return "Error: request failed"

