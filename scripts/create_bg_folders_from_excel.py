"""Create BG folders and their Bilder subfolders from an Excel list.

Excel format (first worksheet):
    A = Baugruppenklasse
    B = SAP-Nummer (preferred folder name)
    C = Teamcenter  (fallback folder name)

Direct execution in VS Code:
    1. The paths below already match C:\\Users\\wdu4fe\\Downloads\\70BG.
    2. Keep DRY_RUN = True for the first run (preview only).
    3. After checking the output, change DRY_RUN to False and run again.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from openpyxl import load_workbook


# ===== Configuration for direct execution with the VS Code Run button =====
EXCEL_PATH = Path(r"C:\Users\YOUR_NAME\Downloads\70BG\70BG.xlsx")
BASE_PATH = Path(r"C:\Users\YOUR_NAME\Downloads\70BG")
DRY_RUN = True  # True = preview only; False = actually create folders
# ========================================================================

VALID_CLASSES = {
    "Keine der verfügbaren Klassen",
    "Kombinierte Einheit",
    "Lineareinheit",
    "Multi-Achs-System (Gantry)",
    "Roboter",
    "Rotationseinheit",
    "Greifer",
}


def cell_text(value: object) -> str:
    """Return a clean identifier without turning an integer into e.g. '123.0'."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def create_folders(excel_path: Path, base_path: Path, dry_run: bool) -> None:
    if not excel_path.is_file():
        raise FileNotFoundError(f"Excel file not found: {excel_path}")
    if not base_path.is_dir():
        raise NotADirectoryError(f"Base folder not found: {base_path}")

    # data_only=True reads the displayed result of formulas instead of formula text.
    workbook = load_workbook(excel_path, read_only=True, data_only=True)
    sheet = workbook.active

    created = existing = skipped = 0

    try:
        # Row 1 is the header. A, B and C are read as class, SAP and Teamcenter.
        for row_number, row in enumerate(
            sheet.iter_rows(min_row=2, min_col=1, max_col=3, values_only=True),
            start=2,
        ):
            baugruppenklasse, sap_nummer, teamcenter = map(cell_text, row)

            if not baugruppenklasse:
                continue

            # SAP has priority. If it is empty, Teamcenter is used.
            folder_name = sap_nummer or teamcenter
            if not folder_name:
                print(f"WARNING Row {row_number}: SAP and Teamcenter are both empty — skipped.")
                skipped += 1
                continue

            if baugruppenklasse not in VALID_CLASSES:
                print(
                    f"WARNING Row {row_number}: unknown Baugruppenklasse "
                    f"'{baugruppenklasse}' — skipped."
                )
                skipped += 1
                continue

            class_folder = base_path / baugruppenklasse
            if not class_folder.is_dir():
                print(f"WARNING Row {row_number}: class folder missing: {class_folder} — skipped.")
                skipped += 1
                continue

            target_folder = class_folder / folder_name
            bilder_folder = target_folder / "Bilder"
            if target_folder.exists():
                print(f"EXISTS  {target_folder}")
                existing += 1
            elif dry_run:
                print(f"PREVIEW {target_folder}")
                created += 1
            else:
                target_folder.mkdir()
                print(f"CREATED {target_folder}")
                created += 1

            # Each individual BG folder receives a place for CAD screenshots.
            if bilder_folder.exists():
                print(f"EXISTS  {bilder_folder}")
            elif dry_run:
                print(f"PREVIEW {bilder_folder}")
            else:
                bilder_folder.mkdir()
                print(f"CREATED {bilder_folder}")
    finally:
        workbook.close()

    action = "would be created" if dry_run else "created"
    print(f"\nDone: {created} {action}; {existing} already existed; {skipped} skipped.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create BG subfolders from the first worksheet of an Excel file."
    )
    parser.add_argument("--excel", type=Path, help="Path to the Excel file")
    parser.add_argument("--base", type=Path, help="Path containing the seven class folders")
    parser.add_argument(
        "--create",
        action="store_true",
        help="Actually create folders. Without this option, only a preview is shown.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        # Command-line paths take priority. With no arguments, use the VS Code settings above.
        excel_path = args.excel or EXCEL_PATH
        base_path = args.base or BASE_PATH
        dry_run = not args.create if args.excel or args.base or args.create else DRY_RUN
        create_folders(excel_path, base_path, dry_run)
    except (FileNotFoundError, NotADirectoryError, PermissionError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)


# Terminal commands (the script, Excel file and class folders are all in Downloads\\70BG):
#
# Preview only (no folders are created):
# python scripts/create_bg_folders_from_excel.py --excel "C:\Users\YOUR_NAME\Downloads\70BG\70BG.xlsx" --base "C:\Users\YOUR_NAME\Downloads\70BG"
#
# Actually create the folders:
# python scripts/create_bg_folders_from_excel.py --excel "C:\Users\YOUR_NAME\Downloads\70BG\70BG.xlsx" --base "C:\Users\YOUR_NAME\Downloads\70BG" --create
