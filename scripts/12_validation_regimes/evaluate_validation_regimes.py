#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
evaluate_validation_regimes.py

Berechnet die Ergebnisse für Abschnitt 5.6 (offline, keine Modellaufrufe):

  Tabelle 5.6  Validierung: E1+E2 im Primärdatensatz (115 BG, Mittel über 10 Läufe)
               gegen E1+E2 im Ergänzungsdatensatz (70 BG, 1 Lauf), je Konfiguration
  Tabelle 5.7  Alle 185 BG zusammen, getrennt nach E1, E2 und M

Zusammenführung je Baugruppe: Für die 115 BG zählt der Anteil korrekter Läufe
(z. B. 9 von 10 = 0,9), für die 70 BG 1 oder 0. Mittelwerte und Bootstrap-CIs
werden über Baugruppen gebildet (jede Baugruppe gleich gewichtet).

Regime je Baugruppe (finale GT):
  M  = mehr als ein zulässiges Label (Ground Truth + Weitere zulässige Ground Truth)
  E1 / E2 = aus der Spalte "Register"; steht dort "M", gibt es aber keine
            weitere zulässige Klasse, wird E2 verwendet (Entscheidung zu 0804EN7325).

Aufruf (Windows, PowerShell):
  python evaluate_validation_regimes.py --main "C:\\...\\Downloads\\test_claude" --supp "C:\\...\\Downloads\\70BG_Ergebnisse"

