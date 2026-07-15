"""Testlauf: Klassifikation der ersten 5 Hauptbaugruppen mit Gemini.

Der Test verwendet:
  - den Baugruppennamen aus all_HBG_random_no_label.xlsx
  - alle zugehoerigen Dateien mit use_for_gemini = priority_1_candidate
  - die erlaubten Klassen aus Functional_classes.xlsx

Die Eingabedateien werden nicht veraendert. Antworten, Logs und Ergebnisse
werden in den vorhandenen output-Unterordnern gespeichert.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


# =============================================================================
# KONFIGURATION
# =============================================================================

SCRIPT_DIR = Path(__file__).resolve().parent
# Empfohlen: Skript direkt im Projektordner. Fuer den ersten Test funktioniert
# es aber auch, wenn es versehentlich noch im Unterordner "prompts" liegt.
if (SCRIPT_DIR / "input").is_dir():
    PROJECT_DIR = SCRIPT_DIR
elif (SCRIPT_DIR.parent / "input").is_dir():
    PROJECT_DIR = SCRIPT_DIR.parent
else:
    PROJECT_DIR = SCRIPT_DIR
INPUT_DIR = PROJECT_DIR / "input"
if (INPUT_DIR / "processed_HBG").is_dir():
    PROCESSED_HBG_DIR = INPUT_DIR / "processed_HBG"
else:
    PROCESSED_HBG_DIR = INPUT_DIR
OUTPUT_DIR = PROJECT_DIR / "output"
LOG_DIR = OUTPUT_DIR / "logs"
RESPONSES_DIR = OUTPUT_DIR / "responses"
RESULTS_DIR = OUTPUT_DIR / "results"

HBG_EXCEL_PATH = INPUT_DIR / "all_HBG_random_no_label.xlsx"
INVENTORY_EXCEL_PATH = INPUT_DIR / "file_inventory.xlsx"
CLASSES_EXCEL_PATH = INPUT_DIR / "Functional_classes.xlsx"

INVENTORY_SHEET = "file_inventory"
PREFERRED_CLASSES_SHEET = "Funktionsklassen_v3"

TEST_LIMIT = 5
RUN_API = True  # False = nur Matching und Dateipruefung, kein Gemini-Aufruf

MODEL_NAME = "gemini-2.5-pro"
BOSCH_FARM_API_KEY = ""  # Bosch Farm API Key zwischen die Anfuehrungszeichen setzen
GENERATION_CONFIG = {
    "temperature": 0.1,
    "topP": 0.95,
    "candidateCount": 1,
    "maxOutputTokens": 1000,
}
API_RETRIES = 2

# Spalten in all_HBG_random_no_label.xlsx
ID_COL = "ID"
SAP_COL = "SAP-Nummer"
TEAMCENTER_COL = "Teamcenter ID"
NAME_COL = "Benennung (EN)"

# Spalten im Sheet file_inventory
INVENTORY_FOLDER_COL = "folder_name"
INVENTORY_SUBFOLDER_COL = "relative_subfolder"
INVENTORY_FILENAME_COL = "file_name"
INVENTORY_FULL_PATH_COL = "file_path"
INVENTORY_PRIORITY_COL = "use_for_gemini"
PRIORITY_1_VALUE = "priority_1_candidate"

FUNCTIONAL_CLASS_COL = "Funktionsklasse"

RUN_TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_PATH = LOG_DIR / f"gemini_first5_test_{RUN_TIMESTAMP}.log"
RESULT_PATH = RESULTS_DIR / f"gemini_first5_test_{RUN_TIMESTAMP}.xlsx"
RAW_RESPONSES_PATH = (
    RESPONSES_DIR / f"gemini_first5_responses_{RUN_TIMESTAMP}.jsonl"
)


# =============================================================================
# HILFSFUNKTIONEN
# =============================================================================

def ensure_directories() -> None:
    """Erstellt die vorgesehenen Ausgabeordner, falls sie noch fehlen."""
    for directory in (LOG_DIR, RESPONSES_DIR, RESULTS_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )


def clean_cell(value: Any) -> str:
    """Konvertiert einen Excel-Zellwert sicher in einen bereinigten String."""
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if text.casefold() in {"nan", "none"}:
        return ""
    return text


def normalize_identifier(value: Any) -> str:
    """Normalisiert SAP-, Teamcenter- und Ordnernamen fuer den Vergleich."""
    return re.sub(r"[^A-Z0-9]", "", clean_cell(value).upper())


def require_columns(df: pd.DataFrame, required: list[str], source: str) -> None:
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(
            f"In {source} fehlen Spalten: {missing}. "
            f"Gefundene Spalten: {list(df.columns)}"
        )


def load_classes_with_detected_header(
    excel_path: Path,
) -> tuple[list[str], str, int]:
    """Findet Sheet und Kopfzeile mit der Spalte 'Funktionsklasse'."""
    excel_file = pd.ExcelFile(excel_path)
    sheets = list(excel_file.sheet_names)
    if PREFERRED_CLASSES_SHEET in sheets:
        sheets.remove(PREFERRED_CLASSES_SHEET)
        sheets.insert(0, PREFERRED_CLASSES_SHEET)

    for sheet_name in sheets:
        raw_df = pd.read_excel(
            excel_path,
            sheet_name=sheet_name,
            header=None,
            dtype=str,
        )

        for header_index, row in raw_df.iterrows():
            values = {clean_cell(value).casefold() for value in row.tolist()}
            if FUNCTIONAL_CLASS_COL.casefold() not in values:
                continue

            classes_df = pd.read_excel(
                excel_path,
                sheet_name=sheet_name,
                header=header_index,
                dtype=str,
            )
            require_columns(
                classes_df,
                [FUNCTIONAL_CLASS_COL],
                f"{excel_path.name}, Sheet {sheet_name}",
            )
            classes = (
                classes_df[FUNCTIONAL_CLASS_COL]
                .dropna()
                .map(clean_cell)
                .loc[lambda series: series.ne("")]
                .drop_duplicates()
                .tolist()
            )
            if not classes:
                raise ValueError(
                    f"Keine Funktionsklassen in Sheet {sheet_name} gefunden."
                )
            return classes, sheet_name, int(header_index)

    raise ValueError(
        f"Die Spalte '{FUNCTIONAL_CLASS_COL}' wurde in keinem Sheet von "
        f"{excel_path.name} gefunden. Sheets: {excel_file.sheet_names}"
    )


def load_input_data() -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """Laedt und validiert die drei Eingabetabellen."""
    for path in (HBG_EXCEL_PATH, INVENTORY_EXCEL_PATH, CLASSES_EXCEL_PATH):
        if not path.is_file():
            raise FileNotFoundError(f"Eingabedatei nicht gefunden: {path}")
    if not PROCESSED_HBG_DIR.is_dir():
        raise FileNotFoundError(
            f"Ordner mit den Baugruppendaten nicht gefunden: {PROCESSED_HBG_DIR}"
        )

    hbg_df = pd.read_excel(HBG_EXCEL_PATH, dtype=str).fillna("")
    inventory_df = pd.read_excel(
        INVENTORY_EXCEL_PATH,
        sheet_name=INVENTORY_SHEET,
        dtype=str,
    ).fillna("")

    require_columns(
        hbg_df,
        [ID_COL, SAP_COL, TEAMCENTER_COL, NAME_COL],
        HBG_EXCEL_PATH.name,
    )
    require_columns(
        inventory_df,
        [
            INVENTORY_FOLDER_COL,
            INVENTORY_SUBFOLDER_COL,
            INVENTORY_FILENAME_COL,
            INVENTORY_PRIORITY_COL,
        ],
        f"{INVENTORY_EXCEL_PATH.name}, Sheet {INVENTORY_SHEET}",
    )

    classes, class_sheet, header_index = load_classes_with_detected_header(
        CLASSES_EXCEL_PATH
    )

    logging.info("HBG-Tabelle geladen: %s Zeilen", len(hbg_df))
    logging.info("File Inventory geladen: %s Dateien", len(inventory_df))
    logging.info(
        "Funktionsklassen geladen: %s Klassen aus Sheet '%s', Excel-Zeile %s",
        len(classes),
        class_sheet,
        header_index + 1,
    )
    return hbg_df, inventory_df, classes


def match_baugruppe_folder(
    sap_number: str,
    teamcenter_id: str,
    folder_names: list[str],
) -> tuple[str | None, str, str]:
    """Ordnet eine HBG eindeutig einem Inventory-Baugruppenordner zu.

    Reihenfolge:
      1. Ordnername entspricht exakt SAP oder Teamcenter ID.
      2. Ordnername enthaelt SAP oder Teamcenter ID.
      3. Mehrdeutige Treffer werden nicht automatisch ausgewaehlt.
    """
    identifiers = {
        "SAP": normalize_identifier(sap_number),
        "TEAMCENTER": normalize_identifier(teamcenter_id),
    }
    identifiers = {key: value for key, value in identifiers.items() if value}
    if not identifiers:
        return None, "NO_IDENTIFIER", "SAP-Nummer und Teamcenter ID fehlen"

    exact_candidates: list[tuple[str, list[str]]] = []
    contains_candidates: list[tuple[str, list[str]]] = []

    for folder_name in folder_names:
        folder_normalized = normalize_identifier(folder_name)
        if not folder_normalized:
            continue

        exact_methods = [
            identifier_name
            for identifier_name, identifier in identifiers.items()
            if folder_normalized == identifier
        ]
        if exact_methods:
            exact_candidates.append((folder_name, exact_methods))
            continue

        contains_methods = [
            identifier_name
            for identifier_name, identifier in identifiers.items()
            if identifier in folder_normalized
        ]
        if contains_methods:
            contains_candidates.append((folder_name, contains_methods))

    if len(exact_candidates) == 1:
        folder, methods = exact_candidates[0]
        return folder, "EXACT_" + "+".join(methods), ""
    if len(exact_candidates) > 1:
        folders = ", ".join(candidate[0] for candidate in exact_candidates)
        return None, "AMBIGUOUS_EXACT", f"Mehrere exakte Treffer: {folders}"

    if len(contains_candidates) == 1:
        folder, methods = contains_candidates[0]
        return folder, "CONTAINS_" + "+".join(methods), ""

    if len(contains_candidates) > 1 and len(identifiers) > 1:
        both_id_candidates = [
            candidate
            for candidate in contains_candidates
            if len(candidate[1]) == len(identifiers)
        ]
        if len(both_id_candidates) == 1:
            folder, methods = both_id_candidates[0]
            return folder, "CONTAINS_" + "+".join(methods), ""

    if len(contains_candidates) > 1:
        folders = ", ".join(candidate[0] for candidate in contains_candidates)
        return None, "AMBIGUOUS_CONTAINS", f"Mehrere Teiltreffer: {folders}"

    return None, "NOT_FOUND", "Kein Ordner enthaelt SAP- oder Teamcenter-ID"


def build_current_file_path(inventory_row: pd.Series, folder_name: str) -> Path:
    """Erzeugt einen portablen Pfad innerhalb des aktuellen Testprojekts."""
    subfolder = clean_cell(inventory_row[INVENTORY_SUBFOLDER_COL])
    filename = clean_cell(inventory_row[INVENTORY_FILENAME_COL])

    path = PROCESSED_HBG_DIR / folder_name
    if subfolder not in {"", ".", "./", ".\\"}:
        path = path / Path(subfolder)
    return path / filename


def select_priority_1_files(
    inventory_df: pd.DataFrame,
    folder_name: str,
) -> tuple[list[Path], list[Path], list[dict[str, str]]]:
    """Waehlt alle P1-Dateien des gematchten Baugruppenordners aus."""
    folder_mask = inventory_df[INVENTORY_FOLDER_COL].map(clean_cell).eq(folder_name)
    priority_mask = (
        inventory_df[INVENTORY_PRIORITY_COL]
        .map(clean_cell)
        .str.casefold()
        .eq(PRIORITY_1_VALUE.casefold())
    )
    selected_rows = inventory_df.loc[folder_mask & priority_mask].copy()
    selected_rows = selected_rows.sort_values(
        by=INVENTORY_FILENAME_COL,
        key=lambda series: series.astype(str).str.casefold(),
    )

    existing_files: list[Path] = []
    missing_files: list[Path] = []
    file_details: list[dict[str, str]] = []
    seen_paths: set[str] = set()

    for _, inventory_row in selected_rows.iterrows():
        current_path = build_current_file_path(inventory_row, folder_name)
        path_source = "current_processed_HBG"
        selected_path = current_path

        # Nur als Rueckfall: alter absoluter Inventory-Pfad, falls er noch gilt.
        if not selected_path.is_file() and INVENTORY_FULL_PATH_COL in inventory_df.columns:
            old_full_path_text = clean_cell(inventory_row[INVENTORY_FULL_PATH_COL])
            if old_full_path_text:
                old_full_path = Path(old_full_path_text)
                if old_full_path.is_file():
                    selected_path = old_full_path
                    path_source = "inventory_full_path_fallback"

        normalized_path = os.path.normcase(str(selected_path.resolve(strict=False)))
        if normalized_path in seen_paths:
            continue
        seen_paths.add(normalized_path)

        exists = selected_path.is_file()
        if exists:
            existing_files.append(selected_path)
        else:
            missing_files.append(selected_path)

        file_details.append(
            {
                "Folder": folder_name,
                "Filename": clean_cell(inventory_row[INVENTORY_FILENAME_COL]),
                "Relative_Subfolder": clean_cell(
                    inventory_row[INVENTORY_SUBFOLDER_COL]
                ),
                "Resolved_Path": str(selected_path),
                "Path_Source": path_source,
                "Exists": "ja" if exists else "nein",
            }
        )

    return existing_files, missing_files, file_details


def build_prompt(baugruppenname: str, classes: list[str], files: list[Path]) -> str:
    """Baut den Zero-Shot-Prompt auf Basis des bisherigen Experiments."""
    classes_text = "\n".join(f"- {class_name}" for class_name in classes)
    files_text = "\n".join(f"- {path.name}" for path in files)

    return f"""
