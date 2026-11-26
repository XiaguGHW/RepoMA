"""Einzelläufe aus 02_Input_P3 (P3, pdf/Bild/text) unter R1 nach Teilmengen auswerten.

Je Modell × Eingabe × Datensatz (115 / 185 BG):
  Allowed Accuracy und Strict Accuracy (nur Primärlabel) für
  alle / eindeutig / mehrdeutig  sowie nach R1-Register E1 / E2 / M (wie in der Zwischenpräsentation).
Hinweis: Register M ohne weiteres zulässiges Label zählt in „eindeutig“, bleibt aber in der Spalte M.

Aufruf:
    python eval_input_regime_r1.py --input "..\\02_Input_P3" --gt R1.md --out "..\\05_Ergebnisse_R1\\Input_P3_Teilmengen_R1.xlsx"
    (nur pdf: --nur pdf)
"""
import argparse
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evaluate_r1 as R  # noqa: E402
import evaluate_r1_ergebnisse as X  # noqa: E402

cm = R.cm


def registers(path):
    """Register (E1/E2/M) je Baugruppe aus der GT-Datei (.md oder .xlsx); Spaltennamen unscharf."""
    reg = {}
    if Path(path).suffix.lower() in (".xlsx", ".xlsm"):
        df = pd.read_excel(path, dtype=str)
        cols = list(df.columns)
        c_sap, c_tc = R.E.find_col(cols, contains=["sap"]), R.E.find_col(cols, contains=["teamcenter"])
        c_reg = R.E.find_col(cols, contains=["regist"])
        for _, r in df.iterrows():
            k = cm.match_key(r[c_sap] if c_sap else None, r[c_tc] if c_tc else None)
            if k and c_reg:
                reg[k] = str(r[c_reg] or "").strip().upper()
        return reg
    head = None
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or re.fullmatch(r"[|\-: ]+", line.strip()):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if head is None:
            if any("SAP" in c for c in cells):
                head = cells
            continue
        if len(cells) < len(head) - 1:
            continue
        r = dict(zip(head, cells + [""] * (len(head) - len(cells))))
        c_sap = next((h for h in head if "sap" in h.lower()), None)
        c_tc = next((h for h in head if "teamcenter" in h.lower()), None)
        c_reg = next((h for h in head if "regist" in h.lower()), None)
        k = cm.match_key(r.get(c_sap) or None, r.get(c_tc) or None)
        if k and c_reg:
            reg[k] = r.get(c_reg, "").strip().upper()
    return reg


def main(argv=None, kind="input", default_out="Input_P3_Teilmengen_R1.xlsx", only_pref=False):
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", "--prompt", dest="input", required=True, action="append",
                    help="z. B. ..\\02_Input_P3 bzw. ..\\01_Prompt_P1-P4")
    ap.add_argument("--gt", required=True)
    ap.add_argument("--nur", choices=["pdf", "image", "text"], help="nur diese Eingabeform")
    ap.add_argument("--p", default="P3", choices=["P1", "P2", "P3", "P4"], help="Prompt (Standard P3)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    gt, pe, _ = R.load_gt(a.gt)
    reg = registers(a.gt)
    if len(reg) < len(gt):
        print(f"! Register nur für {len(reg)} von {len(gt)} Baugruppen gelesen – E1/E2/M-Spalten unvollständig")
    issues = []
    groups, unknown = X.load_runs(X.files_in(a.input), gt, pe, issues, kind)
    if issues:
        print(f"Hinweise beim Einlesen ({len(issues)}):")
        for t in sorted(set(map(str, issues)))[:20]:
            print("  ", t)
    for u in unknown:
        print("! nicht zugeordnet:", u)
    subsets = {
        "alle": lambda k: True,
        "eindeutig": lambda k: len(gt[k][1]) == 1,
        "mehrdeutig": lambda k: len(gt[k][1]) > 1,
        "E1": lambda k: reg.get(k) == "E1",
        "E2": lambda k: reg.get(k) == "E2",
        "M": lambda k: reg.get(k) == "M",
    }
    rows = []
    models = [m for m in X.MODELS if any(g[0] == m for g in groups)]
    for m in models:
        for inp in ("pdf", "image", "text"):
            if a.nur and inp != a.nur:
                continue
            if only_pref and inp != X.pref(m):
                continue
            main = groups.get((m, a.p, inp, "main"), [])
            supp = groups.get((m, a.p, inp, "supp"), [])
            if len(main) > 1 or len(supp) > 1:
                print(f"! {m} {inp}: mehrere Dateien {[f.name for f, _ in main + supp]} – verwendet: "
                      f"{main[-1][0].name if main else '-'}" + (f" + {supp[-1][0].name}" if supp else ""))
            for scope in ("115", "185"):
                if not main or (scope == "185" and not supp):
                    continue
                run = dict(main[-1][1])
                if scope == "185":
                    run.update(supp[-1][1])
                src = main[-1][0].name + ("" if scope == "115" else " + " + supp[-1][0].name)
                row = {"Modell": m, "Prompt": a.p, "Eingabe": inp, "Datensatz": f"{scope} BG", "Quelle": src}
                for name, f in subsets.items():
                    ks = [k for k in run if f(k)]
                    if not ks:
                        continue
                    row[f"n {name}"] = len(ks)
                    row[f"Allowed {name}"] = round(np.mean([R.correct(gt, k, run[k]) for k in ks]) * 100, 1)
                    row[f"Strict {name}"] = round(np.mean([run[k] == gt[k][0] for k in ks]) * 100, 1)
                rows.append(row)
    df = pd.DataFrame(rows)
    if df.empty:
        sys.exit(f"Keine passenden Ergebnisdateien gefunden (Prompt {a.p}"
                 + (f", Eingabe {a.nur}" if a.nur else "") + ") – Ordner und Optionen prüfen.")
    pd.set_option("display.width", 220, "display.max_columns", 40)
    for metric in ("Allowed", "Strict"):
        cols = ["Modell", "Eingabe", "Datensatz"] + [f"{metric} {s}" for s in subsets if f"{metric} {s}" in df]
        print(f"\n{metric} Accuracy (%), R1:")
        print(df[cols].to_string(index=False))
    out = Path(a.out) if a.out else Path(default_out.replace("P3", a.p))
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_excel(out, index=False)
    except PermissionError:
        import datetime
        alt = out.with_name(f"{out.stem}_{datetime.datetime.now():%H-%M-%S}{out.suffix}")
        print(f"\n! {out} ist geöffnet (Excel?) – schreibe stattdessen nach {alt.name}")
        df.to_excel(alt, index=False)
        out = alt
    print(f"\nAusgabe: {out}")


if __name__ == "__main__":
    main()
