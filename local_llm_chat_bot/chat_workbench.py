"""Local browser workbench for the Bosch Farm code/document chat.

Run only on 127.0.0.1.  The browser is a local UI: paths, indexes, source
files, credentials and session data stay on the computer that starts it.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import shutil
import threading
from queue import Empty, Queue
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
import uvicorn

from dotenv import load_dotenv
from code_chat_agent import (PricingCatalog, ProjectState, SYSTEM, ensure_relative,
                             excerpt, parse_json, prompt_for, safe_name, sha256)
from local_document_library import (LocalDocumentLibrary, SUPPORTED_DOCUMENT_EXTENSIONS,
                                    material_is_recommended, material_role, material_role_label)
from llm_connector_with_prompt_caching import LLMConnector


app = FastAPI(title="Bosch Local Workbench", docs_url=None, redoc_url=None)
LOCK = threading.Lock()
ACTIVE: dict[str, Any] = {}

# Retain existing local settings/sessions made by early workbench releases,
# while never sending their obsolete dotted Farm IDs to the endpoint again.
MODEL_ID_MIGRATIONS = {"claude-haiku-5.5": "claude-haiku-5-5"}


def canonical_model_id(value: Any) -> str:
    model = str(value or "").strip()
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


def load_codebook_profile() -> dict:
    try:
        data = json.loads(codebook_profile_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_codebook_profile(profile: dict) -> None:
    app_state_home().mkdir(parents=True, exist_ok=True)
    codebook_profile_path().write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")


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
    for item in items:
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
        keep = sorted(records, key=lambda key: str(records[key].get("updated_at", "")), reverse=True)[:100]
        records = {key: records[key] for key in keep}
    material_selections_path().write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def load_model_tests() -> dict[str, dict]:
    try:
        data = json.loads(model_tests_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_model_test(result: dict) -> None:
    app_state_home().mkdir(parents=True, exist_ok=True)
    records = load_model_tests()
    records[str(result["requested_model"])] = result
    model_tests_path().write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


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
    app_state_home().mkdir(parents=True, exist_ok=True)
    workbench_settings_path().write_text(
        json.dumps({"workspace": str(workspace), "session": session_name, "model": canonical_model_id(model), "language": normalize_language(language)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


class Setup(BaseModel):
    workspace: str
    state_dir: str
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
    question: str


class CompareRequest(BaseModel):
    question: str
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
        raise HTTPException(400, "请先设置工作区。")
    return ACTIVE


def status_data(data: dict[str, Any]) -> dict[str, Any]:
    state = data["state"]
    usage = state.data["usage"]
    return {
        "workspace": str(state.workspace), "model": data["model"], "session": state.data["session_id"][:8],
        "session_name": state.root.name,
        "code_files": len(state.data["files"]), "documents": len(data["documents"].list()),
        "requests": usage["requests"], "input_tokens": usage["input"], "output_tokens": usage["output"],
        "cost": round(float(usage.get("estimated_cost_usd", 0)), 6),
        "bg_context": state.data.get("bg_context"),
    }


def session_list_item(root: Path) -> dict[str, Any]:
    """Small, local-only metadata for the ChatGPT-style session sidebar."""
    state_file = root / "state.json"
    data: dict[str, Any] = {}
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
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
        raise HTTPException(400, f"文件不存在：{path}")
    return path


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
        try:
            path = Path(value).expanduser().resolve()
            path.relative_to(folder)
        except (OSError, ValueError):
            continue
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_DOCUMENT_EXTENSIONS:
            continue
        key = str(path)
        if key not in seen:
            selected.append(path); seen.add(key)
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
        raise ValueError("模型没有返回 Codebook JSON")
    draft = json.loads(text[start:end + 1])
    if not isinstance(draft, dict) or not isinstance(draft.get("classes"), list):
        raise ValueError("Codebook JSON 缺少 classes 列表")
    classes = []
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
                                   "pages": [int(page) for page in value.get("pages", []) if str(page).isdigit()]})
            return result
        name = item["name"].strip()
        key = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-") or "class"
        classes.append({
            "name": name, "definition": str(item.get("definition", "")).strip(),
            "decision_rules": rules(item.get("decision_rules", []), f"{key}-rule"),
            "boundaries": rules(item.get("boundaries", []), f"{key}-boundary"),
            "evidence_pages": [int(page) for page in item.get("evidence_pages", []) if str(page).isdigit()],
        })
    if not classes:
        raise ValueError("Codebook JSON 未包含有效类别")
    def profile_rules(values, prefix):
        result = []
        for index, value in enumerate(values if isinstance(values, list) else [], start=1):
            if isinstance(value, str): result.append({"id": f"{prefix}-{index}", "text": value, "pages": []})
            elif isinstance(value, dict) and str(value.get("text", "")).strip():
                result.append({"id": str(value.get("id") or f"{prefix}-{index}"), "text": str(value["text"]).strip(),
                               "pages": [int(page) for page in value.get("pages", []) if str(page).isdigit()],
                               "table": value.get("table") if isinstance(value.get("table"), dict) else None})
        return result
    return {"classes": classes, "global_rules": profile_rules(draft.get("global_rules", []), "global"),
            "table_rules": profile_rules(draft.get("table_rules", []), "table"), "uncertainties": draft.get("uncertainties", [])}


CODEBOOK_PAGE_SYSTEM = """You transcribe exactly one technical classification Codebook page using supplied native text, OCR text and the full-page image. Return ONLY JSON: {\"page\":number,\"official_names\":[\"exact wording\"],\"definitions\":[\"...\"],\"decision_rules\":[\"...\"],\"boundaries\":[\"...\"],\"tables\":[{\"title\":\"...\",\"columns\":[\"...\"],\"rows\":[[\"cell\"]]}],\"uncertainties\":[\"...\"]}. Preserve table row/column meaning, do not invent text, and use the page number supplied in the prompt."""
CODEBOOK_MERGE_SYSTEM = """You consolidate page-by-page Codebook transcriptions. Return ONLY JSON: {\"classes\":[{\"name\":\"exact official class name\",\"definition\":\"...\",\"decision_rules\":[{\"id\":\"class-rule-1\",\"text\":\"...\",\"pages\":[1]}],\"boundaries\":[{\"id\":\"class-boundary-1\",\"text\":\"...\",\"pages\":[1]}],\"evidence_pages\":[1]}],\"global_rules\":[{\"id\":\"global-1\",\"text\":\"...\",\"pages\":[1]}],\"table_rules\":[{\"id\":\"table-1\",\"text\":\"meaning of the table rule\",\"pages\":[1],\"table\":{\"columns\":[\"...\"],\"rows\":[[\"...\"]]}}],\"uncertainties\":[\"...\"]}. Preserve exact names, rule IDs and page numbers. Do not invent missing rules."""
CODEBOOK_JSON_REPAIR_SYSTEM = """Return ONLY one complete, valid JSON object. Do not use Markdown fences or commentary. Preserve every fact, class name, rule, table value and page number from the supplied candidate; only repair JSON syntax such as missing commas, quotes, brackets or escaping."""


def parse_codebook_draft_with_repair(connector: LLMConnector, raw: str) -> tuple[dict, dict | None]:
    """Parse the final Codebook JSON, making one syntax-only repair attempt if needed."""
    try:
        return parse_codebook_draft(raw), None
    except (ValueError, json.JSONDecodeError) as initial_error:
        repair_prompt = (
            "The candidate Codebook JSON below could not be parsed. Repair its JSON syntax only; "
            "do not summarize, add, omit, translate, or change any factual content.\n"
            f"Parser error: {initial_error}\n\n--- CANDIDATE JSON ---\n{raw}"
        )
        repaired = connector.ask_about_files([], repair_prompt, CODEBOOK_JSON_REPAIR_SYSTEM,
                                             {"maxOutputTokens": 4096, "temperature": 0}, stream=True)
        repair_usage = connector.get_last_token_usage() or {}
        try:
            return parse_codebook_draft(repaired), repair_usage
        except (ValueError, json.JSONDecodeError) as repair_error:
            raise ValueError(f"Codebook JSON 自动修复后仍无效：{repair_error}") from initial_error


def prepare_codebook_profile(data: dict[str, Any], path: Path, model: str) -> dict:
    document = data["documents"].add(str(path))
    connector = LLMConnector(model, data["llm"].api_key, session_id=f"codebook_{os.urandom(6).hex()}")
    ocr_runtime = data["documents"].ocr_runtime_status() if path.suffix.lower() == ".pdf" else {"available": False, "status": "not applicable to DOCX"}
    records = data["documents"].codebook_page_records(path, app_state_home() / "codebook_visual_cache") if path.suffix.lower() == ".pdf" else []
    groups, notes, usages = codebook_page_groups(document), [], []
    if not records and not groups:
        raise HTTPException(400, "Codebook 没有可读取的页面。")
    if records:
        for record in records:
            prompt = f"Codebook page {record['page']} of {len(records)}. Page type: {record['page_type']}.\n--- NATIVE TEXT ---\n{record['native_text'] or '[none]'}\n--- OCR TEXT ({record['ocr_status']}) ---\n{record['ocr_text'] or '[none]'}"
            raw = connector.ask_about_files([record["image_path"]], prompt, CODEBOOK_PAGE_SYSTEM, {"maxOutputTokens": 2200, "temperature": 0}, stream=True)
            notes.append(raw); usages.append(connector.get_last_token_usage() or {})
    else:
        for index, group in enumerate(groups, start=1):
            prompt = f"Codebook DOCX section {index}/{len(groups)}.\n" + "\n\n".join(f"--- {item['label']} ---\n{item['text']}" for item in group)
            raw = connector.ask_about_files([], prompt, CODEBOOK_PAGE_SYSTEM, {"maxOutputTokens": 2200, "temperature": 0}, stream=True)
            notes.append(raw); usages.append(connector.get_last_token_usage() or {})
    merge_prompt = "Consolidate every Codebook page note below. All classes, tables and boundary rules must be retained.\n\n" + "\n\n".join(
        f"--- PAGE GROUP {index} ---\n{note}" for index, note in enumerate(notes, start=1))
    merged = connector.ask_about_files([], merge_prompt, CODEBOOK_MERGE_SYSTEM, {"maxOutputTokens": 3500, "temperature": 0}, stream=True)
    usages.append(connector.get_last_token_usage() or {})
    draft, repair_usage = parse_codebook_draft_with_repair(connector, merged)
    if repair_usage is not None:
        usages.append(repair_usage)
    usage = summarize_usage(usages)
    estimate = data["pricing"].estimate(connector.last_response_model or model, usage["input"], usage["output"])
    usage["cost_usd"] = float(estimate["cost_usd"]) if estimate else None
    page_numbers = {((item.get("visual") or {}).get("page")) for group in groups for item in group}
    page_count = len([number for number in page_numbers if isinstance(number, int)]) or len(document.get("chunks", []))
    return {"status": "draft", "source_path": str(path), "source_name": path.name, "sha256": file_digest(path),
            "prepared_at": datetime.now().astimezone().isoformat(timespec="seconds"), "parser_model": connector.last_response_model or model,
            "page_count": len(records) or page_count,
            "page_groups": len(records) or len(groups), "usage": usage, "draft": draft, "document_id": document["id"],
            "page_records": [{key: record[key] for key in ("page", "page_type", "ocr_status", "embedded_image_count")} for record in records],
            "page_transcriptions": notes, "ocr_runtime": ocr_runtime}


def summarize_usage(records: list[dict]) -> dict[str, int | float]:
    summary: dict[str, int | float] = {
        "input": 0, "output": 0, "total": 0, "reasoning": 0,
        "gemini_thinking": 0, "cache_read": 0, "cache_write": 0,
    }
    for usage in records:
        if not isinstance(usage, dict):
            continue
        def number(value) -> int:
            try:
                return int(value or 0)
            except (TypeError, ValueError):
                return 0
        summary["input"] += number(usage.get("input_tokens"))
        summary["output"] += number(usage.get("output_tokens"))
        summary["total"] += number(usage.get("total_tokens")) or (number(usage.get("input_tokens")) + number(usage.get("output_tokens")))
        summary["cache_read"] += number(usage.get("cache_read_input_tokens"))
        summary["cache_write"] += number(usage.get("cache_creation_input_tokens"))
        detail = usage.get("completion_tokens_details") or usage.get("output_tokens_details") or {}
        if isinstance(detail, dict):
            summary["reasoning"] += number(detail.get("reasoning_tokens"))
        summary["gemini_thinking"] += number(usage.get("thoughtsTokenCount"))
    return summary


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
        "- 累计预估费用：$" + f"{float(usage.get('estimated_cost_usd', 0)):.6f}",
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
        raise HTTPException(400, "当前会话还没有可导出的 Baugruppe 分析结果。")
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
        "- 本轮预估费用：$" + format(float(token.get("cost_usd", 0)), ".6f"),
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
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": MATERIAL_SUMMARY_CACHE_VERSION, "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
               "sha256": document.get("sha256"), "model": model, "full": full, "pages": read_pages,
               "record": record}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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


