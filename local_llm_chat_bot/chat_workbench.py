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

    from release_safety import safe_error, normalize_usage, summarize_usage, context_state_error, valid_rule_profile
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
            missing += 1; continue
        if not path.is_file():
            missing += 1; continue
        restored.add(item["path"])
        try:
            if item.get("bytes") != path.stat().st_size or item.get("mtime_ns") != path.stat().st_mtime_ns:
                changed += 1
        except OSError:
            missing += 1; restored.discard(item["path"])
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


class ChatRequest(BaseModel):
    request_id: str = Field(default="", pattern=r"^(?:[a-f0-9]{32})?$")
    question: str = Field(max_length=50000)
    require_classification: bool = True


class CompareRequest(BaseModel):
    question: str = Field(max_length=50000)
    models: list[str]


class CoverageRequest(BaseModel):
    full: bool = False


class CacheFileRequest(BaseModel):
    document_id: str
    confirmed: bool = False


class CacheConfirmRequest(BaseModel):
    confirmed: bool = False


def session() -> dict[str, Any]:
    if not ACTIVE:
        raise HTTPException(400, ui_message(ACTIVE, 'error.workspace_required'))
    return ACTIVE


def ui_message(data, key, **params):
    language = data.get('language', 'zh') if isinstance(data, dict) else data
    return UIMessage(key, language, **params)


def message_payload(value):
    return value.payload() if isinstance(value, UIMessage) else {'text': str(value)}


class UIRequestError(RuntimeError):
    def __init__(self, message):
        super().__init__(message)
        self.ui_message = message


class UIValidationError(ValueError):
    def __init__(self, message):
        super().__init__(message)
        self.ui_message = message


def error_copy(error, data):
    value = error.detail if isinstance(error, HTTPException) else getattr(error, 'ui_message', str(error))
    if isinstance(error, StartupError):
        value = ui_message(data, error.code, **error.params)
    def redact(item):
        if isinstance(item, UIMessage):
            return UIMessage(item.message_key, item.language, **{key: redact(part) for key, part in item.params.items()})
        return safe_error(item) if isinstance(item, str) else item
    return localize_message(redact(value), data.get('language', 'zh'))


def ui_state(data, value):
    keys = {'ok': 'state.ok', 'not_needed': 'state.not_needed', 'partial': 'state.partial', 'not_requested': 'state.not_requested', 'unknown': 'state.unknown',
            'not_applicable': 'state.not_applicable', 'not applicable': 'state.not_applicable',
            '已完成': 'state.complete', '部分完成': 'state.partial', '不需要（原生文字页）': 'state.native_text',
            '不适用（无页码文档）': 'state.not_applicable', 'not applicable to DOCX': 'state.not_applicable'}
    return ui_message(data, keys[value]) if value in keys else str(value or '—')


@app.exception_handler(HTTPException)
async def localized_http_error(request: Request, error: HTTPException):
    language = request.headers.get('X-Workbench-Language') or ACTIVE.get('language', 'zh')
    detail = error_copy(error, {'language': language})
    return JSONResponse(status_code=error.status_code,
                        content={'detail': str(detail), **message_payload(detail)}, headers=error.headers)


def reject_context_change_while_processing() -> None:
    """Keep the selected session, model and material scope stable per request."""
    if MODEL_WORK_IN_PROGRESS.is_set():
        raise HTTPException(409, ui_message(ACTIVE, 'error.busy'))


def begin_model_work() -> dict[str, Any]:
    """Reserve the single model slot and capture its complete request context."""
    if not LOCK.acquire(blocking=False):
        raise HTTPException(409, ui_message(ACTIVE, 'error.busy'))
    try:
        if MODEL_WORK_IN_PROGRESS.is_set():
            raise HTTPException(409, ui_message(ACTIVE, 'error.busy'))
        data = dict(session())
        data["request_control"] = RequestControl()
        data["cancel_event"] = data["request_control"].cancel_event
        MODEL_WORK_IN_PROGRESS.set()
        return data
    finally:
        LOCK.release()


def status_data(data: dict[str, Any]) -> dict[str, Any]:
    state = data["state"]
    usage = state.data["usage"]
    return {
        "workspace": str(state.workspace), "model": data["model"], "session": state.data["session_id"][:8],
        "session_name": state.root.name,
        "code_files": len(state.data["files"]), "documents": len(data["documents"].list()),
        "requests": usage["requests"], "input_tokens": usage["input"], "output_tokens": usage["output"],
        "known_input_tokens": usage.get("known_input", usage["input"]),
        "known_output_tokens": usage.get("known_output", usage["output"]),
        "usage_complete": usage.get("usage_complete", not usage.get("unpriced_requests")),
        "cost": None if usage.get("unpriced_requests") else round(float(usage.get("estimated_cost_usd", 0)), 6),
        "known_cost_usd": usage.get("estimated_cost_usd", 0),
        "cost_complete": not usage.get("unpriced_requests"),
        "unpriced_requests": usage.get("unpriced_requests", 0),
        "bg_context": state.data.get("bg_context"),
        "context_issue": context_issue(data),
        "context_revision": state.data.get("context_revision", ""),
    }


def session_list_item(root: Path) -> dict[str, Any]:
    """Small, local-only metadata for the ChatGPT-style session sidebar."""
    state_file = root / "state.json"
    data: dict[str, Any] = {}
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    if not isinstance(data, dict): data = {}
    title = str(data.get("sidebar_title") or root.name)
    try:
        updated = state_file.stat().st_mtime
    except OSError:
        updated = 0.0
    return {"name": root.name, "title": title[:100], "pinned": bool(data.get("sidebar_pinned", False)),
            "updated_at": updated}


def available_sessions(state: ProjectState) -> list[dict[str, Any]]:
    root = state.root.parent
    if not root.is_dir():
        return [session_list_item(state.root)]
    records = [session_list_item(item) for item in root.iterdir() if item.is_dir()]
    records.sort(key=lambda item: (not item["pinned"], -item["updated_at"], item["name"].casefold()))
    return records or [session_list_item(state.root)]


def title_session_from_question(state: ProjectState, question: str) -> None:
    current = str(state.data.get("sidebar_title", "")).strip()
    if current and current != "新聊天":
        return
    title = " ".join(str(question).strip().split())[:72]
    if title:
        state.data["sidebar_title"] = title
        state.save()


def safe_file(value: str) -> Path:
    path = Path(value.strip().strip('"')).expanduser().resolve()
    if not path.is_file():
        raise HTTPException(400, ui_message(ACTIVE, 'error.file_missing', path=path))
    return path


def connector_failure(raw: Any) -> str | None:
    """Return a connector-level failure message, if a connector returned one.

    The Bosch Farm connector intentionally returns transport failures as text so
    callers can still display them in simple scripts.  A workbench answer must
    not mistake that text for an LLM answer, however.
    """
    text = str(raw or "").strip()
    if not text:
        return UIMessage("model.empty")
    normalized = text.casefold()
    if normalized.startswith(("error:", "http error", "error after ")):
        return text
    if normalized.startswith("(no text content"):
        return UIMessage("model.empty_endpoint", detail=text)
    return None


def require_model_success(raw: Any, context=None) -> str:
    """Return a non-empty model answer or raise a user-visible failure."""
    text = str(raw or "").strip()
    failure = connector_failure(text)
    if failure:
        context = context or UIMessage('model.context_main')
        language = getattr(context, 'language', 'zh')
        raise UIRequestError(UIMessage('model.request_failed', language, context=context,
                                        detail=localize_message(failure, language)))
    return text


def target_tree(folder: Path, maximum_nodes: int = 5000) -> tuple[dict, bool]:
    """Return a read-only, local folder tree without indexing any material."""
    count, truncated = 0, False

    def visit(path: Path) -> dict | None:
        nonlocal count, truncated
        if count >= maximum_nodes:
            truncated = True
            return None
        try:
            is_folder = path.is_dir()
        except OSError:
            return None
        count += 1
        if not is_folder:
            suffix = path.suffix.lower()
            try:
                size = path.stat().st_size
            except OSError:
                size = 0
            role = material_role(path)
            return {"type": "file", "name": path.name, "path": str(path),
                    "relative": path.relative_to(folder).as_posix(),
                    "supported": suffix in SUPPORTED_DOCUMENT_EXTENSIONS, "bytes": size,
                    "material_role": role, "material_role_label": material_role_label(role),
                    "recommended": suffix in SUPPORTED_DOCUMENT_EXTENSIONS and material_is_recommended(path)}
        children = []
        try:
            entries = sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.casefold()))
        except OSError:
            entries = []
        for child in entries:
            # Do not follow junctions/symlinks outside the selected BG folder.
            if child.is_symlink():
                continue
            item = visit(child)
            if item is not None:
                children.append(item)
        return {"type": "folder", "name": path.name, "path": str(path),
                "relative": "." if path == folder else path.relative_to(folder).as_posix(), "children": children}

    tree = visit(folder)
    return tree or {"type": "folder", "name": folder.name, "path": str(folder), "children": []}, truncated


def selected_target_files(folder: Path, values: list[str]) -> list[Path]:
    """Validate explicit UI selections and keep them inside the picked folder."""
    selected, seen = [], set()
    for value in values:
        candidate = Path(value).expanduser()
        candidate = candidate if candidate.is_absolute() else folder / candidate
        try:
            path = candidate.resolve(); path.relative_to(folder)
            paths = sorted(path.rglob('*')) if path.is_dir() else [path]
            for item in paths:
                if item.is_symlink(): continue
                item = item.resolve(); item.relative_to(folder)
                if item.is_file() and item.suffix.lower() in SUPPORTED_DOCUMENT_EXTENSIONS and str(item) not in seen:
                    selected.append(item); seen.add(str(item))
        except (OSError, ValueError):
            continue
    return selected


def codebook_page_groups(document: dict, pages_per_group: int = 3) -> list[list[dict]]:
    pages: dict[int, list[dict]] = {}
    for chunk in document.get("chunks", []):
        visual = chunk.get("visual") or {}
        page = visual.get("page")
        if isinstance(page, int):
            pages.setdefault(page, []).append(chunk)
    # PDF chunks carry a page number and are grouped page-wise so that every
    # original page (including visual-only/table pages) reaches the model.
    # DOCX does not have PDF page metadata; its extracted paragraphs/tables are
    # still useful and must not make Codebook preparation silently fail.
    ordered = [pages[number] for number in sorted(pages)]
    if not ordered:
        chunks = document.get("chunks", [])
        ordered = [chunks[index:index + pages_per_group]
                   for index in range(0, len(chunks), pages_per_group)]
        return ordered
    return [sum(ordered[index:index + pages_per_group], []) for index in range(0, len(ordered), pages_per_group)]


def parse_codebook_draft(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise UIValidationError(ui_message(ACTIVE, 'rules.model_json'))
    draft = json.loads(text[start:end + 1])
    if not isinstance(draft, dict) or not isinstance(draft.get("classes"), list):
        raise UIValidationError(ui_message(ACTIVE, 'rules.classes_required'))
    classes = []
    seen_names = set()
    for item in draft["classes"]:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"].strip():
            continue
        def rules(values, prefix):
            result = []
            for index, value in enumerate(values if isinstance(values, list) else [], start=1):
                if isinstance(value, str):
                    result.append({"id": f"{prefix}-{index}", "text": value, "pages": []})
                elif isinstance(value, dict) and str(value.get("text", "")).strip():
                    result.append({"id": str(value.get("id") or f"{prefix}-{index}"),
                                   "text": str(value["text"]).strip(),
                                   "pages": [int(page) for page in (value.get("pages") or []) if str(page).isdigit()]})
            return result
        name = item["name"].strip()
        if name.casefold() in seen_names or not isinstance(item.get("definition"), str) or not item["definition"].strip():
            raise UIValidationError(ui_message(ACTIVE, 'rules.class_definitions'))
        seen_names.add(name.casefold())
        key = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-") or "class"
        classes.append({
            "name": name, "definition": str(item.get("definition", "")).strip(),
            "decision_rules": rules(item.get("decision_rules", []), f"{key}-rule"),
            "boundaries": rules(item.get("boundaries", []), f"{key}-boundary"),
            "evidence_pages": [int(page) for page in (item.get("evidence_pages") or []) if str(page).isdigit()],
        })
    if not classes:
        raise UIValidationError(ui_message(ACTIVE, 'rules.classes_empty'))
    def profile_rules(values, prefix):
        result = []
        for index, value in enumerate(values if isinstance(values, list) else [], start=1):
            if isinstance(value, str): result.append({"id": f"{prefix}-{index}", "text": value, "pages": []})
            elif isinstance(value, dict) and str(value.get("text", "")).strip():
                result.append({"id": str(value.get("id") or f"{prefix}-{index}"), "text": str(value["text"]).strip(),
                               "pages": [int(page) for page in (value.get("pages") or []) if str(page).isdigit()],
                               "table": value.get("table") if isinstance(value.get("table"), dict) else None})
        return result
    return {"classes": classes, "global_rules": profile_rules(draft.get("global_rules", []), "global"),
            "table_rules": profile_rules(draft.get("table_rules", []), "table"), "uncertainties": draft.get("uncertainties", [])}


CODEBOOK_PAGE_SYSTEM = """You transcribe exactly one technical classification Codebook page using supplied native text, OCR text and the full-page image. Return ONLY JSON: {\"page\":number,\"official_names\":[\"exact wording\"],\"definitions\":[\"...\"],\"decision_rules\":[\"...\"],\"boundaries\":[\"...\"],\"tables\":[{\"title\":\"...\",\"columns\":[\"...\"],\"rows\":[[\"cell\"]]}],\"uncertainties\":[\"...\"]}. Preserve table row/column meaning, do not invent text, and use the page number supplied in the prompt."""
CODEBOOK_MERGE_SYSTEM = """You consolidate page-by-page Codebook transcriptions. Return ONLY JSON: {\"classes\":[{\"name\":\"exact official class name\",\"definition\":\"...\",\"decision_rules\":[{\"id\":\"class-rule-1\",\"text\":\"...\",\"pages\":[1]}],\"boundaries\":[{\"id\":\"class-boundary-1\",\"text\":\"...\",\"pages\":[1]}],\"evidence_pages\":[1]}],\"global_rules\":[{\"id\":\"global-1\",\"text\":\"...\",\"pages\":[1]}],\"table_rules\":[{\"id\":\"table-1\",\"text\":\"meaning of the table rule\",\"pages\":[1],\"table\":{\"columns\":[\"...\"],\"rows\":[[\"...\"]]}}],\"uncertainties\":[\"...\"]}. Preserve exact names, rule IDs and page numbers. Do not invent missing rules."""
CODEBOOK_JSON_REPAIR_SYSTEM = """Return ONLY one complete, valid JSON object. Do not use Markdown fences or commentary. Preserve every fact, class name, rule, table value and page number from the supplied candidate; only repair JSON syntax such as missing commas, quotes, brackets or escaping."""


def accounted_model_call(data, connector, *args, usage_records=None, **kwargs):
    """Record dispatches before response validation; failed output still costs."""
    check_request(data)
    connector.last_usage = None
    connector.last_response_model = None
    connector.usage_attempts = None
    old_control = getattr(connector, "request_control", None)
    connector.request_control = data.get("request_control")
    try:
        result = connector.ask_about_files(*args, **kwargs)
        check_request(data)
        if data.get("request_control"):
            data["request_control"].limit(len(result))
        return result
    finally:
        connector.request_control = old_control
        attempts = connector.usage_attempts
        if attempts is None:  # Custom/test connector with no transport ledger.
            attempts = [{"usage": connector.get_last_token_usage(),
                         "model": connector.last_response_model or connector.model_name}]
        elif attempts and connector.last_response_model:
            attempts[-1]["model"] = connector.last_response_model
        for attempt in attempts:
            usage = normalize_usage(attempt["usage"])
            estimate = data["state"].note_usage(usage, data["pricing"], attempt["model"])
            usage["cost_usd"] = estimate["cost_usd"] if estimate else None
            if usage_records is not None:
                usage_records.append(usage)


def check_request(data):
    control = data.get("request_control")
    if control:
        control.check()
    elif data.get("cancel_event") and data["cancel_event"].is_set():
        raise RequestCancelled("Request cancelled")


@contextmanager
def commit_answer(data):
    control = data.get("request_control")
    if control:
        with control.commit():
            yield
    else:
        check_request(data)
        yield


def check_answer_size(data, answer):
    control = data.get("request_control")
    if control and len(answer) > control.policy.max_answer_chars:
        raise ResponseLimitExceeded("Answer exceeds the configured size limit")


def parse_codebook_draft_with_repair(connector: LLMConnector, raw: str, *, data, usage_records=None) -> tuple[dict, dict | None]:
    """Parse the final Codebook JSON, making one syntax-only repair attempt if needed."""
    try:
        return parse_codebook_draft(raw), None
    except (ValueError, json.JSONDecodeError) as initial_error:
        repair_prompt = (
            "The candidate Codebook JSON below could not be parsed. Repair its JSON syntax only; "
            "do not summarize, add, omit, translate, or change any factual content.\n"
            f"Parser error: {initial_error}\n\n--- CANDIDATE JSON ---\n{raw}"
        )
        repaired = accounted_model_call(data, connector, [], repair_prompt, CODEBOOK_JSON_REPAIR_SYSTEM,
                                        {"maxOutputTokens": 4096, "temperature": 0}, stream=True,
                                        usage_records=usage_records)
        repaired = require_model_success(repaired, ui_message(data, 'model.context_codebook_repair'))
        repair_usage = connector.get_last_token_usage() or {}
        try:
            return parse_codebook_draft(repaired), repair_usage
        except (ValueError, json.JSONDecodeError) as repair_error:
            raise UIValidationError(ui_message(data, 'rules.repair_invalid', detail=error_copy(repair_error, data))) from initial_error


def prepare_codebook_profile(data: dict[str, Any], path: Path, model: str) -> dict:
    document = data["documents"].add(str(path))
    connector = LLMConnector(model, data["llm"].api_key, session_id=f"codebook_{os.urandom(6).hex()}")
    ocr_runtime = data["documents"].ocr_runtime_status() if path.suffix.lower() == ".pdf" else {"available": False, "status": "not applicable to DOCX"}
    records = data["documents"].codebook_page_records(path, app_state_home() / "codebook_visual_cache") if path.suffix.lower() == ".pdf" else []
    groups, notes = codebook_page_groups(document), []
    usages: list[dict] = []
    if not records and not groups:
        raise HTTPException(400, ui_message(ACTIVE, 'error.rules_empty'))
    if records:
        for record in records:
            prompt = f"Codebook page {record['page']} of {len(records)}. Page type: {record['page_type']}.\n--- NATIVE TEXT ---\n{record['native_text'] or '[none]'}\n--- OCR TEXT ({record['ocr_status']}) ---\n{record['ocr_text'] or '[none]'}"
            raw = accounted_model_call(data, connector, [record["image_path"]], prompt, CODEBOOK_PAGE_SYSTEM, {"maxOutputTokens": 2200, "temperature": 0}, stream=True, usage_records=usages)
            raw = require_model_success(raw, ui_message(data, 'model.context_codebook_page', page=record["page"]))
            notes.append(raw)
    else:
        for index, group in enumerate(groups, start=1):
            prompt = f"Codebook DOCX section {index}/{len(groups)}.\n" + "\n\n".join(f"--- {item['label']} ---\n{item['text']}" for item in group)
            raw = accounted_model_call(data, connector, [], prompt, CODEBOOK_PAGE_SYSTEM, {"maxOutputTokens": 2200, "temperature": 0}, stream=True, usage_records=usages)
            raw = require_model_success(raw, ui_message(data, 'model.context_codebook_section', page=index))
            notes.append(raw)
    merge_prompt = "Consolidate every Codebook page note below. All classes, tables and boundary rules must be retained.\n\n" + "\n\n".join(
        f"--- PAGE GROUP {index} ---\n{note}" for index, note in enumerate(notes, start=1))
    merged = accounted_model_call(data, connector, [], merge_prompt, CODEBOOK_MERGE_SYSTEM, {"maxOutputTokens": 3500, "temperature": 0}, stream=True, usage_records=usages)
    merged = require_model_success(merged, ui_message(data, 'model.context_codebook_merge'))
    draft, _ = parse_codebook_draft_with_repair(connector, merged, data=data, usage_records=usages)
    usage = summarize_usage(usages)
    page_numbers = {((item.get("visual") or {}).get("page")) for group in groups for item in group}
    page_count = len([number for number in page_numbers if isinstance(number, int)]) or len(document.get("chunks", []))
    return {"status": "draft", "source_path": str(path), "source_name": path.name, "sha256": file_digest(path),
            "prepared_at": datetime.now().astimezone().isoformat(timespec="seconds"), "parser_model": connector.last_response_model or model,
            "page_count": len(records) or page_count,
            "page_groups": len(records) or len(groups), "usage": usage, "draft": draft, "document_id": document["id"],
            "page_records": [{key: record[key] for key in ("page", "page_type", "ocr_status", "embedded_image_count")} for record in records],
            "page_transcriptions": notes, "ocr_runtime": ocr_runtime}


def write_session_export(data: dict[str, Any]) -> Path:
    state = data["state"]
    exports = state.root / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    target = exports / f"session_transcript_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    usage = state.data.get("usage", {})
    transcript = state.full_history()
    lines = [
        "# Local LLM Chat – 会话导出", "",
        f"- 导出时间：{datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- 会话：{state.root.name}",
        f"- 当前模型：{data['model']}",
        f"- 累计请求：{usage.get('requests', 0)}",
        f"- 累计 token：输入 {usage.get('input', 0)} ｜ 输出 {usage.get('output', 0)}",
        ("- 累计预估费用：未知；已知部分小计：$" if usage.get("unpriced_requests") else "- 累计预估费用：$") + f"{float(usage.get('estimated_cost_usd', 0)):.6f}",
        f"- 已知 Token 小计：输入 {usage.get('known_input', usage.get('input', 0))} ｜ 输出 {usage.get('known_output', usage.get('output', 0))}",
        "", "## 对话记录", "",
    ]
    for item in transcript:
        role = "用户" if item.get("role") == "user" else "助手"
        timestamp = item.get("time", "")
        lines.extend([f"### {role} {timestamp}", "", str(item.get("content", "")), ""])
    target.write_text("\n".join(lines), encoding="utf-8")
    return target


def write_bg_analysis_export(state: ProjectState) -> Path:
    record = state.data.get("last_bg_analysis")
    if not isinstance(record, dict):
        raise HTTPException(400, ui_message(ACTIVE, 'error.export_missing'))
    exports = state.root / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = exports / f"bg_analysis_{timestamp}.md"
    sources = "\n".join(f"- {item}" for item in record.get("sources", [])) or "- （没有可用的材料来源）"
    bg = record.get("bg_context") or {}
    token = record.get("token_usage") or {}
    content = "\n".join([
        "# Baugruppe 分析结果",
        "",
        "- 导出时间：" + str(record.get("created_at", "")),
        "- 会话：" + str(record.get("session", "")),
        "- 模型：" + str(record.get("model", "")),
        "- Codebook：" + str(bg.get("codebook_name", "—")),
        "- BG 文件夹：" + str(bg.get("folder", "—")),
        "- 本轮 token：输入 " + str(token.get("input", 0)) + " ｜ 输出 " + str(token.get("output", 0)),
        "- 推理 token（若网关返回）： " + str(token.get("reasoning", 0)),
        "- Gemini thinking token（若网关返回）： " + str(token.get("gemini_thinking", 0)),
        "- Claude 缓存：读取 " + str(token.get("cache_read", 0)) + " ｜ 写入 " + str(token.get("cache_write", 0)),
        "- 本轮预估费用：" + ("unknown" if token.get("cost_usd") is None else "$" + format(float(token["cost_usd"]), ".6f")),
        "",
        "## 用户问题",
        "",
        str(record.get("question", "")),
        "",
        "## 模型分析",
        "",
        str(record.get("answer", "")),
        "",
        "## 实际提供给模型的证据来源",
        "",
        sources,
        "",
    ])
    target.write_text(content, encoding="utf-8")
    return target


def build_diff(state: ProjectState, changes: list[dict]) -> list[dict]:
    prepared = []
    for change in changes:
        if not isinstance(change, dict) or not isinstance(change.get("path"), str) or not isinstance(change.get("content"), str):
            continue
        relative = ensure_relative(change["path"])
        path = state.resolve_relative(relative)
        old = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        before = sha256(path.read_bytes()) if path.exists() else None
        diff = "\n".join(difflib.unified_diff(old.splitlines(), change["content"].splitlines(),
                                                 fromfile=f"a/{relative}", tofile=f"b/{relative}", lineterm=""))
        prepared.append({"path": relative, "content": change["content"], "before": before,
                         "reason": str(change.get("reason", "")), "diff": diff})
    return prepared


def coverage_path(state: ProjectState) -> Path:
    return state.root / "analysis_coverage.json"


MATERIAL_SUMMARY_CACHE_VERSION = "material-summary-v1"
BG_DOSSIER_CACHE_VERSION = "bg-dossier-v1"


def material_summary_cache_path(document: dict, model: str, full: bool, read_pages: list[int]) -> Path:
    """A content-addressed local cache, never written beside BG source files."""
    digest = str(document.get("sha256") or "unknown")
    identity = json.dumps({"version": MATERIAL_SUMMARY_CACHE_VERSION, "sha256": digest,
                           "model": model, "full": full, "pages": read_pages},
                          ensure_ascii=False, sort_keys=True)
    key = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return app_state_home() / "material_cache" / digest / f"{key}.json"


def load_material_summary_cache(document: dict, model: str, full: bool, read_pages: list[int]) -> dict | None:
    path = material_summary_cache_path(document, model, full, read_pages)
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(cached, dict) or cached.get("version") != MATERIAL_SUMMARY_CACHE_VERSION:
        return None
    if cached.get("sha256") != document.get("sha256") or cached.get("model") != model:
        return None
    if cached.get("full") is not full or cached.get("pages") != read_pages:
        return None
    record = cached.get("record")
    return record if isinstance(record, dict) else None


def save_material_summary_cache(document: dict, model: str, full: bool, read_pages: list[int], record: dict) -> None:
    path = material_summary_cache_path(document, model, full, read_pages)
    payload = {"version": MATERIAL_SUMMARY_CACHE_VERSION, "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
               "sha256": document.get("sha256"), "model": model, "full": full, "pages": read_pages,
               "record": record}
    write_json_atomically(path, payload)


def bg_dossier_identity(coverage: dict, model: str) -> dict:
    """Only source facts belong here; Codebook stays independently versioned."""
    files = [{"sha256": item.get("sha256"), "name": item.get("name"),
              "pages_read": item.get("pages_read", []), "pages_unread": item.get("pages_unread", []),
              "reading_scope": item.get("reading_scope", "")}
             for item in coverage.get("files", []) if isinstance(item, dict)]
    return {"version": BG_DOSSIER_CACHE_VERSION, "model": model,
            "files": sorted(files, key=lambda item: (str(item["sha256"]), str(item["name"]))) }


def bg_dossier_cache_path(coverage: dict, model: str) -> Path:
    encoded = json.dumps(bg_dossier_identity(coverage, model), ensure_ascii=False, sort_keys=True)
    key = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]
    return app_state_home() / "bg_dossier_cache" / f"{key}.json"


