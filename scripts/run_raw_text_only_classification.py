#!/usr/bin/env python3
"""Run the final source-preserving raw-text-only BG classification experiment.

This is Step 2 of the revised two-step text-only experiment:
1. build_raw_text_only_inputs.py creates one complete local transcription per BG.
2. This script sends only that UTF-8 text file to the selected text model.

No original PDF, screenshot, CAD file, spreadsheet, or image is attached or
re-uploaded here.  The fixed P3 original prompt is used unchanged for every
model and every BG.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args: Any, **_kwargs: Any) -> bool:
        return False

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable: Any, **_kwargs: Any) -> Any:
        return iterable


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent if SCRIPT_DIR.name.casefold() == "scripts" else SCRIPT_DIR

# This path is intentionally not a CLI choice: all cross-model results must use
# exactly the same original P3 prompt.
FIXED_PROMPT_PATH = PROJECT_DIR / "prompts" / "P3_original.txt"
DEFAULT_OUTPUT_DIR = PROJECT_DIR / "outputs" / "raw_text_only_classification"

# Deployment IDs from the Model Farm overview.  These are text-input runs: the
# raw BG transcription is sent as text, never as an attached document/image.
MODEL_REGISTRY: dict[str, dict[str, str]] = {
    "gemini-pro": {"display": "Gemini 2.5 Pro", "id": "gemini-2.5-pro"},
    "gemini-flash": {"display": "Gemini 2.5 Flash", "id": "gemini-2.5-flash"},
    "claude-opus": {"display": "Claude Opus 4.8", "id": "claude-opus-4-8"},
    "claude-haiku": {"display": "Claude Haiku 4.5", "id": "claude-haiku-4-5@20251001"},
    "gpt-4o": {"display": "GPT-4o", "id": "gpt-4o"},
    "gpt-4o-mini": {"display": "GPT-4o mini", "id": "gpt-4o-mini"},
    "deepseek-r1": {"display": "DeepSeek R1", "id": "deepseek-r1"},
    "llama": {"display": "Llama 3.3 70B Instruct", "id": "llama-3.3-70B-instruct"},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raw-input-dir", type=Path, required=True,
        help=(
            "Step-1 run directory containing texts/ and raw_text_manifest.xlsx, e.g. "
            "outputs/raw_text_only_preprocessing/raw_text_only_YYYY-MM-DD_HH-MM-SS"
        ),
    )
    parser.add_argument(
        "--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
        help="Directory for timestamped model result folders.",
    )
    parser.add_argument(
        "--models", nargs="+", choices=[*MODEL_REGISTRY, "all"], default=["all"],
        help="Model aliases to run. Default: all eight requested text-input models.",
    )
    parser.add_argument("--max-bgs", type=int, default=None, help="Run only the first N BG text files; useful for a pilot.")
    parser.add_argument("--max-workers", type=int, default=1, help="Concurrent BG requests per model. Default: 1.")
    parser.add_argument("--max-output-tokens", type=int, default=4000, help="Maximum generated tokens per response. Default: 4000.")
    parser.add_argument(
        "--include-prompt-engineering", action="store_true",
        help="Override the independent-final-test exclusion and include prompt_engineering=yes rows when present.",
    )
    return parser.parse_args()


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("._") or "unnamed"


def clean(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def yes(value: Any) -> bool:
    return clean(value).casefold() in {"yes", "y", "ja", "true", "1"}


def normalise_column(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name).casefold())


def find_column(frame: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    lookup = {normalise_column(column): str(column) for column in frame.columns}
    for candidate in candidates:
        match = lookup.get(normalise_column(candidate))
        if match:
            return match
    return None


def load_connector(model_id: str, session_id: str) -> Any:
    try:
        from llm_connector_with_prompt_caching import LLMConnector
    except ImportError as error:
        raise ImportError(
            "llm_connector_with_prompt_caching.py must be in the same scripts directory."
        ) from error
    return LLMConnector(model_id, os.environ["BOSCH_FARM_SUBSCRIPTION_KEY"], session_id=session_id)


def read_fixed_prompt() -> str:
    if not FIXED_PROMPT_PATH.is_file():
        raise FileNotFoundError(
            f"The fixed prompt file does not exist: {FIXED_PROMPT_PATH}. "
            "Place P3_original.txt in the project's prompts folder."
        )
    prompt = FIXED_PROMPT_PATH.read_text(encoding="utf-8-sig").strip()
    if not prompt:
        raise ValueError(f"The fixed prompt is empty: {FIXED_PROMPT_PATH}")
    return prompt


def extract_json(response: str) -> tuple[dict[str, Any] | None, str]:
    """Accept plain/fenced JSON and recover a single JSON object when possible."""
    text = str(response or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
    try:
        parsed = json.loads(text)
        return (parsed, "VALID_JSON") if isinstance(parsed, dict) else (None, "JSON_NOT_OBJECT")
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            parsed, _end = decoder.raw_decode(text[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed, "RECOVERED_JSON"
    return None, "INVALID_JSON"


def scalar(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(str(item).strip() for item in value if str(item).strip())
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return clean(value)


def prediction_fields(parsed: dict[str, Any] | None) -> tuple[str, str, str]:
    """Support the P3 JSON field names without changing the model's answer."""
    if not parsed:
        return "", "", ""
    primary_keys = ("primary_type", "primary_class", "functional_class", "predicted_class", "class")
    secondary_keys = ("secondary_types", "secondary_type", "alternative_classes", "alternatives")
    reason_keys = ("reasoning", "rationale", "evidence", "justification", "explanation")
    primary = next((scalar(parsed[key]) for key in primary_keys if key in parsed), "")
    secondary = next((scalar(parsed[key]) for key in secondary_keys if key in parsed), "")
    rationale = next((scalar(parsed[key]) for key in reason_keys if key in parsed), "")
    return primary, secondary, rationale


