#!/usr/bin/env python3
"""Build complete, source-traceable raw text inputs for the text-only experiment.

This script deliberately makes NO LLM calls and performs no semantic selection,
summarisation, file-role classification or fact extraction.  It recursively
scans each Baugruppe (BG) folder listed in the experiment Excel, extracts all
available native PDF text, OCRs images and PDF pages that lack native text, and
serialises spreadsheets without omitting non-empty cells.

One UTF-8 ``.txt`` input is written for every BG.  Each text segment is marked
with its original relative file name, PDF page number or spreadsheet sheet.
``converted...`` folders and ``*_visual_context.pdf`` files are excluded only
because they are duplicate conversions of original material.
"""

from __future__ import annotations

import argparse
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable
import zipfile
import xml.etree.ElementTree as ET

import pandas as pd

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    import pytesseract
except ImportError:
    pytesseract = None

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable: Any, **_kwargs: Any) -> Any:
        return iterable

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args: Any, **_kwargs: Any) -> bool:
        return False


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent if SCRIPT_DIR.name.casefold() == "scripts" else SCRIPT_DIR

PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
SPREADSHEET_EXTENSIONS = {".xlsx", ".xls", ".csv"}
TEXT_EXTENSIONS = {".txt", ".md", ".xml", ".json", ".log"}
DOCX_EXTENSIONS = {".docx"}
SUPPORTED_EXTENSIONS = PDF_EXTENSIONS | IMAGE_EXTENSIONS | SPREADSHEET_EXTENSIONS | TEXT_EXTENSIONS | DOCX_EXTENSIONS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-excel", type=Path, required=True,
        help="Experiment Excel containing Data_Folder_Path and, normally, prompt_engineering.",
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=PROJECT_DIR / "outputs" / "raw_text_only_preprocessing",
        help="Base output directory for one timestamped raw-text run.",
    )
    parser.add_argument("--max-bgs", type=int, default=None, help="Extract only the first N selected BG folders.")
    parser.add_argument("--max-workers", type=int, default=1, help="Concurrent BG extraction workers; default 1.")
    parser.add_argument(
        "--include-prompt-engineering", action="store_true",
        help="Include rows whose prompt_engineering column is yes (excluded by default for the final test).",
    )
    parser.add_argument(
        "--ocr-language", default="deu+eng",
        help="Tesseract language specification; default deu+eng.",
    )
    parser.add_argument(
        "--ocr-dpi", type=int, default=200,
        help="Render DPI used only for PDF pages requiring OCR; default 200.",
    )
    parser.add_argument(
        "--native-text-min-chars", type=int, default=20,
        help="OCR a PDF page when its extracted native text has fewer characters; default 20.",
    )
    parser.add_argument(
        "--ocr-all-pdf-pages", action="store_true",
        help="OCR every PDF page as well as preserving its native text; slow but useful for hybrid scans.",
    )
    parser.add_argument(
        "--skip-image-folders", action="store_true",
        help="Optional speed mode: skip Screenshots/Bilder folders. Disabled by default so all original image text is retained.",
    )
    return parser.parse_args()


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("._") or "unnamed_bg"


def clean(value: Any) -> str:
    return str(value or "").strip()


def yes(value: Any) -> bool:
    return clean(value).casefold() in {"yes", "y", "ja", "true", "1"}


def normalise_column(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name).casefold())


def find_column(frame: pd.DataFrame, candidates: Iterable[str]) -> str | None:
    indexed = {normalise_column(column): str(column) for column in frame.columns}
    for candidate in candidates:
        found = indexed.get(normalise_column(candidate))
        if found:
            return found
    return None


def read_dataset(path: Path, include_prompt_engineering: bool) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"Dataset Excel does not exist: {path}")
    workbook = pd.ExcelFile(path)
    preferred_sheet = next((sheet for sheet in workbook.sheet_names if "experiment" in sheet.casefold()), workbook.sheet_names[0])
    frame = pd.read_excel(path, sheet_name=preferred_sheet, dtype=str).fillna("")
    path_column = find_column(frame, ("Data_Folder_Path", "data folder path", "folder_path"))
    if not path_column:
        raise ValueError("Dataset Excel needs a Data_Folder_Path column.")
    prompt_column = find_column(frame, ("prompt_engineering", "prompt engineering"))
    identity_column = find_column(frame, ("BG_Folder", "SAP-Nummer", "SAP_Nummer", "SAP Number", "Teamcenter"))

    rows: list[dict[str, str]] = []
    seen_paths: set[str] = set()
    excluded = 0
    for _, row in frame.iterrows():
        raw_folder_path = clean(row.get(path_column))
        if not raw_folder_path:
            continue
        folder_path = Path(raw_folder_path).expanduser()
        if not include_prompt_engineering and prompt_column and yes(row.get(prompt_column)):
            excluded += 1
            continue
        path_key = str(folder_path).casefold()
        if path_key in seen_paths:
            continue
        seen_paths.add(path_key)
        label = clean(row.get(identity_column)) if identity_column else ""
        rows.append({
            "bg_folder": label or folder_path.name,
            "folder_path": str(folder_path),
            # Carry this audit flag into raw_text_manifest.xlsx so Step 2 can
            # enforce the independent-final-test exclusion again if needed.
            "prompt_engineering": clean(row.get(prompt_column)) if prompt_column else "",
        })
    if excluded:
        logging.info("Excluded %d prompt-engineering dataset row(s).", excluded)
    return rows


