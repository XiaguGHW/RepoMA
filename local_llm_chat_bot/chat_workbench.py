"""Local browser workbench for the Bosch Farm code/document chat.

Run only on 127.0.0.1.  The browser is a local UI: paths, indexes, source
files, credentials and session data stay on the computer that starts it.
"""
from __future__ import annotations

from workbench_startup import (StartupConfig, StartupError, FarmEnvironment, HOST, bootstrap,
                               check_state_directory, check_port, install_command, open_browser_when_ready,
                               running_workbench, workbench_url)


import difflib
import webbrowser
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
from datetime import datetime
from pathlib import Path
from typing import Any

STARTUP_CONFIG = bootstrap() if __name__ == '__main__' else StartupConfig()
FARM_ENVIRONMENT = FarmEnvironment()

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
    import uvicorn

    from release_safety import (safe_error, summarize_usage, context_state_error, valid_rule_profile)
    from dotenv import load_dotenv
    from workbench_i18n import catalog_script_json, UIMessage, localize_message
    from workbench_frontend import load_frontend_html
    from workbench_messages import (UIRequestError, UIValidationError, error_copy, message_payload, redact_value,
                                    ui_message)
    from workbench_models import (ApplyRequest, BGRequest, CacheConfirmRequest, CacheFileRequest, ChatCancelRequest,
                                  ChatRequest, CodebookEditRequest, CodebookPrepareRequest, CompareRequest,
                                  CoverageRequest, LanguageRequest, ModelSwitchRequest, ModelTestRequest,
                                  OperationCancelRequest, PathRequest, SessionDeleteRequest, SessionOpenRequest,
                                  SessionPinRequest, SessionRenameRequest, Setup, TargetRequest)
    from workbench_model_calls import (accounted_model_call, check_answer_size, check_request, commit_answer,
                                       connector_failure, require_model_success)
    from workbench_rules import (CODEBOOK_FILE_TYPES, CODEBOOK_JOB_LOG_LIMIT, CODEBOOK_JSON_REPAIR_SYSTEM,
                                 CODEBOOK_MERGE_SYSTEM, CODEBOOK_PAGE_SYSTEM, CODEBOOK_RECOMMENDED_MODEL,
                                 CODEBOOK_SECTION_SYSTEM, CodebookParseBudget, CodebookPrepareError,
                                 classify_model_failure, codebook_notes_text, codebook_piece_request,
                                 codebook_text_units, codebook_unit_key, codebook_unit_label, json_error_detail,
                                 load_codebook_note_cache, local_timestamp, namespace_duplicate_rule_ids,
                                 nonpaged_references, parse_codebook_note, rule_id_conflicts, split_codebook_piece,
                                 with_blocks)
    from workbench_materials import (BG_DOSSIER_CACHE_VERSION, BG_DOSSIER_TOKENS, MATERIAL_GROUP_FORMAT,
                                     MATERIAL_GROUP_NOTE_VERSION, MATERIAL_GROUP_TOKENS, MATERIAL_KIND_LINE,
                                     MATERIAL_MERGE_FORMAT, MATERIAL_MERGE_TOKENS, MATERIAL_SUMMARY_CACHE_VERSION,
                                     MATERIAL_SUMMARY_SYSTEM, PREREAD_VISUAL_INSTRUCTION, bg_dossier_identity,
                                     coverage_summary_for_answer, document_ocr_audit, document_pages,
                                     guess_document_kind, material_folder, material_retry_limit, model_document_kind,
                                     preread_groups, reading_hints, reading_plan, scope_message,
                                     selected_reading_chunks, selected_target_files, split_material_group,
                                     summary_groups, target_tree, traceable_evidence)
    from workbench_classification import (ANSWER_OUTPUT_TOKENS, ANSWER_RETRY_OUTPUT_TOKENS,
                                          ANSWER_SHORTEN_INSTRUCTION, ClassificationValidationError,
                                          classification_scope, image_group_notices, relevant_codebook_page_evidence,
                                          validated_model_action)
    from code_chat_agent import (PricingCatalog, ProjectState, SYSTEM, ensure_relative,
                                 excerpt, prompt_for, safe_name, sha256)
    from local_document_library import (LocalDocumentLibrary, SUPPORTED_DOCUMENT_EXTENSIONS, TextDecodingError,
                                        decode_text_bytes, material_role_label, MAX_CHUNKS_PER_DOCUMENT)
    from llm_connector_with_prompt_caching import LLMConnector, farm_base_url
    from request_runtime import (RequestControl, RequestStopped, RequestCancelled, RequestTimedOut,
                                 ResponseLimitExceeded, AnswerPreview, looks_like_action)
except ImportError as exc:
    if __name__ != '__main__':
        raise
    print('Cannot import runtime module: ' + str(exc.name or 'required dependency') +
          '\nKeep all downloaded program files together. Repair this Python environment with:\n' + install_command(), file=sys.stderr)
    raise SystemExit(1) from None


app = FastAPI(title="Bosch Assembly Assistant", docs_url=None, redoc_url=None)
LOCK = threading.RLock()
ACTIVE: dict[str, Any] = {}
# A streamed request runs in a background thread.  Keep an explicit marker in
# addition to LOCK so a second browser action cannot replace ACTIVE while that
# request is queued for the lock or is using a captured session context.
MODEL_WORK_IN_PROGRESS = threading.Event()
CHAT_TASK_GUARD = threading.Lock()
# Serializes small settings writes that may run while LOCK is held by model work.
SETTINGS_GUARD = threading.Lock()
CHAT_TASK: dict[str, Any] = {}
# Synchronous long model operations (Codebook preparation, coverage, comparison,
# dossier rebuild) that a browser Stop can cancel by request_id.
OPERATION_GUARD = threading.Lock()
OPERATIONS: dict[str, RequestControl] = {}
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


APP_NAME = "Bosch_Assembly_Assistant"
# Data lives next to the program: wherever the folder is unpacked, the
# launcher and the program find it there.  WORKBENCH_STATE_DIR can override.
LEGACY_STATE_HOME = Path(__file__).resolve().parent / "AI_Bot_State"
_STATE_HOME: Path | None = None


def resolve_state_home(environ=None) -> Path:
    environ = os.environ if environ is None else environ
    override = str(environ.get("WORKBENCH_STATE_DIR") or "").strip().strip('"')
    return Path(override).expanduser().resolve() if override else LEGACY_STATE_HOME


def app_state_home() -> Path:
    global _STATE_HOME
    if _STATE_HOME is None:
        _STATE_HOME = resolve_state_home()
    return _STATE_HOME


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
            "language": normalize_language(data.get("language", "de")),
        } if isinstance(data, dict) else {"workspace": "", "session": "default", "model": "claude-haiku-5-5", "language": "de"}
    except (OSError, ValueError):
        return {"workspace": "", "session": "default", "model": "claude-haiku-5-5", "language": "de"}


def normalize_language(value: Any) -> str:
    return str(value or "de").lower() if str(value or "de").lower() in {"zh", "en", "de"} else "de"


def save_workbench_settings(workspace: Path, session_name: str, model: str, language: str = "zh") -> None:
    write_json_atomically(workbench_settings_path(), {
        "workspace": str(workspace), "session": session_name,
        "model": canonical_model_id(model), "language": normalize_language(language),
    })


def session() -> dict[str, Any]:
    if not ACTIVE:
        raise HTTPException(400, ui_message(ACTIVE, 'error.workspace_required'))
    return ACTIVE


def ui_state(data, value):
    keys = {'ok': 'state.ok', 'not_needed': 'state.not_needed', 'partial': 'state.partial', 'not_requested': 'state.not_requested', 'unknown': 'state.unknown',
            'not_applicable': 'state.not_applicable', 'not applicable': 'state.not_applicable',
            '已完成': 'state.complete', '部分完成': 'state.partial', '不需要（原生文字页）': 'state.native_text',
            '不适用（无页码文档）': 'state.not_applicable', 'not applicable to DOCX': 'state.not_applicable'}
    return ui_message(data, keys[value]) if value in keys else str(value or '—')


@app.exception_handler(HTTPException)
async def localized_http_error(request: Request, error: HTTPException):
    language = request.headers.get('X-Workbench-Language') or ACTIVE.get('language', 'de')
    detail = error_copy(error, {'language': language})
    return JSONResponse(status_code=error.status_code,
                        content={'detail': str(detail), **message_payload(detail)}, headers=error.headers)


def protect_configuration(state: ProjectState, env_file: Any = None) -> ProjectState:
    """Keep every configuration file the app reads outside the model's file access."""
    state.protect(env_file, STARTUP_CONFIG.env_file, Path(__file__).resolve().parent / ".env")
    return state


def context_token(data: dict[str, Any]) -> str:
    """Opaque binding of one session directory and its material/rule revision."""
    state = data["state"]
    identity = f"{state.root}\0{state.data.get('context_revision', '')}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]


def ensure_current_page() -> None:
    """Reject a request made from a page that shows an older session/context."""
    expected = PAGE_CONTEXT.get()
    if expected and ACTIVE and expected != context_token(ACTIVE):
        raise HTTPException(409, ui_message(ACTIVE, 'context.stale_page'), headers={"X-Workbench-Stale": "1"})


def reject_context_change_while_processing() -> None:
    """Keep the selected session, model and material scope stable per request."""
    if MODEL_WORK_IN_PROGRESS.is_set():
        raise HTTPException(409, ui_message(ACTIVE, 'error.busy'))


def begin_model_work(request_id: str = "") -> dict[str, Any]:
    """Reserve the single model slot and capture its complete request context.

    A nonempty request_id makes a synchronous operation stoppable through
    /api/operation/cancel; callers release it with end_model_work().
    """
    if not LOCK.acquire(blocking=False):
        raise HTTPException(409, ui_message(ACTIVE, 'error.busy'))
    try:
        if MODEL_WORK_IN_PROGRESS.is_set():
            raise HTTPException(409, ui_message(ACTIVE, 'error.busy'))
        ensure_current_page()
        data = dict(session())
        data["request_control"] = RequestControl()
        data["cancel_event"] = data["request_control"].cancel_event
        data["operation_id"] = request_id
        if request_id:
            with OPERATION_GUARD:
                OPERATIONS[request_id] = data["request_control"]
        MODEL_WORK_IN_PROGRESS.set()
        return data
    finally:
        LOCK.release()


def end_model_work(data: dict[str, Any]) -> None:
    """Release a synchronous operation only after its work returned or raised."""
    with OPERATION_GUARD:
        OPERATIONS.pop(data.get("operation_id") or "", None)
    MODEL_WORK_IN_PROGRESS.clear()


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
        "unpriced_detail": usage.get("unpriced_detail", {}),
        "pricing_source": getattr(data.get("pricing"), "source", {"kind": "bundled"}),
        "data_folder": str(app_state_home()),
        "bg_context": state.data.get("bg_context"),
        "context_issue": context_issue(data),
        "context_revision": state.data.get("context_revision", ""),
        "last_classification": last_classification_summary(state),
    }


def last_classification_summary(state: ProjectState) -> dict[str, Any] | None:
    """The latest validated classification of the current material range, if any."""
    record = state.data.get("last_bg_analysis")
    classification = record.get("classification") if isinstance(record, dict) else None
    if not isinstance(classification, dict) or not classification.get("label"):
        return None
    return {"label": str(classification["label"]), "confidence": str(classification.get("confidence") or ""),
            "created_at": str(record.get("created_at", "")),
            "current": record.get("context_revision") == state.data.get("context_revision", "")}


