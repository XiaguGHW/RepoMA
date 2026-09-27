from __future__ import annotations

"""
Batch evaluation for independent Excel classification experiments.

Place this script in the SAME folder as the experiment .xlsx files and run:
    python batch_evaluate_excel_experiments.py

Rules:
- Every .xlsx file is one independent experiment.
- Only worksheet "Sheet1" is read; all other worksheets are ignored.
- Ground Truth: header lookup first, fallback column F.
- Regime E1/E2/M: header lookup first, fallback column G.
- Prediction: header lookup first, fallback column I.
- Blank prediction = nicht auswertbar and excluded from classification metrics.
- E1/E2/M/Gesamt use strict primary Ground Truth.
- M confusion matrix also uses strict primary Ground Truth.
- Strict Overall Accuracy and Accepted-Set Overall Accuracy are separate metrics.
- All official metrics are calculated with custom pure-Python logic.
- sklearn independently recalculates confusion matrix and P/R/F1 metrics as a cross-check.
"""

from pathlib import Path
from math import isclose
import re

from openpyxl import load_workbook, Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

try:
    import numpy as np
    from sklearn.metrics import confusion_matrix as sk_confusion_matrix
    from sklearn.metrics import precision_recall_fscore_support
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


OUTPUT_FILENAME = "Evaluation_Summary.xlsx"
INPUT_SHEET_NAME = "Sheet1"

# Fixed class order for every confusion matrix and class-wise result.
CANONICAL_LABELS = [
    "Lineareinheit",
    "Greifer",
    "Roboter",
    "Rotationseinheit",
    "Multi-Achs-System (Gantry)",
    "Kombinierte Einheit",
    "Keine der verfügbaren Klassen",
]

LABEL_ALIASES_RAW = {
    "Lineareinheit": "Lineareinheit",
    "Greifer": "Greifer",
    "Roboter": "Roboter",
    "Rotationseinheit": "Rotationseinheit",

    # Same class:
    "Gantry": "Multi-Achs-System (Gantry)",
    "Multi-Achs-System (Gantry)": "Multi-Achs-System (Gantry)",

    # Same class:
    "Umsetzeinheit": "Kombinierte Einheit",
    "Kombinierte Einheit": "Kombinierte Einheit",

    "Keine der verfügbaren Klassen": "Keine der verfügbaren Klassen",
}

GROUND_TRUTH_HEADERS = ["Ground Truth", "Groundtruth", "Ground_Truth", "GT"]
REGIME_HEADERS = ["Register", "Regime", "Eindeutigkeit", "GT Regime", "Ground Truth Regime"]
PREDICTION_HEADERS = ["Predicted_Label", "Predicted Label", "Prediction", "LLM Output", "Output"]
ALTERNATIVE_GT_HEADERS = [
    "Weitere zulässige Ground Truth",
    "Weitere zulaessige Ground Truth",
    "Alternative Ground Truth",
    "Alternative GT",
    "Accepted Alternative",
    "Weitere Ground Truth",
]

FALLBACK_GT_COL = 6
FALLBACK_REGIME_COL = 7
FALLBACK_PRED_COL = 9
VALID_REGIMES = ("E1", "E2", "M")


def norm_text(value) -> str:
    if value is None:
        return ""
    text = str(value).strip().replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", text)


def key(value) -> str:
    return re.sub(r"[^a-z0-9äöüß]+", "", norm_text(value).casefold())


LABEL_ALIASES = {key(k): v for k, v in LABEL_ALIASES_RAW.items()}
for label in CANONICAL_LABELS:
    LABEL_ALIASES.setdefault(key(label), label)


def normalize_label(value):
    raw = norm_text(value)
    if not raw:
        return None

    k = key(raw)
    if k in LABEL_ALIASES:
        return LABEL_ALIASES[k]

    # Conservative fallback: only accept if exactly one known class alias
    # occurs in the raw text.
    matched = {
        canonical
        for alias_key, canonical in LABEL_ALIASES.items()
        if alias_key and alias_key in k
    }
    if len(matched) == 1:
        return next(iter(matched))

    return f"__UNKNOWN__:{raw}"