def prepare_bg_dossier(data: dict[str, Any], coverage: dict) -> tuple[dict | None, dict | None, bool]:
    """Consolidate reusable per-file facts once; raw evidence remains query-specific."""
    cached = load_bg_dossier_cache(coverage, data["model"])
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
    raw = data["llm"].ask_about_files([], request, system_prompt, {"maxOutputTokens": 2400, "temperature": 0}, stream=True).strip()
    usage = data["llm"].get_last_token_usage() or {}
    dossier = {"version": BG_DOSSIER_CACHE_VERSION, "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
               "identity": bg_dossier_identity(coverage, data["model"]), "model": data["model"],
               "summary": raw, "source_files": [{"name": item.get("name"), "sha256": item.get("sha256"),
                                                     "pages_read": item.get("pages_read", [])} for item in records],
               "cache_status": "created"}
    path = bg_dossier_cache_path(coverage, data["model"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dossier, ensure_ascii=False, indent=2), encoding="utf-8")
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
    coverage_path(state).write_text(json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8")


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


def prepare_coverage(data: dict[str, Any], full: bool = False, progress=None) -> dict:
    """Prepare auditable, document-aware evidence before a BG classification question."""
    state, documents, llm = data["state"], data["documents"], data["llm"]
    active_ids = state.data.get("active_source_ids") or []
    selected = [item for item in documents.list() if item.get("id") in active_ids]
    if not selected:
        raise HTTPException(400, "请先选择一个要分析的文件或文件夹。")
    records, total_calls, reused_files, created_files = [], 0, 0, 0
    previous_report = load_coverage(state)
    previous_records = {(item.get("id"), item.get("sha256")): item for item in previous_report.get("files", [])
                        if isinstance(item, dict)} if previous_report.get("model") == data["model"] and previous_report.get("requested_full_coverage") is full else {}
    summary_system = "You are a careful technical evidence extractor. Use only the supplied file content. Write concise Chinese factual notes. Do not classify the Baugruppe and do not invent missing information."
    total_documents = len(selected)
    for file_index, document in enumerate(selected, start=1):
        if progress:
            progress("reading", f"正在读取并理解文件 {file_index}/{total_documents}：{document['name']}",
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
                           "full_coverage": not unread_pages, "reading_scope": reading_scope,
                           "dfc_structure": documents.dfc_audit(document), "cache_status": "reused"})
            records.append(record)
            reused_files += 1
            if progress:
                progress("reading", f"已复用 {file_index}/{total_documents}：{document['name']} 的本地理解结果",
                         12 + int(file_index / max(total_documents, 1) * 48))
            continue
        groups = summary_groups(document, read_chunks)
        notes, failures = [], []
        for number, group in enumerate(groups, start=1):
            try:
                if progress:
                    progress("reading", f"正在理解 {document['name']}（文本组 {number}/{len(groups)}）",
                             12 + int((file_index - 1 + number / max(len(groups), 1)) / max(total_documents, 1) * 48))
                raw = llm.ask_about_files([], f"文件：{document['name']}。这是第 {number}/{len(groups)} 个完整文本片段组。提取结构、部件、驱动、运动、接口、尺寸和不确定处，并保留页面/表格标签。\n\n{group}",
                                         summary_system, {"maxOutputTokens": 900, "temperature": 0}, stream=True)
                notes.append(raw.strip())
                usage = llm.get_last_token_usage() or {}
                state.note_usage(usage, data["pricing"], data["model"])
                total_calls += 1
            except Exception as exc:
                failures.append(f"组 {number}: {exc}")
        if notes and len(notes) > 1:
            try:
                merged = "\n\n".join(f"[片段组 {i}]\n{note}" for i, note in enumerate(notes, start=1))
                raw = llm.ask_about_files([], f"请将下列同一文件的全部片段笔记合成为一份不遗漏冲突或不确定处的技术摘要。必须保留证据标签。\n\n文件：{document['name']}\n\n{merged}",
                                         summary_system, {"maxOutputTokens": 1400, "temperature": 0}, stream=True)
                summary = raw.strip()
                usage = llm.get_last_token_usage() or {}
                state.note_usage(usage, data["pricing"], data["model"])
                total_calls += 1
            except Exception as exc:
                summary = "\n\n".join(notes); failures.append(f"汇总: {exc}")
        else:
            summary = notes[0] if notes else ""
        record = {"id": document["id"], "name": document["name"], "path": document["path"],
                  "sha256": document.get("sha256"), "pages_total": len(document_pages(document)),
                  "pages_read": read_pages, "pages_unread": unread_pages,
                  "full_coverage": not unread_pages,
                  "text_chunks_total": len(document.get("chunks", [])), "text_chunks_selected": len(read_chunks),
                  "reading_scope": reading_scope, "text_groups_total": len(groups),
                  "text_groups_processed": len(notes), "complete": bool(notes) and not failures,
                  "failures": failures, "dfc_structure": documents.dfc_audit(document), "summary": summary,
                  "cache_status": "created"}
        records.append(record)
        if record["complete"]:
            save_material_summary_cache(document, data["model"], full, read_pages, record)
            created_files += 1
        if progress:
            progress("reading", f"已完成 {file_index}/{total_documents}：{document['name']}",
                     12 + int(file_index / max(total_documents, 1) * 48))
    report = {"created_at": datetime.now().astimezone().isoformat(timespec="seconds"), "model": data["model"], "requested_full_coverage": full,
              "files": records, "complete": all(item["complete"] for item in records), "model_calls": total_calls,
              "reused_files": reused_files, "created_files": created_files}
    coverage_path(state).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
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
    words = {word for word in re.findall(r"[\wäöüß-]{3,}", question.casefold())}
    candidates = []
    groups = list(profile.get("global_rules", [])) + list(profile.get("table_rules", []))
    for cls in profile.get("classes", []):
        if isinstance(cls, dict):
            groups.extend(cls.get("decision_rules", [])); groups.extend(cls.get("boundaries", []))
    for rule in groups:
        if not isinstance(rule, dict):
            continue
        pages = [int(page) for page in rule.get("pages", []) if str(page).isdigit()]
        if not pages:
            continue
        text = str(rule.get("text", ""))
        score = sum(word in text.casefold() for word in words)
        candidates.append((score, pages, str(rule.get("id", "rule")), text))
    candidates.sort(key=lambda item: (-item[0], item[2]))
    selected, seen = [], set()
    for _score, pages, rule_id, text in candidates:
        for page in pages:
            if page in seen:
                continue
            selected.append({"id": "locked-codebook-page", "name": path.name,
                             "label": f"{path.name} — Codebook rule {rule_id}, page {page}",
                             "text": text, "visual": {"kind": "pdf_page", "path": str(path), "page": page}})
            seen.add(page)
            if len(selected) >= maximum_pages:
                return selected
    return selected


def validate_classification(action: dict, evidence: list[dict], codebook: str, profile: dict | None = None) -> str | None:
    """Validate the machine-readable part without judging technical correctness."""
    classification = action.get("classification")
    if not isinstance(classification, dict):
        return "缺少 classification 对象"
    label = classification.get("label")
    if not isinstance(label, str) or not label.strip():
        return "缺少类别 label"
    if codebook and label.casefold() not in codebook.casefold():
        return "类别名称未在当前 Codebook 中找到"
    if classification.get("confidence") not in {"high", "medium", "low"}:
        return "confidence 必须为 high、medium 或 low"
    evidence_labels = classification.get("evidence_labels")
    supplied = {str(item.get("label", "")) for item in evidence}
    if not isinstance(evidence_labels, list) or not evidence_labels:
        return "缺少 evidence_labels"
    if not all(isinstance(item, str) and item in supplied for item in evidence_labels):
        return "evidence_labels 必须完全匹配本轮提供的证据标签"
    rule_ids = classification.get("codebook_rule_ids")
    known_rules = set()
    for group in ((profile or {}).get("global_rules", []), (profile or {}).get("table_rules", [])):
        known_rules.update(str(item.get("id")) for item in group if isinstance(item, dict))
    for item in (profile or {}).get("classes", []):
        if isinstance(item, dict):
            for group in (item.get("decision_rules", []), item.get("boundaries", [])):
                known_rules.update(str(rule.get("id")) for rule in group if isinstance(rule, dict))
    if known_rules and (not isinstance(rule_ids, list) or not rule_ids or not all(str(item) in known_rules for item in rule_ids)):
        return "codebook_rule_ids 必须引用锁定 Codebook 中实际存在的规则 ID"
    if known_rules and (not isinstance(classification.get("codebook_rule_pages"), list) or not classification["codebook_rule_pages"]):
        return "缺少 codebook_rule_pages"
    if not isinstance(classification.get("bg_evidence_pages"), list) or not classification["bg_evidence_pages"]:
        return "缺少 bg_evidence_pages"
    alternative = classification.get("alternative_label", "")
    if alternative and (not isinstance(alternative, str) or (codebook and alternative.casefold() not in codebook.casefold())):
        return "备选类别未在当前 Codebook 中找到"
    uncertainties = classification.get("uncertainties", [])
    if not isinstance(uncertainties, list) or not all(isinstance(item, str) for item in uncertainties):
        return "uncertainties 必须为文字列表"
    return None


def classification_repair_prompt(base_prompt: str, reason: str) -> str:
    return base_prompt + f"""

IMPORTANT: Your preceding classification response was rejected locally: {reason}.
Return the complete JSON action again, with a valid `classification` object. Do not omit any required fields. Copy the exact class name and rule IDs from the supplied Codebook and copy evidence_labels exactly from the supplied document labels. Include separate codebook_rule_pages and bg_evidence_pages. Do not add commentary outside JSON.
"""


def call_model(data: dict[str, Any], question: str, progress=None) -> dict[str, Any]:
    state, documents, llm = data["state"], data["documents"], data["llm"]
    def report(phase: str, text: str, percent: int | None = None) -> None:
        if progress:
            progress(phase, text, percent)

    report("search", "正在检查当前材料与已有理解结果…", 5)
    bg_context = state.data.get("bg_context")
    active_source_ids = state.data.get("active_source_ids")
    matches = state.search(question)
    snippets = {item: excerpt(state, item, question) for item in matches}
    preferred = ([bg_context.get("codebook_id")] + list(bg_context.get("source_ids", []))) if bg_context else active_source_ids
    allowed = list(bg_context.get("source_ids", [])) + [bg_context.get("codebook_id")] if bg_context else active_source_ids
    report("search", "正在检索与当前问题相关的本地证据…", 10)
    evidence = documents.search(question, preferred_ids=preferred, classification=bool(bg_context), allowed_ids=allowed)
    if bg_context:
        existing = {(item.get("visual") or {}).get("page") for item in evidence if item.get("name") == bg_context.get("codebook_name")}
        evidence.extend(item for item in relevant_codebook_page_evidence(question, bg_context) if (item.get("visual") or {}).get("page") not in existing)
    report("search", "正在核对文字、OCR 与视觉证据…", 12)
    evidence = documents.ensure_ocr_for_snippets(evidence, question, classification=bool(bg_context))
    visuals = documents.visual_paths(evidence, state.root / "visual_cache",
                                     bilder_images=documents.bilder_image_paths(allowed))
    reasoning, notices = [], []
    visual_report = documents.last_visual_report
    if visual_report.get("short_drawings"):
        names = "、".join(str(name) for name in visual_report["short_drawings"])
        notices.append(f"图纸视觉证据：已将短图纸 {names} 的全部页转为压缩 JPEG；本轮附件 {visual_report.get('attachments', 0)} 个，约 {int(visual_report.get('bytes', 0)) // 1024} KB。")
    if visual_report.get("image_groups"):
        notices.append("Bilder 图片组：" + "；".join(str(item) for item in visual_report["image_groups"]) + "。")
    if visual_report.get("dfc"):
        for item in visual_report["dfc"]:
            parts = "、".join(str(part) for part in item.get("segments_used", [])) or "无"
            notices.append(f"DFC Struktur：{item.get('name')} · OCR {item.get('ocr_status')} · 已发送第 {parts} 段（共 {item.get('segments_total', 0)} 段）。")
    if visual_report.get("skipped"):
        notices.append("部分视觉附件因本轮总大小预算未发送；文字证据仍已保留。")

    def events(kind: str, text: str):
        if kind == "reasoning": reasoning.append(text)
        elif kind == "notice": notices.append(text)

    coverage = load_coverage(state)
    auto_prepared = False
    classification_request = bool(bg_context) and needs_bg_preparation(question, bg_context)
    # Once a material range is confirmed as a Baugruppe, its first question
    # should transparently prepare the shared understanding, even if the user
    # phrases it as a natural question rather than using a classification word.
    preparation_request = bool(bg_context)
    if not coverage_matches_current_selection(data, coverage) and preparation_request:
        report("reading", "正在进行文件的读取与理解…", 12)
        coverage = prepare_coverage(data, progress=report)
        auto_prepared = True
        report("reading", "文件读取与理解完成。", 62)
    elif preparation_request:
        report("reading", "已复用当前材料的读取与理解结果。", 62)
    coverage_summaries = coverage.get("files", []) if coverage.get("complete") else []
    dossier, usage_records, estimates = None, [], []
    if coverage_summaries:
        try:
            report("dossier", "正在整理 Baugruppe 综合证据档案…", 70)
            dossier, dossier_usage, dossier_created = prepare_bg_dossier(data, coverage)
            if dossier_usage:
                usage_records.append(dossier_usage)
                estimate = state.note_usage(dossier_usage, data["pricing"], data["model"])
                if estimate: estimates.append(estimate)
            if dossier_created:
                notices.append("已生成并保存 BG 综合证据档案；后续追问将复用该档案，仅补充本问题命中的原始证据。")
            elif dossier:
                notices.append("已复用 BG 综合证据档案；本轮未重复发送全部逐文件摘要。")
            report("dossier", "BG 综合证据档案已准备完成。", 80)
        except Exception as exc:
            notices.append(f"BG 综合证据档案未能生成，已回退为逐文件摘要：{exc}")
            dossier = None
    model_prompt = prompt_for(state, question, snippets, document_snippets=evidence, bg_context=bg_context,
                              coverage_summaries=[] if dossier else coverage_summaries, bg_dossier=dossier,
                              response_language=data.get("language", "zh"))
    report("model", f"正在连接 {data['model']} 并提交问题…", 86)
    model_started = False
    def model_events(kind: str, text: str):
        nonlocal model_started
        events(kind, text)
        if not model_started:
            model_started = True
            report("model", "模型正在生成回答…", 92)

    report("model", "正在等待模型输出…", 90)
    raw = llm.ask_about_files(visuals, model_prompt,
                               SYSTEM, {"maxOutputTokens": 4096, "temperature": 0}, stream=True, event_handler=model_events)
    usage_records.append(llm.get_last_token_usage() or {})
    estimate = state.note_usage(usage_records[-1], data["pricing"], data["model"])
    if estimate: estimates.append(estimate)
    def validated_action(raw_response: str, request_prompt: str) -> dict:
        try:
            action = parse_json(raw_response)
            problem = validate_classification(action, evidence, codebook_text(documents, bg_context), (bg_context or {}).get("locked_profile")) if classification_request else None
        except Exception as exc:
            if not classification_request:
                raise
            action, problem = None, str(exc)
        if not problem:
            return action
        notices.append(f"分类 JSON 校验未通过（{problem}），已自动重试一次。")
        report("validation", "正在校验分类证据与 Codebook 规则；模型输出需补全，正在自动重试…", 96)
        repaired = llm.ask_about_files(visuals, classification_repair_prompt(request_prompt, problem),
                                       SYSTEM, {"maxOutputTokens": 4096, "temperature": 0}, stream=True, event_handler=model_events)
        usage_records.append(llm.get_last_token_usage() or {})
        estimate = state.note_usage(usage_records[-1], data["pricing"], data["model"])
        if estimate: estimates.append(estimate)
        action = parse_json(repaired)
        problem = validate_classification(action, evidence, codebook_text(documents, bg_context), (bg_context or {}).get("locked_profile")) if classification_request else None
        if problem:
            raise ValueError(f"自动重试后仍无有效分类 JSON：{problem}")
        notices.append("分类 JSON 已在自动重试后通过校验。")
        return action

    try:
        report("validation", "正在核验模型分类输出…", 96)
        action = validated_action(raw, model_prompt)
    except Exception:
        # Some Bosch Farm models return a normal natural-language answer despite
        # the code-action schema. A read-only question must remain useful:
        # show that answer and never treat it as a file modification.
        answer = raw.strip() or "模型没有返回可显示的文字。"
        title_session_from_question(state, question)
        state.add_turn("user", question)
        state.add_turn("assistant", answer)
        if auto_prepared:
            notices.insert(0, f"已在回答前自动准备 {len(coverage.get('files', []))} 个文件的分类证据（{coverage.get('model_calls', 0)} 次预读调用）。")
        report("complete", "处理完成。", 100)
        return {"answer": answer, "reasoning": "".join(reasoning), "notices": notices,
                "sources": evidence, "dfc_evidence": visual_report.get("dfc", []), "visuals": visuals, "changes": [], "can_export_bg": False,
                "classification": None, "coverage_summary": coverage_summary_for_answer(coverage) if classification_request else None,
                "turn_cost": sum(item["cost_usd"] for item in estimates) if estimates else None,
                "usage": status_data(data)}
    requested = [ensure_relative(item) for item in action.get("read_files", [])[:4] if isinstance(item, str)]
    complete = {}
    for relative in requested:
        path = state.resolve_relative(relative)
        if path.is_file() and path.stat().st_size <= 1_000_000:
            complete[relative] = path.read_text(encoding="utf-8", errors="replace")
            state.refresh_file(relative)
    if complete:
        model_prompt = prompt_for(state, question, snippets, complete, evidence, bg_context,
                                  [] if dossier else coverage_summaries, dossier, data.get("language", "zh"))
        report("model", "正在补充读取模型请求的本地文件并生成回答…", 93)
        raw = llm.ask_about_files(visuals, model_prompt,
                                   SYSTEM, {"maxOutputTokens": 3000, "temperature": 0}, stream=True, event_handler=model_events)
        usage_records.append(llm.get_last_token_usage() or {})
        estimate = state.note_usage(usage_records[-1], data["pricing"], data["model"])
        if estimate: estimates.append(estimate)
        try:
            action = validated_action(raw, model_prompt)
        except Exception as exc:
            notices.append(f"补充读取后的分类输出未通过校验：{exc}；未显示分类结论卡。")
            action = {"answer": raw.strip() or "模型没有返回可显示的文字。", "changes": [], "classification": None}
    changes = build_diff(state, action.get("changes", []))
    data["pending"] = changes
    title_session_from_question(state, question)
    state.add_turn("user", question); state.add_turn("assistant", action.get("answer", ""))
    turn_token_usage = summarize_usage(usage_records)
    turn_token_usage["cost_usd"] = sum(item["cost_usd"] for item in estimates)
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
        notices.insert(0, f"已在回答前自动准备 {len(coverage.get('files', []))} 个文件的分类证据（{coverage.get('model_calls', 0)} 次预读调用）。")
    report("complete", "处理完成。", 100)
    return {"answer": action.get("answer", ""), "reasoning": "".join(reasoning), "notices": notices,
            "sources": evidence, "dfc_evidence": visual_report.get("dfc", []), "visuals": visuals, "changes": [{k: v for k, v in item.items() if k != "content"} for item in changes],
            "can_export_bg": bool(bg_context),
            "turn_usage": turn_token_usage,
            "model_response": llm.last_response_model or data["model"],
            "turn_cost": turn_token_usage["cost_usd"] if estimates else None,
            "classification": action.get("classification") if classification_request else None,
            "coverage_summary": coverage_summary_for_answer(coverage) if classification_request else None,
            "usage": status_data(data)}


