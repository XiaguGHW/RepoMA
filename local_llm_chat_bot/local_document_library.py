"""Local text extraction and lexical retrieval for terminal document chat."""
from __future__ import annotations

import csv
import builtins
import hashlib
import io
import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SUPPORTED_DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".xlsm", ".csv", ".txt", ".md", ".png", ".jpg", ".jpeg", ".webp"}
# The original 25 MB ceiling made a normal multi-page drawing package unusable.
# This remains a local index: files are never copied to the model merely because
# they are added.  Only retrieved text and a few selected visual pages are sent.
MAX_DOCUMENT_BYTES = 80 * 1024 * 1024
MAX_CHUNK_CHARS = 3500
MAX_CHUNKS_PER_DOCUMENT = 900
# Version 2: nonpaged text/DOCX chunks carry "section i/n", CSV chunks their row
# range. Older index records are re-extracted locally (no model call) on reuse.
LABEL_VERSION = 2
MAX_EXCEL_ROWS_PER_SHEET = 2000
MAX_VISUALS_PER_REQUEST = 5
# Bosch Farm sends file attachments base64-encoded.  Keep the binary total
# below this conservative value so the JSON request stays well inside typical
# 4 MB gateway limits, even when the source drawing itself is tens of MB.
MAX_VISUAL_BYTES_PER_REQUEST = 2_400_000
MAX_VISUAL_BYTES_PER_FILE = 700_000
MAX_SHORT_PDF_PAGES = 5
MAX_IMAGE_GROUP_DETAIL_VIEWS = 3
MAX_DFC_SEGMENTS_PER_REQUEST = 4
# DFC exports are often one very tall Teamcenter hierarchy screenshot.  Keep
# the source untouched and cache readable, overlapping crops for a later
# structure-aware reading pass.
DFC_LONG_IMAGE_MIN_HEIGHT = 2400
DFC_LONG_IMAGE_MIN_ASPECT = 1.6
DFC_SEGMENT_MAX_HEIGHT = 2800
DFC_SEGMENT_MIN_HEIGHT = 1600
DFC_SEGMENT_OVERLAP = 240

QUERY_EXPANSIONS = {
    "rotation": ("rotation", "rotieren", "drehen", "dreh", "schwenk", "achse"),
    "旋转": ("rotation", "rotieren", "drehen", "dreh", "schwenk", "achse"),
    "linear": ("linear", "hub", "translator", "schlitten", "führung", "fuehrung"),
    "直线": ("linear", "hub", "translator", "schlitten", "führung", "fuehrung"),
    "greifer": ("greifer", "greif", "end-effektor", "endeffektor", "gripper"),
    "夹": ("greifer", "greif", "end-effektor", "endeffektor", "gripper"),
    "motor": ("motor", "servo", "antrieb", "getriebe", "pneumatik"),
    "驱动": ("motor", "servo", "antrieb", "getriebe", "pneumatik"),
    "interface": ("schnittstelle", "interface", "anschluss", "stecker", "io"),
    "接口": ("schnittstelle", "interface", "anschluss", "stecker", "io"),
}

MATERIAL_ROLE_LABELS = {
    "technical_drawing": "技术图纸",
    "bom": "BOM / 装配表",
    "datasheet": "数据表 / 目录",
    "dfc_structure": "DFC 结构图",
    "cad_screenshot": "CAD 截图",
    "derived_duplicate": "派生重复资料",
    "unsupported_drawing": "Inventor 源图（暂不支持）",
    "other": "其他资料",
}
MATERIAL_ROLE_PRIORITY = {
    "technical_drawing": 0, "dfc_structure": 0, "bom": 1,
    "datasheet": 2, "cad_screenshot": 3, "other": 4,
    "derived_duplicate": 99, "unsupported_drawing": 100,
}


def _path_text(path: Path) -> tuple[str, str]:
    text = " ".join(part.casefold() for part in path.parts)
    return text, re.sub(r"[^a-z0-9]+", "", text)


def has_dfc_structure_signal(path: Path) -> bool:
    """Require both DFC and a structural term; ATB names must not match."""
    text, compact = _path_text(path)
    structure_terms = ("struktur", "strucktur", "structure", "strukturbaum", "baugruppenstruktur")
    return ("dfc" in compact and any(term in text or term in compact for term in structure_terms)) or "strukturbaum" in compact or "baugruppenstruktur" in compact


def material_role(path: Path) -> str:
    """Classify material locally from stable file/folder naming conventions."""
    text, compact = _path_text(path)
    name = path.name.casefold()
    suffix = path.suffix.casefold()
    if "convertedpdfimages" in compact or "converted_pdf_images" in text or "visualcontext" in compact:
        return "derived_duplicate"
    if suffix in {".idw", ".dwg"}:
        return "unsupported_drawing"
    if suffix in {".png", ".jpg", ".jpeg", ".webp"} and has_dfc_structure_signal(path):
        return "dfc_structure"
    if any(term in name for term in ("atb", "stueckliste", "stückliste", "part list", "partslist", "parts_list")):
        return "bom"
    if any(term in name for term in ("datenblatt", "data sheet", "datasheet")) or re.search(r"(?:^|[_-])cat(?:[_-]|$)", name):
        return "datasheet"
    if suffix == ".pdf" and (path.with_suffix(".idw").is_file() or any(term in name for term in ("zeichnung", "drawing", "technische zeichnung"))):
        return "technical_drawing"
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        return "cad_screenshot"
    return "other"


