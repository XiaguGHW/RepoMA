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

DATASHEET_TRIAGE_SYSTEM_PROMPT = """Du bewertest ausschließlich, ob ein
Komponenten-Datenblatt für die spätere funktionale Einordnung einer Baugruppe
relevante Belege liefern kann. Du darfst keine Baugruppen-Funktionsklasse
vorhersagen. Nutze nur den bereitgestellten Dokumentausschnitt und antworte
ausschließlich als JSON."""


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
    parser.add_argument("--datasheet-triage-pages", type=int, default=2)
    parser.add_argument("--max-datasheet-evidence-pages", type=int, default=4)
    parser.add_argument("--datasheet-fallback-pages", type=int, default=2)
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


def datasheet_triage_prompt(relative_path: str, chunk: dict[str, Any], core_evidence: str) -> str:
    return f"""Bewerte, ob dieses Datenblatt für die Funktionsklassifikation der
gesamten Baugruppe als technische Evidenz nützlich ist. Es geht nicht darum,
eine Baugruppenklasse vorherzusagen.

Datei: {relative_path}
Quellabschnitt: {chunk['location']}
Lokaler Text:
{chunk['text'] or '[Kein lokaler Text; nutze nur beigefügte Seite/Bild.]'}

Bereits extrahierte Kernevidenz aus DFC, Stückliste oder Zeichnung:
{core_evidence or '[Noch keine explizite Kernevidenz verfügbar.]'}

Direkt relevant sind z. B. Greifer, Roboter, Linear- oder Rotationsaktoren,
Achsen und eindeutig bewegungsbestimmende Komponenten. Unterstützend relevant
sind z. B. zugeordnete Motoren, Getriebe oder zentrale Antriebs-/Übertragungs-
komponenten. Niedrige Relevanz haben z. B. Sensoren, Kabel, Schrauben,
Schutzelemente, allgemeine Katalogseiten ohne konkretes Modell oder reine
Montage-/Materialdetails.

Return exactly this JSON object:
{{
  "relevance": "directly_relevant | supporting_relevant | low_relevance | uncertain",
  "reason": "short evidence-based reason",
  "identified_component": "component type or model, if explicitly visible",
  "needs_review": false
}}
"""


def triage_datasheet(llm: Any, relative_path: str, chunk: dict[str, Any], core_evidence: str, args: argparse.Namespace) -> tuple[dict[str, Any] | None, str]:
    if not chunk_has_usable_content(chunk):
        return None, ""
    response = ""
    for _attempt in range(args.retries + 1):
        response = llm.ask_about_files(
            file_paths=chunk["attachments"],
            question=datasheet_triage_prompt(relative_path, chunk, core_evidence),
            system_prompt=DATASHEET_TRIAGE_SYSTEM_PROMPT,
            generation_config={"temperature": 0.0, "topP": 0.95, "candidateCount": 1, "maxOutputTokens": 500},
        )
        parsed = extract_json(str(response))
        if parsed and str(parsed.get("relevance", "")).strip() in {
            "directly_relevant", "supporting_relevant", "low_relevance", "uncertain"
        }:
            return parsed, str(response)
    return None, str(response)


def create_connector(model: str, api_key: str):
    try:
        from llm_connector_with_prompt_caching import LLMConnector
    except ImportError as error:
        raise ImportError("Place llm_connector_with_prompt_caching.py next to this script.") from error
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


def component_reference_terms(value: str) -> list[str]:
    """Keep likely model/part-number tokens for local PDF page selection."""
    terms = set()
    for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_./-]{3,}", value or ""):
        has_letter = any(character.isalpha() for character in token)
        has_digit = any(character.isdigit() for character in token)
        if has_letter and has_digit:
            terms.add(token.casefold())
    return sorted(terms, key=len, reverse=True)


def select_datasheet_pages(path: Path, triage: dict[str, Any], core_evidence: str, args: argparse.Namespace) -> list[int] | None:
    """Select a small evidence-page set locally; never send a full PDF catalog."""
    if path.suffix.casefold() != ".pdf":
        return None
    if fitz is None:
        raise ImportError("PyMuPDF is required for PDF page processing.")
    terms = component_reference_terms(
        " ".join([str(triage.get("identified_component", "")), path.stem, core_evidence])
    )[:12]
    document = fitz.open(path)
    try:
        matched_pages: list[int] = []
        if terms:
            for index, page in enumerate(document, start=1):
                page_text = page.get_text("text").casefold()
                if any(term in page_text for term in terms):
                    matched_pages.extend((index - 1, index, index + 1))
        selected = sorted({page for page in matched_pages if 1 <= page <= len(document)})
        if selected:
            return selected[:args.max_datasheet_evidence_pages]
        return list(range(1, min(len(document), args.datasheet_fallback_pages) + 1))
    finally:
        document.close()


def pdf_chunks(path: Path, cache_dir: Path, args: argparse.Namespace, page_limit: int | None = None, page_numbers: list[int] | None = None) -> list[dict[str, Any]]:
    if fitz is None:
        raise ImportError("PyMuPDF is required for PDF page processing.")
    document = fitz.open(path)
    chunks = []
    available_pages = page_numbers or list(range(1, (min(len(document), page_limit) if page_limit else len(document)) + 1))
    for start in range(0, len(available_pages), args.pdf_pages_per_chunk):
        pages = available_pages[start:start + args.pdf_pages_per_chunk]
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
        page_label = ", ".join(str(page) for page in pages)
        chunks.append({"location": f"pages {page_label}", "text": text[:args.max_text_chars], "attachments": attachments})
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


