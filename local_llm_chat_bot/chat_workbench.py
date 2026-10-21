"""Local browser workbench for the Bosch Farm code/document chat.

Run only on 127.0.0.1.  The browser is a local UI: paths, indexes, source
files, credentials and session data stay on the computer that starts it.
"""
from __future__ import annotations

import difflib
import json
import os
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn

from dotenv import load_dotenv
from code_chat_agent import (PricingCatalog, ProjectState, SYSTEM, ensure_relative,
                             excerpt, parse_json, prompt_for, sha256)
from local_document_library import LocalDocumentLibrary
from llm_connector_with_prompt_caching import LLMConnector


app = FastAPI(title="Bosch Local Workbench", docs_url=None, redoc_url=None)
LOCK = threading.Lock()
ACTIVE: dict[str, Any] = {}


def app_state_home() -> Path:
    return Path(__file__).resolve().parent / "AI_Bot_State"


def workbench_settings_path() -> Path:
    return app_state_home() / "workbench_settings.json"


def load_workbench_settings() -> dict[str, str]:
    try:
        data = json.loads(workbench_settings_path().read_text(encoding="utf-8"))
        return {
            "workspace": str(data.get("workspace", "")),
            "session": str(data.get("session", "default")) or "default",
        } if isinstance(data, dict) else {"workspace": "", "session": "default"}
    except (OSError, ValueError):
        return {"workspace": "", "session": "default"}


