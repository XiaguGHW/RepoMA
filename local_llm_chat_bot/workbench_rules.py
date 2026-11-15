"""Rule file (Codebook) parsing helpers: pages and text blocks, parser prompts,
the parse budget, splitting oversized pieces, notes and rule-ID checks.

The job runner, caches and HTTP endpoints stay in chat_workbench.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from release_safety import safe_error
from workbench_i18n import UIMessage


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


def with_blocks(record: dict, values: object, key: str = "blocks") -> dict:
    """Keep text-block references of nonpaged Codebooks (TXT/DOCX) when present.

    The key is added only when the source carried it, so a PDF profile and an
    unchanged edit round-trip keep exactly their previous shape.
    """
    if isinstance(values, list):
        record[key] = [int(value) for value in values if str(value).isdigit() and int(value) > 0]
    return record


def nonpaged_references(draft: dict) -> dict:
    """A TXT/DOCX Codebook has no physical pages: record block numbers instead.

    Models sometimes put block numbers into ``pages``.  For a nonpaged source
    those are moved to ``blocks`` so no rule ever claims a fabricated page.
    """
    def move(record: dict, pages_key: str, blocks_key: str) -> None:
        pages = [page for page in record.get(pages_key, []) if type(page) is int and page > 0]
        existing = record.get(blocks_key)
        blocks = [value for value in existing if type(value) is int and value > 0] if isinstance(existing, list) else []
        record[blocks_key] = sorted(set(blocks) | set(pages))
        record[pages_key] = []
    for item in draft.get("classes", []):
        move(item, "evidence_pages", "evidence_blocks")
        for key in ("decision_rules", "boundaries"):
            for rule in item.get(key, []):
                if isinstance(rule, dict):
                    move(rule, "pages", "blocks")
    for key in ("global_rules", "table_rules"):
        for rule in draft.get(key, []):
            if isinstance(rule, dict):
                move(rule, "pages", "blocks")
    return draft


def profile_rules_in_order(draft: dict):
    """Yield (owner, rule) for every rule; owner is a class key or '' for global/table rules."""
    for key in ("global_rules", "table_rules"):
        for rule in draft.get(key, []) if isinstance(draft.get(key), list) else []:
            if isinstance(rule, dict):
                yield "", rule
    for item in draft.get("classes", []) if isinstance(draft.get("classes"), list) else []:
        if not isinstance(item, dict):
            continue
        owner = re.sub(r"[^a-z0-9]+", "-", str(item.get("name", "")).casefold()).strip("-") or "class"
        for key in ("decision_rules", "boundaries"):
            for rule in item.get(key, []) if isinstance(item.get(key), list) else []:
                if isinstance(rule, dict):
                    yield owner, rule


def rule_id_conflicts(draft: dict | None) -> list[str]:
    """Rule IDs used more than once anywhere in the profile, in first-seen order."""
    counts: dict[str, int] = {}
    for _owner, rule in profile_rules_in_order(draft or {}):
        if isinstance(rule.get("id"), str):
            counts[rule["id"]] = counts.get(rule["id"], 0) + 1
    return [rule_id for rule_id, count in counts.items() if count > 1]


def namespace_duplicate_rule_ids(draft: dict) -> list[dict]:
    """Deterministically rename model-generated duplicate IDs; the first use keeps its ID."""
    conflicts = set(rule_id_conflicts(draft))
    if not conflicts:
        return []
    used = {rule["id"] for _owner, rule in profile_rules_in_order(draft) if isinstance(rule.get("id"), str)}
    seen: set[str] = set()
    renames = []
    for owner, rule in profile_rules_in_order(draft):
        rule_id = rule.get("id")
        if rule_id not in conflicts:
            continue
        if rule_id not in seen:
            seen.add(rule_id)
            continue
        base = f"{owner or 'global'}:{rule_id}"
        candidate, number = base, 2
        while candidate in used:
            candidate, number = f"{base}-{number}", number + 1
        used.add(candidate)
        rule["id"] = candidate
        renames.append({"from": rule_id, "to": candidate})
    return renames


CODEBOOK_PAGE_SYSTEM = """You transcribe exactly one technical classification Codebook page, one part of a page, or one group of text blocks into compact rule notes, using the supplied native text, OCR text and page image. Return ONLY minified JSON: {\"source\":\"page 3\",\"official_names\":[\"exact wording\"],\"definitions\":[\"...\"],\"decision_rules\":[\"...\"],\"boundaries\":[\"...\"],\"tables\":[{\"title\":\"...\",\"columns\":[\"...\"],\"rows\":[[\"cell\"]]}],\"uncertainties\":[\"...\"]}. Keep official class names verbatim. State every definition, decision rule and boundary once, as one short sentence. For a table keep its title, its column names and only the rows that carry classification meaning, with short cells. Do not copy the page verbatim, do not repeat prose that carries no rule, do not invent text and omit empty fields. When the request covers only part of a page or of the text, cover only that part. Use the page or block numbers supplied in the prompt."""


CODEBOOK_MERGE_SYSTEM = """You consolidate page-by-page Codebook transcriptions. Return ONLY JSON: {\"classes\":[{\"name\":\"exact official class name\",\"definition\":\"...\",\"decision_rules\":[{\"id\":\"class-rule-1\",\"text\":\"...\",\"pages\":[1]}],\"boundaries\":[{\"id\":\"class-boundary-1\",\"text\":\"...\",\"pages\":[1]}],\"evidence_pages\":[1]}],\"global_rules\":[{\"id\":\"global-1\",\"text\":\"...\",\"pages\":[1]}],\"table_rules\":[{\"id\":\"table-1\",\"text\":\"meaning of the table rule\",\"pages\":[1],\"table\":{\"columns\":[\"...\"],\"rows\":[[\"...\"]]}}],\"uncertainties\":[\"...\"]}. Preserve exact names, rule IDs and page numbers. Do not invent missing rules. Keep each text short and state each rule once. For a Codebook without physical pages (TXT/DOCX) put the supplied text block numbers in \"blocks\" (and \"evidence_blocks\" for classes) and leave \"pages\" and \"evidence_pages\" empty; never invent page numbers."""


CODEBOOK_SECTION_SYSTEM = """You merge Codebook page notes into a classification rule profile, one section per request. The complete notes of the whole Codebook follow below. Return ONLY one minified JSON object in exactly the shape the request asks for. Preserve exact official class names, rule IDs and page numbers, keep each text short, state each rule once and do not invent rules. For a Codebook without physical pages (TXT/DOCX) put the text block numbers in \"blocks\" (and \"evidence_blocks\" for a class) and leave \"pages\" and \"evidence_pages\" empty; never invent page numbers.

--- CODEBOOK NOTES ---
"""


CODEBOOK_JSON_REPAIR_SYSTEM = """Return ONLY one complete, valid JSON object. Do not use Markdown fences or commentary. Preserve every fact, class name, rule, table value and page number from the supplied candidate; only repair JSON syntax such as missing commas, quotes, brackets or escaping."""


# Codebook rule files the workbench can prepare, by lower-case suffix.
CODEBOOK_FILE_TYPES = {".pdf": "pdf", ".docx": "docx", ".txt": "txt"}


# Offered first when no rule-parsing model was used before (UI default only).
CODEBOOK_RECOMMENDED_MODEL = "claude-haiku-5-5"


@dataclass(frozen=True)
class CodebookParseBudget:
    """Output-token budget and call bounds for Codebook rule parsing only.

    A *unit* is one PDF page or one group of DOCX/TXT text blocks.  Every
    request starts at the same 8192-token ceiling as chat answers (a ceiling,
    not a charge).  When a unit still stops at the output limit (Claude
    ``max_tokens``, Gemini ``MAX_TOKENS``, OpenAI ``length``), only that unit
    is retried once as two halves; if a half is cut too, or the unit cannot
    be split (e.g. a visual-only page), preparation fails for that unit.  A
    truncated response is never parsed, merged or saved.  Every model call of
    one preparation is counted against ``call_limit`` so a pathological file
    cannot cause unbounded cost.

    The merge first tries one request.  If that is cut (a large Codebook does
    not fit one response, and a multi-minute generation is cut by corporate
    proxies), the profile is merged section by section: a class outline, one
    request per class, general rules and table rules, each one request.
    Sections are assembled locally.
    """
    unit_output_tokens: int = 8192
    part_output_tokens: int = 8192
    max_split_depth: int = 1
    min_split_chars: int = 400
    merge_output_tokens: tuple[int, ...] = (8192,)
    section_output_tokens: tuple[int, ...] = (8192,)
    max_merge_classes: int = 40
    repair_output_tokens: int = 8192
    max_total_calls: int = 300

    @property
    def max_attempts_per_unit(self) -> int:
        """Strategy levels per unit: whole unit, then its halves."""
        return self.max_split_depth + 1

    @property
    def max_calls_per_unit(self) -> int:
        """Worst case: the whole unit plus its two halves."""
        return 2 ** (self.max_split_depth + 1) - 1

    def call_limit(self, units: int) -> int:
        sectioned = len(self.section_output_tokens) * (self.max_merge_classes + 3)
        planned = max(1, units) * self.max_calls_per_unit + len(self.merge_output_tokens) + sectioned + 1
        return min(self.max_total_calls, planned)


CODEBOOK_JOB_LOG_LIMIT = 200


CODEBOOK_FAILURE_REASONS = {
    "output_limit", "timeout", "network", "http", "invalid_json", "empty", "model_error",
    "cancelled", "call_limit", "no_rules", "empty_file", "encoding", "binary", "unreadable", "interrupted", "internal",
    "proxy", "section_output_limit", "connect_timeout",
}


def local_timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def codebook_unit_label(unit: dict | None):
    """Localized, user-facing name of one page or text-block range."""
    if not unit:
        return None
    if unit.get("kind") == "page":
        return UIMessage("rulejob.unit.page", "zh", number=unit["number"])
    if unit.get("first") == unit.get("last"):
        return UIMessage("rulejob.unit.block", "zh", number=unit["first"])
    return UIMessage("rulejob.unit.blocks", "zh", first=unit["first"], last=unit["last"])


class CodebookPrepareError(RuntimeError):
    """A classified Codebook preparation failure with a user-explainable reason."""

    def __init__(self, reason: str, stage: str, *, unit: dict | None = None, attempts: int | None = None,
                 technical: Any = "", params: dict | None = None):
        technical_text = safe_error(technical if isinstance(technical, str) else str(technical or ""))
        super().__init__(technical_text or reason)
        self.reason = reason if reason in CODEBOOK_FAILURE_REASONS else "internal"
        self.stage, self.unit, self.attempts = stage, unit, attempts
        self.technical, self.params = technical_text, dict(params or {})

    def messages(self) -> tuple[UIMessage, UIMessage]:
        """(full message, short card text); both re-localized by the browser."""
        params = dict(self.params)
        where = codebook_unit_label(self.unit) or UIMessage(f"rulejob.where.{self.stage}", "zh")
        params.setdefault("where", where)
        params.setdefault("unit", where)
        if self.attempts is not None:
            params.setdefault("attempts", self.attempts)
        full = UIMessage(f"rulejob.reason.{self.reason}", "zh", **{
            key: params[key] for key in re_placeholders(f"rulejob.reason.{self.reason}") if key in params})
        short = UIMessage(f"rulejob.short.{self.reason}", "zh", **{
            key: params[key] for key in re_placeholders(f"rulejob.short.{self.reason}") if key in params})
        return full, short


def re_placeholders(key: str) -> set[str]:
    from workbench_i18n import runtime_messages
    return set(re.findall(r"\{(\w+)\}", runtime_messages()["zh"][key]))


def classify_model_failure(failure: Any) -> tuple[str, dict[str, Any]]:
    """Map a connector failure text to a stable reason code."""
    if isinstance(failure, UIMessage) and failure.message_key in {"model.empty", "model.empty_endpoint"}:
        return "empty", {}
    text = str(failure or "").casefold()
    if "max_tokens" in text or "(length)" in text or "max tokens" in text:
        return "output_limit", {}
    if "proxyerror" in text or "proxy error" in text:
        return "proxy", {}
    if "connecttimeout" in text:
        return "connect_timeout", {}
    if "no complete response within" in text or "timed out" in text or "timeout" in text:
        return "timeout", {}
    if text.startswith("http error"):
        match = re.search(r"\d{3}", text)
        return "http", {"status": match.group(0) if match else "?"}
    if "connection" in text or text.startswith("error after"):
        return "network", {}
    return "model_error", {}


def parse_codebook_note(raw: str) -> dict | None:
    """One JSON object from a complete page/block or section response, or None.

    Tolerates what models commonly add around otherwise valid JSON: Markdown
    fences, text after the object, a second object and trailing commas.  The
    response itself is already known to be complete (its stop reason was
    checked), so this never turns a truncated answer into rules.
    """
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    start = text.find("{")
    if start < 0:
        return None
    candidates = [text[start:]]
    without_trailing_commas = re.sub(r",(\s*[}\]])", r"\1", text[start:])
    if without_trailing_commas != candidates[0]:
        candidates.append(without_trailing_commas)
    for candidate in candidates:
        try:
            note, _end = json.JSONDecoder().raw_decode(candidate)
        except ValueError:
            continue
        if isinstance(note, dict):
            return note
    return None


def json_error_detail(raw: str) -> str:
    """Where a response stopped being valid JSON, for the diagnostics only."""
    text = str(raw or "")
    start = max(0, text.find("{"))
    try:
        json.JSONDecoder().raw_decode(text[start:])
    except ValueError as exc:
        position = start + getattr(exc, "pos", 0)
        return f"{exc}; near: {text[max(0, position - 80):position + 80]!r}"
    return ""


def split_text_in_half(text: str) -> tuple[str, str]:
    """Split near the middle, preferring a line break, then a space."""
    middle = len(text) // 2
    window = max(80, len(text) // 5)
    for separator in ("\n\n", "\n", " "):
        left = text.rfind(separator, max(0, middle - window), middle + 1)
        right = text.find(separator, middle, min(len(text), middle + window))
        candidates = [index for index in (left, right) if index > 0]
        if candidates:
            cut = min(candidates, key=lambda index: abs(index - middle))
            return text[:cut].strip(), text[cut:].strip()
    return text[:middle].strip(), text[middle:].strip()


def split_codebook_piece(piece: dict, minimum: int) -> list[dict] | None:
    """Two smaller pieces of the same unit, or None when it cannot be split."""
    k, n = piece["part"]
    parts = [(2 * k - 1, 2 * n), (2 * k, 2 * n)]
    if "chunks" in piece:
        chunks = piece["chunks"]
        if len(chunks) > 1:
            middle = len(chunks) // 2
            return [dict(piece, chunks=chunks[:middle], part=parts[0]), dict(piece, chunks=chunks[middle:], part=parts[1])]
        number, label, text = chunks[0]
        if len(text) < 2 * minimum:
            return None
        first, second = split_text_in_half(text)
        return [dict(piece, chunks=[(number, label, first)], part=parts[0]),
                dict(piece, chunks=[(number, label, second)], part=parts[1])]
    native, ocr = piece.get("native", ""), piece.get("ocr", "")
    if max(len(native), len(ocr)) < 2 * minimum:
        return None
    native_parts = split_text_in_half(native) if len(native) >= 2 * minimum else (native, "")
    ocr_parts = split_text_in_half(ocr) if len(ocr) >= 2 * minimum else (ocr, "")
    return [dict(piece, native=native_parts[0], ocr=ocr_parts[0], part=parts[0]),
            dict(piece, native=native_parts[1], ocr=ocr_parts[1], part=parts[1])]


def codebook_piece_request(unit: dict, piece: dict, total: int, file_type: str) -> tuple[list[str], str, str]:
    """(files, prompt, source label) for one page/text piece."""
    k, n = piece["part"]
    if unit["kind"] == "page":
        source = f"page {unit['number']}" + (f" part {k}/{n}" if n > 1 else "")
        prompt = f"Codebook page {unit['number']} of {total}. Page type: {unit['page_type']}."
        if n > 1:
            prompt += (f" This request covers only part {k}/{n} of this page's text: extract only the rules stated in "
                       "this part and use the page image only to understand its layout.")
        prompt += (f"\n--- NATIVE TEXT ---\n{piece.get('native') or '[none]'}"
                   f"\n--- OCR TEXT ({unit['ocr_status']}) ---\n{piece.get('ocr') or '[none]'}")
        return [unit["image_path"]], prompt, source
    numbers = [number for number, _label, _text in piece["chunks"]]
    source = f"blocks {numbers[0]}-{numbers[-1]}" + (f" part {k}/{n}" if n > 1 else "")
    prompt = (f"Codebook {file_type.upper()} text blocks {unit['first']}-{unit['last']} of {unit['blocks_total']}. "
              "This Codebook has no physical pages: cite block numbers, never page numbers.")
    if n > 1:
        prompt += f" This request covers only part {k}/{n} of these blocks: extract only the rules stated in this part."
    prompt += "\n\n" + "\n\n".join(f"--- BLOCK {number}: {label} ---\n{text}" for number, label, text in piece["chunks"])
    return [], prompt, source


def codebook_notes_text(notes: list[list[dict]], nonpaged: bool) -> str:
    label = "TEXT BLOCK GROUP" if nonpaged else "PAGE GROUP"
    return "\n\n".join(
        f"--- {label} {index} ---\n{json.dumps(unit_notes[0] if len(unit_notes) == 1 else unit_notes, ensure_ascii=False, separators=(',', ':'))}"
        for index, unit_notes in enumerate(notes, start=1))


def codebook_unit_key(unit: dict) -> str:
    if unit["kind"] == "page":
        content = f"{unit['native_text']}\0{unit['ocr_text']}\0{unit['page_type']}"
        return f"page:{unit['number']}:" + hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    content = "\0".join(text for _number, _label, text in unit["chunks"])
    return f"blocks:{unit['first']}-{unit['last']}:" + hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def load_codebook_note_cache(path: Path) -> dict[str, list[dict]]:
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(cached, dict):
        return {}
    return {key: value for key, value in cached.items()
            if isinstance(value, list) and value and all(isinstance(note, dict) for note in value)}


def codebook_text_units(chunks: list[dict], per_unit: int = 3) -> list[dict]:
    """Group nonpaged text blocks; block numbers match the material section labels."""
    numbered = [(index, str(chunk.get("label", "")), str(chunk.get("text", "")))
                for index, chunk in enumerate(chunks, start=1) if str(chunk.get("text", "")).strip()]
    return [{"kind": "blocks", "first": group[0][0], "last": group[-1][0], "blocks_total": len(chunks), "chunks": group}
            for group in (numbered[index:index + per_unit] for index in range(0, len(numbered), per_unit))]