Du bist ein technischer Experte fuer Baugruppenklassifikation im Maschinen- und Anlagenbau.
Klassifiziere die folgende Baugruppe in genau eine der vorgegebenen Funktionsklassen.
Beruecksichtige dafuer sowohl den Baugruppennamen als auch alle beigefuegten Dateien.
Alle beigefuegten Dateien gehoeren zu derselben Baugruppe.
Der Baugruppenname ist ein besonders wichtiger Hinweis. Wenn der Name eindeutig
einer Funktionsklasse entspricht und die Dateien nicht klar widersprechen,
orientiere dich vorrangig am Baugruppennamen.

Baugruppenname:
{baugruppenname}

Beigefuegte Dateien:
{files_text}

Zulaessige Funktionsklassen:
{classes_text}

Regeln:
- Orientiere die Klassifikation immer an der Hauptfunktion der Baugruppe.
- Waehle genau eine Funktionsklasse aus der Liste.
- Antworte ausschliesslich mit dem exakten Namen der Funktionsklasse, nie mit einer Abkuerzung.
- Keine Erklaerung, keine zusaetzlichen Woerter.
- Wenn keine Klasse eindeutig passt, waehle "Nicht klassifizierbar".

Antwort:
""".strip()


def get_api_key() -> str:
    """Liest den API-Key aus der Konfiguration am Anfang dieses Skripts."""
    api_key = BOSCH_FARM_API_KEY.strip()
    if not api_key:
        raise ValueError(
            "BOSCH_FARM_API_KEY ist leer. Bitte den API Key am Anfang des "
            "Skripts zwischen die Anfuehrungszeichen setzen."
        )
    return api_key


def create_llm_connector() -> Any:
    """Importiert und initialisiert denselben Connector wie im alten Test."""
    try:
        # Aktuelle Struktur: einzelne .py-Datei im Projektordner.
        from Google_native_connector_multiplefiles_1 import BoschLLMConnector
    except ImportError:
        try:
            # Kompatibilitaet mit der Importform aus dem alten Zero-Shot-Skript.
            from Google.native_connector_multiplefiles_1 import BoschLLMConnector
        except ImportError as exc:
            raise ImportError(
                "BoschLLMConnector konnte nicht importiert werden. Erwartet wird "
                "Google_native_connector_multiplefiles_1.py im Projektordner "
                "oder das Python-Paket Google.native_connector_multiplefiles_1."
            ) from exc

    return BoschLLMConnector(model_name=MODEL_NAME, api_key=get_api_key())


def canonicalize_response(raw_response: str, classes: list[str]) -> tuple[str, bool]:
    """Prueft, ob Gemini exakt eine erlaubte Klasse ausgegeben hat."""
    cleaned = raw_response.strip().strip("`").strip().strip('"').strip("'").strip()
    class_map = {class_name.casefold(): class_name for class_name in classes}
    canonical = class_map.get(cleaned.casefold())
    if canonical is None:
        return cleaned, False
    return canonical, True


def ask_gemini(llm: Any, prompt: str, file_paths: list[Path]) -> str:
    """Fuehrt den Multidatei-Aufruf mit begrenzten Wiederholungen aus."""
    last_error: Exception | None = None
    for attempt in range(1, API_RETRIES + 1):
        try:
            answer = llm.ask_about_files(
                file_paths=[str(path) for path in file_paths],
                question=prompt,
                generation_config=GENERATION_CONFIG,
            )
            return str(answer).strip()
        except Exception as exc:  # Connector kann unterschiedliche Fehler liefern
            last_error = exc
            logging.warning(
                "API-Versuch %s/%s fehlgeschlagen: %s",
                attempt,
                API_RETRIES,
                exc,
            )
            if attempt < API_RETRIES:
                time.sleep(2 * attempt)

    raise RuntimeError(f"Gemini-Aufruf fehlgeschlagen: {last_error}")


def write_jsonl(path: Path, record: dict[str, Any]) -> None:
    """Speichert jede Antwort sofort, damit ein Abbruch nichts verliert."""
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def public_case_row(case: dict[str, Any]) -> dict[str, Any]:
    """Entfernt interne Python-Objekte vor dem Export nach Excel."""
    return {
        key: value
        for key, value in case.items()
        if key not in {"_file_paths", "_prompt"}
    }


def export_excel(
    path: Path,
    cases: list[dict[str, Any]],
    used_file_rows: list[dict[str, Any]],
    classes: list[str],
) -> None:
    result_df = pd.DataFrame([public_case_row(case) for case in cases])
    used_files_df = pd.DataFrame(used_file_rows)
    classes_df = pd.DataFrame({FUNCTIONAL_CLASS_COL: classes})

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        result_df.to_excel(writer, sheet_name="test_results", index=False)
        used_files_df.to_excel(writer, sheet_name="used_files", index=False)
        classes_df.to_excel(writer, sheet_name="classes_used", index=False)


# =============================================================================
# TESTABLAUF
# =============================================================================

def prepare_first_five_cases(
    hbg_df: pd.DataFrame,
    inventory_df: pd.DataFrame,
    classes: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Fuehrt Matching und Pfadpruefung fuer exakt die ersten 5 HBG durch."""
    del classes  # Klassen werden erst beim Promptbau benoetigt.

    test_df = hbg_df.head(TEST_LIMIT).copy()
    folder_names = (
        inventory_df[INVENTORY_FOLDER_COL]
        .map(clean_cell)
        .loc[lambda series: series.ne("")]
        .drop_duplicates()
        .tolist()
    )

    cases: list[dict[str, Any]] = []
    used_file_rows: list[dict[str, Any]] = []

    for position, (source_index, row) in enumerate(test_df.iterrows(), start=1):
        hbg_id = clean_cell(row[ID_COL])
        sap_number = clean_cell(row[SAP_COL])
        teamcenter_id = clean_cell(row[TEAMCENTER_COL])
        baugruppenname = clean_cell(row[NAME_COL])

        logging.info(
            "Precheck %s/%s: ID=%s, Name=%s",
            position,
            len(test_df),
            hbg_id,
            baugruppenname,
        )

        matched_folder, match_method, match_error = match_baugruppe_folder(
            sap_number,
            teamcenter_id,
            folder_names,
        )

        case: dict[str, Any] = {
            "Test_Position": position,
            "Source_DataFrame_Index": int(source_index),
            "ID": hbg_id,
            "SAP-Nummer": sap_number,
            "Teamcenter ID": teamcenter_id,
            "Benennung (EN)": baugruppenname,
            "Matched_Folder": matched_folder or "",
            "Match_Method": match_method,
            "Priority_1_Count": 0,
            "Priority_1_Files": "",
            "Missing_Files": "",
            "Gemini_Label": "",
            "Raw_Response": "",
            "Status": "",
            "Error_Message": match_error,
            "_file_paths": [],
            "_prompt": "",
        }

        if not baugruppenname:
            case["Status"] = "NO_BAUGRUPPENNAME"
            case["Error_Message"] = "Benennung (EN) ist leer"
            cases.append(case)
            continue

        if matched_folder is None:
            case["Status"] = match_method
            cases.append(case)
            continue

        existing_files, missing_files, file_details = select_priority_1_files(
            inventory_df,
            matched_folder,
        )
        for detail in file_details:
            used_file_rows.append(
                {
                    "ID": hbg_id,
                    "SAP-Nummer": sap_number,
                    "Teamcenter ID": teamcenter_id,
                    **detail,
                }
            )

        case["Priority_1_Count"] = len(existing_files) + len(missing_files)
        case["Priority_1_Files"] = "\n".join(
            path.name for path in existing_files + missing_files
        )
        case["Missing_Files"] = "\n".join(str(path) for path in missing_files)
        case["_file_paths"] = existing_files

        if not existing_files and not missing_files:
            case["Status"] = "NO_PRIORITY_1_FILES"
            case["Error_Message"] = (
                f"Keine Zeile mit {INVENTORY_PRIORITY_COL}="
                f"{PRIORITY_1_VALUE} gefunden"
            )
        elif missing_files:
            case["Status"] = "FILE_NOT_FOUND"
            case["Error_Message"] = (
                "Mindestens eine Priority-1-Datei fehlt; API-Aufruf wird "
                "nicht mit unvollstaendigen Daten ausgefuehrt"
            )
        else:
            case["Status"] = "READY"
            case["Error_Message"] = ""

        cases.append(case)

    return cases, used_file_rows