def save_workbench_settings(workspace: Path, session_name: str) -> None:
    app_state_home().mkdir(parents=True, exist_ok=True)
    workbench_settings_path().write_text(
        json.dumps({"workspace": str(workspace), "session": session_name}, ensure_ascii=False, indent=2),
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


class BGRequest(BaseModel):
    codebook: str
    folder: str


class ChatRequest(BaseModel):
    question: str


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
    estimate = state.note_usage(llm.get_last_token_usage(), data["pricing"], data["model"])
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
                "sources": evidence, "visuals": visuals, "changes": [],
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
        estimate = state.note_usage(llm.get_last_token_usage(), data["pricing"], data["model"])
        if estimate: estimates.append(estimate)
        action = parse_json(raw)
    changes = build_diff(state, action.get("changes", []))
    data["pending"] = changes
    state.add_turn("user", question); state.add_turn("assistant", action.get("answer", ""))
    return {"answer": action.get("answer", ""), "reasoning": "".join(reasoning), "notices": notices,
            "sources": evidence, "visuals": visuals, "changes": [{k: v for k, v in item.items() if k != "content"} for item in changes],
            "turn_cost": sum(item["cost_usd"] for item in estimates) if estimates else None,
            "usage": status_data(data)}


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
    save_workbench_settings(workspace, state.root.name)
    return status_data(ACTIVE)


@app.get("/api/status")
def status(): return status_data(session())


@app.get("/api/settings")
def settings():
    # Only the local path is returned. No source documents or credentials leave this computer.
    return load_workbench_settings()


@app.get("/api/sessions")
def sessions():
    state = session()["state"]
    return {"current": state.root.name, "sessions": available_sessions(state)}


@app.post("/api/model-test")
def model_test(request: ModelTestRequest):
    model = request.model.strip()
    if not model:
        raise HTTPException(400, "请输入 Bosch Farm 的准确 Model ID。")
    load_dotenv(Path(__file__).resolve().parent / ".env")
    key = os.getenv("BOSCH_FARM_SUBSCRIPTION_KEY") or os.getenv("BOSCH_FARM_API_KEY")
    if not key:
        raise HTTPException(400, "未找到 BOSCH_FARM_SUBSCRIPTION_KEY。")
    try:
        probe = LLMConnector(model, key, session_id=f"model_check_{os.urandom(6).hex()}")
        answer = probe.ask_about_files(
            [], "Reply with exactly OK.", "You are a connection test. Follow the user instruction exactly.",
            {"maxOutputTokens": 32, "temperature": 0}, stream=False,
        ).strip()
        if answer.startswith(("Error:", "HTTP error")):
            return {"ok": False, "model": model, "message": answer, "usage": probe.get_last_token_usage()}
        usage = probe.get_last_token_usage() or {}
        return {
            "ok": True, "model": probe.last_response_model or model, "answer": answer[:120],
            "input_tokens": usage.get("input_tokens", 0), "output_tokens": usage.get("output_tokens", 0),
            "message": "连接、回答和 token usage 均已验证。",
        }
    except Exception as exc:
        return {"ok": False, "model": model, "message": str(exc)}


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


@app.post("/api/chat")
def chat(request: ChatRequest):
    if not request.question.strip(): raise HTTPException(400, "请输入问题。")
    with LOCK: return call_model(session(), request.question.strip())


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
*{box-sizing:border-box}body{margin:0;background:#111827;color:#e5e7eb;font:14px Inter,Segoe UI,Arial,sans-serif}button,input,select{font:inherit}button{background:#2563eb;color:white;border:0;border-radius:7px;padding:8px 10px;cursor:pointer}button.ghost{background:#263244;color:#cbd5e1}.shell{height:100vh;display:grid;grid-template-columns:270px minmax(420px,1fr) 300px}.side{background:#172033;border-right:1px solid #334155;padding:16px;overflow:auto}.right{border-left:1px solid #334155;border-right:0}.main{display:flex;flex-direction:column;min-width:0}.brand{font-weight:700;font-size:16px;margin-bottom:16px}.muted{color:#94a3b8;font-size:12px}.field{margin:10px 0}.field label{display:block;font-size:12px;color:#a9b6c8;margin-bottom:5px}input{width:100%;background:#0f172a;border:1px solid #3b4960;border-radius:6px;padding:8px;color:#f8fafc}.row{display:flex;gap:7px}.row>*{min-width:0}.row input{flex:1}.chat{flex:1;overflow:auto;padding:24px max(32px,8%)}.message{max-width:920px;margin:0 auto 18px;padding:13px 15px;border-radius:10px;white-space:pre-wrap;line-height:1.55}.user{background:#1e3a5f;margin-left:auto;max-width:78%}.assistant{background:#1e293b}.reason{margin:8px auto 18px;max-width:920px;background:#171e2d;border:1px solid #334155;border-radius:8px;padding:9px}.reason summary{cursor:pointer;color:#b9c9e2}.reason pre{white-space:pre-wrap;font-size:12px;color:#aab7c8}.composer{border-top:1px solid #334155;padding:13px 8%;display:flex;gap:8px;background:#111827}.composer input{padding:12px}.composer button{padding:10px 17px}.card{border:1px solid #334155;border-radius:8px;padding:10px;margin:10px 0;background:#141d2d}.list{font-size:12px;line-height:1.5;word-break:break-word}.diff{white-space:pre-wrap;background:#0b1220;border-radius:6px;padding:8px;max-height:230px;overflow:auto;color:#d7e1ed}.ok{color:#86efac}.error{color:#fca5a5}.chip{display:inline-block;padding:3px 6px;border-radius:5px;background:#22314a;color:#bcd5ff;margin:2px;font-size:11px}
</style></head><body><div class="shell"><aside class="side"><div class="brand">Bosch Local Workbench</div><div class="muted">仅本机 127.0.0.1 · 缓存固定保存在程序目录 AI_Bot_State</div>
<div class="field"><label>代码工作区文件夹</label><div class="row"><input id="workspace" placeholder="C:\\...\\项目文件夹"><button class="ghost" onclick="pick('folder','workspace')">选择</button></div></div><div class="field"><label>模型</label>
<select id="model" onchange="toggleCustomModel()">
<option value="claude-haiku-5.5">Claude Haiku 5.5（推荐：日常、便宜）</option>
<option value="gemini-3.5-flash-lite">Gemini 3.5 Flash-Lite（最快、最省）</option>
<option value="gpt-6-luna-2026-09-22">GPT-6 Luna（轻量推理）</option>
<option value="__custom__">其他：手动输入 Model ID…</option>
</select>
<input id="custommodel" placeholder="粘贴准确的 Bosch Farm Model ID" style="display:none;margin-top:7px"></div><div class="row"><button onclick="setup()">打开工作区</button><button class="ghost" onclick="testModel()">测试模型</button></div><div id="setupmsg" class="muted"></div>
<div class="field"><label>聊天会话</label><div class="row"><select id="session"></select><button class="ghost" onclick="openSession()">切换</button><button class="ghost" onclick="newSession()">新建</button></div><div id="sessionmsg" class="muted"></div></div>
<hr><b>单一文件分析</b><div class="muted">选择一个 PDF / Excel / PNG，加入后可围绕该文件连续提问。</div><div class="field"><label>要分析的文件</label><div class="row"><input id="docpath" placeholder="PDF / Excel / PNG …"><button class="ghost" onclick="pick('file','docpath')">选择</button><button class="ghost" onclick="addDoc()">加入</button></div></div><div id="docs" class="list"></div>
<hr><b>Baugruppe 文件夹分析</b><div class="muted">选择 Codebook 和一个 BG 文件夹；程序读取其中全部受支持文件，用于分类及错误原因分析。</div><div class="field"><label>Codebook 文件</label><div class="row"><input id="codebook" placeholder="…Codebook.pdf"><button class="ghost" onclick="pick('file','codebook')">选择</button></div></div><div class="field"><label>BG 文件夹</label><div class="row"><input id="bgfolder" placeholder="选择一个 Baugruppe 文件夹"><button class="ghost" onclick="pick('folder','bgfolder')">选择</button></div></div><button class="ghost" onclick="bg()">开始文件夹分析</button> <button class="ghost" onclick="clearBg()">退出文件夹分析</button><div id="bgstatus" class="muted"></div></aside>
<main class="main"><div class="chat" id="chat"><div class="message assistant">选择工作区后即可聊天。代码修改会先显示 diff，只有点击“应用修改”才会写入本地文件。</div></div><div class="composer"><input id="question" placeholder="问代码，或根据 Codebook 判断 Baugruppe …" onkeydown="if(event.key==='Enter')chat()"><button onclick="chat()">发送</button></div></main>
<aside class="side right"><b>本轮状态</b><div id="status" class="card muted">尚未打开工作区</div><b>证据来源</b><div id="sources" class="card list">回答后会显示实际传给模型的来源。</div><b>待应用修改</b><div id="changes" class="list">无</div></aside></div>
<script>
const $=id=>document.getElementById(id);let busy=false;
async function restoreLastWorkspace(){
  try{
    let s=await api('/api/settings');
    if(!s.workspace)return;
    $('workspace').value=s.workspace;
    $('session').innerHTML='<option>'+ (s.session||'default') +'</option>';
    $('setupmsg').textContent='正在自动打开上次工作区…';
    await setup();
  }catch{
    $('setupmsg').textContent='无法自动打开上次工作区；请重新选择路径。';
  }
}
window.addEventListener('DOMContentLoaded',restoreLastWorkspace);
async function api(url,opt={}){let r=await fetch(url,{headers:{'Content-Type':'application/json'},...opt});let d=await r.json();if(!r.ok)throw Error(d.detail||'请求失败');return d}
async function pick(kind,target){try{$(target).value=(await api('/api/pick/'+kind)).path||''}catch(e){alert(e.message)}}
function message(text,kind='assistant'){let e=document.createElement('div');e.className='message '+kind;e.textContent=text;$('chat').append(e);$('chat').scrollTop=1e9;return e}
function renderStatus(s){$('status').innerHTML=`模型：<b>${s.model}</b><br>会话：${s.session_name||'default'}<br>代码：${s.code_files} 文件<br>材料：${s.documents} 个<br>请求：${s.requests}<br>Token：${s.input_tokens} / ${s.output_tokens}<br>估算：${s.cost}<br>${s.bg_context?'<span class="ok">BG 模式：'+s.bg_context.codebook_name+'</span>':'普通模式'}`}
function toggleCustomModel(){let custom=$('model').value==='__custom__';$('custommodel').style.display=custom?'block':'none';if(custom)$('custommodel').focus()}
function selectedModel(){let selected=$('model').value;return selected==='__custom__' ? $('custommodel').value.trim() : selected}
async function loadSessions(){try{let x=await api('/api/sessions');$('session').innerHTML=x.sessions.map(n=>`<option value="${esc(n)}" ${n===x.current?'selected':''}>${esc(n)}</option>`).join('');$('sessionmsg').textContent='聊天记录、BG 状态、代码索引和 token 统计按会话分开；已加入的材料索引按工作区共享。'}catch(e){$('sessionmsg').textContent=e.message}}
async function setup(){try{let model=selectedModel();if(!model)throw Error('请先输入 Bosch Farm 的准确 Model ID。');let s=await api('/api/setup',{method:'POST',body:JSON.stringify({workspace:$('workspace').value,state_dir:'',env_file:'',model:model,session:$('session').value.trim()||'default'})});renderStatus(s);$('setupmsg').textContent='已打开。';loadDocs();loadSessions()}catch(e){$('setupmsg').innerHTML='<span class="error">'+e.message+'</span>'}}
async function openSession(){if(!$('session').value)return;await setup()}
async function newSession(){let name=prompt('新会话名称，例如：BG_012 或 token_test');if(!name||!name.trim())return;$('session').innerHTML='<option>'+esc(name.trim())+'</option>';await setup()}
async function testModel(){try{let model=selectedModel();if(!model)throw Error('请先输入 Bosch Farm 的准确 Model ID。');$('setupmsg').textContent='正在发送一次极短的测试请求…';let x=await api('/api/model-test',{method:'POST',body:JSON.stringify({model})});$('setupmsg').innerHTML=x.ok?'<span class="ok">模型可用：'+x.model+'；输入 '+x.input_tokens+' / 输出 '+x.output_tokens+' token。 </span>':'<span class="error">模型测试失败：'+x.message+'</span>'}catch(e){$('setupmsg').innerHTML='<span class="error">'+e.message+'</span>'}}
async function loadDocs(){try{let x=await api('/api/documents');$('docs').innerHTML=x.map(d=>`<div class="card">${d.name}<br><span class="muted">${d.chunks} chunks</span></div>`).join('')||'尚无材料。'}catch{}}
async function addDoc(){try{let d=await api('/api/document',{method:'POST',body:JSON.stringify({path:$('docpath').value})});$('docpath').value='';loadDocs();$('setupmsg').textContent=`已索引 ${d.name}（${d.chunks} chunks）`}catch(e){$('setupmsg').innerHTML='<span class="error">'+e.message+'</span>'}}
async function bg(){try{let x=await api('/api/bg',{method:'POST',body:JSON.stringify({codebook:$('codebook').value,folder:$('bgfolder').value})});renderStatus(x.status);$('bgstatus').textContent=`已固定 Codebook 与 ${x.sources} 个 BG 文件。`;loadDocs()}catch(e){$('bgstatus').innerHTML='<span class="error">'+e.message+'</span>'}}
async function clearBg(){try{renderStatus(await api('/api/bg',{method:'DELETE'}));$('bgstatus').textContent='已退出 BG 模式。'}catch(e){$('bgstatus').textContent=e.message}}
async function chat(){if(busy||!$('question').value.trim())return;busy=true;let q=$('question').value;$('question').value='';message(q,'user');let wait=message('正在向 Bosch Farm 请求…');try{let x=await api('/api/chat',{method:'POST',body:JSON.stringify({question:q})});wait.remove();message(x.answer);if(x.reasoning){let d=document.createElement('details');d.className='reason';d.innerHTML='<summary>模型推理（接口返回）</summary><pre></pre>';d.querySelector('pre').textContent=x.reasoning;$('chat').append(d)}if(x.notices?.length)message(x.notices.join('\n'),'assistant');$('sources').innerHTML=x.sources.map(s=>`<div class="card"><b>${s.label}</b><br>${s.visual?'<span class="chip">视觉证据已附带</span>':''}</div>`).join('')||'无可用来源';$('changes').innerHTML=x.changes?.length?x.changes.map(c=>`<div class="card"><b>${c.path}</b><br>${c.reason}<pre class="diff">${esc(c.diff)}</pre></div>`).join('')+'<button onclick="apply()">应用修改</button>':'无';renderStatus(x.usage)}catch(e){wait.textContent='错误：'+e.message;wait.classList.add('error')}finally{busy=false;$('chat').scrollTop=1e9}}
function esc(s){let e=document.createElement('div');e.textContent=s;return e.innerHTML}async function apply(){try{let x=await api('/api/apply',{method:'POST'});$('changes').innerHTML='<span class="ok">已应用 '+x.applied+' 个修改。</span>';message('已写入 '+x.applied+' 个经确认的文件修改。')}catch(e){$('changes').innerHTML='<span class="error">'+e.message+'</span>'}}
</script></body></html>'''


if __name__ == "__main__":
    print("Bosch Local Workbench: http://127.0.0.1:8765")
    uvicorn.run(app, host="127.0.0.1", port=8765)
