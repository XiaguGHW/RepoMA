"""Safe, coordinate-accurate Excel assistant for Bosch Farm terminal workflows.

The program never lets an LLM guess an Excel address.  It first reads the workbook
with openpyxl, exposes exact A1 coordinates/formulas, creates a JSON edit plan, and
only writes that reviewed plan to a *new* output workbook.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from copy import copy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string, get_column_letter


def die(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(2)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def formula_fingerprint(book) -> dict[str, Any]:
    """Return a stable workbook-wide checksum of formula text and locations."""
    digest = hashlib.sha256()
    count = 0
    for sheet in book.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    digest.update(f"{sheet.title}!{cell.coordinate}\0{cell.value}\n".encode("utf-8"))
                    count += 1
    return {"formula_cells": count, "formula_sha256": digest.hexdigest()}


def load_book(path: Path, *, data_only: bool = False):
    if not path.is_file():
        die(f"Workbook not found: {path}")
    if path.suffix.lower() not in {".xlsx", ".xlsm"}:
        die("Only .xlsx and .xlsm workbooks are supported.")
    return load_workbook(path, read_only=False, data_only=data_only, keep_vba=path.suffix.lower() == ".xlsm")


def resolve_sheet(book, selector: str):
    if selector.isdigit():
        index = int(selector) - 1
        if not 0 <= index < len(book.worksheets):
            die(f"Sheet number must be between 1 and {len(book.worksheets)}.")
        return book.worksheets[index]
    if selector not in book.sheetnames:
        die(f"Unknown sheet '{selector}'. Available: {', '.join(book.sheetnames)}")
    return book[selector]


def json_out(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def display_value(value: Any, limit: int = 240) -> str:
    text = "" if value is None else str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def worksheet_overview(book) -> dict[str, Any]:
    return {
        "sheet_count": len(book.worksheets),
        "sheets": [
            {
                "number": i,
                "name": sheet.title,
                "state": sheet.sheet_state,
                "max_row": sheet.max_row,
                "max_column": sheet.max_column,
                "merged_ranges": len(sheet.merged_cells.ranges),
                "tables": [table.name for table in sheet.tables.values()],
            }
            for i, sheet in enumerate(book.worksheets, start=1)
        ],
    }


def command_inspect(args) -> None:
    book = load_book(Path(args.workbook))
    json_out(worksheet_overview(book))


def command_sheet(args) -> None:
    book = load_book(Path(args.workbook), data_only=False)
    sheet = resolve_sheet(book, args.sheet)
    max_rows, max_cols = args.rows, args.cols
    cells = []
    for row in sheet.iter_rows(min_row=1, max_row=min(sheet.max_row, max_rows), max_col=min(sheet.max_column, max_cols)):
        for cell in row:
            if cell.value is not None:
                cells.append({"cell": f"{sheet.title}!{cell.coordinate}", "value": display_value(cell.value), "formula": cell.value if isinstance(cell.value, str) and cell.value.startswith("=") else None})
    json_out({"sheet": sheet.title, "dimensions": sheet.calculate_dimension(), "preview_rows": max_rows, "preview_columns": max_cols, "cells": cells})


def command_range(args) -> None:
    book = load_book(Path(args.workbook), data_only=False)
    sheet = resolve_sheet(book, args.sheet)
    try:
        target = sheet[args.range]
    except ValueError as exc:
        die(f"Invalid range: {exc}")
    values = []
    for row in target:
        values.append([
            {"cell": f"{sheet.title}!{cell.coordinate}", "value": display_value(cell.value), "formula": cell.value if isinstance(cell.value, str) and cell.value.startswith("=") else None}
            for cell in row
        ])
    json_out({"sheet": sheet.title, "range": args.range, "values": values})


# Deliberately conservative A1-reference recogniser.  It reports direct references
# only; INDIRECT, OFFSET, named ranges and external links are surfaced as warnings.
REF_RE = re.compile(r"(?:(?:'([^']+)'|([A-Za-z0-9_ ]+))!)?(\$?[A-Z]{1,3}\$?\d+)")


def formula_references(formula: str, current_sheet: str) -> tuple[list[str], list[str]]:
    refs = []
    for quoted_sheet, plain_sheet, address in REF_RE.findall(formula):
        refs.append(f"{quoted_sheet or plain_sheet or current_sheet}!{address.replace('$', '')}")
    warnings = []
    upper = formula.upper()
    for name in ("INDIRECT", "OFFSET", "[", "!"):
        if name in upper and name in {"INDIRECT", "OFFSET", "["}:
            warnings.append("Formula contains dynamic or external references that cannot be fully traced.")
            break
    return sorted(set(refs)), warnings


def command_trace(args) -> None:
    book = load_book(Path(args.workbook), data_only=False)
    if "!" not in args.cell:
        die("Use a fully qualified cell, e.g. 'Workshop!D37'.")
    sheet_name, address = args.cell.rsplit("!", 1)
    sheet = resolve_sheet(book, sheet_name)
    cell = sheet[address]
    if not isinstance(cell.value, str) or not cell.value.startswith("="):
        json_out({"cell": args.cell, "value": cell.value, "formula": None, "references": []})
        return
    refs, warnings = formula_references(cell.value, sheet.title)
    json_out({"cell": args.cell, "formula": cell.value, "references": refs, "warnings": warnings})


def find_header_column(sheet, header_row: int, header: str) -> int:
    matches = [cell.column for cell in sheet[header_row] if str(cell.value).strip() == header]
    if len(matches) != 1:
        die(f"Expected exactly one header '{header}' in row {header_row}; found {len(matches)}.")
    return matches[0]


def read_values(path: Path, id_column: str, value_column: str) -> dict[str, Any]:
    if not path.is_file():
        die(f"Results file not found: {path}")
    rows: list[dict[str, Any]] = []
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    elif path.suffix.lower() in {".xlsx", ".xlsm"}:
        source = load_book(path, data_only=False)
        sheet = source.active
        headers = [str(cell.value).strip() if cell.value is not None else "" for cell in sheet[1]]
        for raw in sheet.iter_rows(min_row=2, values_only=True):
            rows.append(dict(zip(headers, raw)))
    else:
        die("Results file must be .csv, .xlsx or .xlsm.")
    if not rows or id_column not in rows[0] or value_column not in rows[0]:
        die(f"Results file must contain columns '{id_column}' and '{value_column}'.")
    values: dict[str, Any] = {}
    duplicates = []
    for row in rows:
        key = str(row.get(id_column, "")).strip()
        if not key:
            continue
        if key in values:
            duplicates.append(key)
        values[key] = row.get(value_column)
    if duplicates:
        die("Duplicate IDs in results file: " + ", ".join(sorted(set(duplicates))[:10]))
    return values


def assert_target_safe(sheet, destination_column: int, header_row: int, first_row: int, last_row: int) -> None:
    if any(str(rng).split(":")[0] == f"{get_column_letter(destination_column)}{header_row}" for rng in sheet.merged_cells.ranges):
        die("Destination header is merged. Choose a normal, unmerged column.")
    occupied = [sheet.cell(row, destination_column).coordinate for row in range(header_row, last_row + 1) if sheet.cell(row, destination_column).value is not None]
    if occupied:
        die("Destination column is not empty. Refusing to overwrite: " + ", ".join(occupied[:8]))


def command_plan_participants(args) -> None:
    workbook_path = Path(args.workbook).resolve()
    book = load_book(workbook_path, data_only=False)
    sheet = resolve_sheet(book, args.sheet)
    id_col = find_header_column(sheet, args.header_row, args.id_header)
    template_col = find_header_column(sheet, args.header_row, args.template_header)
    target_col = column_index_from_string(args.target_column.upper())
    first_row = args.header_row + 1
    last_row = sheet.max_row
    assert_target_safe(sheet, target_col, args.header_row, first_row, last_row)
    incoming = read_values(Path(args.results), args.results_id_column, args.results_value_column)
    workbook_ids: dict[str, int] = {}
    duplicates = []
    for row in range(first_row, last_row + 1):
        key = str(sheet.cell(row, id_col).value or "").strip()
        if not key:
            continue
        if key in workbook_ids:
            duplicates.append(key)
        workbook_ids[key] = row
    if duplicates:
        die("Duplicate IDs in workbook target sheet: " + ", ".join(sorted(set(duplicates))[:10]))
    missing = sorted(set(incoming) - set(workbook_ids))
    if missing:
        die("Result IDs absent from workbook; no plan created: " + ", ".join(missing[:15]))
    edits = [{"cell": f"{sheet.title}!{get_column_letter(target_col)}{args.header_row}", "value": args.new_header, "kind": "header"}]
    for key, value in incoming.items():
        edits.append({"cell": f"{sheet.title}!{get_column_letter(target_col)}{workbook_ids[key]}", "value": value, "kind": "participant_judgement", "bg_id": key})
    plan = {
        "format": "bosch-excel-agent-plan-v1",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_workbook": str(workbook_path),
        "source_sha256": sha256(workbook_path),
        "source_formula_fingerprint": formula_fingerprint(book),
        "operation": "fill_existing_empty_participant_column",
        "sheet": sheet.title,
        "header_row": args.header_row,
        "id_header": args.id_header,
        "template_header": args.template_header,
        "template_column": get_column_letter(template_col),
        "target_column": get_column_letter(target_col),
        "copy_style_from": f"{sheet.title}!{get_column_letter(template_col)}",
        "edits": edits,
        "preflight": {"workbook_bg_ids": len(workbook_ids), "incoming_results": len(incoming), "missing_ids": [], "target_cells_confirmed_empty": True},
        "limitations": ["The destination must already be an empty column. This tool deliberately does not insert columns or rewrite unrelated formulas.", "Formula recalculation is delegated to Excel/LibreOffice after opening the output file."],
    }
    out = Path(args.plan).resolve()
    if out.exists() and not args.force:
        die(f"Plan already exists: {out}. Use --force to replace it.")
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    json_out({"plan": str(out), "summary": plan["preflight"], "exact_edits": len(edits), "review_before_apply": True})


def copy_column_presentation(sheet, source_col: int, target_col: int, first_row: int, last_row: int) -> None:
    source_letter, target_letter = get_column_letter(source_col), get_column_letter(target_col)
    sheet.column_dimensions[target_letter].width = sheet.column_dimensions[source_letter].width
    sheet.column_dimensions[target_letter].hidden = sheet.column_dimensions[source_letter].hidden
    for row in range(first_row, last_row + 1):
        source, target = sheet.cell(row, source_col), sheet.cell(row, target_col)
        target._style = copy(source._style)
        target.number_format = source.number_format
        target.font = copy(source.font)
        target.fill = copy(source.fill)
        target.border = copy(source.border)
        target.alignment = copy(source.alignment)
        target.protection = copy(source.protection)


def split_qualified(address: str) -> tuple[str, str]:
    if "!" not in address:
        die(f"Plan cell must be sheet-qualified: {address}")
    return address.rsplit("!", 1)


def command_apply(args) -> None:
    plan_path = Path(args.plan).resolve()
    if not plan_path.is_file():
        die(f"Plan not found: {plan_path}")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    source = Path(args.workbook).resolve()
    output = Path(args.output).resolve()
    if source == output:
        die("Output must be a new file. The source workbook is never overwritten.")
    if plan.get("source_sha256") != sha256(source):
        die("Workbook changed after planning. Create and review a new plan before writing.")
    if output.exists() and not args.force:
        die(f"Output already exists: {output}. Use --force only after reviewing it.")
    book = load_book(source, data_only=False)
    sheet = resolve_sheet(book, plan["sheet"])
    target_col = column_index_from_string(plan["target_column"])
    template_col = column_index_from_string(plan["template_column"])
    first_row, last_row = plan["header_row"], sheet.max_row
    assert_target_safe(sheet, target_col, plan["header_row"], first_row, last_row)
    copy_column_presentation(sheet, template_col, target_col, first_row, last_row)
    for edit in plan["edits"]:
        sheet_name, address = split_qualified(edit["cell"])
        if sheet_name != sheet.title:
            die("Cross-sheet edits are not allowed in a participant-column plan.")
        sheet[address].value = edit["value"]
    output.parent.mkdir(parents=True, exist_ok=True)
    book.save(output)
    verification = verify_plan(output, plan)
    if not verification["ok"]:
        die("Output was written but verification failed: " + "; ".join(verification["errors"]))
    json_out({"output": str(output), "verification": verification, "source_unchanged_sha256": sha256(source) == plan["source_sha256"]})


def verify_plan(workbook: Path, plan: dict[str, Any]) -> dict[str, Any]:
    book = load_book(workbook, data_only=False)
    errors = []
    checked = 0
    for edit in plan["edits"]:
        sheet_name, address = split_qualified(edit["cell"])
        actual = book[sheet_name][address].value
        if actual != edit["value"]:
            errors.append(f"{edit['cell']}: expected {edit['value']!r}, found {actual!r}")
        checked += 1
    actual_formula_fingerprint = formula_fingerprint(book)
    expected_formula_fingerprint = plan.get("source_formula_fingerprint")
    if expected_formula_fingerprint and actual_formula_fingerprint != expected_formula_fingerprint:
        errors.append("Formula locations or formula text changed outside the reviewed value edits.")
    return {"ok": not errors, "checked_cells": checked, "formula_fingerprint": actual_formula_fingerprint, "errors": errors}


def command_verify(args) -> None:
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    json_out(verify_plan(Path(args.workbook), plan))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Coordinate-accurate Excel reader and safe participant-column writer")
    commands = root.add_subparsers(dest="command", required=True)
    for name, func in (("inspect", command_inspect), ("sheet", command_sheet), ("range", command_range), ("trace", command_trace), ("apply", command_apply), ("verify", command_verify)):
        sub = commands.add_parser(name)
        sub.set_defaults(func=func)
        sub.add_argument("workbook")
        if name == "sheet":
            sub.add_argument("--sheet", required=True); sub.add_argument("--rows", type=int, default=40); sub.add_argument("--cols", type=int, default=20)
        elif name == "range":
            sub.add_argument("--sheet", required=True); sub.add_argument("--range", required=True)
        elif name == "trace":
            sub.add_argument("--cell", required=True)
        elif name in {"apply", "verify"}:
            sub.add_argument("--plan", required=True)
            if name == "apply": sub.add_argument("--output", required=True); sub.add_argument("--force", action="store_true")
    sub = commands.add_parser("plan-participants")
    sub.set_defaults(func=command_plan_participants)
    sub.add_argument("workbook"); sub.add_argument("--sheet", required=True); sub.add_argument("--header-row", required=True, type=int)
    sub.add_argument("--id-header", required=True); sub.add_argument("--template-header", required=True); sub.add_argument("--target-column", required=True); sub.add_argument("--new-header", required=True)
    sub.add_argument("--results", required=True); sub.add_argument("--results-id-column", required=True); sub.add_argument("--results-value-column", required=True); sub.add_argument("--plan", required=True); sub.add_argument("--force", action="store_true")
    return root


def main() -> None:
    args = parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

# Recommended workflow for an existing complex Excel file (run in this folder):
# 1) Inspect workbook structure and locate the correct Sheet:
#    python excel_agent.py inspect "C:\\path\\to\\workbook.xlsx"
# 2) Read an exact region including cell coordinates and formulas:
#    python excel_agent.py range "C:\\path\\to\\workbook.xlsx" --sheet "Workshop" --range "A1:Z40"
# 3) Trace direct formula references of one exact cell:
#    python excel_agent.py trace "C:\\path\\to\\workbook.xlsx" --cell "Workshop!D37"
# 4) Create (but do not apply) a reviewable plan. Target column must already be empty:
#    python excel_agent.py plan-participants "C:\\path\\to\\workbook.xlsx" --sheet "Workshop" --header-row 1 --id-header "BG-ID" --template-header "Jonas" --target-column "M" --new-header "Berk" --results "C:\\path\\to\\berk_results.xlsx" --results-id-column "BG-ID" --results-value-column "Judgement" --plan "C:\\path\\to\\berk_plan.json"
# 5) Review berk_plan.json. Only then create a NEW workbook and verify every planned cell:
#    python excel_agent.py apply "C:\\path\\to\\workbook.xlsx" --plan "C:\\path\\to\\berk_plan.json" --output "C:\\path\\to\\workbook_with_berk.xlsx"
# 6) Re-run an independent verification at any time:
#    python excel_agent.py verify "C:\\path\\to\\workbook_with_berk.xlsx" --plan "C:\\path\\to\\berk_plan.json"
