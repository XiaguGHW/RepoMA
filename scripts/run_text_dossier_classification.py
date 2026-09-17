#!/usr/bin/env python3
"""Run the final text-only Baugruppe classification experiment.

The fixed experiment prompt is read from ``prompts/P3_original.txt``.  Each
input dossier is the text file rendered by ``render_text_dossiers_text_only.py``;
no original PDF, screenshot, BOM, DFC or data sheet is uploaded again.

By default the script runs all eight requested text-input models, creating one
reviewable Excel result workbook per model.  The Bosch Model Farm connector is
used unchanged via ``llm_connector_with_prompt_caching.py``.
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
# This is intentionally fixed to keep every cross-model run on exactly P3 original.
FIXED_PROMPT_PATH = PROJECT_DIR / "prompts" / "P3_original.txt"

# IDs are the deployment/model IDs shown in the Model Farm overview, rather than
# display names.  ``deepseek-r1`` is kept as the normal Farm deployment ID; change
# only this value if your Model Farm overview uses a different R1 deployment ID.
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
        "--dossiers-dir", type=Path, required=True,
        help="Directory named text_dossiers produced by render_text_dossiers_text_only.py.",
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=PROJECT_DIR / "outputs" / "text_only_classification",
        help="Directory for one Excel result workbook per model.",
    )
    parser.add_argument(
        "--models", nargs="+", choices=[*MODEL_REGISTRY, "all"], default=["all"],
        help="Model aliases to run. Default: all eight requested text-input models.",
    )
    parser.add_argument("--max-bgs", type=int, default=None, help="Run only the first N dossiers for a pilot.")
    parser.add_argument("--max-workers", type=int, default=1, help="Concurrent BG requests per model; default 1.")
    parser.add_argument("--max-output-tokens", type=int, default=4000, help="Maximum generated tokens; default 4000.")
    return parser.parse_args()


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "unnamed"


def load_connector(model_id: str, session_id: str) -> Any:
    try:
        from llm_connector_with_prompt_caching import LLMConnector
    except ImportError as error:
        raise ImportError(
            "llm_connector_with_prompt_caching.py must be in the same directory as this script."
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
    """Accept plain JSON or fenced JSON, without inventing a prediction."""
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
    return str(value or "").strip()


def prediction_fields(parsed: dict[str, Any] | None) -> tuple[str, str, str]:
    if not parsed:
        return "", "", ""
    primary_keys = ("primary_type", "primary_class", "functional_class", "predicted_class", "class")
    secondary_keys = ("secondary_types", "secondary_type", "alternative_classes", "alternatives")
    reason_keys = ("reasoning", "rationale", "evidence", "justification", "explanation")
    primary = next((scalar(parsed.get(key)) for key in primary_keys if key in parsed), "")
    secondary = next((scalar(parsed.get(key)) for key in secondary_keys if key in parsed), "")
    rationale = next((scalar(parsed.get(key)) for key in reason_keys if key in parsed), "")
    return primary, secondary, rationale


def excel_safe(text: str, limit: int = 32000) -> str:
    text = str(text or "")
    return text if len(text) <= limit else text[:limit] + "\n[truncated in Excel; see Raw_Response_File]"


def classify_one(
    dossier_path: Path,
    fixed_prompt: str,
    model_id: str,
    session_id: str,
    output_raw_dir: Path,
    max_output_tokens: int,
) -> dict[str, Any]:
    bg_folder = dossier_path.stem
    try:
        dossier = dossier_path.read_text(encoding="utf-8", errors="replace").strip()
        if not dossier:
            raise ValueError("Dossier is empty.")
        connector = load_connector(model_id, session_id)
        user_message = (
            "Klassifiziere genau diese eine Baugruppe anhand des festen Codebook-Prompts. "
            "Nutze ausschließlich die folgenden nachverfolgbaren Textfakten.\n\n"
            "--- BEGIN TEXT-ONLY DOSSIER ---\n"
            f"{dossier}\n"
            "--- END TEXT-ONLY DOSSIER ---"
        )
        raw = connector.ask_about_files(
            [], user_message, system_prompt=fixed_prompt,
            generation_config={"temperature": 0.0, "maxOutputTokens": max_output_tokens},
        )
        raw_path = output_raw_dir / f"{safe_name(bg_folder)}.txt"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(raw, encoding="utf-8")
        parsed, json_status = extract_json(raw)
        primary, secondary, rationale = prediction_fields(parsed)
        status = "SUCCESS" if parsed else json_status
        if raw.startswith(("Error:", "HTTP error", "Error after")):
            status = "MODEL_CALL_ERROR"
        usage = connector.get_last_token_usage() or {}
        return {
            "BG_Folder": bg_folder,
            "Dossier_File": str(dossier_path),
            "Primary_Type": primary,
            "Secondary_Types": secondary,
            "Model_Rationale": rationale,
            "Processing_Status": status,
            "JSON_Status": json_status,
            "Needs_Review": "yes" if status != "SUCCESS" else "no",
            "Raw_Response_File": str(raw_path),
            "Raw_Model_Response": excel_safe(raw),
            "Input_Tokens": usage.get("input_tokens", usage.get("prompt_tokens", "")),
            "Output_Tokens": usage.get("output_tokens", usage.get("completion_tokens", "")),
        }
    except Exception as error:
        logging.exception("Failed BG %s with model %s", bg_folder, model_id)
        return {
            "BG_Folder": bg_folder, "Dossier_File": str(dossier_path),
            "Primary_Type": "", "Secondary_Types": "", "Model_Rationale": "",
            "Processing_Status": f"ERROR: {error}", "JSON_Status": "NOT_AVAILABLE",
            "Needs_Review": "yes", "Raw_Response_File": "", "Raw_Model_Response": "",
            "Input_Tokens": "", "Output_Tokens": "",
        }


def run_one_model(
    dossiers: list[Path], fixed_prompt: str, model_alias: str, args: argparse.Namespace, run_stamp: str,
) -> Path:
    model = MODEL_REGISTRY[model_alias]
    model_id = model["id"]
    model_dir = args.output_dir / f"{safe_name(model_id)}_{run_stamp}"
    raw_dir = model_dir / "raw_responses"
    model_dir.mkdir(parents=True, exist_ok=True)
    session_id = f"text_dossier_{safe_name(model_id)}_{run_stamp}"
    rows: list[dict[str, Any]] = []
    logging.info("Starting %s (%s): %d BG dossier(s)", model["display"], model_id, len(dossiers))
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = [
            executor.submit(classify_one, path, fixed_prompt, model_id, session_id, raw_dir, args.max_output_tokens)
            for path in dossiers
        ]
        for future in tqdm(as_completed(futures), total=len(futures), desc=model["display"], unit="BG", dynamic_ncols=True):
            rows.append(future.result())
    rows.sort(key=lambda row: str(row["BG_Folder"]).casefold())
    for row in rows:
        row.update({
            "Run_Model": model_id,
            "Run_Model_Display": model["display"],
            "Fixed_Prompt_File": str(FIXED_PROMPT_PATH),
            "Run_Timestamp": run_stamp,
        })
    output_path = model_dir / f"classification_{safe_name(model_id)}_{run_stamp}.xlsx"
    pd.DataFrame(rows).to_excel(output_path, index=False, engine="openpyxl")
    logging.info("Completed %s: %s", model["display"], output_path)
    return output_path


def run(args: argparse.Namespace) -> list[Path]:
    if not os.getenv("BOSCH_FARM_SUBSCRIPTION_KEY"):
        raise EnvironmentError("BOSCH_FARM_SUBSCRIPTION_KEY is not set in .env or environment.")
    if args.max_workers <= 0 or args.max_output_tokens <= 0:
        raise ValueError("--max-workers and --max-output-tokens must be positive.")
    if args.max_bgs is not None and args.max_bgs <= 0:
        raise ValueError("--max-bgs must be positive.")
    dossier_dir = args.dossiers_dir.expanduser()
    if not dossier_dir.is_dir():
        raise FileNotFoundError(f"Dossier directory does not exist: {dossier_dir}")
    dossiers = sorted(dossier_dir.glob("*.txt"), key=lambda path: path.name.casefold())
    if args.max_bgs:
        dossiers = dossiers[:args.max_bgs]
    if not dossiers:
        raise FileNotFoundError(f"No dossier .txt files found in: {dossier_dir}")
    fixed_prompt = read_fixed_prompt()
    aliases = list(MODEL_REGISTRY) if "all" in args.models else args.models
    args.output_dir.mkdir(parents=True, exist_ok=True)
    run_stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return [run_one_model(dossiers, fixed_prompt, alias, args, run_stamp) for alias in aliases]


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
        logging.error("Text-dossier classification did not finish: %s", error)
        sys.exit(1)

# Final experiment commands. Fixed prompt: .\prompts\P3_original.txt
# First test one model with the first 5 dossiers:
# python run_text_dossier_classification.py --dossiers-dir ".\outputs\text_only_preprocessing\facts_<model>_<timestamp>\text_dossiers" --models gemini-pro --max-bgs 5 --max-workers 8 --max-output-tokens 4000
# Run one selected model for all final-test dossiers:
# python run_text_dossier_classification.py --dossiers-dir ".\outputs\text_only_preprocessing\facts_<model>_<timestamp>\text_dossiers" --models gemini-pro --max-workers 8 --max-output-tokens 4000
# Run all eight requested models sequentially (eight separate Excel workbooks):
# python run_text_dossier_classification.py --dossiers-dir ".\outputs\text_only_preprocessing\facts_<model>_<timestamp>\text_dossiers" --models all --max-workers 8 --max-output-tokens 4000