def call_comparison(data: dict[str, Any], question: str, models: list[str]) -> dict[str, Any]:
    """Run an isolated, read-only answer for each model against identical BG evidence."""
    state, documents = data["state"], data["documents"]
    bg_context = state.data.get("bg_context")
    if not bg_context:
        raise HTTPException(400, "请先开始 Baugruppe 文件夹分析，再运行多模型对比。")
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
            notices.append(f"短图纸已按全页压缩附件发送（{visual_report.get('attachments', 0)} 个附件，约 {int(visual_report.get('bytes', 0)) // 1024} KB）。")
        if visual_report.get("image_groups"):
            notices.append("Bilder 图片组：" + "；".join(str(item) for item in visual_report["image_groups"]) + "。")
        if visual_report.get("dfc"):
            for item in visual_report["dfc"]:
                parts = "、".join(str(part) for part in item.get("segments_used", [])) or "无"
                notices.append(f"DFC Struktur：{item.get('name')} · OCR {item.get('ocr_status')} · 已发送第 {parts} 段。")
        if visual_report.get("skipped"):
            notices.append("部分视觉附件超出总大小预算，未发送；文字证据仍已保留。")

        def events(kind: str, text: str):
            if kind == "notice":
                notices.append(text)

        try:
            connector = LLMConnector(model, data["llm"].api_key,
                                     session_id=f"{state.data['session_id']}-comparison-{index}")
            raw = connector.ask_about_files(
                visuals, prompt, SYSTEM, {"maxOutputTokens": 4096, "temperature": 0},
                stream=True, event_handler=events,
            )
            usage_records = [connector.get_last_token_usage() or {}]
            actual_model = connector.last_response_model or model
            classification = None
            try:
                action = parse_json(raw)
                problem = validate_classification(action, evidence, codebook_text(documents, bg_context), (bg_context or {}).get("locked_profile"))
                if problem:
                    notices.append(f"分类 JSON 校验未通过（{problem}），已自动重试一次。")
                    raw = connector.ask_about_files(visuals, classification_repair_prompt(prompt, problem), SYSTEM,
                                                     {"maxOutputTokens": 4096, "temperature": 0}, stream=True, event_handler=events)
                    usage_records.append(connector.get_last_token_usage() or {})
                    action = parse_json(raw)
                    problem = validate_classification(action, evidence, codebook_text(documents, bg_context), (bg_context or {}).get("locked_profile"))
                    if problem:
                        raise ValueError(f"自动重试后仍无有效分类 JSON：{problem}")
                    notices.append("分类 JSON 已在自动重试后通过校验。")
                answer = str(action.get("answer", "")).strip() or raw.strip()
                classification = action.get("classification")
            except Exception as exc:
                answer = raw.strip() or "模型没有返回可显示的文字。"
                notices.append(f"未显示该模型的分类结论卡：{exc}")
            token_usage = summarize_usage(usage_records)
            estimate = data["pricing"].estimate(actual_model, token_usage["input"], token_usage["output"])
            token_usage["cost_usd"] = float(estimate["cost_usd"]) if estimate else None
            results.append({"requested_model": model, "model_response": actual_model, "ok": True,
                            "answer": answer, "classification": classification, "usage": token_usage, "notices": notices})
        except Exception as exc:
            results.append({"requested_model": model, "model_response": model, "ok": False,
                            "answer": "", "error": str(exc), "usage": None, "notices": notices})
    return {"question": question, "results": results,
            "sources": [str(item.get("label", item.get("name", "未知来源"))) for item in evidence]}


@app.get("/", response_class=HTMLResponse)
def index():
    return HTML


@app.post("/api/setup")
def setup(request: Setup):
    workspace = Path(request.workspace).expanduser().resolve()
    if not workspace.is_dir(): raise HTTPException(400, f"工作区不存在：{workspace}")
    env_file = Path(__file__).resolve().parent / ".env"
    load_dotenv(env_file)
    key = os.getenv("BOSCH_FARM_SUBSCRIPTION_KEY") or os.getenv("BOSCH_FARM_API_KEY")
    if not key: raise HTTPException(400, f"未在 {env_file} 找到 BOSCH_FARM_SUBSCRIPTION_KEY。")
    state_home = app_state_home()
    state = ProjectState(state_home, workspace, request.session)
    documents = LocalDocumentLibrary(state.root.parent / "documents.json")
    price_file = Path(__file__).resolve().parent / "model_pricing.json"
    language = normalize_language(request.language)
    model = canonical_model_id(request.model)
    ACTIVE.clear(); ACTIVE.update({"state": state, "documents": documents, "model": model, "language": language,
                                    "llm": LLMConnector(model, key, session_id=state.data["session_id"]),
                                    "pricing": PricingCatalog(price_file), "pending": []})
    state.scan()
    state.data["selected_model"] = model
    state.save()
    save_workbench_settings(workspace, state.root.name, model, language)
    return status_data(ACTIVE)


@app.get("/api/status")
def status(): return status_data(session())


@app.post("/api/model")
def switch_model(request: ModelSwitchRequest):
    model = canonical_model_id(request.model)
    if not model:
        raise HTTPException(400, "请输入 Bosch Farm 的准确 Model ID。")
    data = session()
    try:
        data["llm"] = LLMConnector(model, data["llm"].api_key, session_id=data["state"].data["session_id"])
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    data["model"] = model
    data["state"].data["selected_model"] = model
    data["state"].save()
    save_workbench_settings(data["state"].workspace, data["state"].root.name, model, data.get("language", "zh"))
    return status_data(data)


def activate_local_session(data: dict[str, Any], session_name: str) -> dict:
    state = ProjectState(app_state_home(), data["state"].workspace, session_name)
    data["state"] = state
    data["documents"] = LocalDocumentLibrary(state.root.parent / "documents.json")
    data["model"] = canonical_model_id(state.data.get("selected_model") or data["model"])
    data["llm"] = LLMConnector(data["model"], data["llm"].api_key, session_id=state.data["session_id"])
    data["pending"] = []
    save_workbench_settings(state.workspace, state.root.name, data["model"], data.get("language", "zh"))
    return status_data(data)


@app.post("/api/session/rename")
def rename_session(request: SessionRenameRequest):
    data = session()
    name = safe_name(request.name.strip())
    state = data["state"] if not request.source.strip() else ProjectState(app_state_home(), data["state"].workspace, safe_name(request.source.strip()))
    if not state.root.is_dir():
        raise HTTPException(404, "会话不存在。")
    target = state.root.parent / name
    if target == state.root:
        return status_data(data)
    if target.exists():
        raise HTTPException(409, "已存在同名会话。")
    try:
        state.root.rename(target)
    except OSError as exc:
        raise HTTPException(500, f"无法重命名会话：{exc}") from exc
    return activate_local_session(data, name) if state.root == data["state"].root else status_data(data)


@app.post("/api/session/delete")
def delete_session(request: SessionDeleteRequest):
    if not request.confirmed:
        raise HTTPException(400, "必须确认后才可删除会话。")
    data = session()
    state = data["state"] if not request.name.strip() else ProjectState(app_state_home(), data["state"].workspace, safe_name(request.name.strip()))
    if not state.root.is_dir():
        raise HTTPException(404, "会话不存在。")
    current = state.root
    parent = current.parent
    try:
        shutil.rmtree(current)
    except OSError as exc:
        raise HTTPException(500, f"无法删除会话：{exc}") from exc
    remaining = available_sessions(ProjectState(app_state_home(), data["state"].workspace, "default")) if parent.is_dir() else []
    return activate_local_session(data, str(remaining[0]["name"]) if remaining else "default") if current == data["state"].root else status_data(data)


@app.get("/api/settings")
def settings():
    # Only the local path is returned. No source documents or credentials leave this computer.
    return load_workbench_settings()


@app.post("/api/language")
def set_language(request: LanguageRequest):
    language = normalize_language(request.language)
    data = session()
    data["language"] = language
    save_workbench_settings(data["state"].workspace, data["state"].root.name, data["model"], language)
    return {"language": language}


@app.get("/api/sessions")
def sessions(offset: int = 0, limit: int = 10):
    state = session()["state"]
    records = available_sessions(state)
    start, amount = max(0, offset), max(1, min(20, limit))
    return {"current": state.root.name, "sessions": records[start:start + amount], "has_more": start + amount < len(records)}


@app.post("/api/session/open")
def open_saved_session(request: SessionOpenRequest):
    data = session(); name = safe_name(request.name.strip())
    target = data["state"].root.parent / name
    if not target.is_dir():
        raise HTTPException(404, "会话不存在。")
    return activate_local_session(data, name)


@app.post("/api/session/new")
def create_session():
    data = session()
    stamp = datetime.now().astimezone().strftime("新聊天_%Y%m%d_%H%M%S")
    return activate_local_session(data, stamp)


@app.post("/api/session/pin")
def pin_session(request: SessionPinRequest):
    data = session(); name = safe_name(request.name.strip())
    target = data["state"].root.parent / name
    if not target.is_dir():
        raise HTTPException(404, "会话不存在。")
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
            "bg_context": state.data.get("bg_context")}


@app.get("/api/model-tests")
def model_tests():
    return {"tests": load_model_tests()}


@app.post("/api/model-test")
def model_test(request: ModelTestRequest):
    model = request.model.strip()
    if not model:
        raise HTTPException(400, "请输入 Bosch Farm 的准确 Model ID。")
    load_dotenv(Path(__file__).resolve().parent / ".env")
    key = os.getenv("BOSCH_FARM_SUBSCRIPTION_KEY") or os.getenv("BOSCH_FARM_API_KEY")
    if not key:
        raise HTTPException(400, "未找到 BOSCH_FARM_SUBSCRIPTION_KEY。")
    def record(ok: bool, message: str, **extra):
        result = {
            "requested_model": model, "ok": ok, "message": message,
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
        ).strip()
        if answer.startswith(("Error:", "HTTP error")):
            return record(False, answer, model=model, usage=probe.get_last_token_usage() or {})
        usage = probe.get_last_token_usage() or {}
        if any("拒绝流式" in item for item in notices):
            streaming = "自动回退为完整响应"
        elif notices:
            streaming = "连接器使用非流式输出"
        else:
            streaming = "原生流式输出"
        usage_available = bool(usage) and (
            "input_tokens" in usage or "output_tokens" in usage or "total_tokens" in usage
        )
        message = "连接和回答已验证；token usage 已返回。" if usage_available else "连接和回答已验证；网关未返回 token usage。"
        return record(
            True, message,
            model=probe.last_response_model or model, answer=answer[:120], streaming=streaming,
            usage_available=usage_available,
            input_tokens=usage.get("input_tokens", 0), output_tokens=usage.get("output_tokens", 0),
        )
    except Exception as exc:
        return record(False, str(exc), model=model)


@app.get("/api/pick/{kind}")
def pick(kind: str):
    """Use the local Python GUI only as a native path chooser, never for files."""
    if kind not in {"file", "folder"}: raise HTTPException(400, "Unknown picker type")
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
        value = filedialog.askopenfilename(title="选择本地文件") if kind == "file" else filedialog.askdirectory(title="选择本地文件夹")
        root.destroy()
    except Exception as exc:
        raise HTTPException(501, f"无法打开系统选择器；请直接粘贴路径。{exc}") from exc
    return {"path": value}


@app.get("/api/documents")
def documents():
    return [{"id": item["id"], "name": item["name"], "path": item["path"], "chunks": len(item.get("chunks", [])),
             "material_role": item.get("material_role", "other"),
             "material_role_label": material_role_label(item.get("material_role", "other"))}
            for item in session()["documents"].list()]


