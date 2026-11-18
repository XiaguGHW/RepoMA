"""Session state, prices and the answer prompt of the Bosch Assembly Assistant.

ProjectState keeps one session (history, usage, context binding) under
AI_Bot_State; PricingCatalog estimates costs; SYSTEM and prompt_for() build
the answer prompt sent to Bosch Farm.  (The name comes from the terminal code
chat this module started as; that terminal tool was removed in refactor
step 2.)"""
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
from release_safety import PROMPT_CACHE_BREAK, context_state_error, normalize_usage
from price_page import merge_page_prices

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

SYSTEM = """You are the Bosch Assembly Assistant. You classify a Baugruppe (assembly) by a locked Codebook
and answer questions about its documents. You have no direct file access: the local program supplies the
locked Codebook profile, an evidence dossier, per-file summaries and locally extracted document excerpts.
Return ONLY one JSON object, without Markdown fences:
{"answer": "plain-text answer in the response language requested in the user prompt", "classification": null}
The user prompt says when and in which form a classification object is required.
Rules:
- Use only the supplied material as evidence. Cite file names with page, sheet, row or chunk exactly as labelled.
  Do not invent evidence. Separate an observed fact from an inference. If the evidence is insufficient, say what is missing.
- Write `answer` in the requested response language. Keep official Codebook category names, file names, part numbers,
  source quotations, supplied table labels and technical evidence exactly as provided.
- `answer` is shown as plain text: no Markdown tables, headings or nested lists.
- Explanation (classification null): normally at most about 1200 Chinese characters (or equivalent): a one-sentence
  conclusion, then 3-5 short numbered points; add a next step only when the user needs an action. Longer only when the
  user explicitly asks for detail.
- Classification (non-null classification object): an evidence-led assessment of at most about 1500 Chinese characters
  (or equivalent), in short sections: recommendation; Codebook decision path; evidence (file/page/sheet/row);
  alternatives; uncertainty. At most 4 short points per section; cite evidence labels instead of quoting long passages.
- The classification object must always be complete, and the JSON object must always be valid: shorten the answer rather
  than leave either unfinished.
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
        self.source: dict[str, Any] = {"kind": "bundled"}
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
        # A Docupedia pricing page saved next to the program overrides the bundled prices.
        self.entries, self.source = merge_page_prices(self.entries, path.parent)

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

    def partial_estimate(self, model: str, usage) -> dict | None:
        """Price what can be priced; name the token types that have no price.

        Bosch Farm publishes no cache prices, so cache tokens are reported by type
        and count instead of being guessed.  None when the model has no price or
        the provider returned incomplete usage."""
        usage = normalize_usage(usage)
        if not usage["usage_complete"]:
            return None
        price = self.price_for(model)
        if not price:
            return None
        known = Decimal(usage["uncached_input_tokens"]) * Decimal(str(price["input_price"]))
        known += Decimal(usage["output_tokens"]) * Decimal(str(price["output_price"]))
        unpriced = {}
        for field, key in (("cache_read", "cache_read_input_tokens"), ("cache_write", "cache_creation_input_tokens")):
            count = usage[key]
            if not count:
                continue
            rate = price.get(field + "_price")
            if rate is None:
                unpriced[field] = count
            else:
                known += Decimal(count) * Decimal(str(rate))
        return {"known_cost_usd": float(known / Decimal(1_000_000)), "unpriced_tokens": unpriced}


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

    def protect(self, *paths) -> None:
        """Add secret/configuration files that must stay outside the model boundary."""
        for path in paths:
            if path:
                try:
                    self.protected_paths.add(Path(path).expanduser().resolve())
                except (OSError, ValueError):
                    continue

    def resolve_relative(self, value: str) -> Path:
        value = ensure_relative(value)
        original = self.workspace / value
        candidate = original.resolve()
        protected = {os.path.normcase(str(path)) for path in getattr(self, "protected_paths", ())}
        if os.path.normcase(str(candidate)) in protected:
            raise ValueError("Application configuration files cannot be read or changed by a model")
        try:
            resolved_parts = candidate.relative_to(self.workspace).parts
        except ValueError as exc:
            raise ValueError("Path is outside the workspace") from exc
        ignored = {os.path.normcase(part) for part in IGNORED_DIRS}
        for parts in (Path(value).parts, resolved_parts):
            if any(os.path.normcase(part) in ignored
                   or part.lower().startswith(".env") or part.lower().endswith(".env")
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
                    if path.is_symlink() or path.name.startswith(".env") or path.stat().st_size > MAX_FILE_BYTES:
                        continue
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
            detail = aggregate.setdefault("unpriced_detail", {})
            partial = pricing.partial_estimate(model, usage) if hasattr(pricing, "partial_estimate") else None
            if partial:
                aggregate["estimated_cost_usd"] = float(Decimal(str(aggregate["estimated_cost_usd"])) + Decimal(str(partial["known_cost_usd"])))
                for kind, count in partial["unpriced_tokens"].items():
                    detail[kind] = detail.get(kind, 0) + count
                estimate = {"cost_usd": None, **partial}
            elif not usage["usage_complete"]:
                detail["usage_missing_requests"] = detail.get("usage_missing_requests", 0) + 1
            else:
                detail["model_requests"] = detail.get("model_requests", 0) + 1
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


class StreamState(TypedDict):
    started: bool
    done: bool
    cursor: int
    escape: bool
    unicode: str
    answer_chars: list[str]


def streamed_answer_handler() -> tuple[Callable[[str, str], None], StreamState]:
    """Reveal only the JSON answer field while retaining the full action internally."""
    raw: list[str] = []
    state: StreamState = {"started": False, "done": False, "cursor": 0, "escape": False, "unicode": "", "answer_chars": []}

    def emit_char(char: str) -> None:
        state["answer_chars"].append(char)
        print(char, end="", flush=True)

    def handler(kind: str, text: str) -> None:
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


def prompt_for(state: ProjectState, question: str,
               document_snippets: list[dict] | None = None, bg_context: dict | None = None,
               coverage_summaries: list[dict] | None = None, bg_dossier: dict | None = None,
               response_language: str = "zh", require_classification: bool | None = True,
               focus_name: str = ""):
    recent = "\n".join(f"{turn['role']}: {turn['content']}" for turn in state.data["history"][-HISTORY_MESSAGES_PER_REQUEST:]) or "(new conversation)"
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
    stable = ""
    if bg_context:
        locked_profile = bg_context.get("locked_profile") or {}
        profile_text = json.dumps(locked_profile, ensure_ascii=False) if locked_profile else "(No locked structured profile available.)"
        manifest = json.dumps(classification_manifest(document_snippets or [], bg_context), ensure_ascii=False)
        if require_classification is None:
            response_mode = ("AUTO MODE: decide from the user request. If the user asks to classify, determine, confirm or "
                             "re-check the Baugruppe class, return a complete classification object and use the detailed "
                             "classification format. Otherwise answer exactly what was asked in the normal answer shape, set "
                             "classification to null, and treat earlier classification results in the conversation as background only.")
        elif require_classification:
            response_mode = "CLASSIFICATION REQUIRED: return a complete classification object."
        else:
            response_mode = ("EXPLANATION MODE: answer the user's question directly; classification should be null unless the user "
                             "explicitly asks for a classification. Any non-null classification must meet every validation rule.")
        focus = (f"- FOCUS FILE: the user restricted this turn to the single file '{focus_name}'. Only its excerpts were supplied. "
                 "Answer about this file; do not draw conclusions from other files except earlier results in the conversation "
                 "or the BG dossier at the top as background, and say so when you use them.\n") if focus_name else ""
        # Stable for the whole Baugruppe context and therefore first: identical
        # across turns, so Claude reads it from cache and other providers can
        # reuse the common prefix.
        stable = f"""BG CLASSIFICATION RULES (identical in every turn of this Baugruppe):