def load_bg_dossier_cache(coverage: dict, model: str) -> dict | None:
    try:
        payload = json.loads(bg_dossier_cache_path(coverage, model).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("identity") != bg_dossier_identity(coverage, model):
        return None
    return payload if str(payload.get("summary", "")).strip() else None


def prepare_bg_dossier(data: dict[str, Any], coverage: dict, *, force: bool = False, usage_records=None) -> tuple[dict | None, dict | None, bool]:
    """Consolidate reusable per-file facts once; raw evidence remains query-specific."""
    ensure_current_sources(data)
    if not coverage_matches_current_selection(data, coverage):
        raise HTTPException(409, ui_message(ACTIVE, 'context.reconfirm'))
    cached = None if force else load_bg_dossier_cache(coverage, data["model"])
    if cached:
        cached = dict(cached); cached["cache_status"] = "reused"
        return cached, None, False
    records = [item for item in coverage.get("files", []) if isinstance(item, dict) and item.get("summary")]
    if not records:
        return None, None, False
    sources = "\n\n".join(
        f"--- SOURCE FILE: {item.get('name', 'unknown')} | read pages: {item.get('pages_read', []) or 'n/a'} | unread pages: {item.get('pages_unread', []) or 'none'} ---\n{item.get('summary', '')}"
        for item in records)
    system_prompt = "You are a careful technical evidence consolidator. Use only supplied file summaries. Write concise Chinese factual evidence for later Baugruppe questions; do not classify it and do not invent facts. Preserve every source file name and page/section label, distinguish confirmed facts from uncertainty, and omit irrelevant detail."
    request = "Create one reusable BG comprehensive evidence dossier with sections: composition/BOM; motion and main functional chain; actuators/transmission; relevant geometry/interfaces; DFC hierarchy; conflicts or limitations; source evidence. Every factual bullet must retain its source file and page/section label.\n\n" + sources
    records_used: list[dict] = []
    try:
        raw = require_model_success(accounted_model_call(data, data["llm"], [], request, system_prompt, {"maxOutputTokens": 2400, "temperature": 0}, stream=True, usage_records=records_used), ui_message(data, 'model.context_dossier'))
    finally:
        if usage_records is not None:
            usage_records.extend(records_used)
    usage = summarize_usage(records_used)
    dossier = {"version": BG_DOSSIER_CACHE_VERSION, "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
               "identity": bg_dossier_identity(coverage, data["model"]), "model": data["model"],
               "summary": raw, "source_files": [{"name": item.get("name"), "sha256": item.get("sha256"),
                                                     "pages_read": item.get("pages_read", [])} for item in records],
               "cache_status": "created"}
    path = bg_dossier_cache_path(coverage, data["model"])
    write_json_atomically(path, dossier)
    return dossier, usage, True


def material_cache_entries(document: dict) -> list[dict]:
    """Return metadata only; source text and model summaries stay local/private."""
    digest = str(document.get("sha256") or "")
    root = app_state_home() / "material_cache" / digest
    entries = []
    try:
        candidates = sorted(root.glob("*.json"))
    except OSError:
        candidates = []
    for path in candidates:
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
            record = item.get("record", {}) if isinstance(item, dict) else {}
            if not isinstance(item, dict) or item.get("sha256") != digest:
                continue
            entries.append({"model": item.get("model", ""), "created_at": item.get("created_at", ""),
                            "full": bool(item.get("full")), "pages": item.get("pages", []),
                            "complete": bool(record.get("complete")), "groups": record.get("text_groups_processed", 0)})
        except (OSError, ValueError):
            continue
    return entries


def document_ocr_audit(document: dict) -> str:
    if document.get("image_type") == "dfc_structure_screenshot":
        audit = LocalDocumentLibrary.dfc_audit(document) or {}
        return "DFC " + str(audit.get("ocr_status", "not requested"))
    pages = document.get("page_inventory", [])
    if not pages:
        return "不需要 / 无 PDF 页"
    statuses = [str(item.get("ocr_status", "not_requested")) for item in pages if item.get("page_type") != "text"]
    if not statuses:
        return "不需要（原生文字页）"
    if all(status == "ok" for status in statuses):
        return "已完成"
    if any(status == "ok" for status in statuses):
        return "部分完成"
    return statuses[0]


def cache_audit(data: dict[str, Any]) -> dict:
    state, documents = data["state"], data["documents"]
    active = set(state.data.get("active_source_ids") or [])
    selected = [item for item in documents.list() if item.get("id") in active]
    coverage = load_coverage(state)
    current = coverage_matches_current_selection(data, coverage)
    dossier = load_bg_dossier_cache(coverage, data["model"]) if current else None
    return {"selection_current": current, "coverage_created_at": coverage.get("created_at", ""),
            "dossier": {"ready": bool(dossier), "created_at": dossier.get("created_at", "") if dossier else "",
                        "model": dossier.get("model", "") if dossier else ""},
            "files": [{"id": item.get("id"), "name": item.get("name"), "sha256": str(item.get("sha256", ""))[:12],
                       "role": material_role_label(item.get("material_role", "other")),
                       "index_status": item.get("index_cache_status", "unknown"), "ocr_status": document_ocr_audit(item),
                       "summary_entries": material_cache_entries(item)} for item in selected]}


def invalidate_current_coverage(state: ProjectState, document_id: str | None = None) -> None:
    coverage = load_coverage(state)
    if not coverage:
        return
    if document_id:
        coverage["files"] = [item for item in coverage.get("files", []) if item.get("id") != document_id]
    coverage["complete"] = False
    write_json_atomically(coverage_path(state), coverage)


def load_coverage(state: ProjectState) -> dict:
    try:
        data = json.loads(coverage_path(state).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def coverage_matches_current_selection(data: dict[str, Any], coverage: dict | None = None) -> bool:
    """A session report is current only for the exact selected material hashes/model."""
    coverage = coverage if coverage is not None else load_coverage(data["state"])
    if not coverage.get("complete") or coverage.get("model") != data["model"]:
        return False
    if context_issue(data) or coverage.get("context_revision") != data["state"].data.get("context_revision"):
        return False
    active = set(data["state"].data.get("active_source_ids") or [])
    selected = [item for item in data["documents"].list() if item.get("id") in active]
    expected = {(item.get("id"), item.get("sha256")) for item in selected}
    actual = {(item.get("id"), item.get("sha256")) for item in coverage.get("files", []) if isinstance(item, dict)}
    return bool(expected) and actual == expected


def coverage_for_ui(data: dict[str, Any]) -> dict:
    coverage = load_coverage(data["state"])
    if coverage:
        coverage = dict(coverage)
        coverage["current_selection"] = coverage_matches_current_selection(data, coverage)
        if coverage["current_selection"]:
            dossier = load_bg_dossier_cache(coverage, data["model"])
            coverage["bg_dossier"] = {"ready": bool(dossier), "created_at": dossier.get("created_at", "") if dossier else ""}
    return coverage


def document_pages(document: dict) -> list[int]:
    pages = []
    for chunk in document.get("chunks", []):
        page = (chunk.get("visual") or {}).get("page")
        if isinstance(page, int) and page not in pages:
            pages.append(page)
    return sorted(pages)


def selected_reading_chunks(document: dict, full: bool = False) -> tuple[list[dict], str, list[int], list[int]]:
    """Use a human-like first pass for large component manuals, not blind full-PDF upload."""
    name = str(document.get("name", "")).casefold()
    is_datasheet = document.get("material_role") == "datasheet" or any(term in name for term in ("datenblatt", "datasheet", "catalog", "katalog"))
    chunks = list(document.get("chunks", []))
    all_pages = document_pages(document)
    if not is_datasheet or full:
        return chunks, "完整文本预读", all_pages, []
    first_pages = []
    for chunk in chunks:
        match = re.search(r"page\s+(\d+)", str(chunk.get("label", "")), re.I)
        if match and int(match.group(1)) <= 15:
            first_pages.append(chunk)
    if first_pages and len(first_pages) < len(chunks):
        read_pages = [page for page in all_pages if page <= 15]
        return first_pages, "Datasheet 前 15 页预读（其余页尚未覆盖）", read_pages, [page for page in all_pages if page > 15]
    return chunks, "完整文本预读", all_pages, []


def summary_groups(document: dict, chunks: list[dict], limit: int = 24_000) -> list[str]:
    groups, current = [], ""
    for chunk in chunks:
        part = f"--- {chunk.get('label', document.get('name', 'file'))} ---\n{chunk.get('text', '')}\n"
        if current and len(current) + len(part) > limit:
            groups.append(current); current = part
        else:
            current += part
    if current:
        groups.append(current)
    return groups


def prepare_coverage(data: dict[str, Any], full: bool = False, progress=None, usage_records=None) -> dict:
    """Prepare auditable, document-aware evidence before a BG classification question."""
    ensure_current_sources(data)
    state, documents, llm = data["state"], data["documents"], data["llm"]
    active_ids = state.data.get("active_source_ids") or []
    selected = [item for item in documents.list() if item.get("id") in active_ids]
    if not selected:
        raise HTTPException(400, ui_message(ACTIVE, 'error.target_required'))
    records, total_calls, reused_files, created_files = [], 0, 0, 0
    previous_report = load_coverage(state)
    previous_records = {(item.get("id"), item.get("sha256")): item for item in previous_report.get("files", [])
                        if isinstance(item, dict)} if previous_report.get("model") == data["model"] and previous_report.get("requested_full_coverage") is full else {}
    summary_system = "You are a careful technical evidence extractor. Use only the supplied file content. Write concise Chinese factual notes. Do not classify the Baugruppe and do not invent missing information."
    total_documents = len(selected)
    for file_index, document in enumerate(selected, start=1):
        if progress:
            progress("reading", ui_message(data, "reading.file", index=file_index, total=total_documents, name=document["name"]),
                     12 + int((file_index - 1) / max(total_documents, 1) * 48))
        # Complete analysis prepares OCR locally for visual pages. It adds no
        # Farm token cost and lets a scanned page participate in the same
        # auditable page/chunk coverage as native-text pages.
        documents.ensure_document_ocr(document)
        read_chunks, reading_scope, read_pages, unread_pages = selected_reading_chunks(document, full=full)
        cached = load_material_summary_cache(document, data["model"], full, read_pages)
        # Migrate a valid summary generated by the immediately preceding
        # version.  This makes the first incremental file addition cheap even
        # when the user prepared its original selection before this update.
        if not cached:
            old = previous_records.get((document.get("id"), document.get("sha256")))
            if old and old.get("complete") and old.get("pages_read") == read_pages and old.get("pages_unread") == unread_pages:
                cached = dict(old)
                save_material_summary_cache(document, data["model"], full, read_pages, cached)
        if cached:
            # Cached facts remain tied to the exact source hash, model and
            # reading scope.  Rebind display metadata in case a same-content
            # file was moved or reselected under a different path.
            record = dict(cached)
            record.update({"id": document["id"], "name": document["name"], "path": document["path"],
                           "sha256": document.get("sha256"), "pages_total": len(document_pages(document)),
                           "pages_read": read_pages, "pages_unread": unread_pages,
                           "full_coverage": not unread_pages, "reading_scope": reading_scope, "reading_scope_message": UIMessage("material.scope_full" if reading_scope == "完整文本预读" else "material.scope_datasheet", pages=15).payload(),
                           "dfc_structure": documents.dfc_audit(document), "cache_status": "reused"})
            records.append(record)
            reused_files += 1
            if progress:
                progress("reading", ui_message(data, "reading.reused", index=file_index, total=total_documents, name=document["name"]),
                         12 + int(file_index / max(total_documents, 1) * 48))
            continue
        groups = summary_groups(document, read_chunks)
        notes, failures = [], []
        for number, group in enumerate(groups, start=1):
            try:
                if progress:
                    progress("reading", ui_message(data, "reading.group", name=document["name"], index=number, total=len(groups)),
                             12 + int((file_index - 1 + number / max(len(groups), 1)) / max(total_documents, 1) * 48))
                attempts: list[dict] = []
                try:
                    raw = accounted_model_call(data, llm, [], f"文件：{document['name']}。这是第 {number}/{len(groups)} 个完整文本片段组。提取结构、部件、驱动、运动、接口、尺寸和不确定处，并保留页面/表格标签。\n\n{group}",
                                               summary_system, {"maxOutputTokens": 900, "temperature": 0}, stream=True, usage_records=attempts)
                finally:
                    total_calls += len(attempts)
                    if usage_records is not None: usage_records.extend(attempts)
                raw = require_model_success(raw, ui_message(data, 'model.context_group', name=document["name"]))
                notes.append(raw.strip())
            except RequestStopped:
                raise
            except Exception as exc:
                failures.append(ui_message(data, "reading.group_failed", index=number, detail=error_copy(exc, data)))
        if notes and len(notes) > 1:
            try:
                merged = "\n\n".join(f"[片段组 {i}]\n{note}" for i, note in enumerate(notes, start=1))
                attempts = []
                try:
                    raw = accounted_model_call(data, llm, [], f"请将下列同一文件的全部片段笔记合成为一份不遗漏冲突或不确定处的技术摘要。必须保留证据标签。\n\n文件：{document['name']}\n\n{merged}",
                                               summary_system, {"maxOutputTokens": 1400, "temperature": 0}, stream=True, usage_records=attempts)
                finally:
                    total_calls += len(attempts)
                    if usage_records is not None: usage_records.extend(attempts)
                raw = require_model_success(raw, ui_message(data, 'model.context_merge', name=document["name"]))
                summary = raw.strip()
            except RequestStopped:
                raise
            except Exception as exc:
                summary = "\n\n".join(notes); failures.append(ui_message(data, "reading.merge_failed", detail=error_copy(exc, data)))
        else:
            summary = notes[0] if notes else ""
        record = {"id": document["id"], "name": document["name"], "path": document["path"],
                  "sha256": document.get("sha256"), "pages_total": len(document_pages(document)),
                  "pages_read": read_pages, "pages_unread": unread_pages,
                  "full_coverage": not unread_pages,
                  "text_chunks_total": len(document.get("chunks", [])), "text_chunks_selected": len(read_chunks),
                  "reading_scope": reading_scope, "reading_scope_message": UIMessage("material.scope_full" if reading_scope == "完整文本预读" else "material.scope_datasheet", pages=15).payload(), "text_groups_total": len(groups),
                  "text_groups_processed": len(notes), "complete": bool(notes) and not failures,
                  "failures": failures, "failure_messages": [message_payload(item) for item in failures], "dfc_structure": documents.dfc_audit(document), "summary": summary,
                  "cache_status": "created"}
        records.append(record)
        if record["complete"]:
            save_material_summary_cache(document, data["model"], full, read_pages, record)
            created_files += 1
        if progress:
            progress("reading", ui_message(data, "reading.complete", index=file_index, total=total_documents, name=document["name"]),
                     12 + int(file_index / max(total_documents, 1) * 48))
    report = {"context_revision": state.data.get("context_revision"), "created_at": datetime.now().astimezone().isoformat(timespec="seconds"), "model": data["model"], "requested_full_coverage": full,
              "files": records, "complete": all(item["complete"] for item in records), "model_calls": total_calls,
              "reused_files": reused_files, "created_files": created_files}
    write_json_atomically(coverage_path(state), report)
    return report


def coverage_summary_for_answer(coverage: dict | None) -> dict | None:
    """Local, auditable reading facts shown next to a classification answer."""
    if not coverage or not coverage.get("files"):
        return None
    files = []
    for item in coverage.get("files", []):
        if not isinstance(item, dict):
            continue
        files.append({
            "name": item.get("name", "未知文件"),
            "scope": item.get("reading_scope", "已读取"),
            "scope_message": item.get("reading_scope_message"),
            "pages_total": item.get("pages_total", 0),
            "pages_read": item.get("pages_read", []),
            "pages_unread": item.get("pages_unread", []),
            "cache_status": item.get("cache_status", ""),
            "complete": bool(item.get("complete")),
        })
    return {"files": files, "complete": bool(coverage.get("complete")),
            "reused_files": int(coverage.get("reused_files", 0)),
            "created_files": int(coverage.get("created_files", 0)),
            "model_calls": int(coverage.get("model_calls", 0))}


def needs_bg_preparation(question: str, bg_context: dict | None) -> bool:
    if not bg_context:
        return False
    text = question.casefold()
    return any(term in text for term in ("分类", "类别", "完整", "全部", "综合", "总结", "codebook", "baugruppe", "classify", "gantry", "greifer", "roboter", "rotationseinheit", "kombinierte"))


def codebook_text(documents: LocalDocumentLibrary, bg_context: dict | None) -> str:
    profile = (bg_context or {}).get("locked_profile") or {}
    profile_text = json.dumps(profile, ensure_ascii=False)
    codebook_id = (bg_context or {}).get("codebook_id")
    document = next((item for item in documents.list() if item.get("id") == codebook_id), None)
    return profile_text + "\n" + "\n".join(str(chunk.get("text", "")) for chunk in (document or {}).get("chunks", []))


CODEBOOK_CLASS_ALIASES = {
    "linear einheit": ("linear einheit", "lineareinheit", "linear unit", "linear axis", "线性单元", "直线单元", "平移单元"),
    "gantry": ("gantry", "gantry system", "portal", "portalachse", "龙门", "桁架"),
    "roboter": ("roboter", "robot", "robotic", "机器人"),
    "greifer/endeffektor": ("greifer/endeffektor", "greifer", "endeffektor", "end-effektor", "end effector", "gripper", "夹爪", "末端执行器"),
    "handhabungsbaugruppe": ("handhabungsbaugruppe", "handhabung", "handling assembly", "handling module", "搬运装配体", "搬运模块", "搬运单元"),
    "rotationseinheit": ("rotationseinheit", "rotation unit", "rotary unit", "旋转单元", "转动单元"),
    "kombinierte einheit": ("kombinierte einheit", "combined unit", "combined assembly", "组合单元", "组合装配体", "复合单元"),
}


def _codebook_name_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold().replace("ä", "a").replace("ö", "o").replace("ü", "u").replace("ß", "ss")).strip()


def _codebook_aliases(class_name: str) -> tuple[str, ...]:
    key = _codebook_name_key(class_name)
    aliases = [class_name]
    for known_name, known_aliases in CODEBOOK_CLASS_ALIASES.items():
        if key == _codebook_name_key(known_name):
            aliases.extend(known_aliases)
            break
    return tuple(dict.fromkeys(alias.casefold() for alias in aliases if str(alias).strip()))


def _rule_pages(rule: dict) -> list[int]:
    return [int(page) for page in rule.get("pages", []) if str(page).isdigit() and int(page) > 0]


def relevant_codebook_page_evidence(question: str, bg_context: dict | None, maximum_pages: int = 3) -> list[dict]:
    """Attach original pages for the rules most relevant to this question.

    The locked profile remains the normal prompt context.  These page images
    are a targeted audit trail for the model, not a repeated full Codebook
    upload.
    """
    profile = (bg_context or {}).get("locked_profile") or {}
    path = Path(str((bg_context or {}).get("codebook_path", "")))
    if not path.is_file() or path.suffix.lower() != ".pdf":
        return []
    limit = max(0, int(maximum_pages))
    if not limit:
        return []
    query = question.casefold()
    words = {word for word in re.findall(r"[\wäöüß-]{3,}", query)}
    # Candidate tuples retain their source relation.  This allows a Chinese
    # question to select a German source page through a class alias, while the
    # visual page label remains strictly grounded in the locked profile.
    candidates: list[tuple[int, int, list[int], str, str]] = []
    for class_index, cls in enumerate(profile.get("classes", [])):
        if not isinstance(cls, dict):
            continue
        name = str(cls.get("name", "")).strip()
        aliases = _codebook_aliases(name)
        alias_hits = sum(1 for alias in aliases if alias and alias in query)
        class_text = " ".join([name, str(cls.get("definition", ""))] + [str(rule.get("text", "")) for group in ("decision_rules", "boundaries") for rule in cls.get(group, []) if isinstance(rule, dict)])
        lexical_hits = sum(word in class_text.casefold() for word in words)
        class_score = alias_hits * 100 + lexical_hits
        definition_pages = [int(page) for page in cls.get("evidence_pages", []) if str(page).isdigit() and int(page) > 0]
        # A named class is the strongest signal. Its evidence/definition page
        # is deliberately considered before narrower rules to yield an
        # explainable, stable fallback for short multilingual questions.
        if definition_pages:
            candidates.append((class_score, class_index * 10, definition_pages, f"class {name}", str(cls.get("definition", ""))))
        for group_index, group_name in enumerate(("decision_rules", "boundaries"), start=1):
            for rule_index, rule in enumerate(cls.get(group_name, [])):
                if not isinstance(rule, dict):
                    continue
                pages = _rule_pages(rule)
                if not pages:
                    continue
                rule_id, text = str(rule.get("id", "")).strip(), str(rule.get("text", ""))
                rule_id_hit = bool(rule_id and rule_id.casefold() in query)
                rule_hits = sum(word in text.casefold() for word in words)
                score = class_score + (80 if rule_id_hit else 0) + rule_hits
                candidates.append((score, class_index * 10 + group_index + rule_index / 1000,
                                   pages, f"class {name}, {group_name[:-1]} {rule_id or rule_index + 1}", text))
    for group_offset, group_name in enumerate(("global_rules", "table_rules"), start=1000):
        for rule_index, rule in enumerate(profile.get(group_name, [])):
            if not isinstance(rule, dict):
                continue
            pages = _rule_pages(rule)
            if not pages:
                continue
            rule_id, text = str(rule.get("id", "")).strip(), str(rule.get("text", ""))
            score = (80 if rule_id and rule_id.casefold() in query else 0) + sum(word in text.casefold() for word in words)
            candidates.append((score, group_offset + rule_index / 1000, pages,
                               f"{group_name[:-1]} {rule_id or rule_index + 1}", text))

    # When there is no reliable hit, retain only definition/core-rule pages in
    # profile order.  This is deterministic and meaningful, unlike selecting
    # arbitrary rule IDs merely because their lexical scores all equal zero.
    reliable = [item for item in candidates if item[0] > 0]
    ranked = sorted(reliable or candidates, key=lambda item: (-item[0], item[1]))
    selected, seen = [], set()
    for _score, _order, pages, relation, text in ranked:
        for page in pages:
            if page in seen:
                continue
            selected.append({"id": "locked-codebook-page", "name": path.name,
                             "label": f"{path.name} — Codebook {relation}, page {page}",
                             "text": text, "visual": {"kind": "pdf_page", "path": str(path), "page": page}})
            seen.add(page)
            if len(selected) >= limit:
                return selected
    return selected


def classification_scope(documents, context):
    if not context:
        return None
    scope = dict(context)
    source = next((item for item in documents.list() if item["id"] == context["codebook_id"]), None)
    scope["_codebook_pages"] = document_pages(source) if source else []
    return scope


def validate_classification(action: dict, evidence: list[dict], codebook: str,
                            profile: dict | None = None, bg_context: dict | None = None) -> str | None:
    """Check schema, fixed labels and provenance, not engineering semantics."""
    classification = action.get("classification")
    if not isinstance(classification, dict):
        return "Missing classification object"
    if not isinstance(profile, dict):
        return "No locked Codebook rules are available"
    names = {item["name"] for item in profile.get("classes", [])
             if isinstance(item, dict) and isinstance(item.get("name"), str)}
    label = classification.get("label")
    if not isinstance(label, str) or not label or label not in names:
        return "Class label must exactly match one locked Codebook class"
    confidence = classification.get("confidence")
    if not isinstance(confidence, str) or confidence not in {"high", "medium", "low"}:
        return "confidence must be high, medium or low"
    alternative = classification.get("alternative_label", "")
    if not isinstance(alternative, str) or (alternative and alternative not in names):
        return "alternative_label must be empty or one exact locked class"
    uncertainties = classification.get("uncertainties", [])
    if not isinstance(uncertainties, list) or any(not isinstance(item, str) for item in uncertainties):
        return "uncertainties must be a string list"

    manifest = classification_manifest(evidence, bg_context)
    supplied = {item.get("label") for item in evidence if isinstance(item.get("label"), str)}
    labels = classification.get("evidence_labels")
    if not isinstance(labels, list) or not labels or any(not isinstance(item, str) or item not in supplied for item in labels):
        return "evidence_labels must copy supplied evidence labels exactly"
    bg_refs = classification.get("bg_evidence_pages")
    if not isinstance(bg_refs, list) or not bg_refs or any(
        not isinstance(item, str) or item not in manifest["bg_labels"] or item not in labels for item in bg_refs
    ):
        return "bg_evidence_pages must copy cited BG page/sheet/row/chunk labels; Codebook-only evidence is not BG evidence"

    rules: dict[str, dict] = {}
    groups = [profile.get("global_rules", []), profile.get("table_rules", [])]
    for item in profile.get("classes", []):
        if isinstance(item, dict):
            groups.extend([item.get("decision_rules", []), item.get("boundaries", [])])
    for group in groups:
        for rule in group if isinstance(group, list) else []:
            if isinstance(rule, dict) and isinstance(rule.get("id"), str) and rule["id"]:
                if rule["id"] in rules and rules[rule["id"]] != rule:
                    return "The locked profile contains an ambiguous rule ID"
                rules[rule["id"]] = rule
    rule_ids = classification.get("codebook_rule_ids")
    if not isinstance(rule_ids, list) or not rule_ids or any(not isinstance(item, str) or item not in rules for item in rule_ids):
        return "codebook_rule_ids must reference existing string IDs from the locked rules"

    pages = classification.get("codebook_rule_pages")
    if not isinstance(pages, list) or any(type(page) is not int or page < 1 for page in pages):
        return "codebook_rule_pages must be positive integer pages, or an empty list for nonpaged rules"
    rule_refs = classification.get("codebook_rule_refs", [])
    if not isinstance(rule_refs, list) or any(not isinstance(item, str) or item not in manifest["codebook_labels"] for item in rule_refs):
        return "codebook_rule_refs must copy supplied Codebook source labels"
    if bg_context and manifest["codebook_source_kind"] == "nonpaged":
        if pages or not rule_refs:
            return "Nonpaged Codebooks require actual section/chunk refs and empty codebook_rule_pages"
    else:
        allowed_pages = {page for rule_id in rule_ids for page in rules[rule_id].get("pages", [])
                         if type(page) is int and page > 0}
        if not pages or not set(pages).issubset(allowed_pages):
            return "Codebook pages must belong to the cited rule or boundary-rule sources"
        if bg_context and not set(pages).issubset(set(bg_context.get("_codebook_pages", []))):
            return "Codebook page reference is outside the actual source document"
    return None


class ClassificationValidationError(ValueError):
    """An unvalidated classification must never become a fallback answer/plan."""


def classification_repair_prompt(base_prompt: str, reason: str, *, required: bool = True) -> str:
    obligation = ("A complete valid classification object is required; do not omit it."
                  if required else "Classification may be null in explanation mode; any non-null object must pass all rules.")
    return base_prompt + f"""

IMPORTANT: The preceding JSON action was rejected locally: {reason}.
Return the complete valid JSON action again. {obligation}
Copy exact locked class names, existing string rule IDs, and supplied reference-manifest labels.
Use physical Codebook pages only for PDF sources and only for the cited rule pages.
For nonpaged Codebooks use actual section/chunk labels in codebook_rule_refs, with codebook_rule_pages=[].
BG evidence must use BG labels, not Codebook labels. Do not add commentary outside JSON.
"""


def complete_model_action(raw):
    """Require the whole action, rather than extracting a complete inner object."""
    text = raw.strip()
    if text.startswith("```"):
        fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.I | re.S)
        if not fenced:
            raise ValueError("Incomplete fenced JSON action")
        text = fenced.group(1)
    if not isinstance(json.loads(text), dict):
        raise ValueError("Model action must be one complete object")
    return parse_json(text)


def validated_model_action(raw, prompt, *, evidence, scope, validation, repair, notices, language="zh"):
    """One validator for every round; one repair budget for the entire answer."""
    while True:
        action = None
        try:
            action = complete_model_action(raw)
            if action.get("classification") is not None:
                validation["required"] = True
            problem = validate_classification(
                action, evidence, "", (scope or {}).get("locked_profile"), scope
            ) if validation["required"] else None
        except (ValueError, TypeError) as exc:
            problem = str(exc)
        if not problem:
            return action
        if not scope and not validation["required"]:
            raise ValueError(problem)
        if validation["repairs"] >= 1 or not scope:
            raise ClassificationValidationError("Classification/action validation failed: " + problem)
        validation["repairs"] += 1
        notices.append(UIMessage('notice.repair', language, detail=problem))
        raw = repair(classification_repair_prompt(prompt, problem, required=validation["required"]))
        # No success notice until this same validator accepts the repaired action.


def image_group_notices(data, report):
    return [ui_message(data, 'notice.image_group_overview' if item['overview'] else 'notice.image_group_full',
                       name=item['name'], count=item['count'], details=item.get('details', 0))
            for item in report.get('image_group_details', [])]


