#!/usr/bin/env python3
"""Extract source-traceable facts for the text-only LLM experiment.

Input is the ``file_inventory_classified_*.xlsx`` produced by
``classify_bg_files_text_only.py``.  This script never predicts a Funktionsklasse.  It
processes PDFs page-by-page in deterministic chunks, Excel/CSV files by row
chunks and images one by one, then writes raw fact records per Baugruppe.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

try:
    import fitz
except ImportError:
    fitz = None
try:
    from PIL import Image
except ImportError:
    Image = None
try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args: Any, **_kwargs: Any) -> bool:
        return False


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent if SCRIPT_DIR.name.casefold() == "scripts" else SCRIPT_DIR
EXCEL_EXTENSIONS = {".xlsx", ".xls", ".csv"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
PROCESSABLE_TYPES = {
    "assembly_drawing", "bom", "component_datasheet", "assembly_structure_or_dfc",
    "cad_screenshot_or_visual_context", "other_technical_document",
}

SYSTEM_PROMPT = """Du extrahierst belegbare technische Fakten aus genau einem
Dokumentausschnitt einer Baugruppe. Du darfst KEINE Funktionsklasse der Baugruppe
ableiten, keine Informationen ergänzen und keine Schlussfolgerung aus fehlenden
Informationen ziehen. Jede Tatsache muss ausdrücklich im Text oder Bild dieses
Ausschnitts erkennbar sein. Antworte ausschließlich als JSON."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory-excel", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_DIR / "outputs" / "text_only_preprocessing")
    parser.add_argument("--model", default="gemini-2.5-pro")
    parser.add_argument("--max-bgs", type=int, default=None, help="Process first N BG folders in inventory order.")
    parser.add_argument("--pdf-pages-per-chunk", type=int, default=2)
    parser.add_argument("--excel-rows-per-chunk", type=int, default=150)
    parser.add_argument("--max-text-chars", type=int, default=12000)
    parser.add_argument("--image-max-px", type=int, default=1600)
    parser.add_argument(
        "--max-attachment-mb", type=float, default=1.0,
        help="Maximum size of each rendered/converted image attachment in MiB.",
    )
    parser.add_argument(
        "--attach-pdf-visuals", action="store_true",
        help="Also attach rendered PDF pages when native text exists; useful for drawings/DFC PDFs.",
    )
    parser.add_argument("--include-other", action="store_true")
    parser.add_argument("--retries", type=int, default=1)
    return parser.parse_args()


def safe_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text)


def clean_text(text: str, limit: int) -> str:
    return re.sub(r"\s+", " ", text).strip()[:limit]


def extract_json(raw: str) -> dict[str, Any] | None:
    raw = str(raw).strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL | re.IGNORECASE)
    candidates = [match.group(1)] if match else []
    first, last = raw.find("{"), raw.rfind("}")
    if first >= 0 and last > first:
        candidates.append(raw[first:last + 1])
    for candidate in candidates:
        try:
            result = json.loads(candidate)
            return result if isinstance(result, dict) else None
        except json.JSONDecodeError:
            pass
    return None


def create_connector(model: str, api_key: str):
    try:
        from llm_connector import LLMConnector
    except ImportError as error:
        raise ImportError("Place the actual Bosch llm_connector.py next to this script.") from error
    return LLMConnector(model, api_key)


def effective_type(row: pd.Series) -> str:
    manual = str(row.get("Manual_Type", "") or "").strip().casefold()
    primary = str(row.get("Primary_Type", "") or "").strip().casefold()
    return manual or primary


def source_path(row: pd.Series) -> Path:
    return Path(str(row["Data_Folder_Path"])).expanduser() / Path(str(row["Relative_Path"]))


def is_duplicate_derivative(row: pd.Series) -> bool:
    """Defensively exclude rows from inventories created before duplicate filtering."""
    relative_path = Path(str(row["Relative_Path"]))
    in_converted_directory = any(
        part.casefold().startswith("converted") for part in relative_path.parts[:-1]
    )
    is_visual_context_pdf = (
        relative_path.suffix.casefold() == ".pdf"
        and "_visual_context" in relative_path.stem.casefold()
    )
    return in_converted_directory or is_visual_context_pdf


