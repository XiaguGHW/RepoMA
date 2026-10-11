"""Low-context, local-first code chat for Bosch Model Farm.

Keep this file beside llm_connector_with_prompt_caching.py from RepoMA's
07_terminal_chat directory.  All indexes and conversation data live in the
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

SYSTEM = """You are a careful local code assistant. You never have direct filesystem access.
The local program gives you code excerpts and, when necessary, current full files.
Return ONLY a JSON object with these fields:
{
  "answer": "brief Chinese explanation for the user",
  "read_files": ["relative/path"],
  "changes": [{"path": "relative/path", "content": "complete new UTF-8 file content", "reason": "brief reason"}]
}
Rules:
- Paths must be relative to the supplied workspace. Never use .. or an absolute path.
- For a modification, first request the complete current target file in read_files unless it was supplied in this message.
- Do not put a change in changes until you have the complete current content for that file.
- A new file may be created directly if its parent path is clear.
- Keep read_files focused (at most 4). Do not request an entire repository.
- If evidence is insufficient, explain what is needed and leave changes empty.
- Do not use Markdown fences around the JSON.
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)[:80] or "session"


def tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z_][A-Za-z0-9_]{1,}|[\u4e00-\u9fff]{2,}|\d{2,}", text.lower())


class ProjectState:
    def __init__(self, state_dir: Path, workspace: Path, session: str):
        self.workspace = workspace.expanduser().resolve()
        self.key = hashlib.sha256(str(self.workspace).encode()).hexdigest()[:16]
        self.root = state_dir.expanduser().resolve() / "projects" / self.key / safe_name(session)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "state.json"
        self.data = self._load()

    def _load(self):
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if data.get("workspace") == str(self.workspace):
                    return data
            except (OSError, json.JSONDecodeError):
                pass
        return {"workspace": str(self.workspace), "session_id": uuid.uuid4().hex,
                "files": {}, "history": [], "summary": "", "usage": {"requests": 0, "input": 0, "output": 0}}

    def save(self):
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

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

    def note_usage(self, usage):
        self.data["usage"]["requests"] += 1
        if isinstance(usage, dict):
            self.data["usage"]["input"] += int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0)
            self.data["usage"]["output"] += int(usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0)
        self.save()


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
    return data


def ensure_relative(path: str) -> str:
    item = Path(path)
    if item.is_absolute() or ".." in item.parts or not path.strip():
        raise ValueError(f"Unsafe path from model: {path!r}")
    return item.as_posix()


def prompt_for(state: ProjectState, question: str, snippets: dict[str, str], full_files: dict[str, str] | None = None):
    recent = "\n".join(f"{turn['role']}: {turn['content']}" for turn in state.data["history"][-4:]) or "(new conversation)"
    indexed = "\n".join(f"- {p}: {', '.join(m.get('symbols', [])[:12])}" for p, m in list(state.data["files"].items())[:250])
    shown = "\n\n".join(f"--- EXCERPT {path} ---\n{text}" for path, text in snippets.items()) or "(No relevant excerpt found.)"
    complete = "\n\n".join(f"--- COMPLETE FILE {path} ---\n{text}" for path, text in (full_files or {}).items()) or "(No complete file was requested yet.)"
    return f"""Workspace: {state.workspace}
Project summary: {state.data['summary'] or '(none)'}
Recent conversation:\n{recent}

Indexed files and symbols (local metadata only):\n{indexed}

Relevant code excerpts:\n{shown}

Complete current files supplied in this turn:\n{complete}

User request: {question}
"""


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
    args = parser.parse_args()
    workspace = Path(args.workspace)
    if not workspace.is_dir():
        raise SystemExit(f"Workspace does not exist: {workspace}")
    load_dotenv(args.env_file or (Path(__file__).resolve().parent / ".env"))
    from llm_connector_with_prompt_caching import LLMConnector
    key = os.getenv("BOSCH_FARM_SUBSCRIPTION_KEY") or os.getenv("BOSCH_FARM_API_KEY")
    if not key:
        raise SystemExit("Missing BOSCH_FARM_SUBSCRIPTION_KEY in .env or environment.")
    state = ProjectState(Path(args.state_dir), workspace, args.session)
    count = state.scan()
    llm = LLMConnector(args.model, key, session_id=state.data["session_id"])
    pending = []
    print(f"Code Chat — model={args.model}; indexed {count} files. State: {state.root}")
    print("Ask in Chinese. Commands: /model ID | /scan | /status | /cancel | 确认执行 | /quit")
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
            print(f"model={args.model}; files={len(state.data['files'])}; requests={u['requests']}; input={u['input']}; output={u['output']}; pending={len(pending)}")
            continue
        if question == "/cancel":
            pending = []
            print("Pending changes discarded.")
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

        matches = state.search(question)
        snippets = {relative: excerpt(state, relative, question) for relative in matches}
        raw = llm.ask_about_files([], prompt_for(state, question, snippets), SYSTEM, {"maxOutputTokens": 1800, "temperature": 0})
        state.note_usage(llm.get_last_token_usage())
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
                raw = llm.ask_about_files([], prompt_for(state, question, snippets, full_files), SYSTEM, {"maxOutputTokens": 3000, "temperature": 0})
                state.note_usage(llm.get_last_token_usage())
                action = parse_json(raw)
            print(f"assistant> {action['answer']}")
            if action["changes"]:
                pending = show_changes(state, action["changes"])
                print("\nReview the diff. Type 确认执行 to write it, or /cancel to discard it.")
            state.add_turn("user", question)
            state.add_turn("assistant", action["answer"])
        except Exception as exc:
            print(f"assistant> The model response was not applied: {exc}\nRaw response:\n{raw}")


if __name__ == "__main__":
    main()

# Run this in the VS Code integrated Terminal (PowerShell). Replace paths,
# model ID and .env path for your computer:
# python code_chat_agent.py --workspace "D:\\Projects\\my_bot" --state-dir "D:\\AI_Bot_State" --model gpt-5.5 --env-file "C:\\path\\to\\.env"
# State, indexes and conversation summaries are stored only under --state-dir.
