# 原版注释版（根据你发来的原始代码截图转写）。
# 原代码的执行顺序和逻辑保持不变；仅删除真实 API key，并加入少量中文 # 注释。

import requests
import json
import logging
import os
import base64


# 配置终端中的日志显示格式。
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class BoschLLMConnector:
    # 创建一个连接器对象：保存模型名、API key 和请求地址。
    def __init__(self, model_name, api_key, base_url):
        self.model_name = model_name
        self.api_key = api_key

        self.base_url = base_url.rstrip("/")
        self.url = f"{self.base_url}/publishers/google/models/{self.model_name}:generateContent"

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # 保存最近一次请求的 token 统计。
        self.last_usage = None

    # 底层函数：真正把准备好的 JSON 请求发给 Bosch LLM Farm。
    def _send_request(self, payload: dict, generation_config: dict = None):
        try:
            if generation_config:
                payload["generationConfig"] = generation_config

            logging.info(f"Sende Anfrage an Modell: {self.model_name}")
            response = requests.post(self.url, headers=self.headers, json=payload)

            response.raise_for_status()
            result = response.json()

            self.last_usage = result.get("usageMetadata", {})

            candidates = result.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                text_parts = [part["text"] for part in parts if "text" in part]
                if text_parts:
                    return "".join(text_parts)

            logging.warning("Keine Textantwort in der Modellantwort gefunden.")
            return ""

        except requests.exceptions.HTTPError as e:
            logging.error(f"HTTP-Fehler: {e}")
            return f"HTTP-Fehler: {e}"
        except requests.exceptions.RequestException as e:
            logging.error(f"Anfragefehler: {e}")
            return f"Anfragefehler: {e}"
        except (ValueError, KeyError, IndexError) as e:
            logging.error(f"Fehler beim Verarbeiten der Antwort: {e}")
            return f"Antwortverarbeitungsfehler: {e}"

    # 只输入文字时使用的入口。
    def ask(self, prompt: str):
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ]
        }
        return self._send_request(payload)

    # 输入“文字问题 + 多个 PDF/图片”时使用的核心函数。
    def analyze_documents(
        self,
        file_paths: list,
        user_prompt: str,
        system_prompt: str = None,
        generation_config: dict = None,
    ):
        logging.info(f"Analysiere {len(file_paths)} Dokument(e) für die Anfrage...")

        # 第一部分是问题文字，后续循环会把每个文件加入同一个请求。
        user_parts = [{"text": user_prompt}]

        for file_path in file_paths:
            if not os.path.exists(file_path):
                logging.error(f"Datei nicht gefunden: {file_path}")
                continue

            try:
                # 以二进制方式读取 PDF/图片，再编码成可放入 JSON 的 Base64 数据。
                with open(file_path, "rb") as f:
                    file_bytes = f.read()

                base64_data = base64.b64encode(file_bytes).decode("utf-8")

                ext = os.path.splitext(file_path)[1].lower()
                mime_map = {
                    ".pdf": "application/pdf",
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                }

                if ext not in mime_map:
                    logging.warning(f"Nicht unterstützter Dateityp übersprungen: {file_path}")
                    continue

                user_parts.append(
                    {
                        "inline_data": {
                            "mime_type": mime_map[ext],
                            "data": base64_data,
                        }
                    }
                )
                logging.info(f"Datei hinzugefügt: {file_path}")

            except Exception as e:
                logging.error(f"Fehler beim Lesen von {file_path}: {e}")

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": user_parts,
                }
            ]
        }

        # 可选的全局规则（例如分类时只允许输出给定类别）。
        if system_prompt:
            payload["system_instruction"] = {
                "parts": [{"text": system_prompt}]
            }

        return self._send_request(payload, generation_config)

    # 更方便的多文件入口；实际工作交给 analyze_documents()。
    def ask_about_files(
        self,
        file_paths: list,
        question: str,
        system_prompt: str = None,
        generation_config: dict = None,
    ):
        return self.analyze_documents(
            file_paths=file_paths,
            user_prompt=question,
            system_prompt=system_prompt,
            generation_config=generation_config,
        )

    def get_last_token_usage(self):
        return self.last_usage


# 这一段仅在直接运行该文件时执行；被其他 .py 文件 import 时不会执行。
if __name__ == "__main__":
    # 原始真实 key 已删除。运行时请填入自己的安全 key，或改为从环境变量读取。
    BOSCH_FARM_API_KEY = "<YOUR_API_KEY>"
    MODEL_NAME = "gemini-2.5-pro"
    BASE_URL = "HIER_BOSCH_LLM_FARM_BASE_URL_EINTRAGEN"

    llm = BoschLLMConnector(
        model_name=MODEL_NAME,
        api_key=BOSCH_FARM_API_KEY,
        base_url=BASE_URL,
    )

    print("Test 1 - Textanfrage:")
    print(llm.ask("Welches Modell bist du?"))
    print("Token usage:", llm.get_last_token_usage())

    test_files = [
        "test.pdf",
        "test.png",
    ]
    existing_files = [path for path in test_files if os.path.exists(path)]

    if existing_files:
        print("\nTest 2 - Anfrage mit Dateien:")
        print(
            llm.ask_about_files(
                file_paths=existing_files,
                question="Beschreibe die bereitgestellten Dokumente kurz.",
            )
        )
        print("Token usage:", llm.get_last_token_usage())
    else:
        print("\nTest 2 übersprungen: Keine Testdateien gefunden.")