def run_api_for_ready_cases(
    cases: list[dict[str, Any]],
    used_file_rows: list[dict[str, Any]],
    classes: list[str],
) -> None:
    ready_cases = [case for case in cases if case["Status"] == "READY"]
    if not RUN_API:
        logging.info("RUN_API=False: Es wird nur der Precheck ausgefuehrt.")
        return
    if not ready_cases:
        logging.warning("Keine der ersten 5 HBG ist fuer den API-Aufruf bereit.")
        return

    llm = create_llm_connector()

    for api_position, case in enumerate(ready_cases, start=1):
        file_paths: list[Path] = case["_file_paths"]
        prompt = build_prompt(case["Benennung (EN)"], classes, file_paths)
        case["_prompt"] = prompt

        logging.info(
            "Gemini-Aufruf %s/%s: ID=%s, Name=%s, P1-Dateien=%s",
            api_position,
            len(ready_cases),
            case["ID"],
            case["Benennung (EN)"],
            len(file_paths),
        )
        for path in file_paths:
            logging.info("  Datei: %s", path)

        raw_record: dict[str, Any] = {
            "run_timestamp": RUN_TIMESTAMP,
            "id": case["ID"],
            "sap_nummer": case["SAP-Nummer"],
            "teamcenter_id": case["Teamcenter ID"],
            "baugruppenname": case["Benennung (EN)"],
            "matched_folder": case["Matched_Folder"],
            "file_paths": [str(path) for path in file_paths],
            "prompt": prompt,
            "model": MODEL_NAME,
            "generation_config": GENERATION_CONFIG,
            "processed_at": datetime.now().isoformat(timespec="seconds"),
        }

        try:
            raw_response = ask_gemini(llm, prompt, file_paths)
            label, is_valid = canonicalize_response(raw_response, classes)
            case["Raw_Response"] = raw_response
            case["Gemini_Label"] = label if is_valid else ""
            case["Status"] = "OK" if is_valid else "INVALID_LABEL"
            if not is_valid:
                case["Error_Message"] = (
                    "Antwort stimmt nicht exakt mit einer erlaubten "
                    "Funktionsklasse ueberein"
                )
            raw_record.update(
                {
                    "raw_response": raw_response,
                    "canonical_label": label if is_valid else None,
                    "status": case["Status"],
                    "error": case["Error_Message"],
                }
            )
            logging.info("Gemini-Antwort fuer ID %s: %s", case["ID"], raw_response)
        except Exception as exc:
            case["Status"] = "API_ERROR"
            case["Error_Message"] = str(exc)
            raw_record.update(
                {
                    "raw_response": None,
                    "canonical_label": None,
                    "status": "API_ERROR",
                    "error": str(exc),
                }
            )
            logging.exception("Gemini-Fehler fuer ID %s", case["ID"])

        write_jsonl(RAW_RESPONSES_PATH, raw_record)

        # Nach jeder Antwort aktualisieren: Bei Abbruch bleiben Ergebnisse erhalten.
        export_excel(RESULT_PATH, cases, used_file_rows, classes)


def main() -> None:
    ensure_directories()
    configure_logging()
    logging.info("Testlauf gestartet: exakt die ersten %s HBG", TEST_LIMIT)

    hbg_df, inventory_df, classes = load_input_data()
    cases, used_file_rows = prepare_first_five_cases(
        hbg_df,
        inventory_df,
        classes,
    )

    for case in cases:
        logging.info(
            "Precheck-Ergebnis: ID=%s | Match=%s | Ordner=%s | P1=%s | Status=%s",
            case["ID"],
            case["Match_Method"],
            case["Matched_Folder"],
            case["Priority_1_Count"],
            case["Status"],
        )

    run_api_for_ready_cases(cases, used_file_rows, classes)
    export_excel(RESULT_PATH, cases, used_file_rows, classes)

    logging.info("Testergebnis gespeichert: %s", RESULT_PATH)
    logging.info("Rohantworten: %s", RAW_RESPONSES_PATH)
    logging.info("Logdatei: %s", LOG_PATH)
    print("\nFertig.")
    print(f"Ergebnis: {RESULT_PATH}")


if __name__ == "__main__":
    main()
