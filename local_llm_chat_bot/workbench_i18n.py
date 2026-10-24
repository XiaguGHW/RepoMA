"""UI copy only: never translate source documents, class names or chat content."""
from __future__ import annotations

import json
import re
from pathlib import Path

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


def catalog_script_json() -> str:
    # Safe inside an inline script, including future copy containing HTML.
    return (json.dumps(load_catalog(), ensure_ascii=False)
            .replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("&", "\\u0026").replace("\u2028", "\\u2028")
            .replace("\u2029", "\\u2029"))