def session_list_item(root: Path) -> dict[str, Any]:
    """Small, local-only metadata for the ChatGPT-style session sidebar."""
    state_file = root / "state.json"
    data: dict[str, Any] = {}
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    if not isinstance(data, dict):
        data = {}
    title = str(data.get("sidebar_title") or root.name)
    title_key = "session.new_title" if (not data.get("sidebar_title") and root.name.startswith("chat_")
                                      or is_new_session_title(title)) else ""
    try:
        updated = state_file.stat().st_mtime
    except OSError:
        updated = 0.0
    return {"name": root.name, "title": title[:100], "title_key": title_key,
            "pinned": bool(data.get("sidebar_pinned", False)),
            "updated_at": updated}


def available_sessions(state: ProjectState) -> list[dict[str, Any]]:
    root = state.root.parent
    if not root.is_dir():
        return [session_list_item(state.root)]
    records = [session_list_item(item) for item in root.iterdir() if item.is_dir()]
    records.sort(key=lambda item: (not item["pinned"], -item["updated_at"], item["name"].casefold()))
    return records or [session_list_item(state.root)]


def is_new_session_title(value: Any) -> bool:
    """Recognize historical new-chat labels while presentation stays in the catalog."""
    return str(value or "").strip() in {"新聊天", "New chat", "Neuer Chat"}


def title_session_from_question(state: ProjectState, question: str) -> None:
    current = str(state.data.get("sidebar_title", "")).strip()
    if current and not is_new_session_title(current):
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
    # Generated IDs must never collide with each other or with an explicit ID;
    # explicit duplicates are reported by rule_id_conflicts() instead.
    explicit_ids = {str(rule["id"]) for group in [draft.get("global_rules"), draft.get("table_rules")]
                    + [item.get(key) for item in draft["classes"] if isinstance(item, dict)
                       for key in ("decision_rules", "boundaries")]
                    for rule in (group if isinstance(group, list) else [])
                    if isinstance(rule, dict) and rule.get("id")}
    generated: set[str] = set()

    def generated_id(base: str) -> str:
        candidate, number = base, 2
        while candidate in explicit_ids or candidate in generated:
            candidate, number = f"{base}-{number}", number + 1
        generated.add(candidate)
        return candidate
    classes: list[dict[str, Any]] = []
    seen_names = set()
    for item in draft["classes"]:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"].strip():
            continue
        def rules(values: object, prefix: str) -> list[dict[str, Any]]:
            result: list[dict[str, Any]] = []
            for index, value in enumerate(values if isinstance(values, list) else [], start=1):
                if isinstance(value, str):
                    result.append({"id": generated_id(f"{prefix}-{index}"), "text": value, "pages": []})
                elif isinstance(value, dict) and str(value.get("text", "")).strip():
                    result.append(with_blocks({"id": str(value.get("id") or generated_id(f"{prefix}-{index}")),
                                               "text": str(value["text"]).strip(),
                                               "pages": [int(page) for page in (value.get("pages") or []) if str(page).isdigit()]},
                                              value.get("blocks")))
            return result
        name = item["name"].strip()
        if name.casefold() in seen_names or not isinstance(item.get("definition"), str) or not item["definition"].strip():
            raise UIValidationError(ui_message(ACTIVE, 'rules.class_definitions'))
        seen_names.add(name.casefold())
        key = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-") or "class"
        classes.append(with_blocks({
            "name": name, "definition": str(item.get("definition", "")).strip(),
            "decision_rules": rules(item.get("decision_rules", []), f"{key}-rule"),
            "boundaries": rules(item.get("boundaries", []), f"{key}-boundary"),
            "evidence_pages": [int(page) for page in (item.get("evidence_pages") or []) if str(page).isdigit()],
        }, item.get("evidence_blocks"), "evidence_blocks"))
    if not classes:
        raise UIValidationError(ui_message(ACTIVE, 'rules.classes_empty'))
    def profile_rules(values: object, prefix: str) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for index, value in enumerate(values if isinstance(values, list) else [], start=1):
            if isinstance(value, str):
                result.append({"id": generated_id(f"{prefix}-{index}"), "text": value, "pages": []})
            elif isinstance(value, dict) and str(value.get("text", "")).strip():
                result.append(with_blocks({"id": str(value.get("id") or generated_id(f"{prefix}-{index}")), "text": str(value["text"]).strip(),
                                           "pages": [int(page) for page in (value.get("pages") or []) if str(page).isdigit()],
                                           "table": value.get("table") if isinstance(value.get("table"), dict) else None},
                                          value.get("blocks")))
        return result
    return {"classes": classes, "global_rules": profile_rules(draft.get("global_rules", []), "global"),
            "table_rules": profile_rules(draft.get("table_rules", []), "table"), "uncertainties": draft.get("uncertainties", [])}


def require_unique_rule_ids(draft: dict | None, status: int = 400) -> None:
    conflicts = rule_id_conflicts(draft)
    if conflicts:
        raise HTTPException(status, ui_message(ACTIVE, 'rules.duplicate_ids', ids=", ".join(conflicts[:20])))


CODEBOOK_BUDGET = CodebookParseBudget()


def parse_codebook_draft_with_repair(connector: LLMConnector, raw: str, *, data, usage_records=None,
                                     on_call=None, output_tokens: int | None = None) -> tuple[dict, dict | None]:
    """Parse the final Codebook JSON, making one syntax-only repair attempt if needed."""
    try:
        return parse_codebook_draft(raw), None
    except (ValueError, json.JSONDecodeError) as initial_error:
        if isinstance(initial_error, UIValidationError) and initial_error.ui_message.message_key != 'rules.model_json':
            raise  # Structurally valid JSON without usable classes: a syntax repair cannot help.
        repair_prompt = (
            "The candidate Codebook JSON below could not be parsed. Repair its JSON syntax only; "
            "do not summarize, add, omit, translate, or change any factual content.\n"
            f"Parser error: {initial_error}\n\n--- CANDIDATE JSON ---\n{raw}"
        )
        if on_call:
            on_call()
        tokens = output_tokens or CODEBOOK_BUDGET.repair_output_tokens
        repaired = accounted_model_call(data, connector, [], repair_prompt, CODEBOOK_JSON_REPAIR_SYSTEM,
                                        {"maxOutputTokens": tokens, "temperature": 0}, stream=True,
                                        usage_records=usage_records)
        repaired = require_model_success(repaired, ui_message(data, 'model.context_codebook_repair'))
        repair_usage = connector.get_last_token_usage() or {}
        try:
            return parse_codebook_draft(repaired), repair_usage
        except (ValueError, json.JSONDecodeError) as repair_error:
            raise UIValidationError(ui_message(data, 'rules.repair_invalid', detail=error_copy(repair_error, data))) from initial_error


# ---------------------------------------------------------------------------
# Observable Codebook preparation
#
# One preparation is described by a small JSON record (stage, current unit,
# log, final result or classified failure).  The record lives in memory while
# the job runs and is mirrored to AI_Bot_State/codebook_task.json, so a page
# reload or a restarted program can show the latest final state.  The rule
# profile itself is written only after every unit, the merge and validation
# succeeded; a failed or cancelled attempt never replaces existing rules.
# ---------------------------------------------------------------------------
CODEBOOK_JOB_GUARD = threading.Lock()
CODEBOOK_JOB: dict[str, Any] = {}


def codebook_job_path() -> Path:
    return app_state_home() / "codebook_task.json"


class CodebookJob:
    """Observable state of one Codebook preparation (background or direct API call)."""

    def __init__(self, path: Path, file_type: str, model: str, request_id: str = "", previous: dict | None = None):
        self.calls = 0
        self.call_limit = CODEBOOK_BUDGET.max_total_calls
        self.usages: list[dict] = []
        try:
            size = path.stat().st_size
        except OSError:
            size = None
        now = local_timestamp()
        self.record: dict[str, Any] = {
            "task_id": uuid.uuid4().hex, "request_id": request_id, "state": "running", "stage": "reading",
            "source": {"path": str(path), "name": path.name, "type": file_type, "bytes": size},
            "model": model, "unit_kind": "page" if file_type == "pdf" else "block",
            "progress": {}, "units_total": None, "started_at": now, "updated_at": now, "finished_at": None,
            "result": None, "failure": None, "log": [], "calls": 0,
            "budget": {"unit_output_tokens": CODEBOOK_BUDGET.unit_output_tokens,
                       "max_attempts_per_unit": CODEBOOK_BUDGET.max_attempts_per_unit,
                       "max_calls_per_unit": CODEBOOK_BUDGET.max_calls_per_unit,
                       "max_total_calls": CODEBOOK_BUDGET.max_total_calls},
            "previous_profile": previous,
        }
        self.event("reading", "rulejob.log.started", name=path.name, type=file_type.upper(), model=model)

    def publish(self) -> None:
        self.record["updated_at"] = local_timestamp()
        self.record["calls"] = self.calls
        snapshot = copy.deepcopy(self.record)
        with CODEBOOK_JOB_GUARD:
            CODEBOOK_JOB.clear()
            CODEBOOK_JOB.update(home=str(app_state_home()), record=snapshot)
        try:
            write_json_atomically(codebook_job_path(), snapshot)
        except OSError:
            pass  # The in-memory record still serves the open page.

    def event(self, stage: str, key: str, *, progress: dict | None = None, level: str = "info",
              publish: bool = True, **params) -> None:
        self.record["stage"] = stage
        if progress is not None:
            self.record["progress"] = progress
        self.record["log"].append({"at": local_timestamp(), "stage": stage, "level": level,
                                   "message": UIMessage(key, "zh", **params).payload()})
        del self.record["log"][:-CODEBOOK_JOB_LOG_LIMIT]
        if publish:
            self.publish()

    def count_call(self) -> None:
        if self.calls >= self.call_limit:
            raise CodebookPrepareError("call_limit", self.record["stage"], params={"limit": self.call_limit})
        self.calls += 1
        self.publish()  # The page shows the call count while the request is in flight.

    def succeed(self, profile: dict) -> None:
        nonpaged = profile.get("unit_kind") == "block"
        self.record.update(state="succeeded", finished_at=local_timestamp(), usage=profile.get("usage"), result={
            "status": profile.get("status"), "prepared_at": profile.get("prepared_at"),
            "profile_version": profile.get("version"), "parser_model": profile.get("parser_model"),
            "page_count": 0 if nonpaged else profile.get("page_count"),
            "block_count": profile.get("block_count") if nonpaged else None,
            "unit_count": profile.get("page_groups"), "classes": len((profile.get("draft") or {}).get("classes", [])),
            "encoding": profile.get("source_encoding")})
        # Published by run_codebook_job only after the model slot is free, so
        # the page can never offer Lock while the server still reports busy.
        self.event("done", "rulejob.log.succeeded", progress={}, publish=False,
                   classes=self.record["result"]["classes"], calls=self.calls)

    def fail(self, error: CodebookPrepareError) -> None:
        full, short = error.messages()
        state = "cancelled" if error.reason == "cancelled" else "failed"
        self.record.update(state=state, finished_at=local_timestamp(), usage=summarize_usage(self.usages), failure={
            "reason": error.reason, "stage": error.stage, "unit": error.unit, "attempts": error.attempts,
            "message": full.payload(), "short": short.payload(), "technical": error.technical})
        self.record["log"].append({"at": local_timestamp(), "stage": error.stage,
                                   "level": "warning" if state == "cancelled" else "error",
                                   "message": full.payload(), "technical": error.technical})
        del self.record["log"][:-CODEBOOK_JOB_LOG_LIMIT]


