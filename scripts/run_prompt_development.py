#!/usr/bin/env python3
"""Run Task 3 prompt-development classifications on the selected Baugruppen.

Expected project layout
-----------------------
Task3_Prompt_Development/
├── .env
├── llm_connector.py
├── run_prompt_development.py
├── input/classification_experiment_dataset.xlsx
├── prompts/P1.txt
└── outputs/

The dataset is created by build_experiment_dataset.py.  By default this script
processes only rows whose prompt_engineering value is yes.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

try:
    import fitz
except ImportError:
    fitz = None

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args, **_kwargs) -> bool:
        return False

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable, **_kwargs):
        return iterable


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT_EXCEL = PROJECT_DIR / "input" / "classification_experiment_dataset.xlsx"
DEFAULT_PROMPT_DIR = PROJECT_DIR / "prompts"
DEFAULT_OUTPUT_DIR = PROJECT_DIR / "outputs"
SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-excel", type=Path, default=DEFAULT_INPUT_EXCEL)
    parser.add_argument("--sheet-name", default="Experiment_Dataset")
    parser.add_argument("--prompt-config", choices=("P1", "P2", "P3"), required=True)
    parser.add_argument("--prompt-file", type=Path, default=None)
    parser.add_argument("--model", default="gemini-2.5-pro")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument(
        "--max-output-tokens", type=int, default=4096,
        help="Maximum generated tokens per response. Default: 4096.",
    )
    parser.add_argument(
        "--max-input-mb", type=float, default=4.0,
        help="Prepared Base64 input-size cap in MiB. Default: 4.0.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument(
        "--all-rows",
        action="store_true",
        help="Run all dataset rows instead of only prompt_engineering = yes.",
    )
    return parser.parse_args()


def find_column(df: pd.DataFrame, expected: str, *, required: bool = True) -> str | None:
    lookup = {str(column).strip().casefold(): str(column) for column in df.columns}
    column = lookup.get(expected.strip().casefold())
    if column or not required:
        return column
    raise ValueError(f"Column '{expected}' is missing. Available: {list(df.columns)}")


def read_prompt(args: argparse.Namespace) -> tuple[Path, str]:
    prompt_path = args.prompt_file or DEFAULT_PROMPT_DIR / f"{args.prompt_config}.txt"
    if not prompt_path.is_file():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    prompt = prompt_path.read_text(encoding="utf-8").strip()
    if not prompt:
        raise ValueError(f"Prompt file is empty: {prompt_path}")
    return prompt_path, prompt


def collect_supported_files(folder_path: str) -> list[str]:
    folder = Path(folder_path)
    if not folder.is_dir():
        return []
    return [
        str(path)
        for path in sorted(folder.rglob("*"))
        if path.is_file() and path.suffix.casefold() in SUPPORTED_EXTENSIONS
    ]


def prepared_base64_size(connector, file_path: str) -> int:
    """Return the size after the connector has rendered and Base64-encoded a file."""
    converter = getattr(connector, "file_to_openai_images", None)
    if not callable(converter):
        raise AttributeError(
            "llm_connector.py must provide file_to_openai_images() for input-size limiting."
        )
    return sum(len(str(image)) for image in converter(file_path))


def write_short_pdf(source: Path, target: Path, page_count: int) -> None:
    if fitz is None:
        raise ImportError("PyMuPDF (fitz) is required for automatic PDF page reduction.")
    original = fitz.open(source)
    reduced = fitz.open()
    try:
        reduced.insert_pdf(original, from_page=0, to_page=min(page_count, len(original)) - 1)
        reduced.save(target)
    finally:
        reduced.close()
        original.close()


def apply_input_size_cap(
    connector, files: list[str], max_input_bytes: int, temp_dir: Path
) -> tuple[list[str], int, str, list[str]]:
    """Reduce only the largest PDF from four to three, then two pages if needed."""
    sizes = {file_path: prepared_base64_size(connector, file_path) for file_path in files}
    total = sum(sizes.values())
    display_files = list(files)
    if total <= max_input_bytes:
        return files, total, "No page reduction required.", display_files

    pdf_paths = [Path(file_path) for file_path in files if Path(file_path).suffix.casefold() == ".pdf"]
    if not pdf_paths:
        raise ValueError(f"Estimated input is {total / 1024 / 1024:.2f} MiB and no PDF can be reduced.")
    largest_pdf = max(pdf_paths, key=lambda path: sizes[str(path)])
    original_size = sizes[str(largest_pdf)]
    for pages in (3, 2):
        reduced_pdf = temp_dir / f"{largest_pdf.stem}_first_{pages}_pages.pdf"
        write_short_pdf(largest_pdf, reduced_pdf, pages)
        reduced_size = prepared_base64_size(connector, str(reduced_pdf))
        candidate_total = total - original_size + reduced_size
        if candidate_total <= max_input_bytes:
            sent_files = [str(reduced_pdf) if Path(file_path) == largest_pdf else file_path for file_path in files]
            display_files = [
                f"{largest_pdf} [first {pages} pages used instead of first 4]"
                if Path(file_path) == largest_pdf else file_path
                for file_path in files
            ]
            note = (
                f"Input cap applied: largest PDF reduced from first 4 pages to first {pages} pages."
            )
            return sent_files, candidate_total, note, display_files

    raise ValueError(
        f"Estimated input remains above {max_input_bytes / 1024 / 1024:.2f} MiB after reducing "
        f"the largest PDF to its first 2 pages."
    )


def build_question(row: pd.Series) -> str:
    english_name = str(row.get("Benennung (E)", "")).strip()
    german_name = str(row.get("Benennung (D)", "")).strip()
    return (
        "Klassifiziere die beigefügte Baugruppe gemäß den Systemanweisungen.\n"
        f"Benennung (E): {english_name}\n"
        f"Benennung (D): {german_name}\n\n"
        "Berücksichtige alle beigefügten technischen Dateien. "
        "Gib ausschließlich das angeforderte JSON-Objekt zurück."
    )


def create_connector(model_name: str, api_key: str):
    try:
        from llm_connector import LLMConnector
    except ImportError as error:
        raise ImportError(
            "llm_connector.py with class LLMConnector was not found. "
            "Place it beside this script."
        ) from error
    return LLMConnector(model_name, api_key)


def parse_json_response(raw_response: object) -> tuple[dict[str, object] | None, str]:
    raw = str(raw_response).strip()
    candidates = [raw]
    if raw.startswith(chr(96) * 3):
        fence = re.escape(chr(96) * 3)
        candidates.append(re.sub(rf"^{fence}(?:json)?\\s*|\\s*{fence}$", "", raw, flags=re.IGNORECASE))
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        candidates.append(raw[start:end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            return (parsed, "SUCCESS") if isinstance(parsed, dict) else (None, "JSON_IS_NOT_OBJECT")
        except json.JSONDecodeError:
            continue
    return None, "INVALID_JSON"


def json_value(payload: dict[str, object] | None, *keys: str) -> object:
    if payload is None:
        return pd.NA
    normalised = {str(key).casefold(): value for key, value in payload.items()}
    for key in keys:
        if key.casefold() in normalised:
            return normalised[key.casefold()]
    return pd.NA


def normalise_possible_classes(value: object) -> str | object:
    if value is None or value is pd.NA:
        return pd.NA
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def make_output_path(args: argparse.Namespace) -> Path:
    model = re.sub(r"[^A-Za-z0-9_.-]+", "_", args.model)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    return args.output_dir / f"prompt_development_{args.prompt_config}_{model}_{timestamp}.xlsx"


def write_checkpoint(frame: pd.DataFrame, output_path: Path) -> None:
    # Keep human-readable experiment results on the left.  Long technical
    # paths stay at the far right, where they cannot cover result cells.
    preferred_order = [
        "prompt_engineering", "SAP-Nummer", "Teamcenter", "Benennung (E)",
        "Benennung (D)", "Ground Truth", "Register", "Weitere zulässige Ground Truth",
        "Predicted_Label", "Reasoning", "Confidence_Percent",
        "Possible_Classes_If_Ambiguous", "Processing_Status", "JSON_Parse_Status",
    ]
    ordered_columns = [column for column in preferred_order if column in frame.columns]
    ordered_columns.extend(column for column in frame.columns if column not in ordered_columns)
    frame.loc[:, ordered_columns].to_excel(output_path, index=False, engine="openpyxl")
    workbook = load_workbook(output_path)
    sheet = workbook.active
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions

    result_columns = {
        "Predicted_Label", "Reasoning", "Confidence_Percent",
        "Possible_Classes_If_Ambiguous", "JSON_Parse_Status", "Processing_Status",
    }
    technical_columns = {
        "Data_Folder_Path", "Files_Used", "Raw_Model_Response", "Token_Usage_JSON",
        "Prompt_File", "Run_Timestamp", "Input_Prepared_MB", "Input_Adjustment",
    }
    widths = {
        "prompt_engineering": 18, "SAP-Nummer": 16, "Teamcenter": 16,
        "Benennung (E)": 22, "Benennung (D)": 22, "Ground Truth": 26,
        "Register": 10, "Weitere zulässige Ground Truth": 30,
        "Data_Folder_Path": 12, "Predicted_Label": 24, "Reasoning": 55,
        "Confidence_Percent": 18, "Possible_Classes_If_Ambiguous": 32,
        "Raw_Model_Response": 55, "JSON_Parse_Status": 20, "Processing_Status": 30,
        "Files_Used": 55, "File_Count": 12, "Run_Model": 22, "Prompt_Config": 14,
        "Prompt_File": 32, "Temperature": 14, "Run_Timestamp": 22,
        "Token_Usage_JSON": 26, "Input_Prepared_MB": 18, "Input_Adjustment": 48,
    }
    header_fill = PatternFill("solid", fgColor="1F4E78")
    result_fill = PatternFill("solid", fgColor="2F75B5")
    technical_fill = PatternFill("solid", fgColor="7F8C8D")

    for column_index, cell in enumerate(sheet[1], start=1):
        header = str(cell.value)
        cell.fill = result_fill if header in result_columns else technical_fill if header in technical_columns else header_fill
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        sheet.column_dimensions[get_column_letter(column_index)].width = widths.get(header, 20)

    sheet.row_dimensions[1].height = 36
    wrap_headers = {"Reasoning", "Possible_Classes_If_Ambiguous", "Raw_Model_Response", "Files_Used", "Processing_Status", "Input_Adjustment"}
    header_positions = {str(cell.value): cell.column for cell in sheet[1]}
    for row_index in range(2, sheet.max_row + 1):
        sheet.row_dimensions[row_index].height = 75
        for header in wrap_headers:
            if header in header_positions:
                sheet.cell(row=row_index, column=header_positions[header]).alignment = Alignment(
                    vertical="top", wrap_text=True
                )

    workbook.save(output_path)


def run(args: argparse.Namespace) -> Path:
    if not 0 <= args.temperature <= 2:
        raise ValueError("--temperature must be between 0 and 2.")
    if args.max_rows is not None and args.max_rows <= 0:
        raise ValueError("--max-rows must be greater than 0.")
    if args.max_output_tokens <= 0:
        raise ValueError("--max-output-tokens must be greater than 0.")
    if args.max_input_mb <= 0:
        raise ValueError("--max-input-mb must be greater than 0.")
    api_key = os.getenv("BOSCH_FARM_SUBSCRIPTION_KEY")
    if not api_key:
        raise EnvironmentError("BOSCH_FARM_SUBSCRIPTION_KEY is not set in .env.")
    if not args.input_excel.is_file():
        raise FileNotFoundError(f"Dataset not found: {args.input_excel}")

    prompt_path, system_prompt = read_prompt(args)
    dataset = pd.read_excel(args.input_excel, sheet_name=args.sheet_name, dtype=str)
    selection_column = find_column(dataset, "prompt_engineering")
    path_column = find_column(dataset, "Data_Folder_Path")

    if not args.all_rows:
        dataset = dataset.loc[
            dataset[selection_column].fillna("").astype(str).str.strip().str.casefold().eq("yes")
        ].copy()
    if dataset.empty:
        scope = "all rows" if args.all_rows else "prompt_engineering = yes"
        raise ValueError(f"No rows selected for {scope}.")
    if args.max_rows is not None:
        dataset = dataset.head(args.max_rows).copy()

    logging.info("Dataset: %s", args.input_excel.resolve())
    logging.info("Prompt: %s", prompt_path.resolve())
    logging.info("Selected rows: %d", len(dataset))

    llm = create_connector(args.model, api_key)
    output_path = make_output_path(args)
    result = dataset.copy()
    for column in (
        "Predicted_Label", "Reasoning", "Confidence_Percent",
        "Possible_Classes_If_Ambiguous", "Raw_Model_Response", "JSON_Parse_Status",
        "Processing_Status", "Files_Used", "File_Count", "Run_Model", "Prompt_Config",
        "Prompt_File", "Temperature", "Run_Timestamp", "Token_Usage_JSON",
        "Input_Prepared_MB", "Input_Adjustment",
    ):
        result[column] = pd.NA

    run_timestamp = datetime.now().isoformat(timespec="seconds")
    generation_config = {
        "temperature": args.temperature,
        "topP": 0.95,
        "candidateCount": 1,
        "maxOutputTokens": args.max_output_tokens,
    }

    for index, row in tqdm(result.iterrows(), total=len(result), desc="Classifying"):
        try:
            files = collect_supported_files(row[path_column])
            if not files:
                result.loc[index, "Processing_Status"] = "SKIPPED: no supported PDF/image files"
                result.loc[index, "File_Count"] = 0
                write_checkpoint(result, output_path)
                continue

            with tempfile.TemporaryDirectory(prefix="prompt_development_") as temp_dir_name:
                sent_files, prepared_size, adjustment, display_files = apply_input_size_cap(
                    llm, files, int(args.max_input_mb * 1024 * 1024), Path(temp_dir_name)
                )
                logging.info(
                    "Row %s prepared input: %.2f MiB. %s",
                    index + 2, prepared_size / 1024 / 1024, adjustment,
                )
                response = llm.ask_about_files(
                    file_paths=sent_files,
                    question=build_question(row),
                    system_prompt=system_prompt,
                    generation_config=generation_config,
                )
            payload, parse_status = parse_json_response(response)
            result.loc[index, "Raw_Model_Response"] = str(response)
            result.loc[index, "JSON_Parse_Status"] = parse_status
            result.loc[index, "Predicted_Label"] = json_value(payload, "class_label", "class")
            result.loc[index, "Reasoning"] = json_value(payload, "reasoning", "begruendung", "begründung")
            result.loc[index, "Confidence_Percent"] = json_value(
                payload, "confidence_percent", "confidence", "konfidenz"
            )
            result.loc[index, "Possible_Classes_If_Ambiguous"] = normalise_possible_classes(
                json_value(payload, "possible_classes_if_ambiguous", "possible_classes", "zweitwahl")
            )
            result.loc[index, "Files_Used"] = "\n".join(display_files)
            result.loc[index, "File_Count"] = len(files)
            result.loc[index, "Input_Prepared_MB"] = round(prepared_size / 1024 / 1024, 2)
            result.loc[index, "Input_Adjustment"] = adjustment
            result.loc[index, "Run_Model"] = args.model
            result.loc[index, "Prompt_Config"] = args.prompt_config
            result.loc[index, "Prompt_File"] = str(prompt_path)
            result.loc[index, "Temperature"] = args.temperature
            result.loc[index, "Run_Timestamp"] = run_timestamp
            result.loc[index, "Token_Usage_JSON"] = json.dumps(
                llm.get_last_token_usage() or {}, ensure_ascii=False
            )
            result.loc[index, "Processing_Status"] = "SUCCESS" if payload else "CHECK: invalid JSON response"
        except Exception as error:
            logging.exception("Failed row %s", index + 2)
            result.loc[index, "Processing_Status"] = f"ERROR: {error}"

        write_checkpoint(result, output_path)

    logging.info("Finished. Result saved to %s", output_path.resolve())
    return output_path


if __name__ == "__main__":
    load_dotenv(PROJECT_DIR / ".env")
    arguments = parse_args()
    log_dir = arguments.output_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_dir / f"prompt_development_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )
    try:
        result_path = run(arguments)
        print(f"Done: {result_path.resolve()}")
    except Exception as error:
        logging.error("Classification did not start: %s", error)
        sys.exit(1)


# PowerShell command: Run P1 for all rows marked prompt_engineering = yes.
# python .\run_prompt_development.py --prompt-config P1 --model gemini-2.5-pro