@app.post("/api/document")
def add_document(request: PathRequest):
    item = session()["documents"].add(str(safe_file(request.path)))
    return {"id": item["id"], "name": item["name"], "chunks": len(item["chunks"]),
            "material_role": item.get("material_role", "other"),
            "material_role_label": material_role_label(item.get("material_role", "other"))}


@app.post("/api/bg")
def activate_bg(request: BGRequest):
    data = session(); codebook = data["documents"].add(str(safe_file(request.codebook)))
    folder = Path(request.folder.strip().strip('"')).expanduser().resolve()
    sources, skipped = data["documents"].add_folder(str(folder))
    data["state"].data["bg_context"] = {"codebook_id": codebook["id"], "codebook_name": codebook["name"],
        "source_ids": [item["id"] for item in sources], "folder": str(folder)}
    data["state"].save()
    return {"sources": len(sources), "skipped": skipped[:10], "status": status_data(data)}


@app.post("/api/target")
def analyze_target(request: TargetRequest):
    """Index one file or explicitly selected files in one folder."""
    data = session()
    target = Path(request.target.strip().strip('"')).expanduser().resolve()
    if target.is_file():
        sources, skipped, target_kind = [data["documents"].add(str(target))], [], "文件"
    elif target.is_dir():
        selected = selected_target_files(target, request.selected_paths)
        if not selected:
            raise HTTPException(400, "请先在文件树中勾选至少一个受支持的文件或文件夹。")
        sources, skipped = [], []
        for path in selected:
            try:
                sources.append(data["documents"].add(str(path)))
            except Exception as exc:
                skipped.append(f"{path.name}: {exc}")
        if not sources:
            raise HTTPException(400, "所选文件均无法读取；请查看扫描报告。")
        save_material_selection(target, selected)
        target_kind = "文件夹"
    else:
        raise HTTPException(400, f"文件或文件夹不存在：{target}")
    profile = load_codebook_profile()
    if profile.get("status") == "locked":
        codebook_path = Path(str(profile.get("source_path", "")))
        if not codebook_path.is_file() or file_digest(codebook_path) != profile.get("sha256"):
            raise HTTPException(409, "已锁定的 Codebook 文件缺失或内容已变化；请重新准备并确认 Codebook。")
        codebook = data["documents"].add(str(codebook_path))
        data["state"].data["bg_context"] = {
            "codebook_id": codebook["id"], "codebook_name": codebook["name"],
            "source_ids": [item["id"] for item in sources], "folder": str(target),
            "locked_profile": profile.get("draft", {}), "codebook_path": str(codebook_path),
        }
    else:
        data["state"].data.pop("bg_context", None)
    data["state"].data["active_source_ids"] = [item["id"] for item in sources]
    data["state"].data["selected_target"] = {
        "path": str(target), "kind": target_kind,
        "selected_paths": [item.relative_to(target).as_posix() for item in selected] if target.is_dir() else [str(target)],
        "codebook_path": str(codebook_path) if profile.get("status") == "locked" else str(data["state"].data.get("selected_codebook_path", "")),
    }
    data["state"].save()
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
        raise HTTPException(400, "请选择一个存在的文件夹后再显示文件树。")
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
    data = session()
    path = safe_file(request.path)
    if path.suffix.lower() not in {".pdf", ".docx"}:
        raise HTTPException(400, "Codebook 目前仅支持 PDF 或 DOCX。")
    model = request.model.strip() or data["model"]
    with LOCK:
        try:
            profile = prepare_codebook_profile(data, path, model)
        except Exception as exc:
            raise HTTPException(400, f"Codebook 准备失败：{exc}") from exc
        save_codebook_profile(profile)
        data["state"].data["selected_codebook_path"] = str(path)
        data["state"].save()
    return profile