def material_is_recommended(path: Path) -> bool:
    return material_role(path) not in {"derived_duplicate", "unsupported_drawing"}


def material_role_label(role: str) -> str:
    return MATERIAL_ROLE_LABELS.get(role, MATERIAL_ROLE_LABELS["other"])


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _tokens(text):
    return re.findall(r"[A-Za-z_][A-Za-z0-9_]{1,}|[\u4e00-\u9fff]{2,}|\d{2,}", text.lower())


def _expanded_tokens(question: str) -> set[str]:
    lowered = question.casefold()
    result = set(_tokens(question))
    for trigger, additions in QUERY_EXPANSIONS.items():
        if trigger in lowered:
            result.update(additions)
    return result


def _sectioned(label, chunks):
    """Give every chunk of a nonpaged source its own traceable section label."""
    if len(chunks) > 1:
        for number, chunk in enumerate(chunks, start=1):
            chunk["label"] = f"{label} — section {number}/{len(chunks)}"
    return chunks


def _row_ranges(label, chunks):
    """Label CSV chunks with the actual first/last data row they contain."""
    for chunk in chunks:
        rows = re.findall(r"(?m)^Row (\d+):", chunk["text"])
        if rows:
            chunk["label"] = f"{label} — rows {rows[0]}-{rows[-1]}"
    return chunks


def _chunks(label, text):
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    result, current = [], ""
    for paragraph in paragraphs:
        if len(paragraph) > MAX_CHUNK_CHARS:
            parts = [paragraph[i:i + MAX_CHUNK_CHARS] for i in range(0, len(paragraph), MAX_CHUNK_CHARS)]
        else:
            parts = [paragraph]
        for part in parts:
            candidate = part if not current else current + "\n\n" + part
            if current and len(candidate) > MAX_CHUNK_CHARS:
                result.append({"label": label, "text": current})
                current = part
            else:
                current = candidate
    if current:
        result.append({"label": label, "text": current})
    return result