def is_duplicate_or_excluded(path: Path, bg_folder: Path, skip_image_folders: bool) -> tuple[bool, str]:
    relative_parts = path.relative_to(bg_folder).parts
    parent_parts = relative_parts[:-1]
    if any(part.casefold().startswith("converted") for part in parent_parts):
        return True, "SKIPPED_DUPLICATE_CONVERTED_FOLDER"
    if path.suffix.casefold() == ".pdf" and "_visual_context" in path.stem.casefold():
        return True, "SKIPPED_DUPLICATE_VISUAL_CONTEXT_PDF"
    if skip_image_folders and any(part.casefold() in {"screenshots", "bilder"} for part in parent_parts):
        return True, "SKIPPED_BY_OPTION_IMAGE_FOLDER"
    return False, ""


def supported_files(bg_folder: Path, skip_image_folders: bool) -> tuple[list[Path], list[dict[str, str]]]:
    usable: list[Path] = []
    skipped: list[dict[str, str]] = []
    try:
        paths = sorted((path for path in bg_folder.rglob("*") if path.is_file()), key=lambda path: str(path).casefold())
    except OSError as error:
        return [], [{"Relative_Path": "", "File_Type": "", "Status": f"FOLDER_SCAN_ERROR: {error}", "Text_Characters": "0"}]
    for path in paths:
        try:
            excluded, status = is_duplicate_or_excluded(path, bg_folder, skip_image_folders)
            relative = str(path.relative_to(bg_folder))
        except OSError:
            continue
        if excluded:
            skipped.append({"Relative_Path": relative, "File_Type": path.suffix.casefold(), "Status": status, "Text_Characters": "0"})
        elif path.suffix.casefold() in SUPPORTED_EXTENSIONS:
            usable.append(path)
        else:
            skipped.append({"Relative_Path": relative, "File_Type": path.suffix.casefold(), "Status": "SKIPPED_UNSUPPORTED_BINARY_OR_FORMAT", "Text_Characters": "0"})
    return usable, skipped


def ocr_image(image: Any, language: str) -> str:
    if pytesseract is None:
        raise RuntimeError("pytesseract is not installed. Install it with: pip install pytesseract")
    try:
        return pytesseract.image_to_string(image, lang=language, config="--psm 6").strip()
    except pytesseract.TesseractNotFoundError as error:
        raise RuntimeError("Tesseract OCR executable was not found. Install Tesseract and add it to PATH.") from error


def pdf_segments(path: Path, args: argparse.Namespace, show_page_progress: bool) -> tuple[list[str], list[dict[str, str]]]:
    if fitz is None:
        raise RuntimeError("PyMuPDF is not installed. Install it with: pip install pymupdf")
    document = fitz.open(path)
    segments: list[str] = []
    records: list[dict[str, str]] = []
    pages: Iterable[Any] = enumerate(document, start=1)
    if show_page_progress:
        pages = tqdm(pages, total=len(document), desc=f"OCR/text {path.name[:28]}", unit="page", leave=False, dynamic_ncols=True)
    try:
        for page_number, page in pages:
            native_text = page.get_text("text").strip()
            need_ocr = args.ocr_all_pdf_pages or len(native_text) < args.native_text_min_chars
            ocr_text = ""
            ocr_status = "NOT_REQUIRED"
            if need_ocr:
                try:
                    scale = args.ocr_dpi / 72.0
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                    if Image is None:
                        raise RuntimeError("Pillow is not installed. Install it with: pip install pillow")
                    image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
                    ocr_text = ocr_image(image, args.ocr_language)
                    ocr_status = "OCR_SUCCESS" if ocr_text else "OCR_NO_TEXT"
                except Exception as error:
                    ocr_status = f"OCR_ERROR: {error}"
                    logging.warning("PDF OCR failed for %s page %d: %s", path.name, page_number, error)
            blocks = [f"[PDF page {page_number} | native text]", native_text or "(no native text extracted)"]
            if need_ocr:
                blocks.extend([f"[PDF page {page_number} | OCR text | {ocr_status}]", ocr_text or "(no OCR text extracted)"])
            segments.append("\n".join(blocks))
            records.append({
                "Relative_Path": "", "File_Type": ".pdf", "Source_Location": f"page {page_number}",
                "Extraction_Mode": "native_text" + (" + OCR" if need_ocr else ""),
                "Status": "SUCCESS" if not ocr_status.startswith("OCR_ERROR") else ocr_status,
                "Text_Characters": str(len(native_text) + len(ocr_text)),
            })
    finally:
        document.close()
    return segments, records


