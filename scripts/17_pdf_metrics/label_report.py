"""Übersicht der Klassennamen: welche Schreibweisen kommen in R1.md und in den Ergebnisdateien vor,
und auf welche Klasse werden sie abgebildet (canon, wie in evaluate_r1 / evaluate_r1_ergebnisse)?

Aufruf:
    python label_report.py --gt R1.md --dir "..\\01_Prompt_P1-P4" --dir "..\\02_Input_P3" --dir "..\\03_Wiederholung_10runs"
Ausgabe: Konsole + Label_Zuordnung.xlsx (Schreibweise, Quelle, Anzahl, Klasse, erkannt ja/nein).
"""
import argparse
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evaluate_pdf_results as E  # noqa: E402

cm = E.cm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gt", required=True)
    ap.add_argument("--dir", action="append", default=[])
    ap.add_argument("--out", default="Label_Zuordnung.xlsx")
    a = ap.parse_args()
    cnt = Counter()
    # R1.md
    head = None
    for line in Path(a.gt).read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or re.fullmatch(r"[|\-: ]+", line.strip()):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if head is None:
            if any("SAP" in c for c in cells):
                head = cells
            continue
        r = dict(zip(head, cells))
        g = next(v for k, v in r.items() if k.strip() == "Ground Truth")
        cnt[("R1 Ground Truth", g)] += 1
        alt = next((v for k, v in r.items() if "weitere" in k.lower()), "")
        for x in re.split(r"[,;]", alt):
            if x.strip():
                cnt[("R1 weitere zulässige", x.strip())] += 1
    # Ergebnisdateien
    for d in a.dir:
        for f in Path(d).rglob("*.xlsx"):
            if E.is_output_or_backup(f) or any(p.lower().startswith("_backup_vor_merge") for p in f.parts):
                continue
            try:
                df = pd.read_excel(f, sheet_name=0, dtype=str)
            except Exception:
                continue
            c = next((x for x in df.columns if "predicted" in str(x).lower()), None)
            if c is None:
                continue
            for v in df[c].fillna("").astype(str).str.strip():
                cnt[("Vorhersage", v if v else "(leer)")] += 1
    rows = []
    for (src, raw), n in sorted(cnt.items(), key=lambda x: (x[0][0], -x[1])):
        k = cm.canon(raw) if raw != "(leer)" else None
        ok = k is not None and not str(k).startswith("UNGÜLTIG")
        rows.append({"Quelle": src, "Schreibweise": raw, "Anzahl": n,
                     "Klasse": k if ok else ("—" if raw == "(leer)" else "NICHT ERKANNT"),
                     "exakt": "ja" if ok and raw == k else ("" if not ok else "nein (umgeschrieben)")})
    df = pd.DataFrame(rows)
    pd.set_option("display.width", 200, "display.max_colwidth", 60, "display.max_rows", 500)
    print(df.to_string(index=False))
    bad = df[df["Klasse"] == "NICHT ERKANNT"]
    print(f"\nNicht erkannte Schreibweisen: {len(bad)} (Zeilen: {int(bad['Anzahl'].sum()) if len(bad) else 0})")
    df.to_excel(a.out, index=False)
    print(f"Ausgabe: {a.out}")


if __name__ == "__main__":
    main()