def normalize_regime(value):
    value = norm_text(value).upper().replace(" ", "")
    return value if value in VALID_REGIMES else None


def find_header_column(ws, candidates):
    wanted = {key(x) for x in candidates}
    for cell in ws[1]:
        if key(cell.value) in wanted:
            return cell.column
    return None


def read_experiment(path: Path):
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        if INPUT_SHEET_NAME not in wb.sheetnames:
            raise ValueError(f'worksheet "{INPUT_SHEET_NAME}" not found')

        ws = wb[INPUT_SHEET_NAME]
        gt_col = find_header_column(ws, GROUND_TRUTH_HEADERS) or FALLBACK_GT_COL
        regime_col = find_header_column(ws, REGIME_HEADERS) or FALLBACK_REGIME_COL
        pred_col = find_header_column(ws, PREDICTION_HEADERS) or FALLBACK_PRED_COL
        alt_col = find_header_column(ws, ALTERNATIVE_GT_HEADERS)

        rows = []
        for r in range(2, ws.max_row + 1):
            raw_gt = ws.cell(r, gt_col).value
            raw_regime = ws.cell(r, regime_col).value
            raw_pred = ws.cell(r, pred_col).value
            raw_alt = ws.cell(r, alt_col).value if alt_col else None

            if all(norm_text(x) == "" for x in (raw_gt, raw_regime, raw_pred, raw_alt)):
                continue

            gt = normalize_label(raw_gt)
            regime = normalize_regime(raw_regime)
            pred = normalize_label(raw_pred)
            alt = normalize_label(raw_alt)

            row_valid = gt is not None and regime is not None
            rows.append({
                "excel_row": r,
                "raw_gt": raw_gt,
                "raw_regime": raw_regime,
                "raw_pred": raw_pred,
                "raw_alt": raw_alt,
                "gt": gt,
                "regime": regime,
                "pred": pred,
                "alt": alt,
                "row_valid": row_valid,
                "issue": "" if row_valid else "Missing/invalid Ground Truth or Regime",
            })

        return rows, {
            "gt_col": gt_col,
            "regime_col": regime_col,
            "pred_col": pred_col,
            "alt_col": alt_col,
        }
    finally:
        wb.close()


def safe_div(a, b):
    return a / b if b else 0.0


def build_confusion_matrix(rows):
    idx = {label: i for i, label in enumerate(CANONICAL_LABELS)}
    n = len(CANONICAL_LABELS)
    cm = [[0] * n for _ in range(n)]

    for row in rows:
        gt, pred = row["gt"], row["pred"]
        if gt not in idx:
            raise ValueError(f"Unknown Ground Truth after normalization: {gt!r}")
        if pred not in idx:
            raise ValueError(f"Unknown prediction after normalization: {pred!r}")
        cm[idx[gt]][idx[pred]] += 1

    return cm