@app.post("/api/codebook/lock")
def codebook_lock():
    profile = load_codebook_profile()
    if profile.get("status") != "draft" or not (profile.get("draft") or {}).get("classes"):
        raise HTTPException(400, "请先成功准备 Codebook 草稿。")
    path = Path(str(profile.get("source_path", "")))
    if not path.is_file() or file_digest(path) != profile.get("sha256"):
        raise HTTPException(409, "Codebook 文件已变化；请重新准备。")
    profile["status"] = "locked"
    profile["locked_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    save_codebook_profile(profile)
    if ACTIVE:
        ACTIVE["state"].data["selected_codebook_path"] = str(path)
        ACTIVE["state"].save()
    return profile


@app.delete("/api/codebook")
def codebook_clear():
    try:
        codebook_profile_path().unlink()
    except FileNotFoundError:
        pass
    # A changed Codebook must not keep classifying with an old profile in the
    # currently open session.  Other sessions are likewise harmless until they
    # explicitly analyse a target again, at which time the global lock is read.
    if ACTIVE:
        ACTIVE["state"].data.pop("bg_context", None)
        ACTIVE["state"].save()
    return {"status": "none"}


@app.get("/api/coverage")
def coverage_status():
    return coverage_for_ui(session())


@app.post("/api/coverage")
def create_coverage(request: CoverageRequest = CoverageRequest()):
    with LOCK:
        return prepare_coverage(session(), full=request.full)


@app.get("/api/cache/audit")
def cache_audit_status():
    return cache_audit(session())


@app.post("/api/cache/file/rebuild")
def rebuild_cached_file(request: CacheFileRequest):
    if not request.confirmed:
        raise HTTPException(400, "必须确认后才会清除该文件的摘要缓存。")
    data = session()
    document = next((item for item in data["documents"].list() if item.get("id") == request.document_id), None)
    if not document:
        raise HTTPException(404, "当前材料范围中找不到该文件。")
    target = app_state_home() / "material_cache" / str(document.get("sha256") or "")
    if target.is_dir():
        shutil.rmtree(target)
    invalidate_current_coverage(data["state"], str(document["id"]))
    return {"message": f"已清除 {document['name']} 的本地摘要；下次分类会只重读该文件。", "audit": cache_audit(data)}


@app.post("/api/cache/dossier/rebuild")
def rebuild_bg_dossier(request: CacheConfirmRequest):
    if not request.confirmed:
        raise HTTPException(400, "必须确认后才会重新生成 BG 综合证据档案。")
    data = session(); coverage = load_coverage(data["state"])
    if not coverage_matches_current_selection(data, coverage):
        raise HTTPException(409, "当前材料尚未完成预读；请先准备分类证据。")
    path = bg_dossier_cache_path(coverage, data["model"])
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    with LOCK:
        dossier, usage, _created = prepare_bg_dossier(data, coverage)
    if usage:
        data["state"].note_usage(usage, data["pricing"], data["model"])
    return {"message": "BG 综合证据档案已重新生成。", "dossier": dossier,
            "usage": summarize_usage([usage or {}]), "audit": cache_audit(data)}


@app.post("/api/cache/clear")
def clear_summary_caches(request: CacheConfirmRequest):
    if not request.confirmed:
        raise HTTPException(400, "必须确认后才会清除本地摘要缓存。")
    for name in ("material_cache", "bg_dossier_cache"):
        target = app_state_home() / name
        if target.is_dir():
            shutil.rmtree(target)
    # Keep local source indexes/OCR derivatives intact; only model-generated
    # summaries and dossiers are cleared.  The current report is marked stale.
    invalidate_current_coverage(session()["state"])
    return {"message": "已清除本地材料摘要和 BG 综合档案；索引与 OCR 缓存保留。", "audit": cache_audit(session())}


@app.delete("/api/bg")
def clear_bg():
    data = session(); data["state"].data.pop("bg_context", None); data["state"].save(); return status_data(data)


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
    if not request.question.strip(): raise HTTPException(400, "请输入问题。")
    with LOCK: return call_model(session(), request.question.strip())


@app.post("/api/chat/stream")
def chat_stream(request: ChatRequest):
    """Expose local processing stages to the browser while retaining one serialized model call."""
    question = request.question.strip()
    if not question:
        raise HTTPException(400, "请输入问题。")
    events: Queue[dict[str, Any]] = Queue()

    def publish(phase: str, text: str, percent: int | None = None) -> None:
        events.put({"type": "progress", "phase": phase, "text": text, "percent": percent})

    def worker() -> None:
        try:
            with LOCK:
                result = call_model(session(), question, progress=publish)
            events.put({"type": "result", "data": result})
        except Exception as exc:
            events.put({"type": "error", "message": str(exc)})
        finally:
            events.put({"type": "end"})

    threading.Thread(target=worker, daemon=True).start()

    def event_stream():
        while True:
            try:
                event = events.get(timeout=15)
            except Empty:
                yield ": keep-alive\n\n"
                continue
            yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
            if event.get("type") == "end":
                break

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/compare")
def compare(request: CompareRequest):
    question = request.question.strip()
    models = list(dict.fromkeys(model.strip() for model in request.models if model and model.strip()))
    if not question:
        raise HTTPException(400, "请输入同一条要对比的问题。")
    if not 2 <= len(models) <= 4:
        raise HTTPException(400, "请勾选 2 到 4 个模型。")
    with LOCK:
        return call_comparison(session(), question, models)


@app.post("/api/apply")
def apply():
    data = session(); pending = data.get("pending", [])
    if not pending: raise HTTPException(400, "没有待应用的修改。")
    state = data["state"]
    for item in pending:
        path = state.resolve_relative(item["path"])
        current = sha256(path.read_bytes()) if path.exists() else None
        if current != item["before"]: raise HTTPException(409, f"{item['path']} 在显示 diff 后已改变。")
    for item in pending:
        path = state.resolve_relative(item["path"]); path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(item["content"], encoding="utf-8", newline=""); state.refresh_file(item["path"])
    count = len(pending); data["pending"] = []
    return {"applied": count}


HTML = r'''<!doctype html><html lang="zh"><head><meta charset="utf-8"><title>Bosch Local Workbench</title>
<style>
*{box-sizing:border-box}:root{--left-panel-width:270px}body{margin:0;background:#111827;color:#e5e7eb;font:14px Inter,Segoe UI,Arial,sans-serif}button,input,select{font:inherit}button{background:#2563eb;color:white;border:0;border-radius:7px;padding:8px 10px;cursor:pointer}button.ghost{background:#263244;color:#cbd5e1}.shell{height:100vh;display:grid;grid-template-columns:var(--left-panel-width) 8px minmax(420px,1fr) 300px}.side{background:#172033;border-right:1px solid #334155;padding:16px;overflow:auto}.splitter{cursor:col-resize;background:#334155;touch-action:none;transition:background .15s}.splitter:hover,.splitter.dragging{background:#38bdf8}.right{border-left:1px solid #334155;border-right:0}.main{display:flex;flex-direction:column;min-width:0}.brand{font-weight:700;font-size:16px;margin-bottom:16px}.muted{color:#94a3b8;font-size:12px}.field{margin:10px 0}.field label{display:block;font-size:12px;color:#a9b6c8;margin-bottom:5px}input{width:100%;background:#0f172a;border:1px solid #3b4960;border-radius:6px;padding:8px;color:#f8fafc}.row{display:flex;gap:7px}.row>*{min-width:0}.row input{flex:1}.chat{flex:1;overflow:auto;padding:24px max(32px,8%)}.message{max-width:920px;margin:0 auto 18px;padding:13px 15px;border-radius:10px;white-space:pre-wrap;line-height:1.55}.user{background:#1e3a5f;margin-left:auto;max-width:78%}.assistant{background:#1e293b}.reason{margin:8px auto 18px;max-width:920px;background:#171e2d;border:1px solid #334155;border-radius:8px;padding:9px}.reason summary{cursor:pointer;color:#b9c9e2}.reason pre{white-space:pre-wrap;font-size:12px;color:#aab7c8}.composer{border-top:1px solid #334155;padding:13px 8%;display:flex;gap:8px;background:#111827}.composer input{padding:12px}.composer button{padding:10px 17px}.card{border:1px solid #334155;border-radius:8px;padding:10px;margin:10px 0;background:#141d2d}.list{font-size:12px;line-height:1.5;word-break:break-word}.diff{white-space:pre-wrap;background:#0b1220;border-radius:6px;padding:8px;max-height:230px;overflow:auto;color:#d7e1ed}.ok{color:#86efac}.error{color:#fca5a5}.chip{display:inline-block;padding:3px 6px;border-radius:5px;background:#22314a;color:#bcd5ff;margin:2px;font-size:11px}.check{display:block;margin:5px 0;color:#dbeafe;font-size:12px}.check input{width:auto;margin-right:5px}.comparison{max-width:1180px;margin:0 auto 20px}.comparison-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(255px,1fr));gap:10px}.comparison .card{margin:0}.comparison .answer{white-space:pre-wrap;line-height:1.5;max-height:440px;overflow:auto}.target-tree{max-height:360px;overflow:auto;border:1px solid #334155;border-radius:7px;padding:7px;background:#0f172a}.target-tree details{margin:3px 0}.target-tree summary{cursor:pointer;list-style:none}.target-tree summary::-webkit-details-marker{display:none}.target-tree summary:before{content:'▸';display:inline-block;width:13px;color:#94a3b8}.target-tree details[open]>summary:before{content:'▾'}.target-tree label{cursor:pointer;margin-left:4px}.target-tree input{width:auto;vertical-align:middle}.tree-children{margin-left:17px;border-left:1px solid #29374d;padding-left:7px}.tree-file{margin:3px 0}.unsupported{color:#64748b}.classification-card{max-width:920px;margin:-8px auto 18px;border:1px solid #38bdf8;border-radius:10px;padding:13px 15px;background:#10263a;line-height:1.55}.classification-card h3{margin:0 0 8px;color:#bae6fd;font-size:14px}.classification-card ul{margin:5px 0 0;padding-left:20px}.classification-card .result{font-size:16px;color:#f8fafc}.codebook-workspace{padding-top:28px}.codebook-workspace .workspace-inner{max-width:980px;margin:auto}.codebook-workspace h1{font-size:22px;margin:0 0 7px}.codebook-workspace h2{font-size:16px;margin:22px 0 8px}.codebook-class{border-left:3px solid #38bdf8}.codebook-class h3{margin:0 0 7px}.codebook-class ul{margin:7px 0;padding-left:20px;line-height:1.55}.workspace-actions{display:flex;gap:8px;position:sticky;bottom:0;padding:12px 0;background:#111827}.language-picker{position:fixed;top:11px;right:14px;z-index:50;display:flex;align-items:center;gap:5px;padding:5px 7px;background:#172033;border:1px solid #3b4960;border-radius:7px;color:#cbd5e1;font-size:12px}.language-picker select{width:auto;background:#0f172a;border:0;color:#f8fafc;padding:3px}@media(max-width:900px){.shell{grid-template-columns:minmax(220px,var(--left-panel-width)) 8px minmax(320px,1fr)}.right{display:none}}
</style></head><body><div class="language-picker"><span>GUI:</span><select id="language" onchange="changeLanguage()"><option value="zh">ZH</option><option value="en">EN</option><option value="de">DE</option></select></div><div class="shell"><aside class="side"><div class="brand">Bosch Local Workbench</div><div class="muted">仅本机 127.0.0.1 · 缓存固定保存在程序目录 AI_Bot_State</div>
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
<main class="main"><div class="chat" id="chat"><div class="message assistant">选择工作区后即可聊天。代码修改会先显示 diff，只有点击“应用修改”才会写入本地文件。</div></div><div class="composer" id="composer"><input id="question" placeholder="问代码，或根据 Codebook 判断 Baugruppe …" onkeydown="if(event.key==='Enter')chat()"><button onclick="chat()">发送</button></div></main>
<aside class="side right"><b>本轮状态</b><div id="status" class="card muted">尚未打开工作区</div><b>会话导出</b><div id="sessionexport" class="card"><button class="ghost" onclick="exportSession()">导出完整会话</button></div><b>本轮 token 明细</b><div id="usagedetail" class="card muted">完成一次请求后显示。</div><b>BG 分析导出</b><div id="analysisexport" class="card muted">仅在 Baugruppe 分析完成后可导出。</div><b>证据来源</b><div id="sources" class="card list">回答后会显示实际传给模型的来源。</div><b>待应用修改</b><div id="changes" class="list">无</div></aside></div>
<script>
const $=id=>document.getElementById(id);let busy=false,lastQuestion='',compareSlots=[{value:'claude-haiku-5-5',custom:''}],savedTargetSelection=new Set(),treeRestoreNote='',lastScanReport=null,scannedSelection='',uiLanguage='zh';
const UI={en:{'代码工作区文件夹':'Code workspace folder','选择':'Browse','模型':'Model','打开工作区':'Open workspace','切换模型':'Switch model','测试模型':'Test model','聊天会话':'Chat session','切换':'Switch','新建':'New','改名':'Rename','删除':'Delete','材料分析':'Material analysis','分析目标：文件或文件夹':'Analysis target: file or folder','文件':'File','文件夹':'Folder','显示文件夹结构':'Show folder tree','用选中材料开始分析':'Analyze selected materials','退出分类模式':'Exit classification mode','多模型对比':'Multi-model comparison','开始对比':'Compare','发送':'Send','本轮状态':'Current status','会话导出':'Session export','导出完整会话':'Export full session','本轮 token 明细':'Current token detail','BG 分析导出':'BG analysis export','证据来源':'Evidence sources','待应用修改':'Pending changes','Codebook 文件（首次准备或更换时选择）':'Codebook file (select when preparing or replacing)','准备 Codebook':'Prepare Codebook','查看':'View','更换':'Replace','＋ 添加对比模型':'＋ Add comparison model','最多 4 个模型':'Maximum 4 models','无':'None','尚未打开工作区':'No workspace open','完成一次请求后显示。':'Shown after a request completes.','回答后会显示实际传给模型的来源。':'Sources actually sent to the model appear after an answer.','仅在 Baugruppe 分析完成后可导出。':'Available after a Baugruppe analysis completes.','选择工作区后即可聊天。代码修改会先显示 diff，只有点击“应用修改”才会写入本地文件。':'Choose a workspace to start chatting. Code edits are shown as a diff and are written only after you click “Apply changes”.'},de:{'代码工作区文件夹':'Code-Arbeitsordner','选择':'Auswählen','模型':'Modell','打开工作区':'Arbeitsordner öffnen','切换模型':'Modell wechseln','测试模型':'Modell testen','聊天会话':'Chat-Sitzung','切换':'Wechseln','新建':'Neu','改名':'Umbenennen','删除':'Löschen','材料分析':'Materialanalyse','分析目标：文件或文件夹':'Analyseziel: Datei oder Ordner','文件':'Datei','文件夹':'Ordner','显示文件夹结构':'Ordnerstruktur anzeigen','用选中材料开始分析':'Ausgewählte Materialien analysieren','退出分类模式':'Klassifizierungsmodus verlassen','多模型对比':'Modellvergleich','开始对比':'Vergleichen','发送':'Senden','本轮状态':'Aktueller Status','会话导出':'Sitzung exportieren','导出完整会话':'Vollständige Sitzung exportieren','本轮 token 明细':'Token-Details dieser Runde','BG 分析导出':'BG-Analyse exportieren','证据来源':'Evidenzquellen','待应用修改':'Ausstehende Änderungen','Codebook 文件（首次准备或更换时选择）':'Codebook-Datei (beim Vorbereiten/Ersetzen wählen)','准备 Codebook':'Codebook vorbereiten','查看':'Ansehen','更换':'Ersetzen','＋ 添加对比模型':'＋ Vergleichsmodell hinzufügen','最多 4 个模型':'Maximal 4 Modelle','无':'Keine','尚未打开工作区':'Kein Arbeitsordner geöffnet','完成一次请求后显示。':'Wird nach Abschluss einer Anfrage angezeigt.','回答后会显示实际传给模型的来源。':'Nach einer Antwort werden die tatsächlich an das Modell gesendeten Quellen angezeigt.','仅在 Baugruppe 分析完成后可导出。':'Nach Abschluss einer Baugruppenanalyse verfügbar.','选择工作区后即可聊天。代码修改会先显示 diff，只有点击“应用修改”才会写入本地文件。':'Arbeitsordner wählen, dann chatten. Codeänderungen werden zuerst als Diff gezeigt und erst nach „Änderungen anwenden“ lokal geschrieben.'}};
const originalText=new WeakMap(),originalAttr=new WeakMap();
function applyLanguage(){let dict=UI[uiLanguage]||{};document.documentElement.lang=uiLanguage;document.title='Bosch Local Workbench';let walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);for(let node;node=walker.nextNode();){let source=originalText.get(node);if(source===undefined){source=node.nodeValue;originalText.set(node,source)}let key=source.trim(),translated=dict[key];if(translated){let lead=source.match(/^\s*/)[0],tail=source.match(/\s*$/)[0];node.nodeValue=lead+translated+tail}}for(let el of document.querySelectorAll('[placeholder],[title]'))for(let attr of ['placeholder','title'])if(el.hasAttribute(attr)){let saved=originalAttr.get(el)||{};if(!(attr in saved)){saved[attr]=el.getAttribute(attr);originalAttr.set(el,saved)}el.setAttribute(attr,dict[saved[attr]]||saved[attr])}}
async function changeLanguage(){uiLanguage=$('language').value;applyLanguage();try{if($('workspace').value.trim())await api('/api/language',{method:'POST',body:JSON.stringify({language:uiLanguage})})}catch(e){console.warn('Could not persist UI language',e)}}
async function restoreLastWorkspace(){
  try{
    let s=await api('/api/settings');
    uiLanguage=['zh','en','de'].includes(s.language)?s.language:'zh';$('language').value=uiLanguage;applyLanguage();
    if(!s.workspace)return;
    $('workspace').value=s.workspace;
    setSelectedModel(s.model||'claude-haiku-5-5');
    $('session').innerHTML='<option>'+ (s.session||'default') +'</option>';
    $('setupmsg').textContent='正在自动打开上次工作区…';
    await setup();
  }catch{
    $('setupmsg').textContent='无法自动打开上次工作区；请重新选择路径。';
  }
}
function setLeftPanelWidth(width){let available=Math.max(240,window.innerWidth-420-300-8);let bounded=Math.max(235,Math.min(Number(width)||270,Math.min(600,available)));document.documentElement.style.setProperty('--left-panel-width',bounded+'px');let drawerStyle=$('scan-drawer-position')||Object.assign(document.createElement('style'),{id:'scan-drawer-position'});drawerStyle.textContent='#scanbackdrop .scan-drawer{left:'+bounded+'px!important}';if(!drawerStyle.parentNode)document.head.append(drawerStyle);localStorage.setItem('bosch-workbench-left-panel-width',String(bounded))}
function initLeftSplitter(){let splitter=$('leftsplitter');if(!splitter)return;let saved=Number(localStorage.getItem('bosch-workbench-left-panel-width'));if(saved)setLeftPanelWidth(saved);let dragging=false;function stop(){if(!dragging)return;dragging=false;splitter.classList.remove('dragging');document.body.style.userSelect=''}splitter.addEventListener('pointerdown',event=>{dragging=true;splitter.classList.add('dragging');splitter.setPointerCapture(event.pointerId);document.body.style.userSelect='none';event.preventDefault()});splitter.addEventListener('pointermove',event=>{if(dragging)setLeftPanelWidth(event.clientX)});splitter.addEventListener('pointerup',stop);splitter.addEventListener('pointercancel',stop);window.addEventListener('resize',()=>setLeftPanelWidth(Number(getComputedStyle(document.documentElement).getPropertyValue('--left-panel-width').replace('px',''))||270))}
function initDarkScrollbars(){let style=document.createElement('style');style.textContent='*{scrollbar-color:#52637a #182235;scrollbar-width:thin}::-webkit-scrollbar{width:10px;height:10px}::-webkit-scrollbar-track{background:#182235;border-radius:10px}::-webkit-scrollbar-thumb{background:#52637a;border:2px solid #182235;border-radius:10px}::-webkit-scrollbar-thumb:hover{background:#70839c}::-webkit-scrollbar-corner{background:#182235}select{width:100%;background:#0f172a!important;color:#e5e7eb!important;border:1px solid #3b4960!important;border-radius:6px;padding:8px;outline:none}select:hover{border-color:#526b88!important}select:focus{border-color:#3b82a8!important;box-shadow:0 0 0 2px rgba(59,130,168,.18)}select option{background:#172033;color:#e5e7eb}.language-picker select{width:auto;padding:3px 6px}.splitter{background:#263449!important}.splitter:hover,.splitter.dragging{background:#3b82a8!important}';document.head.append(style)}
window.addEventListener('DOMContentLoaded',()=>{applyLanguage();initDarkScrollbars();initLeftSplitter();initSessionSidebar();renderCompareSlots();loadCodebookStatus();ensureMaterialFlow();restoreLastWorkspace()});
async function api(url,opt={}){let r=await fetch(url,{headers:{'Content-Type':'application/json'},...opt});let d=await r.json();if(!r.ok)throw Error(d.detail||'请求失败');return d}
async function pick(kind,target){try{$(target).value=(await api('/api/pick/'+kind)).path||''}catch(e){alert(e.message)}}
async function pickWorkspace(){try{let path=(await api('/api/pick/folder')).path||'';if(!path)return;$('workspace').value=path;await setup()}catch(e){$('setupmsg').innerHTML='<span class="error">'+esc(e.message)+'</span>'}}
function message(text,kind='assistant'){let e=document.createElement('div');e.className='message '+kind;e.textContent=text;$('chat').append(e);$('chat').scrollTop=1e9;return e}
function classificationCard(c){let card=document.createElement('section');card.className='classification-card';let alternative=c.alternative_label?'<br>备选类别：'+esc(c.alternative_label):'';let evidence=(c.evidence_labels||[]).map(item=>'<li>'+esc(item)+'</li>').join('')||'<li>未提供</li>';let uncertainty=(c.uncertainties||[]).filter(Boolean).map(item=>'<li>'+esc(item)+'</li>').join('')||'<li>未报告明显不确定性</li>';let rules=(c.codebook_rule_ids||[]).map(esc).join('、')||'未返回';let rulePages=(c.codebook_rule_pages||[]).map(esc).join('、')||'未返回';let bgPages=(c.bg_evidence_pages||[]).map(esc).join('、')||'未返回';card.innerHTML='<h3>本次分类结论（已校验）</h3><div class="result">类别：<b>'+esc(c.label||'—')+'</b></div><div>置信度：'+esc(c.confidence||'—')+alternative+'</div><div><b>Codebook 规则</b>：'+rules+'（页 '+rulePages+'）</div><div><b>BG 页面证据</b>：'+bgPages+'</div><div><b>证据</b><ul>'+evidence+'</ul></div><div><b>不确定性</b><ul>'+uncertainty+'</ul></div>';return card}
function coverageSummaryCard(summary){if(!summary?.files?.length)return null;let card=document.createElement('section');card.className='classification-card';card.style.borderColor='#475569';let rows=summary.files.map(f=>{let read=Array.isArray(f.pages_read)?f.pages_read.length:0,unread=Array.isArray(f.pages_unread)?f.pages_unread.length:0;let pages=f.pages_total?(' · 已读 '+read+'/'+f.pages_total+' 页'+(unread?'；未读 '+unread+' 页':'')):'';let cache=f.cache_status==='reused'?'已复用':'本次读取';return '<li><b>'+esc(f.name)+'</b>：'+esc(f.scope||'已读取')+pages+' · '+cache+'</li>'}).join('');card.innerHTML='<h3>本次资料处理情况（本地记录）</h3><div class="muted">已处理 '+summary.files.length+' 个文件；复用 '+(summary.reused_files||0)+' 个，本次读取 '+(summary.created_files||0)+' 个；预读模型调用 '+(summary.model_calls||0)+' 次。</div><ul>'+rows+'</ul>';return card}
function renderStatus(s){$('status').innerHTML=`模型：<b>${s.model}</b><br>会话：${s.session_name||'default'}<br>代码：${s.code_files} 文件<br>材料：${s.documents} 个<br>累计请求：${s.requests}<br>累计 Token：${s.input_tokens} / ${s.output_tokens}<br>累计估算：${s.cost}<br>${s.bg_context?'<span class="ok">BG 模式：'+s.bg_context.codebook_name+'</span>':'普通模式'}`}
function renderUsageDetail(u,model){if(!u)return;$('usagedetail').innerHTML=`实际模型：<b>${esc(model||'—')}</b><br>输入 / 输出 / 总计：${u.input} / ${u.output} / ${u.total}<br>推理：${u.reasoning||0} ｜ Gemini thinking：${u.gemini_thinking||0}<br>Claude 缓存读 / 写：${u.cache_read||0} / ${u.cache_write||0}<br>本轮估算：${Number(u.cost_usd||0).toFixed(6)}`}
function renderEvidenceSources(sources,dfcEvidence){let normal=(sources||[]).map(s=>`<div class="card"><b>${esc(s.label||s.name||'未知来源')}</b><br>${s.visual?'<span class="chip">视觉证据已附带</span>':''}</div>`).join('');let dfc=(dfcEvidence||[]).map(d=>{let parts=(d.segments_used||[]).join('、')||'无';return `<div class="card"><b>DFC Struktur</b><br>${esc(d.name||'—')}<br><span class="chip">OCR：${esc(d.ocr_status||'—')}</span><span class="chip">本轮：第 ${esc(parts)} 段 / 共 ${esc(d.segments_total||0)} 段</span></div>`}).join('');$('sources').innerHTML=(dfc+normal)||'无可用来源'}
function toggleCustomModel(){let custom=$('model').value==='__custom__';$('custommodelrow').style.display=custom?'flex':'none';if(custom)$('custommodel').focus()}
function setSelectedModel(model){let known=[...$('model').options].some(option=>option.value===model);$('model').value=known?model:'__custom__';$('custommodel').value=known?'':model;toggleCustomModel();loadModelStatus()}
function selectedModel(){let selected=$('model').value;return selected==='__custom__' ? $('custommodel').value.trim() : selected}
async function modelChanged(){toggleCustomModel();loadModelStatus();if($('model').value!=='__custom__'&&$('workspace').value.trim())await switchModel()}
async function confirmCustomModel(){if(!selectedModel()){ $('modelmsg').innerHTML='<span class="error">请先输入 Bosch Farm 的准确 Model ID。</span>';return}if($('workspace').value.trim())await switchModel();else $('modelmsg').textContent='Model ID 已填写；选择工作区后会自动使用该模型。'}
function codebookList(items){let values=Array.isArray(items)?items.filter(Boolean):[];return values.length?'<ul>'+values.map(item=>{if(item&&typeof item==='object'){let text=esc(item.text||item.title||JSON.stringify(item));let id=item.id?' <span class="muted">['+esc(item.id)+']</span>':'';let pages=Array.isArray(item.pages)&&item.pages.length?' <span class="muted">（页 '+esc(item.pages.join('、'))+'）</span>':'';return '<li>'+text+id+pages+'</li>'}return '<li>'+esc(String(item))+'</li>'}).join('')+'</ul>':'<div class="muted">未提取到。</div>'}
function renderCodebookStatus(profile){let host=$('codebookstatus');if(!profile||profile.status==='none'||!profile.status){host.textContent='尚未准备 Codebook；普通材料问答仍可直接使用。';return}let lock=profile.status==='locked';host.innerHTML=(lock?'<span class="ok">已锁定</span>':'<span class="error">草稿待确认</span>')+'：<b>'+esc(profile.source_name||'Codebook')+'</b><br>'+esc(profile.page_count||0)+' 页/片段 · '+esc(profile.parser_model||'—')+(lock?'<br>切换模型、会话或材料后仍会自动沿用。':'<br>请在中间区域核对后一次确认锁定。')}
async function loadCodebookStatus(){try{renderCodebookStatus(await api('/api/codebook'))}catch(e){$('codebookstatus').innerHTML='<span class="error">'+esc(e.message)+'</span>'}}
function leaveCodebookWorkspace(){let composer=$('composer');composer.style.display='flex';$('chat').classList.remove('codebook-workspace');loadHistory()}
function showCodebookWorkspace(profile){let draft=profile.draft||{};$('composer').style.display='none';let classes=(draft.classes||[]).map(item=>'<article class="card codebook-class"><h3>'+esc(item.name||'未命名类别')+'</h3><div>'+esc(item.definition||'未提供定义')+'</div><b>判定规则</b>'+codebookList(item.decision_rules)+'<b>边界 / 排除规则</b>'+codebookList(item.boundaries)+'<div class="muted">依据页：'+esc((item.evidence_pages||[]).join('、')||'未标注')+'</div></article>').join('')||'<div class="card error">未找到可确认的类别，请更换模型或重新准备。</div>';let usage=profile.usage||{},ocr=profile.ocr_runtime||{},locked=profile.status==='locked';let ocrText=ocr.status==='not applicable to DOCX'?'OCR：DOCX 不适用':(ocr.available?('OCR：已启用 · '+esc(ocr.command||'Tesseract')+(ocr.german_available?' · deu':' · 无 deu，使用 eng')):('OCR：未启用 · '+esc(ocr.status||'未检测到 Tesseract')));$('chat').className='chat codebook-workspace';$('chat').innerHTML='<section class="workspace-inner"><h1>Codebook 工作区</h1><div class="muted">'+(locked?'此版本已锁定，将作为后续全部 BG 分类的首要规则来源。':'请阅读下方模型整理的完整结果；确认无误后一次点击锁定。')+'</div><div class="card"><b>来源：</b>'+esc(profile.source_name||'—')+'<br><span class="muted">解析模型：'+esc(profile.parser_model||'—')+' · 页/片段：'+esc(profile.page_count||0)+' · 分组：'+esc(profile.page_groups||0)+' · Token：'+esc(usage.input||0)+' / '+esc(usage.output||0)+(usage.cost_usd===null||usage.cost_usd===undefined?'':' · $'+Number(usage.cost_usd).toFixed(6))+'<br>'+ocrText+'</span></div><h2>类别与判定边界</h2>'+classes+'<h2>通用规则</h2><div class="card">'+codebookList(draft.global_rules)+'</div><h2>表格规则</h2><div class="card">'+codebookList(draft.table_rules)+'</div><h2>需要注意的不确定项</h2><div class="card">'+codebookList(draft.uncertainties)+'</div><div class="workspace-actions">'+(locked?'<button class="ghost" onclick="leaveCodebookWorkspace()">返回聊天</button>':'<button onclick="lockCodebook()">确认并锁定此 Codebook</button><button class="ghost" onclick="leaveCodebookWorkspace()">暂不锁定</button>')+'</div></section>';$('chat').scrollTop=0}
async function prepareCodebook(){let path=$('codebook').value.trim();if(!path){$('codebookstatus').innerHTML='<span class="error">请先选择 PDF 或 DOCX Codebook 文件。</span>';return}let model=prompt('用于完整解析 Codebook 的模型 ID（可修改）。\n建议选擅长视觉/表格理解的模型。',selectedModel());if(model===null)return;model=model.trim();if(!model){$('codebookstatus').innerHTML='<span class="error">请输入一个模型 ID。</span>';return}try{$('codebookstatus').textContent='正在按页读取、提取表格与合并 Codebook；大型文件可能需要几分钟…';let profile=await api('/api/codebook/prepare',{method:'POST',body:JSON.stringify({path,model})});renderCodebookStatus(profile);showCodebookWorkspace(profile)}catch(e){$('codebookstatus').innerHTML='<span class="error">'+esc(e.message)+'</span>'}}
async function viewCodebook(){try{let profile=await api('/api/codebook');if(!profile||!profile.status)throw Error('尚未准备 Codebook。');renderCodebookStatus(profile);showCodebookWorkspace(profile)}catch(e){$('codebookstatus').innerHTML='<span class="error">'+esc(e.message)+'</span>'}}
async function lockCodebook(){if(!confirm('确认锁定此 Codebook？之后切换文件夹、会话或模型都会继续使用它；只有你手动更换或原文件变化时才会失效。'))return;try{let profile=await api('/api/codebook/lock',{method:'POST'});renderCodebookStatus(profile);showCodebookWorkspace(profile);$('setupmsg').innerHTML='<span class="ok">Codebook 已锁定。</span>'}catch(e){$('codebookstatus').innerHTML='<span class="error">'+esc(e.message)+'</span>'}}
async function changeCodebook(){if(!confirm('更换 Codebook 会解除当前锁定；不会删除原始文件或已完成的聊天记录。继续吗？'))return;try{await api('/api/codebook',{method:'DELETE'});$('codebook').value='';renderCodebookStatus({status:'none'});leaveCodebookWorkspace();$('setupmsg').textContent='已解除 Codebook 锁定，请选择新文件并准备。'}catch(e){$('codebookstatus').innerHTML='<span class="error">'+esc(e.message)+'</span>'}}
let sessionOffset=0,sessionHasMore=false,sessionLoading=false,currentSessionName='';
function initSessionSidebar(){if($('sessionpanel'))return;let left=document.querySelector('.shell > .side');if(!left)return;let style=document.createElement('style');style.textContent='.side.left{display:flex;flex-direction:column;overflow:hidden;padding-bottom:10px}.left-content{overflow:auto;min-height:0;padding-right:2px}.session-panel{border-top:1px solid #334155;margin-top:10px;padding-top:10px;display:flex;flex-direction:column;min-height:155px;max-height:42vh}.session-new{width:100%;margin-bottom:8px;text-align:left}.session-list{overflow:auto;min-height:0}.session-row{display:flex;align-items:center;gap:4px;border-radius:7px;margin:2px 0;padding:6px 5px;cursor:pointer;color:#dbeafe}.session-row:hover,.session-row.active{background:#263244}.session-title{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1}.session-more{visibility:hidden;width:25px;padding:2px 3px;background:transparent;color:#cbd5e1}.session-row:hover .session-more,.session-row.active .session-more{visibility:visible}.session-pin{font-size:10px;color:#7dd3fc}.session-loading{text-align:center;padding:8px;color:#94a3b8}.session-menu{position:fixed;z-index:100;min-width:130px;padding:5px;background:#1e293b;border:1px solid #475569;border-radius:8px;box-shadow:0 12px 30px rgba(0,0,0,.4)}.session-menu button{display:block;width:100%;text-align:left;background:transparent;color:#e5e7eb;padding:7px 9px}.session-menu button:hover{background:#334155}.session-menu button.delete{color:#fca5a5}';document.head.append(style);left.classList.add('left');let content=document.createElement('div');content.className='left-content';while(left.firstChild)content.append(left.firstChild);left.append(content);let old=$('session')?.closest('.field');if(old)old.style.display='none';let panel=document.createElement('section');panel.id='sessionpanel';panel.className='session-panel';panel.innerHTML='<button class="ghost session-new" onclick="newSession()">＋ 新聊天</button><div id="sessionlist" class="session-list"></div>';left.append(panel);$('sessionlist').addEventListener('scroll',()=>{let el=$('sessionlist');if(sessionHasMore&&!sessionLoading&&el.scrollTop+el.clientHeight>=el.scrollHeight-18)loadSessions(false)});document.addEventListener('click',event=>{if(!event.target.closest('.session-more')&&!event.target.closest('#sessionmenu'))closeSessionMenu()})}
function closeSessionMenu(){$('sessionmenu')?.remove()}
function renderSessionRows(items,append){let list=$('sessionlist');if(!append)list.innerHTML='';for(let item of items){let row=document.createElement('div');row.className='session-row'+(item.name===currentSessionName?' active':'');row.onclick=()=>openSessionByName(item.name);let title=document.createElement('span');title.className='session-title';title.textContent=item.title;row.append(title);if(item.pinned){let pin=document.createElement('span');pin.className='session-pin';pin.textContent='●';pin.title='已置顶';row.append(pin)}let more=document.createElement('button');more.className='session-more';more.textContent='•••';more.title='更多';more.onclick=e=>{e.stopPropagation();openSessionMenu(e,item)};row.append(more);list.append(row)}if(sessionLoading){let loading=document.createElement('div');loading.id='sessionloading';loading.className='session-loading';loading.textContent='正在加载…';list.append(loading)}}
async function loadSessions(reset=true){if(sessionLoading)return;if(reset){sessionOffset=0;sessionHasMore=false;renderSessionRows([],true)}sessionLoading=true;try{let x=await api('/api/sessions?offset='+sessionOffset+'&limit=10');currentSessionName=x.current;let existingCount=$('sessionlist').querySelectorAll('.session-row').length,items=x.sessions;renderSessionRows(items,!reset);let rows=[...$('sessionlist').querySelectorAll('.session-row')];items.forEach((item,index)=>rows[existingCount+index].dataset.name=item.name);sessionOffset+=items.length;sessionHasMore=!!x.has_more}catch(e){$('sessionmsg').textContent=e.message}finally{sessionLoading=false;$('sessionloading')?.remove()}}
async function restoreSessionTree(target,paths){$('treestatus').textContent='正在恢复该会话的材料范围…';let x=await api('/api/target-tree?target='+encodeURIComponent(target));savedTargetSelection=new Set(paths||[]);treeRestoreNote='已恢复此会话最后确认的材料范围。';let host=$('targettree');host.classList.remove('muted');host.innerHTML='';host.append(makeTreeNode(x.tree));refreshAllFolderStates()}
async function restoreSessionContext(){try{let x=await api('/api/session/context');setSelectedModel(x.model);let target=x.target||{};$('targetpath').value=target.path||'';$('codebook').value=x.codebook_path||'';if(target.path&&target.kind==='文件夹'){await restoreSessionTree(target.path,target.selected_paths)}else{clearTargetTree()}await loadCodebookStatus();loadDocs();loadCoverage()}catch(e){console.warn('Could not restore session context',e)}}
async function openSessionByName(name){try{closeSessionMenu();let s=await api('/api/session/open',{method:'POST',body:JSON.stringify({name})});renderStatus(s);await restoreSessionContext();await loadHistory();await loadSessions(true)}catch(e){$('sessionmsg').innerHTML='<span class="error">'+esc(e.message)+'</span>'}}
async function newSession(){try{let s=await api('/api/session/new',{method:'POST'});renderStatus(s);$('targetpath').value='';$('codebook').value='';clearTargetTree();await loadHistory();await loadSessions(true);loadDocs();loadCodebookStatus()}catch(e){$('sessionmsg').innerHTML='<span class="error">'+esc(e.message)+'</span>'}}
function openSessionMenu(event,item){closeSessionMenu();let menu=document.createElement('div');menu.id='sessionmenu';menu.className='session-menu';let rect=event.currentTarget.getBoundingClientRect();menu.style.left=Math.min(window.innerWidth-145,rect.right+6)+'px';menu.style.top=rect.top+'px';menu.innerHTML='<button data-action="rename">重命名</button><button data-action="pin">'+(item.pinned?'取消置顶':'置顶')+'</button><button class="delete" data-action="delete">删除</button>';menu.onclick=async e=>{let action=e.target.dataset.action;if(!action)return;if(action==='rename')await renameSession(item.name);if(action==='pin')await pinSession(item);if(action==='delete')await deleteSession(item.name);closeSessionMenu()};document.body.append(menu)}
async function renameSession(name){let value=prompt('输入新的会话名称：',name);if(!value?.trim())return;try{let s=await api('/api/session/rename',{method:'POST',body:JSON.stringify({name:value.trim(),source:name})});renderStatus(s);await loadSessions(true)}catch(e){alert(e.message)}}
async function pinSession(item){try{await api('/api/session/pin',{method:'POST',body:JSON.stringify({name:item.name,pinned:!item.pinned})});await loadSessions(true)}catch(e){alert(e.message)}}
async function deleteSession(name){if(!confirm('确定删除此会话吗？只会删除本地聊天记录和会话状态，不会删除原始材料、Codebook 或共享缓存。'))return;try{let wasCurrent=name===currentSessionName;let s=await api('/api/session/delete',{method:'POST',body:JSON.stringify({confirmed:true,name})});renderStatus(s);if(wasCurrent){await restoreSessionContext();await loadHistory()}await loadSessions(true)}catch(e){alert(e.message)}}
async function loadHistory(){try{let x=await api('/api/history');$('chat').innerHTML='';if(!x.history.length){message('这是一个新会话，可以直接开始提问。');return}for(let item of x.history)message(item.content,item.role==='user'?'user':'assistant')}catch{}}
async function setup(){try{let model=selectedModel();if(!model)throw Error('请先输入 Bosch Farm 的准确 Model ID。');let s=await api('/api/setup',{method:'POST',body:JSON.stringify({workspace:$('workspace').value,state_dir:'',env_file:'',model:model,session:$('session').value.trim()||'default',language:uiLanguage})});renderStatus(s);$('setupmsg').textContent='已打开。';loadDocs();loadSessions();loadHistory();loadCodebookStatus()}catch(e){$('setupmsg').innerHTML='<span class="error">'+e.message+'</span>'}}
async function openLegacySession(){if(!$('session').value)return;await setup()}
async function switchModel(){try{let model=selectedModel();if(!model)throw Error('请先输入 Bosch Farm 的准确 Model ID。');let s=await api('/api/model',{method:'POST',body:JSON.stringify({model})});renderStatus(s);$('modelmsg').innerHTML='<span class="ok">已切换至 '+esc(model)+'；当前会话与材料保持不变。</span>'}catch(e){$('modelmsg').innerHTML='<span class="error">'+e.message+'</span>'}}
async function loadModelStatus(){try{let x=await api('/api/model-tests');let r=x.tests[selectedModel()];if(!r){$('modelstatus').textContent='尚未测试此模型。';return}if(!r.ok){$('modelstatus').innerHTML='<span class="error">上次测试失败：'+esc(r.tested_at)+'</span>';return}$('modelstatus').innerHTML='<span class="ok">上次可用：'+esc(r.tested_at)+'；'+esc(r.streaming||'未记录流式状态')+'；usage '+(r.usage_available===false?'未返回':'已返回')+'</span>'}catch{}}
async function testModel(){try{let model=selectedModel();if(!model)throw Error('请先输入 Bosch Farm 的准确 Model ID。');$('setupmsg').textContent='正在发送一次极短的测试请求…';let x=await api('/api/model-test',{method:'POST',body:JSON.stringify({model})});$('setupmsg').innerHTML=x.ok?'<span class="ok">模型可用：'+x.model+'；'+(x.streaming||'')+'；输入 '+x.input_tokens+' / 输出 '+x.output_tokens+' token。 '+(x.usage_available===false?'网关未返回 usage。':'')+'</span>':'<span class="error">模型测试失败：'+x.message+'</span>';loadModelStatus()}catch(e){$('setupmsg').innerHTML='<span class="error">'+e.message+'</span>'}}
async function loadDocs(){try{let x=await api('/api/documents');$('docs').innerHTML=x.map(d=>`<div class="card">${d.name}<br><span class="muted">${d.material_role_label||'其他资料'} · ${d.chunks} chunks</span></div>`).join('')||'尚无材料。'}catch{}}
async function addDoc(){try{let d=await api('/api/document',{method:'POST',body:JSON.stringify({path:$('docpath').value})});$('docpath').value='';loadDocs();$('setupmsg').textContent=`已索引 ${d.name}（${d.chunks} chunks）`}catch(e){$('setupmsg').innerHTML='<span class="error">'+e.message+'</span>'}}
function renderScanReport(x){setScanReportAvailable(x);renderScanDrawer(x)}
function renderCoverageReport(x){if(!x||!x.files){$('coveragestatus').textContent='分类/Codebook 问题会自动准备证据；也可在提问前手动准备。';return}if(x.current_selection===false){$('coveragestatus').innerHTML='<span class="muted">材料选择或模型已更新；下次分类准备时会复用未变文件的本地摘要，仅预读新增/变更文件。</span>';return}let done=x.files.filter(f=>f.complete).length;let details=x.files.map(f=>{let pages=f.pages_total?`页：已读 ${(f.pages_read||[]).join('、')||'—'}${(f.pages_unread||[]).length?'；未读 '+f.pages_unread.join('、'):''}`:'无页码';let dfc=f.dfc_structure?` · <span class="chip">DFC Struktur：${esc(f.dfc_structure.ocr_status||'—')}，${esc(f.dfc_structure.segments_total||0)} 段</span>`:'';let cache=f.cache_status==='reused'?' · <span class="chip">本地摘要已复用</span>':f.cache_status==='created'?' · <span class="chip">本轮新预读</span>':'';return `<br>${f.complete?'✓':'✕'} ${esc(f.name)}：${f.text_groups_processed}/${f.text_groups_total} 个文本组 · ${esc(f.reading_scope||'')} · ${esc(pages)}${cache}${dfc}${f.failures?.length?'（'+esc(f.failures.join('；'))+'）':''}`}).join('');let dossier=x.bg_dossier?.ready?' · <span class="chip">BG 综合证据档案已缓存</span>':' · <span class="chip">首次分类后生成 BG 综合证据档案</span>';$('coveragestatus').innerHTML=(x.complete?'<span class="ok">分类证据已准备：</span>':'<span class="error">分类证据不完整：</span>')+` ${done}/${x.files.length} 个文件；复用 ${x.reused_files||0} 个，新预读 ${x.created_files||0} 个；本次 ${x.model_calls||0} 次模型调用。`+dossier+details}
async function loadCoverage(){try{renderCoverageReport(await api('/api/coverage'))}catch{}}
function ensureMaterialFlow(){if($('materialactions'))return;let style=document.createElement('style');style.textContent='#materialactions{display:flex;gap:7px;margin:8px 0}.scan-backdrop{position:fixed;inset:0;background:rgba(2,6,23,.28);z-index:20;opacity:0;pointer-events:none;transition:opacity .18s}.scan-backdrop.open{opacity:1;pointer-events:auto}.scan-drawer{position:absolute;left:270px;top:72px;bottom:20px;width:min(680px,calc(100vw - 310px));background:#172033;border:1px solid #3b4960;border-left:3px solid #38bdf8;border-radius:0 12px 12px 0;box-shadow:12px 16px 45px rgba(0,0,0,.45);transform:translateX(-34px);opacity:0;transition:transform .22s ease,opacity .18s;display:flex;flex-direction:column}.scan-backdrop.open .scan-drawer{transform:translateX(0);opacity:1}.scan-drawer-head{display:flex;justify-content:space-between;align-items:center;padding:14px 16px;border-bottom:1px solid #334155}.scan-drawer-body{overflow:auto;padding:12px 16px}.scan-drawer .file-card{border:1px solid #334155;border-radius:8px;padding:10px;margin:9px 0;background:#111827;line-height:1.5}.scan-drawer .file-card b{word-break:break-word}@media(max-width:760px){.scan-drawer{left:0;top:0;bottom:0;width:min(94vw,680px);border-radius:0 12px 12px 0}}';document.head.append(style);let tree=$('targettree'),confirm=document.querySelector('button[onclick="analyzeTarget()"]');let actions=document.createElement('div');actions.id='materialactions';confirm.id='confirmmaterials';confirm.textContent='确认选中材料';let report=document.createElement('button');report.id='viewscanreport';report.className='ghost';report.disabled=true;report.textContent='查看扫描报告';report.onclick=openScanReport;actions.append(confirm,report);tree.insertAdjacentElement('afterend',actions);$('scanreport').style.display='none';let backdrop=document.createElement('div');backdrop.id='scanbackdrop';backdrop.className='scan-backdrop';backdrop.innerHTML='<section class="scan-drawer" role="dialog" aria-modal="true" aria-label="扫描报告"><div class="scan-drawer-head"><div><b>本次材料扫描报告</b><div class="muted">仅本地读取与索引；不消耗模型 token。</div></div><button class="ghost" onclick="closeScanReport()">×</button></div><div id="scanreportbody" class="scan-drawer-body"></div></section>';backdrop.addEventListener('click',e=>{if(e.target===backdrop)closeScanReport()});document.body.append(backdrop);document.addEventListener('keydown',e=>{if(e.key==='Escape')closeScanReport()});updateMaterialFlowButtons()}
function updateMaterialFlowButtons(){let confirm=$('confirmmaterials'),report=$('viewscanreport');if(confirm)confirm.disabled=treeFileCount()===0;if(report&&!lastScanReport){report.disabled=true;report.textContent='查看扫描报告'} }
function setScanReportAvailable(report){lastScanReport=report||null;let button=$('viewscanreport');if(button){button.disabled=!lastScanReport;button.textContent=lastScanReport?'查看扫描报告':'查看扫描报告'}}
function openScanReport(){if(!lastScanReport)return;renderScanDrawer(lastScanReport);$('scanbackdrop').classList.add('open');loadCacheAudit()}
function closeScanReport(){$('scanbackdrop')?.classList.remove('open')}
function renderScanDrawer(x){let files=(x.files||[]).map(f=>{let index=f.index_cache_status==='reused'?'本地索引已复用':f.index_cache_status==='changed'?'内容变化，已重新索引':f.index_cache_status==='new'?'已建立本地索引':'—';return `<article class="file-card"><b>${esc(f.name)}</b><br><span class="muted">${esc(f.material_role_label||'其他资料')} · ${(Number(f.bytes)/1024/1024).toFixed(1)} MB<br>本地文本片段：${f.chunks} · ${index}</span></article>`}).join('')||'<div class="muted">没有成功加入的材料。</div>';let skipped=x.skipped_count?`<article class="file-card error"><b>跳过 / 失败 ${x.skipped_count} 个</b><br><span class="muted">${x.skipped.map(esc).join('<br>')}${x.skipped_count>x.skipped.length?'<br>其余失败项未展开。':''}</span></article>`:'';let audit='<details id="cacheauditpanel" class="file-card" ontoggle="if(this.open)loadCacheAudit()"><summary><b>高级：缓存与重新读取</b></summary><div class="muted" style="margin:7px 0">用于核对是否已复用模型摘要，或在分类异常时只重读特定文件。</div><div id="cacheaudit" class="list muted">正在读取缓存状态…</div></details>';$('scanreportbody').innerHTML='<div class="muted">成功加入 '+(x.sources||0)+' 个文件。以下结果只表示本地可读性；首次提问时会自动读取理解并生成分类证据。</div>'+files+skipped+audit}
function renderCacheAudit(x){let host=$('cacheaudit');if(!host)return;if(!x.files?.length){host.textContent='当前没有已选材料。';return}let hasSummary=x.files.some(f=>(f.summary_entries||[]).length);if(!hasSummary){host.innerHTML='<div class="muted">尚无模型生成的缓存。首次提问后，程序会自动读取并理解当前材料；随后这里会显示复用状态、所用模型和 BG 综合档案。</div>';return}let dossier=x.dossier?.ready?`BG 综合档案：已缓存（${esc(x.dossier.model||'—')}）`:'BG 综合档案：尚未生成或材料范围已变化';let files=x.files.map(f=>{let summaries=(f.summary_entries||[]).map(s=>`${esc(s.model||'—')} · ${s.full?'全部页':'默认范围'} · ${s.complete?'完成':'未完成'}`).join('<br>')||'无摘要缓存';let read=(f.summary_entries||[]).length?'<br><button class="ghost" onclick="rebuildCachedFile(\''+esc(f.id)+'\')">仅重读此文件</button>':'';return `<div class="card"><b>${esc(f.name)}</b><br><span class="muted">索引：${esc(f.index_status)} · OCR：${esc(f.ocr_status)}<br>摘要：${summaries}</span>${read}</div>`}).join('');host.innerHTML='<div class="muted">'+dossier+(x.selection_current?'':'；当前材料范围待更新')+'</div><div class="row"><button class="ghost" onclick="rebuildDossier()">重建 BG 档案</button><button class="ghost" onclick="clearSummaryCaches()">清除摘要缓存</button></div>'+files}
async function loadCacheAudit(){let host=$('cacheaudit');if(!host)return;try{renderCacheAudit(await api('/api/cache/audit'))}catch(e){host.innerHTML='<span class="error">'+esc(e.message)+'</span>'}}
async function rebuildCachedFile(id){if(!confirm('仅清除这份文件的本地摘要？下次分类会重新读取该文件；其他文件摘要保持不变。'))return;try{let x=await api('/api/cache/file/rebuild',{method:'POST',body:JSON.stringify({document_id:id,confirmed:true})});$('coveragestatus').textContent=x.message;renderCacheAudit(x.audit)}catch(e){$('cacheaudit').innerHTML='<span class="error">'+esc(e.message)+'</span>'}}
async function rebuildDossier(){if(!confirm('重新生成 BG 综合证据档案会调用当前模型并产生 token 消耗。继续吗？'))return;try{let x=await api('/api/cache/dossier/rebuild',{method:'POST',body:JSON.stringify({confirmed:true})});$('coveragestatus').textContent=x.message;renderCacheAudit(x.audit);renderStatus(await api('/api/status'))}catch(e){$('cacheaudit').innerHTML='<span class="error">'+esc(e.message)+'</span>'}}
async function clearSummaryCaches(){if(!confirm('清除所有本地材料摘要和 BG 综合档案？不会删除原始文件、本地索引或 OCR，但之后需要重新预读。'))return;try{let x=await api('/api/cache/clear',{method:'POST',body:JSON.stringify({confirmed:true})});$('coveragestatus').textContent=x.message;renderCacheAudit(x.audit)}catch(e){$('cacheaudit').innerHTML='<span class="error">'+esc(e.message)+'</span>'}}
function clearTargetTree(){savedTargetSelection=new Set();treeRestoreNote='';scannedSelection='';setScanReportAvailable(null);$('targettree').textContent='选择文件夹后显示可展开的文件树。';$('targettree').classList.add('muted');$('treestatus').textContent='';updateMaterialFlowButtons()}
async function pickFolderForTree(){await pick('folder','targetpath');if($('targetpath').value)loadTargetTree()}
function treeFileCount(){return [...$('targettree').querySelectorAll('input.tree-file:checked')].length}
function updateTreeStatus(){let count=treeFileCount(),signature=selectedTargetPaths().sort().join('|');if(scannedSelection&&signature!==scannedSelection)setScanReportAvailable(null);$('treestatus').textContent=(count?`已选择 ${count} 个受支持文件。`:'尚未选择材料；勾选文件或整个子文件夹。')+(treeRestoreNote?' '+treeRestoreNote:'');updateMaterialFlowButtons()}
function refreshFolderState(folder){let files=[...folder.querySelectorAll('input.tree-file:not(:disabled)')];let box=folder.querySelector(':scope > summary input.tree-folder');if(!box||!files.length)return;let checked=files.filter(x=>x.checked).length;box.checked=checked===files.length;box.indeterminate=checked>0&&checked<files.length}
function refreshAllFolderStates(){[...$('targettree').querySelectorAll('details')].reverse().forEach(refreshFolderState);updateTreeStatus()}
function recommendedTreePaths(node,paths=[]){if(node.type==='file'){if(node.recommended)paths.push(node.relative);return paths}(node.children||[]).forEach(child=>recommendedTreePaths(child,paths));return paths}
function makeTreeNode(node,depth=0){if(node.type==='folder'){let details=document.createElement('details');details.open=depth<1;let summary=document.createElement('summary');let box=document.createElement('input');box.type='checkbox';box.className='tree-folder';box.addEventListener('click',e=>e.stopPropagation());box.addEventListener('change',()=>{details.querySelectorAll('input.tree-file:not(:disabled)').forEach(x=>x.checked=box.checked);refreshAllFolderStates()});let label=document.createElement('label');label.textContent='📁 '+node.name;summary.append(box,label);details.append(summary);let children=document.createElement('div');children.className='tree-children';node.children.forEach(child=>children.append(makeTreeNode(child,depth+1)));details.append(children);return details}let row=document.createElement('div');row.className='tree-file'+(node.supported?'':' unsupported');let box=document.createElement('input');box.type='checkbox';box.className='tree-file';box.dataset.path=node.path;box.checked=!!node.supported&&savedTargetSelection.has(node.relative);box.disabled=!node.supported;box.addEventListener('change',refreshAllFolderStates);let label=document.createElement('label');let role=node.material_role_label?` · ${node.material_role_label}`:'';let hint=node.supported&&!node.recommended?' · 默认不选':'';label.textContent='📄 '+node.name+(node.supported?` · ${(node.bytes/1024/1024).toFixed(node.bytes<1024*1024?2:1)} MB${role}${hint}`:` · 不支持${role}`);row.append(box,label);return row}
async function loadTargetTree(){let target=$('targetpath').value.trim();if(!target){$('treestatus').innerHTML='<span class="error">请先选择或粘贴一个 BG 文件夹路径。</span>';return}try{$('treestatus').textContent='正在仅读取文件夹结构…';let x=await api('/api/target-tree?target='+encodeURIComponent(target));savedTargetSelection=new Set(x.saved_selection||[]);let notes=[];if(savedTargetSelection.size)notes.push(`已恢复上次的 ${savedTargetSelection.size} 项选择。`);else{savedTargetSelection=new Set(recommendedTreePaths(x.tree));notes.push(`已按资料类型默认选择 ${savedTargetSelection.size} 项原始资料；派生重复资料默认未选。`)}if(x.changed_saved_files)notes.push(`${x.changed_saved_files} 个已选文件内容已变化。`);if(x.missing_saved_files)notes.push(`${x.missing_saved_files} 个原选文件不存在，未恢复。`);treeRestoreNote=notes.join(' ');let host=$('targettree');host.classList.remove('muted');host.innerHTML='';host.append(makeTreeNode(x.tree));refreshAllFolderStates();if(x.truncated)$('treestatus').innerHTML='<span class="error">文件树超过 5000 项，已截断；请进入更具体的 BG 文件夹。</span>'}catch(e){$('treestatus').innerHTML='<span class="error">'+esc(e.message)+'</span>'}}
function selectedTargetPaths(){return [...$('targettree').querySelectorAll('input.tree-file:checked')].map(x=>x.dataset.path)}
async function analyzeTarget(){let confirm=$('confirmmaterials');if(confirm){confirm.disabled=true;confirm.textContent='正在本地读取…'}try{let target=$('targetpath').value.trim();let selected=selectedTargetPaths();if($('targettree').querySelector('.tree-file')&&!selected.length)throw Error('请先在文件树中勾选至少一个材料。');let x=await api('/api/target',{method:'POST',body:JSON.stringify({target,codebook:$('codebook').value,selected_paths:selected})});scannedSelection=selected.slice().sort().join('|');renderStatus(x.status);$('bgstatus').textContent=x.classification?`已确认 ${x.target_kind}中的 ${x.sources} 个选定材料；Codebook 分类已就绪。`:`已确认 ${x.target_kind}中的 ${x.sources} 个选定材料；可直接开始普通材料问答。`;renderScanReport(x);$('coveragestatus').textContent='材料范围已更新；首次分类提问会自动读取并理解新增或变化的材料。';loadDocs();loadCacheAudit()}catch(e){$('bgstatus').innerHTML='<span class="error">'+e.message+'</span>'}finally{if(confirm)confirm.textContent='确认选中材料';updateMaterialFlowButtons()}}
async function prepareCoverage(full=false){if(busy)return;busy=true;$('coveragestatus').textContent=full?'正在完整覆盖所有页并生成可审计摘要；会消耗相应 token 与费用…':'正在按文件角色准备分类证据；大型 Datasheet 默认只预读前 15 页，并计入 token 与费用…';try{let x=await api('/api/coverage',{method:'POST',body:JSON.stringify({full})});renderCoverageReport(x)}catch(e){$('coveragestatus').innerHTML='<span class="error">分类证据准备失败：'+esc(e.message)+'</span>'}finally{busy=false}}
async function clearBg(){try{renderStatus(await api('/api/bg',{method:'DELETE'}));$('bgstatus').textContent='已退出 BG 模式。'}catch(e){$('bgstatus').textContent=e.message}}
const compareOptions=[['claude-haiku-5-5','Claude Haiku 5.5'],['claude-sonnet-5-5','Claude Sonnet 5.5'],['claude-opus-5','Claude Opus 5'],['gemini-3.5-flash-lite','Gemini 3.5 Flash-Lite'],['gemini-2.5-pro','Gemini 2.5 Pro'],['gemini-2.5-flash','Gemini 2.5 Flash'],['deepseek-r1-0528-maas','DeepSeek R1 (0528)'],['llama-3.3-70b-instruct-maas','Llama 3.3 70B'],['glm-5-maas','GLM-5']];
function renderCompareSlots(){let host=$('comparemodels');host.innerHTML=compareSlots.map((slot,index)=>{let options='<option value="">选择模型…</option>'+compareOptions.map(([value,label])=>'<option value="'+value+'" '+(slot.value===value?'selected':'')+'>'+label+'</option>').join('')+'<option value="__custom__" '+(slot.value==='__custom__'?'selected':'')+'>其他：手动输入 Model ID…</option>';return '<div class="field"><label>对比模型 '+(index+1)+'</label><div class="row"><select id="cmpsel'+index+'" onchange="changeCompareModel('+index+')">'+options+'</select>'+(index>0?'<button class="ghost" onclick="removeCompareModel('+index+')">×</button>':'')+'</div>'+(slot.value==='__custom__'?'<input id="cmpcustom'+index+'" value="'+esc(slot.custom||'')+'" placeholder="输入准确的 Bosch Farm Model ID" oninput="compareSlots['+index+'].custom=this.value">':'')+'</div>'}).join('');let add=$('addcompare');add.disabled=compareSlots.length>=4;add.textContent=compareSlots.length>=4?'最多 4 个模型':'＋ 添加对比模型';if(compareSlots.length>=4)$('comparestatus').textContent='已达到最多 4 个对比模型。'}
function changeCompareModel(index){let select=$('cmpsel'+index);compareSlots[index].value=select.value;if(select.value!=='__custom__')compareSlots[index].custom='';renderCompareSlots();if(select.value==='__custom__')setTimeout(()=>$('cmpcustom'+index).focus(),0)}
function addCompareModel(){if(compareSlots.length>=4){$('comparestatus').textContent='最多只能同时对比 4 个模型。';return}compareSlots.push({value:'',custom:''});renderCompareSlots();$('cmpsel'+(compareSlots.length-1)).focus()}
function removeCompareModel(index){compareSlots.splice(index,1);renderCompareSlots();$('comparestatus').textContent=''}
function selectedCompareModels(){return compareSlots.map((slot,index)=>slot.value==='__custom__'?$('cmpcustom'+index).value.trim():slot.value).filter(Boolean)}
async function compareModels(){if(busy)return;let q=$('question').value.trim()||lastQuestion;if(!q){$('comparestatus').innerHTML='<span class="error">先在下方输入问题，或先发送一次问题。</span>';return}let models=selectedCompareModels();if(models.length<2||models.length>4||new Set(models).size!==models.length){$('comparestatus').innerHTML='<span class="error">请选择 2–4 个不同模型；“其他”中输入准确的 Bosch Farm Model ID。</span>';return}busy=true;lastQuestion=q;$('comparestatus').textContent='正在按顺序请求 '+models.length+' 个模型…';let wait=message('正在进行多模型对比：'+models.join(' · '));try{let x=await api('/api/compare',{method:'POST',body:JSON.stringify({question:q,models})});wait.remove();let box=document.createElement('section');box.className='comparison';box.innerHTML='<div class="message assistant"><b>多模型对比</b><br>同一问题：'+esc(q)+'<br><span class="muted">相同证据：'+x.sources.map(esc).join(' · ')+'</span></div><div class="comparison-grid"></div>';let grid=box.querySelector('.comparison-grid');for(let r of x.results){let card=document.createElement('article');card.className='card';if(!r.ok){card.innerHTML='<b>'+esc(r.requested_model)+'</b><p class="error">请求失败</p><div class="muted">'+esc(r.error||'未知错误')+'</div>';grid.append(card);continue}let u=r.usage||{};let cost=u.cost_usd===null||u.cost_usd===undefined?'未配置价格':'$'+Number(u.cost_usd).toFixed(6);let classification=r.classification?'<div class="chip">已校验类别：'+esc(r.classification.label)+' · '+esc(r.classification.confidence)+'</div>':'';card.innerHTML='<b>'+esc(r.model_response)+'</b>'+(r.model_response!==r.requested_model?'<div class="muted">请求：'+esc(r.requested_model)+'</div>':'')+'<div class="muted ok">成功 · Token '+(u.input||0)+' / '+(u.output||0)+' · '+cost+'</div>'+classification+'<hr><div class="answer"></div>'+(r.notices?.length?'<div class="muted">'+r.notices.map(esc).join('<br>')+'</div>':'');card.querySelector('.answer').textContent=r.answer;grid.append(card)}$('chat').append(box);$('comparestatus').innerHTML='<span class="ok">对比完成；结果仅显示在当前页面，不写入普通会话。</span>'}catch(e){wait.textContent='多模型对比错误：'+e.message;wait.classList.add('error');$('comparestatus').innerHTML='<span class="error">'+esc(e.message)+'</span>'}finally{busy=false;$('chat').scrollTop=1e9}}
function processingCard(){let card=document.createElement('section');card.className='message assistant';card.style.border='1px solid #334155';card.innerHTML='<b>正在处理你的问题</b><div class="muted" data-process-text>正在建立本地处理连接…</div><div style="height:7px;background:#0b1220;border-radius:8px;overflow:hidden;margin-top:9px"><div data-process-bar style="height:100%;width:4%;background:#38bdf8;transition:width .25s ease"></div></div>';$('chat').append(card);return card}
function updateProcessing(card,event){let text=card.querySelector('[data-process-text]'),bar=card.querySelector('[data-process-bar]');text.textContent=event.text||'正在处理…';if(typeof event.percent==='number')bar.style.width=Math.max(4,Math.min(100,event.percent))+'%';if(event.phase==='complete'){card.style.borderColor='#22c55e';bar.style.background='#22c55e'}}
function showChatResult(x){message(x.answer);if(x.classification)$('chat').append(classificationCard(x.classification));let summary=coverageSummaryCard(x.coverage_summary);if(summary)$('chat').append(summary);if(x.reasoning){let d=document.createElement('details');d.className='reason';d.innerHTML='<summary>模型推理（接口返回）</summary><pre></pre>';d.querySelector('pre').textContent=x.reasoning;$('chat').append(d)}if(x.notices?.length)message(x.notices.join('\n'),'assistant');renderEvidenceSources(x.sources,x.dfc_evidence);$('changes').innerHTML=x.changes?.length?x.changes.map(c=>`<div class="card"><b>${c.path}</b><br>${c.reason}<pre class="diff">${esc(c.diff)}</pre></div>`).join('')+'<button onclick="apply()">应用修改</button>':'无';$('analysisexport').innerHTML=x.can_export_bg?'<button class="ghost" onclick="exportBgAnalysis()">导出本次 BG 分析</button>':'仅在 Baugruppe 分析完成后可导出。';renderUsageDetail(x.turn_usage,x.model_response);renderStatus(x.usage)}
async function chat(){if(busy||!$('question').value.trim())return;busy=true;let q=$('question').value;lastQuestion=q;$('question').value='';message(q,'user');let wait=processingCard(),buffer='',result=null;try{let response=await fetch('/api/chat/stream',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q})});if(!response.ok)throw Error((await response.json()).detail||'请求失败');let reader=response.body.getReader(),decoder=new TextDecoder();while(true){let part=await reader.read();if(part.done)break;buffer+=decoder.decode(part.value,{stream:true});let blocks=buffer.split('\n\n');buffer=blocks.pop();for(let block of blocks){let line=block.split('\n').find(item=>item.startsWith('data: '));if(!line)continue;let event=JSON.parse(line.slice(6));if(event.type==='progress')updateProcessing(wait,event);else if(event.type==='result')result=event.data;else if(event.type==='error')throw Error(event.message||'处理失败')}}if(!result)throw Error('请求未返回结果');updateProcessing(wait,{phase:'complete',text:'处理完成。',percent:100});showChatResult(result)}catch(e){wait.querySelector('[data-process-text]').textContent='错误：'+e.message;wait.classList.add('error')}finally{busy=false;$('chat').scrollTop=1e9}}
async function exportSession(){try{let x=await api('/api/export/session',{method:'POST'});$('sessionexport').innerHTML='<span class="ok">已导出：'+esc(x.path)+'</span>'}catch(e){$('sessionexport').innerHTML='<span class="error">'+esc(e.message)+'</span>'}}
async function exportBgAnalysis(){try{let x=await api('/api/export/bg-analysis',{method:'POST'});$('analysisexport').innerHTML='<span class="ok">已导出：'+esc(x.path)+'</span>'}catch(e){$('analysisexport').innerHTML='<span class="error">'+esc(e.message)+'</span>'}}
function esc(s){let e=document.createElement('div');e.textContent=s;return e.innerHTML}async function apply(){try{let x=await api('/api/apply',{method:'POST'});$('changes').innerHTML='<span class="ok">已应用 '+x.applied+' 个修改。</span>';message('已写入 '+x.applied+' 个经确认的文件修改。')}catch(e){$('changes').innerHTML='<span class="error">'+e.message+'</span>'}}
</script></body></html>'''


if __name__ == "__main__":
    print("Bosch Local Workbench: http://127.0.0.1:8765")
    uvicorn.run(app, host="127.0.0.1", port=8765)
