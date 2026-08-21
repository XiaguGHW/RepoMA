"""Evaluate one or more LLM classification Excel files against a Ground Truth Excel.

The script is designed for the output of ``run_classification.py``. It matches each
Baugruppe to Ground Truth by SAP number first and Teamcenter number second, then
calculates multiclass Accuracy, Precision, Recall, F1 and a confusion matrix.

Typical usage:

    python .\scripts\evaluate_classification.py \
        --predictions-dir .\outputs \
        --ground-truth .\input\ground_truth.xlsx

A single result file can also be evaluated:

    python .\scripts\evaluate_classification.py \
        --prediction-file .\outputs\classification_all_files_gpt-5_....xlsx \
        --ground-truth .\input\ground_truth.xlsx

No scikit-learn dependency is required; the metrics are calculated with pandas.
"""

from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path

import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent if SCRIPT_DIR.name.casefold() == "scripts" else SCRIPT_DIR
DEFAULT_PREDICTIONS_DIR = PROJECT_DIR / "outputs"
DEFAULT_GROUND_TRUTH = PROJECT_DIR / "input" / "ground_truth.xlsx"
DEFAULT_OUTPUT_DIR = PROJECT_DIR / "outputs" / "evaluation"

PREDICTION_COLUMN_CANDIDATES = (
    "Predicted_Label",
    "Predicted Label",
    "Prediction",
    "Vorhersage",
)

GROUND_TRUTH_LABEL_CANDIDATES = (
    "Ground Truth",
    "Ground_Truth",
    "GroundTruth",
    "ground truth",
    "Funktionsklasse",
    "Functional class",
    "Functional_class",
    "Label_Full",
)

SAP_COLUMN_CANDIDATES = (
    "SAP-Nummer",
    "SAP Nummer",
    "SAP_Nummer",
    "Baugruppennummer",
    "Baugruppen-ID",
    "Baugruppen_ID",
    "BG",
    "ID",
)

TEAMCENTER_COLUMN_CANDIDATES = (
    "Teamcenter ID",
    "Teamcenter-ID",
    "Teamcenter Nummer",
    "Teamcenter-Nummer",
    "Teamcenter_ID",
    "TC ID",
    "TC-ID",
    "TC Nummer",
    "TC-Nummer",
)

SPECIAL_ERROR_LABELS = {
    "UNRECOGNISED_RESPONSE",
    "ERROR",
    "API_ERROR",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate LLM classification Excel results against Ground Truth using "
            "SAP/Teamcenter matching."
        )
    )
    source_group = parser.add_mutually_exclusive_group(required=False)
    source_group.add_argument(
        "--prediction-file",
        type=Path,
        default=None,
        help="Evaluate one classification result Excel file.",
    )
    source_group.add_argument(
        "--predictions-dir",
        type=Path,
        default=None,
        help=(
            "Evaluate all classification_all_files_*.xlsx files in this folder. "
            "Defaults to the project's outputs folder."
        ),
    )
    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=DEFAULT_GROUND_TRUTH,
        help="Ground Truth Excel file. Default: input/ground_truth.xlsx",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Folder for evaluation workbooks. Default: outputs/evaluation",
    )
    parser.add_argument("--prediction-column", default=None)
    parser.add_argument("--ground-truth-label-column", default=None)
    parser.add_argument("--sap-column", default=None)
    parser.add_argument("--teamcenter-column", default=None)
    parser.add_argument(
        "--sheet-name",
        default=0,
        help="Excel sheet name or index. Default: first sheet.",
    )
    return parser.parse_args()


def normalize_identifier(value: object) -> str:
    """Normalize SAP/TC IDs for safe comparison, including Excel's 123 vs 123.0."""
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


