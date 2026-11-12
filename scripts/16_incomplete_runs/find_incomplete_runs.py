#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
find_incomplete_runs.py – Welche Baugruppen fehlen in welchen Ergebnisdateien?

Durchsucht einen oder mehrere Ordner rekursiv nach Ergebnisdateien (*.xlsx mit
SAP- und Predicted-Spalte) und meldet je Datei die Baugruppen, für die keine
gültige Vorhersage vorliegt:
  - fehlt   : Baugruppe kommt in der Datei nicht vor
  - leer    : Predicted leer / [EMPTY]
  - ungültig: Predicted ist keine der sieben Klassen
  - Fehler  : Processing_Status enthält ERROR (z. B. HTTP 413)

Referenzmenge je Datei: alle Baugruppen, die in den durchsuchten Dateien desselben
Datensatzes vorkommen (Dateiname mit "70BG" -> 70er-Satz, sonst Hauptsatz).
Mit --reference <xlsx> kann stattdessen eine vollständige Datei als Referenz dienen.

Nutzt FINAL_GT / canon aus evaluate_validation_regimes.py (Skript 12), wenn die Datei
im selben Ordner oder in ../12_validation_regimes liegt.

Aufruf (PowerShell):
  python find_incomplete_runs.py --root C:\\...\\Downloads\\test_claude
  python find_incomplete_runs.py --root <Prompt-Ordner> --root <Input-Ordner>
Ausgabe: Unvollstaendige_Laeufe.xlsx (Blatt Uebersicht, Blatt Fehlende_BG)
"""
import argparse
import importlib.util
import re
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
s12 = None
for cand in (HERE / "evaluate_validation_regimes.py",
             HERE.parent / "12_validation_regimes" / "evaluate_validation_regimes.py"):
    if cand.exists():
        spec = importlib.util.spec_from_file_location("s12", cand)
        s12 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(s12)
        break

SKIP = ("~$", "Validation_", "Evaluation_", "Kosten_", "Fehler_Reasoning", "Unvollstaendige_", "Konfusion")


def key(s):
    return str(s).strip().lstrip("0")


def canon(label):
    if s12 is not None:
        return s12.canon(label)
    return None if label is None or str(label).strip() in ("", "nan", "[EMPTY]") else str(label).strip()


def find_col(cols, *names):
    for n in names:
        for c in cols:
            if n in str(c).lower():
                return c
    return None


def label_of(path):
    name = path.stem
    m_prompt = re.search(r"P[1-4]", name)
    m_input = re.search(r"(pdf|image|text)", name, re.I)
    m_run = re.search(r"run[_ -]?(\d+)", name, re.I)
    parts = [path.parent.name, m_prompt.group(0) if m_prompt else "",
             m_input.group(1).lower() if m_input else "", f"Lauf {m_run.group(1)}" if m_run else ""]
    return " | ".join(p for p in parts if p)


def read(path):
    try:
        xl = pd.ExcelFile(path)
    except Exception:
        return None
    sheet = "Sheet1" if "Sheet1" in xl.sheet_names else xl.sheet_names[0]
    df = pd.read_excel(path, sheet_name=sheet, dtype=str)
    c_sap = find_col(df.columns, "sap")
    c_pred = find_col(df.columns, "predicted")
    if c_sap is None or c_pred is None:
        return None
    c_stat = find_col(df.columns, "processing_status")
    rows = {}
    for _, r in df.iterrows():
        if pd.isna(r[c_sap]) or not str(r[c_sap]).strip():
            continue
        raw = r[c_pred]
        stat = "" if c_stat is None or pd.isna(r[c_stat]) else str(r[c_stat])
        if "error" in stat.lower():
            status = "Fehler"
        elif pd.isna(raw) or str(raw).strip() in ("", "[EMPTY]", "nan"):
            status = "leer"
        elif canon(raw) is None:
            status = "ungültig"
        else:
            status = "ok"
        k = key(r[c_sap])
        if rows.get(k) != "ok":  # doppelte Zeilen: ok gewinnt
            rows[k] = status
        rows.setdefault("_sap_" + k, str(r[c_sap]).strip())
    return rows, (stat if c_stat else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", action="append", required=True)
    ap.add_argument("--reference", help="vollständige Ergebnisdatei als Referenzmenge")
    ap.add_argument("--out", default="Unvollstaendige_Laeufe.xlsx")
    a = ap.parse_args()

    files = [f for r in a.root for f in sorted(Path(r).rglob("*.xlsx")) if not f.name.startswith(SKIP)]
    data = {}
    for f in files:
        res = read(f)
        if res is not None:
            data[f] = res[0]
    if not data:
        sys.exit("Keine Ergebnisdateien mit SAP- und Predicted-Spalte gefunden.")

    def dataset(f):
        return "70" if "70bg" in f.name.lower() or "70bg" in str(f.parent).lower() else "Haupt"

    names = {}
    for rows in data.values():
        for k, v in rows.items():
            if k.startswith("_sap_"):
                names[k[5:]] = v
    if a.reference:
        ref_rows = read(Path(a.reference))[0]
        ref = {"Haupt": {k for k in ref_rows if not k.startswith("_sap_")}}
        ref["70"] = ref["Haupt"]
    else:
        ref = {}
        for f, rows in data.items():
            ref.setdefault(dataset(f), set()).update(k for k in rows if not k.startswith("_sap_"))

    over, miss = [], []
    for f, rows in data.items():
        exp = ref[dataset(f)]
        got = {k: v for k, v in rows.items() if not k.startswith("_sap_")}
        bad = []
        for k in sorted(exp):
            st = got.get(k, "fehlt")
            if st != "ok":
                bad.append((k, st))
        over.append({"Experiment": label_of(f), "Datei": str(f), "Datensatz": dataset(f), "Erwartet": len(exp),
                     "Gültig": len(exp) - len(bad), "Unvollständig": len(bad),
                     "Baugruppen": ", ".join(f"{names.get(k, k)} ({st})" for k, st in bad)})
        for k, st in bad:
            gt = None
            if s12 is not None:
                g = {key(x): v for x, v in s12.FINAL_GT.items()}.get(k)
                gt = g[0] if g else None
            miss.append({"Experiment": label_of(f), "Datei": f.name, "SAP": names.get(k, k), "Status": st, "GT": gt})

    over = pd.DataFrame(over).sort_values(["Unvollständig", "Experiment"], ascending=[False, True])
    with pd.ExcelWriter(a.out, engine="openpyxl") as xw:
        over.to_excel(xw, sheet_name="Uebersicht", index=False)
        pd.DataFrame(miss).to_excel(xw, sheet_name="Fehlende_BG", index=False)
    pd.set_option("display.width", 250, "display.max_colwidth", 120)
    print(f"{len(data)} Ergebnisdateien geprüft; Referenz: " + ", ".join(f"{d} = {len(s)} BG" for d, s in ref.items()))
    inc = over[over["Unvollständig"] > 0]
    if inc.empty:
        print("Alle Dateien vollständig.")
    else:
        print(f"\n{len(inc)} Dateien unvollständig:")
        print(inc[["Experiment", "Gültig", "Erwartet", "Baugruppen"]].to_string(index=False))
    print(f"\nAusgabe: {Path(a.out).resolve()}")


if __name__ == "__main__":
    main()
