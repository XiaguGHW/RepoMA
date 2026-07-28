from __future__ import annotations

import argparse
import math
import re
from collections import Counter
from pathlib import Path

import pandas as pd


GROUNDTRUTH_PATTERN = "ClassificationGroundTruth-Final*.xlsx"
PARTICIPANT_PATTERN = "KlassifikationWorkshop_Template*TN_*.xlsx"


def norm_text(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    text = re.sub(r"\s+", " ", text)
    if text.endswith(".0"):
        text = text[:-2]
    return text


def norm_key(value: object) -> str:
    return norm_text(value).upper()


def norm_label(value: object) -> str:
    return norm_text(value)


def find_column(columns: list[str], candidates: list[str], required: bool = True) -> str | None:
    normalized = {re.sub(r"[^a-z0-9]+", "", c.lower()): c for c in columns}
    for candidate in candidates:
        key = re.sub(r"[^a-z0-9]+", "", candidate.lower())
        if key in normalized:
            return normalized[key]

    for column in columns:
        col_key = re.sub(r"[^a-z0-9]+", "", column.lower())
        for candidate in candidates:
            cand_key = re.sub(r"[^a-z0-9]+", "", candidate.lower())
            if cand_key and cand_key in col_key:
                return column

    if required:
        raise ValueError(f"Keine passende Spalte gefunden. Gesucht: {candidates}. Vorhanden: {columns}")
    return None


def read_relevant_sheet(path: Path, required_columns: list[str]) -> tuple[str, pd.DataFrame]:
    excel = pd.ExcelFile(path)
    best_error = None
    for sheet_name in excel.sheet_names:
        df = pd.read_excel(path, sheet_name=sheet_name, dtype=object)
        df.columns = [norm_text(c) for c in df.columns]
        columns_joined = " | ".join(df.columns).lower()
        if all(required.lower() in columns_joined for required in required_columns):
            return sheet_name, df
        try:
            for required in required_columns:
                find_column(df.columns.tolist(), [required])
            return sheet_name, df
        except ValueError as exc:
            best_error = exc
    raise ValueError(f"In {path.name} wurde kein passendes Sheet gefunden. Letzter Fehler: {best_error}")


def load_groundtruth(path: Path) -> tuple[str, pd.DataFrame, dict[str, str]]:
    sheet_name, df = read_relevant_sheet(path, ["SAP", "Label"])

    columns = df.columns.tolist()
    col_sap = find_column(columns, ["SAP-Nummer", "SAP Nummer", "SAP"])
    col_tc = find_column(columns, ["Teamcenter", "Teamcenter ID", "TC"], required=False)
    col_label = find_column(columns, ["Label", "Ground Truth", "GroundTruth", "Funktionsklasse"])
    col_name_e = find_column(columns, ["Benennung (E)", "Benennung E", "Benennung"], required=False)
    col_name_d = find_column(columns, ["Benennung (D)", "Benennung D"], required=False)
    col_level = find_column(columns, ["Baugruppenebene", "Ebene"], required=False)

    out = pd.DataFrame()
    out["SAP-Nummer"] = df[col_sap].map(norm_text)
    out["Teamcenter"] = df[col_tc].map(norm_text) if col_tc else ""
    if col_name_e:
        out["Benennung (E)"] = df[col_name_e].map(norm_text)
    if col_name_d:
        out["Benennung (D)"] = df[col_name_d].map(norm_text)
    if col_level:
        out["Baugruppenebene"] = df[col_level].map(norm_text)
    out["Ground Truth"] = df[col_label].map(norm_label)

    out = out[out["Ground Truth"] != ""].copy()
    column_map = {"sap": col_sap, "teamcenter": col_tc or "", "label": col_label}
    return sheet_name, out.reset_index(drop=True), column_map


def participant_name(path: Path) -> str:
    match = re.search(r"TN_([A-Z])", path.stem, flags=re.IGNORECASE)
    if match:
        return f"TN_{match.group(1).upper()}"
    return path.stem


def load_participant(path: Path) -> tuple[str, str, pd.DataFrame, dict[str, str]]:
    sheet_name, df = read_relevant_sheet(path, ["Baugruppen", "Klasse"])
    columns = df.columns.tolist()

    col_sap = find_column(columns, ["SAP-Nummer", "SAP Nummer", "SAP"], required=False)
    col_tc = find_column(columns, ["Teamcenter", "Teamcenter ID", "TC"], required=False)
    col_label = find_column(columns, ["Baugruppen-Klasse", "Baugruppen Klasse", "Klasse", "Funktionsklasse"])

    if not col_sap and not col_tc:
        raise ValueError(f"{path.name}: Weder SAP-Nummer noch Teamcenter gefunden.")

    out = pd.DataFrame()
    out["SAP-Nummer"] = df[col_sap].map(norm_text) if col_sap else ""
    out["Teamcenter"] = df[col_tc].map(norm_text) if col_tc else ""
    out["Annotation"] = df[col_label].map(norm_label)
    out = out[out["Annotation"] != ""].copy()

    column_map = {"sap": col_sap or "", "teamcenter": col_tc or "", "label": col_label}
    return participant_name(path), sheet_name, out.reset_index(drop=True), column_map


def build_lookup(df: pd.DataFrame) -> tuple[dict[str, str], dict[str, str]]:
    sap_lookup: dict[str, str] = {}
    tc_lookup: dict[str, str] = {}

    for _, row in df.iterrows():
        label = norm_label(row["Annotation"])
        sap = norm_key(row.get("SAP-Nummer", ""))
        tc = norm_key(row.get("Teamcenter", ""))
        if sap:
            sap_lookup[sap] = label
        if tc:
            tc_lookup[tc] = label
    return sap_lookup, tc_lookup


def merge_annotations(groundtruth: pd.DataFrame, participants: list[tuple[str, pd.DataFrame]]) -> pd.DataFrame:
    overview = groundtruth.copy()
    overview["_SAP_KEY"] = overview["SAP-Nummer"].map(norm_key)
    overview["_TC_KEY"] = overview["Teamcenter"].map(norm_key)

    for name, participant_df in participants:
        sap_lookup, tc_lookup = build_lookup(participant_df)
        values = []
        for _, row in overview.iterrows():
            label = sap_lookup.get(row["_SAP_KEY"], "")
            if not label:
                label = tc_lookup.get(row["_TC_KEY"], "")
            values.append(label)
        overview[name] = values

    return overview.drop(columns=["_SAP_KEY", "_TC_KEY"])


def krippendorff_alpha_nominal(matrix: pd.DataFrame) -> float:
    items = matrix.values.tolist()
    coincidence: Counter[tuple[str, str]] = Counter()
    labels: list[str] = []

    for row in items:
        values = [norm_label(v) for v in row if norm_label(v)]
        labels.extend(values)
        n = len(values)
        if n < 2:
            continue
        for i in range(n):
            for j in range(n):
                if i != j:
                    coincidence[(values[i], values[j])] += 1

    total = sum(coincidence.values())
    if total == 0:
        return math.nan

    do = sum(count for (a, b), count in coincidence.items() if a != b) / total
    label_counts = Counter(labels)
    n_total = sum(label_counts.values())
    if n_total <= 1:
        return math.nan

    de = 1 - sum(count * (count - 1) for count in label_counts.values()) / (n_total * (n_total - 1))
    if de == 0:
        return 1.0 if do == 0 else math.nan
    return 1 - do / de


def confusion_matrix(overview: pd.DataFrame, participant_cols: list[str]) -> pd.DataFrame:
    labels = sorted(
        {
            norm_label(v)
            for v in pd.concat([overview["Ground Truth"], overview[participant_cols].stack()], ignore_index=True)
            if norm_label(v)
        }
    )
    matrix = pd.DataFrame(0, index=labels, columns=labels)
    matrix.index.name = "Ground Truth \\ Annotation"

    for _, row in overview.iterrows():
        gt = norm_label(row["Ground Truth"])
        if not gt:
            continue
        for col in participant_cols:
            pred = norm_label(row[col])
            if pred:
                matrix.loc[gt, pred] += 1
    return matrix


def write_output(
    output_path: Path,
    overview: pd.DataFrame,
    alpha: float,
    matrix: pd.DataFrame,
    source_info: pd.DataFrame,
) -> None:
    participant_cols = [c for c in overview.columns if c.startswith("TN_")]
    missing_rows = []
    for col in participant_cols:
        missing_rows.append({"Teilnehmer": col, "Fehlende Zuordnungen": int((overview[col] == "").sum())})

    alpha_df = pd.DataFrame(
        [
            {
                "Metrik": "Krippendorff's Alpha",
                "Wert": alpha,
                "Hinweis": "Nominal alpha; berechnet nur aus den Teilnehmer-Labels, ohne Ground Truth.",
            }
        ]
    )

    check_df = pd.DataFrame(missing_rows)
    check_df.loc[len(check_df)] = {
        "Teilnehmer": "Confusion Matrix Summe",
        "Fehlende Zuordnungen": int(matrix.to_numpy().sum()),
    }

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        overview.to_excel(writer, index=False, sheet_name="Uebersicht")
        alpha_df.to_excel(writer, index=False, sheet_name="Krippendorff_Alpha")
        matrix.to_excel(writer, sheet_name="Confusion_Matrix")
        check_df.to_excel(writer, index=False, sheet_name="Checks")
        source_info.to_excel(writer, index=False, sheet_name="Quellen")


def main() -> None:
    parser = argparse.ArgumentParser(description="Workshop-Auswertung: Teilnehmerlabels, Alpha, Confusion Matrix.")
    parser.add_argument("--input-dir", default=".", help="Ordner mit Ground Truth und Teilnehmer-Excel-Dateien.")
    parser.add_argument("--output", default="Workshop_Annotation_Auswertung.xlsx", help="Ausgabe-Excel-Datei.")
    args = parser.parse_args()

    input_dir = Path(args.input_dir).resolve()
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = input_dir / output_path

    groundtruth_files = sorted(input_dir.glob(GROUNDTRUTH_PATTERN))
    participant_files = sorted(input_dir.glob(PARTICIPANT_PATTERN))

    if len(groundtruth_files) != 1:
        raise FileNotFoundError(f"Erwartet genau eine Ground-Truth-Datei ({GROUNDTRUTH_PATTERN}), gefunden: {groundtruth_files}")
    if len(participant_files) != 5:
        raise FileNotFoundError(f"Erwartet genau 5 Teilnehmer-Dateien ({PARTICIPANT_PATTERN}), gefunden: {participant_files}")

    gt_sheet, groundtruth, gt_cols = load_groundtruth(groundtruth_files[0])

    participants: list[tuple[str, pd.DataFrame]] = []
    source_rows = [
        {
            "Datei": groundtruth_files[0].name,
            "Typ": "Ground Truth",
            "Sheet": gt_sheet,
            "SAP-Spalte": gt_cols["sap"],
            "Teamcenter-Spalte": gt_cols["teamcenter"],
            "Label-Spalte": gt_cols["label"],
        }
    ]

    for file in participant_files:
        name, sheet, df, cols = load_participant(file)
        participants.append((name, df))
        source_rows.append(
            {
                "Datei": file.name,
                "Typ": name,
                "Sheet": sheet,
                "SAP-Spalte": cols["sap"],
                "Teamcenter-Spalte": cols["teamcenter"],
                "Label-Spalte": cols["label"],
            }
        )

    overview = merge_annotations(groundtruth, participants)
    participant_cols = [name for name, _ in participants]
    alpha = krippendorff_alpha_nominal(overview[participant_cols])
    matrix = confusion_matrix(overview, participant_cols)

    write_output(output_path, overview, alpha, matrix, pd.DataFrame(source_rows))

    print(f"Fertig: {output_path}")
    print(f"Zeilen in Uebersicht: {len(overview)}")
    print(f"Teilnehmer-Spalten: {', '.join(participant_cols)}")
    print(f"Krippendorff's Alpha: {alpha:.4f}")
    print(f"Confusion-Matrix Summe: {int(matrix.to_numpy().sum())}")


if __name__ == "__main__":
    main()
