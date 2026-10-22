"""Local browser workbench for the Bosch Farm code/document chat.

Run only on 127.0.0.1.  The browser is a local UI: paths, indexes, source
files, credentials and session data stay on the computer that starts it.
"""
from __future__ import annotations

import difflib
import json
import os
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn

from dotenv import load_dotenv
from code_chat_agent import (PricingCatalog, ProjectState, SYSTEM, ensure_relative,
                             excerpt, parse_json, prompt_for, safe_name, sha256)
from local_document_library import LocalDocumentLibrary
from llm_connector_with_prompt_caching import LLMConnector


app = FastAPI(title="Bosch Local Workbench", docs_url=None, redoc_url=None)
LOCK = threading.Lock()
ACTIVE: dict[str, Any] = {}


def app_state_home() -> Path:
    return Path(__file__).resolve().parent / "AI_Bot_State"


def workbench_settings_path() -> Path:
    return app_state_home() / "workbench_settings.json"


def model_tests_path() -> Path:
    return app_state_home() / "model_tests.json"


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
            "model": str(data.get("model", "claude-haiku-5.5")) or "claude-haiku-5.5",
        } if isinstance(data, dict) else {"workspace": "", "session": "default", "model": "claude-haiku-5.5"}
    except (OSError, ValueError):
        return {"workspace": "", "session": "default", "model": "claude-haiku-5.5"}


