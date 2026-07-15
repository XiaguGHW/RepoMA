"""Hauptbaugruppen in sieben Rohdaten-Kategorien finden und optional kopieren.

Erwartete Projektstruktur (dieses Skript liegt später unter ``scripts``)::

    Baugruppen_Datenvorverarbeitung/
    ├─ input/
    │  ├─ all_HBG_random_no_label.xlsx
    │  └─ raw_data/
    │     ├─ Datensatz - Gantry_Achssysteme/
    │     └─ ... weitere Kategorien
    ├─ output/
    │  ├─ processed_hbg/
    │  └─ reports/
    └─ scripts/
       └─ find_HBG.py

Normaler Aufruf erstellt nur Prüfberichte (keine Daten werden kopiert):
    python scripts/find_HBG.py

Erst nach Prüfung der Berichte kopieren:
    python scripts/find_HBG.py --copy
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd


EXCEL_FILENAME = "all_HBG_random_no_label.xlsx"
SHEET_NAME = "all_HBG_random_no_label"
SAP_COLUMN = "SAP-Nummer"
TEAMCENTER_COLUMN = "Teamcenter ID"
ID_PATTERN = re.compile(r"(?<![A-Z0-9])[A-Z0-9]{10}(?![A-Z0-9])")


def normalize_id(value: object) -> str:
    """Normalize an ID by trimming whitespace and converting it to uppercase."""
    if pd.isna(value):
        return ""
    return str(value).strip().upper()


def extract_ids_from_folder_name(folder_name: str) -> list[str]:
    """Extract independent 10-character alphanumeric IDs from a folder name."""
    normalized_name = normalize_id(folder_name)
    return list(dict.fromkeys(ID_PATTERN.findall(normalized_name)))


def write_report(path: Path, rows: list[dict], columns: list[str]) -> None:
    """Create an Excel report with column headers, even when there are no rows."""
    pd.DataFrame(rows, columns=columns).to_excel(path, index=False)


def project_paths() -> tuple[Path, Path, Path, Path]:
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    input_dir = project_root / "input"
    raw_data_dir = input_dir / "raw_data"
    processed_dir = project_root / "output" / "processed_hbg"
    reports_dir = project_root / "output" / "reports"
    return input_dir, raw_data_dir, processed_dir, reports_dir


def load_hbg_table(excel_path: Path) -> pd.DataFrame:
    if not excel_path.is_file():
        raise FileNotFoundError(f"Excel file does not exist: {excel_path}")

    workbook = pd.ExcelFile(excel_path)
    if SHEET_NAME not in workbook.sheet_names:
        available = ", ".join(workbook.sheet_names)
        raise ValueError(
            f"Worksheet '{SHEET_NAME}' was not found. Available worksheets: {available}"
        )

    df = pd.read_excel(
        excel_path,
        sheet_name=SHEET_NAME,
        dtype=str,
    )
    df.columns = [str(column).strip() for column in df.columns]

    missing_columns = [
        column
        for column in (SAP_COLUMN, TEAMCENTER_COLUMN)
        if column not in df.columns
    ]
    if missing_columns:
        raise ValueError(
            "The Excel file is missing the following columns: "
            + ", ".join(missing_columns)
            + ". Available columns: "
            + ", ".join(df.columns)
        )

    df = df[[SAP_COLUMN, TEAMCENTER_COLUMN]].copy()
    df[SAP_COLUMN] = df[SAP_COLUMN].map(normalize_id)
    df[TEAMCENTER_COLUMN] = df[TEAMCENTER_COLUMN].map(normalize_id)
    df = df[(df[SAP_COLUMN] != "") | (df[TEAMCENTER_COLUMN] != "")].copy()
    df.reset_index(drop=True, inplace=True)
    df["Excel_Zeile"] = df.index + 2
    return df


def build_id_index(df: pd.DataFrame) -> dict[str, list[dict]]:
    id_index: dict[str, list[dict]] = defaultdict(list)

    for row in df.to_dict("records"):
        for column in (SAP_COLUMN, TEAMCENTER_COLUMN):
            assembly_id = row[column]
            if assembly_id and not any(
                existing["Excel_Zeile"] == row["Excel_Zeile"]
                for existing in id_index[assembly_id]
            ):
                id_index[assembly_id].append(row)

    return dict(id_index)


def scan_folders(
    raw_data_dir: Path,
    id_index: dict[str, list[dict]],
) -> tuple[list[dict], list[dict], list[dict]]:
    if not raw_data_dir.is_dir():
        raise FileNotFoundError(f"The raw_data folder does not exist: {raw_data_dir}")

    matched: list[dict] = []
    not_matched: list[dict] = []
    ambiguous_folder_matches: list[dict] = []

    category_folders = sorted(
        (path for path in raw_data_dir.iterdir() if path.is_dir()),
        key=lambda path: path.name.casefold(),
    )
    if not category_folders:
        raise ValueError(f"No category folders were found in raw_data: {raw_data_dir}")

    for category_folder in category_folders:
        baugruppe_folders = sorted(
            (path for path in category_folder.iterdir() if path.is_dir()),
            key=lambda path: path.name.casefold(),
        )

        for folder in baugruppe_folders:
            folder_id = normalize_id(folder.name)
            candidate_ids = extract_ids_from_folder_name(folder.name)
            base = {
                "Ordnername": folder.name,
                "Urspruengliche_Kategorie": category_folder.name,
                "Quellpfad": str(folder.resolve()),
            }

            matched_ids = [
                candidate_id
                for candidate_id in candidate_ids
                if candidate_id in id_index
            ]
            matched_rows_by_number: dict[int, dict] = {}
            for matched_id in matched_ids:
                for excel_row in id_index[matched_id]:
                    matched_rows_by_number[int(excel_row["Excel_Zeile"])] = excel_row
            excel_rows = list(matched_rows_by_number.values())

            if not excel_rows:
                not_matched.append(base)
                continue

            if len(excel_rows) > 1:
                ambiguous_folder_matches.append(
                    {
                        **base,
                        "Anzahl_Excel_Treffer": len(excel_rows),
                        "Excel_Zeilen": ", ".join(
                            str(row["Excel_Zeile"]) for row in excel_rows
                        ),
                        "Gefundene_IDs": ", ".join(matched_ids),
                    }
                )
                continue

            excel_row = excel_rows[0]
            match_columns = []
            if excel_row[SAP_COLUMN] in matched_ids:
                match_columns.append(SAP_COLUMN)
            if excel_row[TEAMCENTER_COLUMN] in matched_ids:
                match_columns.append(TEAMCENTER_COLUMN)

            match_type = (
                "exact folder name"
                if folder_id in matched_ids
                else "ID contained in folder name"
            )

            matched.append(
                {
                    **base,
                    SAP_COLUMN: excel_row[SAP_COLUMN],
                    TEAMCENTER_COLUMN: excel_row[TEAMCENTER_COLUMN],
                    "Uebereinstimmung": " + ".join(match_columns),
                    "Gefundene_IDs": ", ".join(matched_ids),
                    "Trefferart": match_type,
                    "Excel_Zeile": excel_row["Excel_Zeile"],
                }
            )

    return matched, not_matched, ambiguous_folder_matches


def find_conflicts(
    df: pd.DataFrame,
    id_index: dict[str, list[dict]],
    matched: list[dict],
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    ambiguous_excel_ids = []
    for assembly_id, rows in sorted(id_index.items()):
        if len(rows) > 1:
            ambiguous_excel_ids.append(
                {
                    "Mehrdeutige_ID": assembly_id,
                    "Anzahl_Excel_Zeilen": len(rows),
                    "Excel_Zeilen": ", ".join(
                        str(row["Excel_Zeile"]) for row in rows
                    ),
                }
            )

    by_folder_name: dict[str, list[dict]] = defaultdict(list)
    by_excel_row: dict[int, list[dict]] = defaultdict(list)
    for row in matched:
        by_folder_name[normalize_id(row["Ordnername"])].append(row)
        by_excel_row[int(row["Excel_Zeile"])].append(row)

    duplicate_folder_names = []
    for folder_id, rows in sorted(by_folder_name.items()):
        if len(rows) > 1:
            duplicate_folder_names.append(
                {
                    "Ordnername": folder_id,
                    "Anzahl_Quellordner": len(rows),
                    "Kategorien": " | ".join(
                        row["Urspruengliche_Kategorie"] for row in rows
                    ),
                    "Quellpfade": " | ".join(row["Quellpfad"] for row in rows),
                }
            )

    multiple_folders_per_hbg = []
    for excel_row, rows in sorted(by_excel_row.items()):
        if len(rows) > 1:
            multiple_folders_per_hbg.append(
                {
                    "Excel_Zeile": excel_row,
                    SAP_COLUMN: rows[0][SAP_COLUMN],
                    TEAMCENTER_COLUMN: rows[0][TEAMCENTER_COLUMN],
                    "Anzahl_Quellordner": len(rows),
                    "Ordnernamen": " | ".join(row["Ordnername"] for row in rows),
                    "Quellpfade": " | ".join(row["Quellpfad"] for row in rows),
                }
            )

    matched_excel_rows = {int(row["Excel_Zeile"]) for row in matched}
    missing_hbg = []
    for row in df.to_dict("records"):
        if int(row["Excel_Zeile"]) not in matched_excel_rows:
            missing_hbg.append(
                {
                    "Excel_Zeile": row["Excel_Zeile"],
                    SAP_COLUMN: row[SAP_COLUMN],
                    TEAMCENTER_COLUMN: row[TEAMCENTER_COLUMN],
                }
            )

    return (
        ambiguous_excel_ids,
        duplicate_folder_names,
        multiple_folders_per_hbg,
        missing_hbg,
    )


def copy_hbg_folders(
    matched: list[dict],
    processed_dir: Path,
    reports_dir: Path,
) -> None:
    existing_items = list(processed_dir.iterdir())
    if existing_items:
        raise RuntimeError(
            "The processed_hbg folder is not empty. To prevent overwriting or "
            "mixing results, inspect and empty it manually before running --copy again."
        )

    copy_results = []
    has_error = False

    for number, row in enumerate(matched, start=1):
        source = Path(row["Quellpfad"])
        destination = processed_dir / row["Ordnername"]
        try:
            shutil.copytree(source, destination)
            status = "kopiert"
            error = ""
        except Exception as exc:  # Log the error without automatically deleting copied data.
            status = "Fehler"
            error = f"{type(exc).__name__}: {exc}"
            has_error = True

        copy_results.append(
            {
                "Nr": number,
                "Ordnername": row["Ordnername"],
                "Quellpfad": str(source),
                "Zielpfad": str(destination),
                "Status": status,
                "Fehler": error,
            }
        )
        print(f"[{number}/{len(matched)}] {row['Ordnername']}: {status}")

    write_report(
        reports_dir / "Kopierbericht.xlsx",
        copy_results,
        ["Nr", "Ordnername", "Quellpfad", "Zielpfad", "Status", "Fehler"],
    )

    if has_error:
        raise RuntimeError(
            "Some folders could not be copied. See output/reports/Kopierbericht.xlsx."
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Identify HBG folders by SAP or Teamcenter ID and optionally copy them."
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help="Copy HBG folders to output/processed_hbg after conflict checks pass.",
    )
    args = parser.parse_args()

    input_dir, raw_data_dir, processed_dir, reports_dir = project_paths()
    excel_path = input_dir / EXCEL_FILENAME
    processed_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    try:
        df = load_hbg_table(excel_path)
        id_index = build_id_index(df)
        matched, not_matched, ambiguous_folder_matches = scan_folders(
            raw_data_dir, id_index
        )
        (
            ambiguous_excel_ids,
            duplicate_folder_names,
            multiple_folders_per_hbg,
            missing_hbg,
        ) = find_conflicts(df, id_index, matched)

        write_report(
            reports_dir / "HBG_Ordnerliste.xlsx",
            matched,
            [
                "Ordnername",
                SAP_COLUMN,
                TEAMCENTER_COLUMN,
                "Uebereinstimmung",
                "Gefundene_IDs",
                "Trefferart",
                "Excel_Zeile",
                "Urspruengliche_Kategorie",
                "Quellpfad",
            ],
        )
        write_report(
            reports_dir / "nicht_zugeordnet.xlsx",
            not_matched,
            ["Ordnername", "Urspruengliche_Kategorie", "Quellpfad"],
        )
        write_report(
            reports_dir / "mehrdeutige_Ordnerzuordnung.xlsx",
            ambiguous_folder_matches,
            [
                "Ordnername",
                "Urspruengliche_Kategorie",
                "Quellpfad",
                "Anzahl_Excel_Treffer",
                "Excel_Zeilen",
                "Gefundene_IDs",
            ],
        )
        write_report(
            reports_dir / "mehrdeutige_Excel_IDs.xlsx",
            ambiguous_excel_ids,
            ["Mehrdeutige_ID", "Anzahl_Excel_Zeilen", "Excel_Zeilen"],
        )
        write_report(
            reports_dir / "doppelte_Ordnernamen.xlsx",
            duplicate_folder_names,
            ["Ordnername", "Anzahl_Quellordner", "Kategorien", "Quellpfade"],
        )
        write_report(
            reports_dir / "mehrere_Ordner_pro_HBG.xlsx",
            multiple_folders_per_hbg,
            [
                "Excel_Zeile",
                SAP_COLUMN,
                TEAMCENTER_COLUMN,
                "Anzahl_Quellordner",
                "Ordnernamen",
                "Quellpfade",
            ],
        )
        write_report(
            reports_dir / "fehlende_HBG.xlsx",
            missing_hbg,
            ["Excel_Zeile", SAP_COLUMN, TEAMCENTER_COLUMN],
        )

        blocking_conflicts = (
            ambiguous_folder_matches
            or ambiguous_excel_ids
            or duplicate_folder_names
            or multiple_folders_per_hbg
        )

        print("\nCheck completed (the source data was not modified)")
        print(f"HBG rows in the Excel file: {len(df)}")
        print(f"Successfully matched folders: {len(matched)}")
        print(f"Unmatched source folders: {len(not_matched)}")
        print(f"HBG entries without a matching folder: {len(missing_hbg)}")
        print(f"Conflicts requiring review: {sum(map(len, [ambiguous_folder_matches, ambiguous_excel_ids, duplicate_folder_names, multiple_folders_per_hbg]))}")
        print(f"Report location: {reports_dir}")

        if args.copy:
            if blocking_conflicts:
                raise RuntimeError(
                    "No folders were copied because ID or folder conflicts exist. "
                    "Review the conflict reports first."
                )
            copy_hbg_folders(matched, processed_dir, reports_dir)
            print(f"\nCopy completed: {processed_dir}")
        else:
            print("\nThe script ran in check mode; no folders were copied.")
            print("After verifying the reports, run: python scripts/find_HBG.py --copy")

        return 0

    except Exception as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