def render_page_image(pdf_path: Path, page_number: int, target: Path, max_px: int) -> Path:
    if fitz is None:
        raise ImportError("PyMuPDF is required for PDF page processing.")
    document = fitz.open(pdf_path)
    page = document[page_number - 1]
    scale = min(max_px / max(page.rect.width, page.rect.height), 2.0)
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    target.parent.mkdir(parents=True, exist_ok=True)
    pix.save(target)
    document.close()
    return target


def image_attachment(image_path: Path, cache_dir: Path, max_px: int, max_attachment_mb: float) -> Path | None:
    """Return an upload-safe image, or None when no safe preview can be made."""
    byte_limit = int(max_attachment_mb * 1024 * 1024)
    if Image is None:
        return image_path if image_path.stat().st_size <= byte_limit else None
    try:
        with Image.open(image_path) as image:
            if max(image.size) <= max_px and image_path.stat().st_size <= byte_limit:
                return image_path
            base_image = image.convert("RGB")
            digest = hashlib.sha256(
                f"{image_path}:{max_px}:{max_attachment_mb}".encode("utf-8")
            ).hexdigest()[:16]
            for edge in (max_px, int(max_px * 0.75), int(max_px * 0.5)):
                for quality in (88, 76, 64, 52):
                    output = cache_dir / f"{digest}_{edge}_{quality}.jpg"
                    if output.exists() and output.stat().st_size <= byte_limit:
                        return output
                    preview = base_image.copy()
                    preview.thumbnail((edge, edge))
                    output.parent.mkdir(parents=True, exist_ok=True)
                    preview.save(output, "JPEG", quality=quality, optimize=True)
                    if output.stat().st_size <= byte_limit:
                        return output
    except Exception as error:
        logging.warning("Could not prepare image attachment %s: %s", image_path, error)
    return None


def pdf_chunks(path: Path, cache_dir: Path, args: argparse.Namespace) -> list[dict[str, Any]]:
    if fitz is None:
        raise ImportError("PyMuPDF is required for PDF page processing.")
    document = fitz.open(path)
    chunks = []
    for start in range(0, len(document), args.pdf_pages_per_chunk):
        end = min(start + args.pdf_pages_per_chunk, len(document))
        pages = list(range(start + 1, end + 1))
        page_texts = [clean_text(document[p - 1].get_text("text"), args.max_text_chars) for p in pages]
        text = "\n".join(f"[Page {page}] {content}" for page, content in zip(pages, page_texts) if content)
        # Drawings/DFC documents need visual evidence even when vector text exists.
        attachments: list[str] = []
        if not text or args.attach_pdf_visuals:
            digest = hashlib.sha256(f"{path}:{start}".encode("utf-8")).hexdigest()[:16]
            for page in pages:
                image_path = cache_dir / "pdf_pages" / f"{digest}_page_{page}.jpg"
                if not image_path.exists():
                    render_page_image(path, page, image_path, args.image_max_px)
                attachment = image_attachment(
                    image_path,
                    cache_dir / "pdf_upload_safe",
                    args.image_max_px,
                    args.max_attachment_mb,
                )
                if attachment:
                    attachments.append(str(attachment))
        chunks.append({"location": f"pages {pages[0]}-{pages[-1]}", "text": text[:args.max_text_chars], "attachments": attachments})
    document.close()
    return chunks


def excel_chunks(path: Path, args: argparse.Namespace) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    if path.suffix.casefold() == ".csv":
        sheets = [("CSV", pd.read_csv(path, dtype=str, encoding_errors="replace"))]
    else:
        workbook = pd.ExcelFile(path)
        sheets = [(name, pd.read_excel(path, sheet_name=name, dtype=str)) for name in workbook.sheet_names]
    for sheet, frame in sheets:
        frame = frame.fillna("")
        for start in range(0, len(frame), args.excel_rows_per_chunk):
            part = frame.iloc[start:start + args.excel_rows_per_chunk]
            chunks.append({
                "location": f"sheet '{sheet}', data rows {start + 1}-{start + len(part)}",
                "text": clean_text(part.to_csv(index=False), args.max_text_chars),
                "attachments": [],
            })
    return chunks or [{"location": "empty workbook", "text": "", "attachments": []}]


