"""Selbsttest: simulierte Ergebnisdateien (115 BG aus FINAL_GT) -> Werte gegen unabhängige Berechnung."""

import random
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evaluate_pdf_results as E  # noqa: E402

cm = E.cm
SPELL = {"Multi-Achs-System (Gantry)": "Gantry", "Keine der verfügbaren Klassen": "Keine der verfügbaren Klassen"}


def make_file(path, seed, wrong_status=False):
    rnd = random.Random(seed)
    rows = []
    for sap in cm.MAIN_115:
        gt, reg, alts = cm.FINAL_GT[sap]
        if sap == "0804EN7325":
            reg = "M"  # wie in den Ergebnisdateien: M ohne weiteres zulässiges Label
        u = rnd.random()
        if u < 0.75:
            p = gt
        elif u < 0.85 and alts:
            p = alts[0]
        else:
            p = rnd.choice(cm.CLASSES)
        ok = p == gt or p in alts
        rows.append({"prompt_engineering": "", "SAP-Nummer": sap, "Teamcenter": "x", "Ground Truth": gt,
                     "Register": reg, "Weitere zulässige Ground Truth": ", ".join(alts),
                     "Predicted_Label": SPELL.get(p, p), "Allowed_Set_Status": "CORRECT" if ok else "INCORRECT"})
    if wrong_status:
        rows[0]["Allowed_Set_Status"] = "INCORRECT" if rows[0]["Allowed_Set_Status"] == "CORRECT" else "CORRECT"
    pd.DataFrame(rows).to_excel(path, sheet_name="Sheet1", index=False)
    return rows


def reference(rows, which):
    recs = []
    for r in rows:
        alts = [a.strip() for a in r["Weitere zulässige Ground Truth"].split(",") if a.strip()]
        reg = "M" if alts else ("E2" if r["Register"] == "M" else r["Register"])
        pred = cm.canon(r["Predicted_Label"])
        recs.append((r["Ground Truth"], set([r["Ground Truth"]] + alts), reg, pred))
    if which == "E":
        recs = [x for x in recs if x[2] in ("E1", "E2")]
    elif which != "Total":
        recs = [x for x in recs if x[2] == which]
    n = len(recs)
    acc = sum(p in A for g, A, _, p in recs) / n
    P, R, F = [], [], []
    for c in cm.CLASSES:
        pc = [x for x in recs if x[3] == c]
        gc = [x for x in recs if x[0] == c]
        if pc:
            P.append(sum(c in x[1] for x in pc) / len(pc))
        if gc:
            R.append(sum(x[3] in x[1] for x in gc) / len(gc))
        if pc or gc:
            tp = sum(1 for x in recs if x[0] == c and x[3] == c)
            F.append(2 * tp / (len(pc) + len(gc)))
    return dict(n=n, acc=acc, prec=np.mean(P), rec=np.mean(R), f1=np.mean(F))


def main():
    tmp = Path(tempfile.mkdtemp())
    names = ["haiku-4-5_P3_pdf.xlsx", "gemini-2.5-pro_P3_pdf.xlsx", "claude-opus-4-8_pdf.xlsx", "gemini-2.5-flash_pdf.xlsx"]
    data = {}
    for k, n in enumerate(names):
        data[E.model_name(tmp / n)] = make_file(tmp / n, k, wrong_status=(k == 0))
    res = E.main([str(tmp / n) for n in names] + ["--out", str(tmp / "out")])
    assert [n for n, _ in res] == ["Claude Haiku 4.5", "Gemini 2.5 Pro", "Claude Opus 4.8", "Gemini 2.5 Flash"]
    for name, recs in res:
        assert [len(E.subset(recs, s)) for s in ["E1", "E2", "M"]] == [51, 34, 30], name
        for s in E.SUBSETS:
            got, ref = E.metrics(E.subset(recs, s)), reference(data[name], s)
            for k in ref:
                assert abs(got[k] - ref[k]) < 1e-12, (name, s, k, got[k], ref[k])
        m = E.matrix_for(recs)
        assert m["n"] == 115 and m["diag"].sum() + m["red"].sum() + m["green"].sum() == 115
    pr = pd.read_excel(tmp / "out" / "PDF_Metriken_Konfusion.xlsx", sheet_name="Pruefungen")
    assert (pr.Typ == "Allowed_Set_Status weicht ab").sum() == 1
    assert ((pr.Typ.str.startswith("Register M ohne")) & (pr.SAP == "0804EN7325")).sum() == 4
    assert (tmp / "out" / "konfusion_2x2.png").is_file()
    print("Selbsttest OK:", tmp / "out")


if __name__ == "__main__":
    main()