def build_ground_truth_lookup(
    gt_df: pd.DataFrame,
    gt_label_col: str,
    sap_col: str | None,
    tc_col: str | None,
) -> tuple[dict[str, tuple[str, int]], dict[str, tuple[str, int]]]:
    """Build unique SAP and TC lookups. Duplicate IDs with conflicting labels fail loudly."""
    sap_lookup: dict[str, tuple[str, int]] = {}
    tc_lookup: dict[str, tuple[str, int]] = {}

    for idx, row in gt_df.iterrows():
        label = normalize_label(row[gt_label_col])
        if not label:
            continue

        for column, lookup, identifier_name in (
            (sap_col, sap_lookup, "SAP"),
            (tc_col, tc_lookup, "Teamcenter"),
        ):
            if not column:
                continue
            identifier = normalize_identifier(row[column])
            if not identifier:
                continue

            if identifier in lookup and lookup[identifier][0] != label:
                previous_label, previous_row = lookup[identifier]
                raise ValueError(
                    f"Conflicting Ground Truth for {identifier_name} ID '{row[column]}': "
                    f"row {previous_row + 2}='{previous_label}', row {idx + 2}='{label}'."
                )
            lookup[identifier] = (label, idx)

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

        # Priority 1: exact normalized SAP number.
        if sap_id and sap_id in sap_lookup:
            true_label, gt_idx = sap_lookup[sap_id]
            match_method = "SAP"

        # Priority 2: Teamcenter number as fallback.
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


