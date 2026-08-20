"""Bosch Model Farm 统一连接器（学习注释版）。

同一个 ``LLMConnector`` 会依据模型名，自动选择 Gemini、Claude 或 GPT 的
请求格式；调用方只需要使用 ``ask_about_files(...)``。
"""

import os
import json
import base64
import logging

import requests

try:
    # 只有使用 GPT / OpenAI 路线时才需要这个 SDK。
    from openai import OpenAI
    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False

try:
    # GPT 读取 PDF 时，用它把每页转成 JPEG。
    import fitz
    _FITZ_AVAILABLE = True
except ImportError:
    _FITZ_AVAILABLE = False


# Bosch Model Farm 的基础地址：建议在环境变量中配置，避免把公司地址写死在学习版中。
FARM_BASE = os.getenv("BOSCH_FARM_BASE_URL", "")

# 只支持 pipeline 中实际收集的 PDF 和常见图片格式。
MIME_MAP = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


class LLMConnector:
    def __init__(self, model_name: str, api_key: str):
        self.model_name = model_name
        self.api_key = api_key
        self.last_usage = None
        # 创建对象时先确认后续该走哪条模型调用路线。
        self._family = self._detect_family(model_name)

    @staticmethod
    def _detect_family(model_name: str) -> str:
        name = model_name.lower()

        if name.startswith("gemini") or "gemini" in name:
            return "gemini"
        if name.startswith("claude") or "claude" in name:
            return "claude"
        if (
            name.startswith("gpt") or name.startswith("o1") or name.startswith("o3")
            or "openai-gpt" in name or "openai-o1" in name or "openai-o3" in name
        ):
            return "openai"

        raise ValueError(
            f"Cannot determine model family from '{model_name}'. "
            "Supported prefixes: gemini-, claude-, gpt-, o1-, o3- "
            "(or full Bosch Farm deployment names containing those prefixes)"
        )

    # 对 main.py 的统一入口：内部根据 self._family 自动分流。
    def analyze_documents(
        self,
        file_paths: list,
        user_prompt: str,
        system_prompt: str = None,
        generation_config: dict = None,
    ) -> str:
        """Send files (PDFs / images) and a prompt to the selected LLM."""
        dispatch = {
            "gemini": self._call_gemini,
            "claude": self._call_claude,
            "openai": self._call_openai,
        }
        return dispatch[self._family](
            file_paths, user_prompt, system_prompt, generation_config
        )

    def ask_about_files(
        self,
        file_paths: list,
        question: str,
        system_prompt: str = None,
        generation_config: dict = None,
    ) -> str:
        """Convenience alias – 'question' maps to 'user_prompt'."""
        return self.analyze_documents(
            file_paths, question, system_prompt, generation_config
        )

    def get_last_token_usage(self) -> dict:
        """Returns token usage metadata from the last successful call."""
        return self.last_usage

    # ------------------------------------------------------------------------
    # Gemini - Google native generateContent API
    # ------------------------------------------------------------------------
    def _call_gemini(self, file_paths, user_prompt, system_prompt, generation_config):
        url = (
            f"{FARM_BASE}/google/v1/publishers/google/models"
            f"/{self.model_name}:generateContent"
        )

        headers = {
            "genaiplatform-farm-subscription-key": self.api_key,
            "Content-Type": "application/json",
        }

        user_parts = [{"text": user_prompt}]
        for fp in file_paths:
            part = self._file_to_gemini_part(fp)
            if part:
                user_parts.append(part)

        payload = {"contents": [{"role": "user", "parts": user_parts}]}
        if system_prompt:
            payload["system_instruction"] = {"parts": [{"text": system_prompt}]}
        if generation_config:
            payload["generationConfig"] = generation_config
            logging.info(f"generationConfig: {generation_config}")

        return self._http_post(url, headers, payload, self._extract_gemini_text)

    @staticmethod
    def _extract_gemini_text(rj: dict) -> str:
        candidates = rj.get("candidates", [])
        if candidates and candidates[0].get("content", {}).get("parts"):
            for part in candidates[0]["content"]["parts"]:
                if "text" in part:
                    return part["text"]
        reason = (rj.get("candidates") or [{}])[0].get("finishReason", "unknown")
        return f"(no text content, finishReason={reason})"

    # ------------------------------------------------------------------------
    # Claude - Anthropic rawPredict via Bosch Farm
    # ------------------------------------------------------------------------
    def _call_claude(self, file_paths, user_prompt, system_prompt, generation_config):
        url = (
            f"{FARM_BASE}/google/v1/publishers/anthropic/models"
            f"/{self.model_name}:rawPredict"
        )
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        content = []
        for fp in file_paths:
            block = self._file_to_claude_block(fp)
            if block:
                content.append(block)
        content.append({"type": "text", "text": user_prompt})

        # 将 main.py 使用的通用 generation_config 改成 Claude 的参数名称。
        max_tokens = 8192
        temperature = None
        if generation_config:
            max_tokens = min(int(generation_config.get("maxOutputTokens", max_tokens)), 32000)
            temperature = generation_config.get("temperature")

        # Claude Opus/Sonnet 4.x 不接受 temperature，否则服务会返回 HTTP 400。
        _thinking_prefixes = ("claude-opus-4", "claude-sonnet-4")
        is_thinking_model = any(self.model_name.lower().startswith(p) for p in _thinking_prefixes)

        payload = {
            "anthropic_version": "vertex-2023-10-16",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": content}],
        }
        if system_prompt:
            payload["system"] = system_prompt
        if temperature is not None and not is_thinking_model:
            payload["temperature"] = temperature

        return self._http_post(url, headers, payload, self._extract_claude_text)

    @staticmethod
    def _extract_claude_text(rj: dict) -> str:
        content = rj.get("content", [])
        if content and "text" in content[0]:
            return content[0]["text"]
        return "(no text content)"

    # ------------------------------------------------------------------------
    # OpenAI / GPT – Azure OpenAI SDK via Bosch Farm
    # PDFs are converted to JPEG page images via PyMuPDF.
    # ------------------------------------------------------------------------
    def _call_openai(self, file_paths, user_prompt, system_prompt, generation_config):
        if not _OPENAI_AVAILABLE:
            return "Error: 'openai' package not installed – run: pip install openai"

        base_url = f"{FARM_BASE}/openai/deployments/{self.model_name}"
        client = OpenAI(
            api_key="dummy-key",
            base_url=base_url,
            default_headers={"genaiplatform-farm-subscription-key": self.api_key},
        )

        msg_content = [{"type": "text", "text": user_prompt}]
        for fp in file_paths:
            for img_b64 in self._file_to_openai_images(fp):
                msg_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                })

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": msg_content})

        max_tokens = 8192
        temperature = None
        if generation_config:
            max_tokens = int(generation_config.get("maxOutputTokens", max_tokens))
            temperature = generation_config.get("temperature")

        # 旧版 gpt-4o 的输出上限更低；其他部署在此连接器中限制到 16384。
        if self.model_name == "gpt-4o-2024-05-13":
            max_tokens = min(max_tokens, 4096)
        else:
            max_tokens = min(max_tokens, 16384)

        try:
            kwargs = {
                "model": self.model_name,
                "messages": messages,
                "max_tokens": max_tokens,
                "timeout": 300,
            }
            if temperature is not None:
                kwargs["temperature"] = temperature
            response = client.chat.completions.create(**kwargs)
            return response.choices[0].message.content or "(no text content)"
        except Exception as e:
            logging.error(f"OpenAI request failed: {e}", exc_info=True)
            return f"Error: {e}"

    # ------------------------------------------------------------------------
    # File → model-specific payload helpers
    # ------------------------------------------------------------------------
    def _read_b64(self, file_path: str) -> tuple:
        """Returns (base64_str, mime_type) or ('', '') on error/unsupported type."""
        ext = os.path.splitext(file_path)[1].lower()
        mime = MIME_MAP.get(ext, "")
        if not mime:
            logging.warning(f"Unsupported file type '{ext}' - skipping: {file_path}")
            return "", ""
        if not os.path.exists(file_path):
            logging.error(f"File not found - skipping: {file_path}")
            return "", ""
        try:
            with open(file_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8"), mime
        except Exception as e:
            logging.error(f"Cannot read '{file_path}': {e}")
            return "", ""

    def _file_to_gemini_part(self, file_path: str) -> dict | None:
        """Gemini inline_data part (PDFs and images both supported natively)."""
        b64, mime = self._read_b64(file_path)
        return {"inline_data": {"mime_type": mime, "data": b64}} if b64 else None

    def _file_to_claude_block(self, file_path: str) -> dict | None:
        """Claude content block – PDF as document block, image as image block."""
        b64, mime = self._read_b64(file_path)
        if not b64:
            return None
        if mime == "application/pdf":
            return {
                "type": "document",
                "source": {"type": "base64", "media_type": mime, "data": b64},
            }
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": mime, "data": b64},
        }

    def _file_to_openai_images(self, file_path: str) -> list:
        """
        OpenAI image list from a file.
        PDFs → list of JPEG page images (up to 4 pages) via PyMuPDF.
        Images → single-element list with the raw image base64.
        """
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".pdf":
            if not _FITZ_AVAILABLE:
                logging.warning("PyMuPDF (fitz) not installed – PDF skipped. Run: pip install pymupdf")
                return []
            images = []
            try:
                doc = fitz.open(file_path)
                for i, page in enumerate(doc):
                    if i >= 4:
                        break
                    mat = fitz.Matrix(150 / 72, 150 / 72)
                    pix = page.get_pixmap(matrix=mat)
                    images.append(base64.b64encode(pix.tobytes("jpeg")).decode("utf-8"))
                doc.close()
            except Exception as e:
                logging.error(f"PDF→image conversion failed for '{file_path}': {e}")
            return images

        elif ext in (".png", ".jpg", ".jpeg"):
            try:
                with open(file_path, "rb") as f:
                    return [base64.b64encode(f.read()).decode("utf-8")]
            except Exception as e:
                logging.error(f"Cannot read image '{file_path}': {e}")
                return []

        return []

    # ------------------------------------------------------------------------
    # Shared HTTP POST helper
    # ------------------------------------------------------------------------
    def _http_post(self, url: str, headers: dict, payload: dict, extractor) -> str:
        logging.info(f"POST → {url}")
        try:
            r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=300)
            r.raise_for_status()
            rj = r.json()
            if "usageMetadata" in rj:
                self.last_usage = rj["usageMetadata"]
            return extractor(rj)
        except requests.exceptions.HTTPError as e:
            body = e.response.text[:500] if e.response else str(e)
            logging.error(f"HTTP {e.response.status_code}: {body}")
            return f"HTTP error {e.response.status_code}: {body}"
        except Exception as e:
            logging.error(f"Unexpected error: {e}", exc_info=True)
            return f"Error: {e}"