def metrics_from_cm(cm):
    n_classes = len(CANONICAL_LABELS)
    n_samples = sum(sum(r) for r in cm)
    class_metrics = []

    for c, label in enumerate(CANONICAL_LABELS):
        tp = cm[c][c]
        fn = sum(cm[c][j] for j in range(n_classes) if j != c)
        fp = sum(cm[i][c] for i in range(n_classes) if i != c)
        tn = n_samples - tp - fn - fp

        assert tp + tn + fp + fn == n_samples

        support = tp + fn
        precision = safe_div(tp, tp + fp)
        recall = safe_div(tp, tp + fn)
        f1 = safe_div(2 * precision * recall, precision + recall)
        accuracy_ovr = safe_div(tp + tn, n_samples)

        class_metrics.append({
            "class": label,
            "support": support,
            "TP": tp,
            "TN": tn,
            "FP": fp,
            "FN": fn,
            "accuracy_ovr": accuracy_ovr,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        })

    total_support = sum(x["support"] for x in class_metrics)
    correct = sum(cm[i][i] for i in range(n_classes))

    macro_precision = sum(x["precision"] for x in class_metrics) / n_classes
    macro_recall = sum(x["recall"] for x in class_metrics) / n_classes
    macro_f1 = sum(x["f1"] for x in class_metrics) / n_classes

    weighted_precision = safe_div(
        sum(x["precision"] * x["support"] for x in class_metrics), total_support
    )
    weighted_recall = safe_div(
        sum(x["recall"] * x["support"] for x in class_metrics), total_support
    )
    weighted_f1 = safe_div(
        sum(x["f1"] * x["support"] for x in class_metrics), total_support
    )

    sum_tp = sum(x["TP"] for x in class_metrics)
    sum_tn = sum(x["TN"] for x in class_metrics)
    sum_fp = sum(x["FP"] for x in class_metrics)
    sum_fn = sum(x["FN"] for x in class_metrics)
    assert sum_tp + sum_tn + sum_fp + sum_fn == n_samples * n_classes

    return {
        "n": n_samples,
        "correct": correct,
        "accuracy": safe_div(correct, n_samples),
        "macro_precision": macro_precision,
        "macro_recall": macro_recall,
        "macro_f1": macro_f1,
        "weighted_precision": weighted_precision,
        "weighted_recall": weighted_recall,
        "weighted_f1": weighted_f1,
        "sum_TP": sum_tp,
        "sum_TN": sum_tn,
        "sum_FP": sum_fp,
        "sum_FN": sum_fn,
        "class_metrics": class_metrics,
    }


def evaluate_scope(rows, regime=None):
    population = [
        r for r in rows
        if r["row_valid"] and (regime is None or r["regime"] == regime)
    ]
    evaluated = [r for r in population if r["pred"] is not None]

    # Unknown nonblank labels must never silently disappear.
    for r in evaluated:
        if str(r["gt"]).startswith("__UNKNOWN__"):
            raise ValueError(f"Row {r['excel_row']}: unknown GT {r['raw_gt']!r}")
        if str(r["pred"]).startswith("__UNKNOWN__"):
            raise ValueError(f"Row {r['excel_row']}: unknown prediction {r['raw_pred']!r}")

    cm = build_confusion_matrix(evaluated)
    metrics = metrics_from_cm(cm)
    return population, evaluated, cm, metrics


def overall_accuracies(rows):
    population = [r for r in rows if r["row_valid"]]
    evaluated = [r for r in population if r["pred"] is not None]

    for r in evaluated:
        if str(r["gt"]).startswith("__UNKNOWN__"):
            raise ValueError(f"Row {r['excel_row']}: unknown GT {r['raw_gt']!r}")
        if str(r["pred"]).startswith("__UNKNOWN__"):
            raise ValueError(f"Row {r['excel_row']}: unknown prediction {r['raw_pred']!r}")
        if r["alt"] is not None and str(r["alt"]).startswith("__UNKNOWN__"):
            raise ValueError(f"Row {r['excel_row']}: unknown alternative GT {r['raw_alt']!r}")

    strict_correct = sum(r["pred"] == r["gt"] for r in evaluated)

    accepted_correct = 0
    for r in evaluated:
        accepted = {r["gt"]}
        # Alternative GT changes correctness only for M.
        if r["regime"] == "M" and r["alt"] is not None:
            accepted.add(r["alt"])
        if r["pred"] in accepted:
            accepted_correct += 1

    n_total = len(population)
    n_eval = len(evaluated)

    return {
        "n_total": n_total,
        "n_auswertbar": n_eval,
        "n_nicht_auswertbar": n_total - n_eval,
        "coverage": safe_div(n_eval, n_total),
        "strict_correct": strict_correct,
        "strict_accuracy": safe_div(strict_correct, n_eval),
        "accepted_correct": accepted_correct,
        "accepted_accuracy": safe_div(accepted_correct, n_eval),
    }


