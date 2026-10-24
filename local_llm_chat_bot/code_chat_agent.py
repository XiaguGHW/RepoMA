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
import sys
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path
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
        self.entries = []
        self.error = None
        if not path:
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.entries = data.get("entries", []) if isinstance(data, dict) else []
            if not isinstance(self.entries, list): self.entries = []
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
        if not usage["usage_complete"]: return None
        price = self.price_for(model)
        if not price:
            return None
        counts = [(usage["uncached_input_tokens"], price["input_price"]), (output_tokens, price["output_price"])]
        for field, key in (("cache_read", "cache_read_input_tokens"), ("cache_write", "cache_creation_input_tokens")):
            count = usage[key]
            if count:
                counts.append((count, price[field + "_price"]))
        if any(count is None or rate is None for count, rate in counts): return None
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
        self.data = self._load()
        self.memory = self._load_memory()

    def _load(self):
        defaults = {"workspace": str(self.workspace), "session_id": uuid.uuid4().hex,
                    "context_schema_version": 1, "context_revision": uuid.uuid4().hex,
                    "files": {}, "history": [], "summary": "", "usage": {"requests": 0, "input": 0, "output": 0, "estimated_cost_usd": 0.0, "unpriced_requests": 0}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("workspace") != str(self.workspace): return defaults
            context_problem = context_state_error(data)
            for key, value in defaults.items():
                if not isinstance(data.get(key), type(value)): data[key] = value
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
        value = ensure_relative(value)
        original = self.workspace / value
        candidate = original.resolve()
        try:
            resolved_parts = candidate.relative_to(self.workspace).parts
        except ValueError as exc:
            raise ValueError("Path is outside the workspace") from exc
        ignored = {os.path.normcase(part) for part in IGNORED_DIRS}
        for parts in (Path(value).parts, resolved_parts):
            if any(os.path.normcase(part) in ignored
                   or part.lower().startswith(".env")
                   or Path(part).suffix.lower() in {".pem", ".key"} for part in parts):
                raise ValueError("Private application state/configuration cannot be read or changed by a model")
        if candidate == self.private_state_root or self.private_state_root in candidate.parents:
            raise ValueError("Private application state cannot be read or changed by a model")
        # lstat every component, including directory links, junctions and other
        # Windows reparse points. A missing tail is allowed for a new file.
        component = self.workspace
        for part in Path(value).parts:
            component = component / part
            try:
                metadata = component.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(metadata.st_mode) or (
                getattr(metadata, "st_file_attributes", 0)
                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            ):
                raise ValueError("Linked/reparse paths cannot be read or changed by a model")
        return candidate

    def scan(self):
        files = {}
        for root, dirs, names in os.walk(self.workspace):
            safe_dirs = []
            for directory in dirs:
                try:
                    self.resolve_relative((Path(root) / directory).relative_to(self.workspace).as_posix())
                except (OSError, ValueError, RuntimeError):
                    continue
                safe_dirs.append(directory)
            dirs[:] = safe_dirs
            for name in names:
                path = Path(root) / name
                if path.suffix.lower() not in CODE_EXTENSIONS:
                    continue
                try:
                    path = self.resolve_relative(path.relative_to(self.workspace).as_posix())
                    if path.is_symlink() or path.name.startswith(".env") or path.stat().st_size > MAX_FILE_BYTES: continue
                    raw = path.read_bytes()
                except (OSError, ValueError):
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
        turn = {"role": role, "content": content, "time": now()}
        # Migrate the compact legacy window into the archive on first use.
        if not self.transcript_path.exists() and self.data.get("history"):
            write_jsonl_atomically(self.transcript_path, self.data["history"])
        # Keep a complete local archive for review, while sending only the
        # compact in-state window to the model on later requests.
        append_jsonl_durably(self.transcript_path, turn)
        self.data["history"].append(turn)
        self.data["history"] = self.data["history"][-8:]
        self.save()

    def full_history(self, limit: int = 500):
        if not self.transcript_path.exists():
            return list(self.data.get("history", []))
        records = []
        try:
            with self.transcript_path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        item = json.loads(line)
                        if isinstance(item, dict) and item.get("role") and item.get("content"):
                            records.append(item)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            return list(self.data.get("history", []))
        return records[-limit:]

    def note_usage(self, usage, pricing: PricingCatalog, model: str):
        usage = normalize_usage(usage)
        input_tokens, output_tokens = usage["input_tokens"], usage["output_tokens"]
        aggregate = self.data["usage"]
        if aggregate.get("accounting_version") != 2:
            for field in ("input", "output"):
                aggregate["known_" + field] = aggregate[field]
                if aggregate["unpriced_requests"]:
                    aggregate[field] = None  # Legacy unknown counts cannot be reconstructed.
            aggregate["accounting_version"] = 2
        aggregate["requests"] += 1
        for field, count in (("input", input_tokens), ("output", output_tokens)):
            aggregate["known_" + field] += count if count is not None else 0
            aggregate[field] = aggregate["known_" + field] if aggregate[field] is not None and count is not None else None
        aggregate["usage_complete"] = aggregate["input"] is not None and aggregate["output"] is not None and aggregate.get("usage_complete", True) and usage["usage_complete"]
        estimate = pricing.estimate(model, input_tokens, output_tokens, usage=usage)
        if estimate:
            aggregate["estimated_cost_usd"] = float(Decimal(str(aggregate["estimated_cost_usd"])) + Decimal(str(estimate["cost_usd"])))
        else:
            aggregate["unpriced_requests"] += 1
        aggregate["cost_complete"] = not aggregate["unpriced_requests"]
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
    data.setdefault("classification", None)
    if not isinstance(data["answer"], str) or not isinstance(data["read_files"], list) or not isinstance(data["changes"], list):
        raise ValueError("Invalid action field types")
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
    path = path.replace("\\", "/")
    item = Path(path)
    if item.is_absolute() or ".." in item.parts or ":" in path or not path.strip():
        raise ValueError(f"Unsafe path from model: {path!r}")
    return item.as_posix()


def classification_manifest(evidence, context):
    context = context or {}
    source_ids = set(context.get("source_ids", []))
    codebook_id = context.get("codebook_id")
    bg_labels, rule_labels = [], []
    for item in evidence:
        label = item.get("label")
        if not isinstance(label, str) or not label:
            continue
        is_rule = item.get("id") == codebook_id or item.get("id") == "locked-codebook-page"
        if is_rule and codebook_id:
            rule_labels.append(label)
        elif not context or item.get("id") in source_ids:
            bg_labels.append(label)
    return {
        "bg_labels": list(dict.fromkeys(bg_labels)),
        "codebook_labels": list(dict.fromkeys(rule_labels)),
        "codebook_source_kind": "pdf" if Path(str(context.get("codebook_path", ""))).suffix.lower() == ".pdf" else "nonpaged",
    }


def prompt_for(state: ProjectState, question: str, snippets: dict[str, str], full_files: dict[str, str] | None = None,
               document_snippets: list[dict] | None = None, bg_context: dict | None = None,
               coverage_summaries: list[dict] | None = None, bg_dossier: dict | None = None,
               response_language: str = "zh", require_classification: bool = True):
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
    coverage_text = "\n\n".join(
        f"--- FILE COVERAGE SUMMARY {item.get('name', 'unknown')} ---\n{item.get('summary', '')}"
        for item in (coverage_summaries or []) if item.get("summary")
    ) or "(No complete per-file coverage summary has been prepared.)"
    dossier_text = str((bg_dossier or {}).get("summary", "")).strip() or "(No BG comprehensive evidence dossier has been prepared.)"
    bg_instruction = ""
    if bg_context:
        locked_profile = bg_context.get("locked_profile") or {}
        profile_text = json.dumps(locked_profile, ensure_ascii=False) if locked_profile else "(No locked structured profile available.)"
        manifest = json.dumps(classification_manifest(document_snippets or [], bg_context), ensure_ascii=False)
        response_mode = "CLASSIFICATION REQUIRED: return a complete classification object." if require_classification else "EXPLANATION MODE: classification may be null; any non-null classification must meet every validation rule."
        bg_instruction = f"""
BG CLASSIFICATION MODE (active):
- Codebook: {bg_context.get('codebook_name', 'unknown')}
- Baugruppe folder: {bg_context.get('folder', 'unknown')}
- Locked Codebook profile (user-confirmed; use this as the primary rule source): {profile_text}
- Classification reference manifest: {manifest}
- {response_mode}
- Give the full detailed classification format required by the system prompt.
- Treat the Codebook as the rule source. Cite evidence labels exactly as supplied.
- A source marked visual/scanned may require visual inspection; do not infer text that was not supplied.
- In CLASSIFICATION REQUIRED mode include this `classification` object; in EXPLANATION MODE it may be null:
  {{"label": "exact Codebook class name", "confidence": "high|medium|low", "alternative_label": "exact Codebook class name or empty", "codebook_rule_ids": ["exact rule id from the locked profile"], "codebook_rule_pages": [], "codebook_rule_refs": ["exact codebook_labels entry"], "evidence_labels": ["exact supplied document label"], "bg_evidence_pages": ["exact bg_labels entry"], "uncertainties": []}}.
- Copy the class and evidence-label spelling exactly. Use only evidence labels supplied in this prompt. A non-empty evidence_labels list is mandatory for a classification.
- A non-empty codebook_rule_ids list is mandatory; it must name the actual locked rule(s) used for the decision. Keep Codebook-rule pages and BG-evidence pages separate.
- For a PDF Codebook, codebook_rule_pages must contain actual positive integer pages of the cited rules. For DOCX/TXT or other nonpaged rules, leave codebook_rule_pages empty and cite actual supplied Codebook section/chunk labels in codebook_rule_refs. Never invent physical pages for nonpaged text.
- bg_evidence_pages must copy supplied BG labels, including their actual page/sheet/row/chunk range. Codebook labels are not BG evidence.
"""
    language_name = {"zh": "Chinese", "en": "English", "de": "German"}.get(str(response_language).lower(), "Chinese")
    return f"""Workspace: {state.workspace}
Project summary: {state.data['summary'] or '(none)'}
Recent conversation:\n{recent}

Relevant confirmed long-term memory (local, user-confirmed):\n{memory_text}

Indexed files and symbols (local metadata only):\n{indexed}

Relevant code excerpts:\n{shown}

Relevant locally extracted document excerpts:\n{document_text}

BG comprehensive evidence dossier (compiled from the selected files' local summaries; citations and limitations must be retained):\n{dossier_text}

Prepared per-file evidence summaries (fallback only when no dossier is available; do not claim unread pages were inspected):\n{coverage_text}

Complete current files supplied in this turn:\n{complete}

Response language: Write the natural-language `answer` primarily in {language_name}.
Do not translate official Codebook category names, filenames, part numbers, source quotations,
table labels, or the supplied material evidence; preserve their original spelling verbatim.

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