- Codebook: {bg_context.get('codebook_name', 'unknown')}
- Locked Codebook profile (user-confirmed; use this as the primary rule source): {profile_text}

BG comprehensive evidence dossier (compiled from the selected files' local summaries; citations and limitations must be retained):
{dossier_text}{PROMPT_CACHE_BREAK}"""
        bg_instruction = f"""
BG CLASSIFICATION MODE (active):
- Codebook: {bg_context.get('codebook_name', 'unknown')} (locked profile and dossier: see BG CLASSIFICATION RULES at the top)
- Baugruppe folder: {bg_context.get('folder', 'unknown')}
- Classification reference manifest: {manifest}
- {response_mode}
{focus}- When you return a classification, give the full detailed classification format required by the system prompt.
- Treat the Codebook as the rule source. Cite evidence labels exactly as supplied.
- A source marked visual/scanned may require visual inspection; do not infer text that was not supplied.
- In CLASSIFICATION REQUIRED mode include this `classification` object; in AUTO or EXPLANATION MODE it may be null:
  {{"label": "exact Codebook class name", "confidence": "high|medium|low", "alternative_label": "exact Codebook class name or empty", "codebook_rule_ids": ["exact rule id from the locked profile"], "codebook_rule_pages": [], "codebook_rule_refs": ["exact codebook_labels entry"], "evidence_labels": ["exact supplied document label"], "bg_evidence_pages": ["exact bg_labels entry"], "uncertainties": []}}.
- Copy the class and evidence-label spelling exactly. Use only evidence labels supplied in this prompt. A non-empty evidence_labels list is mandatory for a classification.
- A non-empty codebook_rule_ids list is mandatory; it must name the actual locked rule(s) used for the decision. Keep Codebook-rule pages and BG-evidence pages separate.
- For a PDF Codebook, codebook_rule_pages must contain actual positive integer pages of the cited rules. For DOCX/TXT or other nonpaged rules, leave codebook_rule_pages empty and cite actual supplied Codebook section/chunk labels in codebook_rule_refs. Never invent physical pages for nonpaged text.
- bg_evidence_pages must copy supplied BG labels, including their actual page/sheet/row/chunk range. Codebook labels are not BG evidence.
"""
    language_name = {"zh": "Chinese", "en": "English", "de": "German"}.get(str(response_language).lower(), "Chinese")
    dossier_block = "" if stable else f"""BG comprehensive evidence dossier (compiled from the selected files' local summaries; citations and limitations must be retained):\n{dossier_text}

"""
    return f"""{stable}Recent conversation:\n{recent}

Relevant locally extracted document excerpts:\n{document_text}

{dossier_block}Prepared per-file evidence summaries (fallback only when no dossier is available; do not claim unread pages were inspected):\n{coverage_text}

Response language: Write the natural-language `answer` primarily in {language_name}.
Do not translate official Codebook category names, filenames, part numbers, source quotations,
table labels, or the supplied material evidence; preserve their original spelling verbatim.

User request: {question}
{bg_instruction}
"""
