"""Evaluate LLM classification results against a Ground Truth Excel file.

This script is intended to stay in the same project folder as ``run_classification.py``.
With no command-line arguments it uses the fixed local project structure:

    Multiple_Models/
    ├─ input/                 Ground Truth Excel
    ├─ outputs/
    │  ├─ valid_results/      only these model results are evaluated
    │  └─ test_outputs/       ignored by this script
    ├─ evaluation_results/    evaluation outputs created by this script
    ├─ run_classification.py
    └─ evaluate_classification.py

Matching priority: SAP number first, Teamcenter/TC number second.
Metrics: Accuracy, macro/weighted Precision, Recall, F1, per-class metrics,
and confusion matrix.

Normal usage from the project folder:

    python evaluate_classification.py

No scikit-learn dependency is required; metrics are calculated with pandas.
"""

from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT_DIR = PROJECT_DIR / "input"
DEFAULT_PREDICTIONS_DIR = PROJECT_DIR / "outputs" / "valid_results"
DEFAULT_OUTPUT_DIR = PROJECT_DIR / "evaluation_results"

PREDICTION_COLUMN_CANDIDATES = (
    "Predicted_Label", "Predicted Label", "Prediction", "Vorhersage",
)
GROUND_TRUTH_LABEL_CANDIDATES = (
    "Ground Truth", "Ground_Truth", "GroundTruth", "ground truth",
    "Funktionsklasse", "Functional class", "Functional_class", "Label_Full",
)
SAP_COLUMN_CANDIDATES = (
    "SAP-Nummer", "SAP Nummer", "SAP_Nummer", "Baugruppennummer",
    "Baugruppen-ID", "Baugruppen_ID", "BG", "ID",
)
TEAMCENTER_COLUMN_CANDIDATES = (
    "Teamcenter ID", "Teamcenter-ID", "Teamcenter Nummer", "Teamcenter-Nummer",
    "Teamcenter_ID", "TC ID", "TC-ID", "TC Nummer", "TC-Nummer",
)
SPECIAL_ERROR_LABELS = {"UNRECOGNISED_RESPONSE", "ERROR", "API_ERROR"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate run_classification.py Excel outputs against Ground Truth."
    )
    source_group = parser.add_mutually_exclusive_group(required=False)
    source_group.add_argument("--prediction-file", type=Path, default=None)
    source_group.add_argument("--predictions-dir", type=Path, default=None)
    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=None,
        help=(
            "Ground Truth Excel. If omitted, the script looks in input/ for "
            "ground_truth.xlsx or one Excel filename containing 'ground' and 'truth'."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Evaluation output folder. Default: project/evaluation_results",
    )
    parser.add_argument("--prediction-column", default=None)
    parser.add_argument("--ground-truth-label-column", default=None)
    parser.add_argument("--sap-column", default=None)
    parser.add_argument("--teamcenter-column", default=None)
    parser.add_argument("--sheet-name", default=0)
    return parser.parse_args()


def normalize_identifier(value: object) -> str:
    """Normalize IDs, including Excel's 123 versus 123.0 variation."""
    if pd.isna(value):
        return ""
    raw = str(value).strip()
    if not raw:
        return ""
    try:
        number = float(raw)
        if number.is_integer():
            raw = str(int(number))
    except ValueError:
        pass
    return re.sub(r"[^A-Za-z0-9]+", "", raw).casefold()


