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
import math
import os
import re
import stat
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypedDict
from release_safety import context_state_error, normalize_usage

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args, **_kwargs):
        pass


CODE_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".cpp", ".h", ".cs", ".go", ".rs", ".rb", ".php", ".sql", ".sh", ".ps1", ".html", ".css", ".json", ".yaml", ".yml", ".toml", ".ini", ".md"}
IGNORED_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache", ".pytest_cache", "dist", "build", ".next", "AI_Bot_State", ".bosch_chat", ".excel_chat", "visual_cache"}
MAX_FILE_BYTES = 1_000_000
MAX_SNIPPETS = 6
MAX_SNIPPET_CHARS = 4_000
HISTORY_MESSAGES_PER_REQUEST = 4

SYSTEM = """You are a careful local workspace and document assistant. You never have direct filesystem access.
The local program gives you code excerpts, locally extracted document excerpts, and, when necessary, current full files.
Return ONLY a JSON object with these fields:
{
  "answer": "concise explanation in the response language requested in the user prompt (normally <= 1200 Chinese characters or equivalent; complete the JSON even if you must shorten)",
  "read_files": ["relative/path"],
  "changes": [{"path": "relative/path", "content": "complete new UTF-8 file content", "reason": "brief reason"}],
  "memory_action": {"operation": "none|add|edit|delete", "id": "memory id or empty", "content": "new memory text or empty"},
  "classification": null
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
- Write the natural-language answer in the response language requested in the user prompt.
  Keep official Codebook category names, filenames, part numbers, source quotations,
  supplied table labels, and supplied technical evidence exactly as provided.
- Exception — when the supplied prompt contains BG CLASSIFICATION MODE, give a
  detailed, evidence-led assessment. It may exceed the normal length limit.
  Use concise equivalent sections in the requested response language: recommendation;
  Codebook decision path; evidence (file/page/sheet/row); alternatives; uncertainty.
  Do not invent evidence. Separate an observed fact from an inference.
- Write for a narrow plain terminal, not for Markdown rendering. Use this default shape in the requested language:
  Short conclusion: one sentence
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
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", value)[:80].strip(". ")
    return "session_" + name if name.upper().split(".")[0] in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1,10)], *[f"LPT{i}" for i in range(1,10)]} else (name or "session")


def write_json_atomically(path: Path, payload) -> None:
    """Persist local state without leaving a partial JSON file after a crash."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
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


def write_jsonl_atomically(path: Path, records: list[dict]) -> None:
    """Create a transcript archive as one complete replacement."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
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


def append_jsonl_durably(path: Path, record: dict) -> None:
    """Append one complete transcript line and request it be flushed to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        handle.flush()
        try:
            os.fsync(handle.fileno())
        except OSError:
            pass


def tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z_][A-Za-z0-9_]{1,}|[\u4e00-\u9fff]{2,}|\d{2,}", text.lower())


class PricingCatalog:
    def __init__(self, path: Path | None):
        self.path = path
        self.entries: list[dict[str, Any]] = []
        self.error: str | None = None
        if not path:
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.entries = data.get("entries", []) if isinstance(data, dict) else []
            if not isinstance(self.entries, list):
                self.entries = []
            self.entries = [e for e in self.entries if isinstance(e, dict)]
        except (OSError, json.JSONDecodeError) as exc:
            self.error = str(exc)

    def price_for(self, model: str):
        name = model.lower()
        candidates = []
        for entry in self.entries:
            if "input_usd_per_million" not in entry or "output_usd_per_million" not in entry:
                continue
            for alias in (entry.get("match") or []) if isinstance(entry.get("match"), list) else []:
                if name == str(alias).lower() or name.startswith(str(alias).lower() + "-") or name.startswith(str(alias).lower() + "@"):
                    candidates.append((len(str(alias)), entry))
        if not candidates:
            return None
        entry = max(candidates, key=lambda item: item[0])[1]
        try:
            if any(isinstance(entry[key], bool) for key in ("input_usd_per_million", "output_usd_per_million")):
                return None
            input_price = float(entry["input_usd_per_million"])
            output_price = float(entry["output_usd_per_million"])
            ends = entry.get("promotion_ends")
            if isinstance(ends, str) and datetime.now(timezone.utc).date().isoformat() > ends:
                input_price = float(entry.get("standard_input_usd_per_million", input_price))
                output_price = float(entry.get("standard_output_usd_per_million", output_price))
            if not all(math.isfinite(v) and v >= 0 for v in (input_price, output_price)):
                return None
        except (ValueError, TypeError, OverflowError):
            return None
        price = {"name": entry.get("display_name", model), "input_price": input_price, "output_price": output_price}
        for field in ("cache_read", "cache_write"):
            value = entry.get(field + "_usd_per_million")
            try:
                number = float(value) if value is not None and not isinstance(value, bool) else None
                price[field + "_price"] = number if number is not None and math.isfinite(number) and number >= 0 else None
            except (ValueError, TypeError, OverflowError):
                price[field + "_price"] = None
        return price

    def estimate(self, model: str, input_tokens: int | None, output_tokens: int | None, *, usage=None):
        if usage is None:
            usage = normalize_usage({"input_tokens": input_tokens, "output_tokens": output_tokens})
        else:
            usage = normalize_usage(usage)
        input_tokens, output_tokens = usage["input_tokens"], usage["output_tokens"]
        if not usage["usage_complete"]:
            return None
        price = self.price_for(model)
        if not price:
            return None
        counts = [(usage["uncached_input_tokens"], price["input_price"]), (output_tokens, price["output_price"])]
        for field, key in (("cache_read", "cache_read_input_tokens"), ("cache_write", "cache_creation_input_tokens")):
            count = usage[key]
            if count:
                counts.append((count, price[field + "_price"]))
        if any(count is None or rate is None for count, rate in counts):
            return None
        cost = sum((Decimal(count) * Decimal(str(rate)) for count, rate in counts), Decimal(0)) / Decimal(1_000_000)
        return {
            **price,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": float(cost),
        }