def excel_safe(value: Any, limit: int = 32000) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[:limit] + "\n[truncated only in Excel; see Raw_Response_File]"


def manifest_records(raw_input_dir: Path, include_prompt_engineering: bool) -> list[dict[str, Any]]:
    """Read Step 1's manifest, retaining every text file selected for final testing."""
    manifest_path = raw_input_dir / "raw_text_manifest.xlsx"
    text_dir = raw_input_dir / "texts"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Step-1 manifest was not found: {manifest_path}")
    if not text_dir.is_dir():
        raise FileNotFoundError(f"Step-1 text directory was not found: {text_dir}")

    frame = pd.read_excel(manifest_path, sheet_name="BG_Manifest", dtype=str).fillna("")
    bg_column = find_column(frame, ("BG_Folder", "SAP-Nummer", "Teamcenter"))
    text_column = find_column(frame, ("Output_Text_File", "Output Text File"))
    status_column = find_column(frame, ("Status",))
    prompt_column = find_column(frame, ("prompt_engineering", "prompt engineering"))
    if not bg_column or not text_column:
        raise ValueError(f"BG_Manifest needs BG_Folder and Output_Text_File columns. Found: {list(frame.columns)}")

    records: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        status = clean(row.get(status_column)) if status_column else ""
        output_text = Path(clean(row.get(text_column))).expanduser()
        if not output_text.is_file():
            # The output location may have been copied together with the run folder.
            output_text = text_dir / f"{safe_name(clean(row.get(bg_column)))}.txt"
        if status != "SUCCESS" or not output_text.is_file():
            continue
        if not include_prompt_engineering and prompt_column and yes(row.get(prompt_column)):
            continue
        record = {str(column): row[column] for column in frame.columns}
        record.update({"BG_Folder": clean(row.get(bg_column)), "Text_File": str(output_text)})
        records.append(record)
    records.sort(key=lambda row: row["BG_Folder"].casefold())
    return records