Ausgabe: Validation_Regimes.xlsx im aktuellen Ordner (oder --out).
Benötigt: pandas, numpy, openpyxl
"""

import argparse
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

N_BOOT = 2000
SEED = 42
CI = (2.5, 97.5)

CLASSES = [
    "Greifer",
    "Lineareinheit",
    "Rotationseinheit",
    "Roboter",
    "Multi-Achs-System (Gantry)",
    "Kombinierte Einheit",
    "Keine der verfügbaren Klassen",
]
SYNONYMS = {
    "gantry": "Multi-Achs-System (Gantry)",
    "umsetzeinheit": "Kombinierte Einheit",
    "keine der verfgbaren klassen": "Keine der verfügbaren Klassen",
}
# Zuordnung Ordner-/Dateiname -> Konfiguration (Reihenfolge = Tabellenreihenfolge)
CONFIGS = [
    ("Claude Haiku 4.5 (PDF)", "haiku"),
    ("DeepSeek-V4-Flash (Text)", "deepseek"),
    ("Gemini 2.5 Pro (PDF)", "gemini-2.5-pro"),
    ("GPT-5.5 (Image)", "gpt-5.5"),
]
SKIP_PREFIX = ("~$", "PPT_", "Evaluation_", "Validation_", "nachlauf_")


# ---------------------------------------------------------------- Labels
def _norm(s):
    s = unicodedata.normalize("NFC", str(s)).replace("\u00a0", " ")
    return re.sub(r"\s+", " ", s).strip().lower()


LOOKUP = {_norm(c): c for c in CLASSES}
LOOKUP.update({_norm(k): v for k, v in SYNONYMS.items()})


def is_empty(x):
    if x is None:
        return True
    if isinstance(x, float) and np.isnan(x):
        return True
    s = str(x).strip()
    return s == "" or s.lower() in {"nan", "none", "—", "-"}


def canon(x):
    """Kanonischer Klassenname, None bei leer, 'UNGÜLTIG:<text>' sonst."""
    if is_empty(x):
        return None
    s = re.sub(r"^\[[A-Ga-g]\]\s*", "", str(x).strip())
    n = _norm(s)
    if n in LOOKUP:
        return LOOKUP[n]
    if n.startswith("keine der"):
        return "Keine der verfügbaren Klassen"
    return f"UNGÜLTIG:{s}"


# ---------------------------------------------------------------- Einlesen
def find_col(cols, exact=None, contains=None):
    if exact:
        for c in cols:
            if str(c).strip().lower() == exact.lower():
                return c
    if contains:
        for c in cols:
            if all(t.lower() in str(c).lower() for t in contains):
                return c
    return None


def read_result_file(path, issues, cfg, source, run):
    xl = pd.ExcelFile(path)
    sheet = "Sheet1" if "Sheet1" in xl.sheet_names else xl.sheet_names[0]
    df = pd.read_excel(path, sheet_name=sheet, dtype=str)
    cols = list(df.columns)
    c_sap = find_col(cols, contains=["sap"])
    c_tc = find_col(cols, contains=["teamcenter"])
    c_gt = find_col(cols, exact="Ground Truth")
    c_alt = find_col(cols, contains=["weitere"])
    c_pred = find_col(cols, contains=["predicted"])
    c_stat = find_col(cols, contains=["allowed", "status"])
    c_reg = find_col(cols, exact="Register")
    c_pe = find_col(cols, contains=["prompt", "engineering"])
    if not (c_sap and c_gt and c_pred):
        sys.exit(f"Spalten nicht gefunden in {path.name} (Blatt {sheet}): {cols}")
    if c_reg is None:
        issues.append(dict(Typ="Spalte Register fehlt", Konfiguration=cfg, Quelle=source, Datei=path.name))

    recs = []
    for i, row in df.iterrows():
        if is_empty(row[c_gt]):
            continue
        if c_pe is not None and not is_empty(row[c_pe]) and str(row[c_pe]).strip().lower() == "yes":
            continue
        sap = "" if is_empty(row[c_sap]) else str(row[c_sap]).strip()
        if not sap and c_tc is not None and not is_empty(row[c_tc]):
            sap = "TC:" + str(row[c_tc]).strip()
        if not sap:
            sap = f"ROW{i+2}"
        gt = canon(row[c_gt])
        alts = [canon(a) for a in ("" if c_alt is None or is_empty(row[c_alt]) else str(row[c_alt])).split(",") if a.strip()]
        alts = [a for a in alts if a]
        pred = canon(row[c_pred])
        stat = "" if c_stat is None or is_empty(row[c_stat]) else str(row[c_stat]).strip().upper()
        reg = "" if c_reg is None or is_empty(row[c_reg]) else str(row[c_reg]).strip().upper()
        for lab in [gt] + alts:
            if lab and lab.startswith("UNGÜLTIG"):
                issues.append(dict(Typ="Ungültiges GT-Label", Konfiguration=cfg, Quelle=source, Datei=path.name, SAP=sap, Detail=lab))
        if pred and pred.startswith("UNGÜLTIG"):
            issues.append(dict(Typ="Ungültige Vorhersage (als falsch gewertet)", Konfiguration=cfg, Quelle=source,
                               Datei=path.name, SAP=sap, Detail=pred))
        excluded = pred is None or stat == "EXCLUDED"
        recs.append(dict(cfg=cfg, source=source, run=run, sap=sap, gt=gt,
                         allowed=frozenset([gt] + alts), register=reg, pred=pred, excluded=excluded))
    return recs


def list_xlsx(folder):
    return sorted(f for f in folder.glob("*.xlsx") if not f.name.startswith(SKIP_PREFIX))


def run_key(f):
    m = re.search(r"Run_(\d+)", f.name, re.I)
    t = re.search(r"(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})", f.name)
    return (int(m.group(1)) if m else 10**6, t.group(1) if t else "", f.name)


def load(main_dir, supp_dir):
    recs, issues = [], []
    for cfg, key in CONFIGS:
        # Primärdatensatz: Unterordner mit 10 Läufen
        folders = [d for d in main_dir.iterdir() if d.is_dir() and key in d.name.lower()]
        folders = [d for d in folders if "flash" not in d.name.lower() or key == "deepseek"]
        if len(folders) != 1:
            sys.exit(f"Primärdatensatz: für '{cfg}' {len(folders)} Ordner gefunden: {[d.name for d in folders]}")
        files = sorted(list_xlsx(folders[0]), key=run_key)
        if len(files) != 10:
            issues.append(dict(Typ="Anzahl Läufe", Konfiguration=cfg, Quelle="115", Detail=f"{len(files)} Dateien"))
        for r, f in enumerate(files, 1):
            recs += read_result_file(f, issues, cfg, "115", r)
        # Ergänzungsdatensatz: eine Datei je Konfiguration
        sfiles = [f for f in list_xlsx(supp_dir) if key in f.name.lower()]
        sfiles = [f for f in sfiles if "flash" not in f.name.lower() or key == "deepseek"]
        if len(sfiles) != 1:
            sys.exit(f"Ergänzungsdatensatz: für '{cfg}' {len(sfiles)} Dateien gefunden: {[f.name for f in sfiles]}")
        recs += read_result_file(sfiles[0], issues, cfg, "70", 1)
    return pd.DataFrame(recs), issues


# ---------------------------------------------------------------- Auswertung
def regime(allowed, register):
    if len(allowed) > 1:
        return "M"
    if register in ("E1", "E2"):
        return register
    return "E2" if register == "M" else "?"


def per_assembly(df):
    """Je Konfiguration und Baugruppe: Anteil korrekter (allowed/strict) gültiger Läufe."""
    v = df[~df.excluded].copy()
    v["hit"] = [p in a for p, a in zip(v.pred, v.allowed)]
    v["strict"] = v["pred"] == v["gt"]
    v["alt"] = v.hit & ~v.strict
    g = v.groupby(["cfg", "source", "sap"])
    out = g.agg(hit=("hit", "mean"), strict=("strict", "mean"), alt=("alt", "mean"), n_runs=("run", "nunique")).reset_index()
    first = df.drop_duplicates(["cfg", "source", "sap"]).set_index(["cfg", "source", "sap"])
    out["gt"] = [first.loc[(c, s, a), "gt"] for c, s, a in zip(out.cfg, out.source, out.sap)]
    out["regime"] = [regime(first.loc[(c, s, a), "allowed"], first.loc[(c, s, a), "register"])
                     for c, s, a in zip(out.cfg, out.source, out.sap)]
    return out


def boot_mean(x, rng):
    x = np.asarray(x, float)
    if len(x) == 0:
        return np.nan, np.nan, np.nan
    idx = rng.integers(0, len(x), size=(N_BOOT, len(x)))
    b = x[idx].mean(axis=1)
    lo, hi = np.percentile(b, CI)
    return x.mean(), lo, hi


def boot_diff(x, y, rng):
    x, y = np.asarray(x, float), np.asarray(y, float)
    bx = x[rng.integers(0, len(x), size=(N_BOOT, len(x)))].mean(axis=1)
    by = y[rng.integers(0, len(y), size=(N_BOOT, len(y)))].mean(axis=1)
    d = bx - by
    lo, hi = np.percentile(d, CI)
    return x.mean() - y.mean(), lo, hi


def pct(v, d=1):
    return "–" if v is None or np.isnan(v) else f"{v*100:.{d}f}".replace(".", ",")


def fmt(m, lo, hi):
    return "–" if np.isnan(m) else f"{pct(m)} [{pct(lo)}–{pct(hi)}]"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--main", required=True, help="Ordner mit den 10-Lauf-Ordnern (115 BG)")
    ap.add_argument("--supp", required=True, help="Ordner mit den Ergebnisdateien der 70 BG")
    ap.add_argument("--out", default="Validation_Regimes.xlsx")
    a = ap.parse_args()

    df, issues = load(Path(a.main), Path(a.supp))
    pa = per_assembly(df)
    rng = np.random.default_rng(SEED)
    cfgs = [c for c, _ in CONFIGS]

    # Prüfungen: Regime-Verteilung und GT-Konsistenz
    chk = []
    for src in ["115", "70"]:
        sub = pa[(pa.cfg == cfgs[0]) & (pa.source == src)]
        vc = sub.regime.value_counts()
        chk.append({"Datensatz": src, "Baugruppen": len(sub),
                    **{r: int(vc.get(r, 0)) for r in ["E1", "E2", "M", "?"]}})
    expected = {"115": (115, 51, 34, 30), "70": (70, 59, 10, 1)}
    for row in chk:
        e = expected[row["Datensatz"]]
        row["Erwartet (n/E1/E2/M)"] = "/".join(map(str, e))
        row["OK"] = "ja" if (row["Baugruppen"], row["E1"], row["E2"], row["M"]) == e else "NEIN"
    gt_sets = df.groupby(["source", "sap"]).agg(n=("allowed", lambda s: len(set(s))), g=("gt", lambda s: len(set(s))))
    for (src, sap), r in gt_sets.iterrows():
        if r.n > 1 or r.g > 1:
            issues.append(dict(Typ="GT/ZGT unterscheidet sich zwischen Dateien", Quelle=src, SAP=sap))
    excl = df[df.excluded].groupby(["cfg", "source"]).size()
    for (c, s), n in excl.items():
        issues.append(dict(Typ="EXCLUDED/leer (nicht gewertet)", Konfiguration=c, Quelle=s, Detail=str(n)))

    # Tabelle 5.6
    t56 = []
    for c in cfgs:
        m = pa[(pa.cfg == c) & (pa.source == "115") & pa.regime.isin(["E1", "E2"])].hit
        s = pa[(pa.cfg == c) & (pa.source == "70") & pa.regime.isin(["E1", "E2"])].hit
        t56.append({"Konfiguration": c,
                    "115 BG, E1+E2 (n)": len(m), "115 BG, E1+E2 (10 Läufe)": fmt(*boot_mean(m, rng)),
                    "70 BG, E1+E2 (n)": len(s), "70 BG, E1+E2 (1 Lauf)": fmt(*boot_mean(s, rng)),
                    "Δ (70 − 115)": fmt(*boot_diff(s, m, rng))})
    t56 = pd.DataFrame(t56)

    # Einzelfall M im Ergänzungsdatensatz
    mrows = []
    for c in cfgs:
        sub = df[(df.cfg == c) & (df.source == "70")]
        for r in sub.itertuples():
            if len(r.allowed) > 1:
                mrows.append({"Konfiguration": c, "SAP": r.sap, "Ground Truth": r.gt,
                              "Zulässig": ", ".join(sorted(r.allowed)), "Vorhersage": r.pred,
                              "Korrekt (allowed)": "ja" if r.pred in r.allowed else "nein"})
    mcase = pd.DataFrame(mrows)

    # Klassenweise E1+E2, 115 vs 70
    kl = []
    for c in cfgs:
        for k in CLASSES:
            row = {"Konfiguration": c, "Klasse (Primärlabel)": k}
            for src in ["115", "70"]:
                x = pa[(pa.cfg == c) & (pa.source == src) & pa.regime.isin(["E1", "E2"]) & (pa["gt"] == k)].hit
                row[f"{src} BG n"] = len(x)
                row[f"{src} BG Accuracy"] = pct(x.mean()) if len(x) else "–"
            kl.append(row)
    kl = pd.DataFrame(kl)

    # Tabelle 5.7: 185 BG nach Regime
    t57 = []
    for c in cfgs:
        sub = pa[pa.cfg == c]
        row = {"Konfiguration": c}
        for r in ["E1", "E2", "M"]:
            x = sub[sub.regime == r]
            row[f"{r} (n)"] = len(x)
            row[f"{r} Allowed Accuracy"] = fmt(*boot_mean(x.hit, rng))
        x = sub[sub.regime == "M"]
        row["M: Anteil Primärlabel"] = fmt(*boot_mean(x.strict, rng))
        row["M: Anteil weiteres zulässiges Label"] = fmt(*boot_mean(x.alt, rng))
        row["Gesamt 185 Allowed Accuracy"] = fmt(*boot_mean(sub.hit, rng))
        row["Gesamt 185 Strict Accuracy"] = fmt(*boot_mean(sub.strict, rng))
        t57.append(row)
    t57 = pd.DataFrame(t57)

    notes = pd.DataFrame({"Hinweis": [
        "Werte in %, in Klammern 95%-Bootstrap-CI (B=2000, Seed 42, Ziehen von Baugruppen mit Zurücklegen).",
        "115 BG: je Baugruppe Anteil korrekter Läufe über 10 Läufe; 70 BG: 1 Lauf (0 oder 1).",
        "Tabelle 5.7: alle 185 BG, je Baugruppe gleich gewichtet; CI je Regime getrennt gezogen.",
        "Regime: M = mehr als ein zulässiges Label; sonst Spalte Register (M ohne weitere Klasse -> E2).",
        "Δ (70 − 115): Differenz der Mittelwerte, CI aus unabhängigen Bootstrap-Ziehungen beider Datensätze.",
        "EXCLUDED/leere Vorhersagen werden nicht gewertet (siehe Prüfungen).",
    ]})

    with pd.ExcelWriter(a.out, engine="openpyxl") as xw:
        t56.to_excel(xw, "Tabelle_5_6", index=False)
        t57.to_excel(xw, "Tabelle_5_7", index=False)
        (mcase if len(mcase) else pd.DataFrame({"Hinweis": ["keine M-Baugruppe im Ergänzungsdatensatz"]})).to_excel(xw, "M_im_70er_Satz", index=False)
        kl.to_excel(xw, "Klassen_E1E2_115_vs_70", index=False)
        pd.DataFrame(chk).to_excel(xw, "Pruefung_Regime", index=False)
        (pd.DataFrame(issues) if issues else pd.DataFrame({"Hinweis": ["keine Auffälligkeiten"]})).to_excel(xw, "Pruefungen", index=False)
        notes.to_excel(xw, "Hinweise", index=False)
        for ws in xw.book.worksheets:
            for col in ws.columns:
                w = max(len(str(c.value)) if c.value is not None else 0 for c in col)
                ws.column_dimensions[col[0].column_letter].width = min(max(10, w + 2), 70)

    pd.set_option("display.width", 200, "display.max_columns", 20)
    print("\nPrüfung Regime-Verteilung:\n", pd.DataFrame(chk).to_string(index=False))
    print("\nTabelle 5.6:\n", t56.to_string(index=False))
    print("\nTabelle 5.7:\n", t57.to_string(index=False))
    print(f"\n{len(issues)} Hinweise in 'Pruefungen'. Ausgabe: {Path(a.out).resolve()}")


if __name__ == "__main__":
    main()