def image_segments(path: Path, args: argparse.Namespace) -> tuple[list[str], list[dict[str, str]]]:
    if Image is None:
        raise RuntimeError("Pillow is not installed. Install it with: pip install pillow")
    with Image.open(path) as image:
        text = ocr_image(image.convert("RGB"), args.ocr_language)
    status = "OCR_SUCCESS" if text else "OCR_NO_TEXT"
    return ["[Image OCR text]", text or "(no OCR text extracted)"], [{
        "Relative_Path": "", "File_Type": path.suffix.casefold(), "Source_Location": "image",
        "Extraction_Mode": "OCR", "Status": status, "Text_Characters": str(len(text)),
    }]


def read_delimited_text_table(path: Path) -> pd.DataFrame:
    """Read CSV-like files, including files incorrectly named ``.XLS``.

    Several legacy BOM exports have a .XLS suffix even though their bytes are
    a delimited text table.  Excel displays its format/extension warning and
    can open them after the user's *Konvertieren* choice; pandas cannot infer
    an Excel engine for them.  Only use this path if the file genuinely looks
    like readable text, so a binary/corrupted workbook is never silently
    converted into garbage.
    """
    raw_sample = path.read_bytes()[:131_072]
    if not raw_sample:
        return pd.DataFrame()

    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            decoded = raw_sample.decode(encoding)
        except UnicodeDecodeError as error:
            last_error = error
            continue

        # A genuine delimited export should be overwhelmingly printable and
        # contain at least one normal field/table separator.
        printable = sum(character.isprintable() or character in "\r\n\t" for character in decoded)
        ratio = printable / max(len(decoded), 1)
        if ratio < 0.92 or not any(separator in decoded for separator in (",", ";", "\t", "|")):
            continue
        try:
            return pd.read_csv(
                path,
                sep=None,
                engine="python",
                header=None,
                dtype=str,
                keep_default_na=False,
                encoding=encoding,
                quoting=csv.QUOTE_MINIMAL,
            )
        except Exception as error:
            last_error = error

    explanation = "file does not look like a readable delimited-text table"
    if last_error:
        explanation += f" ({last_error})"
    raise ValueError(explanation)


