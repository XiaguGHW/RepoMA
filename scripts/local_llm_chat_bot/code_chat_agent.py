"""Low-context, local-first code chat for Bosch Model Farm.

Keep this file beside llm_connector_with_prompt_caching.py from RepoMA's
local_llm_chat_bot directory.  All indexes and conversation data live in the
directory supplied with --state-dir; nothing is written to the code project
until the user confirms a displayed change.
"""
import argparse
import difflib
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args, **_kwargs):
        pass


CODE_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".cpp", ".h", ".cs", ".go", ".rs", ".rb", ".php", ".sql", ".sh", ".ps1", ".html", ".css", ".json", ".yaml", ".yml", ".toml", ".ini", ".md"}
IGNORED_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache", ".pytest_cache", "dist", "build", ".next"}
MAX_FILE_BYTES = 1_000_000
MAX_SNIPPETS = 6
MAX_SNIPPET_CHARS = 4_000
HISTORY_MESSAGES_PER_REQUEST = 4

SYSTEM = """You are a careful local workspace and document assistant. You never have direct filesystem access.
The local program gives you code excerpts, locally extracted document excerpts, and, when necessary, current full files.
Return ONLY a JSON object with these fields:
{
  "answer": "concise Chinese explanation for the user (normally <= 1200 Chinese characters; complete the JSON even if you must shorten)",
  "read_files": ["relative/path"],
  "changes": [{"path": "relative/path", "content": "complete new UTF-8 file content", "reason": "brief reason"}],
  "memory_action": {"operation": "none|add|edit|delete", "id": "memory id or empty", "content": "new memory text or empty"}
}
Rules:
- Paths must be relative to the supplied workspace. Never use .. or an absolute path.
- For a modification, first request the complete current target file in read_files unless it was supplied in this message.
- Do not put a change in changes until you have the complete current content for that file.
- A new file may be created directly if its parent path is clear.
- Keep read_files focused (at most 4). Do not request an entire repository.
- Use supplied document excerpts as evidence when answering document questions. Cite their filename/page or sheet in the answer when useful.
- Do not propose a code change merely because the user asks a document question.
- If evidence is insufficient, explain what is needed and leave changes empty.
- Set memory_action only when the user explicitly asks you to remember, update, or delete a long-term memory. Never infer a memory action from ordinary discussion.
- For add use the concise fact/preference in content. For edit/delete, use an exact memory id shown in the supplied long-term memory when available; otherwise use operation none and ask the user to use /memory.
- Never claim a memory action was completed: the local program requires explicit confirmation.
- Do not use Markdown fences around the JSON.
- For ordinary explanations, be structured but concise. Never let a long explanation prevent a complete valid JSON object.
- Exception — when the supplied prompt contains BG CLASSIFICATION MODE, give a
  detailed, evidence-led assessment. It may exceed the normal length limit.
  Use these exact sections: Empfehlung; Entscheidungsweg nach Codebook;
  Belege (file/page/sheet/row); Abgrenzung zu Alternativen; Unsicherheit.
  Do not invent evidence. Separate an observed fact from an inference.
- Write for a narrow plain terminal, not for Markdown rendering. Use this default shape:
  结论：one short sentence
  1) Short heading — one or two short lines
  2) Short heading — one or two short lines
  下一步：only when the user needs an action
- Prefer 3–5 numbered sections. Avoid Markdown tables, long paragraphs, deep nested lists, and more than about 10 visible lines unless the user explicitly asks for a detailed answer.
- For a script-structure explanation, first give only the top-level modules and their roles. Offer to expand a specific numbered module instead of explaining every function at once.
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)[:80] or "session"


def tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z_][A-Za-z0-9_]{1,}|[\u4e00-\u9fff]{2,}|\d{2,}", text.lower())


class PricingCatalog:
    def __init__(self, path: Path | None):
        self.path = path
        self.entries = []
        self.error = None
        if not path:
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.entries = data.get("entries", [])
        except (OSError, json.JSONDecodeError) as exc:
            self.error = str(exc)

    def price_for(self, model: str):
        name = model.lower()
        candidates = []
        for entry in self.entries:
            if "input_usd_per_million" not in entry or "output_usd_per_million" not in entry:
                continue
            for alias in entry.get("match", []):
                if name.startswith(str(alias).lower()):
                    candidates.append((len(str(alias)), entry))
        if not candidates:
            return None
        entry = max(candidates, key=lambda item: item[0])[1]
        input_price = float(entry["input_usd_per_million"])
        output_price = float(entry["output_usd_per_million"])
        ends = entry.get("promotion_ends")
        if ends and datetime.now(timezone.utc).date().isoformat() > ends:
            input_price = float(entry.get("standard_input_usd_per_million", input_price))
            output_price = float(entry.get("standard_output_usd_per_million", output_price))
        return {"name": entry.get("display_name", model), "input_price": input_price, "output_price": output_price}

    def estimate(self, model: str, input_tokens: int, output_tokens: int):
        price = self.price_for(model)
        if not price:
            return None
        return {
            **price,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": input_tokens * price["input_price"] / 1_000_000 + output_tokens * price["output_price"] / 1_000_000,
        }


def format_cost(cost: float) -> str:
    return f"${cost:.6f}"


class ProjectState:
    def __init__(self, state_dir: Path, workspace: Path, session: str):
        self.workspace = workspace.expanduser().resolve()
        self.key = hashlib.sha256(str(self.workspace).encode()).hexdigest()[:16]
        self.root = state_dir.expanduser().resolve() / "projects" / self.key / safe_name(session)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "state.json"
        self.memory_path = self.root.parent / "memory.json"
        self.data = self._load()
        self.memory = self._load_memory()

    def _load(self):
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if data.get("workspace") == str(self.workspace):
                    usage = data.setdefault("usage", {})
                    usage.setdefault("requests", 0)
                    usage.setdefault("input", 0)
                    usage.setdefault("output", 0)
                    usage.setdefault("estimated_cost_usd", 0.0)
                    usage.setdefault("unpriced_requests", 0)
                    return data
            except (OSError, json.JSONDecodeError):
                pass
        return {"workspace": str(self.workspace), "session_id": uuid.uuid4().hex,
                "files": {}, "history": [], "summary": "", "usage": {"requests": 0, "input": 0, "output": 0, "estimated_cost_usd": 0.0, "unpriced_requests": 0}}

    def save(self):
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_memory(self):
        if self.memory_path.exists():
            try:
                data = json.loads(self.memory_path.read_text(encoding="utf-8"))
                if isinstance(data.get("items"), list):
                    return data
            except (OSError, json.JSONDecodeError):
                pass
        return {"version": 1, "items": []}

    def save_memory(self):
        self.memory_path.write_text(json.dumps(self.memory, ensure_ascii=False, indent=2), encoding="utf-8")

    def remember(self, content: str):
        content = content.strip()
        if not content:
            raise ValueError("Memory content is empty.")
        item = {
            "id": uuid.uuid4().hex[:8],
            "content": content,
            "source": "user-confirmed",
            "created_at": now(),
            "updated_at": now(),
        }
        self.memory["items"].append(item)
        self.save_memory()
        return item

    def list_memory(self):
        return self.memory["items"]

    def find_memory(self, item_id: str):
        return next((item for item in self.memory["items"] if item["id"] == item_id), None)

    def delete_memory(self, item_id: str):
        before = len(self.memory["items"])
        self.memory["items"] = [item for item in self.memory["items"] if item["id"] != item_id]
        if len(self.memory["items"]) == before:
            return False
        self.save_memory()
        return True

    def edit_memory(self, item_id: str, content: str):
        item = self.find_memory(item_id)
        if not item:
            return None
        item["content"] = content.strip()
        item["updated_at"] = now()
        self.save_memory()
        return item

    def search_memory(self, question: str, limit: int = 5):
        query_words = set(tokens(question))
        query_chars = set(re.findall(r"[\u4e00-\u9fff]", question.lower()))
        scored = []
        for item in self.memory["items"]:
            content = item["content"].lower()
            word_score = sum(1 for word in query_words if word in content)
            char_score = min(8, len(query_chars & set(re.findall(r"[\u4e00-\u9fff]", content))))
            score = word_score * 10 + char_score
            if score:
                scored.append((score, item))
        scored.sort(key=lambda pair: (-pair[0], pair[1]["updated_at"]))
        return [item for _, item in scored[:limit]]

    def relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.workspace).as_posix()

    def resolve_relative(self, value: str) -> Path:
        candidate = (self.workspace / value).resolve()
        try:
            candidate.relative_to(self.workspace)
        except ValueError as exc:
            raise ValueError("Path is outside the workspace") from exc
        return candidate

    def scan(self):
        files = {}
        for root, dirs, names in os.walk(self.workspace):
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
            for name in names:
                path = Path(root) / name
                if path.suffix.lower() not in CODE_EXTENSIONS:
                    continue
                try:
                    raw = path.read_bytes()
                except OSError:
                    continue
                if len(raw) > MAX_FILE_BYTES or b"\x00" in raw:
                    continue
                text = raw.decode("utf-8", errors="replace")
                rel = self.relative(path)
                files[rel] = {"sha256": sha256(raw), "bytes": len(raw), "symbols": symbols(text), "mtime_ns": path.stat().st_mtime_ns}
        self.data["files"] = files
        self.data["last_scan"] = now()
        self.save()
        return len(files)

    def refresh_file(self, relative: str):
        path = self.resolve_relative(relative)
        if not path.exists() or not path.is_file():
            self.data["files"].pop(relative, None)
            self.save()
            return
        raw = path.read_bytes()
        if len(raw) <= MAX_FILE_BYTES and b"\x00" not in raw:
            text = raw.decode("utf-8", errors="replace")
            self.data["files"][relative] = {"sha256": sha256(raw), "bytes": len(raw), "symbols": symbols(text), "mtime_ns": path.stat().st_mtime_ns}
            self.save()

    def search(self, question: str):
        words = set(tokens(question))
        scored = []
        for relative, meta in self.data["files"].items():
            haystack = (relative + " " + " ".join(meta.get("symbols", []))).lower()
            score = sum(1 for word in words if word in haystack)
            if score:
                scored.append((score, relative))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [relative for _, relative in scored[:MAX_SNIPPETS]]

    def add_turn(self, role: str, content: str):
        self.data["history"].append({"role": role, "content": content, "time": now()})
        self.data["history"] = self.data["history"][-8:]
        self.save()

    def note_usage(self, usage, pricing: PricingCatalog, model: str):
        usage = usage if isinstance(usage, dict) else {}
        input_tokens = int(usage.get("prompt_tokens", usage.get("input_tokens", usage.get("promptTokenCount", usage.get("inputTokenCount", 0)))) or 0)
        output_tokens = int(usage.get("completion_tokens", usage.get("output_tokens", usage.get("candidatesTokenCount", usage.get("outputTokenCount", 0)))) or 0)
        total = input_tokens + output_tokens
        if not total:
            return None
        aggregate = self.data["usage"]
        aggregate["requests"] += 1
        aggregate["input"] += input_tokens
        aggregate["output"] += output_tokens
        estimate = pricing.estimate(model, input_tokens, output_tokens)
        if estimate:
            aggregate["estimated_cost_usd"] += estimate["cost_usd"]
        else:
            aggregate["unpriced_requests"] += 1
        self.save()
        return estimate


def symbols(text: str) -> list[str]:
    found = re.findall(r"(?m)^\s*(?:def|class|function|func|interface|type|export\s+(?:class|function|const))\s+([A-Za-z_][\w]*)", text)
    return found[:100]


def excerpt(state: ProjectState, relative: str, question: str) -> str:
    path = state.resolve_relative(relative)
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    terms = set(tokens(question))
    hits = [i for i, line in enumerate(lines) if any(term in line.lower() for term in terms)]
    if not hits:
        hits = [0]
    blocks, seen = [], set()
    for hit in hits[:3]:
        start, end = max(0, hit - 12), min(len(lines), hit + 30)
        if (start, end) in seen:
            continue
        seen.add((start, end))
        blocks.append("\n".join(f"{number + 1}: {lines[number]}" for number in range(start, end)))
    body = "\n...\n".join(blocks)
    return body[:MAX_SNIPPET_CHARS]


def parse_json(answer: str) -> dict:
    answer = answer.strip()
    if answer.startswith("```"):
        answer = re.sub(r"^```(?:json)?\s*|\s*```$", "", answer, flags=re.I)
    start, end = answer.find("{"), answer.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Model did not return a JSON action")
    data = json.loads(answer[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("Model action must be an object")
    data.setdefault("answer", "")
    data.setdefault("read_files", [])
    data.setdefault("changes", [])
    data.setdefault("memory_action", {"operation": "none", "id": "", "content": ""})
    return data


def streamed_answer_handler():
    """Reveal only the JSON answer field while retaining the full action internally."""
    raw, state = [], {"started": False, "done": False, "cursor": 0, "escape": False, "unicode": "", "answer_chars": []}

    def emit_char(char: str):
        state["answer_chars"].append(char)
        print(char, end="", flush=True)

    def handler(kind, text):
        if kind == "notice":
            print(f"\n[stream] {text}")
            return
        if kind != "content" or not text:
            return
        raw.append(text)
        joined = "".join(raw)
        if not state["started"]:
            match = re.search(r'"answer"\s*:\s*"', joined)
            if not match:
                return
            state["started"] = True
            state["cursor"] = match.end()
            print("assistant> ", end="", flush=True)
        while state["cursor"] < len(joined) and not state["done"]:
            char = joined[state["cursor"]]
            state["cursor"] += 1
            if state["unicode"]:
                state["unicode"] += char
                if len(state["unicode"]) == 4:
                    try:
                        emit_char(chr(int(state["unicode"], 16)))
                    except ValueError:
                        emit_char("\\u" + state["unicode"])
                    state["unicode"] = ""
                    state["escape"] = False
                continue
            if state["escape"]:
                if char == "u":
                    state["unicode"] = ""
                    continue
                emit_char({"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\"}.get(char, char))
                state["escape"] = False
                continue
            if char == "\\":
                state["escape"] = True
            elif char == '"':
                state["done"] = True
            else:
                emit_char(char)

    return handler, state


def ensure_relative(path: str) -> str:
    item = Path(path)
    if item.is_absolute() or ".." in item.parts or not path.strip():
        raise ValueError(f"Unsafe path from model: {path!r}")
    return item.as_posix()


def prompt_for(state: ProjectState, question: str, snippets: dict[str, str], full_files: dict[str, str] | None = None,
               document_snippets: list[dict] | None = None, bg_context: dict | None = None):
    recent = "\n".join(f"{turn['role']}: {turn['content']}" for turn in state.data["history"][-HISTORY_MESSAGES_PER_REQUEST:]) or "(new conversation)"
    memories = state.search_memory(question)
    memory_text = "\n".join(f"- [{item['id']}] {item['content']}" for item in memories) or "(No relevant confirmed long-term memory.)"
    indexed = "\n".join(f"- {p}: {', '.join(m.get('symbols', [])[:12])}" for p, m in list(state.data["files"].items())[:250])
    shown = "\n\n".join(f"--- EXCERPT {path} ---\n{text}" for path, text in snippets.items()) or "(No relevant excerpt found.)"
    complete = "\n\n".join(f"--- COMPLETE FILE {path} ---\n{text}" for path, text in (full_files or {}).items()) or "(No complete file was requested yet.)"
    document_text = "\n\n".join(
        f"--- DOCUMENT [{item['id']}] {item['label']} ---\n{item['text']}"
        for item in (document_snippets or [])
    ) or "(No relevant locally extracted document excerpt.)"
    bg_instruction = ""
    if bg_context:
        bg_instruction = f"""
