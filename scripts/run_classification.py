"""Classify Baugruppen into functional classes with one selected LLM.

For every Baugruppe, the script recursively scans the matched document folder and
sends all supported files to the model. It does not use Priority 1 / Priority 2 or
a file inventory.

The standard files below are resolved relative to this script, so the command can
stay short. The only machine-specific setting is ``BG_DATA_ROOT`` in ``.env``.

This script requires Anja's ``llm_connector.py`` in the same folder. The connector
performs the Gemini / Claude / GPT request; this file reads experiment data, finds
BG folders, builds the classification prompt, and saves results.
"""

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
try:
    from tqdm import tqdm
except ImportError:
    # The script still works without tqdm, but no progress bar is shown.
    def tqdm(iterable, **_kwargs):
        return iterable

try:
    # python-dotenv only loads a local .env; system environment variables still work without it.
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args, **_kwargs) -> bool:
        logging.warning("python-dotenv is not installed; .env will not be loaded.")
        return False


# Default project paths. They are independent of the terminal's current folder.
# All Python files live in scripts/, while .env, input/ and outputs/ stay in the repo root.
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent if SCRIPT_DIR.name.casefold() == "scripts" else SCRIPT_DIR
DEFAULT_INPUT_EXCEL = PROJECT_DIR / "input" / "all_BG_random_no_label.xlsx"
DEFAULT_CLASSES_EXCEL = PROJECT_DIR / "input" / "Functional_classes.xlsx"
DEFAULT_OUTPUT_DIR = PROJECT_DIR / "outputs"

# File types that Anja's connector can send directly to the LLM.
SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}

# The actual spreadsheet column names can vary. They can be passed via CLI; otherwise
# the script attempts to detect one of these common names.
ID_COLUMN_CANDIDATES = (
    "Baugruppennummer", "Baugruppen-ID", "Baugruppen_ID", "BG", "ID",
    "SAP-Nummer", "SAP Nummer",
)
TEAMCENTER_COLUMN_CANDIDATES = (
    "Teamcenter ID", "Teamcenter-ID", "Teamcenter Nummer", "Teamcenter-Nummer",
    "TC ID", "TC-ID",
)
NAME_COLUMN_CANDIDATES = (
    "Benennung", "Benennung (EN)", "Baugruppenname", "Baugruppenbezeichnung",
)
CLASS_COLUMN_CANDIDATES = ("Funktionsklasse", "Functional class", "Functional_class")

GENERATION_CONFIG = {
    "temperature": 0.0,
    "topP": 0.95,
    "candidateCount": 1,
    "maxOutputTokens": 100,
}

