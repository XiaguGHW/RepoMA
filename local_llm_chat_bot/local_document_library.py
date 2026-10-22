"""Local text extraction and lexical retrieval for terminal document chat."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

SUPPORTED_DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".xlsm", ".csv", ".txt", ".md", ".png", ".jpg", ".jpeg", ".webp"}
# The original 25 MB ceiling made a normal multi-page drawing package unusable.
# This remains a local index: files are never copied to the model merely because
# they are added.  Only retrieved text and a few selected visual pages are sent.
MAX_DOCUMENT_BYTES = 80 * 1024 * 1024
MAX_CHUNK_CHARS = 3500
MAX_CHUNKS_PER_DOCUMENT = 900
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
                if isinstance(data.get("documents"), list):
                    return data
            except (OSError, json.JSONDecodeError):
                pass
        return {"version": 1, "documents": []}

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def add(self, value: str):
        path = Path(value.strip().strip('"')).expanduser().resolve()
        if not path.is_file():
            raise ValueError(f"File does not exist: {path}")
        if path.suffix.lower() not in SUPPORTED_DOCUMENT_EXTENSIONS:
            allowed = ", ".join(sorted(SUPPORTED_DOCUMENT_EXTENSIONS))
            raise ValueError(f"Unsupported file type {path.suffix or '(none)'}. Supported: {allowed}")
        raw = path.read_bytes()
        if len(raw) > MAX_DOCUMENT_BYTES:
            raise ValueError(f"File is larger than {MAX_DOCUMENT_BYTES // (1024 * 1024)} MB.")
        digest = hashlib.sha256(raw).hexdigest()
        chunks = self._extract(path)
        if not chunks:
            raise ValueError("No extractable text was found in this file.")
        previous = next((item for item in self.data["documents"] if item["path"] == str(path)), None)
        document = {
            "id": previous["id"] if previous else hashlib.sha256(str(path).encode()).hexdigest()[:8],
            "name": path.name,
            "path": str(path),
            "sha256": digest,
            "bytes": len(raw),
            "indexed_at": _now(),
            "chunks": chunks[:MAX_CHUNKS_PER_DOCUMENT],
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
    def pdf_page_inventory(path: Path) -> list[dict]:
        """Cheap local inventory; it never renders pages or calls OCR/LLM."""
        try:
            import fitz
            records = []
            with fitz.open(path) as document:
                for number, page in enumerate(document, start=1):
                    chars, images = len(page.get_text("text").strip()), len(page.get_images(full=True))
                    kind = "visual" if chars < 40 else ("mixed" if images or chars < 260 else "text")
                    records.append({"page": number, "native_chars": chars, "page_type": kind,
                                    "embedded_image_count": images, "ocr_status": "not_requested"})
            return records
        except Exception:
            return []

    def ensure_ocr_for_snippets(self, snippets: list[dict], question: str = "", classification: bool = False) -> list[dict]:
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
                    document["dfc_structure"] = manifest; changed = True
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
                visual["dfc_ocr_status"] = self._dfc_ocr_status(segments)
                continue
            if visual.get("kind") != "pdf_page":
                continue
            page_number = visual.get("page")
            if not document or not isinstance(page_number, int):
                continue
            if not document.get("page_inventory"):
                document["page_inventory"] = self.pdf_page_inventory(Path(document["path"]))
                changed = True
            record = next((item for item in document.get("page_inventory", []) if item.get("page") == page_number), {})
            if record.get("page_type") == "text" or record.get("ocr_status") not in {"not_requested", None}:
                if record.get("ocr_text"):
                    snippet["text"] += "\n\n[Local OCR]\n" + record["ocr_text"]
                continue
            try:
                image = self._render_pdf_page(Path(document["path"]), page_number, cache_dir)
                text, status = self._ocr_page_image(image)
                record["ocr_status"], record["ocr_text"] = status, text
                if text:
                    snippet["text"] += "\n\n[Local OCR]\n" + text
                    for chunk in document.get("chunks", []):
                        chunk_visual = chunk.get("visual") or {}
                        if chunk_visual.get("kind") == "pdf_page" and chunk_visual.get("page") == page_number and "[Local OCR]" not in chunk.get("text", ""):
                            chunk["text"] += "\n\n[Local OCR]\n" + text
                changed = True
            except Exception as exc:
                record["ocr_status"] = f"unavailable: {str(exc)[:120]}"; changed = True
        if changed:
            self._save()
        return snippets

    def ensure_document_ocr(self, document: dict) -> None:
        """Prepare every visual/mixed page locally for an exhaustive reading pass."""
        snippets = [{"text": "", "visual": chunk.get("visual")} for chunk in document.get("chunks", [])
                    if (chunk.get("visual") or {}).get("kind") in {"pdf_page", "dfc_structure_screenshot"}]
        self.ensure_ocr_for_snippets(snippets, classification=True)

    def bilder_image_paths(self, allowed_ids=None) -> list[Path]:
        """Return explicitly selected CAD screenshots from direct Bilder folders."""
        allowed = set(allowed_ids or [])
        paths = []
        for document in self.data["documents"]:
            if allowed and document.get("id") not in allowed:
                continue
            path = Path(document.get("path", ""))
            if (path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"} and path.parent.name.casefold() == "bilder"
                    and document.get("image_type") != "dfc_structure_screenshot" and path.is_file()):
                paths.append(path)
        return sorted(set(paths), key=lambda item: item.name.casefold())

    @staticmethod
    def image_type(path: Path) -> str:
        """Classify the important DFC hierarchy screenshots before CAD views.

        The rule deliberately requires a DFC/structure signal instead of
        treating every file named "structure" as DFC material.  It also keeps
        common historic spellings from manually exported Teamcenter files.
        """
        text = " ".join(part.casefold() for part in path.parts)
        compact = re.sub(r"[^a-z0-9]+", "", text)
        structure_terms = ("struktur", "strucktur", "structure", "strukturbaum", "baugruppenstruktur")
        has_dfc = "dfc" in compact
        has_structure = any(term in text or term in compact for term in structure_terms)
        if (has_dfc and has_structure) or "strukturbaum" in compact or "baugruppenstruktur" in compact:
            return "dfc_structure_screenshot"
        return "image"

    def dfc_segment_manifest(self, source: Path) -> dict:
        """Create deterministic overlapping crops for a tall DFC screenshot.

        These are local reusable derivatives only.  They are *not* uploaded or
        OCRed by this change; that comes in the subsequent DFC reading step.
        """
        try:
            from PIL import Image
            with Image.open(source) as image:
                image.load()
                width, height = image.size
        except Exception as exc:
            return {"status": f"unavailable: {str(exc)[:120]}", "segments": []}

        is_long = height >= DFC_LONG_IMAGE_MIN_HEIGHT and height / max(width, 1) >= DFC_LONG_IMAGE_MIN_ASPECT
        manifest = {
            "status": "not_needed" if not is_long else "ready",
            "width": width,
            "height": height,
            "overlap_px": DFC_SEGMENT_OVERLAP if is_long else 0,
            "segments": [],
        }
        if not is_long:
            return manifest

        cache_dir = self.path.parent / "dfc_structure_segments"
        key = hashlib.sha256(f"{source}|{source.stat().st_mtime_ns}|{width}x{height}".encode()).hexdigest()[:16]
        segment_height = max(DFC_SEGMENT_MIN_HEIGHT, min(DFC_SEGMENT_MAX_HEIGHT, width * 2))
        step = max(1, segment_height - DFC_SEGMENT_OVERLAP)
        starts = list(range(0, max(1, height - segment_height + 1), step))
        last_start = max(0, height - segment_height)
        if not starts or starts[-1] != last_start:
            starts.append(last_start)

        try:
            with Image.open(source) as image:
                image.load()
                for number, top in enumerate(starts, start=1):
                    bottom = min(height, top + segment_height)
                    target = cache_dir / f"dfc_{key}_part_{number:02d}.jpg"
                    if not target.exists():
                        crop = image.crop((0, top, width, bottom))
                        # This is a local reading cache, so preserve more
                        # detail than the conservative upload-safe copies.
                        self._save_image_jpeg(crop, target, max_bytes=1_400_000, max_edge=3000)
                    manifest["segments"].append({
                        "part": number,
                        "top_px": top,
                        "bottom_px": bottom,
                        "path": str(target),
                    })
        except Exception as exc:
            manifest["status"] = f"unavailable: {str(exc)[:120]}"
            manifest["segments"] = []
        return manifest

    @staticmethod
    def dfc_audit(document: dict) -> dict | None:
        """Small serialisable audit record; never exposes the cached OCR text."""
        manifest = document.get("dfc_structure")
        if document.get("image_type") != "dfc_structure_screenshot" or not isinstance(manifest, dict):
            return None
        segments = manifest.get("segments", [])
        return {
            "type": "DFC Struktur",
            "status": manifest.get("status", "unknown"),
            "segments_total": len(segments),
            "ocr_status": LocalDocumentLibrary._dfc_ocr_status(segments),
            "ocr_ready_segments": [item.get("part") for item in segments if item.get("ocr_status") == "ok"],
            "ocr_failed_segments": [item.get("part") for item in segments if item.get("ocr_status") not in {"ok", None, "not_requested"}],
        }

    @staticmethod
    def _dfc_ocr_status(segments: list[dict]) -> str:
        if not segments:
            return "not_needed"
        statuses = [str(item.get("ocr_status", "not_requested")) for item in segments]
        if all(status == "ok" for status in statuses):
            return "ok"
        if any(status == "ok" for status in statuses):
            return "partial"
        return statuses[0]

    @staticmethod
    def _select_dfc_segments(segments: list[dict], question: str, classification: bool) -> list[dict]:
        """Choose OCR-matched crops, with deterministic whole-structure fallback."""
        if len(segments) <= MAX_DFC_SEGMENTS_PER_REQUEST:
            return list(segments)
        terms = _expanded_tokens(question)
        ranked = []
        for segment in segments:
            text = str(segment.get("ocr_text", "")).casefold()
            score = sum(1 for term in terms if term in text)
            ranked.append((score, int(segment.get("part", 0)), segment))
        matched = [item for item in ranked if item[0] > 0]
        if matched:
            return [item[2] for item in sorted(matched, key=lambda item: (-item[0], item[1]))[:MAX_DFC_SEGMENTS_PER_REQUEST]]
        # A first classification should see the full hierarchy from top to
        # bottom, even when the Chinese question has no lexical OCR match.
        indexes = {round(index * (len(segments) - 1) / (MAX_DFC_SEGMENTS_PER_REQUEST - 1))
                   for index in range(MAX_DFC_SEGMENTS_PER_REQUEST)}
        return [segment for index, segment in enumerate(segments) if index in indexes]

    def remove(self, document_id: str):
        before = len(self.data["documents"])
        self.data["documents"] = [item for item in self.data["documents"] if item["id"] != document_id]
        if len(self.data["documents"]) == before:
            return False
        self._save()
        return True

    def clear(self):
        count = len(self.data["documents"])
        self.data["documents"] = []
        self._save()
        return count

    def search(self, question: str, limit: int = 6, preferred_ids=None, classification=False, allowed_ids=None):
        """Return local evidence. Preferred documents are kept in the result.

        Chinese questions and German technical material rarely share literal
        words.  In classification mode we therefore also return a compact,
        diverse baseline from the selected Codebook/BG sources instead of
        silently returning only page one.
        """
        words = _expanded_tokens(question)
        chars = set(re.findall(r"[\u4e00-\u9fff]", question.lower()))
        allowed = set(allowed_ids or [])
        documents = [item for item in self.data["documents"] if not allowed or item["id"] in allowed]
        scored = []
        for document in documents:
            for index, chunk in enumerate(document.get("chunks", [])):
                text = chunk["text"].lower()
                word_score = sum(1 for word in words if word in text)
                char_score = min(8, len(chars & set(re.findall(r"[\u4e00-\u9fff]", text))))
                score = word_score * 10 + char_score
                if score:
                    scored.append((score, document, index, chunk))
        scored.sort(key=lambda item: (-item[0], item[1]["name"], item[2]))
        preferred = set(preferred_ids or [])
        selected, used = [], set()
        # First keep best lexical hits, but reserve room for each pinned source.
        for item in scored:
            key = (item[1]["id"], item[2])
            if key not in used:
                selected.append(item); used.add(key)
            if len(selected) >= limit:
                break
        if classification and preferred:
            # A Codebook or a visual-only DFC has no matching words for a
            # Chinese question. Include one representative chunk per source.
            for document in documents:
                if document["id"] not in preferred or not document.get("chunks"):
                    continue
                candidates = [(score, doc, index, chunk) for score, doc, index, chunk in scored if doc["id"] == document["id"]]
                item = candidates[0] if candidates else (0, document, 0, document["chunks"][0])
                key = (item[1]["id"], item[2])
                if key not in used:
                    selected.append(item); used.add(key)
        if not selected and documents:
            for document in documents[:2]:
                if document.get("chunks"):
                    selected.append((0, document, 0, document["chunks"][0]))
        if selected and not classification:
            # A page in isolation is a frequent source of wrong technical
            # answers. Keep its immediate local context before taking more
            # distant keyword hits.
            contextual, contextual_used = [], set()
            for _score, document, index, _chunk in selected[:3]:
                for neighbour in range(max(0, index - 1), min(len(document.get("chunks", [])), index + 2)):
                    key = (document["id"], neighbour)
                    if key not in contextual_used:
                        contextual.append((_score if neighbour == index else max(0, _score - 1), document, neighbour, document["chunks"][neighbour]))
                        contextual_used.add(key)
            selected = contextual + [item for item in selected if (item[1]["id"], item[2]) not in contextual_used]
        # Classification favours coverage; normal chat retains the old small context.
        result_limit = max(limit, 12) if classification and preferred else limit
        return [
            {
                "id": item[1]["id"],
                "name": item[1]["name"],
                "label": item[3]["label"],
                "text": item[3]["text"],
                "visual": item[3].get("visual"),
            }
            for item in selected[:result_limit]
        ]

    def visual_paths(self, snippets, cache_dir: Path, limit: int = MAX_VISUALS_PER_REQUEST, bilder_images=None):
        """Make upload-safe visual evidence for only the current request.

        A small-page-count technical drawing is treated differently from a long
        datasheet: every sheet is represented, while no original PDF is ever
        attached.  JPEGs are compressed independently and as a group so a
        visually dense 20 MB drawing cannot cause an HTTP payload failure.
        """
        cache_dir.mkdir(parents=True, exist_ok=True)
        paths, seen, used_bytes, skipped = [], set(), 0, []
        grouped_image_sources = {Path(item) for item in (bilder_images or []) if Path(item).is_file()}
        image_group_reports, title_blocks, dfc_reports = [], [], []
        short_pdfs: list[Path] = []
        for snippet in snippets:
            visual = snippet.get("visual") or {}
            source = Path(visual.get("path", ""))
            # A short Codebook is reference material, not a technical drawing.
            # Keep its retrieved page available below, but reserve the full-page
            # treatment for the BG material that carries the visual geometry.
            if (visual.get("kind") == "pdf_page" and source.is_file() and source not in short_pdfs
                    and "codebook" not in source.name.casefold()):
                try:
                    if self._pdf_page_count(source) <= MAX_SHORT_PDF_PAGES:
                        short_pdfs.append(source)
                except Exception:
                    pass

        def attach(output: Path | None, description: str) -> bool:
            nonlocal used_bytes
            if not output or not output.is_file():
                skipped.append(f"{description} 无法转换")
                return False
            size = output.stat().st_size
            if len(paths) >= limit or used_bytes + size > MAX_VISUAL_BYTES_PER_REQUEST:
                skipped.append(f"{description} 超出本轮视觉附件预算")
                return False
            paths.append(str(output)); used_bytes += size
            return True

        # DFC is a priority-1 structural source, not another CAD screenshot.
        # Attach its selected original-image crops before visual overviews use
        # the request budget.  OCR text for the same numbered crops is already
        # part of the textual evidence supplied to the model.
        dfc_seen = set()
        for snippet in snippets:
            visual = snippet.get("visual") or {}
            if visual.get("kind") != "dfc_structure_screenshot":
                continue
            source = Path(visual.get("path", ""))
            key = str(source)
            if key in dfc_seen:
                continue
            dfc_seen.add(key)
            selected = visual.get("dfc_segments") or []
            attached_parts = []
            for segment in selected:
                part = segment.get("part")
                try:
                    output = self._prepare_image(Path(str(segment.get("path", ""))), cache_dir,
                                                 max_bytes=520_000, max_edge=2600)
                except Exception:
                    skipped.append(f"{source.name} DFC 第 {part} 段无法转换")
                    continue
                if attach(output, f"{source.name} DFC 第 {part} 段"):
                    attached_parts.append(part)
            dfc_reports.append({
                "name": source.name,
                "segments_total": visual.get("dfc_segment_count", len(selected)),
                "segments_used": attached_parts,
                "ocr_status": visual.get("dfc_ocr_status", "not_requested"),
            })

        # For a 1–5 page PDF, an individual retrieved page is not sufficient:
        # the title block, view, BOM and revision can be on different sheets.
        for source in short_pdfs:
            page_count = self._pdf_page_count(source)
            all_overviews_attached = True
            for page_number in range(1, page_count + 1):
                output = self._render_pdf_page(source, page_number, cache_dir)
                if not attach(output, f"{source.name} 第 {page_number} 页总览"):
                    all_overviews_attached = False
            # A readable title block is often decisive for a scanned drawing.
            # Add it only after all sheets and only if payload budget permits.
            if all_overviews_attached and page_count:
                title_blocks.append((source, self._render_pdf_title_block(source, 1, cache_dir)))

        # CAD screenshots belong together. For a larger Bilder folder, a
        # contact sheet preserves the assembly overview in one attachment and
        # a few evenly distributed originals retain readable details.
        groups = {}
        for source in grouped_image_sources:
            groups.setdefault(source.parent, []).append(source)
        for folder, sources in sorted(groups.items(), key=lambda item: str(item[0]).casefold()):
            sources = sorted(sources, key=lambda item: item.name.casefold())
            if len(sources) <= 4:
                for source in sources:
                    attach(self._prepare_image(source, cache_dir), source.name)
                image_group_reports.append(f"{folder.name}: {len(sources)} 张原图")
                continue
            sheet = self._render_contact_sheet(sources, cache_dir)
            attached_sheet = attach(sheet, f"{folder.name} 图片总览")
            details = self._evenly_spaced(sources, MAX_IMAGE_GROUP_DETAIL_VIEWS)
            details_attached = 0
            for source in details:
                if attach(self._prepare_image(source, cache_dir), source.name):
                    details_attached += 1
            if attached_sheet:
                image_group_reports.append(f"{folder.name}: {len(sources)} 张，缩略总览 + {details_attached} 张细节")

        # A title block is useful but less important than an explicitly chosen
        # screenshot group; attach it only after that group has a chance.
        for source, title_block in title_blocks:
            attach(title_block, f"{source.name} 第 1 页标题栏")

        for snippet in snippets:
            visual = snippet.get("visual") or {}
            kind = visual.get("kind")
            source = Path(visual.get("path", ""))
            key = (kind, str(source), visual.get("page"), visual.get("sheet"), visual.get("start_row"))
            if key in seen or not source.is_file() or kind == "dfc_structure_screenshot" or (kind == "pdf_page" and source in short_pdfs) or (kind == "image" and source in grouped_image_sources):
                continue
            try:
                if kind in {"image", "dfc_structure_screenshot"}:
                    output = self._prepare_image(source, cache_dir)
                elif kind == "pdf_page":
                    output = self._render_pdf_page(source, int(visual["page"]), cache_dir)
                elif kind == "excel_range":
                    output = self._prepare_image(self._render_excel_range(source, visual, cache_dir), cache_dir)
                else:
                    continue
            except Exception:
                skipped.append(f"{source.name} 转换失败")
                continue
            seen.add(key)
            attach(output, source.name)

        self.last_visual_report = {
            "attachments": len(paths), "bytes": used_bytes, "budget": MAX_VISUAL_BYTES_PER_REQUEST,
            "short_drawings": [item.name for item in short_pdfs], "image_groups": image_group_reports,
            "dfc": dfc_reports, "skipped": skipped,
        }
        return paths

    def codebook_page_records(self, value: str | Path, cache_dir: Path) -> list[dict]:
        """Build a durable, page-by-page evidence record for a PDF Codebook.

        Native PDF text is retained even when OCR is available.  OCR is a
        second reading channel for scanned/mixed pages, never a replacement
        for genuine embedded text.  A missing local Tesseract installation is
        recorded per page instead of making a long-running preparation fail.
        """
        path = Path(value).expanduser().resolve()
        if path.suffix.lower() != ".pdf":
            return []
        try:
            import fitz
        except ImportError as exc:
            raise ValueError("PDF support requires PyMuPDF.") from exc
        cache_dir.mkdir(parents=True, exist_ok=True)
        records = []
        with fitz.open(path) as document:
            for number, page in enumerate(document, start=1):
                native_text = page.get_text("text").strip()
                image_count = len(page.get_images(full=True))
                if len(native_text) < 40:
                    page_type = "visual"
                elif image_count or len(native_text) < 260:
                    page_type = "mixed"
                else:
                    page_type = "text"
                image = self._render_pdf_page(path, number, cache_dir)
                ocr_text, ocr_status = self._ocr_page_image(image)
                records.append({
                    "page": number, "page_type": page_type,
                    "native_text": native_text, "ocr_text": ocr_text,
                    "ocr_status": ocr_status, "image_path": str(image),
                    "embedded_image_count": image_count,
                })
        return records

    def ocr_runtime_status(self) -> dict[str, object]:
        """Locate a Windows Tesseract installation without requiring PATH."""
        if self._ocr_runtime_cache is not None:
            return self._ocr_runtime_cache
        try:
            import pytesseract
            candidates = [shutil.which("tesseract")]
            for root in (os.environ.get("LOCALAPPDATA"), os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
                if root:
                    candidates.append(str(Path(root) / "Programs" / "Tesseract-OCR" / "tesseract.exe"))
                    candidates.append(str(Path(root) / "Tesseract-OCR" / "tesseract.exe"))
            command = next((candidate for candidate in candidates if candidate and Path(candidate).is_file()), None)
            if not command:
                self._ocr_runtime_cache = {"available": False, "status": "Tesseract executable not found", "command": "", "languages": []}
                return self._ocr_runtime_cache
            pytesseract.pytesseract.tesseract_cmd = command
            version = str(pytesseract.get_tesseract_version())
            languages = pytesseract.get_languages(config="")
            self._ocr_runtime_cache = {"available": True, "status": "ok", "command": command,
                                       "version": version, "languages": languages,
                                       "german_available": "deu" in languages}
            return self._ocr_runtime_cache
        except ImportError:
            self._ocr_runtime_cache = {"available": False, "status": "pytesseract is not installed", "command": "", "languages": []}
            return self._ocr_runtime_cache
        except Exception as exc:
            self._ocr_runtime_cache = {"available": False, "status": str(exc)[:180], "command": "", "languages": []}
            return self._ocr_runtime_cache

    def _ocr_page_image(self, image_path: Path) -> tuple[str, str]:
        """Use the detected engine, with an explicit non-fatal page status."""
        runtime = self.ocr_runtime_status()
        if not runtime.get("available"):
            return "", "unavailable: " + str(runtime.get("status", "unknown"))
        try:
            import pytesseract
            from PIL import Image
            language = "deu+eng" if runtime.get("german_available") else "eng"
            with Image.open(image_path) as image:
                text = pytesseract.image_to_string(image, lang=language).strip()
            return text, "ok"
        except Exception as exc:
            return "", f"unavailable: {str(exc)[:180]}"

    @staticmethod
    def _evenly_spaced(items: list[Path], count: int) -> list[Path]:
        if len(items) <= count:
            return items
        indexes = {round(index * (len(items) - 1) / (count - 1)) for index in range(count)}
        return [item for index, item in enumerate(items) if index in indexes]

    @classmethod
    def _render_contact_sheet(cls, sources: list[Path], cache_dir: Path):
        from PIL import Image, ImageDraw, ImageFont, ImageOps
        identity = "|".join(f"{source}|{source.stat().st_mtime_ns}" for source in sources)
        key = hashlib.sha256(identity.encode()).hexdigest()[:14]
        target = cache_dir / f"bilder_contact_{key}.jpg"
        if target.exists() and target.stat().st_size <= MAX_VISUAL_BYTES_PER_FILE:
            return target
        columns, cell_w, cell_h, label_h, padding = 3, 430, 310, 25, 10
        rows = (len(sources) + columns - 1) // columns
        sheet = Image.new("RGB", (columns * cell_w + (columns + 1) * padding,
                                   rows * (cell_h + label_h) + (rows + 1) * padding), "white")
        draw, font = ImageDraw.Draw(sheet), ImageFont.load_default()
        for index, source in enumerate(sources):
            try:
                with Image.open(source) as image:
                    preview = ImageOps.contain(image.convert("RGB"), (cell_w, cell_h))
                    column, row = index % columns, index // columns
                    x = padding + column * (cell_w + padding) + (cell_w - preview.width) // 2
                    y = padding + row * (cell_h + label_h + padding) + (cell_h - preview.height) // 2
                    sheet.paste(preview, (x, y))
                    draw.text((padding + column * (cell_w + padding), y + cell_h + 3), source.name[:52], fill="black", font=font)
            except Exception:
                continue
        return cls._save_image_jpeg(sheet, target, max_bytes=620_000, max_edge=2000)

    def _extract(self, path: Path):
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return self._pdf(path)
        if suffix == ".docx":
            return self._docx(path)
        if suffix in {".xlsx", ".xlsm"}:
            return self._excel(path)
        if suffix == ".csv":
            return self._csv(path)
        if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
            kind = self.image_type(path)
            label_type = "DFC structure screenshot" if kind == "dfc_structure_screenshot" else "image"
            return [{"label": f"{path.name} — {label_type}", "text": f"Visual evidence: {path.name}", "visual": {"kind": kind, "path": str(path)}}]
        return _chunks(f"{path.name}", path.read_text(encoding="utf-8", errors="replace"))

    def _pdf(self, path: Path):
        try:
            import fitz
        except ImportError as exc:
            raise ValueError("PDF support requires PyMuPDF. Run: python -m pip install -r requirements.txt") from exc
        chunks = []
        with fitz.open(path) as document:
            for number, page in enumerate(document, start=1):
                extracted = page.get_text("text").strip()
                label = f"{path.name} — page {number}"
                page_chunks = _chunks(label, extracted) if extracted else [{"label": label, "text": "[Visual/scanned PDF page: no embedded text]"}]
                for chunk in page_chunks:
                    chunk["visual"] = {"kind": "pdf_page", "path": str(path), "page": number}
                chunks.extend(page_chunks)
        return chunks

    def _docx(self, path: Path):
        try:
            from docx import Document
        except ImportError as exc:
            raise ValueError("Word support requires python-docx. Run: python -m pip install -r requirements.txt") from exc
        document = Document(path)
        parts = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
        for number, table in enumerate(document.tables, start=1):
            rows = [" | ".join(str(cell.text).strip().replace("\n", " ") for cell in row.cells) for row in table.rows]
            if rows:
                parts.append(f"Table {number}:\n" + "\n".join(rows))
        return _chunks(path.name, "\n\n".join(parts))

    def _excel(self, path: Path):
        try:
            from openpyxl import load_workbook
        except ImportError as exc:
            raise ValueError("Excel support requires openpyxl. Run: python -m pip install -r requirements.txt") from exc
        workbook = load_workbook(path, read_only=True, data_only=False)
        chunks = []
        try:
            for sheet in workbook.worksheets:
                rows = []
                for number, row in enumerate(sheet.iter_rows(values_only=True), start=1):
                    if number > MAX_EXCEL_ROWS_PER_SHEET:
                        rows.append(f"[Stopped after {MAX_EXCEL_ROWS_PER_SHEET} rows]")
                        break
                    values = [str(value).replace("\n", " ")[:500] if value is not None else "" for value in row]
                    if any(values):
                        rows.append(f"Row {number}: " + " | ".join(values))
                # Keep ranges small enough that the matching rows can also be
                # rendered as a visual table for the model when needed.
                for start in range(0, len(rows), 80):
                    end = min(len(rows), start + 80)
                    label = f"{path.name} — sheet {sheet.title}, rows {start + 1}-{end}"
                    range_chunks = _chunks(label, "\n".join(rows[start:end]))
                    for chunk in range_chunks:
                        chunk["visual"] = {"kind": "excel_range", "path": str(path), "sheet": sheet.title, "start_row": start + 1, "end_row": end}
                    chunks.extend(range_chunks)
        finally:
            workbook.close()
        return chunks

    def _csv(self, path: Path):
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        rows = []
        for number, row in enumerate(csv.reader(text.splitlines()), start=1):
            if number > MAX_EXCEL_ROWS_PER_SHEET:
                rows.append(f"[Stopped after {MAX_EXCEL_ROWS_PER_SHEET} rows]")
                break
            rows.append(f"Row {number}: " + " | ".join(cell[:500] for cell in row))
        return _chunks(path.name, "\n".join(rows))

    @staticmethod
    def _pdf_page_count(path: Path) -> int:
        import fitz
        with fitz.open(path) as document:
            return len(document)

    @classmethod
    def _render_pdf_page(cls, path: Path, page_number: int, cache_dir: Path):
        import fitz
        key = hashlib.sha256(f"{path}|{path.stat().st_mtime_ns}".encode()).hexdigest()[:10]
        with fitz.open(path) as document:
            page = document[page_number - 1]
            scale = min(180 / 72, 2200 / max(page.rect.width, page.rect.height))
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        return cls._save_safe_jpeg(pix, cache_dir / f"{key}_p{page_number}_overview.jpg")

    @classmethod
    def _render_pdf_title_block(cls, path: Path, page_number: int, cache_dir: Path):
        """Render the usual lower-right title-block area separately at legible size."""
        import fitz
        key = hashlib.sha256(f"{path}|{path.stat().st_mtime_ns}".encode()).hexdigest()[:10]
        with fitz.open(path) as document:
            page = document[page_number - 1]
            rect = page.rect
            clip = fitz.Rect(rect.x0 + rect.width * .55, rect.y0 + rect.height * .66, rect.x1, rect.y1)
            scale = min(250 / 72, 1900 / max(clip.width, clip.height))
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=clip, alpha=False)
        return cls._save_safe_jpeg(pix, cache_dir / f"{key}_p{page_number}_title_block.jpg", max_bytes=420_000, max_edge=1700)

    @classmethod
    def _prepare_image(cls, source: Path, cache_dir: Path, max_bytes=MAX_VISUAL_BYTES_PER_FILE, max_edge=2000):
        key = hashlib.sha256(f"{source}|{source.stat().st_mtime_ns}|{max_bytes}|{max_edge}".encode()).hexdigest()[:12]
        target = cache_dir / f"image_{key}.jpg"
        if target.exists() and target.stat().st_size <= max_bytes:
            return target
        from PIL import Image
        with Image.open(source) as image:
            image.load()
            return cls._save_image_jpeg(image, target, max_bytes=max_bytes, max_edge=max_edge)

    @classmethod
    def _save_safe_jpeg(cls, pix, target: Path, max_bytes=MAX_VISUAL_BYTES_PER_FILE, max_edge=2000):
        if target.exists() and target.stat().st_size <= max_bytes:
            return target
        from PIL import Image
        with Image.open(io.BytesIO(pix.tobytes("png"))) as image:
            image.load()
            return cls._save_image_jpeg(image, target, max_bytes=max_bytes, max_edge=max_edge)

    @staticmethod
    def _save_image_jpeg(image, target: Path, max_bytes=MAX_VISUAL_BYTES_PER_FILE, max_edge=2000):
        """Bound both resolution and bytes; return None if an upload-safe copy fails."""
        target.parent.mkdir(parents=True, exist_ok=True)
        rgb = image.convert("RGB")
        for edge in (max_edge, 1700, 1450, 1200, 1000, 850):
            for quality in (84, 74, 64, 54):
                candidate = rgb.copy()
                candidate.thumbnail((edge, edge))
                candidate.save(target, "JPEG", quality=quality, optimize=True, progressive=True)
                if target.stat().st_size <= max_bytes:
                    return target
        target.unlink(missing_ok=True)
        return None

    @staticmethod
    def _render_excel_range(path: Path, visual: dict, cache_dir: Path):
        from openpyxl import load_workbook
        from PIL import Image, ImageDraw, ImageFont
        sheet_name = visual["sheet"]; start = int(visual["start_row"]); end = int(visual["end_row"])
        key = hashlib.sha256(f"{path}|{sheet_name}|{start}|{end}".encode()).hexdigest()[:12]
        target = cache_dir / f"excel_{key}.png"
        if target.exists():
            return target
        workbook = load_workbook(path, read_only=True, data_only=False)
        try:
            sheet = workbook[sheet_name]
            values = []
            for row in sheet.iter_rows(min_row=start, max_row=end, values_only=True):
                values.append([str(value or "").replace("\n", " ")[:36] for value in row[:12]])
        finally:
            workbook.close()
        font = ImageFont.load_default(); cell_w, cell_h = 130, 22
        columns = max(1, max((len(row) for row in values), default=1))
        image = Image.new("RGB", (columns * cell_w + 20, (len(values) + 2) * cell_h + 20), "white")
        draw = ImageDraw.Draw(image)
        draw.text((8, 4), f"{path.name} | {sheet_name} | rows {start}-{end}", fill="black", font=font)
        for r, row in enumerate(values):
            for c in range(columns):
                x, y = 8 + c * cell_w, 24 + r * cell_h
                draw.rectangle((x, y, x + cell_w, y + cell_h), outline="#808080")
                draw.text((x + 3, y + 4), row[c] if c < len(row) else "", fill="black", font=font)
        image.save(target)
        return target