def document_chunks(path: Path, doc_type: str, cache_dir: Path, args: argparse.Namespace, page_limit: int | None = None, page_numbers: list[int] | None = None) -> list[dict[str, Any]]:
    extension = path.suffix.casefold()
    if extension == ".pdf":
        return pdf_chunks(path, cache_dir, args, page_limit=page_limit, page_numbers=page_numbers)
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
        "component_datasheet": "nur Hersteller, Modell/Teilenummer, Komponententyp, Antriebs-/Bewegungsprinzip sowie für die Baugruppenfunktion relevante Angaben wie linear/rotativ, Hub, Winkel, Achsen oder Greifprinzip. Ignoriere Maße, Material, Zertifikate, Bestellvarianten und sonstige Detailparameter ohne Funktionsbezug.",
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


def core_evidence_text(records: list[dict[str, Any]], max_chars: int = 6000) -> str:
    """Build compact component context from already processed non-datasheet files."""
    facts: list[str] = []
    for record in records:
        if record.get("document_type") == "component_datasheet":
            continue
        for chunk in record.get("chunks", []):
            for fact in chunk.get("facts", []):
                if isinstance(fact, dict) and str(fact.get("fact", "")).strip():
                    facts.append(str(fact["fact"]).strip())
    return "\n".join(f"- {fact}" for fact in facts)[:max_chars]


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
    if args.datasheet_triage_pages <= 0:
        raise ValueError("--datasheet-triage-pages must be positive.")
    if args.max_datasheet_evidence_pages <= 0 or args.datasheet_fallback_pages <= 0:
        raise ValueError("Datasheet evidence page limits must be positive.")
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
        bg_rows = selected[selected["BG_Folder"] == bg_folder].copy()
        # Core assembly evidence is extracted before any component data sheet.
        bg_rows["_datasheet_last"] = (bg_rows["Effective_Type"] == "component_datasheet").astype(int)
        bg_rows = bg_rows.sort_values(["_datasheet_last", "Relative_Path"], kind="stable")
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
            if doc_type == "component_datasheet":
                core_evidence = core_evidence_text(bg_records)
                try:
                    triage_chunks = document_chunks(
                        path,
                        doc_type,
                        cache_dir / "datasheet_triage",
                        args,
                        page_limit=args.datasheet_triage_pages,
                    )
                    triage_chunk = triage_chunks[0]
                    triage, triage_raw = triage_datasheet(llm, relative, triage_chunk, core_evidence, args)
                except Exception as error:
                    triage, triage_raw = None, ""
                    logging.warning("Could not triage datasheet %s: %s", path, error)

                if triage is None:
                    record.update({
                        "status": "SKIPPED_DATASHEET_TRIAGE_UNCERTAIN",
                        "relevance_assessment": {"relevance": "uncertain", "reason": "No valid triage result; full datasheet extraction was not run.", "raw_model_response": triage_raw},
                    })
                    bg_records.append(record)
                    manifest_rows.append({"BG_Folder": bg_folder, "Relative_Path": relative, "Document_Type": doc_type, "Chunk": "triage", "Status": "SKIPPED_DATASHEET_TRIAGE_UNCERTAIN", "Fact_Count": 0, "Relevance": "uncertain", "Relevance_Reason": "No valid triage result; full datasheet extraction was not run."})
                    continue

                relevance = str(triage["relevance"]).strip()
                record["relevance_assessment"] = {**triage, "raw_model_response": triage_raw}
                if relevance in {"low_relevance", "uncertain"}:
                    status = "SKIPPED_LOW_RELEVANCE_DATASHEET" if relevance == "low_relevance" else "SKIPPED_DATASHEET_TRIAGE_UNCERTAIN"
                    record["status"] = status
                    bg_records.append(record)
                    manifest_rows.append({"BG_Folder": bg_folder, "Relative_Path": relative, "Document_Type": doc_type, "Chunk": "triage", "Status": status, "Fact_Count": 0, "Relevance": relevance, "Relevance_Reason": str(triage.get("reason", ""))})
                    continue
                try:
                    selected_pages = select_datasheet_pages(path, triage, core_evidence, args)
                except Exception as error:
                    selected_pages = None
                    logging.warning("Could not select local evidence pages for %s: %s", path, error)
                record["selected_evidence_pages"] = selected_pages
            try:
                chunks = document_chunks(path, doc_type, cache_dir, args, page_numbers=record.get("selected_evidence_pages"))
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

# Command examples (run after reviewing the inventory Excel from step 1):
# 1) Extract facts for the same first 5 BG folders:
# python extract_bg_facts_text_only.py --inventory-excel ".\outputs\text_only_preprocessing\file_inventory_classified_<model>_<timestamp>.xlsx" --max-bgs 5
# 2) Extract facts for all BG folders:
# python extract_bg_facts_text_only.py --inventory-excel ".\outputs\text_only_preprocessing\file_inventory_classified_<model>_<timestamp>.xlsx"
# 3) More conservative scanned-PDF mode (one page and 0.8 MiB per image):
# python extract_bg_facts_text_only.py --inventory-excel ".\outputs\text_only_preprocessing\file_inventory_classified_<model>_<timestamp>.xlsx" --pdf-pages-per-chunk 1 --max-attachment-mb 0.8