SYSTEM_PROMPT = """Du bist ein technischer Experte für Baugruppen im Maschinen- und Anlagenbau.
Ordne jede Baugruppe genau einer vorgegebenen Funktionsklasse zu.
Nutze nur die bereitgestellte Benennung und – falls beigefügt – die technischen Dateien.
Gib ausschließlich den exakten Namen einer erlaubten Funktionsklasse aus.
Wenn die Informationen für eine belastbare Zuordnung nicht reichen, gib ausschließlich
'Nicht klassifizierbar' aus. Keine Begründung, kein Satzzeichen und kein zusätzlicher Text."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify Baugruppen with an LLM and save one timestamped Excel result."
    )
    data_root_from_env = os.getenv("BG_DATA_ROOT")
    parser.add_argument("--input-excel", type=Path, default=DEFAULT_INPUT_EXCEL)
    parser.add_argument("--classes-excel", type=Path, default=DEFAULT_CLASSES_EXCEL)
    parser.add_argument("--model", default="gemini-2.5-pro")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--data-root", type=Path,
        default=Path(data_root_from_env).expanduser() if data_root_from_env else None,
        help=(
            "Absolute root folder containing all Baugruppe folders. Defaults to "
            "BG_DATA_ROOT from .env."
        ),
    )
    parser.add_argument("--max-rows", type=int, default=None,
                        help="Process only the first N input rows; useful for a pilot run.")

    # Default column detection can be overridden through CLI without editing the script.
    parser.add_argument("--id-column", default=None)
    parser.add_argument(
        "--teamcenter-column", default=None,
        help="Teamcenter ID column. Detected automatically by default; optional.",
    )
    parser.add_argument("--name-column", default=None)
    parser.add_argument("--class-column", default=None)
    return parser.parse_args()


def find_column(df: pd.DataFrame, requested: str | None, candidates: tuple[str, ...], label: str) -> str:
    """Use an explicitly requested column or detect a common name."""
    if requested:
        if requested in df.columns:
            return requested
        raise ValueError(f"{label} column '{requested}' was not found. Available: {list(df.columns)}")

    for candidate in candidates:
        if candidate in df.columns:
            return candidate
    raise ValueError(
        f"Could not detect the {label} column. Available: {list(df.columns)}. "
        f"Pass it explicitly, for example --{label.replace('_', '-')} COLUMN_NAME."
    )


def find_optional_column(
    df: pd.DataFrame, requested: str | None, candidates: tuple[str, ...], label: str,
) -> str | None:
    """Like find_column, except a Teamcenter ID is optional."""
    if requested:
        return find_column(df, requested, candidates, label)
    return next((candidate for candidate in candidates if candidate in df.columns), None)


def read_classes(classes_path: Path, requested_column: str | None) -> list[str]:
    df = pd.read_excel(classes_path)
    class_column = find_column(df, requested_column, CLASS_COLUMN_CANDIDATES, "class_column")
    classes = [str(value).strip() for value in df[class_column].dropna() if str(value).strip()]
    classes = list(dict.fromkeys(classes))  # Preserve Excel order while removing duplicates.
    if not classes:
        raise ValueError(f"No allowed classes found in '{classes_path}'.")
    return classes


def assembly_id_variants(value: object) -> list[str]:
    """Create possible folder names, including Excel's 123 versus 123.0 variation."""
    raw = str(value).strip()
    variants = [raw]
    try:
        number = float(raw)
        if number.is_integer():
            variants.append(str(int(number)))
    except ValueError:
        pass
    return list(dict.fromkeys(variants))


def normalize_identifier(value: object) -> str:
    """Normalize IDs for comparison by ignoring punctuation and Excel's .0 variation."""
    if pd.isna(value):
        return ""
    raw = str(value).strip()
    try:
        number = float(raw)
        if number.is_integer():
            raw = str(int(number))
    except ValueError:
        pass
    return re.sub(r"[^A-Za-z0-9]+", "", raw).casefold()


def unique_folder_match(
    folders: list[Path], predicate, status: str,
) -> tuple[Path | None, str | None]:
    """Accept only one match; multiple candidates require manual review."""
    matches = [folder for folder in folders if predicate(normalize_identifier(folder.name))]
    if len(matches) == 1:
        return matches[0], status
    if len(matches) > 1:
        return None, f"AMBIGUOUS_{status}"
    return None, None


def teamcenter_fragments(teamcenter_id: object, minimum_length: int = 6) -> list[str]:
    """Create long contiguous Teamcenter ID fragments, e.g. 12345678 -> 12345678, 1234567.

    Some folders retain only part of a Teamcenter ID. To avoid accidental matches,
    fragments shorter than six characters are excluded and matches must remain unique.
    """
    normalized = normalize_identifier(teamcenter_id)
    fragments: list[str] = []
    for length in range(len(normalized), minimum_length - 1, -1):
        for start in range(len(normalized) - length + 1):
            fragments.append(normalized[start:start + length])
    return list(dict.fromkeys(fragments))


def find_assembly_folder(
    assembly_id: object, teamcenter_id: object | None, data_root: Path,
) -> tuple[Path | None, str]:
    """Find the BG folder by reliability order and return the matching method."""
    folders = sorted(path for path in data_root.iterdir() if path.is_dir())
    sap_id = normalize_identifier(assembly_id)
    tc_id = normalize_identifier(teamcenter_id)

    # 1. An exact folder name match is the most reliable option.
    for identifier, label in ((sap_id, "EXACT_ASSEMBLY_ID"), (tc_id, "EXACT_TEAMCENTER_ID")):
        if identifier:
            folder, status = unique_folder_match(folders, lambda name, x=identifier: name == x, label)
            if folder or status:
                return folder, status

    # 2. The full ID appears in a longer folder name, e.g. BG_123456_REV_A.
    for identifier, label in ((sap_id, "CONTAINS_ASSEMBLY_ID"), (tc_id, "CONTAINS_TEAMCENTER_ID")):
        if identifier:
            folder, status = unique_folder_match(folders, lambda name, x=identifier: x in name, label)
            if folder or status:
                return folder, status

    # 3. A long Teamcenter ID fragment appears in the folder name, e.g.
    #    ABCD12345678 in Excel but only 12345678 in the folder. Matches must be unique.
    if tc_id:
        for fragment in teamcenter_fragments(tc_id):
            folder, status = unique_folder_match(
                folders, lambda name, x=fragment: x in name, "TEAMCENTER_FRAGMENT",
            )
            if folder or status:
                return folder, status

    if not sap_id and not tc_id:
        return None, "NO_IDENTIFIER"
    return None, "NOT_FOUND"