def sklearn_cross_check(rows, custom_cm, custom_metrics, context):
    if not SKLEARN_AVAILABLE:
        return "SKIPPED (sklearn not installed)"

    y_true = [r["gt"] for r in rows]
    y_pred = [r["pred"] for r in rows]

    sk_cm = sk_confusion_matrix(y_true, y_pred, labels=CANONICAL_LABELS)
    if not np.array_equal(np.array(custom_cm, dtype=int), sk_cm):
        raise AssertionError(f"{context}: custom confusion matrix != sklearn")

    p, r, f1, support = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=CANONICAL_LABELS,
        average=None,
        zero_division=0,
    )

    for i, custom in enumerate(custom_metrics["class_metrics"]):
        if custom["support"] != int(support[i]):
            raise AssertionError(f"{context}: support mismatch for {custom['class']}")
        if not isclose(custom["precision"], float(p[i]), abs_tol=1e-12):
            raise AssertionError(f"{context}: precision mismatch for {custom['class']}")
        if not isclose(custom["recall"], float(r[i]), abs_tol=1e-12):
            raise AssertionError(f"{context}: recall mismatch for {custom['class']}")
        if not isclose(custom["f1"], float(f1[i]), abs_tol=1e-12):
            raise AssertionError(f"{context}: F1 mismatch for {custom['class']}")

    for avg, names in [
        ("macro", ("macro_precision", "macro_recall", "macro_f1")),
        ("weighted", ("weighted_precision", "weighted_recall", "weighted_f1")),
    ]:
        sp, sr, sf, _ = precision_recall_fscore_support(
            y_true,
            y_pred,
            labels=CANONICAL_LABELS,
            average=avg,
            zero_division=0,
        )
        for actual, name in zip((sp, sr, sf), names):
            if not isclose(custom_metrics[name], float(actual), abs_tol=1e-12):
                raise AssertionError(f"{context}: {name} mismatch")

    return "PASS"


HEADER_FILL = PatternFill("solid", fgColor="D9EAF7")
SUBHEADER_FILL = PatternFill("solid", fgColor="EDEDED")
HEADER_FONT = Font(bold=True)
PERCENT_FMT = "0.0%"


def style_header(ws, row=1):
    for cell in ws[row]:
        if cell.value is not None:
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = Alignment(horizontal="center", vertical="center")


def auto_width(ws, min_width=10, max_width=40):
    for col_cells in ws.columns:
        col_idx = col_cells[0].column
        max_len = max(len(str(c.value)) if c.value is not None else 0 for c in col_cells)
        ws.column_dimensions[get_column_letter(col_idx)].width = min(
            max(max_len + 2, min_width), max_width
        )


