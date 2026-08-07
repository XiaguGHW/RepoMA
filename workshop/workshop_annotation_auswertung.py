"""Create the overview workbook for the workshop classification results.

How to use
----------
1. Set INPUT_DIR below to the absolute path of the folder containing all Excel
   files from the workshop.
2. Run:  python workshop_annotation_auswertung.py

The script reads only the FIRST sheet of every workbook.
It uses the column "ID" to match Baugruppen, so the reversed order in the
TN_B forms is handled automatically.  The output order is taken from one
TN_A form (all TN_A forms use the same order).
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


# ---------------------------------------------------------------------------
# Settings: only change INPUT_DIR if your folder is stored somewhere else.
# ---------------------------------------------------------------------------
INPUT_DIR = Path(r"C:\Users\YOUR_USERNAME\Documents\Workshop_06.08.2026")
GROUND_TRUTH_FILENAME = "Liste_Workshop_70_Baugruppe_2.Versuch.xlsx"
OUTPUT_FILENAME = "Workshop_Annotation_Auswertung_07.08.2026.xlsx"
PARTICIPANT_PREFIX = "KlassifikationWorkshop_Template_06.08.26_"


def normalise_header(value: Any) -> str:
    """Make header comparisons robust against spaces, hyphens and capitals."""
    text = "" if value is None else str(value)
    return re.sub(r"[^a-z0-9]", "", text.lower())


def normalise_id(value: Any) -> str:
    """Return one stable ID representation, including Excel integer IDs."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def find_column(headers: dict[str, int], *possible_names: str) -> int | None:
    for name in possible_names:
        column = headers.get(normalise_header(name))
        if column is not None:
            return column
    return None


def read_first_sheet(path: Path) -> tuple[list[str], list[list[Any]]]:
    """Read values from the first worksheet only (not any later sheets)."""
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook.worksheets[0]
        rows = list(sheet.iter_rows(values_only=True))
    finally:
        workbook.close()

    if not rows:
        raise ValueError(f"The first sheet of '{path.name}' is empty.")

    headers = ["" if value is None else str(value).strip() for value in rows[0]]
    return headers, [list(row) for row in rows[1:] if any(value is not None for value in row)]


def participant_name_from_filename(path: Path) -> str:
    """Use a short, readable participant label as the result-column header."""
    stem = path.stem
    suffix = stem.removeprefix(PARTICIPANT_PREFIX).strip(" _-")
    return suffix or stem


def column_value(row: list[Any], column: int | None) -> Any:
    return row[column] if column is not None and column < len(row) else None