def collect_all_supported_files(
    assembly_id: object, teamcenter_id: object | None, data_root: Path,
) -> tuple[list[str], Path | None, str]:
    """Find the BG folder and recursively collect its supported PDF/image files."""
    assembly_folder, match_status = find_assembly_folder(assembly_id, teamcenter_id, data_root)
    if not assembly_folder:
        logging.warning(
            "Folder for BG %s (Teamcenter: %s) was not found: %s",
            assembly_id, teamcenter_id, match_status,
        )
        return [], None, match_status

    files = sorted(
        path for path in assembly_folder.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    logging.info(
        "%d supported files found for BG %s in %s (%s)",
        len(files), assembly_id, assembly_folder, match_status,
    )
    return [str(path) for path in files], assembly_folder, match_status


def build_question(assembly_name: object, allowed_classes: list[str]) -> str:
    class_list = "\n".join(f"- {name}" for name in allowed_classes)
    return f"""Baugruppenbenennung: {assembly_name}

Beurteile die Baugruppenbenennung und alle beigefügten technischen Dateien.
Wähle genau eine der folgenden Funktionsklassen:
{class_list}
- Nicht klassifizierbar
"""


def extract_label(raw_response: object, allowed_classes: list[str]) -> str | None:
    """Accept one exact label while tolerating extra whitespace or Markdown backticks."""
    answer = str(raw_response).strip().strip("`").strip()
    allowed_with_fallback = allowed_classes + ["Nicht klassifizierbar"]
    exact_lookup = {name.casefold(): name for name in allowed_with_fallback}
    if answer.casefold() in exact_lookup:
        return exact_lookup[answer.casefold()]

    # If the model adds an explanation, extract only when exactly one allowed label occurs.
    matches = [name for name in allowed_with_fallback if name.casefold() in answer.casefold()]
    unique_matches = list(dict.fromkeys(matches))
    return unique_matches[0] if len(unique_matches) == 1 else None


def make_output_path(args: argparse.Namespace) -> Path:
    safe_model = re.sub(r"[^A-Za-z0-9_.-]+", "_", args.model)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    return args.output_dir / f"classification_all_files_{safe_model}_{timestamp}.xlsx"


def create_connector(model_name: str, api_key: str):
    """Delay the connector import so --help and Excel validation do not need it."""
    try:
        from llm_connector import LLMConnector
    except ImportError as error:
        raise ImportError(
            "llm_connector.py with class LLMConnector was not found. "
            "Place Anja's actual llm_connector.py next to run_classification.py."
        ) from error
    return LLMConnector(model_name, api_key)


def write_checkpoint(df: pd.DataFrame, output_path: Path) -> None:
    """Save after each row so completed results survive a network failure."""
    df.to_excel(output_path, index=False, engine="openpyxl")


def run(args: argparse.Namespace) -> Path:
    if not os.getenv("BOSCH_FARM_SUBSCRIPTION_KEY"):
        raise EnvironmentError("BOSCH_FARM_SUBSCRIPTION_KEY is not set in .env or the environment.")
    if args.max_rows is not None and args.max_rows <= 0:
        raise ValueError("--max-rows must be greater than 0.")
    if args.data_root is None:
        raise EnvironmentError(
            "BG_DATA_ROOT is not set. Add an absolute path to .env, for example: "
            "BG_DATA_ROOT=C:\\path\\to\\processed_BG"
        )
    if not args.data_root.is_absolute():
        raise ValueError(
            f"--data-root must be an absolute local path, not: {args.data_root}"
        )

    input_df = pd.read_excel(args.input_excel)
    input_id_column = find_column(input_df, args.id_column, ID_COLUMN_CANDIDATES, "id_column")
    teamcenter_column = find_optional_column(
        input_df, args.teamcenter_column, TEAMCENTER_COLUMN_CANDIDATES, "teamcenter_column",
    )
    name_column = find_column(input_df, args.name_column, NAME_COLUMN_CANDIDATES, "name_column")
    if teamcenter_column:
        logging.info("Using Teamcenter ID column: %s", teamcenter_column)
    else:
        logging.warning(
            "No Teamcenter ID column detected. Folder matching will use only '%s'.",
            input_id_column,
        )
    if args.max_rows:
        input_df = input_df.head(args.max_rows).copy()

    if not args.data_root.is_dir():
        raise FileNotFoundError(f"--data-root does not exist or is not a directory: {args.data_root}")

    allowed_classes = read_classes(args.classes_excel, args.class_column)
    output_path = make_output_path(args)

    # This only creates the connector and detects its model family; no LLM request yet.
    llm = create_connector(args.model, os.environ["BOSCH_FARM_SUBSCRIPTION_KEY"])

    result_df = input_df.copy()
    for column in (
        "Predicted_Label", "Raw_Model_Response", "Processing_Status", "Files_Used",
        "File_Count", "Matched_Folder", "Folder_Match_Status", "Run_Model", "Run_Mode",
        "Run_Timestamp", "Token_Usage_JSON",
    ):
        result_df[column] = pd.NA

    run_timestamp = datetime.now().isoformat(timespec="seconds")
    for index, row in tqdm(result_df.iterrows(), total=len(result_df), desc="Classifying"):
        assembly_id = row[input_id_column]
        teamcenter_id = row[teamcenter_column] if teamcenter_column else None
        assembly_name = row[name_column]
        if pd.isna(assembly_id) or pd.isna(assembly_name) or not str(assembly_name).strip():
            result_df.loc[index, "Processing_Status"] = "SKIPPED: missing ID or Benennung"
            write_checkpoint(result_df, output_path)
            continue

        try:
            files, matched_folder, match_status = collect_all_supported_files(
                assembly_id, teamcenter_id, args.data_root,
            )
            result_df.loc[index, "Folder_Match_Status"] = match_status
            result_df.loc[index, "Matched_Folder"] = str(matched_folder) if matched_folder else pd.NA
            if not files:
                result_df.loc[index, "Processing_Status"] = (
                    f"SKIPPED: no supported documents found ({match_status})"
                )
                result_df.loc[index, "File_Count"] = 0
                write_checkpoint(result_df, output_path)
                continue

            response = llm.ask_about_files(
                file_paths=files,
                question=build_question(assembly_name, allowed_classes),
                system_prompt=SYSTEM_PROMPT,
                generation_config=GENERATION_CONFIG,
            )
            predicted_label = extract_label(response, allowed_classes)
            result_df.loc[index, "Raw_Model_Response"] = str(response)
            result_df.loc[index, "Predicted_Label"] = predicted_label or "UNRECOGNISED_RESPONSE"
            result_df.loc[index, "Processing_Status"] = "SUCCESS" if predicted_label else "CHECK: response is not one valid label"
            result_df.loc[index, "Files_Used"] = "\n".join(files)
            result_df.loc[index, "File_Count"] = len(files)
            result_df.loc[index, "Run_Model"] = args.model
            result_df.loc[index, "Run_Mode"] = "all_files"
            result_df.loc[index, "Run_Timestamp"] = run_timestamp
            result_df.loc[index, "Token_Usage_JSON"] = json.dumps(
                llm.get_last_token_usage() or {}, ensure_ascii=False
            )
        except Exception as error:
            logging.exception("Failed to process BG %s", assembly_id)
            result_df.loc[index, "Processing_Status"] = f"ERROR: {error}"

        write_checkpoint(result_df, output_path)

    logging.info("Finished. Result saved to %s", output_path.resolve())
    return output_path


if __name__ == "__main__":
    load_dotenv(PROJECT_DIR / ".env")
    arguments = parse_args()
    log_directory = arguments.output_dir / "logs"
    log_directory.mkdir(parents=True, exist_ok=True)
    log_path = log_directory / f"classification_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler()],
        force=True,
    )
    try:
        result_path = run(arguments)
        print(f"Done: {result_path.resolve()}")
    except Exception as error:
        logging.error("Classification did not start: %s", error)
        sys.exit(1)