BG CLASSIFICATION MODE (active):
- Codebook: {bg_context.get('codebook_name', 'unknown')}
- Baugruppe folder: {bg_context.get('folder', 'unknown')}
- Give the full detailed classification format required by the system prompt.
- Treat the Codebook as the rule source. Cite evidence labels exactly as supplied.
- A source marked visual/scanned may require visual inspection; do not infer text that was not supplied.
"""
    return f"""Workspace: {state.workspace}
Project summary: {state.data['summary'] or '(none)'}
Recent conversation:\n{recent}

Relevant confirmed long-term memory (local, user-confirmed):\n{memory_text}

Indexed files and symbols (local metadata only):\n{indexed}

Relevant code excerpts:\n{shown}

Relevant locally extracted document excerpts:\n{document_text}

Complete current files supplied in this turn:\n{complete}

User request: {question}
{bg_instruction}
"""


def prepare_memory_action(state: ProjectState, action: dict):
    if not isinstance(action, dict):
        return None
    operation = str(action.get("operation", "none")).lower()
    item_id = str(action.get("id", "")).strip()
    content = str(action.get("content", "")).strip()
    if operation == "add" and content:
        return {"operation": "add", "content": content}
    if operation in {"edit", "delete"} and item_id:
        item = state.find_memory(item_id)
        if not item:
            return None
        if operation == "edit" and not content:
            return None
        return {"operation": operation, "id": item_id, "content": content, "before": item["content"]}
    return None


def apply_memory_action(state: ProjectState, pending: dict):
    if pending["operation"] == "add":
        item = state.remember(pending["content"])
        return f"Saved local long-term memory: [{item['id']}]"
    if pending["operation"] == "edit":
        item = state.edit_memory(pending["id"], pending["content"])
        if not item:
            raise RuntimeError("Memory no longer exists.")
        return f"Updated local long-term memory: [{item['id']}]"
    if pending["operation"] == "delete":
        if not state.delete_memory(pending["id"]):
            raise RuntimeError("Memory no longer exists.")
        return f"Deleted local long-term memory: [{pending['id']}]"
    raise RuntimeError("Unsupported memory operation.")


def show_changes(state: ProjectState, changes: list[dict]):
    prepared = []
    for change in changes:
        if not isinstance(change, dict) or not isinstance(change.get("path"), str) or not isinstance(change.get("content"), str):
            raise ValueError("Each change needs path and complete content")
        relative = ensure_relative(change["path"])
        path = state.resolve_relative(relative)
        old_bytes = path.read_bytes() if path.exists() else b""
        old = old_bytes.decode("utf-8", errors="replace")
        diff = "\n".join(difflib.unified_diff(old.splitlines(), change["content"].splitlines(), fromfile=f"a/{relative}", tofile=f"b/{relative}", lineterm=""))
        prepared.append({"path": relative, "content": change["content"], "reason": str(change.get("reason", "")), "before": sha256(old_bytes) if path.exists() else None, "diff": diff})
    for item in prepared:
        print(f"\n[{item['path']}] {item['reason']}")
        print(item["diff"] or "(no textual change)")
    return prepared


def apply_changes(state: ProjectState, pending: list[dict]):
    for item in pending:
        path = state.resolve_relative(item["path"])
        current = sha256(path.read_bytes()) if path.exists() else None
        if current != item["before"]:
            raise RuntimeError(f"{item['path']} changed after the diff was shown; request it again.")
    for item in pending:
        path = state.resolve_relative(item["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(item["content"], encoding="utf-8", newline="")
        state.refresh_file(item["path"])
    print(f"Applied {len(pending)} file change(s).")


def main():
    parser = argparse.ArgumentParser(description="Local-first code chat for Bosch Farm")
    parser.add_argument("--workspace", required=True, help="Existing local code directory")
    parser.add_argument("--state-dir", required=True, help="Separate directory for indexes and sessions")
    parser.add_argument("--session", default="default")
    parser.add_argument("--model", default=os.getenv("BOSCH_CHAT_MODEL", "gpt-5.5"))
    parser.add_argument("--env-file", help="Existing .env containing Bosch Farm credentials")
    parser.add_argument("--pricing-file", help="JSON price table; defaults to model_pricing.json beside this script")
    args = parser.parse_args()
    workspace = Path(args.workspace)
    if not workspace.is_dir():
        raise SystemExit(f"Workspace does not exist: {workspace}")
    load_dotenv(args.env_file or (Path(__file__).resolve().parent / ".env"))
    from llm_connector_with_prompt_caching import LLMConnector
    from local_document_library import LocalDocumentLibrary
    key = os.getenv("BOSCH_FARM_SUBSCRIPTION_KEY") or os.getenv("BOSCH_FARM_API_KEY")
    if not key:
        raise SystemExit("Missing BOSCH_FARM_SUBSCRIPTION_KEY in .env or environment.")
    state = ProjectState(Path(args.state_dir), workspace, args.session)
    documents = LocalDocumentLibrary(state.root.parent / "documents.json")
    pricing_path = Path(args.pricing_file) if args.pricing_file else Path(__file__).resolve().parent / "model_pricing.json"
    pricing = PricingCatalog(pricing_path)
    count = state.scan()
    llm = LLMConnector(args.model, key, session_id=state.data["session_id"])
    pending = []
    pending_memory = None
    print(f"Code Chat — model={args.model}; indexed {count} files. State: {state.root}")
    if pricing.error:
        print(f"Pricing disabled: could not load {pricing_path}: {pricing.error}")
    elif not pricing.entries:
        print(f"Pricing disabled: no entries in {pricing_path}")
    print("Ask in Chinese. Commands: /file PATH | /files | /bg CODEBOOK_PATH | BAUGRUPPE_FOLDER | /bg clear | /model ID | /scan | /status | /context | /remember TEXT | /memory | /cancel | 确认执行 | 确认记忆 | /quit")
    while True:
        try:
            question = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question:
            continue
        if question in {"/quit", "/exit"}:
            break
        if question == "/scan":
            print(f"Indexed {state.scan()} files.")
            continue
        if question == "/status":
            u = state.data["usage"]
            print(f"model={args.model}; files={len(state.data['files'])}; requests={u['requests']}; input={u['input']}; output={u['output']}; estimated={format_cost(float(u.get('estimated_cost_usd', 0.0)))}; unpriced={u.get('unpriced_requests', 0)}; documents={len(documents.list())}; pending={len(pending)}")
            continue
        if question == "/context":
            history = state.data["history"]
            carried = history[-HISTORY_MESSAGES_PER_REQUEST:]
            history_chars = sum(len(str(turn.get("content", ""))) for turn in carried)
            print(
                f"本次请求会带入：最近最多 {HISTORY_MESSAGES_PER_REQUEST} 条历史消息"
                f"（当前可带入 {len(carried)} 条，约 {history_chars} 个字符）。"
            )
            print(
                f"另外会带入：系统规则、当前问题、文件索引元数据；"
                f"按问题命中的最多 {MAX_SNIPPETS} 个代码片段（每个最多 {MAX_SNIPPET_CHARS} 字符）。"
            )
            print(
                "另外会按当前问题带入最多 5 条相关的、用户确认的长期记忆，"
                "以及最多 6 个本地文档片段。"
            )
            print(
                "若模型请求修改某个文件，下一次调用还会带入该目标文件全文。"
                "底层模型的最大上下文窗口未由 Model Farm 接口提供，因此脚本不能可靠显示该上限。"
            )
            continue
        if question == "/files":
            entries = documents.list()
            if not entries:
                print("No local documents indexed. Add one with /file PATH")
            else:
                print(f"Local documents ({len(entries)}):")
                for item in entries:
                    print(f"[{item['id']}] {item['name']} — {len(item.get('chunks', []))} chunks")
            continue
        if question == "/bg clear":
            state.data.pop("bg_context", None)
            state.save()
            print("Baugruppe classification mode cleared. Document indexes were kept locally.")
            continue
        if question.startswith("/bg "):
            specification = question[len("/bg "):].strip()
            if "|" not in specification:
                print("Usage: /bg \"CODEBOOK_PATH\" | \"BAUGRUPPE_FOLDER\"")
                continue
            codebook_value, folder_value = (part.strip().strip('"') for part in specification.split("|", 1))
            try:
                codebook = documents.add(codebook_value)
                sources, skipped = documents.add_folder(folder_value)
                state.data["bg_context"] = {
                    "codebook_id": codebook["id"],
                    "codebook_name": codebook["name"],
                    "source_ids": [item["id"] for item in sources],
                    "folder": str(Path(folder_value).expanduser().resolve()),
                    "created_at": now(),
                }
                state.save()
                print(f"BG mode active: Codebook [{codebook['id']}] + {len(sources)} source file(s).")
                if skipped:
                    print(f"Skipped {len(skipped)} file(s); use /files to inspect indexed sources.")
            except Exception as exc:
                print(f"BG mode not activated: {exc}")
            continue
        if question == "/file clear":
            print(f"Removed {documents.clear()} local document index(es). Original files were not changed.")
            continue
        if question.startswith("/file remove "):
            document_id = question[len("/file remove "):].strip()
            print("Document index removed." if documents.remove(document_id) else "Document ID not found.")
            continue
        if question.startswith("/file "):
            value = question[len("/file "):].strip()
            try:
                item = documents.add(value)
                print(f"Indexed locally: [{item['id']}] {item['name']} — {len(item['chunks'])} chunks.")
            except Exception as exc:
                print(f"Document not indexed: {exc}")
            continue
        if question == "/memory":
            items = state.list_memory()
            if not items:
                print("No long-term memory saved for this workspace.")
            else:
                print(f"Long-term memory ({len(items)} item(s), local only):")
                for item in items:
                    print(f"[{item['id']}] {item['content']}  ({item['updated_at'][:10]})")
            continue
        if question.startswith("/memory search "):
            query = question[len("/memory search "):].strip()
            results = state.search_memory(query, limit=20)
            if not results:
                print("No matching memory.")
            else:
                for item in results:
                    print(f"[{item['id']}] {item['content']}")
            continue
        if question.startswith("/memory delete "):
            item_id = question[len("/memory delete "):].strip()
            print("Memory deleted." if state.delete_memory(item_id) else "Memory ID not found.")
            continue
        if question.startswith("/memory edit "):
            parts = question.split(maxsplit=3)
            if len(parts) < 4 or not parts[3].strip():
                print("Usage: /memory edit ID new text")
            else:
                item = state.edit_memory(parts[2], parts[3])
                print(f"Memory updated: [{item['id']}]" if item else "Memory ID not found.")
            continue
        explicit_memory = None
        if question.startswith("/remember "):
            explicit_memory = question[len("/remember "):].strip()
        if explicit_memory is not None:
            try:
                item = state.remember(explicit_memory)
                print(f"Saved local long-term memory: [{item['id']}]")
            except ValueError as exc:
                print(exc)
            continue
        if question == "/cancel":
            pending = []
            pending_memory = None
            print("Pending code changes and memory actions discarded.")
            continue
        if question == "确认记忆":
            if not pending_memory:
                print("There is no pending memory action.")
                continue
            try:
                print(apply_memory_action(state, pending_memory))
                pending_memory = None
            except Exception as exc:
                print(f"Memory not changed: {exc}")
            continue
        if question == "确认执行":
            if not pending:
                print("There are no pending changes.")
                continue
            try:
                apply_changes(state, pending)
                pending = []
            except Exception as exc:
                print(f"Not applied: {exc}")
            continue
        if question.startswith("/model "):
            args.model = question[7:].strip()
            llm = LLMConnector(args.model, key, session_id=state.data["session_id"])
            print(f"Switched to {args.model}.")
            continue

        bg_context = state.data.get("bg_context")
        matches = state.search(question)
        snippets = {relative: excerpt(state, relative, question) for relative in matches}
        preferred_ids = None
        if bg_context:
            preferred_ids = [bg_context.get("codebook_id")] + list(bg_context.get("source_ids", []))
        document_snippets = documents.search(question, preferred_ids=preferred_ids, classification=bool(bg_context))
        visual_paths = documents.visual_paths(document_snippets, state.root / "visual_cache")
        turn_estimates = []
        stream_handler, streamed = streamed_answer_handler()
        raw = llm.ask_about_files(
            visual_paths, prompt_for(state, question, snippets, document_snippets=document_snippets, bg_context=bg_context), SYSTEM,
            {"maxOutputTokens": 4096, "temperature": 0},
            stream=True, event_handler=stream_handler,
        )
        if streamed["started"]:
            print()
        estimate = state.note_usage(llm.get_last_token_usage(), pricing, args.model)
        if estimate:
            turn_estimates.append(estimate)
        try:
            action = parse_json(raw)
            requested = [ensure_relative(p) for p in action["read_files"][:4] if isinstance(p, str)]
            full_files = {}
            for relative in requested:
                path = state.resolve_relative(relative)
                if path.is_file() and path.stat().st_size <= MAX_FILE_BYTES:
                    full_files[relative] = path.read_text(encoding="utf-8", errors="replace")
                    state.refresh_file(relative)
            # A request for current files is a planning step.  Ignore any
            # premature change returned with it and obtain a new action based
            # on the actual latest file content.
            if full_files:
                stream_handler, streamed = streamed_answer_handler()
                raw = llm.ask_about_files(
                    visual_paths, prompt_for(state, question, snippets, full_files, document_snippets, bg_context), SYSTEM,
                    {"maxOutputTokens": 3000, "temperature": 0},
                    stream=True, event_handler=stream_handler,
                )
                if streamed["started"]:
                    print()
                estimate = state.note_usage(llm.get_last_token_usage(), pricing, args.model)
                if estimate:
                    turn_estimates.append(estimate)
                action = parse_json(raw)
            if not streamed["started"]:
                print(f"assistant> {action['answer']}")
            if turn_estimates:
                turn_input = sum(item["input_tokens"] for item in turn_estimates)
                turn_output = sum(item["output_tokens"] for item in turn_estimates)
                turn_cost = sum(item["cost_usd"] for item in turn_estimates)
                print(f"usage> 本轮：输入 {turn_input} | 输出 {turn_output} | 估算 {format_cost(turn_cost)}（{turn_estimates[0]['name']}）")
            elif llm.get_last_token_usage():
                print("usage> 网关未返回可识别的 token 用量，未计算本轮费用。")
            memory_proposal = prepare_memory_action(state, action.get("memory_action", {}))
            if memory_proposal:
                pending_memory = memory_proposal
                if memory_proposal["operation"] == "add":
                    print(f"\nmemory> 将保存：{memory_proposal['content']}")
                elif memory_proposal["operation"] == "edit":
                    print(f"\nmemory> 将修改 [{memory_proposal['id']}]：\n- 原内容：{memory_proposal['before']}\n- 新内容：{memory_proposal['content']}")
                else:
                    print(f"\nmemory> 将删除 [{memory_proposal['id']}]：{memory_proposal['before']}")
                print("Type 确认记忆 to apply this memory action, or /cancel to discard it.")
            if action["changes"]:
                pending = show_changes(state, action["changes"])
                print("\nReview the diff. Type 确认执行 to write it, or /cancel to discard it.")
            state.add_turn("user", question)
            state.add_turn("assistant", action["answer"])
        except Exception as exc:
            # A gateway may cut a response before the final JSON quote/brace.
            # Do not echo the full raw JSON again after a streamed response.
            if streamed["started"]:
                state.add_turn("user", question)
                partial = "".join(streamed["answer_chars"]).strip()
                if partial:
                    state.add_turn("assistant", partial)
                print("assistant> 本轮回答未形成完整的操作 JSON，未执行文件或记忆操作。若内容在句中结束，请用“继续上一段”重试；已显示的文字不会被重复打印。")
            else:
                print(f"assistant> The model response was not applied: {exc}")


if __name__ == "__main__":
    main()

# Run this in the VS Code integrated Terminal (PowerShell):
# python code_chat_agent.py --workspace "C:\\Users\\XXXXX\\Documents\\Python_Projects\\bosch_chat\\bot_workspace" --state-dir "C:\\Users\\XXXXX\\Documents\\Python_Projects\\bosch_chat\\AI_Bot_State" --model gpt-6-luna-2026-09-22 --env-file "C:\\Users\\XXXXX\\Documents\\Python_Projects\\bosch_chat\\.env"
# Price table defaults to model_pricing.json beside this script; use --pricing-file to choose another local JSON file.
# State, indexes and conversation summaries are stored only under --state-dir.