def classify_one(
    record: dict[str, Any], fixed_prompt: str, model_id: str, session_id: str,
    raw_response_dir: Path, max_output_tokens: int,
) -> dict[str, Any]:
    bg_folder = str(record["BG_Folder"])
    text_file = Path(record["Text_File"])
    try:
        source_text = text_file.read_text(encoding="utf-8", errors="replace").strip()
        if not source_text:
            raise ValueError("Raw BG text file is empty.")
        connector = load_connector(model_id, session_id)
        user_message = (
            "Klassifiziere genau diese eine Baugruppe anhand des festen P3-Original-Prompts. "
            "Nutze ausschließlich den folgenden vollständigen, quellenerhaltenden Rohtext. "
            "Es wurden keine Dateien angehängt.\n\n"
            "--- BEGIN COMPLETE RAW BG TEXT ---\n"
            f"{source_text}\n"
            "--- END COMPLETE RAW BG TEXT ---"
        )
        # Empty file_paths is deliberate: this is a pure text-input experiment.
        raw = connector.ask_about_files(
            file_paths=[], question=user_message, system_prompt=fixed_prompt,
            generation_config={"temperature": 0.0, "topP": 0.95, "candidateCount": 1,
                               "maxOutputTokens": max_output_tokens},
        )
        raw_path = raw_response_dir / f"{safe_name(bg_folder)}.txt"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(str(raw), encoding="utf-8")
        parsed, json_status = extract_json(str(raw))
        primary, secondary, rationale = prediction_fields(parsed)
        call_error = str(raw).startswith(("Error:", "HTTP error", "Error after"))
        status = "MODEL_CALL_ERROR" if call_error else ("SUCCESS" if parsed else json_status)
        usage = connector.get_last_token_usage() or {}
        return {
            **record,
            "Primary_Type": primary, "Secondary_Types": secondary, "Model_Rationale": rationale,
            "Processing_Status": status, "JSON_Status": json_status,
            "Needs_Review": "yes" if status != "SUCCESS" else "no",
            "Raw_Response_File": str(raw_path), "Raw_Model_Response": excel_safe(raw),
            "Input_Tokens": usage.get("input_tokens", usage.get("prompt_tokens", "")),
            "Output_Tokens": usage.get("output_tokens", usage.get("completion_tokens", "")),
        }
    except Exception as error:
        logging.exception("Failed BG %s with model %s", bg_folder, model_id)
        return {
            **record,
            "Primary_Type": "", "Secondary_Types": "", "Model_Rationale": "",
            "Processing_Status": f"ERROR: {error}", "JSON_Status": "NOT_AVAILABLE",
            "Needs_Review": "yes", "Raw_Response_File": "", "Raw_Model_Response": "",
            "Input_Tokens": "", "Output_Tokens": "",
        }


def write_checkpoint(rows: list[dict[str, Any]], output_path: Path) -> None:
    """Save after each completed BG so an interrupted run remains reviewable."""
    frame = pd.DataFrame(rows)
    if not frame.empty:
        technical = {"Raw_Model_Response", "Raw_Response_File", "Text_File", "Output_Text_File", "Data_Folder_Path"}
        ordered = [column for column in frame.columns if column not in technical]
        ordered.extend(column for column in frame.columns if column in technical)
        frame = frame.loc[:, ordered]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_excel(output_path, index=False, engine="openpyxl")


