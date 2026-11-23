"""Einzelläufe aus 02_Input_P3 (P3, pdf/Bild/text) unter R1 nach Teilmengen auswerten.

Je Modell × Eingabe × Datensatz (115 / 185 BG):
  Allowed Accuracy und Strict Accuracy (nur Primärlabel) für
  alle / eindeutig / mehrdeutig  sowie nach R1-Register E1 / E2 / M (wie in der Zwischenpräsentation).
Hinweis: Register M ohne weiteres zulässiges Label zählt in „eindeutig“, bleibt aber in der Spalte M.

Aufruf:
    python eval_input_regime_r1.py --input "..\\02_Input_P3" --gt R1.md --out "..\\05_Ergebnisse\\Input_P3_Teilmengen_R1.xlsx"
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
    """R1-Register (E1/E2/M) je Baugruppe aus R1.md."""
    head, reg = None, {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or re.fullmatch(r"[|\-: ]+", line.strip()):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if head is None:
            if any("SAP" in c for c in cells):
                head = cells
            continue
        if len(cells) != len(head):
            continue
        r = dict(zip(head, cells))
        k = cm.match_key(r.get("SAP-Nummer") or None, r.get("Teamcenter") or None)
        if k:
            reg[k] = r.get("Register", "").strip().upper()
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
    groups, unknown = X.load_runs(X.files_in(a.input), gt, pe, [], kind)
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
                print(f"! {m} {inp}: mehrere Dateien – letzte verwendet: {[f.name for f, _ in main + supp]}")
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
    pd.set_option("display.width", 220, "display.max_columns", 40)
    show = ["Modell", "Eingabe", "Datensatz"] + [c for c in df.columns if c.startswith(("Allowed", "Strict"))]
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