def document_chunks(path: Path, doc_type: str, cache_dir: Path, args: argparse.Namespace) -> list[dict[str, Any]]:
    extension = path.suffix.casefold()
    if extension == ".pdf":
        return pdf_chunks(path, cache_dir, args)
    if extension in EXCEL_EXTENSIONS:
        return excel_chunks(path, args)
    if extension in IMAGE_EXTENSIONS:
        attachment = image_attachment(path, cache_dir / "images", args.image_max_px, args.max_attachment_mb)
        return [{"location": "image", "text": "", "attachments": [str(attachment)] if attachment else []}]
    raise ValueError(f"Unsupported extension: {extension}")


def fact_prompt(doc_type: str, relative_path: str, location: str, text: str) -> str:
    focus = {
        "bom": "Teilenummern, Benennungen, Mengen, Positionen und explizite Hierarchieangaben.",
        "assembly_drawing": "Zeichnungsnummer, Revision, Ansichten, explizite Hinweise, Positionsreferenzen sowie ausdrücklich benannte Bewegungs-/Maßangaben.",
        "component_datasheet": "Hersteller, Modell/Teilenummer, Komponentenbeschreibung und ausdrücklich angegebene technische Parameter mit Einheit.",
        "assembly_structure_or_dfc": "sichtbare Komponenten-/Unterbaugruppennamen und explizite Eltern-Kind-, Struktur- oder Verbindungsbeziehungen.",
        "cad_screenshot_or_visual_context": "nur klar sichtbare Bauteile, Anordnungen oder Beschriftungen; keine Funktionsinterpretation.",
        "other_technical_document": "nur ausdrücklich dokumentierte technisch relevante Fakten.",
    }[doc_type]
    return f"""Dokumentrolle: {doc_type}
Datei: {relative_path}
Quellabschnitt: {location}

Extrahiere nur: {focus}
Lokaler Text des Abschnitts:
{text or '[Kein lokaler Text; nutze nur die beigefügten Seiten/Bilder.]'}

Return exactly this JSON object:
{{
  "facts": [
    {{"fact_type": "short category", "fact": "explicit fact", "source_location": "{location}"}}
  ],
  "missing_or_uncertain": ["only limitations visible in this chunk"]
}}
"""


def call_chunk(llm: Any, doc_type: str, relative_path: str, chunk: dict[str, Any], args: argparse.Namespace) -> tuple[dict[str, Any] | None, str]:
    response = ""
    for _attempt in range(args.retries + 1):
        response = llm.ask_about_files(
            file_paths=chunk["attachments"],
            question=fact_prompt(doc_type, relative_path, chunk["location"], chunk["text"]),
            system_prompt=SYSTEM_PROMPT,
            generation_config={"temperature": 0.0, "topP": 0.95, "candidateCount": 1, "maxOutputTokens": 1400},
        )
        parsed = extract_json(str(response))
        if parsed is not None and isinstance(parsed.get("facts", []), list):
            return parsed, str(response)
    return None, str(response)


def chunk_has_usable_content(chunk: dict[str, Any]) -> bool:
    if str(chunk.get("text", "")).strip():
        return True
    return any(Path(str(path)).is_file() for path in chunk.get("attachments", []))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_manifest(rows: list[dict[str, Any]], output_path: Path) -> None:
    pd.DataFrame(rows).to_excel(output_path, index=False, engine="openpyxl")