def run_one_model(
    records: list[dict[str, Any]], fixed_prompt: str, model_alias: str,
    args: argparse.Namespace, run_stamp: str,
) -> Path:
    model = MODEL_REGISTRY[model_alias]
    model_id = model["id"]
    run_dir = args.output_dir / f"raw_text_{safe_name(model_id)}_{run_stamp}"
    raw_response_dir = run_dir / "raw_responses"
    output_path = run_dir / f"classification_raw_text_{safe_name(model_id)}_{run_stamp}.xlsx"
    run_dir.mkdir(parents=True, exist_ok=True)
    session_id = f"raw_text_{safe_name(model_id)}_{run_stamp}"
    completed: list[dict[str, Any]] = []
    logging.info("Starting %s (%s): %d BG raw-text input(s)", model["display"], model_id, len(records))

    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = [
            executor.submit(classify_one, record, fixed_prompt, model_id, session_id,
                            raw_response_dir, args.max_output_tokens)
            for record in records
        ]
        for future in tqdm(as_completed(futures), total=len(futures), desc=model["display"], unit="BG", dynamic_ncols=True):
            result = future.result()
            result.update({
                "Run_Model": model_id, "Run_Model_Display": model["display"],
                "Fixed_Prompt_File": str(FIXED_PROMPT_PATH), "Run_Timestamp": run_stamp,
                "Run_Mode": "complete_raw_text_only_no_attachments",
            })
            completed.append(result)
            write_checkpoint(completed, output_path)

    completed.sort(key=lambda row: str(row["BG_Folder"]).casefold())
    write_checkpoint(completed, output_path)
    logging.info("Completed %s: %s", model["display"], output_path)
    return output_path


def run(args: argparse.Namespace) -> list[Path]:
    if not os.getenv("BOSCH_FARM_SUBSCRIPTION_KEY"):
        raise EnvironmentError("BOSCH_FARM_SUBSCRIPTION_KEY is not set in .env or environment.")
    if args.max_workers <= 0 or args.max_output_tokens <= 0:
        raise ValueError("--max-workers and --max-output-tokens must be positive.")
    if args.max_bgs is not None and args.max_bgs <= 0:
        raise ValueError("--max-bgs must be positive.")

    records = manifest_records(args.raw_input_dir.expanduser(), args.include_prompt_engineering)
    if args.max_bgs:
        records = records[:args.max_bgs]
    if not records:
        raise ValueError("No successful raw BG .txt inputs were found in the specified Step-1 run directory.")

    fixed_prompt = read_fixed_prompt()
    aliases = list(MODEL_REGISTRY) if "all" in args.models else args.models
    args.output_dir.mkdir(parents=True, exist_ok=True)
    run_stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return [run_one_model(records, fixed_prompt, alias, args, run_stamp) for alias in aliases]


def main() -> None:
    load_dotenv(PROJECT_DIR / ".env")
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", force=True)
    outputs = run(args)
    print("Done:")
    for output in outputs:
        print(output.resolve())


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        logging.error("Raw text-only classification did not finish: %s", error)
        sys.exit(1)

# Revised raw-text-only final classification commands.
# Fixed system prompt (not supplied on the command line): .\prompts\P3_original.txt
# Replace <raw_text_run_folder> with the exact Step-1 output folder, for example
# raw_text_only_2026-09-22_22-00-00.  This script sends no original attachment.
#
# Step 2a) Pilot: Gemini 2.5 Pro for the first 5 independent final-test BGs:
# python run_raw_text_only_classification.py --raw-input-dir ".\outputs\raw_text_only_preprocessing\<raw_text_run_folder>" --models gemini-pro --max-bgs 5 --max-workers 1 --max-output-tokens 4000
#
# Step 2b) Full run for one selected model (recommended first full run):
# python run_raw_text_only_classification.py --raw-input-dir ".\outputs\raw_text_only_preprocessing\<raw_text_run_folder>" --models gemini-pro --max-workers 8 --max-output-tokens 4000
#
# Step 2c) Full cross-model experiment: eight separate Excel result workbooks:
# python run_raw_text_only_classification.py --raw-input-dir ".\outputs\raw_text_only_preprocessing\<raw_text_run_folder>" --models all --max-workers 8 --max-output-tokens 4000
#
# Available --models aliases: gemini-pro, gemini-flash, claude-opus, claude-haiku,
# gpt-4o, gpt-4o-mini, deepseek-r1, llama, all.
