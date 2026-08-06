"""
Main entry point: classify a batch of Baugruppen into functional classes with a selected LLM model.

For each Baugruppe, the script recursively scans its document folder and sends all supported files
to the model together. Priority 1 / Priority 2 and a file inventory are no longer used.

Example command (first test with 20 BGs):
    python run_classification.py \
        --input-excel input/all_HBG_random_no_label.xlsx \
        --classes-excel input/Functional_classes.xlsx \
        --data-root "processed HBG" \
        --max-rows 20

It depends on Anja's llm_connector.py in the same folder; that connector performs the actual calls to
Gemini / Claude / GPT. This file only reads the experiment data, scans BG folders, builds the classification prompt, and
saves the results.
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
    # The script still runs without tqdm, but does not show a progress bar.
    def tqdm(iterable, **_kwargs):
        return iterable

try:
    # python-dotenv is only used to read the local .env file; without it, already configured environment variables can still be used.
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv() -> bool:
        logging.warning("python-dotenv is not installed; .env will not be loaded.")
        return False


# These are the file types that Anja's connector can accept directly.
SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}

# The actual column names may vary. They can be supplied through CLI parameters; otherwise these common names are detected automatically.
ID_COLUMN_CANDIDATES = (
    "Baugruppennummer", "Baugruppen-ID", "Baugruppen_ID", "HBG", "ID",
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
    parser.add_argument("--input-excel", required=True, type=Path)
    parser.add_argument("--classes-excel", required=True, type=Path)
    parser.add_argument("--model", default="gemini-2.5-pro")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument(
        "--data-root", required=True, type=Path,
        help="Root directory containing the Baugruppe folders, for example processed HBG.",
    )
    parser.add_argument("--max-rows", type=int, default=None,
                        help="Process only the first N rows of the input Excel, useful for a 20-BG pilot.")

    # Default column names can be overridden on the command line; no source-code change is required.
    parser.add_argument("--id-column", default=None)
    parser.add_argument(
        "--teamcenter-column", default=None,
        help="Column containing the Teamcenter ID in the Excel file. Detected automatically by default; it may be omitted if absent.",
    )
    parser.add_argument("--name-column", default=None)
    parser.add_argument("--class-column", default=None)
    return parser.parse_args()


def find_column(df: pd.DataFrame, requested: str | None, candidates: tuple[str, ...], label: str) -> str:
    """Find a user-specified column or automatically match common column names; list the actual headers if no match is found."""
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
    """Same as find_column, but Teamcenter ID is optional and its absence does not raise an error."""
    if requested:
        return find_column(df, requested, candidates, label)
    return next((candidate for candidate in candidates if candidate in df.columns), None)


def read_classes(classes_path: Path, requested_column: str | None) -> list[str]:
    df = pd.read_excel(classes_path)
    class_column = find_column(df, requested_column, CLASS_COLUMN_CANDIDATES, "class_column")
    classes = [str(value).strip() for value in df[class_column].dropna() if str(value).strip()]
    classes = list(dict.fromkeys(classes))  # Preserve the Excel order while removing duplicates.
    if not classes:
        raise ValueError(f"No allowed classes found in '{classes_path}'.")
    return classes


def assembly_id_variants(value: object) -> list[str]:
    """Generate possible folder names, including the case where Excel reads 123 as 123.0."""
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
    """Normalize IDs for comparison: ignore spaces, hyphens, and Excel's numeric .0 display difference."""
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
    """Accept only a unique candidate; multiple candidates require manual review to avoid sending incorrect documents to the model."""
    matches = [folder for folder in folders if predicate(normalize_identifier(folder.name))]
    if len(matches) == 1:
        return matches[0], status
    if len(matches) > 1:
        return None, f"AMBIGUOUS_{status}"
    return None, None


def teamcenter_fragments(teamcenter_id: object, minimum_length: int = 6) -> list[str]:
    """Generate long contiguous Teamcenter ID fragments, e.g. 12345678 -> 12345678, 1234567, ...

    Some folders retain only part of the Teamcenter ID. To avoid false matches from short numbers, try only
    fragments of at least 6 characters and still require a unique folder match.
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
    """Find the BG folder by reliability order and return the match method for manual review in the result Excel."""
    folders = sorted(path for path in data_root.iterdir() if path.is_dir())
    sap_id = normalize_identifier(assembly_id)
    tc_id = normalize_identifier(teamcenter_id)

    # 1. The folder name exactly matches an identifier in Excel: most reliable.
    for identifier, label in ((sap_id, "EXACT_ASSEMBLY_ID"), (tc_id, "EXACT_TEAMCENTER_ID")):
        if identifier:
            folder, status = unique_folder_match(folders, lambda name, x=identifier: name == x, label)
            if folder or status:
                return folder, status

    # 2. The full identifier appears in a longer folder name, e.g. HBG_123456_REV_A.
    for identifier, label in ((sap_id, "CONTAINS_ASSEMBLY_ID"), (tc_id, "CONTAINS_TEAMCENTER_ID")):
        if identifier:
            folder, status = unique_folder_match(folders, lambda name, x=identifier: x in name, label)
            if folder or status:
                return folder, status

    # 3. A long Teamcenter ID fragment appears in the folder name. For example, when the Teamcenter ID is
    #    ABCD12345678but the folder name retains only 12345678. Accept only a unique match.
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
    """After locating the matching BG folder, recursively collect all supported PDF and image files."""
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
    """Accept only one exact label; tolerate occasional extra spaces or Markdown code fences in the model response."""
    answer = str(raw_response).strip().strip("`").strip()
    allowed_with_fallback = allowed_classes + ["Nicht klassifizierbar"]
    exact_lookup = {name.casefold(): name for name in allowed_with_fallback}
    if answer.casefold() in exact_lookup:
        return exact_lookup[answer.casefold()]

    # If the model accidentally adds an explanation, extract a label only when exactly one allowed label occurs in the full response; do not guess.
    matches = [name for name in allowed_with_fallback if name.casefold() in answer.casefold()]
    unique_matches = list(dict.fromkeys(matches))
    return unique_matches[0] if len(unique_matches) == 1 else None


def make_output_path(args: argparse.Namespace) -> Path:
    safe_model = re.sub(r"[^A-Za-z0-9_.-]+", "_", args.model)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    return args.output_dir / f"classification_all_files_{safe_model}_{timestamp}.xlsx"


def create_connector(model_name: str, api_key: str):
    """Import the connector lazily so that --help and Excel-parameter validation do not depend on the company connector file."""
    try:
        from llm_connector import LLMConnector
    except ImportError as error:
        raise ImportError(
            "llm_connector.py with class LLMConnector was not found. "
            "Place Anja's actual llm_connector.py next to run_classification.py."
        ) from error
    return LLMConnector(model_name, api_key)


def write_checkpoint(df: pd.DataFrame, output_path: Path) -> None:
    """Save after every row so completed results are not lost if a network failure occurs."""
    df.to_excel(output_path, index=False, engine="openpyxl")


def run(args: argparse.Namespace) -> Path:
    if not os.getenv("BOSCH_FARM_SUBSCRIPTION_KEY"):
        raise EnvironmentError("BOSCH_FARM_SUBSCRIPTION_KEY is not set in .env or the environment.")
    if args.max_rows is not None and args.max_rows <= 0:
        raise ValueError("--max-rows must be greater than 0.")

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

    # This step only creates the connector and detects the model family; it does not yet make an LLM request.
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
    load_dotenv()
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
