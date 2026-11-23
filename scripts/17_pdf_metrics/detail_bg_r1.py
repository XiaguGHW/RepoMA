"""Einzelnachweis je Baugruppe unter R1 (zum Nachprüfen von Teilmengen-Werten, z. B. „mehrdeutig“).

Für jedes Modell und jede Baugruppe: Primärlabel, zulässige Labels (R1), die Vorhersagen aller Läufe,
Anzahl korrekt / Läufe. Daraus lässt sich jede Accuracy-Zelle von Hand nachrechnen:
Accuracy (Teilmenge) = Summe korrekt / Summe Läufe über die Baugruppen der Teilmenge.

Aufruf:
    python detail_bg_r1.py --dir "..\\03_Wiederholung_10runs" --gt R1.md --out "..\\05_Ergebnisse\\Detail_BG_R1.xlsx"
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evaluate_r1 as R  # noqa: E402

cm = R.cm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, action="append")
    ap.add_argument("--gt", required=True)
    ap.add_argument("--out", default="Detail_BG_R1.xlsx")
    a = ap.parse_args()
    gt, pe, _ = R.load_gt(a.gt)
    data, _ = R.collect(a.dir, "Sheet1", gt, pe, [])
    main_keys = set(cm.MAIN_115)
    rows = []
    for m in [x for x in R.MODEL_ORDER if x in data]:
        for ds, runs in (("115", data[m]["main"]), ("70", data[m]["supp"])):
            runs = [r for _, r in runs]
            if not runs:
                continue
            for k in sorted(set().union(*runs)):
                g, allowed = gt[k]
                preds = [r.get(k) for r in runs]
                ok = sum(R.correct(gt, k, p) for p in preds if p is not None)
                n = sum(p is not None for p in preds)
                rows.append({"Modell": m, "Datensatz": f"{ds} BG", "Baugruppe": k,
                             "Teilmenge": "mehrdeutig" if len(allowed) > 1 else "eindeutig",
                             "Primärlabel (R1)": g,
                             "weitere zulässige (R1)": ", ".join(sorted(allowed - {g})),
                             "korrekt": ok, "Läufe": n, "Anteil": round(ok / n, 3) if n else None,
                             **{f"Lauf {i + 1}": (p or "") for i, p in enumerate(preds)}})
    df = pd.DataFrame(rows)
    summ = (df.groupby(["Modell", "Datensatz", "Teilmenge"])[["korrekt", "Läufe"]].sum()
            .assign(Accuracy=lambda x: (x["korrekt"] / x["Läufe"] * 100).round(1)).reset_index())
    with pd.ExcelWriter(a.out) as xw:
        summ.to_excel(xw, sheet_name="Summen", index=False)
        df[df["Teilmenge"] == "mehrdeutig"].to_excel(xw, sheet_name="mehrdeutig", index=False)
        df.to_excel(xw, sheet_name="alle BG", index=False)
    pd.set_option("display.width", 160)
    print(summ.to_string(index=False))
    print(f"\nAusgabe: {a.out}")


if __name__ == "__main__":
    main()
