"""Local browser workbench for the Bosch Farm code/document chat.

Run only on 127.0.0.1.  The browser is a local UI: paths, indexes, source
files, credentials and session data stay on the computer that starts it.
"""
from __future__ import annotations

from workbench_startup import (StartupConfig, StartupError, FarmEnvironment, HOST, bootstrap,
                               check_state_directory, check_port, install_command)


import difflib
import asyncio
import copy
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
import threading
import time
import uuid
from contextvars import ContextVar
from functools import wraps
from queue import Empty, Full, Queue
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

STARTUP_CONFIG = bootstrap() if __name__ == '__main__' else StartupConfig()
FARM_ENVIRONMENT = FarmEnvironment()

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
    from pydantic import BaseModel, Field
    import uvicorn

    from release_safety import (safe_error, normalize_usage, summarize_usage, context_state_error, valid_rule_profile,
                                redact_secrets)
    from dotenv import load_dotenv
    from workbench_i18n import catalog_script_json, UIMessage, localize_message
    from code_chat_agent import (PricingCatalog, ProjectState, SYSTEM, ensure_relative, classification_manifest,
                                 excerpt, parse_json, prompt_for, safe_name, sha256)
    from local_document_library import (LocalDocumentLibrary, SUPPORTED_DOCUMENT_EXTENSIONS,
                                        material_is_recommended, material_role, material_role_label)
    from llm_connector_with_prompt_caching import LLMConnector, farm_base_url
    from request_runtime import (RequestControl, RequestStopped, RequestCancelled, RequestTimedOut,
                                 ResponseLimitExceeded, AnswerPreview, looks_like_action)
except ImportError as exc:
    if __name__ != '__main__':
        raise
    print('Cannot import runtime module: ' + str(exc.name or 'required dependency') +
          '\nKeep all downloaded program files together. Repair this Python environment with:\n' + install_command(), file=sys.stderr)
    raise SystemExit(1) from None


app = FastAPI(title="Bosch Local Workbench", docs_url=None, redoc_url=None)
LOCK = threading.RLock()
ACTIVE: dict[str, Any] = {}
# A streamed request runs in a background thread.  Keep an explicit marker in
# addition to LOCK so a second browser action cannot replace ACTIVE while that
# request is queued for the lock or is using a captured session context.
MODEL_WORK_IN_PROGRESS = threading.Event()
CHAT_TASK_GUARD = threading.Lock()
CHAT_TASK: dict[str, Any] = {}
# Synchronous long model operations (Codebook preparation, coverage, comparison,
# dossier rebuild) that a browser Stop can cancel by request_id.
OPERATION_GUARD = threading.Lock()
OPERATIONS: dict[str, RequestControl] = {}
REQUEST_ID = r"^(?:[a-f0-9]{32})?$"
# The session/context a browser page displays (X-Workbench-Context). Requests
# that act on the current context are rejected when it no longer matches, so a
# stale tab can never run in, or change, another tab's session or material scope.
PAGE_CONTEXT: ContextVar[str] = ContextVar("PAGE_CONTEXT", default="")
CONTEXT_HEADER = "X-Workbench-Context"
# Navigation that (re)binds a page, and controls that must work from any page.
# /api/codebook/edit has its own stricter guard: the edited profile_version.
UNCHECKED_PAGE_PATHS = {"/api/setup", "/api/session/open", "/api/session/new", "/api/language",
                        "/api/chat/cancel", "/api/operation/cancel", "/api/model-test", "/api/codebook/edit"}

# Retain existing local settings/sessions made by early workbench releases,
# while never sending their obsolete dotted Farm IDs to the endpoint again.
MODEL_ID_MIGRATIONS = {"claude-haiku-5.5": "claude-haiku-5-5"}


def canonical_model_id(value: Any) -> str:
    model = str(value or "").strip().lower()
    return MODEL_ID_MIGRATIONS.get(model, model)


def app_state_home() -> Path:
    return Path(__file__).resolve().parent / "AI_Bot_State"


def workbench_settings_path() -> Path:
    return app_state_home() / "workbench_settings.json"


def model_tests_path() -> Path:
    return app_state_home() / "model_tests.json"


def material_selections_path() -> Path:
    return app_state_home() / "material_selections.json"


def codebook_profile_path() -> Path:
    return app_state_home() / "codebook_profile.json"


