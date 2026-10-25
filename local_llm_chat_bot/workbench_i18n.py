"""UI copy only: never translate source documents, class names or chat content."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

LANGUAGES = ("zh", "en", "de")
CATALOG_PATH = Path(__file__).with_name("workbench_i18n.json")


def validate_catalog(catalog: dict) -> None:
    messages = catalog["messages"]
    if set(messages) != set(LANGUAGES):
        raise ValueError("Catalog must contain exactly zh, en and de")
    keys = set(messages["zh"])
    for language in LANGUAGES:
        if set(messages[language]) != keys:
            raise ValueError(f"Translation keys differ for {language}")
        for key, value in messages[language].items():
            if not re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+", key):
                raise ValueError(f"Invalid semantic key: {key}")
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Empty translation: {language}/{key}")
            expected = set(re.findall(r"\{(\w+)\}", messages["zh"][key]))
            if set(re.findall(r"\{(\w+)\}", value)) != expected:
                raise ValueError(f"Placeholder mismatch: {language}/{key}")
            if language != "zh" and re.search(r"[\u4e00-\u9fff]", value):
                raise ValueError(f"Unexpected Chinese UI copy: {language}/{key}")
    for key in catalog["legacy_keys"].values():
        if key not in keys:
            raise ValueError(f"Unknown compatibility key: {key}")


def load_catalog() -> dict:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    validate_catalog(catalog)
    return catalog


@lru_cache(maxsize=1)
def runtime_messages():
    return load_catalog()['messages']


class UIMessage(str):
    """Compatible text plus an explicit key/parameters for later UI redraws."""
    message_key: str
    language: str
    params: dict[str, Any]

    def __new__(cls, key, language='zh', **params):
        language = language if language in LANGUAGES else 'zh'
        template = runtime_messages()[language][key]
        text = re.sub(r'\{(\w+)\}', lambda match: str(params.get(match[1], match[0])), template)
        instance = super().__new__(cls, text)
        instance.message_key = key
        instance.language = language
        instance.params = params
        return instance

    def payload(self):
        def encode(value):
            if isinstance(value, UIMessage):
                return value.payload()
            if isinstance(value, dict):
                return {key: encode(item) for key, item in value.items()}
            if isinstance(value, (list, tuple)):
                return [encode(item) for item in value]
            return value if value is None or isinstance(value, (str, int, float, bool)) else str(value)
        return {'message_key': self.message_key, 'params': {key: encode(value) for key, value in self.params.items()}}


def localize_message(value, language='zh'):
    if not isinstance(value, UIMessage):
        return value  # Model/user/source text must never be inferred or translated.
    return UIMessage(value.message_key, language, **{
        key: localize_message(item, language) for key, item in value.params.items()})


def catalog_script_json() -> str:
    # Safe inside an inline script, including future copy containing HTML.
    return (json.dumps(load_catalog(), ensure_ascii=False)
            .replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("&", "\\u0026").replace("\u2028", "\\u2028")
            .replace("\u2029", "\\u2029"))