def main() -> None:
    if not INPUT_DIR.is_dir():
        raise FileNotFoundError(
            "INPUT_DIR does not exist. Please enter the absolute path of your "
            f"workshop folder at the top of this script. Current value: {INPUT_DIR}"
        )

    ground_truth_path = INPUT_DIR / GROUND_TRUTH_FILENAME
    if not ground_truth_path.is_file():
        raise FileNotFoundError(
            f"Ground-truth file not found: '{GROUND_TRUTH_FILENAME}' in {INPUT_DIR}"
        )

    participant_files = sorted(
        path
        for path in INPUT_DIR.glob(f"{PARTICIPANT_PREFIX}*.xlsx")
        if not path.name.startswith("~$")
    )
    if not participant_files:
        raise FileNotFoundError(
            f"No participant files beginning with '{PARTICIPANT_PREFIX}' were found."
        )

    tn_a_files = [path for path in participant_files if "TN_A_" in path.name]
    if not tn_a_files:
        raise ValueError("No TN_A file was found. At least one TN_A form is needed for the output order.")
    order_source_path = tn_a_files[0]

    # Read the ground-truth sheet. The ID remains an internal matching key and
    # is intentionally not written to the overview, matching the old format.
    gt_headers, gt_rows = read_first_sheet(ground_truth_path)
    gt_header_map = {normalise_header(header): index for index, header in enumerate(gt_headers)}
    gt_id_col = find_column(gt_header_map, "ID")
    gt_truth_col = find_column(gt_header_map, "Ground Truth", "GroundTruth")
    if gt_id_col is None or gt_truth_col is None:
        raise ValueError(
            f"'{ground_truth_path.name}' must contain the columns 'ID' and 'Ground Truth' in its first sheet."
        )

    gt_by_id: dict[str, list[Any]] = {}
    for row in gt_rows:
        bg_id = normalise_id(column_value(row, gt_id_col))
        if not bg_id:
            continue
        if bg_id in gt_by_id:
            raise ValueError(f"Duplicate ID '{bg_id}' in '{ground_truth_path.name}'.")
        gt_by_id[bg_id] = row

    # The first TN_A form determines the required display order.
    order_headers, order_rows = read_first_sheet(order_source_path)
    order_header_map = {normalise_header(header): index for index, header in enumerate(order_headers)}
    order_id_col = find_column(order_header_map, "ID")
    if order_id_col is None:
        raise ValueError(f"'{order_source_path.name}' has no 'ID' column in its first sheet.")

    ordered_ids = [normalise_id(column_value(row, order_id_col)) for row in order_rows]
    ordered_ids = [bg_id for bg_id in ordered_ids if bg_id]
    duplicates = [bg_id for bg_id, count in Counter(ordered_ids).items() if count > 1]
    if duplicates:
        raise ValueError(f"Duplicate ID(s) in TN_A order source: {', '.join(duplicates[:10])}")
    if len(ordered_ids) != 70:
        print(f"Warning: TN_A form contains {len(ordered_ids)} non-empty IDs (70 were expected).")

    missing_gt = [bg_id for bg_id in ordered_ids if bg_id not in gt_by_id]
    if missing_gt:
        raise ValueError(
            "The following TN_A IDs are missing from the ground-truth file: "
            + ", ".join(missing_gt[:10])
        )

    # Read each participant's Baugruppen-Klasse column into an ID -> answer map.
    participant_results: list[tuple[str, dict[str, Any]]] = []
    for participant_path in participant_files:
        headers, rows = read_first_sheet(participant_path)
        header_map = {normalise_header(header): index for index, header in enumerate(headers)}
        id_col = find_column(header_map, "ID")
        class_col = find_column(header_map, "Baugruppen-Klasse", "Baugruppen Klasse")
        if id_col is None or class_col is None:
            raise ValueError(
                f"'{participant_path.name}' must contain 'ID' and 'Baugruppen-Klasse' in its first sheet."
            )

        answers: dict[str, Any] = {}
        for row in rows:
            bg_id = normalise_id(column_value(row, id_col))
            if not bg_id:
                continue
            if bg_id in answers:
                raise ValueError(f"Duplicate ID '{bg_id}' in '{participant_path.name}'.")
            answers[bg_id] = column_value(row, class_col)

        unknown_ids = sorted(set(answers) - set(ordered_ids))
        if unknown_ids:
            print(
                f"Warning: '{participant_path.name}' contains IDs not present in the TN_A order: "
                + ", ".join(unknown_ids[:10])
            )
        participant_results.append((participant_name_from_filename(participant_path), answers))

    # These five information columns reproduce the old Übersicht format.
    # If Baugruppenebene is absent in the new ground-truth file, the column is
    # kept empty so that Ground Truth remains in column F.
    info_columns = [
        ("SAP-Nummer", ("SAP-Nummer", "SAP Nummer")),
        ("Teamcenter ID", ("Teamcenter ID",)),
        ("Benennung (EN)", ("Benennung (EN)", "Benennung EN")),
        ("Benennung (DE)", ("Benennung (DE)", "Benennung DE")),
        ("Baugruppenebene", ("Baugruppenebene",)),
    ]
    info_source_columns = [find_column(gt_header_map, *names) for _, names in info_columns]

    output_path = INPUT_DIR / OUTPUT_FILENAME
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Übersicht"

    output_headers = [name for name, _ in info_columns] + ["Ground Truth"]
    output_headers.extend(name for name, _ in participant_results)
    sheet.append(output_headers)

    for bg_id in ordered_ids:
        gt_row = gt_by_id[bg_id]
        row_values = [column_value(gt_row, source_col) for source_col in info_source_columns]
        row_values.append(column_value(gt_row, gt_truth_col))
        row_values.extend(answers.get(bg_id) for _, answers in participant_results)
        sheet.append(row_values)

    # Simple, readable formatting for the generated overview.
    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(color="FFFFFF", bold=True)
    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    sheet.freeze_panes = "G2"
    sheet.auto_filter.ref = sheet.dimensions
    sheet.row_dimensions[1].height = 34

    preferred_widths = [18, 20, 32, 32, 18, 24] + [28] * len(participant_results)
    for index, width in enumerate(preferred_widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)

    workbook.save(output_path)

    print("Finished successfully.")
    print(f"TN_A order source: {order_source_path.name}")
    print(f"Participants included ({len(participant_results)}): " + ", ".join(name for name, _ in participant_results))
    print(f"Output file: {output_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
