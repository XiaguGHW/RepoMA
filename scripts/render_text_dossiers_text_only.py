#!/usr/bin/env python3
"""Render one source-traceable text dossier per BG for a text-only LLM experiment.

This script consumes the ``facts/*.json`` files written by
``extract_bg_facts_text_only.py``.  It makes no LLM calls and never assigns a
functional class.  It preserves every extracted fact together with its source
file and source location, so the resulting ``.txt`` files are ready for the
subsequent text-only classification experiment.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import logging
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--facts-dir",
        type=Path,
        required=True,
        help="Directory named 'facts' inside an extract_bg_facts_text_only.py run output.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Default: sibling directory 'text_dossiers' beside --facts-dir.",
    )
    parser.add_argument(
        "--max-bgs",
        type=int,
        default=None,
        help="Render only the first N dossiers in filename order.",
    )
    parser.add_argument("--max-workers", type=int, default=1, help="Concurrent dossier-rendering workers; default 1.")
    return parser.parse_args()


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return cleaned or "unnamed_bg"


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def is_excluded_derivative_document(document: dict[str, Any]) -> bool:
    relative_path = Path(clean_text(document.get("relative_path")))
    parent_parts = relative_path.parts[:-1]
    return (
        any(part.casefold().startswith("converted") for part in parent_parts)
        or any(part.casefold() in {"screenshots", "bilder"} for part in parent_parts)
        or (
            relative_path.suffix.casefold() == ".pdf"
            and "_visual_context" in relative_path.stem.casefold()
        )
    )


def document_heading(document_type: str) -> str:
    labels = {
        "assembly_drawing": "Assembly drawing",
        "bom": "Bill of materials",
        "component_datasheet": "Component datasheet",
        "assembly_structure_or_dfc": "Assembly structure / DFC",
        "cad_screenshot_or_visual_context": "CAD screenshot / visual context",
        "other_technical_document": "Other technical document",
    }
    return labels.get(document_type, document_type or "Unspecified document type")


def load_fact_file(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Top-level JSON value must be an object.")
    if not isinstance(payload.get("documents", []), list):
        raise ValueError("Field 'documents' must be a list.")
    return payload


def render_dossier(payload: dict[str, Any], source_json_name: str) -> tuple[str, dict[str, int]]:
    bg_folder = clean_text(payload.get("bg_folder")) or Path(source_json_name).stem
    run_id = clean_text(payload.get("run_id")) or "not recorded"
    lines = [
        "TEXT-ONLY BAUGRUPPE DOSSIER",
        "",
        "This dossier contains extracted source facts only. It does not contain a functional classification.",
        "",
        "ASSEMBLY IDENTIFIER",
        f"- BG folder: {bg_folder}",
        f"- Fact-extraction run: {run_id}",
        f"- Fact source JSON: {source_json_name}",
        "",
        "EXTRACTED TECHNICAL FACTS",
    ]
    counts = Counter(documents=0, chunks=0, successful_chunks=0, facts=0, limitations=0, low_relevance_datasheets=0, uncertain_datasheets=0, excluded_derivative_documents=0)
    documents = payload.get("documents", [])
    if not documents:
        lines.extend(["", "- No source documents were available in this extraction result."])

    for document in documents:
        if not isinstance(document, dict):
            continue
        if is_excluded_derivative_document(document):
            counts["excluded_derivative_documents"] += 1
            continue
        relative_path = clean_text(document.get("relative_path")) or "unknown source file"
        doc_type = clean_text(document.get("document_type"))
        document_status = clean_text(document.get("status"))
        if document_status == "SKIPPED_LOW_RELEVANCE_DATASHEET":
            counts["low_relevance_datasheets"] += 1
            continue
        if document_status == "SKIPPED_DATASHEET_TRIAGE_UNCERTAIN":
            counts["uncertain_datasheets"] += 1
            continue
        counts["documents"] += 1
        lines.extend(["", f"## {document_heading(doc_type)}", f"Source file: {relative_path}"])
        if document_status:
            lines.append(f"Document status: {document_status}")

        chunks = document.get("chunks", [])
        if not isinstance(chunks, list) or not chunks:
            lines.append("- No extractable facts were recorded for this source file.")
            continue

        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            counts["chunks"] += 1
            location = clean_text(chunk.get("source_location")) or "source location not recorded"
            status = clean_text(chunk.get("status")) or "status not recorded"
            lines.extend(["", f"Source section: {location}", f"Extraction status: {status}"])
            if status == "SUCCESS":
                counts["successful_chunks"] += 1

            facts = chunk.get("facts", [])
            if isinstance(facts, list) and facts:
                lines.append("Facts:")
                for fact in facts:
                    if not isinstance(fact, dict):
                        continue
                    fact_text = clean_text(fact.get("fact"))
                    if not fact_text:
                        continue
                    fact_type = clean_text(fact.get("fact_type")) or "technical fact"
                    fact_location = clean_text(fact.get("source_location")) or location
                    lines.append(f"- [{fact_type}] {fact_text} (Source: {relative_path}; {fact_location})")
                    counts["facts"] += 1
            else:
                lines.append("Facts: none extracted from this source section.")

            limitations = chunk.get("missing_or_uncertain", [])
            if isinstance(limitations, list) and limitations:
                lines.append("Extraction limitations / uncertainties:")
                for limitation in limitations:
                    limitation_text = clean_text(limitation)
                    if limitation_text:
                        lines.append(f"- {limitation_text}")
                        counts["limitations"] += 1

    lines.extend([
        "",
        "SOURCE COVERAGE SUMMARY",
        f"- Source documents represented: {counts['documents']}",
        f"- Source sections processed: {counts['chunks']}",
        f"- Successfully extracted sections: {counts['successful_chunks']}",
        f"- Source-traceable facts: {counts['facts']}",
        f"- Recorded limitations / uncertainties: {counts['limitations']}",
        f"- Low-relevance datasheets omitted: {counts['low_relevance_datasheets']}",
        f"- Uncertain datasheets omitted for review: {counts['uncertain_datasheets']}",
        f"- Converted/visual-context/image-folder documents omitted: {counts['excluded_derivative_documents']}",
        "",
        "END OF DOSSIER",
        "",
    ])
    return "\n".join(lines), dict(counts)


def write_manifest(rows: list[dict[str, Any]], path: Path) -> None:
    frame = pd.DataFrame(rows)
    frame.to_csv(path, index=False, encoding="utf-8-sig")


def run(args: argparse.Namespace) -> Path:
    if args.max_bgs is not None and args.max_bgs <= 0:
        raise ValueError("--max-bgs must be positive.")
    if args.max_workers <= 0:
        raise ValueError("--max-workers must be positive.")
    facts_dir = args.facts_dir.expanduser()
    if not facts_dir.is_dir():
        raise FileNotFoundError(f"Facts directory does not exist: {facts_dir}")

    json_files = sorted(facts_dir.glob("*.json"), key=lambda path: path.name.casefold())
    if args.max_bgs:
        json_files = json_files[:args.max_bgs]
    if not json_files:
        raise FileNotFoundError(f"No .json fact files found in: {facts_dir}")

    output_dir = args.output_dir.expanduser() if args.output_dir else facts_dir.parent / "text_dossiers"
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_rows: list[dict[str, Any]] = []

    def render_one(json_path: Path) -> dict[str, Any]:
        try:
            payload = load_fact_file(json_path)
            dossier, counts = render_dossier(payload, json_path.name)
            bg_folder = clean_text(payload.get("bg_folder")) or json_path.stem
            dossier_path = output_dir / f"{safe_name(bg_folder)}.txt"
            dossier_path.write_text(dossier, encoding="utf-8")
            logging.info("Rendered dossier for %s: %s", bg_folder, dossier_path.name)
            return {
                "BG_Folder": bg_folder,
                "Source_JSON": str(json_path),
                "Dossier_File": str(dossier_path),
                "Status": "SUCCESS",
                "Source_Document_Count": counts["documents"],
                "Source_Section_Count": counts["chunks"],
                "Successful_Section_Count": counts["successful_chunks"],
                "Fact_Count": counts["facts"],
                "Limitation_Count": counts["limitations"],
            }
        except Exception as error:
            logging.exception("Could not render dossier from %s", json_path)
            return {
                "BG_Folder": json_path.stem,
                "Source_JSON": str(json_path),
                "Dossier_File": "",
                "Status": f"ERROR: {error}",
                "Source_Document_Count": 0,
                "Source_Section_Count": 0,
                "Successful_Section_Count": 0,
                "Fact_Count": 0,
                "Limitation_Count": 0,
            }

    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        manifest_rows.extend(executor.map(render_one, json_files))

    manifest_path = output_dir / "text_dossier_manifest.csv"
    write_manifest(manifest_rows, manifest_path)
    return output_dir


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", force=True)
    result = run(args)
    print(f"Done: {result.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        logging.error("Text dossier rendering did not finish: %s", error)
        sys.exit(1)

# Final text-only pipeline commands (run after Step 2):
# Step 3a) Render the text dossiers for all final-test BG facts:
# python render_text_dossiers_text_only.py --facts-dir ".\outputs\text_only_preprocessing\facts_<model>_<timestamp>\facts" --max-workers 8
# Step 3b) Render only the first 5 dossiers for inspection:
# python render_text_dossiers_text_only.py --facts-dir ".\outputs\text_only_preprocessing\facts_<model>_<timestamp>\facts" --max-bgs 5 --max-workers 8
# Optional: store the final dossiers in an explicit directory:
# python render_text_dossiers_text_only.py --facts-dir ".\outputs\text_only_preprocessing\facts_<model>_<timestamp>\facts" --output-dir ".\outputs\text_only_preprocessing\review_dossiers" --max-workers 8

