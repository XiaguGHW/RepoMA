"""Print BGs from neuBG.xlsx that already occur in 129BG.xlsx.

Both workbooks are read from their first worksheet.  A row counts as a duplicate
when either its SAP number or its Teamcenter ID occurs in the other workbook.
The script only reads Excel files and prints the result; it does not create or
modify any files.
"""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_NEW_EXCEL = SCRIPT_DIR / "neuBG.xlsx"
DEFAULT_REFERENCE_EXCEL = SCRIPT_DIR / "129BG.xlsx"

SAP_COLUMN_CANDIDATES = (
    "SAP-Nummer",
    "SAP Nummer",
    "SAP-Nummer ",
    "SAP",
    "Baugruppennummer",
    "Baugruppen-ID",
    "Baugruppen_ID",
    "HBG",
)
TEAMCENTER_COLUMN_CANDIDATES = (
    "Teamcenter",
    "Teamcenter ID",
    "Teamcenter-ID",
    "Teamcenter Nummer",
    "Teamcenter-Nummer",
    "TC ID",
    "TC-ID",
)
CLASS_COLUMN_CANDIDATES = (
    "Baugruppen-Klasse",
    "Baugruppen Klasse",
    "Baugruppenklasse",
    "Funktionsklasse",
    "Funktions-Klasse",
    "Klasse",
)


def clean_identifier(value: object) -> str:
    """Convert an Excel cell to a comparable SAP or Teamcenter identifier."""
    if pd.isna(value):
        return ""
    identifier = str(value).strip()
    if re.fullmatch(r"\d+\.0", identifier):
        return identifier[:-2]
    return identifier


def identifier_key(value: object) -> str:
    """Ignore casing and accidental whitespace, but keep all identifier characters."""
    return re.sub(r"\s+", "", clean_identifier(value)).casefold()


def find_column(columns: pd.Index, candidates: tuple[str, ...]) -> str | None:
    normalized = {clean_identifier(column).casefold(): str(column) for column in columns}
    for candidate in candidates:
        column = normalized.get(candidate.casefold())
        if column:
            return column
    return None


def index_identifiers(dataframe: pd.DataFrame, column: str | None) -> dict[str, list[int]]:
    """Map each non-empty identifier to its Excel row numbers."""
    index: dict[str, list[int]] = defaultdict(list)
    if column is None:
        return index
    for excel_row, value in enumerate(dataframe[column], start=2):
        key = identifier_key(value)
        if key:
            index[key].append(excel_row)
    return index


def display_identifier(row: pd.Series, column: str | None) -> str:
    return clean_identifier(row[column]) if column else ""


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print SAP/Teamcenter duplicates between neuBG.xlsx and 129BG.xlsx."
    )
    parser.add_argument(
        "--new-excel",
        type=Path,
        default=DEFAULT_NEW_EXCEL,
        help="New BG workbook; its first sheet is read (default: neuBG.xlsx next to script).",
    )
    parser.add_argument(
        "--reference-excel",
        type=Path,
        default=DEFAULT_REFERENCE_EXCEL,
        help="Existing BG workbook; its first sheet is read (default: 129BG.xlsx next to script).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    new_excel = args.new_excel.expanduser()
    reference_excel = args.reference_excel.expanduser()
    for workbook in (new_excel, reference_excel):
        if not workbook.is_file():
            raise FileNotFoundError(f"Excel file not found: {workbook}")

    new_data = pd.read_excel(new_excel, sheet_name=0, dtype=str)
    reference_data = pd.read_excel(reference_excel, sheet_name=0, dtype=str)

    new_sap = find_column(new_data.columns, SAP_COLUMN_CANDIDATES)
    new_tc = find_column(new_data.columns, TEAMCENTER_COLUMN_CANDIDATES)
    reference_sap = find_column(reference_data.columns, SAP_COLUMN_CANDIDATES)
    reference_tc = find_column(reference_data.columns, TEAMCENTER_COLUMN_CANDIDATES)
    new_class = find_column(new_data.columns, CLASS_COLUMN_CANDIDATES)
    reference_class = find_column(reference_data.columns, CLASS_COLUMN_CANDIDATES)

    if not (new_sap or new_tc):
        raise ValueError(
            f"No SAP or Teamcenter column found in {new_excel.name}. "
            f"Columns: {list(new_data.columns)}"
        )
    if not (reference_sap or reference_tc):
        raise ValueError(
            f"No SAP or Teamcenter column found in {reference_excel.name}. "
            f"Columns: {list(reference_data.columns)}"
        )

    reference_sap_index = index_identifiers(reference_data, reference_sap)
    reference_tc_index = index_identifiers(reference_data, reference_tc)

    print(f"New BG file: {new_excel}")
    print(f"Reference BG file: {reference_excel}")
    print(f"New columns: SAP={new_sap or '-'}, Teamcenter={new_tc or '-'}")
    print(f"Reference columns: SAP={reference_sap or '-'}, Teamcenter={reference_tc or '-'}")
    print(f"Category column used for summary: {reference_class or new_class or '-'}")
    print()

    duplicate_count = 0
    duplicates_by_category: dict[str, set[int]] = defaultdict(set)
    for new_row_number, (_, row) in enumerate(new_data.iterrows(), start=2):
        sap = display_identifier(row, new_sap)
        teamcenter = display_identifier(row, new_tc)
        sap_rows = reference_sap_index.get(identifier_key(sap), []) if sap else []
        tc_rows = reference_tc_index.get(identifier_key(teamcenter), []) if teamcenter else []

        if not (sap_rows or tc_rows):
            continue

        duplicate_count += 1
        matched_by: list[str] = []
        if sap_rows:
            matched_by.append(f"SAP {sap} (129BG Excel row(s): {', '.join(map(str, sap_rows))})")
        if tc_rows:
            matched_by.append(
                f"Teamcenter {teamcenter} (129BG Excel row(s): {', '.join(map(str, tc_rows))})"
            )

        # The 129BG category is preferred because it is the established class of
        # the already existing BG.  If it is absent, use the category in neuBG.
        categories: set[str] = set()
        if reference_class:
            for reference_row in set(sap_rows + tc_rows):
                category = clean_identifier(reference_data.iloc[reference_row - 2][reference_class])
                if category:
                    categories.add(category)
        if not categories and new_class:
            category = clean_identifier(row[new_class])
            if category:
                categories.add(category)
        for category in categories:
            duplicates_by_category[category].add(new_row_number)

        identifiers = ", ".join(
            item for item in (f"SAP={sap}" if sap else "", f"TC={teamcenter}" if teamcenter else "") if item
        )
        print(f"Duplicate — neuBG Excel row {new_row_number}: {identifiers}")
        print(f"  Match: {'; '.join(matched_by)}")
        if categories:
            print(f"  Category: {' / '.join(sorted(categories))}")

    print()
    if duplicate_count:
        print(f"Result: {duplicate_count} duplicate BG row(s) found.")
        if duplicates_by_category:
            print("Duplicates by category:")
            for category in sorted(duplicates_by_category, key=str.casefold):
                print(f"  {category}: {len(duplicates_by_category[category])}")
        else:
            print("No category column was available for a category summary.")
    else:
        print("Result: no duplicates found.")


if __name__ == "__main__":
    main()
