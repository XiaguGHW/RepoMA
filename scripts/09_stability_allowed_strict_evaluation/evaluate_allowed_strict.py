#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
evaluate_allowed_strict.py

Berechnet Allowed- und Strict-Metriken mit 95%-Konfidenzintervallen
(Bootstrap über Baugruppen) für alle Modellordner (je 10 Läufe).

Ablage: dieselbe Ebene wie die Modellordner, z. B.
    <Ordner>/
        evaluate_allowed_strict.py
        claude_haiku_pdf_P3_10_runs/
        gemini-2.5-pro_pdf_P3_10_runs/
        ...
Aufruf:  python evaluate_allowed_strict.py
Ausgabe: Evaluation_Allowed_Strict.xlsx im selben Ordner

Benötigt: pandas, numpy, openpyxl
"""

import re
import sys
import unicodedata
import warnings
import itertools
from pathlib import Path

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------------
# Einstellungen
# ----------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = BASE_DIR / "Evaluation_Allowed_Strict.xlsx"
SHEET_NAME = "Sheet1"
N_BOOT = 2000
SEED = 42
CI = (2.5, 97.5)
SKIP_PREFIX = ("~$", "PPT_", "Evaluation_Summary", "Evaluation_Allowed_Strict")

CLASSES = [
    "Lineareinheit",
    "Greifer",
    "Roboter",
    "Rotationseinheit",
    "Multi-Achs-System (Gantry)",
    "Kombinierte Einheit",
    "Keine der verfügbaren Klassen",
]
CODES = list("ABCDEFG")
K = len(CLASSES)

# Synonyme laut Codebook (bei Bedarf ergänzen, Schlüssel in Kleinbuchstaben)
SYNONYMS = {
    "gantry": "Multi-Achs-System (Gantry)",
    "umsetzeinheit": "Kombinierte Einheit",
    "keine der verfgbaren klassen": "Keine der verfügbaren Klassen",
}


# ----------------------------------------------------------------------------
# Label-Normalisierung
# ----------------------------------------------------------------------------
def _norm(s):
    s = unicodedata.normalize("NFC", str(s)).replace("\u00a0", " ")
    return re.sub(r"\s+", " ", s).strip().lower()


LOOKUP = {_norm(c): i for i, c in enumerate(CLASSES)}
LOOKUP.update({_norm(k): CLASSES.index(v) for k, v in SYNONYMS.items()})


def is_empty(x):
    if x is None:
        return True
    if isinstance(x, float) and np.isnan(x):
        return True
    s = str(x).strip()
    return s == "" or s.lower() in {"nan", "none"}


def label_index(x):
    """Klassenindex 0..K-1, None bei leer, K bei nicht zuordenbar."""
    if is_empty(x):
        return None
    s = re.sub(r"^\[[A-Ga-g]\]\s*", "", str(x).strip())
    n = _norm(s)
    if n in LOOKUP:
        return LOOKUP[n]
    if n.startswith("keine der"):
        return CLASSES.index("Keine der verfügbaren Klassen")
    return K  # ungültig


# ----------------------------------------------------------------------------
# Dateien einlesen
# ----------------------------------------------------------------------------
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


def list_run_files(folder):
    files = [f for f in folder.glob("*.xlsx") if not f.name.startswith(SKIP_PREFIX)]

    def key(f):
        m = re.search(r"Run_(\d+)", f.name, re.I)
        t = re.search(r"(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})", f.name)
        return (int(m.group(1)) if m else 10**6, t.group(1) if t else "", f.name)

    return sorted(files, key=key)


def model_label(folder):
    return re.sub(r"_?\d+_runs$", "", folder.name)


def load_all():
    folders = sorted(
        d for d in BASE_DIR.iterdir()
        if d.is_dir() and any(not f.name.startswith(SKIP_PREFIX) for f in d.glob("*.xlsx"))
    )
    if not folders:
        sys.exit("Keine Modellordner mit .xlsx-Dateien gefunden.")

    recs, issues = [], []
    for folder in folders:
        model = model_label(folder)
        files = list_run_files(folder)
        if len(files) != 10:
            issues.append(dict(Typ="Anzahl Läufe", Modell=model, Detail=f"{len(files)} Dateien gefunden"))
        for run, f in enumerate(files, 1):
            df = pd.read_excel(f, sheet_name=SHEET_NAME, dtype=str)
            cols = list(df.columns)
            c_sap = find_col(cols, contains=["sap"])
            c_gt = find_col(cols, exact="Ground Truth")
            c_alt = find_col(cols, contains=["weitere"])
            c_pred = find_col(cols, contains=["predicted"])
            c_stat = find_col(cols, contains=["allowed", "status"])
            c_reg = find_col(cols, exact="Register")
            if not (c_sap and c_gt and c_pred):
                sys.exit(f"Spalten nicht gefunden in {f.name}: {cols}")

            seen = {}
            for i, row in df.iterrows():
                if is_empty(row[c_gt]):
                    continue
                sap = "" if is_empty(row[c_sap]) else str(row[c_sap]).strip()
                if not sap:
                    sap = f"ROW{i+2}"
                seen[sap] = seen.get(sap, 0) + 1
                key = sap if seen[sap] == 1 else f"{sap}#{seen[sap]}"
                if seen[sap] == 2:
                    issues.append(dict(Typ="Doppelte SAP-Nummer", Modell=model, Lauf=run,
                                       Datei=f.name, SAP=sap))

                gt = label_index(row[c_gt])
                alt_raw = "" if (c_alt is None or is_empty(row[c_alt])) else str(row[c_alt])
                alts = [label_index(a) for a in alt_raw.split(",") if a.strip()]
                pred = label_index(row[c_pred])
                stat = "" if (c_stat is None or is_empty(row[c_stat])) else str(row[c_stat]).strip().upper()
                reg = "" if (c_reg is None or is_empty(row[c_reg])) else str(row[c_reg]).strip()

                if gt == K or K in alts:
                    issues.append(dict(Typ="Ungültiges GT/ZGT-Label", Modell=model, Lauf=run, Datei=f.name,
                                       SAP=sap, Detail=f"GT={row[c_gt]} | ZGT={alt_raw}"))
                if pred == K:
                    issues.append(dict(Typ="Ungültige Vorhersage (als falsch gewertet)", Modell=model, Lauf=run,
                                       Datei=f.name, SAP=sap, Detail=str(row[c_pred])))

                allowed = {gt} | {a for a in alts if a is not None and a != K}
                excluded = pred is None or stat == "EXCLUDED"
                recs.append(dict(model=model, run=run, file=f.name, key=key, gt=gt,
                                 allowed=frozenset(allowed), n_alts=len(allowed) - 1,
                                 pred=pred, excluded=excluded, status=stat, register=reg,
                                 alt_raw=alt_raw, pred_raw=row[c_pred]))
    return pd.DataFrame(recs), issues


# ----------------------------------------------------------------------------
# Arrays und Indikatoren
# ----------------------------------------------------------------------------
def build_arrays(dfm, kidx, R, N):
    valid = np.zeros((R, N), bool)
    gt = np.full((R, N), -1)
    pred = np.full((R, N), -1)
    allowed = np.zeros((R, N, K + 1), bool)
    for r in dfm.itertuples():
        if r.gt is None or r.gt == K:
            continue
        i, n = r.run - 1, kidx[r.key]
        gt[i, n] = r.gt
        for a in r.allowed:
            allowed[i, n, a] = True
        if not r.excluded:
            valid[i, n] = True
            pred[i, n] = r.pred
    return dict(valid=valid, gt=gt, pred=pred, allowed=allowed)


def indicators(A, mask=None):
    valid = A["valid"] if mask is None else (A["valid"] & mask[None, :])
    gt, pred, allowed = A["gt"], A["pred"], A["allowed"]
    R, N = valid.shape
    eye = np.eye(K + 1, dtype=bool)[:, :K]
    gt_oh = np.zeros((R, N, K), bool)
    pred_oh = np.zeros((R, N, K), bool)
    gt_oh[valid] = eye[gt[valid]]
    pred_oh[valid] = eye[pred[valid]]
    p = np.where(pred < 0, 0, pred)
    hit = valid & np.take_along_axis(allowed, p[..., None], 2)[..., 0]
    f = lambda x: x.astype(np.float64)
    return dict(
        valid=f(valid), strict=f(valid & (pred == gt)), hit=f(hit),
        gt_oh=f(gt_oh), pred_oh=f(pred_oh), tp=f(gt_oh & pred_oh),
        aP=f(pred_oh & allowed[:, :, :K]), aR=f(gt_oh & hit[..., None]),
    )


def compute(W, I):
    """W: (B,N) Gewichte. Rückgabe: Metriken je Bootstrap und Lauf."""
    g = lambda M: np.einsum("bn,rn->br", W, M)
    f = lambda M: np.einsum("bn,rnk->brk", W, M)
    nv, sc, ac = g(I["valid"]), g(I["strict"]), g(I["hit"])
    gtc, pc, tp = f(I["gt_oh"]), f(I["pred_oh"]), f(I["tp"])
    ap, ar = f(I["aP"]), f(I["aR"])
    with np.errstate(divide="ignore", invalid="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        m = dict(
            strict_acc=sc / nv, allowed_acc=ac / nv,
            sP=tp / pc, sR=tp / gtc, sF1=2 * tp / (gtc + pc),
            aP=ap / pc, aR=ar / gtc,
        )
        for name, src in [("strict_macroP", "sP"), ("strict_macroR", "sR"), ("strict_macroF1", "sF1"),
                          ("allowed_macroP", "aP"), ("allowed_macroR", "aR")]:
            m[name] = np.nanmean(m[src], axis=2)
    return m


def run_mean(m):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return {k: np.nanmean(v, axis=1) for k, v in m.items()}


OVERALL = [
    ("Allowed Accuracy", "allowed_acc"),
    ("Allowed Macro-Precision", "allowed_macroP"),
    ("Allowed Macro-Recall", "allowed_macroR"),
    ("Strict Accuracy", "strict_acc"),
    ("Strict Macro-Precision", "strict_macroP"),
    ("Strict Macro-Recall", "strict_macroR"),
    ("Strict Macro-F1", "strict_macroF1"),
]
PERCLASS = [
    ("Allowed Precision", "aP"),
    ("Allowed Recall", "aR"),
    ("Strict Precision", "sP"),
    ("Strict Recall", "sR"),
    ("Strict F1", "sF1"),
]


def pct(x, d=2):
    return "–" if x is None or np.isnan(x) else f"{x*100:.{d}f}%".replace(".", ",")


def fmt(p, lo, hi):
    if np.isnan(p):
        return "–"
    return f"{pct(p)} [{pct(lo,1)[:-1]}–{pct(hi,1)[:-1]}]"


def ci(arr):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanpercentile(arr, CI, axis=0)


def boot_p(d):
    """Zweiseitiger Bootstrap-p-Wert für H0: Δ = 0."""
    d = d[~np.isnan(d)]
    if len(d) == 0:
        return np.nan
    return min(1.0, 2 * min(np.mean(d <= 0), np.mean(d >= 0)))


def holm(pvals):
    """Holm-Bonferroni-adjustierte p-Werte (gleiche Reihenfolge wie Eingabe)."""
    p = np.asarray(pvals, float)
    m = len(p)
    order = np.argsort(p)
    adj = np.empty(m)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * p[i]))
        adj[i] = running
    return adj


def pfmt(p):
    if np.isnan(p):
        return "–"
    if p < 1.0 / N_BOOT:
        return f"<{1.0 / N_BOOT:.4f}".replace(".", ",")
    return f"{p:.4f}".replace(".", ",")


# ----------------------------------------------------------------------------
# Excel-Formatierung (Blautöne wie bisherige Auswertungstabellen)
# ----------------------------------------------------------------------------
TITLE_FILL = "1F3864"
HEADER_FILL = "2F5597"
ROW_FILLS = ("DCE6F1", "EEF3FA")
HIGHLIGHT_FILL = "BDD7EE"
SECTION_FILL = "D9D9D9"


def write_styled(xw, df, sheet, title, highlight=(), section=()):
    """Schreibt df mit Titelzeile, blauem Kopf und abwechselnd hellblauen Zeilen.
    highlight: Zeilenindizes (0-basiert) fett hervorheben; section: Trennzeilen grau."""
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    df.to_excel(xw, sheet_name=sheet, index=False, startrow=1)
    ws = xw.book[sheet]
    ncol = max(1, df.shape[1])
    white = Side(style="thin", color="FFFFFF")
    border = Border(left=white, right=white, top=white, bottom=white)

    ws.cell(row=1, column=1, value=title)
    if ncol > 1:
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncol)
    tc = ws.cell(row=1, column=1)
    tc.font = Font(name="Calibri", size=13, bold=True, color="FFFFFF")
    tc.fill = PatternFill("solid", fgColor=TITLE_FILL)
    tc.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 26

    for c in range(1, ncol + 1):
        h = ws.cell(row=2, column=c)
        h.font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        h.fill = PatternFill("solid", fgColor=HEADER_FILL)
        h.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        h.border = border
    ws.row_dimensions[2].height = 30

    for i in range(len(df)):
        r = i + 3
        if i in section:
            fill, bold = SECTION_FILL, True
        elif i in highlight:
            fill, bold = HIGHLIGHT_FILL, True
        else:
            fill, bold = ROW_FILLS[i % 2], False
        for c in range(1, ncol + 1):
            cell = ws.cell(row=r, column=c)
            cell.fill = PatternFill("solid", fgColor=fill)
            cell.font = Font(name="Calibri", size=11, bold=bold)
            cell.border = border
            cell.alignment = Alignment(horizontal="left" if c == 1 else "center", vertical="center")

    for c in range(1, ncol + 1):
        vals = [ws.cell(row=r, column=c).value for r in range(2, len(df) + 3)]
        width = max((len(str(v)) for v in vals if v is not None), default=8)
        ws.column_dimensions[ws.cell(row=2, column=c).column_letter].width = min(max(12, width + 3), 70)
    ws.freeze_panes = "B3"
    ws.sheet_view.showGridLines = False


# ----------------------------------------------------------------------------
# Hauptprogramm
# ----------------------------------------------------------------------------
def main():
    df, issues = load_all()
    models = list(dict.fromkeys(df["model"]))
    keys = sorted(df["key"].unique())
    kidx = {k: i for i, k in enumerate(keys)}
    N = len(keys)
    R = {m: int(df.loc[df.model == m, "run"].max()) for m in models}
    print(f"{len(models)} Modelle, {N} Baugruppen, {len(df)} Zeilen gelesen.")

    arrays = {m: build_arrays(df[df.model == m], kidx, R[m], N) for m in models}
    common = np.all(np.vstack([arrays[m]["valid"] for m in models]), axis=0)

    rng = np.random.default_rng(SEED)
    W = rng.multinomial(N, np.full(N, 1.0 / N), size=N_BOOT).astype(np.float64)
    W1 = np.ones((1, N))

    def evaluate(mask=None):
        point, perrun, boot = {}, {}, {}
        for m in models:
            I = indicators(arrays[m], mask)
            pr = compute(W1, I)
            perrun[m] = {k: v[0] for k, v in pr.items()}
            point[m] = {k: v[0] for k, v in run_mean(pr).items()}
            boot[m] = run_mean(compute(W, I))
        return point, perrun, boot

    point, perrun, boot = evaluate()
    point_c, _, boot_c = evaluate(common)

    # ---- Hauptergebnisse -----------------------------------------------------
    def overall_table(pt, bt):
        rows = []
        for name, k in OVERALL:
            row = {"Metrik": name}
            for m in models:
                lo, hi = ci(bt[m][k])
                row[m] = fmt(pt[m][k], lo, hi)
            rows.append(row)
        return pd.DataFrame(rows)

    main_tab = overall_table(point, boot)

    # Zusatzzeilen
    first = df.drop_duplicates("key").set_index("key")
    extra = []
    for label, fn in [
        ("Baugruppen gesamt", lambda m: str(N)),
        ("Mehrdeutige Baugruppen (|A|>1)",
         lambda m: f"{int((first.n_alts > 0).sum())} ({pct((first.n_alts > 0).mean(),1)})"),
        ("EXCLUDED (Summe über Läufe)",
         lambda m: str(int(df[(df.model == m)].excluded.sum()))),
    ]:
        extra.append({"Metrik": label, **{m: fn(m) for m in models}})
    main_tab = pd.concat([main_tab, pd.DataFrame(extra)], ignore_index=True)

    # Accuracy-CI analytisch (CLT, Baugruppe als Einheit)
    clt_rows = []
    for m in models:
        A = arrays[m]
        I = indicators(A)
        for name, key in [("Allowed Accuracy", "hit"), ("Strict Accuracy", "strict")]:
            v = I["valid"].sum(0)
            s = np.divide(I[key].sum(0), v, out=np.full(N, np.nan), where=v > 0)
            s = s[~np.isnan(s)]
            mu, se = s.mean(), s.std(ddof=1) / np.sqrt(len(s))
            clt_rows.append(dict(Modell=m, Metrik=name, Mittel=pct(mu), SE=pct(se),
                                 CI_95=f"[{pct(mu-1.96*se,1)}–{pct(mu+1.96*se,1)}]", n=len(s)))

    # ---- Klassenweise --------------------------------------------------------
    n_cls = {CLASSES[c]: int((first["gt"] == c).sum()) for c in range(K)}

    def class_table(k):
        rows = []
        for c in range(K):
            row = {"Klasse": f"[{CODES[c]}] {CLASSES[c]}", "n": n_cls[CLASSES[c]]}
            for m in models:
                lo, hi = ci(boot[m][k][:, c])
                row[m] = fmt(point[m][k][c], lo, hi)
            rows.append(row)
        return pd.DataFrame(rows)

    cls = {name: class_table(k) for name, k in PERCLASS}

    # ---- Run-to-run SD -------------------------------------------------------
    sd_rows = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        for name, k in OVERALL:
            sd_rows.append({"Metrik": name, **{m: pct(np.nanstd(perrun[m][k], ddof=1)) for m in models}})
        for name, k in PERCLASS:
            for c in range(K):
                sd_rows.append({"Metrik": f"{name} [{CODES[c]}] {CLASSES[c]}",
                                **{m: pct(np.nanstd(perrun[m][k][:, c], ddof=1)) for m in models}})
    sd_tab = pd.DataFrame(sd_rows)

    # Pro-Lauf-Werte (zum Abgleich mit bisherigen Tabellen)
    run_rows = []
    for m in models:
        for r in range(R[m]):
            row = {"Modell": m, "Lauf": r + 1}
            for name, k in OVERALL:
                row[name] = pct(perrun[m][k][r])
            for c in range(K):
                row[f"Strict F1 [{CODES[c]}]"] = pct(perrun[m]["sF1"][r, c])
            run_rows.append(row)

    # ---- Paarweise Vergleiche (gepaarter Bootstrap) --------------------------
    pair_rows = []
    for a, b in itertools.combinations(models, 2):
        for name, k in [("Allowed Accuracy", "allowed_acc"), ("Allowed Macro-Recall", "allowed_macroR"),
                        ("Strict Macro-F1", "strict_macroF1")]:
            d = boot[a][k] - boot[b][k]
            lo, hi = ci(d)
            dp = point[a][k] - point[b][k]
            pair_rows.append({"Modell A": a, "Modell B": b, "Metrik": name,
                              "Δ (A−B)": pct(dp), "95%-CI": f"[{pct(lo,1)}; {pct(hi,1)}]",
                              "_p": boot_p(d),
                              "Signifikant (CI ohne 0)": "ja" if (lo > 0 or hi < 0) else "nein"})
    p_adj = holm([r["_p"] for r in pair_rows]) if pair_rows else []
    for r, pa in zip(pair_rows, p_adj):
        p_raw = r.pop("_p")
        sig_raw = r.pop("Signifikant (CI ohne 0)")
        r["p (roh)"] = pfmt(p_raw)
        r["Signifikant (roh, CI ohne 0)"] = sig_raw
        r["p (Holm)"] = pfmt(pa)
        r["Signifikant (Holm, α=0,05)"] = "ja" if pa < 0.05 else "nein"

    # ---- Robustheit: gemeinsame Stichprobe -----------------------------------
    robust = overall_table(point_c, boot_c)
    robust = pd.concat([robust, pd.DataFrame([{"Metrik": "Baugruppen in gemeinsamer Stichprobe",
                                                **{m: str(int(common.sum())) for m in models}}])],
                       ignore_index=True)

    # ---- Ausfälle (EXCLUDED) -------------------------------------------------
    exc_run = (df.groupby(["model", "run"]).excluded.agg(["sum", "count"])
               .reset_index().rename(columns={"model": "Modell", "run": "Lauf",
                                              "sum": "EXCLUDED", "count": "Zeilen"}))
    exc_key = (df[df.excluded].groupby("key").agg(Ausfälle=("excluded", "size"),
                                                 Modelle=("model", lambda s: ", ".join(sorted(set(s)))))
               .sort_values("Ausfälle", ascending=False).reset_index().rename(columns={"key": "SAP-Nummer"}))
    total_runs = sum(R.values())
    exc_key["von Läufen"] = total_runs

    # ---- Stabilität der Vorhersagen ------------------------------------------
    stab_rows = []
    for m in models:
        A = arrays[m]
        changed = []
        for n in range(N):
            v = A["valid"][:, n]
            if v.sum() >= 2 and len(set(A["pred"][v, n])) > 1:
                changed.append(keys[n])
        stab_rows.append({"Modell": m, "Baugruppen mit wechselnder Vorhersage": len(changed),
                          "SAP-Nummern": ", ".join(changed)})

    # ---- Prüfungen -----------------------------------------------------------
    chk = []
    for r in df.itertuples():
        if r.excluded or r.gt is None or r.status not in ("CORRECT", "INCORRECT"):
            continue
        mine = "CORRECT" if r.pred in r.allowed else "INCORRECT"
        if mine != r.status:
            chk.append(dict(Typ="Abweichung Allowed_Set_Status", Modell=r.model, Lauf=r.run, Datei=r.file,
                            SAP=r.key, Detail=f"GT={CLASSES[r.gt] if r.gt is not None and r.gt < K else r.gt} | "
                                              f"ZGT={r.alt_raw} | Pred={r.pred_raw} | Datei={r.status} | Neu={mine}"))
    for k_, g in first.iterrows():
        reg = str(g.register).upper()
        if reg == "M" and g.n_alts == 0:
            chk.append(dict(Typ="Register M ohne ZGT", SAP=k_))
        if reg.startswith("E") and g.n_alts > 0:
            chk.append(dict(Typ=f"Register {g.register} mit ZGT", SAP=k_, Detail=g.alt_raw))
    gt_conf = df.groupby("key").agg(n_gt=("gt", "nunique"), n_al=("allowed", "nunique"))
    for k_ in gt_conf[(gt_conf.n_gt > 1) | (gt_conf.n_al > 1)].index:
        chk.append(dict(Typ="GT/ZGT unterscheidet sich zwischen Dateien", SAP=k_))
    checks = pd.DataFrame(issues + chk) if (issues or chk) else pd.DataFrame([{"Typ": "Keine Auffälligkeiten"}])

    # ---- Hinweise ------------------------------------------------------------
    notes = pd.DataFrame({"Hinweis": [
        "Allowed: Vorhersage ∈ {GT} ∪ {weitere zulässige GT} gilt als korrekt.",
        "Strict: Vorhersage = GT (Primärlabel) gilt als korrekt.",
        "Allowed Precision (Klasse c): unter allen Vorhersagen c der Anteil, bei dem c zulässig ist.",
        "Allowed Recall (Klasse c): unter allen Baugruppen mit Primärlabel c der Anteil mit zulässiger Vorhersage.",
        "Kein Allowed-F1: Allowed Precision und Allowed Recall zählen verschiedene Ereignisse.",
        "Macro = ungewichteter Mittelwert über die 7 Klassen; je Lauf berechnet, dann über Läufe gemittelt.",
        "Strict F1 = 2TP/(2TP+FP+FN); Macro-F1 = Mittelwert der Klassen-F1.",
        f"95%-CI: Perzentil-Bootstrap über Baugruppen (B={N_BOOT}, Seed={SEED}); jede gezogene Baugruppe "
        "behält alle ihre Läufe. Gepaarter Bootstrap: gleiche Ziehungen für alle Modelle.",
        "EXCLUDED (HTTP-Fehler, keine Ausgabe) wird je Lauf nicht gewertet.",
        "Robustheit: gleiche Auswertung nur auf Baugruppen, die in allen Läufen aller Modelle eine Ausgabe haben.",
        "Run-to-run SD: Standardabweichung über die 10 Läufe (ddof=1), misst Stabilität, nicht Unsicherheit.",
        "Paarvergleich: zweiseitiger Bootstrap-p-Wert = 2·min(P(Δ≤0), P(Δ≥0)); Holm-Bonferroni-Korrektur "
        "über alle Vergleiche der Tabelle (Holm, 1979). Kleinster darstellbarer p-Wert: 1/B.",
    ]})

    # ---- Schreiben -----------------------------------------------------------
    n_main = len(main_tab)
    tag = f"95%-CI, Bootstrap B={N_BOOT}"
    with pd.ExcelWriter(OUTPUT_FILE, engine="openpyxl") as xw:
        write_styled(xw, main_tab, "Hauptergebnis",
                     f"Hauptergebnis – Allowed (Hauptmetrik) und Strict (Primärlabel) ({tag})",
                     highlight=(0,), section=())
        write_styled(xw, cls["Allowed Recall"], "Klassen_Allowed_Recall",
                     f"Allowed Recall je Klasse (nach Primärlabel) ({tag})")
        write_styled(xw, cls["Allowed Precision"], "Klassen_Allowed_Precision",
                     f"Allowed Precision je Klasse (nach Vorhersage) ({tag})")
        write_styled(xw, cls["Strict F1"], "Klassen_Strict_F1", f"Strict F1 je Klasse ({tag})")
        write_styled(xw, cls["Strict Precision"], "Klassen_Strict_Precision", f"Strict Precision je Klasse ({tag})")
        write_styled(xw, cls["Strict Recall"], "Klassen_Strict_Recall", f"Strict Recall je Klasse ({tag})")
        write_styled(xw, pd.DataFrame(pair_rows), "Paarvergleich",
                     f"Paarweiser Modellvergleich – gepaarter Bootstrap, Holm-Korrektur über {len(pair_rows)} Vergleiche")
        write_styled(xw, robust, "Robustheit_gemeinsam",
                     f"Robustheit – nur Baugruppen mit Ausgabe in allen Läufen aller Modelle ({tag})", highlight=(0,))
        write_styled(xw, pd.DataFrame(clt_rows), "Accuracy_CLT", "Accuracy – analytisches 95%-CI (CLT, Baugruppe als Einheit)")
        write_styled(xw, sd_tab, "Run_to_run_SD", "Run-to-run-Standardabweichung über 10 Läufe (Stabilität)")
        write_styled(xw, pd.DataFrame(run_rows), "Pro_Lauf", "Metriken je Lauf")
        write_styled(xw, exc_run, "Ausfaelle_pro_Lauf", "EXCLUDED (keine Ausgabe) je Modell und Lauf")
        write_styled(xw, exc_key if len(exc_key) else pd.DataFrame([{"SAP-Nummer": "keine Ausfälle"}]),
                     "Ausfaelle_pro_SAP", "EXCLUDED je Baugruppe (über alle Läufe aller Modelle)")
        write_styled(xw, pd.DataFrame(stab_rows), "Stabilitaet", "Baugruppen mit wechselnder Vorhersage über die Läufe")
        write_styled(xw, checks, "Pruefungen", "Datenprüfungen")
        write_styled(xw, notes, "Hinweise", "Hinweise und Definitionen")

    print("\nHauptergebnis:")
    print(main_tab.to_string(index=False))
    print(f"\nPrüfungen: {0 if checks.iloc[0, 0] == 'Keine Auffälligkeiten' else len(checks)} Auffälligkeiten")
    print(f"Gespeichert: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