def codebook_failure(exc: BaseException, job: CodebookJob | None) -> CodebookPrepareError:
    """Classify any exception raised while preparing rules."""
    stage = job.record["stage"] if job else "reading"
    if isinstance(exc, CodebookPrepareError):
        return exc
    if isinstance(exc, RequestCancelled):
        return CodebookPrepareError("cancelled", stage, technical=str(exc))
    if isinstance(exc, RequestTimedOut):
        return CodebookPrepareError("timeout", stage, technical=str(exc))
    if isinstance(exc, (UIRequestError, ResponseLimitExceeded)):
        reason, params = classify_model_failure(exc)
        return CodebookPrepareError(reason, stage, technical=str(exc), params=params)
    return CodebookPrepareError("internal", stage, technical=f"{type(exc).__name__}: {exc}")


def load_codebook_job() -> dict | None:
    """The live job, or the last persisted final state (interrupted runs are closed)."""
    home = str(app_state_home())
    with CODEBOOK_JOB_GUARD:
        live = copy.deepcopy(CODEBOOK_JOB.get("record")) if CODEBOOK_JOB.get("home") == home else None
    if live and live.get("state") == "running":
        return live
    try:
        record = json.loads(codebook_job_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return live
    if not isinstance(record, dict):
        return live
    if record.get("state") == "running" and not MODEL_WORK_IN_PROGRESS.is_set():
        # The program stopped (or crashed) mid-way: nothing was saved.
        error = CodebookPrepareError("interrupted", str(record.get("stage") or "reading"))
        full, short = error.messages()
        record.update(state="failed", finished_at=record.get("updated_at"), failure={
            "reason": "interrupted", "stage": error.stage, "unit": None, "attempts": None,
            "message": full.payload(), "short": short.payload(), "technical": ""})
        try:
            write_json_atomically(codebook_job_path(), record)
        except OSError:
            pass
    return record


def parse_codebook_unit(job: CodebookJob, data: dict[str, Any], connector: LLMConnector, unit: dict,
                        total: int, file_type: str) -> list[dict]:
    """Parse one unit within CODEBOOK_BUDGET; returns complete JSON notes only."""
    budget = CODEBOOK_BUDGET
    reference = {key: unit[key] for key in ("kind", "number", "first", "last") if key in unit}
    tried = {"levels": 0}

    def attempts() -> int:
        return tried["levels"]

    def request(piece: dict, tokens: int) -> tuple[dict | None, tuple[str, dict, str] | None]:
        files, prompt, source = codebook_piece_request(unit, piece, total, file_type)
        job.count_call()
        raw = accounted_model_call(data, connector, files, prompt, CODEBOOK_PAGE_SYSTEM,
                                   {"maxOutputTokens": tokens, "temperature": 0}, stream=True,
                                   usage_records=job.usages)
        failure = connector_failure(raw)
        if failure:
            reason, params = classify_model_failure(failure)
            return None, (reason, params, str(failure))
        note = parse_codebook_note(raw)
        if note is None:
            if not str(raw).strip():
                raise CodebookPrepareError("invalid_json", "parsing", unit=reference, technical=str(raw)[:800])
            # The response is complete (its stop reason was checked) but not
            # valid JSON.  A page note is only input to the merge, so its text
            # is passed on as is instead of failing the whole Codebook or
            # paying for the page again.  The final profile is still validated
            # strictly, and the page is flagged for review before locking.
            note = {"unparsed_note": str(raw).strip()[:20000]}
            job.record.setdefault("unparsed_units", []).append(dict(reference, detail=json_error_detail(raw)[:600]))
            job.event("parsing", "rulejob.log.note_unparsed", level="warning", unit=codebook_unit_label(reference))
        note["source"] = source
        return note, None

    def run(piece: dict, level: int) -> list[dict]:
        tried["levels"] = max(tried["levels"], level + 1)
        note, failure = request(piece, budget.unit_output_tokens if level == 0 else budget.part_output_tokens)
        if note is not None:
            return [note]
        reason, params, technical = failure or ("model_error", {}, "")
        if reason != "output_limit":
            raise CodebookPrepareError(reason, "parsing", unit=reference, technical=technical, params=params)
        parts = split_codebook_piece(piece, budget.min_split_chars) if level < budget.max_split_depth else None
        if parts:
            job.event("parsing", "rulejob.log.retry_split", level="warning", unit=codebook_unit_label(reference),
                      attempt=level + 2, limit=budget.max_attempts_per_unit)
            return [note for part in parts for note in run(part, level + 1)]
        # Already at the full ceiling and split once (or not splittable): stop.
        raise CodebookPrepareError(reason, "parsing", unit=reference, attempts=attempts(),
                                   technical=technical, params=params)

    if unit["kind"] == "page":
        piece = {"native": unit["native_text"], "ocr": unit["ocr_text"], "part": (1, 1)}
    else:
        piece = {"chunks": unit["chunks"], "part": (1, 1)}
    return run(piece, 0)


def merge_codebook_notes(job: CodebookJob, data: dict[str, Any], connector: LLMConnector,
                         notes: list[list[dict]], nonpaged: bool,
                         cache: tuple[dict, Path] | None = None) -> str:
    """Merge every unit's notes into profile JSON.

    One request first; on an output-limit stop the profile is merged section
    by section (see CodebookParseBudget) instead of asking for ever longer
    single responses.
    """
    budget = CODEBOOK_BUDGET
    notes_text = codebook_notes_text(notes, nonpaged)
    prompt = (f"Consolidate every Codebook {'text-block' if nonpaged else 'page'} note below. "
              "All classes, tables and boundary rules must be retained.")
    if nonpaged:
        prompt += (" This Codebook has no physical pages: cite the supplied block numbers in \"blocks\" and "
                   "\"evidence_blocks\" and leave \"pages\" and \"evidence_pages\" empty.")
    prompt += "\n\n" + notes_text
    for tokens in budget.merge_output_tokens:
        job.count_call()
        raw = accounted_model_call(data, connector, [], prompt, CODEBOOK_MERGE_SYSTEM,
                                   {"maxOutputTokens": tokens, "temperature": 0}, stream=True, usage_records=job.usages)
        failure = connector_failure(raw)
        if not failure:
            return raw
        reason, params = classify_model_failure(failure)
        if reason != "output_limit":
            raise CodebookPrepareError(reason, "merging", technical=str(failure), params=params)
    job.event("merging", "rulejob.log.merge_sectioned", tokens=budget.section_output_tokens[0])
    return json.dumps(merge_codebook_sections(job, data, connector, notes_text, cache), ensure_ascii=False)


def merge_codebook_sections(job: CodebookJob, data: dict[str, Any], connector: LLMConnector, notes_text: str,
                            cache: tuple[dict, Path] | None = None) -> dict:
    """Outline, one request per class, general rules and table rules; assembled locally.

    The notes travel in the system prompt so Claude's prompt cache serves the
    repeated input; each section is one request with the normal ceiling.
    """
    budget = CODEBOOK_BUDGET
    system = CODEBOOK_SECTION_SYSTEM + notes_text

    def section(label: UIMessage, request: str, current: int | None, total: int | None) -> dict:
        # A section that succeeded before (same notes, request and model) is
        # reused, so a retry after a dropped connection pays only for the rest.
        key = "section:" + hashlib.sha256(f"{system}\0{request}".encode("utf-8")).hexdigest()[:24]
        if cache and isinstance(cache[0].get(key), list) and cache[0][key]:
            job.event("merging", "rulejob.log.section_reused", section=label)
            return dict(cache[0][key][0])
        if total is None:
            job.event("merging", "rulejob.log.merge_outline", progress={}, section=label)
        else:
            job.event("merging", "rulejob.log.merge_section", progress={"current": current, "total": total},
                      current=current, total=total, section=label)
        technical = ""
        for attempt, tokens in enumerate(budget.section_output_tokens, start=1):
            text = request
            job.count_call()
            raw = accounted_model_call(data, connector, [], text, system,
                                       {"maxOutputTokens": tokens, "temperature": 0}, stream=True,
                                       usage_records=job.usages)
            failure = connector_failure(raw)
            if failure:
                reason, params = classify_model_failure(failure)
                technical = str(failure)
                if reason != "output_limit":
                    raise CodebookPrepareError(reason, "merging", technical=technical, params=params)
                continue
            result = parse_codebook_note(raw)
            if result is None:
                raise CodebookPrepareError("invalid_json", "merging", technical=str(raw)[:800])
            if cache:
                cache[0][key] = [result]
                try:
                    write_json_atomically(cache[1], cache[0])
                except OSError:
                    pass
            return result
        raise CodebookPrepareError("section_output_limit", "merging", attempts=len(budget.section_output_tokens),
                                   technical=technical, params={"section": label})

    outline = section(UIMessage("rulejob.section.outline", "zh"),
                      'SECTION outline. Return {"classes":[{"name":"exact official class name"}]} listing every '
                      'classification class defined in the notes, in Codebook order. Names only.', None, None)
    names: list[str] = []
    for item in outline.get("classes", []) if isinstance(outline.get("classes"), list) else []:
        name = str((item.get("name") if isinstance(item, dict) else item) or "").strip()
        if name and name.casefold() not in {known.casefold() for known in names}:
            names.append(name)
    if not names:
        raise CodebookPrepareError("no_rules", "merging", technical="The class outline contains no class",
                                   params={"detail": UIMessage("rules.classes_empty", "zh")})
    if len(names) > budget.max_merge_classes:
        raise CodebookPrepareError("call_limit", "merging", params={"limit": budget.max_merge_classes},
                                   technical=f"{len(names)} classes exceed max_merge_classes")
    total = len(names) + 2
    classes = []
    for index, name in enumerate(names, start=1):
        key = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-") or "class"
        result = section(UIMessage("rulejob.section.class", "zh", name=name),
                         f'SECTION class. Return {{"name":{json.dumps(name, ensure_ascii=False)},"definition":"...",'
                         f'"decision_rules":[{{"id":"{key}-rule-1","text":"...","pages":[1]}}],'
                         f'"boundaries":[{{"id":"{key}-boundary-1","text":"...","pages":[1]}}],"evidence_pages":[1]}} '
                         f'for the class {json.dumps(name, ensure_ascii=False)} only, with every decision rule and '
                         'boundary/exclusion rule that applies to it.', index, total)
        result["name"] = name  # The outline fixes the exact official name.
        classes.append(result)
    general = section(UIMessage("rulejob.section.general", "zh"),
                      'SECTION general. Return {"global_rules":[{"id":"global-1","text":"...","pages":[1]}],'
                      '"uncertainties":["..."]} with rules that apply to all classes (procedure, counting, required '
                      'fields) and the uncertainties noted. Do not repeat class-specific rules.', total - 1, total)
    tables = section(UIMessage("rulejob.section.tables", "zh"),
                     'SECTION tables. Return {"table_rules":[{"id":"table-1","text":"meaning of the table rule",'
                     '"pages":[1],"table":{"columns":["..."],"rows":[["..."]]}}]} for the decision tables. Keep only '
                     'classification-relevant rows with short cells; return {"table_rules":[]} if there are none.',
                     total, total)
    return {"classes": classes,
            "global_rules": general.get("global_rules", []) if isinstance(general.get("global_rules"), list) else [],
            "table_rules": tables.get("table_rules", []) if isinstance(tables.get("table_rules"), list) else [],
            "uncertainties": general.get("uncertainties", []) if isinstance(general.get("uncertainties"), list) else []}


# Completed page/block notes are kept per file content, model and parsing
# prompt, so a retry after a failed merge or a dropped connection does not
# pay for pages that already succeeded.  Notes are complete JSON only.
CODEBOOK_NOTES_VERSION = hashlib.sha256(json.dumps([
    CODEBOOK_PAGE_SYSTEM, CODEBOOK_BUDGET.unit_output_tokens, CODEBOOK_BUDGET.part_output_tokens,
    CODEBOOK_BUDGET.max_split_depth, CODEBOOK_BUDGET.min_split_chars,
]).encode("utf-8")).hexdigest()[:12]


def codebook_note_cache_path(file_sha: str, model: str) -> Path:
    identity = hashlib.sha256(f"{model}\0{CODEBOOK_NOTES_VERSION}".encode("utf-8")).hexdigest()[:12]
    return app_state_home() / "codebook_note_cache" / f"{file_sha[:20]}_{identity}.json"


def prepare_codebook_profile(data: dict[str, Any], path: Path, model: str, job: CodebookJob | None = None) -> dict:
    """Read, parse, merge and validate a Codebook into an unsaved draft profile."""
    file_type = CODEBOOK_FILE_TYPES.get(path.suffix.lower())
    if not file_type:
        raise CodebookPrepareError("unreadable", "reading", technical=f"Unsupported rule file type {path.suffix}")
    job = job or CodebookJob(path, file_type, model, data.get("operation_id", ""))
    encoding = None
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        raise CodebookPrepareError("unreadable", "reading", technical=f"{type(exc).__name__}: {exc}") from exc
    if file_type == "txt":
        job.event("extracting", "rulejob.stage.extracting_txt")
        try:
            _text, encoding = decode_text_bytes(raw_bytes)  # TXT stays local: no PDF, OCR or page images.
        except TextDecodingError as exc:
            reason = {"empty": "empty_file", "binary": "binary", "encoding": "encoding"}[exc.reason]
            raise CodebookPrepareError(reason, "extracting", technical=str(exc)) from exc
    else:
        job.event("extracting", "rulejob.stage.extracting_pdf" if file_type == "pdf" else "rulejob.stage.extracting_docx")
    try:
        document = data["documents"].add(str(path))
    except Exception as exc:
        empty = "no extractable text" in str(exc).casefold()
        raise CodebookPrepareError("empty_file" if empty else "unreadable", "extracting",
                                   technical=f"{type(exc).__name__}: {exc}") from exc
    connector = LLMConnector(model, data["llm"].api_key, session_id=f"codebook_{os.urandom(6).hex()}")
    records: list[dict] = []
    if file_type == "pdf":
        ocr_runtime = data["documents"].ocr_runtime_status()

        def extracted(current: int, total: int) -> None:
            check_request(data)
            job.event("extracting", "rulejob.stage.extracting_pdf_page", progress={"current": current, "total": total},
                      current=current, total=total)
        try:
            records = data["documents"].codebook_page_records(path, app_state_home() / "codebook_visual_cache",
                                                              progress=extracted)
        except (RequestCancelled, RequestTimedOut):
            raise
        except Exception as exc:
            raise CodebookPrepareError("unreadable", "extracting", technical=f"{type(exc).__name__}: {exc}") from exc
        if not records:
            raise CodebookPrepareError("empty_file", "extracting")
        units = [{"kind": "page", "number": record["page"], "page_type": record["page_type"],
                  "native_text": record["native_text"], "ocr_text": record["ocr_text"],
                  "ocr_status": record["ocr_status"], "image_path": record["image_path"]} for record in records]
    else:
        ocr_runtime = {"available": False, "status": f"not applicable to {file_type.upper()}"}
        units = codebook_text_units(document.get("chunks", []))
        if not units:
            raise CodebookPrepareError("empty_file", "extracting")
        if encoding:
            job.event("extracting", "rulejob.log.txt_decoded", encoding=encoding, blocks=len(document.get("chunks", [])))
    nonpaged = file_type != "pdf"
    job.record["units_total"] = len(units)
    job.call_limit = CODEBOOK_BUDGET.call_limit(len(units))
    notes: list[list[dict]] = []
    note_cache_path = codebook_note_cache_path(hashlib.sha256(raw_bytes).hexdigest(), model)
    note_cache = load_codebook_note_cache(note_cache_path)
    job.event("parsing", "rulejob.log.cache_status", reusable=sum(codebook_unit_key(unit) in note_cache for unit in units),
              total=len(units), file=note_cache_path.name)
    reused_units = 0
    for index, unit in enumerate(units, start=1):
        if nonpaged:
            job.event("parsing", "rulejob.stage.parsing_blocks", current=index, total=len(units),
                      first=unit["first"], last=unit["last"],
                      progress={"current": index, "total": len(units), "first": unit["first"], "last": unit["last"],
                                "blocks": unit["blocks_total"]})
        else:
            job.event("parsing", "rulejob.stage.parsing_page", current=unit["number"], total=len(units),
                      progress={"current": unit["number"], "total": len(units)})
        key = codebook_unit_key(unit)
        if key in note_cache:
            reused_units += 1
            if any("unparsed_note" in note for note in note_cache[key]):
                job.record.setdefault("unparsed_units", []).append(
                    {name: unit[name] for name in ("kind", "number", "first", "last") if name in unit})
            job.event("parsing", "rulejob.log.unit_reused", unit=codebook_unit_label(
                {name: unit[name] for name in ("kind", "number", "first", "last") if name in unit}))
            notes.append(note_cache[key])
            continue
        unit_notes = parse_codebook_unit(job, data, connector, unit, len(units), file_type)
        notes.append(unit_notes)
        note_cache[key] = unit_notes
        try:
            write_json_atomically(note_cache_path, note_cache)
        except OSError:
            pass  # Reuse is an optimisation only.
    job.event("merging", "rulejob.stage.merging", progress={})
    merged = merge_codebook_notes(job, data, connector, notes, nonpaged, (note_cache, note_cache_path))
    try:
        draft, _ = parse_codebook_draft_with_repair(connector, merged, data=data, usage_records=job.usages,
                                                    on_call=job.count_call)
    except UIValidationError as exc:
        key = exc.ui_message.message_key
        if key in {"rules.classes_required", "rules.classes_empty", "rules.class_definitions"}:
            raise CodebookPrepareError("no_rules", "merging", technical=str(exc), params={"detail": exc.ui_message}) from exc
        raise CodebookPrepareError("invalid_json", "merging", technical=str(exc)) from exc
    except UIRequestError as exc:
        reason, params = classify_model_failure(exc)
        raise CodebookPrepareError("invalid_json" if reason == "output_limit" else reason, "merging",
                                   technical=str(exc), params=params) from exc
    if nonpaged:
        nonpaged_references(draft)
    rule_id_renames = namespace_duplicate_rule_ids(draft)
    usage = summarize_usage(job.usages)
    chunk_count = len(document.get("chunks", []))
    return {"status": "draft", "source_path": str(path), "source_name": path.name, "sha256": file_digest(path),
            "source_type": file_type, "unit_kind": "block" if nonpaged else "page",
            "source_encoding": encoding,
            "prepared_at": local_timestamp(), "parser_model": connector.last_response_model or model,
            "requested_model": model,
            "page_count": len(records) or chunk_count, "block_count": chunk_count if nonpaged else None,
            "page_groups": len(units), "usage": usage, "draft": draft, "document_id": document["id"],
            "parse_calls": job.calls, "reused_units": reused_units,
            "unparsed_units": [{key: item[key] for key in ("kind", "number", "first", "last") if key in item}
                               for item in job.record.get("unparsed_units", [])],
            "page_records": [{key: record[key] for key in ("page", "page_type", "ocr_status", "embedded_image_count")} for record in records],
            "page_transcriptions": [json.dumps(unit_notes, ensure_ascii=False) for unit_notes in notes],
            "ocr_runtime": ocr_runtime, "rule_id_renames": rule_id_renames}


def run_codebook_job(data: dict[str, Any], job: CodebookJob, path: Path, model: str) -> dict:
    """Prepare and save a draft; on any failure record it and keep existing rules.

    Owns the model slot reserved by begin_model_work(): it is released before
    the final state is published, so a finished state never meets a busy server.
    """
    try:
        with LOCK:
            profile = prepare_codebook_profile(data, path, model, job)
            job.event("saving", "rulejob.stage.saving")
            with commit_answer(data):  # A Stop that wins here saves no profile.
                save_codebook_profile(profile)
                rules_changed(data)
                data["state"].data["selected_codebook_path"] = str(path)
                data["state"].save()
            # Saving rules changes the context revision.  The page that started
            # the job (and was current then) may adopt the new token; any other
            # page stays stale exactly as with every other context change.
            job.record["context_after"] = context_token(data)
        job.succeed(profile)
        return profile
    except Exception as exc:
        error = codebook_failure(exc, job)
        job.fail(error)
        if error is exc:
            raise
        raise error from exc
    finally:
        end_model_work(data)
        job.publish()


def write_session_export(data: dict[str, Any]) -> Path:
    state = data["state"]
    exports = state.root / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    target = exports / f"session_transcript_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    usage = state.data.get("usage", {})
    transcript = state.full_history()
    def copy(key, **params):
        return str(ui_message(data, key, **params))

    def number(value):
        return 0 if value is None else value
    cost = f"${float(number(usage.get('estimated_cost_usd', 0))):.6f}"
    cost_text = f"{copy('state.unknown')}; {copy('export.known_tokens')}: {cost}" if usage.get("unpriced_requests") else cost
    lines = [
        f"# {copy('export.session_heading')}", "",
        f"- {copy('export.generated_at')}: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- {copy('export.session_name')}: {state.root.name}",
        f"- {copy('export.model')}: {data['model']}",
        f"- {copy('export.total_requests')}: {number(usage.get('requests', 0))}",
        f"- {copy('export.total_tokens')}: {number(usage.get('input', 0))} / {number(usage.get('output', 0))}",
        f"- {copy('export.estimated_cost')}: {cost_text}",
        f"- {copy('export.known_tokens')}: {number(usage.get('known_input', usage.get('input', 0)))} / {number(usage.get('known_output', usage.get('output', 0)))}",
        "", f"## {copy('export.transcript')}", "",
    ]
    for item in transcript:
        role = copy('export.user') if item.get("role") == "user" else copy('export.assistant')
        timestamp = item.get("time", "")
        lines.extend([f"### {role} {timestamp}", "", str(item.get("content", "")), ""])
    target.write_text("\n".join(lines), encoding="utf-8")
    return target


def write_bg_analysis_export(state: ProjectState, language: str = "zh") -> Path:
    record = state.data.get("last_bg_analysis")
    if not isinstance(record, dict):
        raise HTTPException(400, ui_message(ACTIVE, 'error.export_missing'))
    exports = state.root / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = exports / f"bg_analysis_{timestamp}.md"
    def copy(key, **params):
        return str(ui_message({"language": language}, key, **params))

    def number(value):
        return 0 if value is None else value
    unknown = copy("state.unknown")
    sources = "\n".join(f"- {item}" for item in record.get("sources", [])) or f"- {copy('export.no_sources')}"
    bg = record.get("bg_context") or {}
    token = record.get("token_usage") or {}
    content = "\n".join([
        "# " + copy("export.analysis_heading"),
        "",
        "- " + copy("export.generated_at") + ": " + str(record.get("created_at", "")),
        "- " + copy("export.session_name") + ": " + str(record.get("session", "")),
        "- " + copy("export.model") + ": " + str(record.get("model", "")),
        "- " + copy("export.codebook") + ": " + str(bg.get("codebook_name") or "—"),
        "- " + copy("export.folder") + ": " + str(bg.get("folder") or "—"),
        "- " + copy("export.turn_tokens") + ": " + str(number(token.get("input", 0))) + " / " + str(number(token.get("output", 0))),
        "- " + copy("export.reasoning_tokens") + ": " + str(number(token.get("reasoning", 0))),
        "- " + copy("export.gemini_thinking_tokens") + ": " + str(number(token.get("gemini_thinking", 0))),
        "- " + copy("export.claude_cache") + ": " + str(number(token.get("cache_read", 0))) + " / " + str(number(token.get("cache_write", 0))),
        "- " + copy("export.turn_cost") + ": " + (unknown if token.get("cost_usd") is None else "$" + format(float(token["cost_usd"]), ".6f")),
        "",
        "## " + copy("export.question"),
        "",
        str(record.get("question", "")),
        "",
        "## " + copy("export.answer"),
        "",
        str(record.get("answer", "")),
        "",
        "## " + copy("export.evidence_sources"),
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


def material_summary_cache_path(document: dict, model: str, full: bool, read_pages: list[int]) -> Path:
    """A content-addressed local cache, never written beside BG source files."""
    digest = str(document.get("sha256") or "unknown")
    identity = json.dumps({"version": MATERIAL_SUMMARY_CACHE_VERSION, "sha256": digest,
                           "model": model, "full": full, "pages": read_pages},
                          ensure_ascii=False, sort_keys=True)
    key = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return app_state_home() / "material_cache" / digest / f"{key}.json"


MODEL_CHECK_TOKENS = 4096


def material_group_note_path(document: dict, model: str, group: str) -> Path:
    """One successful group note, keyed by its exact text, model and prompt version.

    Lives below the file's material_cache folder, so rebuilding that file or
    clearing summary caches removes it too.
    """
    digest = str(document.get("sha256") or "unknown")
    identity = hashlib.sha256(f"{MATERIAL_GROUP_NOTE_VERSION}\0{model}\0{group}".encode("utf-8")).hexdigest()[:24]
    return app_state_home() / "material_cache" / digest / "groups" / f"{identity}.json"


def load_material_group_note(document: dict, model: str, group: str) -> str | None:
    try:
        cached = json.loads(material_group_note_path(document, model, group).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(cached, dict) or cached.get("version") != MATERIAL_GROUP_NOTE_VERSION or cached.get("model") != model:
        return None
    note = cached.get("note")
    return note if isinstance(note, str) and note.strip() else None


def save_material_group_note(document: dict, model: str, group: str, note: str) -> None:
    try:
        write_json_atomically(material_group_note_path(document, model, group), {
            "version": MATERIAL_GROUP_NOTE_VERSION, "model": model, "note": note,
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds")})
    except OSError:
        pass  # Reuse is an optimisation; the pre-reading result is unaffected.


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
        cached = dict(cached)
        cached["cache_status"] = "reused"
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
        raw = require_model_success(accounted_model_call(data, data["llm"], [], request, system_prompt, {"maxOutputTokens": BG_DOSSIER_TOKENS, "temperature": 0}, stream=True, usage_records=records_used), ui_message(data, 'model.context_dossier'))
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
    """A session report is usable only when complete and made for the exact selected material hashes/model."""
    coverage = coverage if coverage is not None else load_coverage(data["state"])
    return bool(coverage.get("complete")) and coverage_is_for_current_selection(data, coverage)


def coverage_is_for_current_selection(data: dict[str, Any], coverage: dict) -> bool:
    """True when the report belongs to the current materials and model, complete or not.

    An incomplete report of the current selection must still be shown with its
    per-file failures, not hidden behind a "selection changed" notice."""
    if coverage.get("model") != data["model"]:
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
        coverage["current_selection"] = coverage_is_for_current_selection(data, coverage)
        if coverage_matches_current_selection(data, coverage):
            dossier = load_bg_dossier_cache(coverage, data["model"])
            coverage["bg_dossier"] = {"ready": bool(dossier), "created_at": dossier.get("created_at", "") if dossier else ""}
    return coverage


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
    summary_system = MATERIAL_SUMMARY_SYSTEM
    total_documents = len(selected)
    # The retry allowance is sized from every group this scan may read.
    hints = reading_hints(data, selected)
    planned_groups = sum(len(summary_groups(item, selected_reading_chunks(item, full=full, hints=hints)[0], folder=material_folder(data)))
                         for item in selected)
    retry_limit = material_retry_limit(planned_groups)
    retry_calls = 0
    for file_index, document in enumerate(selected, start=1):
        if progress:
            progress("reading", ui_message(data, "reading.check", index=file_index, total=total_documents, name=document["name"]),
                     12 + int((file_index - 1) / max(total_documents, 1) * 48))
        # Complete analysis prepares OCR locally for visual pages. It adds no
        # Farm token cost and lets a scanned page participate in the same
        # auditable page/chunk coverage as native-text pages.
        plan_of_file = reading_plan(document, full, hints)
        # OCR only the pages that will be read (scans among them); no token cost.
        documents.ensure_document_ocr(document, pages=set(plan_of_file["read"]) or None)
        read_chunks, reading_scope = plan_of_file["chunks"], plan_of_file["scope"]
        read_pages, unread_pages = plan_of_file["read"], plan_of_file["unread"]
        page_reasons = {str(page): reasons for page, reasons in plan_of_file["reasons"].items()}
        cached = load_material_summary_cache(document, data["model"], full, read_pages)
        # Migrate a valid summary generated by the immediately preceding
        # version.  This makes the first incremental file addition cheap even
        # when the user prepared its original selection before this update.
        if not cached:
            old = previous_records.get((document.get("id"), document.get("sha256")))
            if (old and old.get("complete") and old.get("preread_version") == MATERIAL_SUMMARY_CACHE_VERSION
                    and old.get("pages_read") == read_pages and old.get("pages_unread") == unread_pages):
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
                           "full_coverage": not unread_pages, "reading_scope": reading_scope, "reading_scope_message": scope_message(plan_of_file, len(document_pages(document))), "page_reasons": page_reasons, "bom_found": hints["bom_found"],
                           "dfc_structure": documents.dfc_audit(document), "cache_status": "reused"})
            records.append(record)
            reused_files += 1
            if progress:
                progress("reading", ui_message(data, "reading.reused", index=file_index, total=total_documents, name=document["name"]),
                         12 + int(file_index / max(total_documents, 1) * 48))
            continue
        plan, visual_skipped = preread_groups(documents, document, read_chunks, material_folder(data), state.root / "visual_cache")
        groups = [item["text"] for item in plan]
        images_for = {item["text"]: item["images"] for item in plan}
        notes, failures = [], []
        reused_groups = 0
        file_retry_calls = 0
        visual_labels = [label for item in plan for label in item["labels"]]
        visual_fallback = False

        def group_call(text: str, label: str, images: list[str] | None = None) -> str:
            nonlocal total_calls, visual_fallback
            images = list(images or [])

            def call(attached: list[str]) -> str:
                nonlocal total_calls
                attempts: list[dict] = []
                hint = PREREAD_VISUAL_INSTRUCTION.format(count=len(attached)) if attached else ""
                try:
                    return accounted_model_call(data, llm, attached, f"文件：{document['name']}。{label}提取结构、部件、驱动、运动、接口、尺寸和不确定处，并保留页面/表格标签。{hint}{MATERIAL_GROUP_FORMAT}\n\n{text}",
                                                summary_system, {"maxOutputTokens": MATERIAL_GROUP_TOKENS, "temperature": 0}, stream=True, usage_records=attempts)
                finally:
                    total_calls += len(attempts)
                    if usage_records is not None:
                        usage_records.extend(attempts)

            raw = call(images)
            failure = connector_failure(raw) if images else None
            if failure and classify_model_failure(failure)[0] not in {"output_limit", "timeout"}:
                # A model or endpoint that refuses pictures still gets the text.
                visual_fallback = True
                raw = call([])
            return raw

        for number, group in enumerate(groups, start=1):
            # A group that succeeded before (e.g. in a scan where another group
            # failed) is never paid for again.
            cached_note = load_material_group_note(document, data["model"], group)
            if cached_note:
                notes.append(cached_note)
                reused_groups += 1
                continue
            halves = split_material_group(group)
            half_notes = [load_material_group_note(document, data["model"], half) for half in halves] if halves else []
            if halves and all(half_notes):
                notes.append("\n".join(note for note in half_notes if note))
                reused_groups += 1
                continue
            label = f"这是第 {number}/{len(groups)} 个完整文本片段组。" + (MATERIAL_KIND_LINE if number == 1 else "")
            try:
                # A cached half means this whole group was cut before: go
                # straight to the missing half instead of paying for it again.
                split = bool(halves) and any(half_notes)
                if not split:
                    if progress:
                        progress("reading", ui_message(data, "reading.group", name=document["name"], index=number, total=len(groups)),
                                 12 + int((file_index - 1 + number / max(len(groups), 1)) / max(total_documents, 1) * 48))
                    raw = group_call(group, label, images_for.get(group))
                    failure = connector_failure(raw)
                    if failure and classify_model_failure(failure)[0] == "output_limit" and halves:
                        split = True
                    else:
                        raw = require_model_success(raw, ui_message(data, 'model.context_group', name=document["name"]))
                        notes.append(raw.strip())
                        save_material_group_note(document, data["model"], group, raw.strip())
                        continue
                needed = sum(1 for note in half_notes if not note)
                if retry_calls + needed > retry_limit:
                    failures.append(ui_message(data, "reading.retry_limit", index=number, limit=retry_limit))
                    notes.extend(note for note in half_notes if note)
                    continue
                collected = list(half_notes)
                for part, half in enumerate(halves or (), start=1):
                    if collected[part - 1]:
                        continue
                    if progress:
                        progress("reading", ui_message(data, "reading.group_part", name=document["name"], index=number,
                                                       total=len(groups), part=part), None)
                    retry_calls += 1
                    file_retry_calls += 1
                    # Pictures ride with the first half of a split group.
                    raw = group_call(half, label + f"本次只处理该组的第 {part}/2 部分。",
                                     images_for.get(group) if part == 1 else None)
                    try:
                        note = require_model_success(raw, ui_message(data, 'model.context_group', name=document["name"])).strip()
                    except RequestStopped:
                        raise
                    except Exception as exc:
                        failures.append(ui_message(data, "reading.part_failed", index=number, part=part, detail=error_copy(exc, data)))
                        continue
                    collected[part - 1] = note
                    save_material_group_note(document, data["model"], half, note)
                notes.extend(note for note in collected if note)
                if all(collected):
                    save_material_group_note(document, data["model"], group, "\n".join(note for note in collected if note))
            except RequestStopped:
                raise
            except Exception as exc:
                failures.append(ui_message(data, "reading.group_failed", index=number, detail=error_copy(exc, data)))
        if notes and len(notes) > 1:
            try:
                merged = "\n\n".join(f"[片段组 {i}]\n{note}" for i, note in enumerate(notes, start=1))
                attempts: list[dict] = []
                try:
                    raw = accounted_model_call(data, llm, [], f"请将下列同一文件的全部片段笔记合成为一份不遗漏冲突或不确定处的技术摘要。必须保留证据标签。{MATERIAL_MERGE_FORMAT}\n\n文件：{document['name']}\n\n{merged}",
                                               summary_system, {"maxOutputTokens": MATERIAL_MERGE_TOKENS, "temperature": 0}, stream=True, usage_records=attempts)
                finally:
                    total_calls += len(attempts)
                    if usage_records is not None:
                        usage_records.extend(attempts)
                raw = require_model_success(raw, ui_message(data, 'model.context_merge', name=document["name"]))
                summary = raw.strip()
            except RequestStopped:
                raise
            except Exception as exc:
                summary = "\n\n".join(notes)
                failures.append(ui_message(data, "reading.merge_failed", detail=error_copy(exc, data)))
        else:
            summary = notes[0] if notes else ""
        record = {"id": document["id"], "name": document["name"], "path": document["path"],
                  "sha256": document.get("sha256"), "pages_total": len(document_pages(document)),
                  "pages_read": read_pages, "pages_unread": unread_pages,
                  "full_coverage": not unread_pages,
                  "text_chunks_total": len(document.get("chunks", [])), "text_chunks_selected": len(read_chunks),
                  "reading_scope": reading_scope, "reading_scope_message": scope_message(plan_of_file, len(document_pages(document))), "page_reasons": page_reasons, "bom_found": hints["bom_found"], "text_groups_total": len(groups),
                  "text_groups_processed": len(notes), "text_groups_reused": reused_groups,
                  "retry_calls": file_retry_calls,
                  "complete": bool(notes) and not failures,
                  "failures": failures, "failure_messages": [message_payload(item) for item in failures], "dfc_structure": documents.dfc_audit(document), "summary": summary,
                  "images_read": visual_labels, "images_skipped": visual_skipped, "images_fallback": visual_fallback,
                  "kind_guess": guess_document_kind(document), "kind_model": model_document_kind(summary or (notes[0] if notes else "")),
                  "preread_version": MATERIAL_SUMMARY_CACHE_VERSION,
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
              "retry_calls": retry_calls, "retry_limit": retry_limit,
              "reused_files": reused_files, "created_files": created_files}
    write_json_atomically(coverage_path(state), report)
    return report


        # No success notice until this same validator accepts the repaired action.


def call_model(data: dict[str, Any], question: str, progress=None, *, require_classification: bool | None = True,
               focus_source_id: str = "") -> dict[str, Any]:
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
    material_ids = list(bg_context.get("source_ids", [])) if bg_context else list(active_source_ids)
    focus = None
    if focus_source_id:
        if focus_source_id not in material_ids:
            raise HTTPException(409, ui_message(data, 'scope.focus_invalid'))
        focus = next((item for item in documents.list() if item.get("id") == focus_source_id), None)
        if not focus:
            raise HTTPException(409, ui_message(data, 'scope.focus_invalid'))
        material_ids = [focus_source_id]
    matches = state.search(question)
    snippets = {item: excerpt(state, item, question) for item in matches}
    preferred = ([bg_context.get("codebook_id")] + material_ids) if bg_context else material_ids
    allowed = material_ids + [bg_context.get("codebook_id")] if bg_context else material_ids
    report("search", ui_message(data, 'progress.search'), 10)
    plans = {}
    search_terms = set()
    if bg_context:
        chosen_docs = [item for item in documents.list() if item.get("id") in material_ids]
        hints = reading_hints(data, [item for item in documents.list() if item.get("id") in (state.data.get("active_source_ids") or [])])
        plans = {item["id"]: reading_plan(item, False, hints) for item in chosen_docs}
        search_terms = set(hints["bom_terms"]) | set(hints["rule_terms"])
    evidence = traceable_evidence(data, documents.search(question, preferred_ids=preferred,
                                                         classification=bool(bg_context), allowed_ids=allowed,
                                                         extra_terms=search_terms,
                                                         preferred_pages={key: plan["read"] for key, plan in plans.items()}))
    # Mark excerpts from pages the pre-read did not cover, for the model and the audit.
    for item in evidence:
        plan = plans.get(item.get("id"))
        page = (item.get("visual") or {}).get("page")
        if plan and page in plan["unread"] and "[not pre-read]" not in str(item.get("label", "")):
            item["label"] = f"{item.get('label', '')} [not pre-read]"
            item["unread_page"] = True
    if bg_context:
        existing = {(item.get("visual") or {}).get("page") for item in evidence if item.get("name") == bg_context.get("codebook_name")}
        evidence.extend(item for item in relevant_codebook_page_evidence(question, bg_context) if (item.get("visual") or {}).get("page") not in existing)
    report("search", ui_message(data, 'progress.visual'), 12)
    evidence = documents.ensure_ocr_for_snippets(evidence, question, classification=bool(bg_context))
    visuals = documents.visual_paths(evidence, state.root / "visual_cache",
                                     bilder_images=documents.bilder_image_paths(allowed),
                                     first_per_file_ids=set(material_ids) if bg_context else None)
    reasoning, notices = [], []
    turn_scope = ({"kind": "file", "id": focus["id"], "name": focus["name"]} if focus
                  else {"kind": "all", "count": len(material_ids)})
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
        if kind == "reasoning":
            reasoning.append(text)
        elif kind == "notice":
            notices.append(localize_message(text, data.get("language", "zh")))

    usage_records: list[dict] = []
    coverage = load_coverage(state)
    auto_prepared = False
    if require_classification is None:
        # No mode switch: the first whole-material question on a confirmed
        # Baugruppe is a classification; later questions let the model decide.
        first_turn = not state.data.get("history")
        classification_request = (True if first_turn and not focus else None) if bg_context else False
    else:
        classification_request = bool(bg_context) and require_classification
    classification_required = classification_request is True
    # Once a material range is confirmed as a Baugruppe, its first question
    # should transparently prepare the shared understanding, even if the user
    # phrases it as a natural question rather than using a classification word.
    # A question focused on one file needs neither the whole-range pre-read
    # nor the comprehensive dossier, so it costs no extra model calls.
    preparation_request = bool(bg_context) and not focus
    if focus:
        report("reading", ui_message(data, 'progress.focus_file', name=focus["name"]), 62)
    if not coverage_matches_current_selection(data, coverage) and preparation_request:
        report("reading", ui_message(data, 'progress.reading_start'), 12)
        coverage = prepare_coverage(data, progress=report, usage_records=usage_records)
        auto_prepared = True
        report("reading", ui_message(data, 'progress.reading_done'), 62)
    elif preparation_request:
        report("reading", ui_message(data, 'progress.reading_reused'), 62)
    coverage_summaries = coverage.get("files", []) if coverage_matches_current_selection(data, coverage) else []
    if focus:  # Reuse only this file's existing pre-read summary, if any.
        coverage_summaries = [item for item in coverage_summaries if item.get("id") == focus["id"]]
    dossier = None
    # A dossier only pays off when it combines several files; for a single
    # file its pre-read summary is used directly (no extra model call).
    if len(coverage_summaries) > 1 and not focus:
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
    elif focus and coverage_matches_current_selection(data, coverage):
        # Keep the cached prompt start identical to whole-range turns: reuse an
        # existing dossier as background, never build one for a focused turn.
        dossier = load_bg_dossier_cache(coverage, data["model"])
    model_prompt = prompt_for(state, question, snippets, document_snippets=evidence, bg_context=bg_context,
                              coverage_summaries=[] if dossier and not focus else coverage_summaries, bg_dossier=dossier,
                              response_language=data.get("language", "zh"), require_classification=classification_request,
                              focus_name=focus["name"] if focus else "")
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

    def answer_call(prompt, tokens, shortened=False):
        nonlocal preview
        check_request(data)
        limit = data["request_control"].policy.max_answer_chars if data.get("request_control") else 131072
        preview = AnswerPreview(limit)
        if data.get("answer_events"):
            data["answer_events"]({"type": "answer_reset"})
        raw_response = accounted_model_call(data, llm, visuals, prompt, SYSTEM,
                                            {"maxOutputTokens": tokens, "temperature": 0}, stream=True,
                                            event_handler=model_events, usage_records=usage_records)
        failure = connector_failure(raw_response)
        if failure and classify_model_failure(failure)[0] == "output_limit":
            if shortened:
                raise UIRequestError(ui_message(data, 'model.answer_too_long', tokens=tokens))
            report("model", ui_message(data, 'progress.answer_shorten'), 92)
            notices.append(ui_message(data, 'notice.answer_shortened'))
            return answer_call(prompt + ANSWER_SHORTEN_INSTRUCTION, ANSWER_RETRY_OUTPUT_TOKENS, shortened=True)
        # Non-streaming providers cannot emit early chunks; still use the same
        # safe answer decoder, without replaying chunks from streaming providers.
        if not preview.started and not preview.disabled:
            model_events("content", raw_response)
        return raw_response

    report("model", ui_message(data, 'progress.waiting'), 90)
    raw = answer_call(model_prompt, ANSWER_OUTPUT_TOKENS)
    raw = require_model_success(raw, ui_message(data, 'model.context_main'))
    validation = {"required": classification_required, "repairs": 0}
    scope = classification_scope(documents, bg_context)

    def repair_classification(repair_prompt):
        report("validation", ui_message(data, 'progress.repair'), 96)
        repaired = answer_call(repair_prompt, ANSWER_OUTPUT_TOKENS)
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
            ensure_current_sources(data)
            title_session_from_question(state, question)
            state.add_turn("user", question)
            state.add_turn("assistant", answer)
        if auto_prepared:
            notices.insert(0, ui_message(data, 'notice.auto_prepared', files=len(coverage.get("files", [])), calls=coverage.get("model_calls", 0)))
        report("complete", ui_message(data, 'model.complete'), 100)
        return {"answer": answer, "reasoning": "".join(reasoning), "notices": notices, "notice_messages": [message_payload(item) for item in notices],
                "sources": redact_value(evidence, llm.api_key), "dfc_evidence": visual_report.get("dfc", []), "visuals": visuals, "changes": [], "can_export_bg": False,
                "classification": None, "coverage_summary": coverage_summary_for_answer(coverage) if classification_required and not focus else None,
                "scope": turn_scope,
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
                                  [] if dossier and not focus else coverage_summaries, dossier, data.get("language", "zh"),
                                  require_classification=classification_request, focus_name=focus["name"] if focus else "")
        report("model", ui_message(data, 'progress.supplementary'), 93)
        raw = answer_call(model_prompt, ANSWER_OUTPUT_TOKENS)
        raw = require_model_success(raw, ui_message(data, 'model.context_supplementary'))
        try:
            action = validated_action(raw, model_prompt)
        except RequestStopped:
            raise
        except Exception as exc:
            if bg_context or isinstance(exc, ClassificationValidationError):
                raise
            if looks_like_action(raw):
                raise ValueError("Incomplete or invalid action JSON; no answer committed") from exc
            check_answer_size(data, raw)
            notices.append(ui_message(data, 'notice.supplementary_failed', detail=error_copy(exc, data)))
            action = {"answer": raw.strip() or str(ui_message(data, "model.empty")), "changes": [], "classification": None}
    for change in action.get("changes", []):
        if isinstance(change, dict) and state.resolve_relative(change.get("path", "")).exists() and change.get("path") not in complete:
            raise ValueError("A complete current file must be read before proposing its replacement")
    with commit_answer(data):
        ensure_current_sources(data)
        changes = build_diff(state, action.get("changes", []))
        plan_id = publish_pending(data, changes)
        title_session_from_question(state, question)
        state.add_turn("user", question)
        state.add_turn("assistant", action.get("answer", ""))
        turn_token_usage = summarize_usage(usage_records)
        # An explanation turn must not overwrite the exportable classification.
        if bg_context and (action.get("classification") is not None or not state.data.get("last_bg_analysis")):
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
                # The validated result and the context it was made in drive the
                # "classified" state of the classify button in the composer.
                "classification": action.get("classification"),
                "context_revision": state.data.get("context_revision", ""),
            }
            state.save()
    if auto_prepared:
        notices.insert(0, ui_message(data, 'notice.auto_prepared', files=len(coverage.get("files", [])), calls=coverage.get("model_calls", 0)))
    report("complete", ui_message(data, 'model.complete'), 100)
    return {"answer": action.get("answer", ""), "reasoning": "".join(reasoning), "notices": notices, "notice_messages": [message_payload(item) for item in notices],
            "sources": redact_value(evidence, llm.api_key), "dfc_evidence": visual_report.get("dfc", []), "visuals": visuals, "changes": [{k: v for k, v in item.items() if k != "content"} for item in changes],
            "plan_id": plan_id, "can_export_bg": bool(bg_context),
            "turn_usage": turn_token_usage,
            "model_response": llm.last_response_model or data["model"],
            "turn_cost": turn_token_usage["cost_usd"],
            "classification": action.get("classification"),
            "coverage_summary": coverage_summary_for_answer(coverage) if action.get("classification") is not None and not focus else None,
            "scope": turn_scope,
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
    evidence = traceable_evidence(data, documents.search(question, preferred_ids=preferred, classification=True,
                                                         allowed_ids=preferred))
    evidence.extend(relevant_codebook_page_evidence(question, bg_context))
    evidence = documents.ensure_ocr_for_snippets(evidence, question, classification=True)
    visuals = documents.visual_paths(evidence, state.root / "visual_cache",
                                     bilder_images=documents.bilder_image_paths(preferred))
    visual_report = documents.last_visual_report
    coverage = load_coverage(state)
    dossier = load_bg_dossier_cache(coverage, data["model"]) if coverage_matches_current_selection(data, coverage) else None
    prompt = prompt_for(state, question, snippets, document_snippets=evidence, bg_context=bg_context,
                        coverage_summaries=[] if dossier else (coverage.get("files", []) if coverage_matches_current_selection(data, coverage) else []),
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
                visuals, prompt, SYSTEM, {"maxOutputTokens": ANSWER_OUTPUT_TOKENS, "temperature": 0},
                stream=True, event_handler=events, usage_records=usage_records,
            )
            raw = require_model_success(raw, ui_message(data, 'model.context_compare', model=model))
            actual_model = connector.last_response_model or model
            validation = {"required": True, "repairs": 0}

            def repair_comparison(repair_prompt):
                repaired = accounted_model_call(data, connector, visuals, repair_prompt, SYSTEM,
                                                      {"maxOutputTokens": ANSWER_OUTPUT_TOKENS, "temperature": 0},
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
        except RequestStopped:
            raise  # Stop/deadline ends the comparison; consumed usage is already recorded.
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
            ensure_current_page()
            return function(*args, **kwargs)
        finally:
            LOCK.release()
    return guarded


def reset_context(data):
    state = data["state"]
    if state.transcript_path.exists():
        archive = state.root / "archives"
        archive.mkdir(exist_ok=True)
        state.transcript_path.rename(archive / (uuid.uuid4().hex + '.jsonl'))
    state.data['history'] = []
    state.data['summary'] = ''
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
        # A profile locked before IDs were enforced could never validate a classification.
        require_unique_rule_ids(context.get('locked_profile'), 409)
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
    detail = error_copy(exc, {'language': request.headers.get('X-Workbench-Language') or ACTIVE.get('language', 'de')})
    status = 503 if isinstance(exc, StartupError) and exc.code == 'startup.state_unwritable' else 400
    return JSONResponse(status_code=status, content={"detail": str(detail), **message_payload(detail)})


@app.middleware("http")
async def local_origin_only(request: Request, call_next):
    from urllib.parse import urlsplit
    origin = request.headers.get('origin')
    host = request.headers.get('host', '').split(':')[0]
    allowed_hosts = {'127.0.0.1', 'localhost'}
    if os.getenv('WORKBENCH_ALLOW_TEST_HOST') == '1':
        allowed_hosts.add('testserver')
    if request.headers.get('sec-fetch-site', '').strip().lower() == 'cross-site':
        return JSONResponse(status_code=403, content={"detail": "Local same-origin access only"})
    if host not in allowed_hosts or (origin and urlsplit(origin).netloc != request.headers.get('host')):
        return JSONResponse(status_code=403, content={"detail": "Local same-origin access only"})
    checked = request.method not in {"GET", "HEAD", "OPTIONS"} and request.url.path not in UNCHECKED_PAGE_PATHS
    marker = PAGE_CONTEXT.set(request.headers.get(CONTEXT_HEADER, "").strip() if checked else "")
    try:
        response = await call_next(request)
    finally:
        PAGE_CONTEXT.reset(marker)
    if ACTIVE.get("state") is not None:
        response.headers[CONTEXT_HEADER] = context_token(ACTIVE)
    return response


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


def automatic_workspace(state_home: Path) -> Path:
    """The session folder used when no workspace is given; adopts earlier sessions once."""
    folder = (state_home / "workspace").resolve()
    folder.mkdir(parents=True, exist_ok=True)
    previous = load_workbench_settings().get("workspace", "")
    if previous:
        try:
            adopt_sessions(state_home, Path(previous).expanduser().resolve(), folder)
        except (OSError, ValueError, shutil.Error):
            pass  # earlier sessions stay where they are; a new session starts
    return folder


def project_key(workspace: Path) -> str:
    return hashlib.sha256(str(workspace).encode()).hexdigest()[:16]


def adopt_sessions(state_home: Path, old: Path, new: Path) -> bool:
    """Copy sessions of a workspace chosen in earlier versions to the automatic folder.

    Rules, materials and chats then stay available; their code index is
    dropped because code is no longer part of any prompt."""
    source = state_home / "projects" / project_key(old)
    target = state_home / "projects" / project_key(new)
    if old == new or not source.is_dir() or target.exists():
        return False
    shutil.copytree(source, target)
    for state_file in target.glob("*/state.json"):
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            data["workspace"], data["files"] = str(new), {}
            write_json_atomically(state_file, data)
    return True


@app.post("/api/setup")
@context_mutation
def setup(request: Setup):
    reject_context_change_while_processing()
    state_home = app_state_home()
    if request.workspace.strip():
        workspace = Path(request.workspace.strip().strip('"')).expanduser().resolve()
        if not workspace.is_dir():
            raise HTTPException(400, ui_message(ACTIVE, 'error.workspace_missing', path=workspace))
    else:
        # The page no longer asks for a folder: sessions live in an empty,
        # automatic folder, so no program or code files reach any prompt.
        workspace = automatic_workspace(state_home)
    if request.state_dir.strip():
        raise StartupError('startup.state_fixed', path=state_home)
    env_file, explicit = effective_env_file(request.env_file)
    try:
        with FARM_ENVIRONMENT.use(env_file, load_dotenv, explicit=explicit) as key:
            validate_farm_endpoint(env_file)
            check_state_directory(state_home)
            state = protect_configuration(ProjectState(state_home, workspace, request.session), env_file)
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
        if data["model"] != model:
            reset_context(data)
        data["model"] = model
        data["state"].data["selected_model"] = model
        data["state"].save()
        save_workbench_settings(data["state"].workspace, data["state"].root.name, model, data.get("language", "zh"))
        return status_data(data)


def activate_local_session(data: dict[str, Any], session_name: str) -> dict:
    with LOCK:
        reject_context_change_while_processing()
        state = protect_configuration(ProjectState(app_state_home(), data["state"].workspace, session_name),
                                      data.get("env_file"))
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
    # A rule preparation or answer holds LOCK for minutes.  Saving the GUI
    # language must not wait for it: while model work runs, setup and session
    # switches are refused, so ACTIVE cannot be replaced underneath us, and the
    # running job uses its own captured copy of the session.
    acquired = LOCK.acquire(blocking=not MODEL_WORK_IN_PROGRESS.is_set())
    try:
        with SETTINGS_GUARD:
            if ACTIVE:
                data = ACTIVE
                data['language'] = language
                save_workbench_settings(data['state'].workspace, data['state'].root.name, data['model'], language)
            else:
                settings = load_workbench_settings()
                settings['language'] = language
                write_json_atomically(workbench_settings_path(), settings)
    finally:
        if acquired:
            LOCK.release()
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
        data = session()
        name = safe_name(request.name.strip())
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
        stamp = datetime.now().astimezone().strftime("chat_%Y%m%d_%H%M%S")
        return activate_local_session(data, stamp)


@app.post("/api/session/pin")
@context_mutation
def pin_session(request: SessionPinRequest):
    reject_context_change_while_processing()
    data = session()
    name = safe_name(request.name.strip())
    target = data["state"].root.parent / name
    if not target.is_dir():
        raise HTTPException(404, ui_message(ACTIVE, 'error.session_missing'))
    saved = ProjectState(app_state_home(), data["state"].workspace, name)
    saved.data["sidebar_pinned"] = bool(request.pinned)
    saved.save()
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
    data = session()
    state = data["state"]
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
            {"maxOutputTokens": MODEL_CHECK_TOKENS, "temperature": 0}, stream=True,
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
        language = request.headers.get('X-Workbench-Language') or ACTIVE.get('language', 'de')
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
    """Legacy endpoint: confirm every supported file below ``folder`` as material.

    The ``codebook`` field is ignored. Classification always uses the globally
    prepared and locked rules, exactly as /api/target does.
    """
    reject_context_change_while_processing()
    return analyze_target(TargetRequest(target=request.folder, selected_paths=["."]))


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
        require_unique_rule_ids(profile.get("draft"), 409)
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
            "files": [scan_report_file(item, reading_hints(data, sources)) for item in sources],
            "classification": bool(codebook_path), "status": status_data(data)}


def scan_report_file(item: dict, hints: dict | None = None) -> dict:
    pages = document_pages(item)
    plan = reading_plan(item, False, hints or {})
    no_text = sum(1 for record in item.get("page_inventory", []) if isinstance(record, dict) and record.get("page_type") == "visual")
    return {"name": item["name"], "chunks": len(item.get("chunks", [])), "bytes": item.get("bytes", 0),
            "material_role": item.get("material_role", "other"),
            "material_role_label": material_role_label(item.get("material_role", "other")),
            "index_cache_status": item.get("index_cache_status", "unknown"),
            "pages_total": len(pages), "pages_no_text": no_text, "plan_read": len(plan["read"]),
            "plan_scope": plan["scope"], "kind_guess": guess_document_kind(item),
            "chunk_limit_reached": len(item.get("chunks", [])) >= MAX_CHUNKS_PER_DOCUMENT,
            "bom_found": bool((hints or {}).get("bom_found"))}


@app.get("/api/scan/report")
def current_scan_report():
    """Rebuild the local scan report of the confirmed materials, e.g. after a page reload.

    Only local index data is used; skipped files of the original scan are not kept."""
    data = session()
    active = list(data["state"].data.get("active_source_ids") or [])
    by_id = {item["id"]: item for item in data["documents"].list()}
    sources = [by_id[source_id] for source_id in active if source_id in by_id]
    target = data["state"].data.get("selected_target") or {}
    return {"sources": len(sources), "skipped": [], "skipped_count": 0, "target_kind": target.get("kind", ""),
            "files": [scan_report_file(item, reading_hints(data, sources)) for item in sources], "restored": True}


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


def codebook_profile_summary(profile: dict) -> dict | None:
    """Which rules are in effect, recorded at the start of a new preparation."""
    if not profile.get("status") or profile.get("status") == "none":
        return None
    return {key: profile.get(key) for key in ("status", "source_name", "source_path", "source_type", "version",
                                              "prepared_at", "locked_at", "parser_model")}


def validated_codebook_model(value: str, fallback: str) -> str:
    model = canonical_model_id(value) or canonical_model_id(fallback)
    try:
        LLMConnector._detect_family(model)
        if not model or any(character.isspace() for character in model) or any(character in model for character in "?#\\"):
            raise ValueError(model)
    except ValueError:
        raise HTTPException(400, ui_message(ACTIVE, 'rulejob.model_invalid', model=model or '—')) from None
    return model


@app.get("/api/codebook/task")
def codebook_task_status():
    """Latest rule preparation (live or final) plus the model the page should offer."""
    task = load_codebook_job()
    profile = load_codebook_profile()
    default = (task or {}).get("model") or profile.get("requested_model") or ""
    return {"task": task, "running": bool(task and task.get("state") == "running"),
            "default_model": default, "recommended_model": CODEBOOK_RECOMMENDED_MODEL,
            "budget": {"unit_output_tokens": CODEBOOK_BUDGET.unit_output_tokens,
                       "max_attempts_per_unit": CODEBOOK_BUDGET.max_attempts_per_unit,
                       "max_total_calls": CODEBOOK_BUDGET.max_total_calls}}


@app.post("/api/codebook/prepare")
def codebook_prepare(request: CodebookPrepareRequest):
    path = safe_file(request.path)
    file_type = CODEBOOK_FILE_TYPES.get(path.suffix.lower())
    if not file_type:
        raise HTTPException(400, ui_message(ACTIVE, 'error.rules_format'))
    session()
    model = validated_codebook_model(request.model, ACTIVE.get("model", ""))
    request_id = request.request_id or (uuid.uuid4().hex if request.background else "")
    data = begin_model_work(request_id)
    try:
        job = CodebookJob(path, file_type, model, request_id, codebook_profile_summary(load_codebook_profile()))
        job.record["context_before"] = context_token(data)
    except BaseException:
        end_model_work(data)
        raise
    if request.background:
        def worker():
            try:
                run_codebook_job(data, job, path, model)
            except Exception:
                pass  # Recorded in the job; the browser reads /api/codebook/task.
        try:
            threading.Thread(target=worker, name="codebook-prepare", daemon=True).start()
        except BaseException as exc:
            job.fail(codebook_failure(exc, job))
            end_model_work(data)
            job.publish()
            raise
        return JSONResponse(status_code=202, content={"task": job.record, "running": True})
    try:
        return run_codebook_job(data, job, path, model)
    except CodebookPrepareError as exc:
        detail = error_copy(HTTPException(400, ui_message(ACTIVE, 'error.rules_prepare', detail=exc.technical or exc.reason)), ACTIVE)
        return JSONResponse(status_code=400, content={'detail': str(detail), **message_payload(detail),
                                                      'failure': job.record.get('failure')})


def rules_changed(data, issue="rules_changed"):
    reset_context(data)
    state = data["state"]
    state.data.pop("bg_context", None)
    state.data["context_issue"] = issue if state.data.get("selected_target") or state.data.get("active_source_ids") else ""
    state.save()


@app.post("/api/codebook/edit")
@context_mutation
def codebook_edit(request: CodebookEditRequest):
    if not request.confirmed:
        raise HTTPException(400, ui_message(ACTIVE, 'error.confirmation'))
    profile = load_codebook_profile()
    if not profile.get('source_path'):
        raise HTTPException(400, ui_message(ACTIVE, 'error.rules_first'))
    if not request.profile_version:
        raise HTTPException(400, ui_message(ACTIVE, 'rules.version_required'))
    if request.profile_version != profile.get('version'):
        raise HTTPException(409, ui_message(ACTIVE, 'rules.version_changed'))
    try:
        draft = parse_codebook_draft(json.dumps(request.draft))
    except ValueError as exc:
        raise HTTPException(400, ui_message(ACTIVE, 'error.rules_invalid', detail=error_copy(exc, ACTIVE))) from exc
    require_unique_rule_ids(draft)
    previous = dict(profile)
    profile['draft'] = draft
    profile['status'] = 'draft'
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
    require_unique_rule_ids(profile["draft"])
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
    # The finished preparation goes too, so the drawer no longer shows it.
    with CODEBOOK_JOB_GUARD:
        if (CODEBOOK_JOB.get("record") or {}).get("state") != "running":
            CODEBOOK_JOB.pop("record", None)
    for stale in (codebook_profile_path(), codebook_job_path()):
        try:
            stale.unlink()
        except FileNotFoundError:
            pass
    # A changed Codebook must not keep classifying with an old profile in the
    # currently open session.  Other sessions are likewise harmless until they
    # explicitly analyse a target again, at which time the global lock is read.
    # With no rules left, reconfirming the materials for ordinary questions is
    # allowed; only a changed-but-unlocked profile requires locking first.
    if ACTIVE:
        rules_changed(ACTIVE, "rules_removed")
    return {"status": "none"}


@app.get("/api/coverage")
def coverage_status():
    return coverage_for_ui(session())


@app.post("/api/coverage")
def create_coverage(request: CoverageRequest = CoverageRequest()):
    data = begin_model_work(request.request_id)
    try:
        with LOCK:
            return prepare_coverage(data, full=request.full)
    finally:
        end_model_work(data)


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
    data = begin_model_work(request.request_id)
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
        end_model_work(data)


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
    data = session()
    reset_context(data)
    data["state"].data.pop("bg_context", None)
    data["state"].data["context_issue"] = ""
    data["state"].save()
    return status_data(data)


@app.post("/api/export/session")
def export_session():
    ensure_current_page()
    target = write_session_export(session())
    return {"path": str(target)}


@app.post("/api/export/bg-analysis")
def export_bg_analysis():
    ensure_current_page()
    data = session()
    target = write_bg_analysis_export(data["state"], data.get("language", "zh"))
    return {"path": str(target)}


@app.post("/api/chat")
def chat(request: ChatRequest):
    if not request.question.strip():
        raise HTTPException(400, ui_message(ACTIVE, 'error.question'))
    data = begin_model_work()
    try:
        with LOCK:
            return call_model(data, request.question.strip(), require_classification=request.require_classification,
                              focus_source_id=request.focus_source_id)
    finally:
        MODEL_WORK_IN_PROGRESS.clear()


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


@app.post("/api/operation/cancel")
def cancel_operation(request: OperationCancelRequest):
    """Stop a running Codebook preparation, coverage, comparison or dossier rebuild."""
    with OPERATION_GUARD:
        control = OPERATIONS.get(request.request_id)
    if control is None:
        raise HTTPException(404, ui_message(ACTIVE, 'error.unknown_task'))
    return {"request_id": request.request_id, "cancelled": bool(control.cancel())}


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
                                            require_classification=request.require_classification,
                                            focus_source_id=request.focus_source_id)
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
        try:
            thread.join()
            with CHAT_TASK_GUARD:
                if task["result"] is None and not isinstance(task.get("error"), dict):
                    detail = ui_message(data, "error.worker_failed")
                    task["error"] = {"type": "error", "code": "failed", "message": safe_error(str(detail)),
                                     **message_payload(detail)}
                code = (task.get("error") or {}).get("code", "failed")
                task["state"] = ("completed" if task["result"] is not None else
                                 "cancelled" if code == "cancelled" else
                                 "timed_out" if code == "timeout" else "failed")
                if CHAT_TASK.get("id") == task["id"]:
                    CHAT_TASK.update(task)
        finally:
            with CHAT_TASK_GUARD:
                task["done"].set()
                if CHAT_TASK.get("id") == task["id"]:
                    CHAT_TASK.update(task)
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
    data = begin_model_work(request.request_id)
    try:
        with LOCK:
            return call_comparison(data, question, models)
    finally:
        end_model_work(data)


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
    if not request.confirmed:
        raise HTTPException(400, ui_message(ACTIVE, 'error.confirmation'))
    data = session()
    pending = data.get("pending", [])
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
                backup = backup_dir / item["path"]
                backup.parent.mkdir(parents=True, exist_ok=True)
                backup.write_bytes(old)
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
            staged.append((path, temp))
            with temp.open('w', encoding='utf-8', newline='') as handle:
                handle.write(item['content'])
                handle.flush()
                os.fsync(handle.fileno())
        for path, temp in staged:
            os.replace(temp, path)
            applied.append(path)
        invalidate_pending(data)
        for path, _ in staged:
            state.refresh_file(state.relative(path))
    except Exception:
        for path in reversed(applied):
            old = originals[path]
            if old is None:
                path.unlink(missing_ok=True)
            else:
                rollback = path.with_name('.' + path.name + '.rollback')
                rollback.write_bytes(old)
                os.replace(rollback, path)
        raise
    finally:
        for _, temp in staged:
            temp.unlink(missing_ok=True)
    return {"applied": len(pending), "backup": str(backup_dir)}


@app.delete("/api/pending")
@context_mutation
def cancel_pending():
    invalidate_pending(session())
    return {"cancelled": True}


HTML = load_frontend_html()

# Embed the packaged catalog without introducing an HTTP endpoint or network call.
HTML = HTML.replace('__WORKBENCH_I18N_JSON__', catalog_script_json())


def main() -> None:
    config = STARTUP_CONFIG
    try:
        # A second double-click on the launcher reuses the running Workbench.
        if running_workbench(config.port):
            print(f"Bosch Assembly Assistant is already running: {workbench_url(config.port)}", flush=True)
            if config.open_browser:
                webbrowser.open(workbench_url(config.port))
            return
        with FARM_ENVIRONMENT.use(config.env_file, load_dotenv, explicit=config.env_explicit):
            validate_farm_endpoint(config.env_file)
            check_state_directory(app_state_home())
            check_port(config.port)
        print(f"Bosch Assembly Assistant: {workbench_url(config.port)}", flush=True)
        if config.open_browser:
            open_browser_when_ready(config.port)
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