class LocalDocumentLibrary:
    """Documents and extracted chunks stay in one local JSON file."""

    def __init__(self, path: Path):
        self.path = path
        self.data = self._load()
        self.last_visual_report: dict[str, object] = {}
        self._ocr_runtime_cache: dict[str, object] | None = None

    def _load(self):
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and isinstance(data.get("documents"), list):
                    from release_safety import valid_document_record
                    valid = [d for d in data["documents"] if valid_document_record(d)]
                    if len(valid) != len(data["documents"]):
                        import uuid
                        quarantine = self.path.parent / "quarantine" / ("documents-" + uuid.uuid4().hex + ".json")
                        quarantine.parent.mkdir(exist_ok=True)
                        quarantine.write_bytes(self.path.read_bytes())
                    data["documents"] = valid
                    return data
            except (OSError, json.JSONDecodeError):
                pass
        return {"version": 1, "documents": []}

    def _save(self):
        """Persist the index without ever exposing a partially written JSON file.

        The index is an expendable local cache, but a power loss during a direct
        ``write_text`` could otherwise leave it syntactically truncated.  Keep
        the temporary file in the same directory so ``os.replace`` is atomic on
        the local filesystem.  A corrupt historical index is still handled by
        ``_load`` as an empty index; no source material is touched.
        """
        if getattr(self, "_defer_save", False):
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent, text=True
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
                json.dump(self.data, handle, ensure_ascii=False, indent=2)
                handle.flush()
                try:
                    os.fsync(handle.fileno())
                except OSError:
                    # Some network/synchronised folders do not support fsync.
                    # Closing and replacing still prevents half-written JSON.
                    pass
            os.replace(temporary, self.path)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def add(self, value: str):
        path = Path(value.strip().strip('"')).expanduser().resolve()
        if not path.is_file():
            raise ValueError(f"File does not exist: {path}")
        if path.suffix.lower() not in SUPPORTED_DOCUMENT_EXTENSIONS:
            allowed = ", ".join(sorted(SUPPORTED_DOCUMENT_EXTENSIONS))
            raise ValueError(f"Unsupported file type {path.suffix or '(none)'}. Supported: {allowed}")
        if path.stat().st_size > MAX_DOCUMENT_BYTES:
            raise ValueError(f"{path.name}: File is larger than {MAX_DOCUMENT_BYTES // (1024 * 1024)} MB.")
        raw = path.read_bytes()
        if len(raw) > MAX_DOCUMENT_BYTES:
            raise ValueError(f"File is larger than {MAX_DOCUMENT_BYTES // (1024 * 1024)} MB.")
        digest = hashlib.sha256(raw).hexdigest()
        previous = next((item for item in self.data["documents"] if item["path"] == str(path)), None)
        # Re-opening the same unchanged BG selection must not repeat local PDF
        # extraction, OCR or DFC preparation.  The document record already
        # carries those local artefacts and is safe to reuse by content hash.
        if previous and previous.get("sha256") == digest and previous.get("label_version") == LABEL_VERSION:
            previous["material_role"] = material_role(path)
            previous["index_cache_status"] = "reused"
            self._save()
            return previous
        chunks = self._extract(path)
        if not chunks:
            raise ValueError("No extractable text was found in this file.")
        document = {
            "id": previous["id"] if previous else hashlib.sha256(str(path).encode()).hexdigest()[:8],
            "name": path.name,
            "path": str(path),
            "sha256": digest,
            "bytes": len(raw),
            "indexed_at": _now(),
            "chunks": chunks[:MAX_CHUNKS_PER_DOCUMENT],
            "material_role": material_role(path),
            "index_cache_status": "new" if previous is None else "changed",
            "label_version": LABEL_VERSION,
        }
        if path.suffix.lower() == ".pdf":
            document["page_inventory"] = self.pdf_page_inventory(path)
        elif path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            document["image_type"] = self.image_type(path)
            if document["image_type"] == "dfc_structure_screenshot":
                document["dfc_structure"] = self.dfc_segment_manifest(path)
        self.data["documents"] = [item for item in self.data["documents"] if item["path"] != str(path)]
        self.data["documents"].append(document)
        self._save()
        return document

    def add_folder(self, value: str):
        """Index supported files below a Baugruppe directory, deterministically."""
        folder = Path(value.strip().strip('"')).expanduser().resolve()
        if not folder.is_dir():
            raise ValueError(f"Folder does not exist: {folder}")
        added, skipped = [], []
        for path in sorted(folder.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_DOCUMENT_EXTENSIONS:
                continue
            try:
                added.append(self.add(str(path)))
            except Exception as exc:
                skipped.append(f"{path.name}: {exc}")
        if not added:
            raise ValueError("No supported, extractable files were found in this folder.")
        return added, skipped

    def list(self):
        return self.data["documents"]

    @staticmethod
    def pdf_page_inventory(path: Path) -> builtins.list[dict]:
        """Cheap local inventory; it never renders pages or calls OCR/LLM."""
        try:
            import fitz
            records: builtins.list[dict] = []
            with fitz.open(path) as document:
                for number, page in enumerate(document, start=1):
                    chars, images = len(page.get_text("text").strip()), len(page.get_images(full=True))
                    kind = "visual" if chars < 40 else ("mixed" if images or chars < 260 else "text")
                    records.append({"page": number, "native_chars": chars, "page_type": kind,
                                    "embedded_image_count": images, "ocr_status": "not_requested"})
            return records
        except Exception:
            return []

    def ensure_ocr_for_snippets(self, snippets: builtins.list[dict], question: str = "", classification: bool = False) -> builtins.list[dict]:
        """OCR selected visual PDF pages and DFC image segments locally.

        DFC OCR is deliberately segment-aware: its text remains tied to the
        exact image crop that will be shown to the model, rather than becoming
        an untraceable flattened list of component names.
        """
        changed = False
        by_path = {item.get("path"): item for item in self.data["documents"]}
        cache_dir = self.path.parent / "pdf_ocr_cache"
        for snippet in snippets:
            visual = snippet.get("visual") or {}
            document = by_path.get(str(visual.get("path", "")))
            if visual.get("kind") == "dfc_structure_screenshot":
                if not document:
                    continue
                manifest = document.get("dfc_structure")
                if not isinstance(manifest, dict):
                    manifest = self.dfc_segment_manifest(Path(document["path"]))
                    document["dfc_structure"] = manifest
                    changed = True
                segments = manifest.get("segments", []) if isinstance(manifest, dict) else []
                for segment in segments:
                    if segment.get("ocr_status") not in {None, "not_requested"}:
                        continue
                    text, status = self._ocr_page_image(Path(segment["path"]))
                    segment["ocr_text"], segment["ocr_status"] = text, status
                    changed = True
                selected = self._select_dfc_segments(segments, question, classification)
                ocr_parts = []
                for segment in selected:
                    text = str(segment.get("ocr_text", "")).strip()
                    if text:
                        ocr_parts.append(f"[DFC Struktur, Abschnitt {segment.get('part')}]\n{text}")
                if ocr_parts and "[DFC Struktur OCR]" not in snippet.get("text", ""):
                    snippet["text"] += "\n\n[DFC Struktur OCR]\n" + "\n\n".join(ocr_parts)
                visual["dfc_segment_count"] = len(segments)
                visual["dfc_segments"] = [
                    {key: segment.get(key) for key in ("part", "path", "top_px", "bottom_px", "ocr_status")}
                    for segment in selected
                ]
                visual["dfc_ocr_status"] = self.