def save_workbench_settings(workspace: Path, session_name: str, model: str) -> None:
    app_state_home().mkdir(parents=True, exist_ok=True)
    workbench_settings_path().write_text(
        json.dumps({"workspace": str(workspace), "session": session_name, "model": model}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


class Setup(BaseModel):
    workspace: str
    state_dir: str
    model: str = "gpt-5.5"
    session: str = "default"
    env_file: str = ""


class PathRequest(BaseModel):
    path: str


class ModelTestRequest(BaseModel):
    model: str


class ModelSwitchRequest(BaseModel):
    model: str


class SessionRenameRequest(BaseModel):
    name: str


class SessionDeleteRequest(BaseModel):
    confirmed: bool = False


class BGRequest(BaseModel):
    codebook: str
    folder: str


class ChatRequest(BaseModel):
    question: str


class CompareRequest(BaseModel):
    question: str
    models: list[str]


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


def available_sessions(state: ProjectState) -> list[str]:
    root = state.root.parent
    if not root.is_dir():
        return [state.root.name]
    names = sorted((item.name for item in root.iterdir() if item.is_dir()), key=str.lower)
    return names or [state.root.name]


def safe_file(value: str) -> Path:
    path = Path(value.strip().strip('"')).expanduser().resolve()
    if not path.is_file():
        raise HTTPException(400, f"文件不存在：{path}")
    return path


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


def call_model(data: dict[str, Any], question: str) -> dict[str, Any]:
    state, documents, llm = data["state"], data["documents"], data["llm"]
    bg_context = state.data.get("bg_context")
    matches = state.search(question)
    snippets = {item: excerpt(state, item, question) for item in matches}
    preferred = ([bg_context.get("codebook_id")] + list(bg_context.get("source_ids", []))) if bg_context else None
    evidence = documents.search(question, preferred_ids=preferred, classification=bool(bg_context))
    visuals = documents.visual_paths(evidence, state.root / "visual_cache")
    reasoning, notices = [], []

    def events(kind: str, text: str):
        if kind == "reasoning": reasoning.append(text)
        elif kind == "notice": notices.append(text)

    raw = llm.ask_about_files(visuals, prompt_for(state, question, snippets, document_snippets=evidence, bg_context=bg_context),
                               SYSTEM, {"maxOutputTokens": 4096, "temperature": 0}, stream=True, event_handler=events)
    estimates = []
    usage_records = [llm.get_last_token_usage() or {}]
    estimate = state.note_usage(usage_records[-1], data["pricing"], data["model"])
    if estimate: estimates.append(estimate)
    try:
        action = parse_json(raw)
    except Exception:
        # Some Bosch Farm models return a normal natural-language answer despite
        # the code-action schema. A read-only question must remain useful:
        # show that answer and never treat it as a file modification.
        answer = raw.strip() or "模型没有返回可显示的文字。"
        state.add_turn("user", question)
        state.add_turn("assistant", answer)
        return {"answer": answer, "reasoning": "".join(reasoning), "notices": notices,
                "sources": evidence, "visuals": visuals, "changes": [], "can_export_bg": False,
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
        raw = llm.ask_about_files(visuals, prompt_for(state, question, snippets, complete, evidence, bg_context),
                                   SYSTEM, {"maxOutputTokens": 3000, "temperature": 0}, stream=True, event_handler=events)
        usage_records.append(llm.get_last_token_usage() or {})
        estimate = state.note_usage(usage_records[-1], data["pricing"], data["model"])
        if estimate: estimates.append(estimate)
        action = parse_json(raw)
    changes = build_diff(state, action.get("changes", []))
    data["pending"] = changes
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
            "bg_context": dict(bg_context),
            "token_usage": turn_token_usage,
        }
        state.save()
    return {"answer": action.get("answer", ""), "reasoning": "".join(reasoning), "notices": notices,
            "sources": evidence, "visuals": visuals, "changes": [{k: v for k, v in item.items() if k != "content"} for item in changes],
            "can_export_bg": bool(bg_context),
            "turn_usage": turn_token_usage,
            "model_response": llm.last_response_model or data["model"],
            "turn_cost": turn_token_usage["cost_usd"] if estimates else None,
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
    evidence = documents.search(question, preferred_ids=preferred, classification=True)
    visuals = documents.visual_paths(evidence, state.root / "visual_cache")
    prompt = prompt_for(state, question, snippets, document_snippets=evidence, bg_context=bg_context)
    results = []
    for index, model in enumerate(models, start=1):
        notices: list[str] = []

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
            usage = connector.get_last_token_usage() or {}
            token_usage = summarize_usage([usage])
            actual_model = connector.last_response_model or model
            estimate = data["pricing"].estimate(actual_model, token_usage["input"], token_usage["output"])
            token_usage["cost_usd"] = float(estimate["cost_usd"]) if estimate else None
            try:
                action = parse_json(raw)
                answer = str(action.get("answer", "")).strip() or raw.strip()
            except Exception:
                answer = raw.strip() or "模型没有返回可显示的文字。"
            results.append({"requested_model": model, "model_response": actual_model, "ok": True,
                            "answer": answer, "usage": token_usage, "notices": notices})
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
    ACTIVE.clear(); ACTIVE.update({"state": state, "documents": documents, "model": request.model,
                                    "llm": LLMConnector(request.model, key, session_id=state.data["session_id"]),
                                    "pricing": PricingCatalog(price_file), "pending": []})
    state.scan()
    save_workbench_settings(workspace, state.root.name, request.model)
    return status_data(ACTIVE)


@app.get("/api/status")
def status(): return status_data(session())


@app.post("/api/model")
def switch_model(request: ModelSwitchRequest):
    model = request.model.strip()
    if not model:
        raise HTTPException(400, "请输入 Bosch Farm 的准确 Model ID。")
    data = session()
    try:
        data["llm"] = LLMConnector(model, data["llm"].api_key, session_id=data["state"].data["session_id"])
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    data["model"] = model
    save_workbench_settings(data["state"].workspace, data["state"].root.name, model)
    return status_data(data)


def activate_local_session(data: dict[str, Any], session_name: str) -> dict:
    state = ProjectState(app_state_home(), data["state"].workspace, session_name)
    data["state"] = state
    data["documents"] = LocalDocumentLibrary(state.root.parent / "documents.json")
    data["llm"] = LLMConnector(data["model"], data["llm"].api_key, session_id=state.data["session_id"])
    data["pending"] = []
    save_workbench_settings(state.workspace, state.root.name, data["model"])
    return status_data(data)


@app.post("/api/session/rename")
def rename_session(request: SessionRenameRequest):
    data = session()
    name = safe_name(request.name.strip())
    state = data["state"]
    target = state.root.parent / name
    if target == state.root:
        return status_data(data)
    if target.exists():
        raise HTTPException(409, "已存在同名会话。")
    try:
        state.root.rename(target)
    except OSError as exc:
        raise HTTPException(500, f"无法重命名会话：{exc}") from exc
    return activate_local_session(data, name)


@app.post("/api/session/delete")
def delete_session(request: SessionDeleteRequest):
    if not request.confirmed:
        raise HTTPException(400, "必须确认后才可删除会话。")
    data = session()
    state = data["state"]
    current = state.root
    parent = current.parent
    try:
        shutil.rmtree(current)
    except OSError as exc:
        raise HTTPException(500, f"无法删除会话：{exc}") from exc
    remaining = sorted((item.name for item in parent.iterdir() if item.is_dir()), key=str.lower) if parent.is_dir() else []
    return activate_local_session(data, remaining[0] if remaining else "default")


@app.get("/api/settings")
def settings():
    # Only the local path is returned. No source documents or credentials leave this computer.
    return load_workbench_settings()


@app.get("/api/sessions")
def sessions():
    state = session()["state"]
    return {"current": state.root.name, "sessions": available_sessions(state)}


@app.get("/api/history")
def history():
    records = session()["state"].full_history()
    return {"history": [
        {"role": item.get("role", "assistant"), "content": str(item.get("content", ""))}
        for item in records if isinstance(item, dict) and item.get("content")
    ]}


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
    return [{"id": item["id"], "name": item["name"], "path": item["path"], "chunks": len(item.get("chunks", []))}
            for item in session()["documents"].list()]


@app.post("/api/document")
def add_document(request: PathRequest):
    item = session()["documents"].add(str(safe_file(request.path)))
    return {"id": item["id"], "name": item["name"], "chunks": len(item["chunks"])}


@app.post("/api/bg")
def activate_bg(request: BGRequest):
    data = session(); codebook = data["documents"].add(str(safe_file(request.codebook)))
    folder = Path(request.folder.strip().strip('"')).expanduser().resolve()
    sources, skipped = data["documents"].add_folder(str(folder))
    data["state"].data["bg_context"] = {"codebook_id": codebook["id"], "codebook_name": codebook["name"],
        "source_ids": [item["id"] for item in sources], "folder": str(folder)}
    data["state"].save()
    return {"sources": len(sources), "skipped": skipped[:10], "status": status_data(data)}


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
*{box-sizing:border-box}body{margin:0;background:#111827;color:#e5e7eb;font:14px Inter,Segoe UI,Arial,sans-serif}button,input,select{font:inherit}button{background:#2563eb;color:white;border:0;border-radius:7px;padding:8px 10px;cursor:pointer}button.ghost{background:#263244;color:#cbd5e1}.shell{height:100vh;display:grid;grid-template-columns:270px minmax(420px,1fr) 300px}.side{background:#172033;border-right:1px solid #334155;padding:16px;overflow:auto}.right{border-left:1px solid #334155;border-right:0}.main{display:flex;flex-direction:column;min-width:0}.brand{font-weight:700;font-size:16px;margin-bottom:16px}.muted{color:#94a3b8;font-size:12px}.field{margin:10px 0}.field label{display:block;font-size:12px;color:#a9b6c8;margin-bottom:5px}input{width:100%;background:#0f172a;border:1px solid #3b4960;border-radius:6px;padding:8px;color:#f8fafc}.row{display:flex;gap:7px}.row>*{min-width:0}.row input{flex:1}.chat{flex:1;overflow:auto;padding:24px max(32px,8%)}.message{max-width:920px;margin:0 auto 18px;padding:13px 15px;border-radius:10px;white-space:pre-wrap;line-height:1.55}.user{background:#1e3a5f;margin-left:auto;max-width:78%}.assistant{background:#1e293b}.reason{margin:8px auto 18px;max-width:920px;background:#171e2d;border:1px solid #334155;border-radius:8px;padding:9px}.reason summary{cursor:pointer;color:#b9c9e2}.reason pre{white-space:pre-wrap;font-size:12px;color:#aab7c8}.composer{border-top:1px solid #334155;padding:13px 8%;display:flex;gap:8px;background:#111827}.composer input{padding:12px}.composer button{padding:10px 17px}.card{border:1px solid #334155;border-radius:8px;padding:10px;margin:10px 0;background:#141d2d}.list{font-size:12px;line-height:1.5;word-break:break-word}.diff{white-space:pre-wrap;background:#0b1220;border-radius:6px;padding:8px;max-height:230px;overflow:auto;color:#d7e1ed}.ok{color:#86efac}.error{color:#fca5a5}.chip{display:inline-block;padding:3px 6px;border-radius:5px;background:#22314a;color:#bcd5ff;margin:2px;font-size:11px}.check{display:block;margin:5px 0;color:#dbeafe;font-size:12px}.check input{width:auto;margin-right:5px}.comparison{max-width:1180px;margin:0 auto 20px}.comparison-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(255px,1fr));gap:10px}.comparison .card{margin:0}.comparison .answer{white-space:pre-wrap;line-height:1.5;max-height:440px;overflow:auto}
</style></head><body><div class="shell"><aside class="side"><div class="brand">Bosch Local Workbench</div><div class="muted">仅本机 127.0.0.1 · 缓存固定保存在程序目录 AI_Bot_State</div>
<div class="field"><label>代码工作区文件夹</label><div class="row"><input id="workspace" placeholder="C:\\...\\项目文件夹"><button class="ghost" onclick="pick('folder','workspace')">选择</button></div></div><div class="field"><label>模型</label>
<select id="model" onchange="toggleCustomModel();loadModelStatus()">
<option value="claude-haiku-5.5">Claude Haiku 5.5（推荐：日常、便宜）</option>
<option value="gemini-3.5-flash-lite">Gemini 3.5 Flash-Lite（最快、最省）</option>
<option value="gpt-6-luna-2026-09-22">GPT-6 Luna（轻量推理）</option>
<option value="__custom__">其他：手动输入 Model ID…</option>
</select>
<input id="custommodel" placeholder="粘贴准确的 Bosch Farm Model ID" style="display:none;margin-top:7px"></div><div id="modelstatus" class="muted"></div><div class="row"><button onclick="setup()">打开工作区</button><button class="ghost" onclick="switchModel()">切换模型</button><button class="ghost" onclick="testModel()">测试模型</button></div><div id="setupmsg" class="muted"></div>
<div class="field"><label>聊天会话</label><div class="row"><select id="session"></select><button class="ghost" onclick="openSession()">切换</button><button class="ghost" onclick="newSession()">新建</button><button class="ghost" onclick="renameSession()">改名</button><button class="ghost" onclick="deleteSession()">删除</button></div><div id="sessionmsg" class="muted"></div></div>
<hr><b>单一文件分析</b><div class="muted">选择一个 PDF / Excel / PNG，加入后可围绕该文件连续提问。</div><div class="field"><label>要分析的文件</label><div class="row"><input id="docpath" placeholder="PDF / Excel / PNG …"><button class="ghost" onclick="pick('file','docpath')">选择</button><button class="ghost" onclick="addDoc()">加入</button></div></div><div id="docs" class="list"></div>
<hr><b>Baugruppe 文件夹分析</b><div class="muted">选择 Codebook 和一个 BG 文件夹；程序读取其中全部受支持文件，用于分类及错误原因分析。</div><div class="field"><label>Codebook 文件</label><div class="row"><input id="codebook" placeholder="…Codebook.pdf"><button class="ghost" onclick="pick('file','codebook')">选择</button></div></div><div class="field"><label>BG 文件夹</label><div class="row"><input id="bgfolder" placeholder="选择一个 Baugruppe 文件夹"><button class="ghost" onclick="pick('folder','bgfolder')">选择</button></div></div><button class="ghost" onclick="bg()">开始文件夹分析</button> <button class="ghost" onclick="clearBg()">退出文件夹分析</button><div id="bgstatus" class="muted"></div>
<hr><b>多模型对比</b><div class="muted">同一条问题、同一份 BG 证据；逐个选择 2–4 个模型后顺序请求。结果不会写进普通聊天会话。</div><div id="comparemodels"></div><div class="row"><button class="ghost" id="addcompare" onclick="addCompareModel()">＋ 添加对比模型</button><button class="ghost" onclick="compareModels()">开始对比</button></div><div id="comparestatus" class="muted"></div></aside>
<main class="main"><div class="chat" id="chat"><div class="message assistant">选择工作区后即可聊天。代码修改会先显示 diff，只有点击“应用修改”才会写入本地文件。</div></div><div class="composer"><input id="question" placeholder="问代码，或根据 Codebook 判断 Baugruppe …" onkeydown="if(event.key==='Enter')chat()"><button onclick="chat()">发送</button></div></main>
<aside class="side right"><b>本轮状态</b><div id="status" class="card muted">尚未打开工作区</div><b>会话导出</b><div id="sessionexport" class="card"><button class="ghost" onclick="exportSession()">导出完整会话</button></div><b>本轮 token 明细</b><div id="usagedetail" class="card muted">完成一次请求后显示。</div><b>BG 分析导出</b><div id="analysisexport" class="card muted">仅在 Baugruppe 分析完成后可导出。</div><b>证据来源</b><div id="sources" class="card list">回答后会显示实际传给模型的来源。</div><b>待应用修改</b><div id="changes" class="list">无</div></aside></div>
<script>
const $=id=>document.getElementById(id);let busy=false,lastQuestion='',compareSlots=[{value:'claude-haiku-5.5',custom:''}];
async function restoreLastWorkspace(){
  try{
    let s=await api('/api/settings');
    if(!s.workspace)return;
    $('workspace').value=s.workspace;
    setSelectedModel(s.model||'claude-haiku-5.5');
    $('session').innerHTML='<option>'+ (s.session||'default') +'</option>';
    $('setupmsg').textContent='正在自动打开上次工作区…';
    await setup();
  }catch{
    $('setupmsg').textContent='无法自动打开上次工作区；请重新选择路径。';
  }
}
window.addEventListener('DOMContentLoaded',()=>{renderCompareSlots();restoreLastWorkspace()});
async function api(url,opt={}){let r=await fetch(url,{headers:{'Content-Type':'application/json'},...opt});let d=await r.json();if(!r.ok)throw Error(d.detail||'请求失败');return d}
async function pick(kind,target){try{$(target).value=(await api('/api/pick/'+kind)).path||''}catch(e){alert(e.message)}}
function message(text,kind='assistant'){let e=document.createElement('div');e.className='message '+kind;e.textContent=text;$('chat').append(e);$('chat').scrollTop=1e9;return e}
function renderStatus(s){$('status').innerHTML=`模型：<b>${s.model}</b><br>会话：${s.session_name||'default'}<br>代码：${s.code_files} 文件<br>材料：${s.documents} 个<br>累计请求：${s.requests}<br>累计 Token：${s.input_tokens} / ${s.output_tokens}<br>累计估算：${s.cost}<br>${s.bg_context?'<span class="ok">BG 模式：'+s.bg_context.codebook_name+'</span>':'普通模式'}`}
function renderUsageDetail(u,model){if(!u)return;$('usagedetail').innerHTML=`实际模型：<b>${esc(model||'—')}</b><br>输入 / 输出 / 总计：${u.input} / ${u.output} / ${u.total}<br>推理：${u.reasoning||0} ｜ Gemini thinking：${u.gemini_thinking||0}<br>Claude 缓存读 / 写：${u.cache_read||0} / ${u.cache_write||0}<br>本轮估算：${Number(u.cost_usd||0).toFixed(6)}`}
function toggleCustomModel(){let custom=$('model').value==='__custom__';$('custommodel').style.display=custom?'block':'none';if(custom)$('custommodel').focus()}
function setSelectedModel(model){let known=[...$('model').options].some(option=>option.value===model);$('model').value=known?model:'__custom__';$('custommodel').value=known?'':model;toggleCustomModel();loadModelStatus()}
function selectedModel(){let selected=$('model').value;return selected==='__custom__' ? $('custommodel').value.trim() : selected}
async function loadSessions(){try{let x=await api('/api/sessions');$('session').innerHTML=x.sessions.map(n=>`<option value="${esc(n)}" ${n===x.current?'selected':''}>${esc(n)}</option>`).join('');$('sessionmsg').textContent='聊天记录、BG 状态、代码索引和 token 统计按会话分开；已加入的材料索引按工作区共享。'}catch(e){$('sessionmsg').textContent=e.message}}
async function loadHistory(){try{let x=await api('/api/history');$('chat').innerHTML='';if(!x.history.length){message('这是一个新会话，可以直接开始提问。');return}for(let item of x.history)message(item.content,item.role==='user'?'user':'assistant')}catch{}}
async function setup(){try{let model=selectedModel();if(!model)throw Error('请先输入 Bosch Farm 的准确 Model ID。');let s=await api('/api/setup',{method:'POST',body:JSON.stringify({workspace:$('workspace').value,state_dir:'',env_file:'',model:model,session:$('session').value.trim()||'default'})});renderStatus(s);$('setupmsg').textContent='已打开。';loadDocs();loadSessions();loadHistory()}catch(e){$('setupmsg').innerHTML='<span class="error">'+e.message+'</span>'}}
async function openSession(){if(!$('session').value)return;await setup()}
async function newSession(){let name=prompt('新会话名称，例如：BG_012 或 token_test');if(!name||!name.trim())return;$('session').innerHTML='<option>'+esc(name.trim())+'</option>';await setup()}
async function renameSession(){try{let name=prompt('输入新的会话名称：',$('session').value);if(!name||!name.trim())return;let s=await api('/api/session/rename',{method:'POST',body:JSON.stringify({name:name.trim()})});renderStatus(s);$('sessionmsg').textContent='会话已重命名。';loadSessions()}catch(e){$('sessionmsg').innerHTML='<span class="error">'+e.message+'</span>'}}
async function deleteSession(){if(!confirm('确定删除当前会话吗？只会删除本地聊天记录、索引和导出文件，不会删除代码工作区或原始材料。'))return;try{let s=await api('/api/session/delete',{method:'POST',body:JSON.stringify({confirmed:true})});renderStatus(s);$('sessionmsg').textContent='当前会话已删除，已切换到其他会话。';loadSessions();loadHistory()}catch(e){$('sessionmsg').innerHTML='<span class="error">'+e.message+'</span>'}}
async function switchModel(){try{let model=selectedModel();if(!model)throw Error('请先输入 Bosch Farm 的准确 Model ID。');let s=await api('/api/model',{method:'POST',body:JSON.stringify({model})});renderStatus(s);$('setupmsg').innerHTML='<span class="ok">已切换至 '+esc(model)+'；当前会话与材料保持不变。</span>'}catch(e){$('setupmsg').innerHTML='<span class="error">'+e.message+'</span>'}}
async function loadModelStatus(){try{let x=await api('/api/model-tests');let r=x.tests[selectedModel()];if(!r){$('modelstatus').textContent='尚未测试此模型。';return}if(!r.ok){$('modelstatus').innerHTML='<span class="error">上次测试失败：'+esc(r.tested_at)+'</span>';return}$('modelstatus').innerHTML='<span class="ok">上次可用：'+esc(r.tested_at)+'；'+esc(r.streaming||'未记录流式状态')+'；usage '+(r.usage_available===false?'未返回':'已返回')+'</span>'}catch{}}
async function testModel(){try{let model=selectedModel();if(!model)throw Error('请先输入 Bosch Farm 的准确 Model ID。');$('setupmsg').textContent='正在发送一次极短的测试请求…';let x=await api('/api/model-test',{method:'POST',body:JSON.stringify({model})});$('setupmsg').innerHTML=x.ok?'<span class="ok">模型可用：'+x.model+'；'+(x.streaming||'')+'；输入 '+x.input_tokens+' / 输出 '+x.output_tokens+' token。 '+(x.usage_available===false?'网关未返回 usage。':'')+'</span>':'<span class="error">模型测试失败：'+x.message+'</span>';loadModelStatus()}catch(e){$('setupmsg').innerHTML='<span class="error">'+e.message+'</span>'}}
async function loadDocs(){try{let x=await api('/api/documents');$('docs').innerHTML=x.map(d=>`<div class="card">${d.name}<br><span class="muted">${d.chunks} chunks</span></div>`).join('')||'尚无材料。'}catch{}}
async function addDoc(){try{let d=await api('/api/document',{method:'POST',body:JSON.stringify({path:$('docpath').value})});$('docpath').value='';loadDocs();$('setupmsg').textContent=`已索引 ${d.name}（${d.chunks} chunks）`}catch(e){$('setupmsg').innerHTML='<span class="error">'+e.message+'</span>'}}
async function bg(){try{let x=await api('/api/bg',{method:'POST',body:JSON.stringify({codebook:$('codebook').value,folder:$('bgfolder').value})});renderStatus(x.status);$('bgstatus').textContent=`已固定 Codebook 与 ${x.sources} 个 BG 文件。`;loadDocs()}catch(e){$('bgstatus').innerHTML='<span class="error">'+e.message+'</span>'}}
async function clearBg(){try{renderStatus(await api('/api/bg',{method:'DELETE'}));$('bgstatus').textContent='已退出 BG 模式。'}catch(e){$('bgstatus').textContent=e.message}}
const compareOptions=[['claude-haiku-5.5','Claude Haiku 5.5'],['claude-opus-4','Claude Opus 4'],['gemini-3.5-flash-lite','Gemini 3.5 Flash-Lite'],['gemini-2.5-pro','Gemini 2.5 Pro'],['gpt-6-luna-2026-09-22','GPT-6 Luna'],['gpt-5.5','GPT-5.5']];
function renderCompareSlots(){let host=$('comparemodels');host.innerHTML=compareSlots.map((slot,index)=>{let options='<option value="">选择模型…</option>'+compareOptions.map(([value,label])=>'<option value="'+value+'" '+(slot.value===value?'selected':'')+'>'+label+'</option>').join('')+'<option value="__custom__" '+(slot.value==='__custom__'?'selected':'')+'>其他：手动输入 Model ID…</option>';return '<div class="field"><label>对比模型 '+(index+1)+'</label><div class="row"><select id="cmpsel'+index+'" onchange="changeCompareModel('+index+')">'+options+'</select>'+(index>0?'<button class="ghost" onclick="removeCompareModel('+index+')">×</button>':'')+'</div>'+(slot.value==='__custom__'?'<input id="cmpcustom'+index+'" value="'+esc(slot.custom||'')+'" placeholder="输入准确的 Bosch Farm Model ID" oninput="compareSlots['+index+'].custom=this.value">':'')+'</div>'}).join('');let add=$('addcompare');add.disabled=compareSlots.length>=4;add.textContent=compareSlots.length>=4?'最多 4 个模型':'＋ 添加对比模型';if(compareSlots.length>=4)$('comparestatus').textContent='已达到最多 4 个对比模型。'}
function changeCompareModel(index){let select=$('cmpsel'+index);compareSlots[index].value=select.value;if(select.value!=='__custom__')compareSlots[index].custom='';renderCompareSlots();if(select.value==='__custom__')setTimeout(()=>$('cmpcustom'+index).focus(),0)}
function addCompareModel(){if(compareSlots.length>=4){$('comparestatus').textContent='最多只能同时对比 4 个模型。';return}compareSlots.push({value:'',custom:''});renderCompareSlots();$('cmpsel'+(compareSlots.length-1)).focus()}
function removeCompareModel(index){compareSlots.splice(index,1);renderCompareSlots();$('comparestatus').textContent=''}
function selectedCompareModels(){return compareSlots.map((slot,index)=>slot.value==='__custom__'?$('cmpcustom'+index).value.trim():slot.value).filter(Boolean)}
async function compareModels(){if(busy)return;let q=$('question').value.trim()||lastQuestion;if(!q){$('comparestatus').innerHTML='<span class="error">先在下方输入问题，或先发送一次问题。</span>';return}let models=selectedCompareModels();if(models.length<2||models.length>4||new Set(models).size!==models.length){$('comparestatus').innerHTML='<span class="error">请选择 2–4 个不同模型；“其他”中输入准确的 Bosch Farm Model ID。</span>';return}busy=true;lastQuestion=q;$('comparestatus').textContent='正在按顺序请求 '+models.length+' 个模型…';let wait=message('正在进行多模型对比：'+models.join(' · '));try{let x=await api('/api/compare',{method:'POST',body:JSON.stringify({question:q,models})});wait.remove();let box=document.createElement('section');box.className='comparison';box.innerHTML='<div class="message assistant"><b>多模型对比</b><br>同一问题：'+esc(q)+'<br><span class="muted">相同证据：'+x.sources.map(esc).join(' · ')+'</span></div><div class="comparison-grid"></div>';let grid=box.querySelector('.comparison-grid');for(let r of x.results){let card=document.createElement('article');card.className='card';if(!r.ok){card.innerHTML='<b>'+esc(r.requested_model)+'</b><p class="error">请求失败</p><div class="muted">'+esc(r.error||'未知错误')+'</div>';grid.append(card);continue}let u=r.usage||{};let cost=u.cost_usd===null||u.cost_usd===undefined?'未配置价格':'$'+Number(u.cost_usd).toFixed(6);card.innerHTML='<b>'+esc(r.model_response)+'</b>'+(r.model_response!==r.requested_model?'<div class="muted">请求：'+esc(r.requested_model)+'</div>':'')+'<div class="muted ok">成功 · Token '+(u.input||0)+' / '+(u.output||0)+' · '+cost+'</div><hr><div class="answer"></div>'+(r.notices?.length?'<div class="muted">'+r.notices.map(esc).join('<br>')+'</div>':'');card.querySelector('.answer').textContent=r.answer;grid.append(card)}$('chat').append(box);$('comparestatus').innerHTML='<span class="ok">对比完成；结果仅显示在当前页面，不写入普通会话。</span>'}catch(e){wait.textContent='多模型对比错误：'+e.message;wait.classList.add('error');$('comparestatus').innerHTML='<span class="error">'+esc(e.message)+'</span>'}finally{busy=false;$('chat').scrollTop=1e9}}
async function chat(){if(busy||!$('question').value.trim())return;busy=true;let q=$('question').value;lastQuestion=q;$('question').value='';message(q,'user');let wait=message('正在向 Bosch Farm 请求…');try{let x=await api('/api/chat',{method:'POST',body:JSON.stringify({question:q})});wait.remove();message(x.answer);if(x.reasoning){let d=document.createElement('details');d.className='reason';d.innerHTML='<summary>模型推理（接口返回）</summary><pre></pre>';d.querySelector('pre').textContent=x.reasoning;$('chat').append(d)}if(x.notices?.length)message(x.notices.join('\n'),'assistant');$('sources').innerHTML=x.sources.map(s=>`<div class="card"><b>${s.label}</b><br>${s.visual?'<span class="chip">视觉证据已附带</span>':''}</div>`).join('')||'无可用来源';$('changes').innerHTML=x.changes?.length?x.changes.map(c=>`<div class="card"><b>${c.path}</b><br>${c.reason}<pre class="diff">${esc(c.diff)}</pre></div>`).join('')+'<button onclick="apply()">应用修改</button>':'无';$('analysisexport').innerHTML=x.can_export_bg?'<button class="ghost" onclick="exportBgAnalysis()">导出本次 BG 分析</button>':'仅在 Baugruppe 分析完成后可导出。';renderUsageDetail(x.turn_usage,x.model_response);renderStatus(x.usage)}catch(e){wait.textContent='错误：'+e.message;wait.classList.add('error')}finally{busy=false;$('chat').scrollTop=1e9}}
async function exportSession(){try{let x=await api('/api/export/session',{method:'POST'});$('sessionexport').innerHTML='<span class="ok">已导出：'+esc(x.path)+'</span>'}catch(e){$('sessionexport').innerHTML='<span class="error">'+esc(e.message)+'</span>'}}
async function exportBgAnalysis(){try{let x=await api('/api/export/bg-analysis',{method:'POST'});$('analysisexport').innerHTML='<span class="ok">已导出：'+esc(x.path)+'</span>'}catch(e){$('analysisexport').innerHTML='<span class="error">'+esc(e.message)+'</span>'}}
function esc(s){let e=document.createElement('div');e.textContent=s;return e.innerHTML}async function apply(){try{let x=await api('/api/apply',{method:'POST'});$('changes').innerHTML='<span class="ok">已应用 '+x.applied+' 个修改。</span>';message('已写入 '+x.applied+' 个经确认的文件修改。')}catch(e){$('changes').innerHTML='<span class="error">'+e.message+'</span>'}}
</script></body></html>'''


if __name__ == "__main__":
    print("Bosch Local Workbench: http://127.0.0.1:8765")
    uvicorn.run(app, host="127.0.0.1", port=8765)