def normalize_label(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def find_column(
    df: pd.DataFrame,
    requested: str | None,
    candidates: tuple[str, ...],
    label: str,
    *,
    required: bool = True,
) -> str | None:
    if requested:
        if requested in df.columns:
            return requested
        raise ValueError(
            f"Requested {label} column '{requested}' was not found. "
            f"Available columns: {list(df.columns)}"
        )
    for candidate in candidates:
        if candidate in df.columns:
            return candidate
    if required:
        raise ValueError(
            f"Could not detect {label} column. Available columns: {list(df.columns)}"
        )
    return None


def read_excel(path: Path, sheet_name: str | int) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Excel file not found: {path}")
    resolved_sheet: str | int = sheet_name
    if isinstance(sheet_name, str) and sheet_name.isdigit():
        resolved_sheet = int(sheet_name)
    return pd.read_excel(path, sheet_name=resolved_sheet)


def find_ground_truth_path(requested: Path | None) -> Path:
    if requested:
        if not requested.is_file():
            raise FileNotFoundError(f"Ground Truth file not found: {requested}")
        return requested

    standard = DEFAULT_INPUT_DIR / "ground_truth.xlsx"
    if standard.is_file():
        return standard

    if not DEFAULT_INPUT_DIR.is_dir():
        raise FileNotFoundError(f"Input folder not found: {DEFAULT_INPUT_DIR}")

    candidates = [
        path for path in DEFAULT_INPUT_DIR.glob("*.xlsx")
        if "ground" in path.stem.casefold() and "truth" in path.stem.casefold()
    ]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise FileNotFoundError(
            "No Ground Truth Excel detected in input/. Name it 'ground_truth.xlsx' "
            "or include both 'ground' and 'truth' in the filename."
        )
    raise ValueError(
        "More than one Ground Truth candidate found in input/: "
        + ", ".join(path.name for path in candidates)
    )


def build_ground_truth_lookup(
    gt_df: pd.DataFrame,
    gt_label_col: str,
    sap_col: str | None,
    tc_col: str | None,
) -> tuple[dict[str, tuple[str, int]], dict[str, tuple[str, int]]]:
    sap_lookup: dict[str, tuple[str, int]] = {}
    tc_lookup: dict[str, tuple[str, int]] = {}

    for idx, row in gt_df.iterrows():
        true_label = normalize_label(row[gt_label_col])
        if not true_label:
            continue

        for column, lookup, id_name in (
            (sap_col, sap_lookup, "SAP"),
            (tc_col, tc_lookup, "Teamcenter"),
        ):
            if not column:
                continue
            identifier = normalize_identifier(row[column])
            if not identifier:
                continue
            if identifier in lookup and lookup[identifier][0] != true_label:
                old_label, old_idx = lookup[identifier]
                raise ValueError(
                    f"Conflicting Ground Truth for {id_name} ID '{row[column]}': "
                    f"row {old_idx + 2}='{old_label}', row {idx + 2}='{true_label}'."
                )
            lookup[identifier] = (true_label, idx)

    return sap_lookup, tc_lookup


def match_prediction_rows(
    pred_df: pd.DataFrame,
    prediction_col: str,
    pred_sap_col: str | None,
    pred_tc_col: str | None,
    sap_lookup: dict[str, tuple[str, int]],
    tc_lookup: dict[str, tuple[str, int]],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    for pred_idx, row in pred_df.iterrows():
        predicted = normalize_label(row[prediction_col])
        sap_value = row[pred_sap_col] if pred_sap_col else pd.NA
        tc_value = row[pred_tc_col] if pred_tc_col else pd.NA
        sap_id = normalize_identifier(sap_value)
        tc_id = normalize_identifier(tc_value)

        true_label = ""
        gt_idx: int | None = None
        match_method = "NOT_MATCHED"

        if sap_id and sap_id in sap_lookup:
            true_label, gt_idx = sap_lookup[sap_id]
            match_method = "SAP"
        elif tc_id and tc_id in tc_lookup:
            true_label, gt_idx = tc_lookup[tc_id]
            match_method = "TEAMCENTER"

        rows.append(
            {
                "Prediction_Row": pred_idx + 2,
                "Ground_Truth_Row": (gt_idx + 2) if gt_idx is not None else pd.NA,
                "SAP_Number": sap_value,
                "Teamcenter_Number": tc_value,
                "Ground_Truth": true_label or pd.NA,
                "Predicted_Label": predicted or pd.NA,
                "Match_Method": match_method,
                "Correct": bool(true_label and predicted and true_label == predicted),
            }
        )

    return pd.DataFrame(rows)


def compute_metrics(
    matched_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float | int]]:
    eval_df = matched_df[
        matched_df["Ground_Truth"].notna() & matched_df["Predicted_Label"].notna()
    ].copy()
    if eval_df.empty:
        raise ValueError("No matched rows with both Ground Truth and prediction were found.")

    y_true = eval_df["Ground_Truth"].astype(str)
    y_pred = eval_df["Predicted_Label"].astype(str)

    true_labels = list(dict.fromkeys(y_true.tolist()))
    predicted_only = [x for x in dict.fromkeys(y_pred.tolist()) if x not in true_labels]
    labels = true_labels + predicted_only

    confusion = pd.crosstab(y_true, y_pred, dropna=False)
    confusion = confusion.reindex(index=labels, columns=labels, fill_value=0)
    confusion.index.name = "Ground Truth"
    confusion.columns.name = "Predicted"

    total = len(eval_df)
    correct = int((y_true == y_pred).sum())
    metric_rows: list[dict[str, object]] = []

    for label in labels:
        tp = int(((y_true == label) & (y_pred == label)).sum())
        fp = int(((y_true != label) & (y_pred == label)).sum())
        fn = int(((y_true == label) & (y_pred != label)).sum())
        tn = total - tp - fp - fn
        support = int((y_true == label).sum())
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        metric_rows.append(
            {
                "Class": label,
                "Precision": precision,
                "Recall": recall,
                "F1": f1,
                "Support": support,
                "TP": tp,
                "FP": fp,
                "FN": fn,
                "TN": tn,
            }
        )

    per_class = pd.DataFrame(metric_rows)
    average_df = per_class[per_class["Support"] > 0].copy()
    support_sum = int(average_df["Support"].sum())

    summary: dict[str, float | int] = {
        "Evaluated_Rows": total,
        "Correct_Rows": correct,
        "Accuracy": correct / total,
        "Macro_Precision": float(average_df["Precision"].mean()),
        "Macro_Recall": float(average_df["Recall"].mean()),
        "Macro_F1": float(average_df["F1"].mean()),
        "Weighted_Precision": float(
            (average_df["Precision"] * average_df["Support"]).sum() / support_sum
        ),
        "Weighted_Recall": float(
            (average_df["Recall"] * average_df["Support"]).sum() / support_sum
        ),
        "Weighted_F1": float(
            (average_df["F1"] * average_df["Support"]).sum() / support_sum
        ),
    }
    return per_class, confusion, summary


def model_name_from_file(path: Path, pred_df: pd.DataFrame) -> str:
    if "Run_Model" in pred_df.columns:
        values = pred_df["Run_Model"].dropna().astype(str).str.strip()
        if not values.empty and values.iloc[0]:
            return values.iloc[0]

    stem = path.stem
    prefix = "classification_all_files_"
    if stem.startswith(prefix):
        remainder = stem[len(prefix):]
        return re.sub(r"_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}$", "", remainder)
    return stem


def safe_filename(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_") or "model"


def collect_prediction_files(args: argparse.Namespace) -> list[Path]:
    if args.prediction_file:
        if not args.prediction_file.is_file():
            raise FileNotFoundError(f"Prediction file not found: {args.prediction_file}")
        return [args.prediction_file]

    directory = args.predictions_dir or DEFAULT_PREDICTIONS_DIR
    if not directory.is_dir():
        raise FileNotFoundError(
            f"Valid results folder not found: {directory}. "
            "Create outputs/valid_results and place the final model result Excel files there."
        )

    files = sorted(directory.glob("classification_all_files_*.xlsx"))
    if not files:
        raise FileNotFoundError(
            f"No classification_all_files_*.xlsx files found in valid results folder: {directory}"
        )
    return files


def evaluate_file(
    prediction_path: Path,
    args: argparse.Namespace,
    sap_lookup: dict[str, tuple[str, int]],
    tc_lookup: dict[str, tuple[str, int]],
) -> tuple[Path, dict[str, object]]:
    pred_df = read_excel(prediction_path, args.sheet_name)
    prediction_col = find_column(
        pred_df, args.prediction_column, PREDICTION_COLUMN_CANDIDATES, "prediction"
    )
    pred_sap_col = find_column(
        pred_df, args.sap_column, SAP_COLUMN_CANDIDATES, "SAP", required=False
    )
    pred_tc_col = find_column(
        pred_df,
        args.teamcenter_column,
        TEAMCENTER_COLUMN_CANDIDATES,
        "Teamcenter",
        required=False,
    )
    if not pred_sap_col and not pred_tc_col:
        raise ValueError(
            f"'{prediction_path.name}' has neither a detectable SAP nor Teamcenter column."
        )

    matched = match_prediction_rows(
        pred_df,
        prediction_col,
        pred_sap_col,
        pred_tc_col,
        sap_lookup,
        tc_lookup,
    )
    per_class, confusion, metrics = compute_metrics(matched)
    model_name = model_name_from_file(prediction_path, pred_df)

    summary_row: dict[str, object] = {
        "Model": model_name,
        "Prediction_File": prediction_path.name,
        "Prediction_Rows": len(matched),
        "Matched_Rows": int((matched["Match_Method"] != "NOT_MATCHED").sum()),
        "Unmatched_Rows": int((matched["Match_Method"] == "NOT_MATCHED").sum()),
        "Missing_Prediction_Rows": int(matched["Predicted_Label"].isna().sum()),
        "Unrecognised_or_Error_Rows": int(
            matched["Predicted_Label"].astype(str).isin(SPECIAL_ERROR_LABELS).sum()
        ),
        **metrics,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / (
        f"evaluation_{safe_filename(model_name)}_{prediction_path.stem}.xlsx"
    )
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        pd.DataFrame([summary_row]).to_excel(writer, sheet_name="Summary", index=False)
        per_class.to_excel(writer, sheet_name="Per_Class", index=False)
        confusion.to_excel(writer, sheet_name="Confusion_Matrix")
        matched.to_excel(writer, sheet_name="Matched_Rows", index=False)

    return output_path, summary_row


def main() -> None:
    args = parse_args()
    prediction_files = collect_prediction_files(args)
    ground_truth_path = find_ground_truth_path(args.ground_truth)
    gt_df = read_excel(ground_truth_path, args.sheet_name)

    gt_label_col = find_column(
        gt_df,
        args.ground_truth_label_column,
        GROUND_TRUTH_LABEL_CANDIDATES,
        "Ground Truth label",
    )
    gt_sap_col = find_column(
        gt_df, args.sap_column, SAP_COLUMN_CANDIDATES, "SAP", required=False
    )
    gt_tc_col = find_column(
        gt_df,
        args.teamcenter_column,
        TEAMCENTER_COLUMN_CANDIDATES,
        "Teamcenter",
        required=False,
    )
    if not gt_sap_col and not gt_tc_col:
        raise ValueError("Ground Truth has neither a detectable SAP nor Teamcenter column.")

    sap_lookup, tc_lookup = build_ground_truth_lookup(
        gt_df, gt_label_col, gt_sap_col, gt_tc_col
    )

    print(f"Ground Truth: {ground_truth_path}")
    print(f"Valid model results: {DEFAULT_PREDICTIONS_DIR}")
    print(f"Evaluation output: {args.output_dir}\n")

    summaries: list[dict[str, object]] = []
    created_files: list[Path] = []

    for prediction_path in prediction_files:
        output_path, summary = evaluate_file(
            prediction_path, args, sap_lookup, tc_lookup
        )
        summaries.append(summary)
        created_files.append(output_path)
        print(
            f"{summary['Model']}: Accuracy={summary['Accuracy']:.4f}, "
            f"Macro-F1={summary['Macro_F1']:.4f}"
        )

    if len(summaries) > 1:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        comparison_path = args.output_dir / f"model_comparison_{timestamp}.xlsx"
        comparison_df = pd.DataFrame(summaries).sort_values(
            by=["Macro_F1", "Accuracy"], ascending=False
        )
        with pd.ExcelWriter(comparison_path, engine="openpyxl") as writer:
            comparison_df.to_excel(writer, sheet_name="Model_Comparison", index=False)
        created_files.append(comparison_path)

    print("\nCreated evaluation files:")
    for path in created_files:
        print(f"- {path}")


if __name__ == "__main__":
    main()