def call_model(data: dict[str, Any], question: str, progress=None, *, require_classification: bool = True) -> dict[str, Any]:
    state, documents, llm = data["state"], data["documents"], data["llm"]
    ensure_current_sources(data)
    invalidate_pending(data)
    def report(phase: str, text: str, percent: int | None = None) -> None:
        check_request(data)
        if progress:
            progress(phase, text, percent)

    report("search", ui_message(data, 'progress.check'), 5)
    bg_context = state.data.get("bg_context")
    active_source_ids = state.data.get("active_source_ids", [])
    matches = state.search(question)
    snippets = {item: excerpt(state, item, question) for item in matches}
    preferred = ([bg_context.get("codebook_id")] + list(bg_context.get("source_ids", []))) if bg_context else active_source_ids
    allowed = list(bg_context.get("source_ids", [])) + [bg_context.get("codebook_id")] if bg_context else active_source_ids
    report("search", ui_message(data, 'progress.search'), 10)
    evidence = documents.search(question, preferred_ids=preferred, classification=bool(bg_context), allowed_ids=allowed)
    if bg_context:
        existing = {(item.get("visual") or {}).get("page") for item in evidence if item.get("name") == bg_context.get("codebook_name")}
        evidence.extend(item for item in relevant_codebook_page_evidence(question, bg_context) if (item.get("visual") or {}).get("page") not in existing)
    report("search", ui_message(data, 'progress.visual'), 12)
    evidence = documents.ensure_ocr_for_snippets(evidence, question, classification=bool(bg_context))
    visuals = documents.visual_paths(evidence, state.root / "visual_cache",
                                     bilder_images=documents.bilder_image_paths(allowed))
    reasoning, notices = [], []
    visual_report = documents.last_visual_report
    if visual_report.get("short_drawings"):
        names = "、".join(str(name) for name in visual_report["short_drawings"])
        notices.append(ui_message(data, 'notice.short_drawings', names=names, count=visual_report.get("attachments", 0), kb=int(visual_report.get("bytes", 0)) // 1024))
    if visual_report.get("image_groups"):
        notices.extend(image_group_notices(data, visual_report))
    if visual_report.get("dfc"):
        for item in visual_report["dfc"]:
            parts = "、".join(str(part) for part in item.get("segments_used", [])) or "—"
            notices.append(ui_message(data, 'notice.dfc', name=item.get("name"), status=ui_state(data, item.get("ocr_status")), segments=parts))
    if visual_report.get("skipped"):
        notices.append(ui_message(data, 'notice.visual_skipped'))

    def events(kind: str, text: str):
        if kind == "reasoning": reasoning.append(text)
        elif kind == "notice": notices.append(localize_message(text, data.get("language", "zh")))

    usage_records: list[dict] = []
    coverage = load_coverage(state)
    auto_prepared = False
    classification_request = bool(bg_context) and require_classification
    # Once a material range is confirmed as a Baugruppe, its first question
    # should transparently prepare the shared understanding, even if the user
    # phrases it as a natural question rather than using a classification word.
    preparation_request = bool(bg_context)
    if not coverage_matches_current_selection(data, coverage) and preparation_request:
        report("reading", ui_message(data, 'progress.reading_start'), 12)
        coverage = prepare_coverage(data, progress=report, usage_records=usage_records)
        auto_prepared = True
        report("reading", ui_message(data, 'progress.reading_done'), 62)
    elif preparation_request:
        report("reading", ui_message(data, 'progress.reading_reused'), 62)
    coverage_summaries = coverage.get("files", []) if coverage.get("complete") else []
    dossier = None
    if coverage_summaries:
        try:
            report("dossier", ui_message(data, 'progress.dossier'), 70)
            dossier, _, dossier_created = prepare_bg_dossier(data, coverage, usage_records=usage_records)
            if dossier_created:
                notices.append(ui_message(data, 'notice.dossier_created'))
            elif dossier:
                notices.append(ui_message(data, 'notice.dossier_reused'))
            report("dossier", ui_message(data, 'progress.dossier_ready'), 80)
        except RequestStopped:
            raise
        except Exception as exc:
            notices.append(ui_message(data, 'notice.dossier_failed', detail=error_copy(exc, data)))
            dossier = None
    model_prompt = prompt_for(state, question, snippets, document_snippets=evidence, bg_context=bg_context,
                              coverage_summaries=[] if dossier else coverage_summaries, bg_dossier=dossier,
                              response_language=data.get("language", "zh"), require_classification=classification_request)
    report("model", ui_message(data, 'progress.connect', model=data["model"]), 86)
    model_started = False
    preview = AnswerPreview()
    def model_events(kind: str, text: str):
        nonlocal model_started
        events(kind, text)
        check_request(data)
        if kind == "content":
            delta = preview.feed(text)
            if delta and data.get("answer_events"):
                data["answer_events"]({"type": "answer_delta", "text": delta})
        if not model_started:
            model_started = True
            report("model", ui_message(data, 'progress.generating'), 92)

    def answer_call(prompt, tokens):
        nonlocal preview
        check_request(data)
        limit = data["request_control"].policy.max_answer_chars if data.get("request_control") else 131072
        preview = AnswerPreview(limit)
        if data.get("answer_events"):
            data["answer_events"]({"type": "answer_reset"})
        raw_response = accounted_model_call(data, llm, visuals, prompt, SYSTEM,
                                            {"maxOutputTokens": tokens, "temperature": 0}, stream=True,
                                            event_handler=model_events, usage_records=usage_records)
        # Non-streaming providers cannot emit early chunks; still use the same
        # safe answer decoder, without replaying chunks from streaming providers.
        if not preview.started and not preview.disabled:
            model_events("content", raw_response)
        return raw_response

    report("model", ui_message(data, 'progress.waiting'), 90)
    raw = answer_call(model_prompt, 4096)
    raw = require_model_success(raw, ui_message(data, 'model.context_main'))
    validation = {"required": classification_request, "repairs": 0}
    scope = classification_scope(documents, bg_context)

    def repair_classification(repair_prompt):
        report("validation", ui_message(data, 'progress.repair'), 96)
        repaired = answer_call(repair_prompt, 4096)
        repaired = require_model_success(repaired, ui_message(data, 'model.context_repair'))
        return repaired

    def validated_action(raw_response: str, request_prompt: str) -> dict:
        result = validated_model_action(raw_response, request_prompt, evidence=evidence, scope=scope,
                                        validation=validation, repair=repair_classification, notices=notices, language=data.get("language", "zh"))
        check_answer_size(data, result["answer"])
        return result

    try:
        report("validation", ui_message(data, 'progress.validation'), 96)
        action = validated_action(raw, model_prompt)
    except RequestStopped:
        raise
    except Exception as exc:
        if bg_context or isinstance(exc, ClassificationValidationError):
            raise ClassificationValidationError(str(exc)) from exc
        if looks_like_action(raw):
            raise ValueError("Incomplete or invalid action JSON; no answer committed") from exc
        # Some Bosch Farm models return a normal natural-language answer despite
        # the code-action schema. A read-only question must remain useful:
        # show that answer and never treat it as a file modification.
        answer = raw.strip() or str(ui_message(data, "model.empty"))
        check_answer_size(data, answer)
        with commit_answer(data):
            title_session_from_question(state, question)
            state.add_turn("user", question)
            state.add_turn("assistant", answer)
        if auto_prepared:
            notices.insert(0, ui_message(data, 'notice.auto_prepared', files=len(coverage.get("files", [])), calls=coverage.get("model_calls", 0)))
        report("complete", ui_message(data, 'model.complete'), 100)
        return {"answer": answer, "reasoning": "".join(reasoning), "notices": notices, "notice_messages": [message_payload(item) for item in notices],
                "sources": evidence, "dfc_evidence": visual_report.get("dfc", []), "visuals": visuals, "changes": [], "can_export_bg": False,
                "classification": None, "coverage_summary": coverage_summary_for_answer(coverage) if classification_request else None,
                "turn_usage": summarize_usage(usage_records), "model_response": llm.last_response_model or data["model"],
                "turn_cost": summarize_usage(usage_records)["cost_usd"],
                "usage": status_data(data)}
    requested = [ensure_relative(item) for item in action.get("read_files", [])[:4] if isinstance(item, str)]
    complete = {}
    for relative in requested:
        check_request(data)
        path = state.resolve_relative(relative)
        if path.is_file() and path.stat().st_size <= 1_000_000:
            complete[relative] = path.read_text(encoding="utf-8", errors="replace")
            state.refresh_file(relative)
    if complete:
        model_prompt = prompt_for(state, question, snippets, complete, evidence, bg_context,
                                  [] if dossier else coverage_summaries, dossier, data.get("language", "zh"),
                                  require_classification=classification_request)
        report("model", ui_message(data, 'progress.supplementary'), 93)
        raw = answer_call(model_prompt, 3000)
        raw = require_model_success(raw, ui_message(data, 'model.context_supplementary'))
        try:
            action = validated_action(raw, model_prompt)
        except RequestStopped:
            raise
        except Exception as exc:
            if bg_context or isinstance(exc, ClassificationValidationError): raise
            if looks_like_action(raw):
                raise ValueError("Incomplete or invalid action JSON; no answer committed") from exc
            check_answer_size(data, raw)
            notices.append(ui_message(data, 'notice.supplementary_failed', detail=error_copy(exc, data)))
            action = {"answer": raw.strip() or str(ui_message(data, "model.empty")), "changes": [], "classification": None}
    for change in action.get("changes", []):
        if isinstance(change, dict) and state.resolve_relative(change.get("path", "")).exists() and change.get("path") not in complete:
            raise ValueError("A complete current file must be read before proposing its replacement")
    with commit_answer(data):
        changes = build_diff(state, action.get("changes", []))
        plan_id = publish_pending(data, changes)
        title_session_from_question(state, question)
        state.add_turn("user", question); state.add_turn("assistant", action.get("answer", ""))
        turn_token_usage = summarize_usage(usage_records)
        if bg_context:
            state.data["last_bg_analysis"] = {
                "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "session": state.root.name,
                "model": llm.last_response_model or data["model"],
                "question": question,
                "answer": action.get("answer", ""),
                "sources": [str(item.get("label", item.get("name", "未知来源"))) for item in evidence],
                "dfc_evidence": visual_report.get("dfc", []),
                "bg_context": dict(bg_context),
                "token_usage": turn_token_usage,
            }
            state.save()
    if auto_prepared:
        notices.insert(0, ui_message(data, 'notice.auto_prepared', files=len(coverage.get("files", [])), calls=coverage.get("model_calls", 0)))
    report("complete", ui_message(data, 'model.complete'), 100)
    return {"answer": action.get("answer", ""), "reasoning": "".join(reasoning), "notices": notices, "notice_messages": [message_payload(item) for item in notices],
            "sources": evidence, "dfc_evidence": visual_report.get("dfc", []), "visuals": visuals, "changes": [{k: v for k, v in item.items() if k != "content"} for item in changes],
            "plan_id": plan_id, "can_export_bg": bool(bg_context),
            "turn_usage": turn_token_usage,
            "model_response": llm.last_response_model or data["model"],
            "turn_cost": turn_token_usage["cost_usd"],
            "classification": action.get("classification"),
            "coverage_summary": coverage_summary_for_answer(coverage) if action.get("classification") is not None else None,
            "usage": status_data(data)}


def call_comparison(data: dict[str, Any], question: str, models: list[str]) -> dict[str, Any]:
    """Run an isolated, read-only answer for each model against identical BG evidence."""
    ensure_current_sources(data)
    state, documents = data["state"], data["documents"]
    bg_context = state.data.get("bg_context")
    if not bg_context:
        raise HTTPException(400, ui_message(ACTIVE, 'error.bg_required'))
    matches = state.search(question)
    snippets = {item: excerpt(state, item, question) for item in matches}
    preferred = [bg_context.get("codebook_id")] + list(bg_context.get("source_ids", []))
    evidence = documents.search(question, preferred_ids=preferred, classification=True, allowed_ids=preferred)
    evidence.extend(relevant_codebook_page_evidence(question, bg_context))
    evidence = documents.ensure_ocr_for_snippets(evidence, question, classification=True)
    visuals = documents.visual_paths(evidence, state.root / "visual_cache",
                                     bilder_images=documents.bilder_image_paths(preferred))
    visual_report = documents.last_visual_report
    coverage = load_coverage(state)
    dossier = load_bg_dossier_cache(coverage, data["model"]) if coverage_matches_current_selection(data, coverage) else None
    prompt = prompt_for(state, question, snippets, document_snippets=evidence, bg_context=bg_context,
                        coverage_summaries=[] if dossier else (coverage.get("files", []) if coverage.get("complete") else []),
                        bg_dossier=dossier, response_language=data.get("language", "zh"))
    results = []
    for index, model in enumerate(models, start=1):
        notices: list[str] = []
        if visual_report.get("short_drawings"):
            notices.append(ui_message(data, 'notice.short_drawings', names=", ".join(visual_report["short_drawings"]), count=visual_report.get("attachments", 0), kb=int(visual_report.get("bytes", 0)) // 1024))
        if visual_report.get("image_groups"):
            notices.extend(image_group_notices(data, visual_report))
        if visual_report.get("dfc"):
            for item in visual_report["dfc"]:
                parts = "、".join(str(part) for part in item.get("segments_used", [])) or "—"
                notices.append(ui_message(data, 'notice.dfc', name=item.get("name"), status=ui_state(data, item.get("ocr_status")), segments=parts))
        if visual_report.get("skipped"):
            notices.append(ui_message(data, 'notice.visual_skipped'))

        def events(kind: str, text: str):
            if kind == "notice":
                notices.append(localize_message(text, data.get("language", "zh")))

        usage_records: list[dict] = []
        try:
            connector = LLMConnector(model, data["llm"].api_key,
                                     session_id=f"{state.data['session_id']}-comparison-{index}")
            raw = accounted_model_call(data, connector,
                visuals, prompt, SYSTEM, {"maxOutputTokens": 4096, "temperature": 0},
                stream=True, event_handler=events, usage_records=usage_records,
            )
            raw = require_model_success(raw, ui_message(data, 'model.context_compare', model=model))
            actual_model = connector.last_response_model or model
            validation = {"required": True, "repairs": 0}

            def repair_comparison(repair_prompt):
                repaired = accounted_model_call(data, connector, visuals, repair_prompt, SYSTEM,
                                                      {"maxOutputTokens": 4096, "temperature": 0},
                                                      stream=True, event_handler=events, usage_records=usage_records)
                repaired = require_model_success(repaired, ui_message(data, 'model.context_compare_repair', model=model))
                return repaired

            action = validated_model_action(raw, prompt, evidence=evidence,
                                            scope=classification_scope(documents, bg_context),
                                            validation=validation, repair=repair_comparison, notices=notices, language=data.get("language", "zh"))
            answer = action["answer"]
            classification = action["classification"]
            token_usage = summarize_usage(usage_records)
            results.append({"requested_model": model, "model_response": actual_model, "ok": True,
                            "answer": answer, "classification": classification, "usage": token_usage, "notices": notices, "notice_messages": [message_payload(item) for item in notices]})
        except Exception as exc:
            results.append({"requested_model": model, "model_response": model, "ok": False,
                            "answer": "", "error": str(error_copy(exc, data)), "error_message": message_payload(error_copy(exc, data)), "usage": summarize_usage(usage_records), "notices": notices, "notice_messages": [message_payload(item) for item in notices]})
    return {"question": question, "results": results,
            "usage": status_data(data),
            "sources": [str(item.get("label", item.get("name", "未知来源"))) for item in evidence]}


def context_mutation(function):
    @wraps(function)
    def guarded(*args, **kwargs):
        if not LOCK.acquire(blocking=False):
            raise HTTPException(409, ui_message(ACTIVE, 'error.busy'))
        try:
            reject_context_change_while_processing()
            return function(*args, **kwargs)
        finally:
            LOCK.release()
    return guarded


def reset_context(data):
    state = data["state"]
    if state.transcript_path.exists():
        archive = state.root / "archives"; archive.mkdir(exist_ok=True)
        state.transcript_path.rename(archive / (uuid.uuid4().hex + '.jsonl'))
    state.data['history'] = []; state.data['summary'] = ''
    state.data.pop('last_bg_analysis', None)
    coverage_path(state).unlink(missing_ok=True)
    invalidate_pending(data)
    state.data["context_revision"] = uuid.uuid4().hex
    state.save()


def context_issue(data):
    state = data["state"]
    if context_state_error(state.data):
        return "restored_invalid"
    if state.data.get("context_issue"):
        return state.data["context_issue"]
    context = state.data.get("bg_context")
    if context:
        profile = load_codebook_profile()
        if (profile.get("status") != "locked"
                or profile.get("version") != context.get("rule_profile_version")
                or profile.get("draft") != context.get("locked_profile")):
            return "rules_changed"
    ids = set(state.data.get("active_source_ids") or [])
    if state.data.get("bg_context"):
        ids.add(state.data["bg_context"]["codebook_id"])
    if ids - {item["id"] for item in data["documents"].list()}:
        return "index_invalid"
    return ""


def source_binding(documents, ids):
    return [{key: item[key] for key in ("id", "path", "sha256")}
            for item in documents.list() if item["id"] in set(ids)]


def restore_context_binding(data):
    state = data["state"]
    if "source_binding" not in state.data:
        try:
            ensure_current_sources(data)
        except (HTTPException, OSError):
            state.data["context_issue"] = context_issue(data) or "source_changed"
        else:
            state.data["source_binding"] = source_binding(data["documents"], state.data.get("active_source_ids", []))


def ensure_current_sources(data):
    state = data["state"]
    if context_issue(data):
        raise HTTPException(409, ui_message(ACTIVE, 'context.reconfirm'))
    context = state.data.get('bg_context')
    if context:
        profile = load_codebook_profile()
        path = Path(context.get('codebook_path', ''))
        if (profile.get('status') != 'locked' or not valid_rule_profile(profile.get("draft"))
            or profile.get('draft') != context.get('locked_profile')
            or profile.get("version") != context.get("rule_profile_version")
            or profile.get("sha256") != context.get("codebook_sha256")
            or not path.is_file() or file_digest(path) != profile.get('sha256')):
            raise HTTPException(409, ui_message(ACTIVE, 'error.rules_changed'))
    ids = set(state.data.get('active_source_ids') or [])
    bound = state.data.get("source_binding")
    if bound is not None and bound != source_binding(data["documents"], ids):
        raise HTTPException(409, ui_message(ACTIVE, 'context.reconfirm'))
    for item in data['documents'].list():
        if item.get('id') in ids:
            path = Path(item['path'])
            if not path.is_file() or file_digest(path) != item.get('sha256'):
                raise HTTPException(409, ui_message(ACTIVE, 'error.source_changed', path=path.name))


@app.exception_handler(Exception)
@app.exception_handler(ValueError)
@app.exception_handler(OSError)
@app.exception_handler(RuntimeError)
async def readable_error(request: Request, exc: Exception):
    detail = error_copy(exc, {'language': request.headers.get('X-Workbench-Language') or ACTIVE.get('language', 'zh')})
    status = 503 if isinstance(exc, StartupError) and exc.code == 'startup.state_unwritable' else 400
    return JSONResponse(status_code=status, content={"detail": str(detail), **message_payload(detail)})


@app.middleware("http")
async def local_origin_only(request: Request, call_next):
    from urllib.parse import urlsplit
    origin = request.headers.get('origin')
    host = request.headers.get('host', '').split(':')[0]
    if host not in {'127.0.0.1', 'localhost', 'testserver'} or (origin and urlsplit(origin).netloc != request.headers.get('host')):
        return JSONResponse(status_code=403, content={"detail": "Local same-origin access only"})
    return await call_next(request)


@app.get("/", response_class=HTMLResponse)
def index():
    return HTML


def effective_env_file(override: str = '') -> tuple[Path, bool]:
    if override.strip():
        try:
            return Path(override.strip().strip('"')).expanduser().resolve(), True
        except (OSError, ValueError):
            raise StartupError('startup.env_unreadable', path=override) from None
    active_path = ACTIVE.get('env_file')
    return (Path(active_path), bool(ACTIVE.get('env_explicit'))) if active_path else (STARTUP_CONFIG.env_file, STARTUP_CONFIG.env_explicit)


def validate_farm_endpoint(path: Path) -> str:
    try:
        return farm_base_url()
    except ValueError:
        raise StartupError('startup.endpoint_invalid', path=path) from None


@app.post("/api/setup")
@context_mutation
def setup(request: Setup):
    reject_context_change_while_processing()
    if not request.workspace.strip():
        raise HTTPException(400, ui_message(ACTIVE, 'error.workspace_required'))
    workspace = Path(request.workspace.strip().strip('"')).expanduser().resolve()
    if not workspace.is_dir():
        raise HTTPException(400, ui_message(ACTIVE, 'error.workspace_missing', path=workspace))
    state_home = app_state_home()
    if request.state_dir.strip():
        raise StartupError('startup.state_fixed', path=state_home)
    env_file, explicit = effective_env_file(request.env_file)
    try:
        with FARM_ENVIRONMENT.use(env_file, load_dotenv, explicit=explicit) as key:
            validate_farm_endpoint(env_file)
            check_state_directory(state_home)
            state = ProjectState(state_home, workspace, request.session)
            documents = LocalDocumentLibrary(state.root.parent / "documents.json")
            price_file = Path(__file__).resolve().parent / "model_pricing.json"
            language = normalize_language(request.language)
            model = canonical_model_id(request.model)
            connector = LLMConnector(model, key, session_id=state.data["session_id"])
            candidate = {"state": state, "documents": documents, "model": model, "language": language,
                         "llm": connector, "env_file": str(env_file), "env_explicit": explicit,
                         "pricing": PricingCatalog(price_file), "pending": []}
            restore_context_binding(candidate)
            state.scan()
            state.data["selected_model"] = model
            state.save()
            save_workbench_settings(workspace, state.root.name, model, language)
            ACTIVE.clear()
            ACTIVE.update(candidate)
            return status_data(ACTIVE)
    except OSError:
        raise StartupError('startup.state_unwritable', path=state_home) from None


@app.get("/api/status")
def status(): return status_data(session())


@app.post("/api/model")
@context_mutation
def switch_model(request: ModelSwitchRequest):
    reject_context_change_while_processing()
    model = canonical_model_id(request.model)
    if not model:
        raise HTTPException(400, ui_message(ACTIVE, 'model.id_required'))
    with LOCK:
        reject_context_change_while_processing()
        data = session()
        try:
            data["llm"] = LLMConnector(model, data["llm"].api_key, session_id=data["state"].data["session_id"])
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if data["model"] != model: reset_context(data)
        data["model"] = model
        data["state"].data["selected_model"] = model
        data["state"].save()
        save_workbench_settings(data["state"].workspace, data["state"].root.name, model, data.get("language", "zh"))
        return status_data(data)


def activate_local_session(data: dict[str, Any], session_name: str) -> dict:
    with LOCK:
        reject_context_change_while_processing()
        state = ProjectState(app_state_home(), data["state"].workspace, session_name)
        data["state"] = state
        data["documents"] = LocalDocumentLibrary(state.root.parent / "documents.json")
        restore_context_binding(data)
        data["model"] = canonical_model_id(state.data.get("selected_model") or data["model"])
        data["llm"] = LLMConnector(data["model"], data["llm"].api_key, session_id=state.data["session_id"])
        invalidate_pending(data)
        save_workbench_settings(state.workspace, state.root.name, data["model"], data.get("language", "zh"))
        return status_data(data)


@app.post("/api/session/rename")
@context_mutation
def rename_session(request: SessionRenameRequest):
    with LOCK:
        reject_context_change_while_processing()
        data = session()
        name = safe_name(request.name.strip())
        state = data["state"] if not request.source.strip() else ProjectState(app_state_home(), data["state"].workspace, safe_name(request.source.strip()))
        if not state.root.is_dir():
            raise HTTPException(404, ui_message(ACTIVE, 'error.session_missing'))
        target = state.root.parent / name
        if target == state.root:
            return status_data(data)
        if target.exists():
            raise HTTPException(409, ui_message(ACTIVE, 'error.session_exists'))
        try:
            state.root.rename(target)
        except OSError as exc:
            raise HTTPException(500, ui_message(ACTIVE, 'error.session_rename', detail=error_copy(exc, ACTIVE))) from exc
        return activate_local_session(data, name) if state.root == data["state"].root else status_data(data)


@app.post("/api/session/delete")
@context_mutation
def delete_session(request: SessionDeleteRequest):
    with LOCK:
        reject_context_change_while_processing()
        if not request.confirmed:
            raise HTTPException(400, ui_message(ACTIVE, 'error.confirmation'))
        data = session()
        state = data["state"] if not request.name.strip() else ProjectState(app_state_home(), data["state"].workspace, safe_name(request.name.strip()))
        if not state.root.is_dir():
            raise HTTPException(404, ui_message(ACTIVE, 'error.session_missing'))
        current = state.root
        parent = current.parent
        try:
            shutil.rmtree(current)
        except OSError as exc:
            raise HTTPException(500, ui_message(ACTIVE, 'error.session_delete', detail=error_copy(exc, ACTIVE))) from exc
        remaining = available_sessions(ProjectState(app_state_home(), data["state"].workspace, "default")) if parent.is_dir() else []
        return activate_local_session(data, str(remaining[0]["name"]) if remaining else "default") if current == data["state"].root else status_data(data)


@app.get("/api/settings")
def settings():
    # Only the local path is returned. No source documents or credentials leave this computer.
    return load_workbench_settings()


@app.post("/api/language")
def set_language(request: LanguageRequest):
    language = normalize_language(request.language)
    with LOCK:
        if ACTIVE:
            data = session(); data['language'] = language
            save_workbench_settings(data['state'].workspace, data['state'].root.name, data['model'], language)
        else:
            settings = load_workbench_settings(); settings['language'] = language
            write_json_atomically(workbench_settings_path(), settings)
    return {"language": language}


@app.get("/api/sessions")
def sessions(offset: int = 0, limit: int = 10):
    state = session()["state"]
    records = available_sessions(state)
    start, amount = max(0, offset), max(1, min(20, limit))
    return {"current": state.root.name, "sessions": records[start:start + amount], "has_more": start + amount < len(records)}


@app.post("/api/session/open")
@context_mutation
def open_saved_session(request: SessionOpenRequest):
    with LOCK:
        reject_context_change_while_processing()
        data = session(); name = safe_name(request.name.strip())
        target = data["state"].root.parent / name
        if not target.is_dir():
            raise HTTPException(404, ui_message(ACTIVE, 'error.session_missing'))
        return activate_local_session(data, name)


@app.post("/api/session/new")
@context_mutation
def create_session():
    with LOCK:
        reject_context_change_while_processing()
        data = session()
        stamp = datetime.now().astimezone().strftime("新聊天_%Y%m%d_%H%M%S")
        return activate_local_session(data, stamp)


@app.post("/api/session/pin")
@context_mutation
def pin_session(request: SessionPinRequest):
    reject_context_change_while_processing()
    data = session(); name = safe_name(request.name.strip())
    target = data["state"].root.parent / name
    if not target.is_dir():
        raise HTTPException(404, ui_message(ACTIVE, 'error.session_missing'))
    saved = ProjectState(app_state_home(), data["state"].workspace, name)
    saved.data["sidebar_pinned"] = bool(request.pinned); saved.save()
    return {"name": name, "pinned": bool(request.pinned)}


@app.get("/api/history")
def history():
    records = session()["state"].full_history()
    return {"history": [
        {"role": item.get("role", "assistant"), "content": str(item.get("content", ""))}
        for item in records if isinstance(item, dict) and item.get("content")
    ]}


@app.get("/api/session/context")
def session_context():
    data = session(); state = data["state"]
    return {"model": data["model"], "target": state.data.get("selected_target", {}),
            "codebook_path": state.data.get("selected_codebook_path", ""),
            "bg_context": state.data.get("bg_context"), "context_issue": context_issue(data)}


@app.get("/api/model-tests")
def model_tests():
    return {"tests": load_model_tests()}


@app.get("/api/diagnostics")
@context_mutation
def diagnostics():
    """Local-only readiness checks; this endpoint never contacts Bosch Farm."""
    return local_diagnostics()


@app.post("/api/model-test")
@context_mutation
def model_test(request: ModelTestRequest):
    env_file, explicit = effective_env_file()
    with FARM_ENVIRONMENT.use(env_file, load_dotenv, explicit=explicit, commit=not bool(ACTIVE)) as key:
        validate_farm_endpoint(env_file)
        check_state_directory(app_state_home())
        return run_model_test(request, key)


def run_model_test(request: ModelTestRequest, key: str):
    model = request.model.strip()
    if not model:
        raise HTTPException(400, ui_message(ACTIVE, 'model.id_required'))
    def record(ok: bool, message: str, **extra):
        result = {
            "requested_model": model, "ok": ok, "message": str(message), **message_payload(message),
            "tested_at": datetime.now().astimezone().isoformat(timespec="seconds"), **extra,
        }
        save_model_test(result)
        return result
    try:
        probe = LLMConnector(model, key, session_id=f"model_check_{os.urandom(6).hex()}")
        notices = []
        answer = probe.ask_about_files(
            [], "Reply with exactly OK.", "You are a connection test. Follow the user instruction exactly.",
            {"maxOutputTokens": 32, "temperature": 0}, stream=True,
            event_handler=lambda kind, text: notices.append(text) if kind == "notice" else None,
        )
        answer = require_model_success(answer, ui_message(ACTIVE, 'model.test'))
        usage = probe.get_last_token_usage() or {}
        if any(getattr(item, 'message_key', '') == 'notice.stream_fallback' for item in notices):
            streaming = ui_message(ACTIVE, 'model.stream_fallback')
        elif notices:
            streaming = ui_message(ACTIVE, 'model.stream_full')
        else:
            streaming = ui_message(ACTIVE, 'model.stream_native')
        usage_available = bool(usage) and (
            "input_tokens" in usage or "output_tokens" in usage or "total_tokens" in usage
        )
        message = ui_message(ACTIVE, 'model.test_ok' if usage_available else 'model.test_no_usage')
        return record(
            True, message,
            model=probe.last_response_model or model, answer=answer[:120], streaming=str(streaming),
            streaming_message=message_payload(streaming),
            usage_available=usage_available,
            input_tokens=usage.get("input_tokens", 0), output_tokens=usage.get("output_tokens", 0),
        )
    except Exception as exc:
        return record(False, error_copy(exc, ACTIVE), model=model)


@app.get("/api/pick/{kind}")
def pick(kind: str, request: Request):
    """Use the local Python GUI only as a native path chooser, never for files."""
    if kind not in {"file", "folder"}:
        raise HTTPException(400, ui_message(ACTIVE, 'error.picker_type'))
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        language = request.headers.get('X-Workbench-Language') or ACTIVE.get('language', 'zh')
        value = filedialog.askopenfilename(title=ui_message(language, 'picker.file_title')) if kind == "file" else filedialog.askdirectory(title=ui_message(language, 'picker.folder_title'))
        root.destroy()
    except Exception as exc:
        raise HTTPException(501, ui_message(ACTIVE, 'error.picker_failed', detail=error_copy(exc, ACTIVE))) from exc
    return {"path": value}


@app.get("/api/documents")
def documents():
    return [{"id": item["id"], "name": item["name"], "path": item["path"], "chunks": len(item.get("chunks", [])),
             "material_role": item.get("material_role", "other"),
             "material_role_label": material_role_label(item.get("material_role", "other"))}
            for item in session()["documents"].list() if item["id"] in set(session()["state"].data.get("active_source_ids") or [])]


@app.post("/api/document")
@context_mutation
def add_document(request: PathRequest):
    reject_context_change_while_processing()
    if session()["state"].data.get("bg_context") or context_issue(session()):
        raise HTTPException(409, ui_message(ACTIVE, 'context.reconfirm'))
    item = session()["documents"].add(str(safe_file(request.path)))
    state = session()["state"]
    state.data.setdefault("active_source_ids", []).append(item["id"])
    state.data["active_source_ids"] = list(dict.fromkeys(state.data["active_source_ids"]))
    state.data["source_binding"] = source_binding(session()["documents"], state.data["active_source_ids"])
    state.data["context_revision"] = uuid.uuid4().hex
    invalidate_pending(session())
    state.save()
    return {"id": item["id"], "name": item["name"], "chunks": len(item["chunks"]),
            "material_role": item.get("material_role", "other"),
            "material_role_label": material_role_label(item.get("material_role", "other"))}


@app.post("/api/bg")
@context_mutation
def activate_bg(request: BGRequest):
    reject_context_change_while_processing()
    return analyze_target(TargetRequest(target=request.folder, selected_paths=["."]))
    data = session(); codebook = data["documents"].add(str(safe_file(request.codebook)))
    folder = Path(request.folder.strip().strip('"')).expanduser().resolve()
    sources, skipped = data["documents"].add_folder(str(folder))
    data["state"].data["bg_context"] = {"codebook_id": codebook["id"], "codebook_name": codebook["name"],
        "source_ids": [item["id"] for item in sources], "folder": str(folder)}
    data["state"].save()
    return {"sources": len(sources), "skipped": skipped[:10], "status": status_data(data)}


def restore_state_file(path: Path, original: bytes | None):
    if original is None:
        path.unlink(missing_ok=True)
    elif not path.exists() or path.read_bytes() != original:
        temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex + ".restore")
        try:
            temporary.write_bytes(original)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


@app.post("/api/target")
@context_mutation
def analyze_target(request: TargetRequest):
    """Prepare against a private index copy, then commit or restore all bindings."""
    reject_context_change_while_processing()
    data = session()
    if not request.target.strip():
        raise HTTPException(400, ui_message(ACTIVE, 'error.target_required'))
    target = Path(request.target.strip().strip('"')).expanduser().resolve()
    profile = load_codebook_profile()
    codebook_path = None
    if profile.get("status") == "locked":
        codebook_path = Path(str(profile.get("source_path", "")))
        if (not valid_rule_profile(profile.get("draft")) or not codebook_path.is_file()
                or file_digest(codebook_path) != profile.get("sha256")):
            raise HTTPException(409, ui_message(ACTIVE, 'error.rules_changed'))
    elif data["state"].data.get("context_issue") == "rules_changed":
        raise HTTPException(409, ui_message(ACTIVE, 'error.rules_lock'))

    # Defer index writes while preserving content-addressed parser/OCR caches.
    documents = data["documents"]
    staged = copy.copy(documents)
    staged.data = copy.deepcopy(documents.data)
    staged._defer_save = True
    selected, sources, skipped = [], [], []
    if target.is_file():
        sources = [staged.add(str(target))]
        target_kind = "文件"
    elif target.is_dir():
        selected = selected_target_files(target, request.selected_paths)
        if not selected:
            raise HTTPException(400, ui_message(ACTIVE, 'materials.selection_required'))
        for path in selected:
            try:
                sources.append(staged.add(str(path)))
            except OSError:
                raise
            except Exception as exc:
                skipped.append(f"{path.name}: {exc}")
        if not sources:
            raise HTTPException(400, ui_message(ACTIVE, "error.material_unreadable", detail="; ".join(skipped[:10])))
        target_kind = "文件夹"
    else:
        raise HTTPException(400, ui_message(ACTIVE, 'error.file_missing', path=target))
    codebook = staged.add(str(codebook_path)) if codebook_path else None
    if profile != load_codebook_profile():
        raise HTTPException(409, ui_message(ACTIVE, 'error.rules_changed'))
    for item in sources + ([codebook] if codebook else []):
        if file_digest(Path(item["path"])) != item["sha256"]:
            raise HTTPException(409, ui_message(ACTIVE, 'context.reconfirm'))

    state = data["state"]
    old_state, old_index = state.data, documents.data
    candidate = copy.deepcopy(old_state)
    candidate.update({
        "history": [], "summary": "", "context_issue": "", "context_schema_version": 1,
        "context_revision": uuid.uuid4().hex,
        "active_source_ids": [item["id"] for item in sources],
        "selected_target": {
            "path": str(target), "kind": target_kind,
            "selected_paths": [path.relative_to(target).as_posix() for path in selected] if target.is_dir() else [str(target)],
            "codebook_path": str(codebook_path) if codebook_path else "",
        },
    })
    candidate.pop("bg_context", None)
    candidate.pop("last_bg_analysis", None)
    if codebook:
        candidate["bg_context"] = {
            "codebook_id": codebook["id"], "codebook_name": codebook["name"],
            "source_ids": [item["id"] for item in sources], "folder": str(target),
            "locked_profile": copy.deepcopy(profile["draft"]), "codebook_path": str(codebook_path),
            "codebook_sha256": profile["sha256"], "rule_profile_version": profile.get("version"),
        }
        candidate["selected_codebook_path"] = str(codebook_path)
    candidate["source_binding"] = source_binding(staged, candidate["active_source_ids"])
    problem = context_state_error(candidate)
    if problem:
        raise HTTPException(409, ui_message(ACTIVE, "error.binding", detail=problem))

    paths = [state.path, documents.path, material_selections_path(), state.transcript_path, coverage_path(state)]
    originals = {path: path.read_bytes() if path.exists() else None for path in paths}
    archive = state.root / "archives" / (uuid.uuid4().hex + ".jsonl")
    staged_state = copy.copy(state)
    staged_state.data = candidate
    try:
        staged._defer_save = False
        staged._save()
        staged_state.save()
        if target.is_dir():
            save_material_selection(target, selected)
        if state.transcript_path.exists():
            archive.parent.mkdir(exist_ok=True)
            state.transcript_path.replace(archive)
        coverage_path(state).unlink(missing_ok=True)
    except Exception:
        state.data, documents.data = old_state, old_index
        for path, original in originals.items():
            restore_state_file(path, original)
        archive.unlink(missing_ok=True)
        raise
    state.data, documents.data = candidate, staged.data
    invalidate_pending(data)
    return {"sources": len(sources), "skipped": skipped[:10], "skipped_count": len(skipped), "target_kind": target_kind,
            "files": [{"name": item["name"], "chunks": len(item.get("chunks", [])), "bytes": item.get("bytes", 0),
                       "material_role": item.get("material_role", "other"),
                       "material_role_label": material_role_label(item.get("material_role", "other")),
                       "index_cache_status": item.get("index_cache_status", "unknown")} for item in sources],
            "classification": bool(codebook_path), "status": status_data(data)}


@app.get("/api/target-tree")
def get_target_tree(target: str):
    folder = Path(target.strip().strip('"')).expanduser().resolve()
    if not folder.is_dir():
        raise HTTPException(400, ui_message(ACTIVE, 'tree.path_required'))
    tree, truncated = target_tree(folder)
    saved_paths, missing, changed = load_material_selection(folder)
    return {"tree": tree, "truncated": truncated,
            "saved_selection": sorted(saved_paths), "missing_saved_files": missing,
            "changed_saved_files": changed,
            "supported_extensions": sorted(SUPPORTED_DOCUMENT_EXTENSIONS)}


@app.get("/api/codebook")
def codebook_status():
    return load_codebook_profile()


@app.post("/api/codebook/prepare")
def codebook_prepare(request: CodebookPrepareRequest):
    path = safe_file(request.path)
    if path.suffix.lower() not in {".pdf", ".docx"}:
        raise HTTPException(400, ui_message(ACTIVE, 'error.rules_format'))
    data = begin_model_work()
    model = request.model.strip() or data["model"]
    try:
        with LOCK:
            profile = prepare_codebook_profile(data, path, model)
            save_codebook_profile(profile)
            rules_changed(data)
            data["state"].data["selected_codebook_path"] = str(path)
            data["state"].save()
        return profile
    except Exception as exc:
        raise HTTPException(400, ui_message(ACTIVE, 'error.rules_prepare', detail=error_copy(exc, ACTIVE))) from exc
    finally:
        MODEL_WORK_IN_PROGRESS.clear()


class CodebookEditRequest(BaseModel):
    draft: dict
    confirmed: bool = False
    profile_version: str | None = None


def rules_changed(data):
    reset_context(data)
    state = data["state"]
    state.data.pop("bg_context", None)
    state.data["context_issue"] = "rules_changed" if state.data.get("selected_target") or state.data.get("active_source_ids") else ""
    state.save()


@app.post("/api/codebook/edit")
@context_mutation
def codebook_edit(request: CodebookEditRequest):
    if not request.confirmed: raise HTTPException(400, ui_message(ACTIVE, 'error.confirmation'))
    profile = load_codebook_profile()
    if not profile.get('source_path'): raise HTTPException(400, ui_message(ACTIVE, 'error.rules_first'))
    if request.profile_version is not None and request.profile_version != profile.get('version'):
        raise HTTPException(409, ui_message(ACTIVE, 'rules.version_changed'))
    try:
        draft = parse_codebook_draft(json.dumps(request.draft))
    except ValueError as exc:
        raise HTTPException(400, ui_message(ACTIVE, 'error.rules_invalid', detail=error_copy(exc, ACTIVE))) from exc
    previous = dict(profile)
    profile['draft'] = draft; profile['status'] = 'draft'
    profile['previous_draft'] = previous.get('draft', {})
    save_codebook_profile(profile)
    if ACTIVE:
        rules_changed(ACTIVE)
    return profile


@app.post("/api/codebook/lock")
@context_mutation
def codebook_lock():
    reject_context_change_while_processing()
    profile = load_codebook_profile()
    if profile.get("status") != "draft" or not (profile.get("draft") or {}).get("classes"):
        raise HTTPException(400, ui_message(ACTIVE, 'error.rules_first'))
    path = Path(str(profile.get("source_path", "")))
    if not path.is_file() or file_digest(path) != profile.get("sha256"):
        raise HTTPException(409, ui_message(ACTIVE, 'error.rules_changed'))
    profile["draft"] = parse_codebook_draft(json.dumps(profile["draft"]))
    profile["status"] = "locked"
    profile["locked_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    save_codebook_profile(profile)
    if ACTIVE:
        rules_changed(ACTIVE)
        ACTIVE["state"].data["selected_codebook_path"] = str(path)
        ACTIVE["state"].save()
    return profile


@app.delete("/api/codebook")
@context_mutation
def codebook_clear():
    reject_context_change_while_processing()
    try:
        codebook_profile_path().unlink()
    except FileNotFoundError:
        pass
    # A changed Codebook must not keep classifying with an old profile in the
    # currently open session.  Other sessions are likewise harmless until they
    # explicitly analyse a target again, at which time the global lock is read.
    if ACTIVE:
        rules_changed(ACTIVE)
    return {"status": "none"}


@app.get("/api/coverage")
def coverage_status():
    return coverage_for_ui(session())


@app.post("/api/coverage")
def create_coverage(request: CoverageRequest = CoverageRequest()):
    data = begin_model_work()
    try:
        with LOCK:
            return prepare_coverage(data, full=request.full)
    finally:
        MODEL_WORK_IN_PROGRESS.clear()


@app.get("/api/cache/audit")
def cache_audit_status():
    return cache_audit(session())


@app.post("/api/cache/file/rebuild")
@context_mutation
def rebuild_cached_file(request: CacheFileRequest):
    reject_context_change_while_processing()
    if not request.confirmed:
        raise HTTPException(400, ui_message(ACTIVE, 'error.confirmation'))
    data = session()
    ensure_current_sources(data)
    document = next((item for item in data["documents"].list() if item.get("id") == request.document_id
                     and item["id"] in data["state"].data.get("active_source_ids", [])), None)
    if not document:
        raise HTTPException(404, ui_message(ACTIVE, 'error.material_missing'))
    target = app_state_home() / "material_cache" / str(document.get("sha256") or "")
    if target.is_dir():
        shutil.rmtree(target)
    invalidate_current_coverage(data["state"], str(document["id"]))
    message = ui_message(data, 'cache.file_cleared', name=document['name'])
    return {"message": str(message), **message_payload(message), "audit": cache_audit(data)}


@app.post("/api/cache/dossier/rebuild")
def rebuild_bg_dossier(request: CacheConfirmRequest):
    if not request.confirmed:
        raise HTTPException(400, ui_message(ACTIVE, 'error.confirmation'))
    # Reserve the shared model slot before inspecting the session.  Until the
    # finally block runs, every context-changing route and every other model
    # task sees this rebuild as active.
    data = begin_model_work()
    try:
        ensure_current_sources(data)
        coverage = load_coverage(data["state"])
        if not coverage_matches_current_selection(data, coverage):
            raise HTTPException(409, ui_message(ACTIVE, 'error.coverage_missing'))
        with LOCK:
            # Do not unlink an existing dossier first.  The replacement is
            # written atomically only after the new model response succeeded,
            # so a failed rebuild cannot masquerade as a completed cache or
            # discard a previously valid audit record.
            dossier, usage, _created = prepare_bg_dossier(data, coverage, force=True)
        message = ui_message(data, 'cache.dossier_rebuilt')
        return {"message": str(message), **message_payload(message), "dossier": dossier,
                "usage": usage or summarize_usage([]), "audit": cache_audit(data)}
    finally:
        MODEL_WORK_IN_PROGRESS.clear()


@app.post("/api/cache/clear")
@context_mutation
def clear_summary_caches(request: CacheConfirmRequest):
    reject_context_change_while_processing()
    if not request.confirmed:
        raise HTTPException(400, ui_message(ACTIVE, 'error.confirmation'))
    for name in ("material_cache", "bg_dossier_cache"):
        target = app_state_home() / name
        if target.is_dir():
            shutil.rmtree(target)
    # Keep local source indexes/OCR derivatives intact; only model-generated
    # summaries and dossiers are cleared.  The current report is marked stale.
    invalidate_current_coverage(session()["state"])
    message = ui_message(ACTIVE, 'cache.cleared')
    return {"message": str(message), **message_payload(message), "audit": cache_audit(session())}


@app.delete("/api/bg")
@context_mutation
def clear_bg():
    reject_context_change_while_processing()
    data = session(); reset_context(data); data["state"].data.pop("bg_context", None)
    data["state"].data["context_issue"] = ""
    data["state"].save(); return status_data(data)


@app.post("/api/export/session")
def export_session():
    target = write_session_export(session())
    return {"path": str(target)}


@app.post("/api/export/bg-analysis")
def export_bg_analysis():
    target = write_bg_analysis_export(session()["state"])
    return {"path": str(target)}


@app.post("/api/chat")
def chat(request: ChatRequest):
    if not request.question.strip(): raise HTTPException(400, ui_message(ACTIVE, 'error.question'))
    data = begin_model_work()
    try:
        with LOCK:
            return call_model(data, request.question.strip(), require_classification=request.require_classification)
    finally:
        MODEL_WORK_IN_PROGRESS.clear()


class ChatCancelRequest(BaseModel):
    request_id: str


def chat_task_status(task):
    return {"request_id": task["id"], "done": task["done"].is_set(),
            "state": task["state"], "worker_alive": task["worker"].is_alive()}


@app.get("/api/chat/task/{request_id}")
def get_chat_task(request_id: str):
    with CHAT_TASK_GUARD:
        if CHAT_TASK.get("id") != request_id:
            raise HTTPException(404, ui_message(ACTIVE, 'error.unknown_task'))
        return chat_task_status(CHAT_TASK)


@app.post("/api/chat/cancel")
def cancel_chat(request: ChatCancelRequest):
    with CHAT_TASK_GUARD:
        if CHAT_TASK.get("id") != request.request_id:
            raise HTTPException(404, ui_message(ACTIVE, 'error.unknown_task'))
        task = dict(CHAT_TASK)
    if not task["done"].is_set() and task["control"].cancel():
        with CHAT_TASK_GUARD:
            if CHAT_TASK.get("id") == request.request_id and not task["done"].is_set():
                CHAT_TASK["state"] = "cancelling"
    return get_chat_task(request.request_id)


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest, http_request: Request):
    """A bounded preview queue; only the joined worker can release its slot."""
    question = request.question.strip()
    if not question:
        raise HTTPException(400, ui_message(ACTIVE, 'error.question'))
    data = begin_model_work()
    try:
        with LOCK:
            ensure_current_sources(data)
    except Exception:
        MODEL_WORK_IN_PROGRESS.clear()
        raise
    control = data["request_control"]
    events: Queue[dict[str, Any]] = Queue(maxsize=64)
    task = {"id": request.request_id or uuid.uuid4().hex, "control": control, "done": threading.Event(),
            "state": "running", "result": None, "error": None}

    def emit(event):
        while True:
            control.check()
            try:
                events.put(event, timeout=.05)
                return
            except Full:
                if control.committed:
                    return
                continue

    def publish(phase: str, text: str, percent: int | None = None) -> None:
        emit({"type": "progress", "phase": phase, "text": str(text), "percent": percent,
              **message_payload(text)})

    data["answer_events"] = emit

    def worker():
        try:
            with LOCK:
                task["result"] = call_model(data, question, progress=publish,
                                            require_classification=request.require_classification)
        except Exception as exc:
            code = ("cancelled" if isinstance(exc, RequestCancelled) else
                    "timeout" if isinstance(exc, RequestTimedOut) else
                    "limit" if isinstance(exc, RequestStopped) else "failed")
            detail = error_copy(exc, data)
            task["error"] = {"type": "error", "code": code, "message": safe_error(str(detail)),
                             **message_payload(detail)}

    thread = threading.Thread(target=worker, daemon=True)
    task["worker"] = thread
    with CHAT_TASK_GUARD:
        CHAT_TASK.clear()
        CHAT_TASK.update(task)
    try:
        thread.start()
    except Exception:
        MODEL_WORK_IN_PROGRESS.clear()
        raise

    def reap_worker():
        thread.join()
        with CHAT_TASK_GUARD:
            task["state"] = ("completed" if task["result"] is not None else
                             "cancelled" if task["error"]["code"] == "cancelled" else
                             "timed_out" if task["error"]["code"] == "timeout" else "failed")
            if CHAT_TASK.get("id") == task["id"]:
                CHAT_TASK.update(task)
            task["done"].set()
            MODEL_WORK_IN_PROGRESS.clear()

    threading.Thread(target=reap_worker, daemon=True).start()

    async def watch_disconnect():
        # Also cover a connection lost before the body iterator starts.
        while not task["done"].is_set():
            if await http_request.is_disconnected():
                control.cancel("disconnected")
                return
            await asyncio.sleep(.05)

    asyncio.create_task(watch_disconnect())

    async def event_stream():
        last_heartbeat = time.monotonic()
        try:
            yield "data: " + json.dumps({"type": "start", "request_id": task["id"]}) + "\n\n"
            while True:
                if await http_request.is_disconnected():
                    control.cancel("disconnected")
                    break
                try:
                    control.check()
                except RequestStopped:
                    pass  # Worker still owns the slot until its actual exit.
                try:
                    event = events.get_nowait()
                except Empty:
                    if task["done"].is_set():
                        terminal = ({"type": "result", "data": task["result"]}
                                    if task["result"] is not None else task["error"])
                        yield "data: " + json.dumps(terminal, ensure_ascii=False) + "\n\n"
                        yield 'data: {"type":"end"}\n\n'
                        break
                    if time.monotonic() - last_heartbeat >= 5:
                        yield ": keep-alive\n\n"
                        last_heartbeat = time.monotonic()
                    await asyncio.sleep(.02)
                    continue
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
        finally:
            if not task["done"].is_set():
                control.cancel("disconnected")

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/compare")
def compare(request: CompareRequest):
    question = request.question.strip()
    models = list(dict.fromkeys(model.strip() for model in request.models if model and model.strip()))
    if not question:
        raise HTTPException(400, ui_message(ACTIVE, 'error.question'))
    if not 2 <= len(models) <= 4:
        raise HTTPException(400, ui_message(ACTIVE, 'compare.models_required'))
    data = begin_model_work()
    try:
        with LOCK:
            return call_comparison(data, question, models)
    finally:
        MODEL_WORK_IN_PROGRESS.clear()


class ApplyRequest(BaseModel):
    confirmed: bool = False
    plan_id: str = ""


def invalidate_pending(data):
    data["pending"] = []
    data.pop("pending_plan", None)
    if ACTIVE.get("state") is data.get("state") and ACTIVE is not data:
        ACTIVE["pending"] = []
        ACTIVE.pop("pending_plan", None)


def plan_digest(changes):
    return sha256(json.dumps(changes, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8"))


def plan_context(data):
    state = data["state"]
    rules = load_codebook_profile()
    rule_path = Path(str(rules.get("source_path", "")))
    return plan_digest({
        "workspace": str(state.workspace), "session": str(state.root),
        "session_id": state.data["session_id"], "model": data["model"],
        "revision": state.data.get("context_revision"),
        "context_schema_version": state.data.get("context_schema_version", 1),
        "target": state.data.get("selected_target"),
        "bg": state.data.get("bg_context"),
        "sources": state.data.get("active_source_ids"),
        "documents": [{key: item.get(key) for key in ("id", "path", "sha256")}
                      for item in data["documents"].list()],
        "rules": rules,
        "rule_source_sha256": file_digest(rule_path) if rule_path.is_file() else None,
    })


def publish_pending(data, changes):
    """Bind the exact displayed ordered plan to this session and context."""
    with LOCK:
        invalidate_pending(data)
        if not changes:
            return None
        plan = {"id": uuid.uuid4().hex, "context": plan_context(data),
                "changes": plan_digest(changes)}
        data["pending"], data["pending_plan"] = changes, plan
        if ACTIVE.get("state") is data["state"]:
            ACTIVE["pending"], ACTIVE["pending_plan"] = changes, plan
        return plan["id"]


@app.post("/api/apply")
@context_mutation
def apply(request: ApplyRequest):
    if not request.confirmed: raise HTTPException(400, ui_message(ACTIVE, 'error.confirmation'))
    data = session(); pending = data.get("pending", [])
    plan = data.get("pending_plan") or {}
    if not request.plan_id or request.plan_id != plan.get("id") or not pending:
        raise HTTPException(409, ui_message(ACTIVE, 'error.plan_expired'))
    if plan.get("context") != plan_context(data) or plan.get("changes") != plan_digest(pending):
        raise HTTPException(409, ui_message(ACTIVE, 'error.plan_changed'))
    ensure_current_sources(data)
    state = data["state"]
    backup_dir = state.root / "backups" / uuid.uuid4().hex
    staged, applied, originals = [], [], {}
    try:
        for item in pending:
            path = state.resolve_relative(item["path"])
            if path.suffix.lower() not in {".py", ".txt", ".md", ".json", ".csv", ".html", ".css", ".js"}:
                raise ValueError("Binary documents and Excel must use the dedicated copy-based editor")
            old = path.read_bytes() if path.exists() else None
            if (sha256(old) if old is not None else None) != item["before"]:
                raise HTTPException(409, ui_message(ACTIVE, 'error.source_changed', path=item['path']))
            originals[path] = old
            if old is not None:
                backup = backup_dir / item["path"]; backup.parent.mkdir(parents=True, exist_ok=True); backup.write_bytes(old)
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
            staged.append((path, temp))
            with temp.open('w', encoding='utf-8', newline='') as handle:
                handle.write(item['content']); handle.flush(); os.fsync(handle.fileno())
        for path, temp in staged:
            os.replace(temp, path); applied.append(path)
        invalidate_pending(data)
        for path, _ in staged: state.refresh_file(state.relative(path))
    except Exception:
        for path in reversed(applied):
            old = originals[path]
            if old is None: path.unlink(missing_ok=True)
            else:
                rollback = path.with_name('.' + path.name + '.rollback')
                rollback.write_bytes(old); os.replace(rollback, path)
        raise
    finally:
        for _, temp in staged: temp.unlink(missing_ok=True)
    return {"applied": len(pending), "backup": str(backup_dir)}


@app.delete("/api/pending")
@context_mutation
def cancel_pending():
    invalidate_pending(session())
    return {"cancelled": True}


HTML = r'''<!doctype html><html lang="zh"><head><meta charset="utf-8"><title>Bosch Local Workbench</title>
<style>
*{box-sizing:border-box}:root{--left-panel-width:264px;--ui-bg:#0b1020;--ui-surface:#111a2c;--ui-surface-2:#172338;--ui-surface-3:#1d2b43;--ui-line:#283750;--ui-line-soft:#1c2a40;--ui-text:#edf3fb;--ui-muted:#92a2b8;--ui-faint:#687992;--ui-blue:#4f9bf5;--ui-cyan:#54c7dc;--ui-green:#43c59e;--ui-shadow:0 18px 60px rgba(0,0,0,.38)}body{margin:0;background:radial-gradient(900px 500px at 55% -220px,#1d407050,transparent 72%),var(--ui-bg);color:var(--ui-text);font:14px/1.45 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",Arial,sans-serif}button,input,select{font:inherit}button{background:var(--ui-blue);color:white;border:0;border-radius:9px;padding:8px 10px;cursor:pointer}button.ghost{background:var(--ui-surface-2);color:#cbd9e9;border:1px solid var(--ui-line)}button.ghost:hover{background:var(--ui-surface-3);border-color:#456183}.topbar{height:58px;display:flex;align-items:center;gap:14px;padding:0 18px;border-bottom:1px solid var(--ui-line-soft);background:rgba(12,18,32,.82);backdrop-filter:blur(18px);position:relative;z-index:6}.app-brand{display:flex;align-items:center;gap:10px;font-weight:700;letter-spacing:-.02em;font-size:15px}.brand-mark{width:25px;height:25px;border-radius:8px;background:linear-gradient(135deg,#65b9ff,#3275d1);box-shadow:0 0 22px #4f9bf568;position:relative}.brand-mark:after{content:"";position:absolute;inset:6px;border:2px solid white;border-left-color:transparent;border-radius:5px}.topbar-workspace{border:0;border-left:1px solid var(--ui-line);border-radius:0;background:transparent;color:var(--ui-muted);padding:4px 0 4px 14px;font-size:12px;max-width:370px;text-overflow:ellipsis;overflow:hidden;white-space:nowrap}.topbar-workspace:hover{color:white}.top-spacer{flex:1}.topbar-status{display:flex;align-items:center;gap:7px;color:var(--ui-muted);font-size:12px}.status-dot{width:7px;height:7px;border-radius:50%;background:var(--ui-green);box-shadow:0 0 0 3px #43c59e22}.shell{height:calc(100vh - 58px);display:grid;grid-template-columns:var(--left-panel-width) 8px minmax(420px,1fr) 300px}.side{background:#0d1525;border-right:1px solid var(--ui-line-soft);padding:0;overflow:hidden}.splitter{cursor:col-resize;background:#162238;touch-action:none;transition:background .15s}.splitter:hover,.splitter.dragging{background:#345a80}.right{border-left:1px solid var(--ui-line-soft);border-right:0;background:#0e1728;padding:15px 13px;overflow:auto}.main{display:flex;flex-direction:column;min-width:0;position:relative;background:linear-gradient(120deg,rgba(14,24,42,.55),rgba(11,16,32,.2))}.chat-header{height:60px;border-bottom:1px solid var(--ui-line-soft);padding:0 28px;display:flex;align-items:center;gap:12px}.chat-title{font-weight:650;letter-spacing:-.01em}.chat-subtitle{font-size:12px;color:var(--ui-muted)}.header-spacer{flex:1}.header-icon{display:inline-grid;place-items:center;width:31px;height:31px;border:1px solid var(--ui-line);background:var(--ui-surface);color:var(--ui-muted);border-radius:8px;cursor:pointer}.header-icon:hover{color:white;border-color:#466185}.brand{font-weight:700;font-size:16px;margin-bottom:16px}.muted{color:var(--ui-muted);font-size:12px}.field{margin:10px 0}.field label{display:block;font-size:12px;color:#a9b6c8;margin-bottom:5px}input,select{width:100%;background:#0f172a;border:1px solid #3b4960;border-radius:8px;padding:8px;color:#f8fafc}.row{display:flex;gap:7px}.row>*{min-width:0}.row input{flex:1}.chat{flex:1;overflow:auto;padding:34px max(8%,42px)}.message{max-width:920px;margin:0 auto 18px;padding:13px 15px;border-radius:12px;white-space:pre-wrap;line-height:1.55}.user{background:#1d3a60;margin-left:auto;max-width:78%}.assistant{background:#17243a;border:1px solid #273b57}.reason{margin:8px auto 18px;max-width:920px;background:#121d30;border:1px solid #2b3e5a;border-radius:10px;padding:9px}.reason summary{cursor:pointer;color:#b9c9e2}.reason pre{white-space:pre-wrap;font-size:12px;color:#aab7c8}.composer-wrap{padding:0 28px 22px;background:linear-gradient(transparent,var(--ui-bg) 26%)}.composer{max-width:900px;width:100%;margin:auto;background:#141f33;border:1px solid #33435e;border-radius:14px;box-shadow:0 14px 40px #00000038;overflow:hidden;display:flex;flex-wrap:wrap;gap:0;padding:0}.composer input#question{border:0;background:transparent;padding:15px 14px;min-width:0;flex:1}.composer>button{margin:9px 10px 9px 0;height:38px}.composer-tools{width:100%;min-height:40px;border-top:1px solid #293851;display:flex;align-items:center;padding:5px 8px 5px 12px;gap:7px}.composer-tools .spacer{flex:1}.composer-tools select{width:auto;max-width:330px;color:#dbe8f8;background:#1c2b43;border:1px solid #354863;border-radius:999px;padding:5px 28px 5px 10px;font-size:12px}.composer-tools #custommodelrow{margin:0;align-items:center}.composer-tools #custommodelrow input{width:250px;padding:5px 8px}.composer-tools #custommodelrow button{padding:5px 8px}.model-test{font-size:12px;color:#a9bdd5;background:transparent;border:1px solid transparent;padding:5px 7px}.model-test:hover{background:#1e2e47;color:#fff}.card{border:1px solid #2b3e59;border-radius:10px;padding:10px;margin:10px 0;background:#121d30}.list{font-size:12px;line-height:1.5;word-break:break-word}.diff{white-space:pre-wrap;background:#0b1220;border-radius:6px;padding:8px;max-height:230px;overflow:auto;color:#d7e1ed}.ok{color:#86efac}.error{color:#fca5a5}.chip{display:inline-block;padding:3px 6px;border-radius:5px;background:#22314a;color:#bcd5ff;margin:2px;font-size:11px}.check{display:block;margin:5px 0;color:#dbeafe;font-size:12px}.check input{width:auto;margin-right:5px}.comparison{max-width:1180px;margin:0 auto 20px}.comparison-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(255px,1fr));gap:10px}.comparison .card{margin:0}.comparison .answer{white-space:pre-wrap;line-height:1.5;max-height:440px;overflow:auto}.target-tree{max-height:360px;overflow:auto;border:1px solid #334155;border-radius:8px;padding:7px;background:#0f172a}.target-tree details{margin:3px 0}.target-tree summary{cursor:pointer;list-style:none}.target-tree summary::-webkit-details-marker{display:none}.target-tree summary:before{content:'▸';display:inline-block;width:13px;color:#94a3b8}.target-tree details[open]>summary:before{content:'▾'}.target-tree label{cursor:pointer;margin-left:4px}.target-tree input{width:auto;vertical-align:middle}.tree-children{margin-left:17px;border-left:1px solid #29374d;padding-left:7px}.tree-file{margin:3px 0}.unsupported{color:#64748b}.classification-card{max-width:920px;margin:-8px auto 18px;border:1px solid #388ee8;border-radius:12px;padding:13px 15px;background:#10263a;line-height:1.55}.classification-card h3{margin:0 0 8px;color:#bae6fd;font-size:14px}.classification-card ul{margin:5px 0 0;padding-left:20px}.classification-card .result{font-size:16px;color:#f8fafc}.codebook-workspace{padding-top:28px}.codebook-workspace .workspace-inner{max-width:980px;margin:auto}.codebook-workspace h1{font-size:22px;margin:0 0 7px}.codebook-workspace h2{font-size:16px;margin:22px 0 8px}.codebook-class{border-left:3px solid #38bdf8}.codebook-class h3{margin:0 0 7px}.codebook-class ul{margin:7px 0;padding-left:20px;line-height:1.55}.workspace-actions{display:flex;gap:8px;position:sticky;bottom:0;padding:12px 0;background:#111827}.language-picker{position:relative;top:auto;right:auto;z-index:50;display:flex;align-items:center;gap:5px;padding:5px 7px;background:#172033;border:1px solid var(--ui-line);border-radius:8px;color:#cbd5e1;font-size:12px}.language-picker select{width:auto;background:transparent;border:0;color:#f8fafc;padding:3px}.context-title{font-size:12px;letter-spacing:.08em;color:var(--ui-faint);margin:2px 4px 11px;text-transform:uppercase}.context-card{width:100%;display:block;text-align:left;padding:13px;margin:0 0 10px;border:1px solid var(--ui-line);border-radius:11px;background:linear-gradient(150deg,#142138,#101a2b);color:#e5e7eb;transition:.18s}.context-card:hover{border-color:#42658f;background:#182841;transform:translateY(-1px)}.context-card strong{display:block;font-size:13px;margin-bottom:5px}.context-card span{display:block;color:var(--ui-muted);font-size:12px;line-height:1.45;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.context-card em{font-style:normal;color:#67e8f9;font-size:11px;float:right}.context-store{display:none}.context-backdrop{position:fixed;inset:58px 0 0;background:#05091475;z-index:45;opacity:0;pointer-events:none;transition:opacity .18s;backdrop-filter:blur(2px)}.context-backdrop.open{opacity:1;pointer-events:auto}.context-drawer{position:absolute;right:300px;top:0;bottom:0;width:min(680px,calc(100vw - 340px));display:flex;flex-direction:column;background:#111c30;border:1px solid #3a4d68;border-right:3px solid #38bdf8;border-radius:12px 0 0 12px;box-shadow:-14px 18px 48px rgba(0,0,0,.48);transform:translateX(34px);opacity:0;transition:transform .22s ease,opacity .18s}.context-backdrop.open .context-drawer{transform:translateX(0);opacity:1}.context-drawer-head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:16px 18px;border-bottom:1px solid var(--ui-line)}.context-drawer-head h2{font-size:16px;margin:0}.context-drawer-body{overflow:auto;padding:16px 18px}.context-drawer-body .target-tree{max-height:none}.context-drawer-body .field:first-child{margin-top:0}.welcome{max-width:750px;margin:20px auto}.welcome .eyebrow{color:var(--ui-cyan);font-size:12px;font-weight:700;letter-spacing:.09em;text-transform:uppercase}.welcome h1{font-size:31px;letter-spacing:-.04em;line-height:1.18;margin:10px 0}.welcome p{max-width:580px;color:var(--ui-muted);font-size:15px}.left-content{display:none!important}.side.left{display:flex!important;flex-direction:column!important;padding:0!important}.session-panel{border:0!important;margin:0!important;padding:16px 8px 8px!important;min-height:0!important;max-height:none!important;flex:1}.session-new{width:100%;margin:0 0 12px!important;text-align:left!important;padding:9px 10px!important;background:var(--ui-surface-2)!important;border:1px solid var(--ui-line)!important}.session-list{padding:0;overflow:auto}.session-row{border-radius:8px!important;margin:2px 0!important;padding:9px 7px!important;color:#b9c5d6!important}.session-row:hover,.session-row.active{background:#1a2c46!important;color:#fff!important}.session-more{font-size:15px!important}.session-menu{background:#19263a!important;border-color:#384b67!important;border-radius:10px!important;box-shadow:var(--ui-shadow)!important}.session-menu button{color:#dbe6f5!important}.session-menu button:hover{background:#293a56!important}@media(max-width:900px){.shell{grid-template-columns:minmax(220px,var(--left-panel-width)) 8px minmax(320px,1fr)}.right{display:none}.context-drawer{right:0;width:min(94vw,680px)}}
.message,.reason,.classification-card,.codebook-class,.context-drawer-body{overflow-wrap:anywhere;min-width:0}.workspace-actions{flex-wrap:wrap}.message pre,.reason pre{max-width:100%;overflow:auto}textarea{font:inherit;background:#0f172a;color:#f8fafc;border:1px solid #3b4960;border-radius:8px;padding:10px}@media(max-width:650px){.shell{grid-template-columns:minmax(0,1fr)}.side,.splitter{display:none!important}.topbar{padding:0 8px;gap:6px}.app-brand{font-size:11px;max-width:105px}.topbar-status{display:none}.topbar-workspace{max-width:140px}.chat{padding:16px 10px}.composer-wrap{padding:0 10px 10px}.chat-header{padding:0 12px}.composer-tools{flex-wrap:wrap}.composer-tools select{max-width:100%}.context-drawer{width:96vw;right:0}.language-picker{padding:3px}.message{padding:10px}.context-backdrop{inset:58px 0 0}}
</style></head><body><header class="topbar"><div class="app-brand"><span class="brand-mark"></span>Bosch Baugruppen Assistant</div><button class="topbar-workspace" id="workspaceshortcut" onclick="openContextDrawer('workspace')">选择工作区文件夹</button><div class="top-spacer"></div><div class="topbar-status"><span class="status-dot"></span><span id="topbarstatus">本地运行</span></div><div class="language-picker"><span>GUI:</span><select id="language" onchange="changeLanguage()"><option value="zh">ZH</option><option value="en">EN</option><option value="de">DE</option></select></div></header><div class="shell"><aside class="side"><div class="brand">Bosch Local Workbench</div><div class="muted">仅本机 127.0.0.1 · 缓存固定保存在程序目录 AI_Bot_State</div>
<div class="field"><label>工作区文件夹</label><div class="row"><input id="workspace" placeholder="C:\\...\\项目文件夹"><button class="ghost" onclick="pickWorkspace()">选择</button></div><div id="setupmsg" class="muted"></div></div><hr><div class="field"><label>模型</label>
<select id="model" onchange="modelChanged()">
<option value="claude-haiku-5-5">Claude Haiku 5.5（推荐：日常、便宜）</option>
<option value="claude-sonnet-5-5">Claude Sonnet 5.5（更强分析）</option>
<option value="claude-opus-5">Claude Opus 5（最强 Claude）</option>
<option value="gemini-3.5-flash-lite">Gemini 3.5 Flash-Lite（最快、最省）</option>
<option value="gemini-2.5-pro">Gemini 2.5 Pro（复杂文档）</option>
<option value="gemini-2.5-flash">Gemini 2.5 Flash（均衡）</option>
<option value="deepseek-r1-0528-maas">DeepSeek R1 (0528)</option>
<option value="llama-3.3-70b-instruct-maas">Llama 3.3 70B</option>
<option value="glm-5-maas">GLM-5</option>
<option value="__custom__">其他：手动输入 Model ID…</option>
</select>
<div class="row" id="custommodelrow" style="display:none;margin-top:7px"><input id="custommodel" placeholder="粘贴准确的 Bosch Farm Model ID" onkeydown="if(event.key==='Enter')confirmCustomModel()"><button class="ghost" onclick="confirmCustomModel()">确定</button></div></div><div id="modelstatus" class="muted"></div><div class="row"><button class="ghost" onclick="testModel()">测试模型</button></div><div id="modelmsg" class="muted"></div>
<div class="field"><label>聊天会话</label><div class="row"><select id="session"></select><button class="ghost" onclick="openSession()">切换</button><button class="ghost" onclick="newSession()">新建</button><button class="ghost" onclick="renameSession()">改名</button><button class="ghost" onclick="deleteSession()">删除</button></div><div id="sessionmsg" class="muted"></div></div>
<hr><b>Codebook</b><div id="codebookstatus" class="muted">尚未锁定 Codebook。</div><div class="field"><label>Codebook 文件（首次准备或更换时选择）</label><div class="row"><input id="codebook" placeholder="…Codebook.pdf / .docx"><button class="ghost" onclick="pick('file','codebook')">选择</button></div></div><div class="row"><button class="ghost" onclick="prepareCodebook()">准备 Codebook</button><button class="ghost" onclick="viewCodebook()">查看</button><button class="ghost" onclick="changeCodebook()">更换</button></div><hr><b>材料分析</b><div class="muted">文件直接分析；文件夹先显示结构，再明确勾选要用的材料。已锁定 Codebook 会自动用于分类。</div><div class="field"><label>分析目标：文件或文件夹</label><div class="row"><input id="targetpath" placeholder="PDF / Excel / PNG，或 Baugruppe 文件夹" oninput="clearTargetTree()"><button class="ghost" onclick="pick('file','targetpath')">文件</button><button class="ghost" onclick="pickFolderForTree()">文件夹</button></div></div><div class="row"><button class="ghost" onclick="loadTargetTree()">显示文件夹结构</button><button class="ghost" onclick="analyzeTarget()">用选中材料开始分析</button></div><div id="treestatus" class="muted"></div><div id="targettree" class="target-tree muted">选择文件夹后显示可展开的文件树。</div><button class="ghost" onclick="clearBg()">退出分类模式</button><div id="bgstatus" class="muted"></div><div id="scanreport" class="list"></div><div id="coveragestatus" class="muted">首次分类提问会自动读取并理解所选材料；无需预先操作。</div><div id="docs" class="list"></div>
<hr><b>多模型对比</b><div class="muted">同一条问题、同一份 BG 证据；逐个选择 2–4 个模型后顺序请求。结果不会写进普通聊天会话。</div><div id="comparemodels"></div><div class="row"><button class="ghost" id="addcompare" onclick="addCompareModel()">＋ 添加对比模型</button><button class="ghost" onclick="compareModels()">开始对比</button></div><div id="comparestatus" class="muted"></div></aside><div class="splitter" id="leftsplitter" role="separator" aria-orientation="vertical" aria-label="调整左侧栏宽度"></div>
<main class="main"><div class="chat-header"><div><div class="chat-title">Baugruppen 分析</div><div class="chat-subtitle">基于当前分类规则与已选材料</div></div><div class="header-spacer"></div><button class="header-icon" title="多模型对比" onclick="openCompareDrawer()">⇄</button><button class="header-icon" title="导出会话" onclick="exportSession()">⇩</button></div><div class="chat" id="chat"><section class="welcome"><div class="eyebrow">Baugruppen Intelligence</div><h1>你想进行什么分析？</h1><p>选择单一文件或一个 BG 文件夹。程序会先在本地读取、提取文字与结构，再将必要信息交给模型。</p><div class="row" style="margin-top:22px"><button onclick="openContextDrawer('materials')">▣&nbsp; 选择 BG 文件夹</button><button class="ghost" onclick="openContextDrawer('rules')">▤&nbsp; 管理分类规则</button></div></section></div><div class="composer-wrap"><div class="composer" id="composer"><input id="question" placeholder="问代码，或根据分类规则判断 Baugruppe …" onkeydown="if(event.key==='Enter')chat()"><button onclick="chat()">发送</button><button id="cancelchat" class="ghost" onclick="stopChat()" disabled>停止</button></div></div></main>
<aside class="side right" id="contextpanel"><div class="context-title">当前上下文</div><button class="context-card" onclick="openContextDrawer('rules')"><strong>分类规则 <em>管理 ›</em></strong><span id="context-rule-summary">尚未选择分类规则文件</span></button><button class="context-card" onclick="openContextDrawer('materials')"><strong>本次材料 <em>管理 ›</em></strong><span id="context-material-summary">尚未选择文件或 BG 文件夹</span></button><button class="context-card" onclick="openContextDrawer('scan')"><strong>扫描状态 <em>查看 ›</em></strong><span id="context-scan-summary">等待选择材料</span></button><button class="context-card" onclick="openContextDrawer('audit')"><strong>材料缓存与审计 <em>查看 ›</em></strong><span id="context-audit-summary">尚无本地读取或模型缓存</span></button><div class="context-store"><div id="status" class="card muted">尚未打开工作区</div><div id="sessionexport" class="card"><button class="ghost" onclick="exportSession()">导出完整会话</button></div><div id="usagedetail" class="card muted">完成一次请求后显示。</div><div id="analysisexport" class="card muted">仅在 Baugruppe 分析完成后可导出。</div><div id="sources" class="card list">回答后会显示实际传给模型的来源。</div><div id="changes" class="list">无</div></div></aside></div>
<script>
const $=id=>document.getElementById(id);let busy=false,lastQuestion='',compareSlots=[{value:'claude-haiku-5-5',custom:''}],savedTargetSelection=new Set(),treeRestoreNote='',lastScanReport=null,scannedSelection='',uiLanguage='zh',activeContextDrawer=null,lastStatusSnapshot=null,lastUsageSnapshot=null,lastCodebookProfile=null,lastCodebookWorkspaceProfile=null,lastDocumentsSnapshot=null,lastCoverageReport=null,lastCacheAudit=null,lastSessionRows=[],lastTargetTreePayload=null,lastComparison=null;
// Single source of translated copy. Compatibility adapters are temporary;
// new UI components must use t('area.item', parameters).
const CATALOG=__WORKBENCH_I18N_JSON__;
const I18N=CATALOG.messages;
const LEGACY_KEYS=CATALOG.legacy_keys;
const UI=Object.fromEntries(['zh','en','de'].map(language=>[
  language,Object.fromEntries(Object.entries(LEGACY_KEYS).map(([source,key])=>[source,I18N[language][key]]))
]));
// Bind only server-rendered interface copy once.  Model responses, filenames,
// user input and text added later must never enter this collection.
let initialStaticI18nBound=false;
const initialStaticText=[],initialStaticAttributes=[];
const STATIC_ELEMENT_BINDINGS=[
  ['#cancelchat','stream.stop'],
  ['.chat-title','chat.title'],['.chat-subtitle','chat.subtitle'],
  ['.welcome .eyebrow','welcome.eyebrow'],['.welcome h1','welcome.title'],
  ['.welcome p','welcome.description'],['.welcome .row button','welcome.choose_folder','▣\u00a0 '],
  ['.welcome .row button.ghost','welcome.manage_rules','▤\u00a0 '],
  ['#contextpanel > .context-title','context.title']
];
function t(key,variables={}){
  const template=(I18N[uiLanguage]||I18N.zh)[key];
  if(template===undefined){console.warn('Unknown UI translation key:',key);return key}
  return template.replace(/\{(\w+)\}/g,(_,name)=>Object.prototype.hasOwnProperty.call(variables,name)?String(variables[name]):'{'+name+'}');
}
function uiCopy(value){
  if(value==null)return '';
  if(Array.isArray(value))return value.map(uiCopy).join('');
  if(typeof value==='string')return value;
  if(value.message_key){let params=Object.fromEntries(Object.entries(value.params||{}).map(([key,item])=>[key,item&&typeof item==='object'&&(item.message_key||typeof item.text==='string')?uiCopy(item):item]));return t(value.message_key,params)}
  return String(value.text??value.message??'');
}
function registerUI(node,kind,data){node.dataset.uiComponent=kind;node.uiData=data;return node}
function setUIMessage(host,data,kind=''){if(!host)return;let node=document.createElement('span');node.className=kind;node.textContent=uiCopy(data);registerUI(node,'message',data);host.replaceChildren(node);return node}
function showStartupNotice(data){
  let host=$('startupnotice');
  if(!host){host=document.createElement('div');host.id='startupnotice';host.className='message error';host.setAttribute('role','alert');host.style.cssText='margin:8px 14px;max-height:30vh;overflow:auto;flex-shrink:0';$('chat').before(host)}
  setUIMessage(host,data,'error');
}

function uiMessageNode(data,kind='assistant'){return registerUI(message(uiCopy(data),kind),'message',data)}
function scopeCopy(record){
  if(record.scope_message)return uiCopy(record.scope_message);
  if(record.reading_scope_message)return uiCopy(record.reading_scope_message);
  let scope=record.scope??record.reading_scope??'';
  return scope==='完整文本预读'?t('material.scope_full'):scope==='Datasheet 前 15 页预读（其余页尚未覆盖）'?t('material.scope_datasheet',{pages:15}):scope==='已读取'?t('coverage.default_scope'):scope;
}
function stateCopy(value){let keys={'ok':'state.ok','not_needed':'state.not_needed','partial':'state.partial','unknown':'state.unknown','not_requested':'state.not_requested','not_applicable':'state.not_applicable','not applicable':'state.not_applicable','已完成':'state.complete','部分完成':'state.partial','不需要（原生文字页）':'state.native_text','不适用（无页码文档）':'state.not_applicable'};return keys[value]?t(keys[value]):String(value??'—')}
function roleCopy(value){let keys={'技术图纸':'material.role_drawing','BOM / 装配表':'material.role_bom','数据表 / 目录':'material.role_datasheet','DFC 结构图':'material.role_dfc','CAD 截图':'material.role_cad','派生重复资料':'material.role_derived','Inventor 源图（暂不支持）':'material.role_unsupported','其他资料':'material.role_other'};return keys[value]?t(keys[value]):String(value||t('material.role_other'))}
function rerenderUIComponents(){
  for(let node of document.querySelectorAll('[data-ui-component]')){
    let data=node.uiData;
    if(node.dataset.uiComponent==='classification')node.innerHTML=classificationCard(data).innerHTML;
    else if(node.dataset.uiComponent==='coverage')node.innerHTML=coverageSummaryCard(data).innerHTML;
    else if(node.dataset.uiComponent==='message')node.textContent=uiCopy(data);
    else if(node.dataset.uiComponent==='notices')node.textContent=data.map(uiCopy).join('\n');
    else if(node.dataset.uiComponent==='processing'){
      node.querySelector('[data-process-title]').textContent=t('model.processing');
      node.querySelector('[data-process-text]').textContent=uiCopy(data)||t('model.connecting');
    }
    else if(node.dataset.uiComponent==='preview')node.querySelector('.muted').textContent=t('stream.preview');
    else if(node.dataset.uiComponent==='reasoning')node.querySelector('summary').textContent=t('model.reasoning');
  }
}
function setI18nText(element,key,variables){if(element)element.textContent=t(key,variables)}
function tr(source){return LEGACY_KEYS[source]?t(LEGACY_KEYS[source]):source}
function rt(key,values={}){return t(key,values)}
function bindInitialStaticI18n(){
  if(initialStaticI18nBound)return;
  initialStaticI18nBound=true;
  let walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
  for(let node;node=walker.nextNode();){
    let source=node.nodeValue,key=LEGACY_KEYS[source.trim()];
    if(key)initialStaticText.push({node,key,lead:source.match(/^\s*/)[0],tail:source.match(/\s*$/)[0]});
  }
  for(let el of document.querySelectorAll('[placeholder],[title],[aria-label]'))for(let attr of ['placeholder','title','aria-label']){
    let source=el.getAttribute(attr),key=source&&LEGACY_KEYS[source];
    if(key)initialStaticAttributes.push({el,attr,key});
  }
}
function applyLanguage(){
  bindInitialStaticI18n();
  document.documentElement.lang=uiLanguage;document.documentElement.dataset.uiLanguage=uiLanguage;
  document.title='Bosch Local Workbench';
  for(let item of initialStaticText)item.node.nodeValue=item.lead+t(item.key)+item.tail;
  for(let item of initialStaticAttributes)item.el.setAttribute(item.attr,t(item.key));
  for(let [selector,key,prefix=''] of STATIC_ELEMENT_BINDINGS){let el=document.querySelector(selector);if(el)el.textContent=prefix+t(key)}
}
let languageSave=Promise.resolve();
async function changeLanguage(){uiLanguage=$('language').value;applyLanguage();rerenderLanguageSensitiveUI();let language=uiLanguage;languageSave=languageSave.catch(()=>{}).then(()=>api('/api/language',{method:'POST',body:JSON.stringify({language})}));try{await languageSave}catch(e){console.warn('Language save failed',e)}}

async function restoreLastWorkspace(){
  try{
    let s=await api('/api/settings');
    uiLanguage=['zh','en','de'].includes(s.language)?s.language:'zh';$('language').value=uiLanguage;applyLanguage();
    if(!s.workspace)return;
    $('workspace').value=s.workspace;
    setSelectedModel(s.model||'claude-haiku-5-5');
    $('session').innerHTML='<option>'+ esc(s.session||'default') +'</option>';
    setUIMessage($('setupmsg'),{message_key:'workspace.restoring'});
    await setup();
  }catch{
    setUIMessage($('setupmsg'),{message_key:'workspace.restore_failed'});
  }
}
function setLeftPanelWidth(width){let available=Math.max(240,window.innerWidth-420-300-8);let bounded=Math.max(235,Math.min(Number(width)||270,Math.min(600,available)));document.documentElement.style.setProperty('--left-panel-width',bounded+'px');let drawerStyle=$('scan-drawer-position')||Object.assign(document.createElement('style'),{id:'scan-drawer-position'});drawerStyle.textContent='#scanbackdrop .scan-drawer{left:'+bounded+'px!important}';if(!drawerStyle.parentNode)document.head.append(drawerStyle);localStorage.setItem('bosch-workbench-left-panel-width',String(bounded))}
function initLeftSplitter(){let splitter=$('leftsplitter');if(!splitter)return;let saved=Number(localStorage.getItem('bosch-workbench-left-panel-width'));if(saved)setLeftPanelWidth(saved);let dragging=false;function stop(){if(!dragging)return;dragging=false;splitter.classList.remove('dragging');document.body.style.userSelect=''}splitter.addEventListener('pointerdown',event=>{dragging=true;splitter.classList.add('dragging');splitter.setPointerCapture(event.pointerId);document.body.style.userSelect='none';event.preventDefault()});splitter.addEventListener('pointermove',event=>{if(dragging)setLeftPanelWidth(event.clientX)});splitter.addEventListener('pointerup',stop);splitter.addEventListener('pointercancel',stop);window.addEventListener('resize',()=>setLeftPanelWidth(Number(getComputedStyle(document.documentElement).getPropertyValue('--left-panel-width').replace('px',''))||270))}
function initDarkScrollbars(){let style=document.createElement('style');style.textContent='*{scrollbar-color:#52637a #182235;scrollbar-width:thin}::-webkit-scrollbar{width:10px;height:10px}::-webkit-scrollbar-track{background:#182235;border-radius:10px}::-webkit-scrollbar-thumb{background:#52637a;border:2px solid #182235;border-radius:10px}::-webkit-scrollbar-thumb:hover{background:#70839c}::-webkit-scrollbar-corner{background:#182235}select{width:100%;background:#0f172a!important;color:#e5e7eb!important;border:1px solid #3b4960!important;border-radius:6px;padding:8px;outline:none}select:hover{border-color:#526b88!important}select:focus{border-color:#3b82a8!important;box-shadow:0 0 0 2px rgba(59,130,168,.18)}select option{background:#172033;color:#e5e7eb}.language-picker select{width:auto;padding:3px 6px}.splitter{background:#263449!important}.splitter:hover,.splitter.dragging{background:#3b82a8!important}';document.head.append(style)}
window.addEventListener('DOMContentLoaded',()=>{bindInitialStaticI18n();applyLanguage();initDarkScrollbars();initLeftSplitter();initSessionSidebar();initComposerControls();initVisualAdjustments();initLanguageLayout();renderCompareSlots();loadCodebookStatus();ensureMaterialFlow();initContextPanel();refreshAppChrome();restoreLastWorkspace()});
function rerenderLanguageSensitiveUI(){
  refreshAppChrome();
  localizeComposerControls();
  localizeSessionChrome();
  for(let kind of ['materials','rules']){let node=$('contextshortcut-'+kind);if(node){node.title=t(kind==='materials'?'context.materials':'rules.title');node.setAttribute('aria-label',node.title)}}
  if(lastStatusSnapshot)renderStatus(lastStatusSnapshot);
  if(lastUsageSnapshot)renderUsageDetail(lastUsageSnapshot.usage,lastUsageSnapshot.model);
  if(lastCodebookProfile)renderCodebookStatus(lastCodebookProfile);
  if(lastDocumentsSnapshot)renderDocuments(lastDocumentsSnapshot);
  if(lastTargetTreePayload){captureTargetTreeSelection();renderTargetTreeForLanguage(lastTargetTreePayload);}
  localizeMaterialFlowControls();
  if(lastCoverageReport)renderCoverageReport(lastCoverageReport);
  if(lastScanReport){setScanReportAvailable(lastScanReport);if($('scanbackdrop')?.classList.contains('open'))renderScanDrawer(lastScanReport)}
  if(lastCacheAudit)renderCacheAudit(lastCacheAudit);
  if(lastSourcesSnapshot)renderEvidenceSources(lastSourcesSnapshot.sources,lastSourcesSnapshot.dfc);
  if(lastSessionRows.length)renderSessionRowsForLanguage(lastSessionRows,false);
  renderCompareSlots();
  if(lastComparison)renderComparisonForLanguage(lastComparison);
  if(ruleEditState)renderRuleEditor();
  else if(lastCodebookWorkspaceProfile&&$('chat')?.classList.contains('codebook-workspace'))showCodebookWorkspace(lastCodebookWorkspaceProfile);
  rerenderUIComponents();
  for(let node of document.querySelectorAll('button[data-plan-id]'))node.textContent=t('changes.apply');
  for(let node of document.querySelectorAll('button[onclick="exportBgAnalysis()"]'))node.textContent=t('export.assembly');
  if(activeContextDrawer){
    let kind=activeContextDrawer,values=[...$('contextdrawerbody').querySelectorAll('input[id],textarea[id]')].filter(node=>!node.classList.contains('tree-file')&&!node.classList.contains('tree-folder')).map(node=>[node.id,node.value,node.selectionStart,node.selectionEnd]);
    let notices=[...$('contextdrawerbody').querySelectorAll('[data-ui-component="message"]')].filter(node=>node.parentElement?.id.startsWith('context')).map(node=>[node.parentElement.id,node.uiData,node.className]);
    openContextDrawer(kind);
    for(let [id,value,start,end] of values){let node=$(id);if(node){node.value=value;if(node.setSelectionRange&&start!=null)node.setSelectionRange(start,end)}}
    for(let [id,data,kind] of notices)setUIMessage($(id),data,kind);
  }
  refreshContextPanel();
}
function responseTextSummary(raw){let text=String(raw||'').replace(/<[^>]*>/g,' ').replace(/\s+/g,' ').trim();return text.length>360?text.slice(0,357)+'…':text}
function apiErrorMessage(response,body){let detail=body?.message_key?uiCopy(body):'';if(!detail&&body&&typeof body==='object')detail=typeof body.detail==='string'?body.detail:(typeof body.message==='string'?body.message:'');let summary=detail||responseTextSummary(typeof body==='string'?body:'');return `HTTP ${response.status}${response.statusText?` ${response.statusText}`:''}${summary?`：${summary}`:`：${t('api.failed')}`}`}
async function readApiResponse(response){let raw=await response.text(),body=null;if(raw.trim()){try{body=JSON.parse(raw)}catch{body=raw}}if(!response.ok){let error=Error(apiErrorMessage(response,body));if(body?.message_key)error.uiMessage=body;throw error}if(body===null||typeof body==='string')throw Error(`HTTP ${response.status}：${t('api.invalid_json')}${responseTextSummary(raw)?' '+responseTextSummary(raw):''}`);return body}
async function api(url,opt={}){let response;try{response=await fetch(url,{headers:{'Content-Type':'application/json','X-Workbench-Language':uiLanguage},...opt})}catch(error){throw Error(t('model.connection_failed')+(error?.message?` ${error.message}`:''))}return readApiResponse(response)}
async function pick(kind,target){try{$(target).value=(await api('/api/pick/'+kind)).path||''}catch(e){alert(e.message)}}
async function pickWorkspace(){try{let path=(await api('/api/pick/folder')).path||'';if(!path)return;$('workspace').value=path;await setup()}catch(e){setUIMessage($('setupmsg'),e.uiMessage||{text:e.message},'error')}}
function refreshAppChrome(){let path=$('workspace')?.value.trim();let short=path?path.replace(/\\/g,'/').split('/').filter(Boolean).slice(-2).join(' / '):tr('选择工作区文件夹');if($('workspaceshortcut'))$('workspaceshortcut').textContent=short;if($('topbarstatus'))$('topbarstatus').textContent=path?tr('本地运行 · 工作区已打开'):tr('本地运行')}
function initVisualAdjustments(){if($('visual-adjustments'))return;let style=document.createElement('style');style.id='visual-adjustments';style.textContent='.composer-tools select{border-radius:8px!important}';document.head.append(style)}
function initLanguageLayout(){if($('language-layout'))return;let style=document.createElement('style');style.id='language-layout';style.textContent=`.context-shortcut{display:none}@media(max-width:1180px){.context-shortcut{display:inline-grid}}html[lang="zh"] body,html[lang="zh"] button,html[lang="zh"] input,html[lang="zh"] select{font-family:"Microsoft YaHei UI","Microsoft YaHei","Noto Sans SC","Segoe UI",sans-serif;letter-spacing:0}html[lang="en"] body,html[lang="en"] button,html[lang="en"] input,html[lang="en"] select,html[lang="de"] body,html[lang="de"] button,html[lang="de"] input,html[lang="de"] select{font-family:Inter,"Segoe UI",Arial,sans-serif}html[lang="zh"] .chat-subtitle,html[lang="zh"] .muted{line-height:1.55}html[lang="de"] .context-card strong,html[lang="de"] .context-drawer-head h2{letter-spacing:0}html[lang="de"] .context-card strong{padding-right:42px}.row{flex-wrap:wrap;align-items:center}.row input{min-width:min(100%,185px)}.row button{white-space:normal;line-height:1.25;min-height:34px}.context-card{min-height:78px}.context-card strong{position:relative;line-height:1.3;padding-right:50px;overflow-wrap:anywhere}.context-card em{position:absolute;right:0;top:0;float:none;white-space:nowrap}.context-card span{white-space:normal;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere}.context-drawer-head h2,.context-drawer-body label,.classification-card h3{overflow-wrap:anywhere}.context-drawer-body button,.workspace-actions button{max-width:100%;overflow-wrap:anywhere}.composer-tools{flex-wrap:wrap;row-gap:5px}.composer-tools .spacer{min-width:0}.composer-tools select{min-width:170px;max-width:min(330px,100%)}html[lang="de"] .composer-tools select{max-width:285px}@media(max-width:1180px){.shell{grid-template-columns:minmax(220px,var(--left-panel-width)) 8px minmax(360px,1fr) 260px}.right{padding:13px 10px}.context-drawer{right:260px;width:min(640px,calc(100vw - 300px))}.chat-header{padding:0 20px}.composer-wrap{padding-left:20px;padding-right:20px}}@media(max-width:760px){.topbar{gap:8px;padding:0 10px}.app-brand{font-size:13px}.topbar-workspace{max-width:145px}.shell{grid-template-columns:minmax(180px,42vw) 7px minmax(0,1fr)}.chat{padding:20px 14px}.chat-header{padding:0 14px}.composer-wrap{padding:0 14px 14px}.welcome h1{font-size:26px}.composer-tools .spacer{display:none}.composer-tools select{width:100%;max-width:none}.composer-tools #custommodelrow{width:100%;flex-wrap:wrap}.composer-tools #custommodelrow input{width:100%}.context-drawer{left:0;right:0;width:auto;max-width:100vw;border-radius:0;transform:none!important;transition:opacity .18s}.context-drawer-body{min-width:0;overflow-x:hidden}.context-drawer-body input{min-width:0;max-width:100%}#scanbackdrop.open .scan-drawer{left:0!important;right:0;width:auto;max-width:100vw;transform:none}.main{min-width:0}.composer{grid-template-columns:minmax(0,1fr) auto}.composer #cancelchat{grid-column:2}.composer input{min-width:0}.composer-tools{grid-column:1/-1}.context-card{min-height:0}}@media(max-width:900px){.shell{grid-template-columns:minmax(220px,var(--left-panel-width)) 8px minmax(0,1fr)}}@media(max-width:650px){.shell{grid-template-columns:minmax(0,1fr)}.chat-header{gap:6px}.chat-subtitle{display:none}.chat-title{font-size:13px}}`;document.head.append(style)}
function initComposerControls(){if($('composertools'))return;let composer=$('composer');if(!composer)return;let tools=document.createElement('div');tools.id='composertools';tools.className='composer-tools';let note=document.createElement('span');note.id='composermodelnote';note.className='muted';let spacer=document.createElement('span');spacer.className='spacer';let model=$('model'),custom=$('custommodelrow'),modelmsg=$('modelmsg'),test=document.querySelector('button[onclick="testModel()"]');if(model)tools.append(note,model);if(custom)tools.append(custom);if(test){test.id='modeltestbutton';test.className='model-test';tools.append(test)}if(modelmsg)tools.append(modelmsg);tools.append(spacer);let mode=document.createElement('select');mode.id='answermode';for(let value of ['classification','explanation']){let option=document.createElement('option');option.value=value;option.textContent=(value==='classification'?t('answer.classification'):t('answer.explanation'));mode.append(option)}tools.append(mode);composer.append(tools);mode.setAttribute('aria-label',t('answer.mode'));localizeComposerControls()}
function localizeComposerControls(){setI18nText($('composermodelnote'),'model.current');setI18nText($('modeltestbutton'),'model.test')}
async function contextPickWorkspace(){try{let path=(await api('/api/pick/folder')).path||'';if(!path)return;$('workspace').value=path;$('contextworkspacepath').value=path;if(await setup()){refreshAppChrome();closeContextDrawer()}}catch(e){setUIMessage($('contextworkspacemsg'),e.uiMessage||{text:e.message},'error')}}
async function contextOpenWorkspace(){let path=$('contextworkspacepath').value.trim();if(!path){$('contextworkspacemsg').innerHTML='<span class="error">'+t('workspace.path_required')+'</span>';return}$('workspace').value=path;if(await setup()){refreshAppChrome();closeContextDrawer()}}
let contextMoved=[];
function contextText(id,fallback){let el=$(id);let text=(el?.innerText||el?.textContent||'').replace(/\s+/g,' ').trim();return text||fallback}
function refreshContextPanel(){
  let rule=contextText('codebookstatus',t('rules.no_file'));
  let path=$('targetpath')?.value.trim();let selected=treeFileCount?.()||0;
  let material=path?(selected?t('material.selected_path',{count:selected,path}):path):t('materials.no_selection');
  let scan=contextText('coveragestatus',path?t('coverage.selection_changed'):t('materials.waiting'));
  let audit=contextText('usagedetail',t('audit.no_cache'));
  if($('context-rule-summary'))$('context-rule-summary').textContent=rule;
  if($('context-material-summary'))$('context-material-summary').textContent=material;
  if($('context-scan-summary'))$('context-scan-summary').textContent=scan;
  if($('context-audit-summary'))$('context-audit-summary').textContent=audit;
  renderContextGuard();
}
function renderContextGuard(){
  let issue=!!lastStatusSnapshot?.context_issue,host=$('contextguard');
  if(!host&&$('composer')){host=document.createElement('div');host.id='contextguard';host.className='muted';$('composer').before(host)}
  if(host)host.textContent=issue?t('context.reconfirm'):'';
  if($('question'))$('question').disabled=issue;
  let mode=$('answermode'),revision=lastStatusSnapshot?.context_revision||'';
  if(mode){mode.disabled=issue||!lastStatusSnapshot?.bg_context;if(mode.dataset.scope!==revision){mode.value='classification';mode.dataset.scope=revision}mode.setAttribute('aria-label',t('answer.mode'));for(let option of mode.options)option.textContent=(option.value==='classification'?t('answer.classification'):t('answer.explanation'))}
  document.querySelectorAll('button[onclick="chat()"],button[onclick="compareModels()"]').forEach(button=>button.disabled=issue);
  let draft=$('contextcodebookpath')?.value.trim(),prepared=lastCodebookProfile?.source_path||'';
  if($('contextrulemsg'))$('contextrulemsg').textContent=draft&&draft!==prepared?t('rules.pending_path',{path:prepared||'—'}):'';
}
function initContextPanel(){
  if($('contextbackdrop'))return;
  for(let [kind,label] of [['materials','▣'],['rules','▤']]){
    let button=document.createElement('button');button.className='header-icon context-shortcut';button.id='contextshortcut-'+kind;
    button.textContent=label;button.title=t(kind==='materials'?'context.materials':'rules.title');button.setAttribute('aria-label',button.title);
    button.setAttribute('onclick',"openContextDrawer('"+kind+"')");document.querySelector('.chat-header').append(button);
  }
  let backdrop=document.createElement('div');backdrop.id='contextbackdrop';backdrop.className='context-backdrop';
  backdrop.innerHTML='<section class="context-drawer" role="dialog" aria-modal="true" aria-label="上下文详情"><div class="context-drawer-head"><h2 id="contextdrawertitle">当前上下文</h2><button class="ghost" onclick="closeContextDrawer()">×</button></div><div id="contextdrawerbody" class="context-drawer-body"></div></section>';
  backdrop.addEventListener('click',e=>{if(e.target===backdrop)closeContextDrawer()});document.body.append(backdrop);
  document.addEventListener('keydown',e=>{if(e.key==='Escape')closeContextDrawer()});
  for(let id of ['codebookstatus','targetpath','targettree','treestatus','coveragestatus','usagedetail','status']){let el=$(id);if(el)new MutationObserver(refreshContextPanel).observe(el,{subtree:true,childList:true,characterData:true,attributes:true})}
  $('targetpath')?.addEventListener('input',refreshContextPanel);refreshContextPanel();
}
function moveContextElements(ids,host){
  ids.forEach(id=>{let el=$(id);if(!el)return;let marker=document.createComment('context:'+id);el.parentNode.insertBefore(marker,el);contextMoved.push({el,marker});host.append(el)});
}
function closeContextDrawer(){
  for(let item of contextMoved){if(item.marker.parentNode)item.marker.parentNode.replaceChild(item.el,item.marker)}
  contextMoved=[];activeContextDrawer=null;$('contextbackdrop')?.classList.remove('open');refreshContextPanel();
}
async function contextPickTarget(kind){try{let path=(await api('/api/pick/'+kind)).path||'';if(!path)return;materialDraftDirty=true;$('targetpath').value=path;$('contexttargetpath').value=path;if(kind==='folder')await loadTargetTree();else clearTargetTree();refreshContextPanel()}catch(e){setUIMessage($('contexttargetmsg'),e.uiMessage||{text:e.message},'error')}}
function contextSyncTarget(){let value=$('contexttargetpath').value.trim();if(value!==$('targetpath').value.trim()){materialDraftDirty=true;$('targetpath').value=value;clearTargetTree()}refreshContextPanel()}
function contextSyncRule(){let value=$('contextcodebookpath').value.trim();$('codebook').value=value;refreshContextPanel()}
async function contextPickRule(){try{let path=(await api('/api/pick/file')).path||'';if(!path)return;$('codebook').value=path;$('contextcodebookpath').value=path;refreshContextPanel()}catch(e){setUIMessage($('contextrulemsg'),e.uiMessage||{text:e.message},'error')}}
function renderDiagnostics(report){
  let host=$('diagnosticsresult');if(!host)return;
  let ready=report.overall==='ready';
  let rows=(report.checks||[]).map(check=>{
    let marker=check.ok===true?'<span class="ok">✓</span>':check.required===false?'<span class="muted">△</span>':'<span class="error">×</span>';
    let key='diagnostic.'+String(check.id||''),label=(I18N[uiLanguage]||I18N.zh)[key]?t(key):String(check.label||'—');
    // The endpoint deliberately remains language-neutral.  Convert its stable
    // status fields at presentation time; raw details stay visible only in ZH
    // or as a technical fallback for unknown future checks.
    let detail=check.detail_message?uiCopy(check.detail_message):uiLanguage==='zh'?String(check.detail||'—'):check.ok===true?t('diagnostic.available'):check.ok===null?t('diagnostic.not_tested'):t('diagnostic.not_available');if(check.path)detail+=' · '+check.path;
    return '<div class="card"><b>'+marker+' '+esc(label)+'</b><br><span class="muted">'+esc(detail)+'</span></div>';
  }).join('');
  host.innerHTML='<div class="'+(ready?'ok':'error')+'"><b>'+t(ready?'audit.diagnostics_ready':'audit.diagnostics_attention')+'</b></div>'+rows;
}
async function runDiagnostics(){
  let host=$('diagnosticsresult');if(!host)return;
  host.textContent=t('audit.diagnostics_loading');
  try{renderDiagnostics(await api('/api/diagnostics'))}
  catch(e){host.innerHTML='<span class="error">'+t('audit.diagnostics_failed')+esc(e.message)+'</span>'}
}
function openContextDrawer(kind){
  closeContextDrawer();activeContextDrawer=kind;let title=$('contextdrawertitle'),body=$('contextdrawerbody');
  if(kind==='workspace'){
    title.textContent=t('workspace.title');body.innerHTML='<div class="muted">'+t('workspace.description')+'</div><div class="field"><label>'+t('workspace.path_label')+'</label><div class="row"><input id="contextworkspacepath" placeholder="'+t('workspace.path_label')+'" value="'+escAttr($('workspace').value)+'"><button class="ghost" onclick="contextPickWorkspace()">'+t('workspace.choose')+'</button></div></div><div class="row"><button onclick="contextOpenWorkspace()">'+t('workspace.open')+'</button></div><div id="contextworkspacemsg" class="muted" style="margin-top:10px"></div>';
  }else if(kind==='rules'){
    title.textContent=t('rules.title');body.innerHTML='<div class="muted">'+t('rules.description')+'</div><div class="field"><label>'+t('rules.file_label')+'</label><div class="row"><input id="contextcodebookpath" placeholder="'+t('rules.choose')+'" value="'+escAttr($('codebook').value)+'" oninput="contextSyncRule()"><button class="ghost" onclick="contextPickRule()">'+t('workspace.choose')+'</button></div></div><div class="row"><button onclick="contextSyncRule();prepareCodebook()">'+t('rules.prepare')+'</button><button class="ghost" onclick="viewCodebook()">'+t('rules.view')+'</button><button class="ghost" onclick="changeCodebook()">'+t('rules.replace')+'</button></div><div id="contextrulemsg" class="muted" style="margin-top:10px"></div><div class="card">'+$('codebookstatus').innerHTML+'</div>';
  }else if(kind==='materials'){
    title.textContent=t('materials.title');body.innerHTML='<div class="muted">'+t('materials.description')+'</div><div class="field"><label>'+t('materials.target_label')+'</label><div class="row"><input id="contexttargetpath" placeholder="'+t('materials.target_placeholder')+'" value="'+escAttr($('targetpath').value)+'" oninput="contextSyncTarget()"><button class="ghost" onclick="contextPickTarget(\'file\')">'+t('materials.file')+'</button><button class="ghost" onclick="contextPickTarget(\'folder\')">'+t('materials.folder')+'</button></div></div><div class="row"><button class="ghost" onclick="contextSyncTarget();loadTargetTree()">'+t('materials.show_tree')+'</button><button class="ghost" onclick="contextSyncTarget();analyzeTarget()">'+t('materials.confirm_scope')+'</button></div><div id="contexttargetmsg" class="muted" style="margin:8px 0"></div><div id="contextmaterialmount"></div>';
    moveContextElements(['treestatus','targettree','materialactions','bgstatus','coveragestatus'], $('contextmaterialmount'));
  }else if(kind==='scan'){
    title.textContent=t('scan.title');body.innerHTML='<div class="muted">'+t('scan.description')+'</div><div class="card" id="contextcoveragestatus">'+$('coveragestatus').innerHTML+'</div><div class="row"><button class="ghost" onclick="openScanReport()">'+t('scan.report')+'</button><button class="ghost" onclick="prepareCoverage(true)">'+t('scan.extend')+'</button></div>';
  }else if(kind==='compare'){
    title.textContent=t('compare.title');body.innerHTML='<div class="muted">'+t('compare.description')+'</div><div id="contextcomparemount"></div>';
    let host=$('contextcomparemount');moveContextElements(['comparemodels'],host);let row=$('addcompare')?.parentNode;if(row){let marker=document.createComment('context:compare-actions');row.parentNode.insertBefore(marker,row);contextMoved.push({el:row,marker});host.append(row)}moveContextElements(['comparestatus'],host);
  }else{
    title.textContent=t('audit.title');body.innerHTML='<div class="muted">'+t('audit.description')+'</div><div class="card">'+$('usagedetail').innerHTML+'</div><div class="card">'+$('status').innerHTML+'</div><div class="row"><button class="ghost" onclick="openScanReport();setTimeout(loadCacheAudit,80)">'+t('audit.open')+'</button><button class="ghost" onclick="runDiagnostics()">'+t('audit.diagnostics')+'</button></div><div id="diagnosticsresult" class="list muted" style="margin-top:12px">'+t('audit.diagnostics_idle')+'</div>';
  }
  $('contextbackdrop').classList.add('open');applyLanguage();refreshContextPanel();if(kind==='audit')runDiagnostics();
}
function openCompareDrawer(){openContextDrawer('compare')}
function message(text,kind='assistant'){let e=document.createElement('div');e.className='message '+kind;e.textContent=text;$('chat').append(e);$('chat').scrollTop=1e9;return e}
function classificationCard(c){let card=document.createElement('section');card.className='classification-card';let alternative=c.alternative_label?'<br>'+t('classification.alternative')+'：'+esc(c.alternative_label):'';let evidence=(c.evidence_labels||[]).map(item=>'<li>'+esc(item)+'</li>').join('')||'<li>'+t('classification.none')+'</li>';let uncertainty=(c.uncertainties||[]).filter(Boolean).map(item=>'<li>'+esc(item)+'</li>').join('')||'<li>'+t('classification.not_reported')+'</li>';let rules=(c.codebook_rule_ids||[]).map(esc).join('、')||t('classification.not_returned');let rulePages=(c.codebook_rule_pages||[]).length?t('classification.rule_pages')+' '+c.codebook_rule_pages.map(esc).join('、'):t('classification.rule_refs')+' '+((c.codebook_rule_refs||[]).map(esc).join('、')||t('classification.not_returned'));let bgPages=(c.bg_evidence_pages||[]).map(esc).join('、')||t('classification.not_returned');card.innerHTML='<h3>'+t('classification.title')+'</h3><div class="result">'+t('classification.label')+'：<b>'+esc(c.label||'—')+'</b></div><div>'+t('classification.confidence')+'：'+esc(c.confidence||'—')+alternative+'</div><div><b>'+t('classification.rules')+'</b>：'+rules+'（'+rulePages+'）</div><div><b>'+t('classification.evidence_pages')+'</b>：'+bgPages+'</div><div><b>'+t('classification.evidence')+'</b><ul>'+evidence+'</ul></div><div><b>'+t('classification.uncertainty')+'</b><ul>'+uncertainty+'</ul></div>';return registerUI(card,'classification',c)}
function coverageSummaryCard(summary){if(!summary?.files?.length)return null;let card=document.createElement('section');card.className='classification-card';card.style.borderColor='#475569';let rows=summary.files.map(f=>{let read=Array.isArray(f.pages_read)?f.pages_read.length:0,unread=Array.isArray(f.pages_unread)?f.pages_unread.length:0;let pages=f.pages_total?(' · '+t('coverage.read')+' '+read+'/'+f.pages_total+' '+t('coverage.pages')+(unread?'；'+t('coverage.unread')+' '+unread+' '+t('coverage.pages'):'')):'';let cache=f.cache_status==='reused'?t('coverage.reused'):t('coverage.created');return '<li><b>'+esc(f.name)+'</b>：'+esc(scopeCopy(f)||t('coverage.default_scope'))+pages+' · '+cache+'</li>'}).join('');card.innerHTML='<h3>'+t('coverage.title')+'</h3><div class="muted">'+t('coverage.summary',{files:summary.files.length,reused:summary.reused_files||0,created:summary.created_files||0,calls:summary.model_calls||0})+'</div><ul>'+rows+'</ul>';return registerUI(card,'coverage',summary)}
function renderStatus(s){lastStatusSnapshot=s;$('status').innerHTML=`${t('status.model')}：<b>${s.model}</b><br>${t('status.session')}：${s.session_name||'default'}<br>${t('status.code')}：${s.code_files} ${uiLanguage==='en'?'files':'文件'}<br>${t('status.documents')}：${s.documents} ${uiLanguage==='en'?'items':'个'}<br>${t('status.requests')}：${s.requests}<br>${t('status.tokens')}：${s.input_tokens} / ${s.output_tokens}<br>${t('status.cost')}：${s.cost}<br>${s.bg_context?'<span class="ok">'+t('status.assembly_mode')+'：'+s.bg_context.codebook_name+'</span>':t('status.normal_mode')}`;refreshAppChrome();refreshContextPanel()}
function usageNumber(value){return value==null?t('usage.unknown'):esc(value)}
function usageCost(u){return u.cost_usd==null?t('usage.unknown')+(u.known_cost_usd!=null?' · '+t('usage.known_subtotal')+': $'+Number(u.known_cost_usd).toFixed(6):''):'$'+Number(u.cost_usd).toFixed(6)}
function renderUsageDetail(u,model){if(!u)return;lastUsageSnapshot={usage:u,model};return renderUsageDetailForLanguage(u,model)}
function renderEvidenceSources(sources,dfcEvidence){let normal=(sources||[]).map(s=>`<div class="card"><b>${esc(s.label||s.name||'未知来源')}</b><br>${s.visual?'<span class="chip">视觉证据已附带</span>':''}</div>`).join('');let dfc=(dfcEvidence||[]).map(d=>{let parts=(d.segments_used||[]).join('、')||'无';return `<div class="card"><b>DFC Struktur</b><br>${esc(d.name||'—')}<br><span class="chip">OCR：${esc(d.ocr_status||'—')}</span><span class="chip">本轮：第 ${esc(parts)} 段 / 共 ${esc(d.segments_total||0)} 段</span></div>`}).join('');$('sources').innerHTML=(dfc+normal)||'无可用来源'}
function toggleCustomModel(){let custom=$('model').value==='__custom__';$('custommodelrow').style.display=custom?'flex':'none';if(custom)$('custommodel').focus()}
function setSelectedModel(model){let known=[...$('model').options].some(option=>option.value===model);$('model').value=known?model:'__custom__';$('custommodel').value=known?'':model;toggleCustomModel();loadModelStatus()}
function selectedModel(){let selected=$('model').value;return selected==='__custom__' ? $('custommodel').value.trim() : selected}
async function modelChanged(){toggleCustomModel();loadModelStatus();if($('model').value!=='__custom__'&&$('workspace').value.trim())await switchModel()}
async function confirmCustomModel(){if(!selectedModel()){ $('modelmsg').innerHTML='<span class="error">'+t('model.id_required')+'</span>';return}if($('workspace').value.trim())await switchModel();else setUIMessage($('modelmsg'),{message_key:'model.custom_saved'})}
function codebookList(items){let values=Array.isArray(items)?items.filter(Boolean):[];return values.length?'<ul>'+values.map(item=>{if(item&&typeof item==='object'){let text=esc(item.text||item.title||JSON.stringify(item));let id=item.id?' <span class="muted">['+esc(item.id)+']</span>':'';let pages=Array.isArray(item.pages)&&item.pages.length?' <span class="muted">('+t('rulews.evidence_pages')+' '+esc(item.pages.join('、'))+')</span>':'';return '<li>'+text+id+pages+'</li>'}return '<li>'+esc(String(item))+'</li>'}).join('')+'</ul>':'<div class="muted">'+t('classification.none')+'</div>'}
function renderCodebookStatus(profile){lastCodebookProfile=profile;let host=$('codebookstatus');if(!profile||profile.status==='none'||!profile.status){host.textContent=t('rulews.not_prepared');return}let lock=profile.status==='locked';host.innerHTML=(lock?'<span class="ok">'+t('rulews.locked')+'</span>':'<span class="error">'+t('rulews.draft')+'</span>')+'：<b>'+esc(profile.source_path||profile.source_name||'—')+'</b><br>'+esc(profile.page_count||0)+' '+t('rulews.pages')+' · '+esc(profile.parser_model||'—')+(lock?'<br>'+t('rulews.reused'):'<br>'+t('rulews.confirm'))}
async function loadCodebookStatus(){try{renderCodebookStatus(await api('/api/codebook'))}catch(e){setUIMessage($('codebookstatus'),e.uiMessage||{text:e.message},'error')}}
function leaveCodebookWorkspace(){if(!allowRuleDraftTransition())return;lastCodebookWorkspaceProfile=null;let composer=$('composer');composer.style.display='flex';$('chat').classList.remove('codebook-workspace');loadHistory()}
function showCodebookWorkspace(profile){if(ruleEditState){captureRuleEditor();if(ruleEditState.binding===ruleEditorBinding(profile)){renderRuleEditor();return}if(!allowRuleDraftTransition())return}lastCodebookWorkspaceProfile=profile;let draft=profile.draft||{};$('composer').style.display='none';let classes=(draft.classes||[]).map(item=>'<article class="card codebook-class"><h3>'+esc(item.name||t('rulews.untitled'))+'</h3><div>'+esc(item.definition||t('rulews.no_definition'))+'</div><b>'+t('rulews.decision_rules')+'</b>'+codebookList(item.decision_rules)+'<b>'+t('rulews.boundaries')+'</b>'+codebookList(item.boundaries)+'<div class="muted">'+t('rulews.evidence_pages')+'：'+esc((item.evidence_pages||[]).join('、')||'—')+'</div></article>').join('')||'<div class="card error">'+t('rulews.no_class')+'</div>';let usage=profile.usage||{},ocr=profile.ocr_runtime||{},locked=profile.status==='locked';let ocrText=ocr.status==='not applicable to DOCX'?t('rulews.ocr_docx'):(ocr.available?(t('rulews.ocr_enabled')+' · '+esc(ocr.command||'Tesseract')+(ocr.german_available?' · deu':' · eng')):(t('rulews.ocr_disabled')+' · '+esc(ocr.status||'Tesseract')));$('chat').className='chat codebook-workspace';$('chat').innerHTML='<section class="workspace-inner"><h1>'+t('rulews.title')+'</h1><div class="muted">'+(locked?t('rulews.locked_intro'):t('rulews.draft_intro'))+'</div><div class="card"><b>'+t('rulews.source')+'：</b>'+esc(profile.source_name||'—')+'<br><span class="muted">'+t('rulews.parser_model')+'：'+esc(profile.parser_model||'—')+' · '+t('rulews.pages')+'：'+esc(profile.page_count||0)+' · '+t('rulews.groups')+'：'+esc(profile.page_groups||0)+' · Token：'+usageNumber(usage.input)+' / '+usageNumber(usage.output)+(' · '+usageCost(usage))+'<br>'+ocrText+'</span></div><h2>'+t('rulews.classes')+'</h2>'+classes+'<h2>'+t('rulews.global_rules')+'</h2><div class="card">'+codebookList(draft.global_rules)+'</div><h2>'+t('rulews.table_rules')+'</h2><div class="card">'+codebookList(draft.table_rules)+'</div><h2>'+t('rulews.uncertainties')+'</h2><div class="card">'+codebookList(draft.uncertainties)+'</div><div class="workspace-actions"><button class="ghost" onclick="editCodebookDraft()">'+t('rules.edit')+'</button>'+ (locked?'<button class="ghost" onclick="leaveCodebookWorkspace()">'+t('rulews.back')+'</button>':'<button onclick="lockCodebook()">'+t('rulews.lock_action')+'</button><button class="ghost" onclick="leaveCodebookWorkspace()">'+t('rulews.defer')+'</button>')+'</div></section>';$('chat').scrollTop=0}
async function prepareCodebook(){if(!allowRuleDraftTransition())return;let path=$('codebook').value.trim();if(!path){$('codebookstatus').innerHTML='<span class="error">'+t('rulews.choose_file')+'</span>';return}let model=prompt(t('rulews.model_prompt'),selectedModel());if(model===null)return;model=model.trim();if(!model){$('codebookstatus').innerHTML='<span class="error">'+t('rulews.model_required')+'</span>';return}try{setUIMessage($('codebookstatus'),{message_key:'rulews.preparing'});let profile=await api('/api/codebook/prepare',{method:'POST',body:JSON.stringify({path,model})});renderCodebookStatus(profile);renderStatus(await api('/api/status'));showCodebookWorkspace(profile)}catch(e){setUIMessage($('codebookstatus'),e.uiMessage||{text:e.message},'error')}}
async function viewCodebook(){if(!allowRuleDraftTransition())return;try{let profile=await api('/api/codebook');if(!profile||!profile.status)throw Error(t('rulews.not_prepared'));renderCodebookStatus(profile);showCodebookWorkspace(profile)}catch(e){setUIMessage($('codebookstatus'),e.uiMessage||{text:e.message},'error')}}
async function lockCodebook(){if(!allowRuleDraftTransition())return;if(!confirm(t('rulews.lock_confirm')))return;try{let profile=await api('/api/codebook/lock',{method:'POST'});renderCodebookStatus(profile);renderStatus(await api('/api/status'));showCodebookWorkspace(profile);$('setupmsg').innerHTML='<span class="ok">'+t('rulews.lock_success')+'</span>'}catch(e){setUIMessage($('codebookstatus'),e.uiMessage||{text:e.message},'error')}}
async function changeCodebook(){if(!allowRuleDraftTransition())return;if(!confirm(t('rulews.replace_confirm')))return;try{await api('/api/codebook',{method:'DELETE'});$('codebook').value='';renderCodebookStatus({status:'none'});leaveCodebookWorkspace();setUIMessage($('setupmsg'),{message_key:'rulews.replace_success'})}catch(e){setUIMessage($('codebookstatus'),e.uiMessage||{text:e.message},'error')}}
let sessionOffset=0,sessionHasMore=false,sessionLoading=false,currentSessionName='';
function initSessionSidebar(){if($('sessionpanel'))return;let left=document.querySelector('.shell > .side');if(!left)return;let style=document.createElement('style');style.textContent='.side.left{display:flex;flex-direction:column;overflow:hidden;padding-bottom:10px}.left-content{overflow:auto;min-height:0;padding-right:2px}.session-panel{border-top:1px solid #334155;margin-top:10px;padding-top:10px;display:flex;flex-direction:column;min-height:155px;max-height:42vh}.session-new{width:100%;margin-bottom:8px;text-align:left}.session-list{overflow:auto;min-height:0}.session-row{display:flex;align-items:center;gap:4px;border-radius:7px;margin:2px 0;padding:6px 5px;cursor:pointer;color:#dbeafe}.session-row:hover,.session-row.active{background:#263244}.session-title{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1}.session-more{visibility:hidden;width:25px;padding:2px 3px;background:transparent;color:#cbd5e1}.session-row:hover .session-more,.session-row.active .session-more{visibility:visible}.session-pin{font-size:10px;color:#7dd3fc}.session-loading{text-align:center;padding:8px;color:#94a3b8}.session-menu{position:fixed;z-index:100;min-width:130px;padding:5px;background:#1e293b;border:1px solid #475569;border-radius:8px;box-shadow:0 12px 30px rgba(0,0,0,.4)}.session-menu button{display:block;width:100%;text-align:left;background:transparent;color:#e5e7eb;padding:7px 9px}.session-menu button:hover{background:#334155}.session-menu button.delete{color:#fca5a5}';document.head.append(style);left.classList.add('left');let content=document.createElement('div');content.className='left-content';while(left.firstChild)content.append(left.firstChild);left.append(content);let old=$('session')?.closest('.field');if(old)old.style.display='none';let panel=document.createElement('section');panel.id='sessionpanel';panel.className='session-panel';panel.innerHTML='<button id="newsessionbutton" class="ghost session-new" onclick="newSession()"></button><div id="sessionlist" class="session-list"></div>';left.append(panel);localizeSessionChrome();$('sessionlist').addEventListener('scroll',()=>{let el=$('sessionlist');if(sessionHasMore&&!sessionLoading&&el.scrollTop+el.clientHeight>=el.scrollHeight-18)loadSessions(false)});document.addEventListener('click',event=>{if(!event.target.closest('.session-more')&&!event.target.closest('#sessionmenu'))closeSessionMenu()})}
function localizeSessionChrome(){setI18nText($('newsessionbutton'),'session.new')}
function closeSessionMenu(){$('sessionmenu')?.remove()}
function renderSessionRows(items,append){let list=$('sessionlist');if(!append)list.innerHTML='';for(let item of items){let row=document.createElement('div');row.className='session-row'+(item.name===currentSessionName?' active':'');row.onclick=()=>openSessionByName(item.name);let title=document.createElement('span');title.className='session-title';title.textContent=item.title;row.append(title);if(item.pinned){let pin=document.createElement('span');pin.className='session-pin';pin.textContent='●';pin.title='已置顶';row.append(pin)}let more=document.createElement('button');more.className='session-more';more.textContent='•••';more.title='更多';more.onclick=e=>{e.stopPropagation();openSessionMenu(e,item)};row.append(more);list.append(row)}if(sessionLoading){let loading=document.createElement('div');loading.id='sessionloading';loading.className='session-loading';loading.textContent='正在加载…';list.append(loading)}}
async function loadSessions(reset=true){if(sessionLoading)return;if(reset){sessionOffset=0;sessionHasMore=false;renderSessionRows([],true)}sessionLoading=true;try{let x=await api('/api/sessions?offset='+sessionOffset+'&limit=10');currentSessionName=x.current;let existingCount=$('sessionlist').querySelectorAll('.session-row').length,items=x.sessions;renderSessionRows(items,!reset);let rows=[...$('sessionlist').querySelectorAll('.session-row')];items.forEach((item,index)=>rows[existingCount+index].dataset.name=item.name);sessionOffset+=items.length;sessionHasMore=!!x.has_more}catch(e){$('sessionmsg').textContent=e.message}finally{sessionLoading=false;$('sessionloading')?.remove()}}
async function restoreSessionTree(target,paths){$('treestatus').textContent=rt('session.restoring');let x=await api('/api/target-tree?target='+encodeURIComponent(target));savedTargetSelection=new Set(paths||[]);treeRestoreNote=rt('session.restored');let host=$('targettree');host.classList.remove('muted');host.innerHTML='';host.append(makeTreeNode(x.tree));refreshAllFolderStates()}
async function restoreSessionContext(){try{let x=await api('/api/session/context');setSelectedModel(x.model);let target=x.target||{};$('targetpath').value=target.path||'';$('codebook').value=x.codebook_path||'';if(target.path&&target.kind==='文件夹'){await restoreSessionTree(target.path,target.selected_paths)}else{clearTargetTree()}materialDraftDirty=false;await loadCodebookStatus();loadDocs();loadCoverage()}catch(e){console.warn('Could not restore session context',e);$('treestatus').innerHTML='<span class="error">'+esc(rt('session.restore_failed')+e.message)+'</span>'}}
async function openSessionByName(name){if(!allowRuleDraftTransition())return;try{closeSessionMenu();let s=await api('/api/session/open',{method:'POST',body:JSON.stringify({name})});renderStatus(s);await restoreSessionContext();await loadHistory();await loadSessions(true)}catch(e){setUIMessage($('sessionmsg'),e.uiMessage||{text:e.message},'error')}}
async function newSession(){if(!allowRuleDraftTransition())return;try{let s=await api('/api/session/new',{method:'POST'});renderStatus(s);$('targetpath').value='';$('codebook').value='';clearTargetTree();await loadHistory();await loadSessions(true);loadDocs();loadCodebookStatus()}catch(e){setUIMessage($('sessionmsg'),e.uiMessage||{text:e.message},'error')}}
function openSessionMenu(event,item){closeSessionMenu();let menu=document.createElement('div');menu.id='sessionmenu';menu.className='session-menu';let rect=event.currentTarget.getBoundingClientRect();menu.style.left=Math.min(window.innerWidth-145,rect.right+6)+'px';menu.style.top=rect.top+'px';menu.innerHTML='<button data-action="rename">重命名</button><button data-action="pin">'+(item.pinned?'取消置顶':'置顶')+'</button><button class="delete" data-action="delete">删除</button>';menu.onclick=async e=>{let action=e.target.dataset.action;if(!action)return;if(action==='rename')await renameSession(item.name);if(action==='pin')await pinSession(item);if(action==='delete')await deleteSession(item.name);closeSessionMenu()};document.body.append(menu)}
async function renameSession(name){let value=prompt(t('session.rename_prompt'),name);if(!value?.trim())return;try{let s=await api('/api/session/rename',{method:'POST',body:JSON.stringify({name:value.trim(),source:name})});renderStatus(s);await loadSessions(true)}catch(e){alert(e.message)}}
async function pinSession(item){try{await api('/api/session/pin',{method:'POST',body:JSON.stringify({name:item.name,pinned:!item.pinned})});await loadSessions(true)}catch(e){alert(e.message)}}
async function deleteSession(name){if(name===currentSessionName&&!allowRuleDraftTransition())return;if(!confirm(t('session.delete_confirm')))return;try{let wasCurrent=name===currentSessionName;let s=await api('/api/session/delete',{method:'POST',body:JSON.stringify({confirmed:true,name})});renderStatus(s);if(wasCurrent){await restoreSessionContext();await loadHistory()}await loadSessions(true)}catch(e){alert(e.message)}}
async function loadHistory(){if(ruleEditState)return;try{let x=await api('/api/history');if(ruleEditState)return;$('chat').innerHTML='';if(!x.history.length){uiMessageNode({message_key:'session.new_hint'});return}for(let item of x.history)message(item.content,item.role==='user'?'user':'assistant')}catch{}}
async function setup(){if(!allowRuleDraftTransition())return false;try{let model=selectedModel();if(!model)throw Error(t('model.id_required'));let s=await api('/api/setup',{method:'POST',body:JSON.stringify({workspace:$('workspace').value,state_dir:'',env_file:'',model:model,session:$('session').value.trim()||'default',language:uiLanguage})});renderStatus(s);await restoreSessionContext();await Promise.all([loadDocs(),loadSessions(),loadHistory(),loadCodebookStatus()]);setUIMessage($('setupmsg'),{message_key:'workspace.opened'});refreshAppChrome();$('startupnotice')?.remove();return true}catch(e){let detail=e.uiMessage||{text:e.message};setUIMessage($('setupmsg'),detail,'error');setUIMessage($('contextworkspacemsg'),detail,'error');showStartupNotice(detail);return false}}
async function openLegacySession(){if(!$('session').value)return;await setup()}
async function switchModel(){if(!allowRuleDraftTransition())return;try{let model=selectedModel();if(!model)throw Error(t('model.id_required'));let s=await api('/api/model',{method:'POST',body:JSON.stringify({model})});renderStatus(s);clearResultPanels();await loadHistory();$('modelmsg').innerHTML='<span class="ok">'+t('model.switched_prefix')+esc(model)+t('model.context_unchanged')+'</span>'}catch(e){setUIMessage($('modelmsg'),e.uiMessage||{text:e.message},'error')}}
async function loadModelStatus(){try{
  let x=await api('/api/model-tests'),r=x.tests[selectedModel()];
  if(!r){setUIMessage($('modelstatus'),{message_key:'model.untested'});return}
  setUIMessage($('modelstatus'),[{message_key:r.ok?'model.last_available':'model.last_failed'},r.tested_at,
    ...(r.ok?['; ',r.streaming_message||{text:r.streaming||''},'; ',{message_key:'model.usage_label'},' ',
      {message_key:r.usage_available===false?'model.usage_missing':'model.usage_returned'}]:[])],r.ok?'ok':'error');
}catch{}}
async function testModel(){try{
  let model=selectedModel();if(!model)throw Error(t('model.id_required'));
  setUIMessage($('modelmsg'),{message_key:'model.testing'});
  let x=await api('/api/model-test',{method:'POST',body:JSON.stringify({model})});$('startupnotice')?.remove();
  setUIMessage($('modelmsg'),x.ok?[{message_key:'model.available'},x.model,'; ',x.streaming_message||{text:x.streaming||''},
    {message_key:'usage.input_fragment'},String(x.input_tokens),{message_key:'usage.output_fragment'},String(x.output_tokens),
    {message_key:'usage.token_suffix'},' ',...(x.usage_available===false?[{message_key:'usage.unavailable'}]:[])]:
    [{message_key:'model.test_failed'},x.message_key?x:{text:x.message}],x.ok?'ok':'error');
  loadModelStatus();
}catch(e){let detail=e.uiMessage||{text:e.message};setUIMessage($('modelmsg'),detail,'error');showStartupNotice(detail)}}
function renderDocuments(documents){lastDocumentsSnapshot=documents;$('docs').innerHTML=documents.map(d=>`<div class="card">${esc(d.name)}<br><span class="muted">${esc(roleCopy(d.material_role_label))} · ${t('scan.report.chunks',{count:d.chunks})}</span></div>`).join('')||t('materials.empty')}
async function loadDocs(){try{renderDocuments(await api('/api/documents'))}catch{}}
async function addDoc(){try{let d=await api('/api/document',{method:'POST',body:JSON.stringify({path:$('docpath').value})});$('docpath').value='';loadDocs();$('setupmsg').textContent=`已索引 ${d.name}（${d.chunks} chunks）`}catch(e){setUIMessage($('setupmsg'),e.uiMessage||{text:e.message},'error')}}
function renderScanReport(x){setScanReportAvailable(x);renderScanDrawer(x)}
function renderCoverageReport(x){if(!x||!x.files){$('coveragestatus').textContent='分类/Codebook 问题会自动准备证据；也可在提问前手动准备。';return}if(x.current_selection===false){$('coveragestatus').innerHTML='<span class="muted">材料选择或模型已更新；下次分类准备时会复用未变文件的本地摘要，仅预读新增/变更文件。</span>';return}let done=x.files.filter(f=>f.complete).length;let details=x.files.map(f=>{let pages=f.pages_total?`页：已读 ${(f.pages_read||[]).join('、')||'—'}${(f.pages_unread||[]).length?'；未读 '+f.pages_unread.join('、'):''}`:'无页码';let dfc=f.dfc_structure?` · <span class="chip">DFC Struktur：${esc(f.dfc_structure.ocr_status||'—')}，${esc(f.dfc_structure.segments_total||0)} 段</span>`:'';let cache=f.cache_status==='reused'?' · <span class="chip">本地摘要已复用</span>':f.cache_status==='created'?' · <span class="chip">本轮新预读</span>':'';return `<br>${f.complete?'✓':'✕'} ${esc(f.name)}：${f.text_groups_processed}/${f.text_groups_total} 个文本组 · ${esc(f.reading_scope||'')} · ${esc(pages)}${cache}${dfc}${f.failures?.length?'（'+esc(f.failures.join('；'))+'）':''}`}).join('');let dossier=x.bg_dossier?.ready?' · <span class="chip">BG 综合证据档案已缓存</span>':' · <span class="chip">首次分类后生成 BG 综合证据档案</span>';$('coveragestatus').innerHTML=(x.complete?'<span class="ok">分类证据已准备：</span>':'<span class="error">分类证据不完整：</span>')+` ${done}/${x.files.length} 个文件；复用 ${x.reused_files||0} 个，新预读 ${x.created_files||0} 个；本次 ${x.model_calls||0} 次模型调用。`+dossier+details}
async function loadCoverage(){try{renderCoverageReport(await api('/api/coverage'))}catch{}}
function ensureMaterialFlow(){if($('materialactions'))return;let style=document.createElement('style');style.textContent='#materialactions{display:flex;gap:7px;margin:8px 0}.scan-backdrop{position:fixed;inset:0;background:rgba(2,6,23,.28);z-index:20;opacity:0;pointer-events:none;transition:opacity .18s}.scan-backdrop.open{opacity:1;pointer-events:auto}.scan-drawer{position:absolute;left:270px;top:72px;bottom:20px;width:min(680px,calc(100vw - 310px));background:#172033;border:1px solid #3b4960;border-left:3px solid #38bdf8;border-radius:0 12px 12px 0;box-shadow:12px 16px 45px rgba(0,0,0,.45);transform:translateX(-34px);opacity:0;transition:transform .22s ease,opacity .18s;display:flex;flex-direction:column}.scan-backdrop.open .scan-drawer{transform:translateX(0);opacity:1}.scan-drawer-head{display:flex;justify-content:space-between;align-items:center;padding:14px 16px;border-bottom:1px solid #334155}.scan-drawer-body{overflow:auto;padding:12px 16px}.scan-drawer .file-card{border:1px solid #334155;border-radius:8px;padding:10px;margin:9px 0;background:#111827;line-height:1.5}.scan-drawer .file-card b{word-break:break-word}@media(max-width:760px){.scan-drawer{left:0;top:0;bottom:0;width:min(94vw,680px);border-radius:0 12px 12px 0}}';document.head.append(style);let tree=$('targettree'),confirm=document.querySelector('button[onclick="analyzeTarget()"]');let actions=document.createElement('div');actions.id='materialactions';confirm.id='confirmmaterials';confirm.textContent='确认选中材料';let report=document.createElement('button');report.id='viewscanreport';report.className='ghost';report.disabled=true;report.textContent='查看扫描报告';report.onclick=openScanReport;actions.append(confirm,report);tree.insertAdjacentElement('afterend',actions);$('scanreport').style.display='none';let backdrop=document.createElement('div');backdrop.id='scanbackdrop';backdrop.className='scan-backdrop';backdrop.innerHTML='<section class="scan-drawer" role="dialog" aria-modal="true" aria-label="扫描报告"><div class="scan-drawer-head"><div><b>本次材料扫描报告</b><div class="muted">仅本地读取与索引；不消耗模型 token。</div></div><button class="ghost" onclick="closeScanReport()">×</button></div><div id="scanreportbody" class="scan-drawer-body"></div></section>';backdrop.addEventListener('click',e=>{if(e.target===backdrop)closeScanReport()});document.body.append(backdrop);document.addEventListener('keydown',e=>{if(e.key==='Escape')closeScanReport()});updateMaterialFlowButtons()}
function updateMaterialFlowButtons(){let confirm=$('confirmmaterials'),report=$('viewscanreport');if(confirm)confirm.disabled=treeFileCount()===0;if(report&&!lastScanReport){report.disabled=true;report.textContent='查看扫描报告'} }
function setScanReportAvailable(report){lastScanReport=report||null;let button=$('viewscanreport');if(button){button.disabled=!lastScanReport;button.textContent=lastScanReport?'查看扫描报告':'查看扫描报告'}}
function openScanReport(){if(!lastScanReport)return;renderScanDrawer(lastScanReport);$('scanbackdrop').classList.add('open');loadCacheAudit()}
function closeScanReport(){$('scanbackdrop')?.classList.remove('open')}
function renderScanDrawer(x){let files=(x.files||[]).map(f=>{let index=f.index_cache_status==='reused'?rt('scan.index.reused'):f.index_cache_status==='changed'?rt('scan.index.changed'):f.index_cache_status==='new'?rt('scan.index.created'):'—';return `<article class="file-card"><b>${esc(f.name)}</b><br><span class="muted">${esc(f.material_role_label||'其他资料')} · ${(Number(f.bytes)/1024/1024).toFixed(1)} MB<br>本地文本片段：${f.chunks} · ${index}</span></article>`}).join('')||'<div class="muted">'+rt('scan.report.none')+'</div>';let skipped=x.skipped_count?`<article class="file-card error"><b>跳过 / 失败 ${x.skipped_count} 个</b><br><span class="muted">${x.skipped.map(esc).join('<br>')}${x.skipped_count>x.skipped.length?'<br>其余失败项未展开。':''}</span></article>`:'';let audit='<details id="cacheauditpanel" class="file-card" ontoggle="if(this.open)loadCacheAudit()"><summary><b>'+rt('scan.report.cache')+'</b></summary><div class="muted" style="margin:7px 0">'+rt('scan.report.cache_detail')+'</div><div id="cacheaudit" class="list muted">'+rt('scan.report.cache_loading')+'</div></details>';$('scanreportbody').innerHTML='<div class="muted">'+rt('scan.report.added',{count:x.sources||0})+'</div>'+files+skipped+audit}
function renderCacheAudit(x){let host=$('cacheaudit');if(!host)return;if(!x.files?.length){host.textContent=rt('material.none');return}let hasSummary=x.files.some(f=>(f.summary_entries||[]).length);if(!hasSummary){host.innerHTML='<div class="muted">'+rt('material.cache_empty')+'</div>';return}let dossier=x.dossier?.ready?`BG 综合档案：已缓存（${esc(x.dossier.model||'—')}）`:'BG 综合档案：尚未生成或材料范围已变化';let files=x.files.map(f=>{let summaries=(f.summary_entries||[]).map(s=>`${esc(s.model||'—')} · ${s.full?'全部页':'默认范围'} · ${s.complete?'完成':'未完成'}`).join('<br>')||'无摘要缓存';let read=(f.summary_entries||[]).length?'<br><button class="ghost" data-document-id="'+escAttr(f.id)+'" onclick="rebuildCachedFile(this.dataset.documentId)">仅重读此文件</button>':'';return `<div class="card"><b>${esc(f.name)}</b><br><span class="muted">索引：${esc(f.index_status)} · OCR：${esc(f.ocr_status)}<br>摘要：${summaries}</span>${read}</div>`}).join('');host.innerHTML='<div class="muted">'+dossier+(x.selection_current?'':'；当前材料范围待更新')+'</div><div class="row"><button class="ghost" onclick="rebuildDossier()">重建 BG 档案</button><button class="ghost" onclick="clearSummaryCaches()">清除摘要缓存</button></div>'+files}
async function loadCacheAudit(){let host=$('cacheaudit');if(!host)return;try{renderCacheAudit(await api('/api/cache/audit'))}catch(e){setUIMessage(host,e.uiMessage||{text:e.message},'error')}}
async function rebuildCachedFile(id){if(!confirm(t('cache.rebuild_file_confirm')))return;try{let x=await api('/api/cache/file/rebuild',{method:'POST',body:JSON.stringify({document_id:id,confirmed:true})});setUIMessage($('coveragestatus'),x);renderCacheAudit(x.audit)}catch(e){setUIMessage($('cacheaudit'),e.uiMessage||{text:e.message},'error')}}
async function rebuildDossier(){if(!confirm(rt('dossier.confirm')))return;let host=$('cacheaudit');let button=host?.querySelector('button[onclick="rebuildDossier()"]');if(button)button.disabled=true;$('coveragestatus').textContent=rt('dossier.working');try{let x=await api('/api/cache/dossier/rebuild',{method:'POST',body:JSON.stringify({confirmed:true})});setUIMessage($('coveragestatus'),x);renderCacheAudit(x.audit);renderStatus(await api('/api/status'))}catch(e){$('coveragestatus').innerHTML='<span class="error">'+esc(rt('dossier.failed')+e.message)+'</span>';if(host)host.innerHTML='<span class="error">'+esc(rt('dossier.failed')+e.message)+'</span>'}finally{if(button)button.disabled=false}}
async function clearSummaryCaches(){if(!confirm(t('cache.clear_confirm')))return;try{let x=await api('/api/cache/clear',{method:'POST',body:JSON.stringify({confirmed:true})});setUIMessage($('coveragestatus'),x);renderCacheAudit(x.audit)}catch(e){setUIMessage($('cacheaudit'),e.uiMessage||{text:e.message},'error')}}
function clearTargetTree(){savedTargetSelection=new Set();treeRestoreNote='';scannedSelection='';setScanReportAvailable(null);$('targettree').textContent='选择文件夹后显示可展开的文件树。';$('targettree').classList.add('muted');$('treestatus').textContent='';updateMaterialFlowButtons()}
// These renderers deliberately receive data, never pre-rendered text.  This
// makes a language switch deterministic even after a scan or cache view is open.
function renderStatusForLanguage(s){let tokens=usageNumber(s.input_tokens)+' / '+usageNumber(s.output_tokens);if(s.usage_complete===false)tokens+=' · '+t('usage.known_subtotal')+': '+usageNumber(s.known_input_tokens)+' / '+usageNumber(s.known_output_tokens);let cost=usageCost({cost_usd:s.cost,known_cost_usd:s.known_cost_usd});$('status').innerHTML=`${t('status.model')}：<b>${esc(s.model)}</b><br>${t('status.session')}：${esc(s.session_name||'default')}<br>${t('status.code')}：${t('status.files',{count:s.code_files})}<br>${t('status.documents')}：${t('status.items',{count:s.documents})}<br>${t('status.requests')}：${esc(s.requests)}<br>${t('status.tokens')}：${tokens}<br>${t('status.cost')}：${cost}${s.unpriced_requests?' · '+t('usage.partial',{count:s.unpriced_requests}):''}<br>${s.bg_context?'<span class="ok">'+t('status.assembly_mode')+'：'+esc(s.bg_context.codebook_name)+'</span>':t('status.normal_mode')}`;refreshAppChrome();refreshContextPanel()}
function renderUsageDetailForLanguage(u,model){if(!u)return;$('usagedetail').innerHTML=`${t('usage.actual_model')}：<b>${esc(model||'—')}</b><br>${t('usage.input_output_total')}：${usageNumber(u.input)} / ${usageNumber(u.output)} / ${usageNumber(u.total)}${u.usage_complete===false?' · '+t('usage.known_subtotal')+': '+usageNumber(u.known_input)+' / '+usageNumber(u.known_output):''}<br>${t('usage.reasoning')}：${usageNumber(u.reasoning)} ｜ ${t('usage.gemini_thinking')}：${usageNumber(u.gemini_thinking)}<br>${t('usage.claude_cache')}：${usageNumber(u.cache_read)} / ${usageNumber(u.cache_write)}<br>${t('usage.estimate')}：${usageCost(u)}`}
function renderEvidenceSourcesForLanguage(sources,dfcEvidence){let normal=(sources||[]).map(s=>`<div class="card"><b>${esc(s.label||s.name||t('model.unknown_source'))}</b><br>${s.visual?'<span class="chip">'+t('evidence.visual')+'</span>':''}</div>`).join('');let dfc=(dfcEvidence||[]).map(d=>{let parts=(d.segments_used||[]).join('、')||'—';return `<div class="card"><b>DFC Struktur</b><br>${esc(d.name||'—')}<br><span class="chip">OCR：${esc(stateCopy(d.ocr_status))}</span><span class="chip">${t('dfc.segment_info',{segments:esc(parts),total:esc(d.segments_total||0)})}</span></div>`}).join('');$('sources').innerHTML=(dfc+normal)||t('evidence.none')}
function renderCompareSlotsForLanguage(){let host=$('comparemodels');host.innerHTML=compareSlots.map((slot,index)=>{let options='<option value="">'+t('compare.select_model')+'</option>'+compareOptions.map(([value,label])=>'<option value="'+escAttr(value)+'" '+(slot.value===value?'selected':'')+'>'+esc(label)+'</option>').join('')+'<option value="__custom__" '+(slot.value==='__custom__'?'selected':'')+'>'+t('model.other')+'</option>';return '<div class="field"><label>'+t('compare.model_number',{index:index+1})+'</label><div class="row"><select id="cmpsel'+index+'" onchange="changeCompareModel('+index+')">'+options+'</select>'+(index>0?'<button class="ghost" onclick="removeCompareModel('+index+')">×</button>':'')+'</div>'+(slot.value==='__custom__'?'<input id="cmpcustom'+index+'" value="'+escAttr(slot.custom||'')+'" placeholder="'+t('model.id_placeholder')+'" oninput="compareSlots['+index+'].custom=this.value">':'')+'</div>'}).join('');let add=$('addcompare');add.disabled=compareSlots.length>=4;add.textContent=compareSlots.length>=4?t('compare.maximum'):t('compare.add');if(compareSlots.length>=4)setUIMessage($('comparestatus'),{message_key:'compare.maximum'})}
function renderSessionRowsForLanguage(items,append){let list=$('sessionlist');if(!list)return;if(!append)list.innerHTML='';for(let item of items){let row=document.createElement('div');row.className='session-row'+(item.name===currentSessionName?' active':'');row.onclick=()=>openSessionByName(item.name);let title=document.createElement('span');title.className='session-title';title.textContent=item.title;row.append(title);if(item.pinned){let pin=document.createElement('span');pin.className='session-pin';pin.textContent='●';pin.title=t('session.pin_title');row.append(pin)}let more=document.createElement('button');more.className='session-more';more.textContent='•••';more.title=t('session.more_title');more.onclick=e=>{e.stopPropagation();openSessionMenu(e,item)};row.append(more);list.append(row)}if(sessionLoading){let loading=document.createElement('div');loading.id='sessionloading';loading.className='session-loading';loading.textContent=t('session.loading');list.append(loading)}}
function openSessionMenuForLanguage(event,item){closeSessionMenu();let menu=document.createElement('div');menu.id='sessionmenu';menu.className='session-menu';let rect=event.currentTarget.getBoundingClientRect();menu.style.left=Math.min(window.innerWidth-145,rect.right+6)+'px';menu.style.top=rect.top+'px';menu.innerHTML='<button data-action="rename">'+t('actions.rename_full')+'</button><button data-action="pin">'+t(item.pinned?'session.unpin':'session.pin')+'</button><button class="delete" data-action="delete">'+t('actions.delete')+'</button>';menu.onclick=async e=>{let action=e.target.dataset.action;if(!action)return;if(action==='rename')await renameSession(item.name);if(action==='pin')await pinSession(item);if(action==='delete')await deleteSession(item.name);closeSessionMenu()};document.body.append(menu)}
function renderCoverageReportForLanguage(x){
  if(!x||!x.files){setUIMessage($('coveragestatus'),{message_key:'coverage.auto_prepare'});return}
  if(x.current_selection===false){$('coveragestatus').innerHTML='<span class="muted">'+t('coverage.selection_changed')+'</span>';return}
  let done=x.files.filter(f=>f.complete).length;
  let details=x.files.map(f=>{let pages=f.pages_total?t('coverage.pages')+'：'+t('coverage.read_pages',{pages:(f.pages_read||[]).join('、')||'—'})+((f.pages_unread||[]).length?'；'+t('coverage.unread_pages',{pages:f.pages_unread.join('、')}):''):t('coverage.no_pages');let dfc=f.dfc_structure?' · <span class="chip">'+t('coverage.dfc',{status:esc(stateCopy(f.dfc_structure.ocr_status)),count:esc(f.dfc_structure.segments_total||0)})+'</span>':'';let cache=f.cache_status==='reused'?' · <span class="chip">'+t('coverage.reused_summary')+'</span>':f.cache_status==='created'?' · <span class="chip">'+t('coverage.new_pre_read')+'</span>':'';return `<br>${f.complete?'✓':'✕'} ${esc(f.name)}：${t('coverage.text_groups',{done:f.text_groups_processed,total:f.text_groups_total})} · ${esc(scopeCopy(f))} · ${esc(pages)}${cache}${dfc}${f.failures?.length?'（'+esc((f.failure_messages||f.failures).map(uiCopy).join('; '))+'）':''}`}).join('');
  let dossier=x.bg_dossier?.ready?' · <span class="chip">'+t('coverage.dossier_ready')+'</span>':' · <span class="chip">'+t('coverage.dossier_pending')+'</span>';
  $('coveragestatus').innerHTML=(x.complete?'<span class="ok">'+t('coverage.ready')+'：</span>':'<span class="error">'+t('coverage.incomplete')+'：</span>')+' '+t('coverage.overview',{done,total:x.files.length,reused:x.reused_files||0,created:x.created_files||0,calls:x.model_calls||0})+dossier+details;
}
function renderScanDrawerForLanguage(x){
  let files=(x.files||[]).map(f=>{let index=f.index_cache_status==='reused'?t('scan.index.reused'):f.index_cache_status==='changed'?t('scan.index.changed'):f.index_cache_status==='new'?t('scan.index.created'):'—';return `<article class="file-card"><b>${esc(f.name)}</b><br><span class="muted">${esc(roleCopy(f.material_role_label))} · ${(Number(f.bytes)/1024/1024).toFixed(1)} MB<br>${t('scan.report.chunks',{count:f.chunks})} · ${index}</span></article>`}).join('')||'<div class="muted">'+t('scan.report.none')+'</div>';
  let skipped=x.skipped_count?`<article class="file-card error"><b>${t('scan.report.skipped',{count:x.skipped_count})}</b><br><span class="muted">${x.skipped.map(esc).join('<br>')}${x.skipped_count>x.skipped.length?'<br>'+t('scan.report.more_failures'):''}</span></article>`:'';
  let audit='<details id="cacheauditpanel" class="file-card" ontoggle="if(this.open)loadCacheAudit()"><summary><b>'+t('scan.report.cache')+'</b></summary><div class="muted" style="margin:7px 0">'+t('scan.report.cache_detail')+'</div><div id="cacheaudit" class="list muted">'+t('scan.report.cache_loading')+'</div></details>';
  $('scanreportbody').innerHTML='<div class="muted">'+t('scan.report.added',{count:x.sources||0})+'</div>'+files+skipped+audit;
}
function renderCacheAuditForLanguage(x){
  let host=$('cacheaudit');if(!host)return;
  if(!x.files?.length){host.textContent=t('material.none');return}
  if(!x.files.some(f=>(f.summary_entries||[]).length)){host.innerHTML='<div class="muted">'+t('material.cache_empty')+'</div>';return}
  let dossier=x.dossier?.ready?t('cache.dossier_ready',{model:esc(x.dossier.model||'—')}):t('cache.dossier_missing');
  let files=x.files.map(f=>{let summaries=(f.summary_entries||[]).map(s=>`${esc(s.model||'—')} · ${t(s.full?'cache.full':'cache.default_scope')} · ${t(s.complete?'cache.complete':'cache.incomplete')}`).join('<br>')||t('cache.no_summary');let read=(f.summary_entries||[]).length?'<br><button class="ghost" data-document-id="'+escAttr(f.id)+'" onclick="rebuildCachedFile(this.dataset.documentId)">'+t('cache.rebuild_file')+'</button>':'';return `<div class="card"><b>${esc(f.name)}</b><br><span class="muted">${t('cache.index')}：${esc(({reused:t('scan.index.reused'),changed:t('scan.index.changed'),new:t('scan.index.created')})[f.index_status]||stateCopy(f.index_status))} · OCR：${esc(stateCopy(f.ocr_status))}<br>${t('cache.summary')}：${summaries}</span>${read}</div>`}).join('');
  host.innerHTML='<div class="muted">'+dossier+(x.selection_current?'':'；'+t('cache.scope_changed'))+'</div><div class="row"><button class="ghost" onclick="rebuildDossier()">'+t('cache.rebuild_dossier')+'</button><button class="ghost" onclick="clearSummaryCaches()">'+t('cache.clear')+'</button></div>'+files;
}
// Keep the last data payload, then redraw it with the active language.  The
// renderers remain the single source of HTML for both fresh API data and a UI
// language switch.
const baseRenderCoverageReport=renderCoverageReport;
renderCoverageReport=function(x){lastCoverageReport=x;return renderCoverageReportForLanguage(x)};
renderScanDrawer=function(x){return renderScanDrawerForLanguage(x)};
renderCacheAudit=function(x){lastCacheAudit=x;return renderCacheAuditForLanguage(x)};
renderStatus=function(s){lastStatusSnapshot=s;return renderStatusForLanguage(s)};
renderUsageDetail=function(u,model){if(u)lastUsageSnapshot={usage:u,model};return renderUsageDetailForLanguage(u,model)};
let lastSourcesSnapshot=null;
renderEvidenceSources=function(sources,dfcEvidence){lastSourcesSnapshot={sources,dfc:dfcEvidence};return renderEvidenceSourcesForLanguage(sources,dfcEvidence)};
renderCompareSlots=function(){return renderCompareSlotsForLanguage()};
renderSessionRows=function(items,append){if(!append)lastSessionRows=[];lastSessionRows.push(...items);return renderSessionRowsForLanguage(items,append)};
openSessionMenu=function(event,item){return openSessionMenuForLanguage(event,item)};
async function pickFolderForTree(){await pick('folder','targetpath');if($('targetpath').value)loadTargetTree()}
function treeFileCount(){return [...$('targettree').querySelectorAll('input.tree-file:checked')].length}
function updateTreeStatus(){let count=treeFileCount(),signature=selectedTargetPaths().sort().join('|');if(scannedSelection&&signature!==scannedSelection)setScanReportAvailable(null);$('treestatus').textContent=(count?`已选择 ${count} 个受支持文件。`:'尚未选择材料；勾选文件或整个子文件夹。')+(treeRestoreNote?' '+treeRestoreNote:'');updateMaterialFlowButtons()}
function refreshFolderState(folder){let files=[...folder.querySelectorAll('input.tree-file:not(:disabled)')];let box=folder.querySelector(':scope > summary input.tree-folder');if(!box||!files.length)return;let checked=files.filter(x=>x.checked).length;box.checked=checked===files.length;box.indeterminate=checked>0&&checked<files.length}
function refreshAllFolderStates(){[...$('targettree').querySelectorAll('details')].reverse().forEach(refreshFolderState);updateTreeStatus()}
function recommendedTreePaths(node,paths=[]){if(node.type==='file'){if(node.recommended)paths.push(node.relative);return paths}(node.children||[]).forEach(child=>recommendedTreePaths(child,paths));return paths}
function makeTreeNode(node,depth=0){if(node.type==='folder'){let details=document.createElement('details');details.open=depth<1;let summary=document.createElement('summary');let box=document.createElement('input');box.type='checkbox';box.className='tree-folder';box.addEventListener('click',e=>e.stopPropagation());box.addEventListener('change',()=>{materialDraftDirty=true;details.querySelectorAll('input.tree-file:not(:disabled)').forEach(x=>x.checked=box.checked);refreshAllFolderStates()});let label=document.createElement('label');label.textContent='📁 '+node.name;summary.append(box,label);details.append(summary);let children=document.createElement('div');children.className='tree-children';node.children.forEach(child=>children.append(makeTreeNode(child,depth+1)));details.append(children);return details}let row=document.createElement('div');row.className='tree-file'+(node.supported?'':' unsupported');let box=document.createElement('input');box.type='checkbox';box.className='tree-file';box.dataset.path=node.path;box.checked=!!node.supported&&savedTargetSelection.has(node.relative);box.disabled=!node.supported;box.addEventListener('change',()=>{materialDraftDirty=true;refreshAllFolderStates()});let label=document.createElement('label');let role=node.material_role_label?` · ${tr(node.material_role_label)}`:'';let hint=node.supported&&!node.recommended?' · 默认不选':'';label.textContent='📄 '+node.name+(node.supported?` · ${(node.bytes/1024/1024).toFixed(node.bytes<1024*1024?2:1)} MB${role}${hint}`:` · 不支持${role}`);row.append(box,label);return row}
async function loadTargetTree(){let target=$('targetpath').value.trim();if(!target){$('treestatus').innerHTML='<span class="error">请先选择或粘贴一个 BG 文件夹路径。</span>';return}try{$('treestatus').textContent='正在仅读取文件夹结构…';let x=await api('/api/target-tree?target='+encodeURIComponent(target));savedTargetSelection=new Set(x.saved_selection||[]);let notes=[];if(savedTargetSelection.size)notes.push(`已恢复上次的 ${savedTargetSelection.size} 项选择。`);else{savedTargetSelection=new Set(recommendedTreePaths(x.tree));notes.push(`已按资料类型默认选择 ${savedTargetSelection.size} 项原始资料；派生重复资料默认未选。`)}if(x.changed_saved_files)notes.push(`${x.changed_saved_files} 个已选文件内容已变化。`);if(x.missing_saved_files)notes.push(`${x.missing_saved_files} 个原选文件不存在，未恢复。`);treeRestoreNote=notes.join(' ');let host=$('targettree');host.classList.remove('muted');host.innerHTML='';host.append(makeTreeNode(x.tree));refreshAllFolderStates();if(x.truncated)$('treestatus').innerHTML='<span class="error">文件树超过 5000 项，已截断；请进入更具体的 BG 文件夹。</span>'}catch(e){setUIMessage($('treestatus'),e.uiMessage||{text:e.message},'error')}}
// The server returns data and stable identifiers; the browser owns localized
// presentation.  Keeping the payload lets a language switch redraw the same
// selection without another folder read or a change to selection semantics.
function localizeMaterialFlowControls(){
  let confirm=$('confirmmaterials'),report=$('viewscanreport'),backdrop=$('scanbackdrop');
  if(confirm&&!busy)confirm.textContent=t('materials.confirm_selected');
  if(report)report.textContent=t('scan.report');
  if(backdrop){
    backdrop.setAttribute('aria-label',t('scan.report.title'));
    let title=backdrop.querySelector('.scan-drawer-head b'),note=backdrop.querySelector('.scan-drawer-head .muted');
    if(title)title.textContent=t('scan.report.title');
    if(note)note.textContent=t('scan.report.local');
  }
}
function updateMaterialFlowButtonsForLanguage(){
  let confirm=$('confirmmaterials'),report=$('viewscanreport');
  if(confirm)confirm.disabled=treeFileCount()===0;
  if(report){report.disabled=!lastScanReport;report.textContent=t('scan.report')}
}
function setScanReportAvailableForLanguage(report){lastScanReport=report||null;updateMaterialFlowButtonsForLanguage()}
function clearTargetTreeForLanguage(){
  savedTargetSelection=new Set();treeRestoreNote='';scannedSelection='';lastTargetTreePayload=null;setScanReportAvailableForLanguage(null);
  setUIMessage($('targettree'),{message_key:'tree.placeholder'});$('targettree').classList.add('muted');$('treestatus').textContent='';updateMaterialFlowButtonsForLanguage();
}
function updateTreeStatusForLanguage(){
  let count=treeFileCount(),signature=selectedTargetPaths().sort().join('|');
  if(scannedSelection&&signature!==scannedSelection)setScanReportAvailableForLanguage(null);
  $('treestatus').textContent=(count?t('tree.selected',{count}):t('tree.none'))+(treeRestoreNote?' '+treeRestoreNote:'');
  updateMaterialFlowButtonsForLanguage();
}
function makeTreeNodeForLanguage(node,depth=0){
  if(node.type==='folder'){
    let details=document.createElement('details');details.open=depth<1;let summary=document.createElement('summary');let box=document.createElement('input');
    box.type='checkbox';box.className='tree-folder';box.addEventListener('click',e=>e.stopPropagation());box.addEventListener('change',()=>{materialDraftDirty=true;details.querySelectorAll('input.tree-file:not(:disabled)').forEach(x=>x.checked=box.checked);refreshAllFolderStates()});
    let label=document.createElement('label');label.textContent='📁 '+node.name;summary.append(box,label);details.append(summary);
    let children=document.createElement('div');children.className='tree-children';(node.children||[]).forEach(child=>children.append(makeTreeNodeForLanguage(child,depth+1)));details.append(children);return details;
  }
  let row=document.createElement('div');row.className='tree-file'+(node.supported?'':' unsupported');let box=document.createElement('input');
  box.type='checkbox';box.className='tree-file';box.dataset.path=node.path;box.checked=!!node.supported&&savedTargetSelection.has(node.relative);box.disabled=!node.supported;box.addEventListener('change',()=>{materialDraftDirty=true;refreshAllFolderStates()});
  let label=document.createElement('label'),role=node.material_role_label?` · ${tr(node.material_role_label)}`:'',size=(node.bytes/1024/1024).toFixed(node.bytes<1024*1024?2:1);
  label.textContent='📄 '+node.name+(node.supported?` · ${size} MB${role}${node.recommended?'':' · '+t('tree.not_recommended')}`:` · ${t('tree.unsupported')}${role}`);row.append(box,label);return row;
}
function renderTargetTreeForLanguage(x){
  lastTargetTreePayload=x;let host=$('targettree');host.classList.remove('muted');host.innerHTML='';host.append(makeTreeNodeForLanguage(x.tree));refreshAllFolderStates();
  if(x.truncated)$('treestatus').innerHTML='<span class="error">'+t('tree.truncated')+'</span>';
}
function captureTargetTreeSelection(){
  if(!lastTargetTreePayload?.tree)return;
  let selected=new Set(selectedTargetPaths()),relative=new Set();
  (function visit(node){if(node.type==='file'){if(selected.has(node.path))relative.add(node.relative);return}(node.children||[]).forEach(visit)})(lastTargetTreePayload.tree);
  savedTargetSelection=relative;
}
async function loadTargetTreeForLanguage(){
  let target=$('targetpath').value.trim();
  if(!target){$('treestatus').innerHTML='<span class="error">'+t('tree.path_required')+'</span>';return}
  try{
    setUIMessage($('treestatus'),{message_key:'tree.loading'});let x=await api('/api/target-tree?target='+encodeURIComponent(target));savedTargetSelection=new Set(x.saved_selection||[]);
    let notes=[];
    if(savedTargetSelection.size)notes.push(t('tree.restored',{count:savedTargetSelection.size}));
    else{savedTargetSelection=new Set(recommendedTreePaths(x.tree));notes.push(t('tree.default_selection',{count:savedTargetSelection.size}));}
    if(x.changed_saved_files)notes.push(t('tree.changed',{count:x.changed_saved_files}));
    if(x.missing_saved_files)notes.push(t('tree.missing',{count:x.missing_saved_files}));
    treeRestoreNote=notes.join(' ');renderTargetTreeForLanguage(x);
  }catch(e){setUIMessage($('treestatus'),e.uiMessage||{text:e.message},'error')}
}
// Compatibility assignments ensure every old event handler uses the localized
// renderers while preserving the original public function names.
updateMaterialFlowButtons=updateMaterialFlowButtonsForLanguage;
setScanReportAvailable=setScanReportAvailableForLanguage;
clearTargetTree=clearTargetTreeForLanguage;
updateTreeStatus=updateTreeStatusForLanguage;
makeTreeNode=makeTreeNodeForLanguage;
loadTargetTree=loadTargetTreeForLanguage;
function selectedTargetPaths(){return [...$('targettree').querySelectorAll('input.tree-file:checked')].map(x=>x.dataset.path)}
async function analyzeTarget(){if(!allowRuleDraftTransition())return;let confirm=$('confirmmaterials');if(confirm){confirm.disabled=true;confirm.textContent=rt('scan.reading')}try{let target=$('targetpath').value.trim();let selected=selectedTargetPaths();if($('targettree').querySelector('.tree-file')&&!selected.length)throw Error(t('materials.selection_required'));let x=await api('/api/target',{method:'POST',body:JSON.stringify({target,codebook:$('codebook').value,selected_paths:selected})});scannedSelection=selected.slice().sort().join('|');materialDraftDirty=false;clearResultPanels();await loadHistory();renderStatus(x.status);$('bgstatus').textContent=t(x.classification?'materials.confirmed_bg':'materials.confirmed_normal',{kind:tr(x.target_kind),count:x.sources});renderScanReport(x);$('coveragestatus').textContent=rt('material.updated');loadDocs();loadCacheAudit()}catch(e){setUIMessage($('bgstatus'),e.uiMessage||{text:e.message},'error')}finally{if(confirm)confirm.textContent=t('materials.confirm_selected');updateMaterialFlowButtons()}}
async function prepareCoverage(full=false){if(busy)return;busy=true;setUIMessage($('coveragestatus'),{message_key:full?'coverage.preparing_full':'coverage.preparing'});try{let x=await api('/api/coverage',{method:'POST',body:JSON.stringify({full})});renderCoverageReport(x);renderStatus(await api('/api/status'))}catch(e){setUIMessage($('coveragestatus'),{message_key:'error.operation_failed',params:{detail:e.uiMessage||{text:e.message}}},'error')}finally{busy=false}}
async function clearBg(){if(!allowRuleDraftTransition())return;try{renderStatus(await api('/api/bg',{method:'DELETE'}));setUIMessage($('bgstatus'),{message_key:'bg.exited'})}catch(e){$('bgstatus').textContent=e.message}}
const compareOptions=[['claude-haiku-5-5','Claude Haiku 5.5'],['claude-sonnet-5-5','Claude Sonnet 5.5'],['claude-opus-5','Claude Opus 5'],['gemini-3.5-flash-lite','Gemini 3.5 Flash-Lite'],['gemini-2.5-pro','Gemini 2.5 Pro'],['gemini-2.5-flash','Gemini 2.5 Flash'],['deepseek-r1-0528-maas','DeepSeek R1 (0528)'],['llama-3.3-70b-instruct-maas','Llama 3.3 70B'],['glm-5-maas','GLM-5']];
function renderCompareSlots(){let host=$('comparemodels');host.innerHTML=compareSlots.map((slot,index)=>{let options='<option value="">选择模型…</option>'+compareOptions.map(([value,label])=>'<option value="'+escAttr(value)+'" '+(slot.value===value?'selected':'')+'>'+label+'</option>').join('')+'<option value="__custom__" '+(slot.value==='__custom__'?'selected':'')+'>其他：手动输入 Model ID…</option>';return '<div class="field"><label>对比模型 '+(index+1)+'</label><div class="row"><select id="cmpsel'+index+'" onchange="changeCompareModel('+index+')">'+options+'</select>'+(index>0?'<button class="ghost" onclick="removeCompareModel('+index+')">×</button>':'')+'</div>'+(slot.value==='__custom__'?'<input id="cmpcustom'+index+'" value="'+escAttr(slot.custom||'')+'" placeholder="输入准确的 Bosch Farm Model ID" oninput="compareSlots['+index+'].custom=this.value">':'')+'</div>'}).join('');let add=$('addcompare');add.disabled=compareSlots.length>=4;add.textContent=compareSlots.length>=4?'最多 4 个模型':'＋ 添加对比模型';if(compareSlots.length>=4)$('comparestatus').textContent='已达到最多 4 个对比模型。'}
function changeCompareModel(index){let select=$('cmpsel'+index);compareSlots[index].value=select.value;if(select.value!=='__custom__')compareSlots[index].custom='';renderCompareSlots();if(select.value==='__custom__')setTimeout(()=>$('cmpcustom'+index).focus(),0)}
function addCompareModel(){if(compareSlots.length>=4){$('comparestatus').textContent='最多只能同时对比 4 个模型。';return}compareSlots.push({value:'',custom:''});renderCompareSlots();$('cmpsel'+(compareSlots.length-1)).focus()}
function removeCompareModel(index){compareSlots.splice(index,1);renderCompareSlots();$('comparestatus').textContent=''}
function selectedCompareModels(){return compareSlots.map((slot,index)=>slot.value==='__custom__'?$('cmpcustom'+index).value.trim():slot.value).filter(Boolean)}
function renderComparisonForLanguage(record){
  $('comparison-result')?.remove();let x=record.data,box=document.createElement('section');box.id='comparison-result';box.className='comparison';
  box.innerHTML='<div class="message assistant"><b>'+t('compare.title')+'</b><br>'+t('compare.question')+'：'+esc(record.question)+'<br><span class="muted">'+t('compare.same_evidence')+'：'+(x.sources||[]).map(esc).join(' · ')+'</span></div><div class="comparison-grid"></div>';
  let grid=box.querySelector('.comparison-grid');for(let r of x.results||[]){let card=document.createElement('article');card.className='card';if(!r.ok){card.innerHTML='<b>'+esc(r.requested_model)+'</b><p class="error">'+t('compare.request_failed')+'</p><div class="muted">'+esc(r.error_message?uiCopy(r.error_message):r.error||t('compare.unknown_error'))+'</div>';grid.append(card);continue}let u=r.usage||{},cost=usageCost(u),classification=r.classification?'<div class="chip">'+t('classification.verified')+'：'+esc(r.classification.label)+' · '+esc(r.classification.confidence)+'</div>':'';card.innerHTML='<b>'+esc(r.model_response)+'</b>'+(r.model_response!==r.requested_model?'<div class="muted">'+t('compare.requested_model')+'：'+esc(r.requested_model)+'</div>':'')+'<div class="muted ok">'+t('compare.success')+' · Token '+usageNumber(u.input)+' / '+usageNumber(u.output)+' · '+cost+'</div>'+classification+'<hr><div class="answer"></div>'+(r.notices?.length?'<div class="muted">'+(r.notice_messages||r.notices).map(value=>esc(uiCopy(value))).join('<br>')+'</div>':'');card.querySelector('.answer').textContent=r.answer;grid.append(card)}$('chat').append(box);
}
async function compareModels(){if(busy)return;if(lastStatusSnapshot?.context_issue){uiMessageNode({message_key:'context.reconfirm'});return;}if(materialDraftDirty){uiMessageNode({message_key:'materials.reconfirm'});return;}let q=$('question').value.trim()||lastQuestion;if(!q){setUIMessage($('comparestatus'),{message_key:'compare.question_required'},'error');return}let models=selectedCompareModels();if(models.length<2||models.length>4||new Set(models).size!==models.length){setUIMessage($('comparestatus'),{message_key:'compare.models_required'},'error');return}busy=true;lastQuestion=q;setUIMessage($('comparestatus'),{message_key:'compare.running',params:{count:models.length}});let wait=uiMessageNode({message_key:'compare.in_progress',params:{models:models.join(' · ')}});try{let x=await api('/api/compare',{method:'POST',body:JSON.stringify({question:q,models})});wait.remove();lastComparison={question:q,data:x};renderComparisonForLanguage(lastComparison);renderStatus(x.usage);setUIMessage($('comparestatus'),{message_key:'compare.complete'},'ok')}catch(e){wait.uiData={message_key:'error.operation_failed',params:{detail:e.uiMessage||{text:e.message}}};wait.textContent=uiCopy(wait.uiData);wait.classList.add('error');setUIMessage($('comparestatus'),e.uiMessage||{text:e.message},'error')}finally{busy=false;$('chat').scrollTop=1e9}}
function processingCard(){let card=document.createElement('section');card.className='message assistant';card.style.border='1px solid #334155';card.innerHTML='<b data-process-title>'+rt('model.processing')+'</b><div class="muted" data-process-text>'+rt('model.connecting')+'</div><div style="height:7px;background:#0b1220;border-radius:8px;overflow:hidden;margin-top:9px"><div data-process-bar style="height:100%;width:4%;background:#38bdf8;transition:width .25s ease"></div></div>';$('chat').append(card);return registerUI(card,'processing',null)}
function updateProcessing(card,event){let text=card.querySelector('[data-process-text]'),bar=card.querySelector('[data-process-bar]');card.uiData=event;text.textContent=uiCopy(event)||rt('model.waiting');if(typeof event.percent==='number')bar.style.width=Math.max(4,Math.min(100,event.percent))+'%';if(event.phase==='complete'){card.style.borderColor='#22c55e';bar.style.background='#22c55e'}}
function showChatResult(x){message(x.answer);if(x.classification)$('chat').append(classificationCard(x.classification));let summary=coverageSummaryCard(x.coverage_summary);if(summary)$('chat').append(summary);if(x.reasoning){let d=document.createElement('details');d.className='reason';d.innerHTML='<summary>'+t('model.reasoning')+'</summary><pre></pre>';d.querySelector('pre').textContent=x.reasoning;registerUI(d,'reasoning',x.reasoning);$('chat').append(d)}if(x.notices?.length){let data=x.notice_messages||x.notices;registerUI(message(data.map(uiCopy).join('\n'),'assistant'),'notices',data)}renderEvidenceSources(x.sources,x.dfc_evidence);$('changes').innerHTML=x.changes?.length?x.changes.map(c=>`<div class="card"><b>${esc(c.path)}</b><br>${esc(c.reason)}<pre class="diff">${esc(c.diff)}</pre></div>`).join('')+'<button data-plan-id="'+escAttr(x.plan_id||'')+'" onclick="apply(this.dataset.planId,this)">'+t('changes.apply')+'</button>':t('changes.none');if(!x.changes?.length)setUIMessage($('changes'),{message_key:'changes.none'});if(x.changes?.length){let review=$('changes').cloneNode(true);review.removeAttribute('id');review.className='message assistant change-plan';$('chat').append(review)}$('analysisexport').innerHTML=x.can_export_bg?'<button class="ghost" onclick="exportBgAnalysis()">'+t('export.assembly')+'</button>':t('export.assembly_unavailable');if(!x.can_export_bg)setUIMessage($('analysisexport'),{message_key:'export.assembly_unavailable'});renderUsageDetail(x.turn_usage,x.model_response);renderStatus(x.usage)}
let activeChat=null;
async function stopChat(){
  if(!activeChat||activeChat.stopping)return;
  activeChat.stopping=true;$('cancelchat').disabled=true;
  activeChat.controller.abort();
  if(activeChat.id)try{await api('/api/chat/cancel',{method:'POST',body:JSON.stringify({request_id:activeChat.id})})}catch{}
}
async function settleChat(task,wait){
  if(!task.id)return null;
  let failures=0;
  while(true){
    try{
      let response=await fetch('/api/chat/task/'+encodeURIComponent(task.id));
      if(response.status===404)return null;
      let status=await readApiResponse(response);
      if(status.done)return status;
      failures=0;
      updateProcessing(wait,{message_key:'stream.stopping'});
    }catch{if(++failures>=3)return null}
    await new Promise(resolve=>setTimeout(resolve,100));
  }
}
async function chat(){
  if(busy||!$('question').value.trim())return;
  if(lastStatusSnapshot?.context_issue){message(t('context.reconfirm'));return}
  if(materialDraftDirty){message(t('materials.reconfirm'));return}
  busy=true;let task={controller:new AbortController(),id:crypto.randomUUID().replaceAll('-',''),stopping:false};activeChat=task;$('cancelchat').disabled=false;
  let q=$('question').value;lastQuestion=q;$('question').value='';message(q,'user');
  let wait=processingCard(),buffer='',result=null,error=null,preview=null,previewText=null,failureText='';
  function resetPreview(){preview?.remove();preview=null;previewText=null}
  function appendPreview(text){
    if(!preview){preview=message('');preview.classList.add('answer-preview');registerUI(preview,'preview',null);let label=document.createElement('div');label.className='muted';label.textContent=t('stream.preview');let body=document.createElement('div');body.className='preview-text';body.style.whiteSpace='pre-wrap';previewText=document.createTextNode('');body.append(previewText);preview.append(label,body)}
    previewText.appendData(text);
  }
  try{
    let response=await fetch('/api/chat/stream',{method:'POST',headers:{'Content-Type':'application/json'},signal:task.controller.signal,body:JSON.stringify({question:q,request_id:task.id,require_classification:$('answermode')?.value!=='explanation'})});
    if(!response.ok)await readApiResponse(response);
    let reader=response.body.getReader(),decoder=new TextDecoder();
    while(true){
      let part=await reader.read();if(part.done)break;
      buffer+=decoder.decode(part.value,{stream:true});
      let blocks=buffer.split('\n\n');buffer=blocks.pop();
      for(let block of blocks){
        let line=block.split('\n').find(item=>item.startsWith('data: '));if(!line)continue;
        let event=JSON.parse(line.slice(6));
        if(event.type==='start')task.id=event.request_id;
        else if(event.type==='progress')updateProcessing(wait,event);
        else if(event.type==='answer_reset')resetPreview();
        else if(event.type==='answer_delta')appendPreview(event.text);
        else if(event.type==='result')result=event.data;
        else if(event.type==='error'){error=event;throw Error(uiCopy(event)||event.message||t('model.failed'))}
      }
    }
    if(!result)throw Error(t('api.no_result'));
    resetPreview();updateProcessing(wait,{phase:'complete',message_key:'model.complete',percent:100});showChatResult(result);
  }catch(e){
    resetPreview();task.controller.abort();
    if(task.id)try{await api('/api/chat/cancel',{method:'POST',body:JSON.stringify({request_id:task.id})})}catch{}
    let code=task.stopping?'cancelled':error?.code;
    wait.uiData={message_key:code==='cancelled'?'stream.cancelled':code==='timeout'?'stream.timeout':code==='limit'?'stream.limit':'error.operation_failed',params:{detail:error?.message_key?error:e.uiMessage||{text:e.message}}};
    failureText=uiCopy(wait.uiData);
    wait.querySelector('[data-process-text]').textContent=failureText;
    if(code!=='cancelled')wait.classList.add('error');
  }finally{
    resetPreview();let status=await settleChat(task,wait);
    if(task.stopping)updateProcessing(wait,{message_key:status?.state==='completed'?'stream.completed':'stream.cancelled'});
    else if(failureText)wait.querySelector('[data-process-text]').textContent=failureText;
    activeChat=null;busy=false;$('cancelchat').disabled=true;$('chat').scrollTop=1e9;
  }
}
async function exportSession(){try{let x=await api('/api/export/session',{method:'POST'});setUIMessage($('sessionexport'),{message_key:'export.complete',params:{path:x.path}},'ok')}catch(e){setUIMessage($('sessionexport'),e.uiMessage||{text:e.message},'error')}}
async function exportBgAnalysis(){try{let x=await api('/api/export/bg-analysis',{method:'POST'});setUIMessage($('analysisexport'),{message_key:'export.complete',params:{path:x.path}},'ok')}catch(e){setUIMessage($('analysisexport'),e.uiMessage||{text:e.message},'error')}}
function esc(s){let e=document.createElement('div');e.textContent=s;return e.innerHTML}function escAttr(s){return esc(s).replace(/"/g,'&quot;').replace(/'/g,'&#39;')}async function apply(planId,button){let review=button?.closest('.change-plan')||$('changes');if(!confirm(t('changes.confirm')))return;try{let x=await api('/api/apply',{method:'POST',body:JSON.stringify({confirmed:true,plan_id:planId})});review.innerHTML='<span class="ok">'+t('apply.complete',{count:x.applied})+'</span>';message(t('apply.message',{count:x.applied}))}catch(e){setUIMessage(review,e.uiMessage||{text:e.message},'error')}}

let materialDraftDirty=false;
function clearResultPanels(){lastSourcesSnapshot=null;lastUsageSnapshot=null;lastComparison=null;lastCoverageReport=null;lastCacheAudit=null;setUIMessage($('sources'),{message_key:'evidence.none'});setUIMessage($('changes'),{message_key:'changes.none'});setUIMessage($('analysisexport'),{message_key:'export.assembly_unavailable'});setUIMessage($('usagedetail'),{message_key:'usage.unavailable'});setUIMessage($('coveragestatus'),{message_key:'material.updated'});}
let ruleEditState=null;
function ruleEditorBinding(profile=lastCodebookWorkspaceProfile){
  return JSON.stringify([lastStatusSnapshot?.workspace,lastStatusSnapshot?.session_name,profile?.source_path,profile?.sha256,profile?.version]);
}
function captureRuleEditor(){
  let field=$('ruleeditor');if(!ruleEditState||!field)return;
  Object.assign(ruleEditState,{text:field.value,dirty:field.value!==ruleEditState.initialText,start:field.selectionStart,end:field.selectionEnd,direction:field.selectionDirection,scroll:field.scrollTop});
}
function allowRuleDraftTransition(){
  captureRuleEditor();
  if(!ruleEditState)return true;
  if(ruleEditState.saving)return false;
  if(ruleEditState.dirty&&!confirm(t('rules.discard_confirm')))return false;
  ruleEditState=null;return true;
}
function renderRuleEditor(){
  if(!ruleEditState)return;
  captureRuleEditor();
  if(!$('ruleeditor')){
    $('chat').className='chat codebook-workspace';$('composer').style.display='none';
    $('chat').innerHTML='<section class="workspace-inner"><h1 data-rule-copy="rules.edit"></h1><p data-rule-copy="rules.edit_help"></p><textarea id="ruleeditor" style="width:100%;min-height:380px"></textarea><div class="row"><button id="rulesave" onclick="saveCodebookDraft()" data-rule-copy="rules.save_draft"></button><button class="ghost" onclick="cancelRuleDraft()" data-rule-copy="rules.cancel"></button></div><div id="ruledirty" class="muted"></div><div id="ruleediterror" class="error"></div></section>';
    let field=$('ruleeditor');field.value=ruleEditState.text;field.setSelectionRange(ruleEditState.start,ruleEditState.end,ruleEditState.direction);field.scrollTop=ruleEditState.scroll;
    for(let event of ['input','select','keyup','click','blur','scroll'])field.addEventListener(event,()=>{captureRuleEditor();updateRuleEditorCopy()});
  }
  updateRuleEditorCopy();
}
function updateRuleEditorCopy(){
  if(!ruleEditState||!$('ruleeditor'))return;
  for(let node of $('chat').querySelectorAll('[data-rule-copy]'))node.textContent=t(node.dataset.ruleCopy);
  $('ruleeditor').setAttribute('aria-label',t('rules.edit'));
  $('ruledirty').textContent=t(ruleEditState.saving?'rules.saving':ruleEditState.dirty?'rules.unsaved':'rules.saved_copy');
  $('rulesave').disabled=!!ruleEditState.saving;
  $('ruleeditor').readOnly=!!ruleEditState.saving;
  $('ruleediterror').textContent=ruleEditState.error?uiCopy(ruleEditState.error):'';
}
function editCodebookDraft(){
  if(ruleEditState){renderRuleEditor();return}
  let profile=lastCodebookWorkspaceProfile;if(!profile)return;
  let text=JSON.stringify(profile.draft,null,2);
  ruleEditState={text,initialText:text,dirty:false,binding:ruleEditorBinding(profile),start:0,end:0,direction:'none',scroll:0,error:null,saving:false};
  renderRuleEditor();
}
function cancelRuleDraft(){
  if(ruleEditState?.saving)return;
  if(!allowRuleDraftTransition())return;
  showCodebookWorkspace(lastCodebookWorkspaceProfile);
}
async function saveCodebookDraft(){
  captureRuleEditor();let editing=ruleEditState;if(!editing||editing.saving)return;
  if(editing.binding!==ruleEditorBinding()){editing.error={message_key:'rules.context_changed'};updateRuleEditorCopy();return}
  let draft;try{draft=JSON.parse(editing.text)}catch(e){editing.error={message_key:'rules.invalid_json',params:{detail:e.message}};updateRuleEditorCopy();return}
  if(!confirm(t('rules.save_confirm')))return;
  editing.saving=true;editing.error=null;updateRuleEditorCopy();
  try{
    let profile=await api('/api/codebook/edit',{method:'POST',body:JSON.stringify({draft,confirmed:true,profile_version:lastCodebookWorkspaceProfile?.version})});
    ruleEditState=null;renderCodebookStatus(profile);showCodebookWorkspace(profile);renderStatus(await api('/api/status'));
  }catch(e){editing.error=e.uiMessage||{message_key:'rules.save_failed',params:{detail:e.message}}}
  finally{editing.saving=false;updateRuleEditorCopy()}
}
window.addEventListener('beforeunload',event=>{captureRuleEditor();if(ruleEditState?.dirty){event.preventDefault();event.returnValue=''}});

</script></body></html>'''

# Embed the packaged catalog without introducing an HTTP endpoint or network call.
HTML = HTML.replace('__WORKBENCH_I18N_JSON__', catalog_script_json())


def main() -> None:
    config = STARTUP_CONFIG
    try:
        with FARM_ENVIRONMENT.use(config.env_file, load_dotenv, explicit=config.env_explicit):
            validate_farm_endpoint(config.env_file)
            check_state_directory(app_state_home())
            check_port(config.port)
        print(f"Bosch Local Workbench: http://{HOST}:{config.port}", flush=True)
        uvicorn.run(app, host=HOST, port=config.port)
    except StartupError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None
    except (OSError, SystemExit) as exc:
        if isinstance(exc, SystemExit) and exc.code in (None, 0):
            raise
        # The port probe is advisory; another process may bind before Uvicorn.
        print(str(StartupError('startup.server_failed', port=config.port)), file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()

