"""Local text extraction and lexical retrieval for terminal document chat."""
from __future__ import annotations

import csv
import hashlib
import json
import re
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


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _tokens(text):
    return re.findall(r"[A-Za-z_][A-Za-z0-9_]{1,}|[\u4e00-\u9fff]{2,}|\d{2,}", text.lower())


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
        words = set(_tokens(question))
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

    def visual_paths(self, snippets, cache_dir: Path, limit: int = MAX_VISUALS_PER_REQUEST):
        """Materialise a few cited visual sources only for the current request."""
        cache_dir.mkdir(parents=True, exist_ok=True)
        paths, seen = [], set()
        for snippet in snippets:
            visual = snippet.get("visual") or {}
            kind = visual.get("kind")
            source = Path(visual.get("path", ""))
            key = (kind, str(source), visual.get("page"), visual.get("sheet"), visual.get("start_row"))
            if key in seen or not source.is_file():
                continue
            try:
                if kind == "image":
                    output = source
                elif kind == "pdf_page":
                    output = self._render_pdf_page(source, int(visual["page"]), cache_dir)
                elif kind == "excel_range":
                    output = self._render_excel_range(source, visual, cache_dir)
                else:
                    continue
            except Exception:
                continue
            seen.add(key); paths.append(str(output))
            if len(paths) >= limit:
                break
        return paths

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
            return [{"label": f"{path.name} — image", "text": f"Visual evidence: {path.name}", "visual": {"kind": "image", "path": str(path)}}]
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
    def _render_pdf_page(path: Path, page_number: int, cache_dir: Path):
        import fitz
        target = cache_dir / f"{hashlib.sha256(str(path).encode()).hexdigest()[:10]}_p{page_number}.jpg"
        if target.exists():
            return target
        with fitz.open(path) as document:
            pix = document[page_number - 1].get_pixmap(matrix=fitz.Matrix(160 / 72, 160 / 72), alpha=False)
            pix.save(target)
        return target

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