def compute_metrics(matched_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float | int]]:
    """Return per-class metrics, confusion matrix, and overall summary metrics."""
    eval_df = matched_df[
        matched_df["Ground_Truth"].notna() & matched_df["Predicted_Label"].notna()
    ].copy()

    if eval_df.empty:
        raise ValueError("No matched rows with both Ground Truth and prediction were found.")

    y_true = eval_df["Ground_Truth"].astype(str)
    y_pred = eval_df["Predicted_Label"].astype(str)

    true_labels = list(dict.fromkeys(y_true.tolist()))
    predicted_only_labels = [label for label in dict.fromkeys(y_pred.tolist()) if label not in true_labels]
    labels = true_labels + predicted_only_labels

    confusion = pd.crosstab(y_true, y_pred, dropna=False)
    confusion = confusion.reindex(index=labels, columns=labels, fill_value=0)
    confusion.index.name = "Ground Truth"
    confusion.columns.name = "Predicted"

    metric_rows: list[dict[str, object]] = []
    total = len(eval_df)
    correct = int((y_true == y_pred).sum())

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

    # For macro/weighted averages, use actual Ground Truth classes only. A pure prediction
    # error label such as UNRECOGNISED_RESPONSE has support 0 and should not become a new
    # functional class in the macro average.
    averaging_df = per_class[per_class["Support"] > 0].copy()
    macro_precision = float(averaging_df["Precision"].mean())
    macro_recall = float(averaging_df["Recall"].mean())
    macro_f1 = float(averaging_df["F1"].mean())

    support_sum = int(averaging_df["Support"].sum())
    weighted_precision = float(
        (averaging_df["Precision"] * averaging_df["Support"]).sum() / support_sum
    )
    weighted_recall = float(
        (averaging_df["Recall"] * averaging_df["Support"]).sum() / support_sum
    )
    weighted_f1 = float(
        (averaging_df["F1"] * averaging_df["Support"]).sum() / support_sum
    )

    summary: dict[str, float | int] = {
        "Evaluated_Rows": total,
        "Correct_Rows": correct,
        "Accuracy": correct / total,
        "Macro_Precision": macro_precision,
        "Macro_Recall": macro_recall,
        "Macro_F1": macro_f1,
        "Weighted_Precision": weighted_precision,
        "Weighted_Recall": weighted_recall,
        "Weighted_F1": weighted_f1,
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
        # Remove the timestamp produced by run_classification.py.
        return re.sub(r"_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}$", "", remainder)
    return stem


def safe_filename(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_") or "model"


def evaluate_file(
    prediction_path: Path,
    gt_df: pd.DataFrame,
    gt_label_col: str,
    gt_sap_col: str | None,
    gt_tc_col: str | None,
    args: argparse.Namespace,
    sap_lookup: dict[str, tuple[str, int]],
    tc_lookup: dict[str, tuple[str, int]],
) -> tuple[Path, dict[str, object]]:
    pred_df = read_excel(prediction_path, args.sheet_name)
    prediction_col = find_column(
        pred_df,
        args.prediction_column,
        PREDICTION_COLUMN_CANDIDATES,
        "prediction",
    )
    pred_sap_col = find_column(
        pred_df,
        args.sap_column,
        SAP_COLUMN_CANDIDATES,
        "SAP",
        required=False,
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

    matched_count = int((matched["Match_Method"] != "NOT_MATCHED").sum())
    unmatched_count = int((matched["Match_Method"] == "NOT_MATCHED").sum())
    missing_prediction_count = int(matched["Predicted_Label"].isna().sum())
    unrecognised_count = int(
        matched["Predicted_Label"].astype(str).isin(SPECIAL_ERROR_LABELS).sum()
    )

    summary_row: dict[str, object] = {
        "Model": model_name,
        "Prediction_File": prediction_path.name,
        "Prediction_Rows": len(matched),
        "Matched_Rows": matched_count,
        "Unmatched_Rows": unmatched_count,
        "Missing_Prediction_Rows": missing_prediction_count,
        "Unrecognised_or_Error_Rows": unrecognised_count,
        **metrics,
    }

    summary_df = pd.DataFrame([summary_row])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / f"evaluation_{safe_filename(model_name)}_{prediction_path.stem}.xlsx"

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="Summary", index=False)
        per_class.to_excel(writer, sheet_name="Per_Class", index=False)
        confusion.to_excel(writer, sheet_name="Confusion_Matrix")
        matched.to_excel(writer, sheet_name="Matched_Rows", index=False)

    return output_path, summary_row


def collect_prediction_files(args: argparse.Namespace) -> list[Path]:
    if args.prediction_file:
        if not args.prediction_file.is_file():
            raise FileNotFoundError(f"Prediction file not found: {args.prediction_file}")
        return [args.prediction_file]

    directory = args.predictions_dir or DEFAULT_PREDICTIONS_DIR
    if not directory.is_dir():
        raise FileNotFoundError(f"Predictions directory not found: {directory}")

    files = sorted(directory.glob("classification_all_files_*.xlsx"))
    if not files:
        raise FileNotFoundError(
            f"No 'classification_all_files_*.xlsx' files found in: {directory}"
        )
    return files


def main() -> None:
    args = parse_args()
    prediction_files = collect_prediction_files(args)
    gt_df = read_excel(args.ground_truth, args.sheet_name)

    gt_label_col = find_column(
        gt_df,
        args.ground_truth_label_column,
        GROUND_TRUTH_LABEL_CANDIDATES,
        "Ground Truth label",
    )
    gt_sap_col = find_column(
        gt_df,
        args.sap_column,
        SAP_COLUMN_CANDIDATES,
        "SAP",
        required=False,
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
        gt_df,
        gt_label_col,
        gt_sap_col,
        gt_tc_col,
    )

    all_summaries: list[dict[str, object]] = []
    created_files: list[Path] = []

    for prediction_path in prediction_files:
        output_path, summary_row = evaluate_file(
            prediction_path,
            gt_df,
            gt_label_col,
            gt_sap_col,
            gt_tc_col,
            args,
            sap_lookup,
            tc_lookup,
        )
        created_files.append(output_path)
        all_summaries.append(summary_row)
        print(
            f"{summary_row['Model']}: "
            f"Accuracy={summary_row['Accuracy']:.4f}, "
            f"Macro-F1={summary_row['Macro_F1']:.4f} -> {output_path}"
        )

    if len(all_summaries) > 1:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        comparison_path = args.output_dir / f"model_comparison_{timestamp}.xlsx"
        comparison_df = pd.DataFrame(all_summaries).sort_values(
            by=["Macro_F1", "Accuracy"], ascending=False
        )
        with pd.ExcelWriter(comparison_path, engine="openpyxl") as writer:
            comparison_df.to_excel(writer, sheet_name="Model_Comparison", index=False)
        created_files.append(comparison_path)
        print(f"Combined model comparison -> {comparison_path}")

    print("\nCreated evaluation files:")
    for path in created_files:
        print(f"- {path}")


if __name__ == "__main__":
    main()