def write_output(results, output_path):
    wb = Workbook()
    wb.remove(wb.active)

    ws = wb.create_sheet("Experiment_Summary")
    ws.append([
        "Experiment", "N total", "N auswertbar", "N nicht auswertbar", "Coverage",
        "Strict Overall Correct", "Strict Overall Accuracy",
        "Accepted-Set Correct", "Accepted-Set Overall Accuracy",
        "E1 N", "E1 Accuracy", "E1 Macro Precision", "E1 Macro Recall", "E1 Macro F1", "E1 Weighted F1",
        "E2 N", "E2 Accuracy", "E2 Macro Precision", "E2 Macro Recall", "E2 Macro F1", "E2 Weighted F1",
        "M N", "M Accuracy", "M Macro Precision", "M Macro Recall", "M Macro F1", "M Weighted F1",
        "Gesamt N", "Gesamt Accuracy", "Gesamt Macro Precision", "Gesamt Macro Recall", "Gesamt Macro F1", "Gesamt Weighted F1",
        "sklearn verification", "Alternative-GT column detected",
    ])
    style_header(ws)
    ws.freeze_panes = "A2"

    for res in results:
        overall = res["overall"]
        row = [
            res["experiment"],
            overall["n_total"],
            overall["n_auswertbar"],
            overall["n_nicht_auswertbar"],
            overall["coverage"],
            overall["strict_correct"],
            overall["strict_accuracy"],
            overall["accepted_correct"],
            overall["accepted_accuracy"],
        ]
        for scope in ("E1", "E2", "M", "Gesamt"):
            m = res["scopes"][scope]["metrics"]
            row.extend([
                m["n"], m["accuracy"], m["macro_precision"], m["macro_recall"],
                m["macro_f1"], m["weighted_f1"],
            ])
        row.extend([
            res["sklearn_status"],
            "Yes" if res["columns"]["alt_col"] else "No",
        ])
        ws.append(row)

    for col in [5,7,9,11,12,13,14,15,17,18,19,20,21,23,24,25,26,27,29,30,31,32,33]:
        for r in range(2, ws.max_row + 1):
            ws.cell(r, col).number_format = PERCENT_FMT
    auto_width(ws)

    ws = wb.create_sheet("Regime_Metrics")
    ws.append([
        "Experiment", "Scope", "N auswertbar", "Correct", "Strict Accuracy",
        "Macro Precision", "Macro Recall", "Macro F1",
        "Weighted Precision", "Weighted Recall", "Weighted F1",
        "Sum TP", "Sum TN", "Sum FP", "Sum FN",
    ])
    style_header(ws)
    ws.freeze_panes = "A2"
    for res in results:
        for scope in ("E1", "E2", "M", "Gesamt"):
            m = res["scopes"][scope]["metrics"]
            ws.append([
                res["experiment"], scope, m["n"], m["correct"], m["accuracy"],
                m["macro_precision"], m["macro_recall"], m["macro_f1"],
                m["weighted_precision"], m["weighted_recall"], m["weighted_f1"],
                m["sum_TP"], m["sum_TN"], m["sum_FP"], m["sum_FN"],
            ])
    for col in range(5, 12):
        for r in range(2, ws.max_row + 1):
            ws.cell(r, col).number_format = PERCENT_FMT
    auto_width(ws)

    ws = wb.create_sheet("Class_Metrics")
    ws.append([
        "Experiment", "Scope", "Class", "Support", "TP", "TN", "FP", "FN",
        "One-vs-Rest Accuracy", "Precision", "Recall", "F1",
    ])
    style_header(ws)
    ws.freeze_panes = "A2"
    for res in results:
        for scope in ("E1", "E2", "M", "Gesamt"):
            for c in res["scopes"][scope]["metrics"]["class_metrics"]:
                ws.append([
                    res["experiment"], scope, c["class"], c["support"],
                    c["TP"], c["TN"], c["FP"], c["FN"],
                    c["accuracy_ovr"], c["precision"], c["recall"], c["f1"],
                ])
    for col in range(9, 13):
        for r in range(2, ws.max_row + 1):
            ws.cell(r, col).number_format = PERCENT_FMT
    auto_width(ws)

    ws = wb.create_sheet("Confusion_Matrices")
    row = 1
    for res in results:
        for scope in ("E1", "E2", "M", "Gesamt"):
            ws.cell(row, 1, f"{res['experiment']} — {scope} — Strict Ground Truth")
            ws.cell(row, 1).font = Font(bold=True, size=12)
            row += 1
            ws.cell(row, 1, "True \\ Pred")
            for j, label in enumerate(CANONICAL_LABELS, start=2):
                ws.cell(row, j, label)
            for c in ws[row][:len(CANONICAL_LABELS)+1]:
                c.fill = SUBHEADER_FILL
                c.font = HEADER_FONT
            row += 1

            cm = res["scopes"][scope]["cm"]
            for i, label in enumerate(CANONICAL_LABELS):
                ws.cell(row, 1, label)
                ws.cell(row, 1).font = HEADER_FONT
                for j, value in enumerate(cm[i], start=2):
                    ws.cell(row, j, value)
                row += 1
            row += 2
    auto_width(ws, 12, 30)

    ws = wb.create_sheet("Nicht_Auswertbar")
    ws.append([
        "Experiment", "Excel row", "Regime", "Ground Truth",
        "Prediction", "Alternative GT", "Reason",
    ])
    style_header(ws)
    ws.freeze_panes = "A2"
    for res in results:
        for r in res["rows"]:
            if not r["row_valid"]:
                reason = r["issue"]
            elif r["pred"] is None:
                reason = "Predicted_Label blank -> nicht auswertbar"
            else:
                continue
            ws.append([
                res["experiment"], r["excel_row"], r["raw_regime"], r["raw_gt"],
                r["raw_pred"], r["raw_alt"], reason,
            ])
    auto_width(ws)

    ws = wb.create_sheet("Config")
    ws.append(["Setting", "Value"])
    style_header(ws)
    ws.append(["Input worksheet", INPUT_SHEET_NAME])
    ws.append(["Output file", OUTPUT_FILENAME])
    ws.append(["Canonical labels", " | ".join(CANONICAL_LABELS)])
    ws.append(["Gantry mapping", "Gantry = Multi-Achs-System (Gantry)"])
    ws.append(["Umsetzeinheit mapping", "Umsetzeinheit = Kombinierte Einheit"])
    ws.append(["Blank prediction", "nicht auswertbar; excluded from all classification metrics"])
    ws.append(["E1/E2/M/Gesamt confusion matrices", "Strict primary Ground Truth"])
    ws.append(["Strict Overall Accuracy", "Primary GT only; denominator = all auswertbar rows"])
    ws.append(["Accepted-Set Overall Accuracy", "Primary GT + M alternative GT; denominator = all auswertbar rows"])
    ws.append(["Calculation", "Custom pure-Python metrics are authoritative"])
    ws.append(["sklearn", "Independent verification for E1, E2, M and Gesamt"])
    auto_width(ws, 18, 90)

    wb.save(output_path)