def run(args: argparse.Namespace) -> Path:
    if not os.getenv("BOSCH_FARM_SUBSCRIPTION_KEY"):
        raise EnvironmentError("BOSCH_FARM_SUBSCRIPTION_KEY is not set in .env or environment.")
    if args.pdf_pages_per_chunk <= 0 or args.excel_rows_per_chunk <= 0:
        raise ValueError("Chunk sizes must be positive.")
    if args.max_attachment_mb <= 0:
        raise ValueError("--max-attachment-mb must be positive.")
    inventory = pd.read_excel(args.inventory_excel, sheet_name="file_classification", dtype=str).fillna("")
    required = {"BG_Folder", "Data_Folder_Path", "Relative_Path", "Primary_Type", "Manual_Type"}
    missing = required.difference(inventory.columns)
    if missing:
        raise ValueError(f"Inventory misses required columns: {sorted(missing)}")

    selected = inventory.copy()
    selected["Effective_Type"] = selected.apply(effective_type, axis=1)
    selected = selected[selected["Effective_Type"].isin(PROCESSABLE_TYPES)]
    if not args.include_other:
        selected = selected[selected["Effective_Type"] != "other_technical_document"]
    duplicate_count = int(selected.apply(is_duplicate_derivative, axis=1).sum())
    if duplicate_count:
        logging.info("Excluding %d duplicate converted/visual-context inventory row(s).", duplicate_count)
        selected = selected[~selected.apply(is_duplicate_derivative, axis=1)]
    bg_order = list(dict.fromkeys(selected["BG_Folder"].tolist()))
    if args.max_bgs:
        bg_order = bg_order[:args.max_bgs]
        selected = selected[selected["BG_Folder"].isin(bg_order)]

    run_id = f"facts_{safe_name(args.model)}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
    run_dir = args.output_dir / run_id
    cache_dir = run_dir / "preview_cache"
    manifest_path = run_dir / "extraction_manifest.xlsx"
    llm = create_connector(args.model, os.environ["BOSCH_FARM_SUBSCRIPTION_KEY"])
    manifest_rows: list[dict[str, Any]] = []

    for bg_folder in bg_order:
        bg_records: list[dict[str, Any]] = []
        bg_rows = selected[selected["BG_Folder"] == bg_folder]
        for _, row in bg_rows.iterrows():
            path = source_path(row)
            relative = str(row["Relative_Path"])
            doc_type = str(row["Effective_Type"])
            record = {"relative_path": relative, "document_type": doc_type, "chunks": []}
            if not path.is_file():
                record["status"] = "SOURCE_FILE_NOT_FOUND"
                bg_records.append(record)
                manifest_rows.append({"BG_Folder": bg_folder, "Relative_Path": relative, "Document_Type": doc_type, "Chunk": "", "Status": "SOURCE_FILE_NOT_FOUND", "Fact_Count": 0})
                continue
            try:
                chunks = document_chunks(path, doc_type, cache_dir, args)
            except Exception as error:
                record["status"] = f"PREPARATION_ERROR: {error}"
                bg_records.append(record)
                manifest_rows.append({"BG_Folder": bg_folder, "Relative_Path": relative, "Document_Type": doc_type, "Chunk": "", "Status": f"PREPARATION_ERROR: {error}", "Fact_Count": 0})
                continue
            for index, chunk in enumerate(chunks, start=1):
                if not chunk_has_usable_content(chunk):
                    parsed, raw = None, ""
                    status = "SKIPPED_NO_USABLE_CONTENT"
                    limitations = ["No extractable text and no upload-safe page/image preview were available; no LLM request was made."]
                else:
                    parsed, raw = call_chunk(llm, doc_type, relative, chunk, args)
                    status = "SUCCESS" if parsed else "CHECK_INVALID_JSON_OR_RESPONSE"
                    limitations = parsed.get("missing_or_uncertain", []) if parsed else []
                facts = parsed.get("facts", []) if parsed else []
                chunk_record = {
                    "chunk_index": index, "source_location": chunk["location"],
                    "status": status,
                    "facts": facts,
                    "missing_or_uncertain": limitations,
                    "raw_model_response": raw,
                }
                record["chunks"].append(chunk_record)
                manifest_rows.append({"BG_Folder": bg_folder, "Relative_Path": relative, "Document_Type": doc_type, "Chunk": chunk["location"], "Status": chunk_record["status"], "Fact_Count": len(facts)})
                write_manifest(manifest_rows, manifest_path)
                write_json(run_dir / "facts" / f"{safe_name(bg_folder)}.json", {"bg_folder": bg_folder, "run_id": run_id, "documents": bg_records + [record]})
            bg_records.append(record)
        write_json(run_dir / "facts" / f"{safe_name(bg_folder)}.json", {"bg_folder": bg_folder, "run_id": run_id, "documents": bg_records})

    write_manifest(manifest_rows, manifest_path)
    return run_dir


def main() -> None:
    load_dotenv(PROJECT_DIR / ".env")
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", handlers=[logging.StreamHandler()], force=True)
    result = run(args)
    print(f"Done: {result.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        logging.error("Fact extraction did not finish: %s", error)
        sys.exit(1)

# Example command (run from RepoMA root):
# python scripts\extract_bg_facts_text_only.py --inventory-excel ".\outputs\text_only_preprocessing\file_inventory_classified_....xlsx" --max-bgs 5