def format_cost(cost: float) -> str:
    return f"${cost:.6f}"


class ProjectState:
    def __init__(self, state_dir: Path, workspace: Path, session: str):
        self.workspace = workspace.expanduser().resolve()
        self.key = hashlib.sha256(str(self.workspace).encode()).hexdigest()[:16]
        self.private_state_root = state_dir.expanduser().resolve()
        self.root = state_dir.expanduser().resolve() / "projects" / self.key / safe_name(session)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "state.json"
        self.transcript_path = self.root / "transcript.jsonl"
        self.memory_path = self.root.parent / "memory.json"
        # Configuration files the application itself reads (e.g. a custom
        # --env-file). A model may never read, diff or overwrite them.
        self.protected_paths: set[Path] = set()
        self.data = self._load()
        self.memory = self._load_memory()

    def _load(self):
        defaults: dict[str, Any] = {"workspace": str(self.workspace), "session_id": uuid.uuid4().hex,
                    "context_schema_version": 1, "context_revision": uuid.uuid4().hex,
                    "files": {}, "history": [], "summary": "", "usage": {"requests": 0, "input": 0, "output": 0, "estimated_cost_usd": 0.0, "unpriced_requests": 0}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("workspace") != str(self.workspace):
                return defaults
            context_problem = context_state_error(data)
            for key, value in defaults.items():
                if not isinstance(data.get(key), type(value)):
                    data[key] = value
            for key, value in defaults["usage"].items():
                current = data["usage"].get(key)
                if key in {"input", "output"} and current is None and data["usage"].get("accounting_version") == 2:
                    continue
                if not isinstance(current, (int, float)) or not math.isfinite(current) or current < 0:
                    data["usage"][key] = value
            if data["usage"].get("accounting_version") == 2:
                for field in ("input", "output"):
                    known = data["usage"].get("known_" + field)
                    if type(known) is not int or known < 0:
                        data["usage"]["known_" + field] = 0
                        data["usage"][field] = None
            data["history"] = [v for v in data["history"] if isinstance(v, dict) and isinstance(v.get("content"), str) and v.get("role") in {"user", "assistant"}]
            data["files"] = {k:v for k,v in data["files"].items() if isinstance(v, dict)}
            if context_problem or context_state_error(data):
                # Keep the original scope for recovery before setup saves a
                # sanitized state; valid conversation and usage remain intact.
                quarantine = self.root / "quarantine" / ("state-" + uuid.uuid4().hex + ".json")
                quarantine.parent.mkdir(exist_ok=True)
                quarantine.write_bytes(self.path.read_bytes())
                for key in ("bg_context", "selected_target", "source_binding", "selected_codebook_path"):
                    data.pop(key, None)
                data["active_source_ids"] = []
                data["context_issue"] = "restored_invalid"
                data["context_revision"] = uuid.uuid4().hex
            data["context_schema_version"] = 1
            data.setdefault("context_revision", uuid.uuid4().hex)
            return data
        except (OSError, ValueError):
            return defaults

    def save(self):
        write_json_atomically(self.path, self.data)

    def _load_memory(self):
        if self.memory_path.exists():
            try:
                data = json.loads(self.memory_path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and isinstance(data.get("items"), list):
                    return data
            except (OSError, json.JSONDecodeError):
                pass
        return {"version": 1, "items": []}

    def save_memory(self):
        write_json_atomically(self.memory_path, self.memory)

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

    def edit_memory(self, item_id: str, content: str)