def write_json_atomically(path: Path, payload: Any) -> None:
    """Replace one local JSON file without ever exposing a half-written file.

    All workbench state stays beside the program.  Writing a sibling temporary
    file and replacing it only after close prevents an interrupted shutdown
    from corrupting settings, Codebook profiles or reusable evidence caches.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def load_codebook_profile() -> dict:
    try:
        data = json.loads(codebook_profile_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_codebook_profile(profile: dict) -> None:
    profile["version"] = uuid.uuid4().hex
    write_json_atomically(codebook_profile_path(), profile)


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_material_selection(folder: Path) -> tuple[set[str], int, int]:
    """Restore only still-existing files; never touch the original BG folder."""
    try:
        all_records = json.loads(material_selections_path().read_text(encoding="utf-8"))
        record = all_records.get(str(folder), {}) if isinstance(all_records, dict) else {}
        items = record.get("files", []) if isinstance(record, dict) else []
    except (OSError, ValueError):
        items = []
    restored, missing, changed = set(), 0, 0
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            continue
        try:
            path = (folder / item["path"]).resolve()
            path.relative_to(folder)
        except (OSError, ValueError):
            missing += 1
            continue
        if not path.is_file():
            missing += 1
            continue
        restored.add(item["path"])
        try:
            if item.get("bytes") != path.stat().st_size or item.get("mtime_ns") != path.stat().st_mtime_ns:
                changed += 1
        except OSError:
            missing += 1
            restored.discard(item["path"])
    return restored, missing, changed


def save_material_selection(folder: Path, files: list[Path]) -> None:
    """Persist a compact, path-relative manual selection under AI_Bot_State."""
    app_state_home().mkdir(parents=True, exist_ok=True)
    try:
        records = json.loads(material_selections_path().read_text(encoding="utf-8"))
        records = records if isinstance(records, dict) else {}
    except (OSError, ValueError):
        records = {}
    entries = []
    for path in files:
        try:
            stat = path.stat()
            entries.append({"path": path.relative_to(folder).as_posix(), "bytes": stat.st_size,
                            "mtime_ns": stat.st_mtime_ns})
        except (OSError, ValueError):
            continue
    records[str(folder)] = {"updated_at": datetime.now().astimezone().isoformat(timespec="seconds"), "files": entries}
    # A bounded history keeps this settings file permanently lightweight.
    if len(records) > 100:
        keep = sorted(records, key=lambda key: str((records[key] if isinstance(records[key], dict) else {}).get("updated_at", "")), reverse=True)[:100]
        records = {key: records[key] for key in keep}
    write_json_atomically(material_selections_path(), records)


def load_model_tests() -> dict[str, dict]:
    try:
        data = json.loads(model_tests_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_model_test(result: dict) -> None:
    records = load_model_tests()
    records[str(result["requested_model"])] = result
    write_json_atomically(model_tests_path(), records)


def local_diagnostics() -> dict[str, Any]:
    """Return a non-sensitive readiness report for the local workbench.

    This deliberately never calls a model endpoint and never includes a
    credential (or even its length).  It is safe to show directly in the UI.
    """
    env_file, explicit = effective_env_file()
    configuration_error = None
    endpoint = ''
    try:
        with FARM_ENVIRONMENT.use(env_file, load_dotenv, explicit=explicit, commit=False):
            endpoint = validate_farm_endpoint(env_file)
        key_present = True
    except StartupError as exc:
        configuration_error = exc
        key_present = False
    checks: list[dict[str, Any]] = [
        {"id": "env_file", "label": "配置文件 (.env)", "ok": env_file.is_file(), "required": explicit or not key_present,
         "path": str(env_file), "detail": "已找到。" if env_file.is_file() else "未找到；请在程序目录添加 .env。"},
        {"id": "farm_key", "label": "Bosch Farm 密钥", "ok": key_present, "required": True,
         "detail": "已读取（不会显示密钥）。" if key_present else "未读取；请设置 BOSCH_FARM_SUBSCRIPTION_KEY。"},
        {"id": "farm_endpoint", "label": "Bosch Farm 地址", "ok": bool(endpoint), "required": True,
         "detail": endpoint or "未配置。"},
    ]
    if configuration_error:
        error = error_copy(configuration_error, ACTIVE)
        checks[1]['detail'] = str(error)
        checks[1]['detail_message'] = message_payload(error)
    package_groups = {
        "Web 服务": ("fastapi", "uvicorn"),
        "PDF 读取 (PyMuPDF)": ("fitz",),
        "DOCX / Excel 读取": ("docx", "openpyxl"),
    }
    for label, modules in package_groups.items():
        missing = [module for module in modules if importlib.util.find_spec(module) is None]
        checks.append({"id": "packages_" + "_".join(modules), "label": label,
                       "ok": not missing, "required": True,
                       "detail": "可用。" if not missing else "缺少：" + ", ".join(missing)})
    try:
        probe = LocalDocumentLibrary(app_state_home() / ".diagnostic_document_index.json")
        ocr = probe.ocr_runtime_status()
        ocr_ok = bool(ocr.get("available"))
        if ocr_ok:
            detail = "可用" + ("；已安装德语 deu。" if ocr.get("german_available") else "；未检测到德语 deu 语言包。")
        else:
            detail = "不可用：" + str(ocr.get("status", "未知原因"))
        checks.append({"id": "ocr", "label": "OCR (Tesseract)", "ok": ocr_ok,
                       "required": False, "detail": detail})
    except Exception as exc:
        checks.append({"id": "ocr", "label": "OCR (Tesseract)", "ok": False,
                       "required": False, "detail": "检查失败：" + str(exc)[:160]})
    try:
        state_dir = app_state_home()
        check_state_directory(state_dir)
        checks.append({"id": "state_storage", "label": "本地状态目录", "ok": True,
                       "required": True, "detail": "可读写。"})
    except StartupError as exc:
        error = error_copy(exc, ACTIVE)
        checks.append({"id": "state_storage", "label": "本地状态目录", "ok": False,
                       "required": True, "detail": str(error), "detail_message": message_payload(error)})
    settings = load_workbench_settings()
    active_model = str(ACTIVE.get("model") or settings.get("model") or "")
    previous_test = load_model_tests().get(active_model, {})
    if previous_test:
        detail = ("上次测试可用：" if previous_test.get("ok") else "上次测试失败：") + str(previous_test.get("tested_at", "—"))
        checks.append({"id": "model_test", "label": "当前模型的上次测试", "ok": bool(previous_test.get("ok")),
                       "required": False, "detail": detail})
    else:
        checks.append({"id": "model_test", "label": "当前模型的上次测试", "ok": None,
                       "required": False, "detail": "尚未测试；可在模型选择器旁测试。"})
    return {"generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "overall": "ready" if all(check["ok"] or not check["required"] for check in checks) else "attention",
            "checks": checks}


def load_workbench_settings() -> dict[str, str]:
    try:
        data = json.loads(workbench_settings_path().read_text(encoding="utf-8"))
        return {
            "workspace": str(data.get("workspace", "")),
            "session": str(data.get("session", "default")) or "default",
            "model": canonical_model_id(data.get("model", "claude-haiku-5-5")) or "claude-haiku-5-5",
            "language": normalize_language(data.get("language", "zh")),
        } if isinstance(data, dict) else {"workspace": "", "session": "default", "model": "claude-haiku-5-5", "language": "zh"}
    except (OSError, ValueError):
        return {"workspace": "", "session": "default", "model": "claude-haiku-5-5", "language": "zh"}


def normalize_language(value: Any) -> str:
    return str(value or "zh").lower() if str(value or "zh").lower() in {"zh", "en", "de"} else "zh"


def save_workbench_settings(workspace: Path, session_name: str, model: str, language: str = "zh") -> None:
    write_json_atomically(workbench_settings_path(), {
        "workspace": str(workspace), "session": session_name,
        "model": canonical_model_id(model), "language": normalize_language(language),
    })


class Setup(BaseModel):
    workspace: str
    state_dir: str = ""
    model: str = "gpt-5.5"
    session: str = "default"
    env_file: str = ""
    language: str = "zh"


class PathRequest(BaseModel):
    path: str


class ModelTestRequest(BaseModel):
    model: str


class ModelSwitchRequest(BaseModel):
    model: str


class LanguageRequest(BaseModel):
    language: str


class SessionRenameRequest(BaseModel):
    name: str
    source: str = ""


class SessionDeleteRequest(BaseModel):
    confirmed: bool = False
    name: str = ""


class SessionOpenRequest(BaseModel):
    name: str


class SessionPinRequest(BaseModel):
    name: str
    pinned: bool


class BGRequest(BaseModel):
    codebook: str
    folder: str


class TargetRequest(BaseModel):
    target: str
    codebook: str = ""
    selected_paths: list[str] = []


class CodebookPrepareRequest(BaseModel):
    path: str
    model: str = ""
    request_id: str = Field(default="", pattern=REQUEST_ID)


class ChatRequest(BaseModel):
    request_id: str = Field(default="", pattern=r"^(?:[a-f0-9]{32})?$")
    question: str = Field(max_length=50000)
    require_classification: bool = True


class CompareRequest(BaseModel):
    question: str = Field(max_length=50000)
    models: list[str]
    request_id: str = Field(default="", pattern=REQUEST_ID)


class CoverageRequest(BaseModel):
    full: bool = False
    request_id: str = Field(default="", pattern=REQUEST_ID)


class CacheFileRequest(BaseModel):
    document_id: str
    confirmed: bool = False


class CacheConfirmRequest(BaseModel):
    confirmed: bool = False
    request_id: str = Field(default="", pattern=REQUEST_ID)


class OperationCancelRequest(BaseModel):
    request_id: str = Field(pattern=r"^[a-f0-9]{32}$")