def spreadsheet_segments(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    records: list[dict[str, str]] = []
    segments: list[str] = []
    suffix = path.suffix.casefold()
    if suffix == ".csv":
        sheets = [("CSV", read_delimited_text_table(path))]
    else:
        try:
            workbook = pd.ExcelFile(path)
            sheets = [
                (sheet, pd.read_excel(path, sheet_name=sheet, header=None, dtype=str, keep_default_na=False))
                for sheet in workbook.sheet_names
            ]
        except Exception as workbook_error:
            # Excel's warning "file format and extension do not match" is a
            # common sign of this exact legacy export.  Preserve all cells by
            # falling back to delimited text; keep the mode explicit in the
            # manifest for traceability.
            if suffix != ".xls":
                raise
            try:
                sheets = [("TEXT_TABLE_FALLBACK", read_delimited_text_table(path))]
                logging.info(
                    "Read extension-mismatched .XLS as a delimited text table: %s",
                    path,
                )
            except Exception as text_error:
                raise ValueError(
                    f"Could not read legacy .XLS as an Excel workbook ({workbook_error}) "
                    f"or as a delimited text table ({text_error})."
                ) from workbook_error
    for sheet_name, frame in sheets:
        lines = [f"[Spreadsheet sheet: {sheet_name}]"]
        nonempty_count = 0
        for row_number, values in enumerate(frame.itertuples(index=False, name=None), start=1):
            cells = []
            for column_number, value in enumerate(values, start=1):
                value_text = clean(value)
                if value_text:
                    column = ""
                    current = column_number
                    while current:
                        current, remainder = divmod(current - 1, 26)
                        column = chr(65 + remainder) + column
                    cells.append(f"{column}{row_number}={value_text}")
                    nonempty_count += 1
            if cells:
                lines.append(" | ".join(cells))
        segments.append("\n".join(lines))
        text_count = sum(len(line) for line in lines)
        records.append({
            "Relative_Path": "", "File_Type": path.suffix.casefold(), "Source_Location": f"sheet {sheet_name}",
            "Extraction_Mode": "all_nonempty_cells" if sheet_name != "TEXT_TABLE_FALLBACK" else "delimited_text_fallback",
            "Status": "SUCCESS",
            "Text_Characters": str(text_count), "Nonempty_Cells": str(nonempty_count),
        })
    return segments, records


def docx_segments(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml")
    root = ET.fromstring(xml)
    paragraphs = []
    for paragraph in root.iter(f"{namespace}p"):
        text = "".join(node.text or "" for node in paragraph.iter(f"{namespace}t")).strip()
        if text:
            paragraphs.append(text)
    text = "\n".join(paragraphs)
    return ["[DOCX native text]", text or "(no text extracted)"], [{
        "Relative_Path": "", "File_Type": ".docx", "Source_Location": "document",
        "Extraction_Mode": "native_docx_xml", "Status": "SUCCESS" if text else "NO_TEXT",
        "Text_Characters": str(len(text)),
    }]


def plain_text_segments(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        text = path.read_text(encoding="latin-1")
    return ["[Native text file]", text.rstrip() or "(empty text file)"], [{
        "Relative_Path": "", "File_Type": path.suffix.casefold(), "Source_Location": "file",
        "Extraction_Mode": "native_text", "Status": "SUCCESS" if text.strip() else "NO_TEXT",
        "Text_Characters": str(len(text)),
    }]


def extract_file(path: Path, bg_folder: Path, args: argparse.Namespace, show_page_progress: bool) -> tuple[str, list[dict[str, str]]]:
    relative = str(path.relative_to(bg_folder))
    suffix = path.suffix.casefold()
    if suffix in PDF_EXTENSIONS:
        segments, records = pdf_segments(path, args, show_page_progress)
    elif suffix in IMAGE_EXTENSIONS:
        segments, records = image_segments(path, args)
    elif suffix in SPREADSHEET_EXTENSIONS:
        segments, records = spreadsheet_segments(path)
    elif suffix in DOCX_EXTENSIONS:
        segments, records = docx_segments(path)
    else:
        segments, records = plain_text_segments(path)
    for record in records:
        record["Relative_Path"] = relative
        record.setdefault("Nonempty_Cells", "")
    header = f"===== SOURCE FILE: {relative} ====="
    return "\n".join([header, *segments]).rstrip(), records


def write_manifest(bg_rows: list[dict[str, Any]], source_rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(bg_rows).to_excel(writer, sheet_name="BG_Manifest", index=False)
        pd.DataFrame(source_rows).to_excel(writer, sheet_name="Source_Manifest", index=False)


def extract_bg(
    item: dict[str, str], args: argparse.Namespace, text_dir: Path, show_page_progress: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    bg_folder = Path(item["folder_path"])
    bg_name = item["bg_folder"]
    output_path = text_dir / f"{safe_name(bg_name)}.txt"
    source_rows: list[dict[str, Any]] = []
    if not bg_folder.is_dir():
        return ({"BG_Folder": bg_name, "Data_Folder_Path": str(bg_folder),
                 "prompt_engineering": item.get("prompt_engineering", ""),
                 "Output_Text_File": "", "Status": "SKIPPED_BG_FOLDER_NOT_AVAILABLE",
                 "Source_File_Count": 0, "Text_Characters": 0}, source_rows)

    files, skipped_rows = supported_files(bg_folder, args.skip_image_folders)
    for row in skipped_rows:
        source_rows.append({"BG_Folder": bg_name, "Data_Folder_Path": str(bg_folder), **row})
    sections = [
        "TEXT-ONLY RAW BAUGRUPPE INPUT",
        f"BG FOLDER: {bg_name}",
        "This file is a source-preserving local transcription. No LLM classification, summary, relevance ranking or fact extraction was performed.",
        "",
    ]
    file_count = 0
    for path in files:
        try:
            text, records = extract_file(path, bg_folder, args, show_page_progress)
            sections.extend([text, ""])
            file_count += 1
            for record in records:
                source_rows.append({"BG_Folder": bg_name, "Data_Folder_Path": str(bg_folder), **record})
        except Exception as error:
            relative = str(path.relative_to(bg_folder))
            logging.warning("Could not extract %s: %s", path, error)
            source_rows.append({
                "BG_Folder": bg_name, "Data_Folder_Path": str(bg_folder), "Relative_Path": relative,
                "File_Type": path.suffix.casefold(), "Source_Location": "", "Extraction_Mode": "",
                "Status": f"EXTRACTION_ERROR: {error}", "Text_Characters": "0", "Nonempty_Cells": "",
            })
    sections.extend(["END OF RAW BG TEXT", ""])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(sections), encoding="utf-8")
    text_characters = output_path.stat().st_size
    return ({
        "BG_Folder": bg_name, "Data_Folder_Path": str(bg_folder),
        "prompt_engineering": item.get("prompt_engineering", ""),
        "Output_Text_File": str(output_path),
        "Status": "SUCCESS", "Source_File_Count": file_count, "Text_Characters": text_characters,
    }, source_rows)


def run(args: argparse.Namespace) -> Path:
    if args.max_bgs is not None and args.max_bgs <= 0:
        raise ValueError("--max-bgs must be positive.")
    if args.max_workers <= 0:
        raise ValueError("--max-workers must be positive.")
    if args.ocr_dpi <= 0 or args.native_text_min_chars < 0:
        raise ValueError("OCR parameters must be non-negative, and --ocr-dpi must be positive.")
    selected = read_dataset(args.dataset_excel, args.include_prompt_engineering)
    if args.max_bgs:
        selected = selected[:args.max_bgs]
    if not selected:
        raise ValueError("No BG folders selected from the dataset Excel.")

    run_id = f"raw_text_only_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
    run_dir = args.output_dir / run_id
    text_dir = run_dir / "texts"
    run_dir.mkdir(parents=True, exist_ok=True)
    text_dir.mkdir(parents=True, exist_ok=True)
    bg_rows: list[dict[str, Any]] = []
    source_rows: list[dict[str, Any]] = []

    # A nested page bar is readable only when one BG is processed at a time.
    show_page_progress = args.max_workers == 1
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        future_items = {
            executor.submit(extract_bg, item, args, text_dir, show_page_progress): item
            for item in selected
        }
        for future in tqdm(as_completed(future_items), total=len(future_items), desc="Building raw text inputs", unit="BG", dynamic_ncols=True):
            item = future_items[future]
            try:
                bg_record, file_records = future.result()
            except Exception as error:
                logging.exception("Unexpected BG extraction failure for %s", item["bg_folder"])
                bg_record = {
                    "BG_Folder": item["bg_folder"], "Data_Folder_Path": item["folder_path"],
                    "prompt_engineering": item.get("prompt_engineering", ""),
                    "Output_Text_File": "", "Status": f"UNEXPECTED_BG_ERROR: {error}",
                    "Source_File_Count": 0, "Text_Characters": 0,
                }
                file_records = []
            bg_rows.append(bg_record)
            source_rows.extend(file_records)
            # Save a recoverable checkpoint after every completed BG.
            write_manifest(bg_rows, source_rows, run_dir / "raw_text_manifest.xlsx")
    bg_rows.sort(key=lambda row: str(row["BG_Folder"]).casefold())
    source_rows.sort(key=lambda row: (str(row["BG_Folder"]).casefold(), str(row.get("Relative_Path", "")).casefold(), str(row.get("Source_Location", ""))))
    write_manifest(bg_rows, source_rows, run_dir / "raw_text_manifest.xlsx")
    return run_dir


def main() -> None:
    load_dotenv(PROJECT_DIR / ".env")
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", force=True)
    result = run(args)
    print(f"Done: {result.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        logging.error("Raw text-only input build did not finish: %s", error)
        sys.exit(1)

# Raw text-only preprocessing commands. No LLM is called by this script.
# Pilot: build complete text/OCR input for the first 5 independent final-test BGs:
# python build_raw_text_only_inputs.py --dataset-excel ".\input\classification_experiment_dataset_V2.xlsx" --max-bgs 5 --max-workers 1
# Full run: all independent final-test BGs; max-workers 4 is a good local OCR starting point:
# python build_raw_text_only_inputs.py --dataset-excel ".\input\classification_experiment_dataset_V2.xlsx" --max-workers 4
# Strict hybrid-scan mode: OCR every PDF page as well as retaining native PDF text (slower):
# python build_raw_text_only_inputs.py --dataset-excel ".\input\classification_experiment_dataset_V2.xlsx" --max-workers 1 --ocr-all-pdf-pages
# Optional legacy speed mode: skip Screenshots/Bilder folders (not recommended when retaining all image text):
# python build_raw_text_only_inputs.py --dataset-excel ".\input\classification_experiment_dataset_V2.xlsx" --max-workers 4 --skip-image-folders