def main():
    base_dir = Path(__file__).resolve().parent
    output_path = base_dir / OUTPUT_FILENAME

    input_files = sorted(
        p for p in base_dir.glob("*.xlsx")
        if p.name != OUTPUT_FILENAME and not p.name.startswith("~$")
    )
    if not input_files:
        raise SystemExit(f"No .xlsx experiment files found in: {base_dir}")

    print(f"Found {len(input_files)} experiment file(s).")
    print(f"Only worksheet {INPUT_SHEET_NAME!r} will be read.")

    results = []
    for i, path in enumerate(input_files, 1):
        print(f"[{i}/{len(input_files)}] {path.name}")

        rows, columns = read_experiment(path)
        overall = overall_accuracies(rows)

        scopes = {}
        checks = []
        for scope, regime in (("E1","E1"), ("E2","E2"), ("M","M"), ("Gesamt",None)):
            population, evaluated, cm, metrics = evaluate_scope(rows, regime)
            status = sklearn_cross_check(evaluated, cm, metrics, f"{path.name}/{scope}")
            checks.append(f"{scope}:{status}")
            scopes[scope] = {
                "population": population,
                "evaluated": evaluated,
                "cm": cm,
                "metrics": metrics,
            }

        results.append({
            "experiment": path.stem,
            "rows": rows,
            "columns": columns,
            "overall": overall,
            "scopes": scopes,
            "sklearn_status": "; ".join(checks),
        })

        print(
            f"    total={overall['n_total']} | "
            f"auswertbar={overall['n_auswertbar']} | "
            f"strict={overall['strict_accuracy']:.1%} | "
            f"accepted={overall['accepted_accuracy']:.1%}"
        )

    write_output(results, output_path)
    print(f"DONE: {output_path}")

    if not SKLEARN_AVAILABLE:
        print("NOTE: sklearn cross-check was skipped. Install: pip install scikit-learn numpy")


if __name__ == "__main__":
    main()
