"""Hauptauswertung mit R1 als Ground Truth: Wiederholungsläufe (10 runs) auf 115 und 185 Baugruppen.

Struktur nach Absprache mit dem Betreuer (22.11.2026):
  - Allowed-Label-Set Accuracy (Mittel über die Läufe, Standardabweichung, 95%-Bootstrap-KI)
    für alle Baugruppen, nur eindeutige (keine weiteren zulässigen Labels) und nur mehrdeutige.
  - Macro-Precision, -Recall, -F1 nur auf den eindeutigen Baugruppen (Standardformeln, je Lauf, gemittelt;
    ohne Bootstrap). Dort ist das zulässige Set = {Primärlabel}, also Allowed = Strict.
  - Keine Trennung E1/E2 mehr. M ohne weiteres zulässiges Label zählt als eindeutig.

GT: R1 aus thesis/R1.md (Markdown-Tabelle) oder einer Excel-Datei mit den Spalten SAP-Nummer, Teamcenter,
Ground Truth, Register, Weitere zulässige Ground Truth (optional prompt_engineering). GT, Register und
zulässige Labels der Ergebnisdateien werden ignoriert. Prompt-Engineering-BG (14) sind ausgeschlossen.

Eingabe: --dir mit Konfigurationsordnern (z. B. gemini-2.5-flash_pdf_P3_10_runs, ..._70BG_10_runs).
Modell aus dem Ordnernamen; Hauptdatensatz (115) oder Ergänzung (70) wird aus den Baugruppen erkannt,
daher dürfen Ordner beliebig heißen. Läufe werden je Datensatz nach Dateiname (Zeitstempel) sortiert;
für 185 BG wird Lauf i (115) mit Lauf i (70) zusammengelegt.

Bootstrap: 2000 Wiederholungen, Baugruppen mit Zurücklegen, jede mit allen ihren Läufen
(Wert je BG = Anteil korrekter Läufe; bei 185 BG getrennt nach Datensatz gezogen).

Benötigt im selben Ordner: evaluate_pdf_results.py, evaluate_70bg_results.py, evaluate_prompt_results.py,
confusion_human_llm.py, evaluate_validation_regimes.py.

Aufruf (PowerShell):
    python evaluate_r1.py --dir "C:\\...\\stability" --gt "C:\\...\\R1.md" --out "C:\\...\\Ergebnis_R1"
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evaluate_pdf_results as E  # noqa: E402
import evaluate_70bg_results as S  # noqa: E402

cm = E.cm
B, SEED = 2000, 42
MODEL_ORDER = ["Gemini 2.5 Pro", "Gemini 2.5 Flash", "Claude Haiku 4.5", "GPT-5.5", "DeepSeek-V4-Flash"]
SKIP_DIRS = {"backup_original", "__pycache__", "nachlauf"}


# ---------------------------------------------------------------- GT (R1)
def load_gt(path):
    path = Path(path)
    if path.suffix.lower() == ".md":
        rows = []
        head = None
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.startswith("|") or set(line.replace("|", "").strip()) <= set("-: "):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if head is None and any("SAP" in c for c in cells):
                head = cells
                continue
            if head and len(cells) >= len(head) - 1:
                rows.append(dict(zip(head, cells + [""] * (len(head) - len(cells)))))
        df = pd.DataFrame(rows)
    else:
        df = pd.read_excel(path, dtype=str)
    cols = list(df.columns)
    c = dict(sap=E.find_col(cols, contains=["sap"]), tc=E.find_col(cols, contains=["teamcenter"]),
             gt=E.find_col(cols, exact="Ground Truth"), reg=E.find_col(cols, contains=["regist"]),
             alt=E.find_col(cols, contains=["weitere"]),
             pe=E.find_col(cols, contains=["prompt"]) or next((x for x in cols if "Prompt Engineering" in x), None))
    gt, pe, issues = {}, set(), []
    for _, r in df.iterrows():
        sap = r[c["sap"]] if c["sap"] else None
        tc = r[c["tc"]] if c["tc"] else None
        k = cm.match_key(sap if sap else None, tc if tc else None)
        if k is None:
            issues.append(f"GT-Zeile ohne Zuordnung: {sap} / {tc}")
            continue
        g = cm.canon(str(r[c["gt"]]).strip())
        if g is None or g.startswith("UNGÜLTIG"):
            issues.append(f"GT-Label nicht erkannt: {sap} / {tc}: {r[c['gt']]}")
            continue
        alts = {cm.canon(a.strip()) for a in re.split(r"[,;\n|]", str(r[c["alt"]] or "")) if a.strip()} - {g}
        alts = {a for a in alts if a and not a.startswith("UNGÜLTIG")}
        gt[k] = (g, frozenset({g} | alts))
        if c["pe"] and str(r[c["pe"]]).strip().lower() == "yes":
            pe.add(k)
    return gt, pe, issues


# ---------------------------------------------------------------- Läufe einlesen
def collect(root, sheet, gt, pe, issues):
    """{Modell: {"main": [Lauf...], "supp": [Lauf...]}}; Lauf = {BG: (pred oder None)}."""
    main_keys = set(cm.MAIN_115)
    out, info = {}, []
    roots = [Path(x) for x in (root if isinstance(root, (list, tuple)) else [root])]
    # Konfigurationsordner = Ordner, die selbst Ergebnisdateien enthalten (auch eine Ebene tiefer,
    # z. B. 03_Wiederholung\115BG\<Konfiguration>)
    cands = []
    for rt in roots:
        for p in [rt] + sorted(rt.rglob("*")):
            if p.is_dir() and not any(x.lower() in SKIP_DIRS or x.lower().startswith("_backup_vor_merge")
                                      for x in p.relative_to(rt).parts) \
                    and any(f.suffix.lower() in (".xlsx", ".xlsm") and not E.is_output_or_backup(f) for f in p.glob("*")):
                cands.append(p)
    for d in cands:
        files = sorted(f for f in d.glob("*") if f.suffix.lower() in (".xlsx", ".xlsm")
                       and not E.is_output_or_backup(f))
        if not files:
            continue
        model = E.model_name(d)
        if model not in MODEL_ORDER and model not in ("Claude Opus 4.8",):
            print(f"  ! Ordner {d.name}: Modell nicht erkannt – übersprungen")
            continue
        for f in files:
            run = read_predictions(f, sheet, f"{model} | {d.name}", gt, pe, issues)
            if not run:
                print(f"  ! {d.name}/{f.name}: keine auswertbaren Zeilen – übersprungen")
                continue
            parts = {"main": {k: v for k, v in run.items() if k in main_keys},
                     "supp": {k: v for k, v in run.items() if k not in main_keys}}
            if parts["main"] and parts["supp"]:
                print(f"  Hinweis: {f.name} enthält beide Datensätze – aufgeteilt")
            for ds, part in parts.items():
                if part:
                    out.setdefault(model, {"main": [], "supp": []})[ds].append((f, part))
                    info.append((model, ds, d.name))
    # Warnung: Läufe eines Modells/Datensatzes aus mehreren Ordnern (z. B. Vergleichsläufe mit eingelesen)
    for model in out:
        for ds in ("main", "supp"):
            dirs = sorted({d for m, x, d in info if m == model and x == ds})
            if len(dirs) > 1:
                print(f"  ! {model} ({'115' if ds == 'main' else '70'} BG): Läufe aus mehreren Ordnern {dirs} – "
                      f"nur Ordner der Wiederholungsläufe in --dir legen!")
            n = len(out[model][ds])
            if n and n != 10:
                print(f"  ! {model} ({'115' if ds == 'main' else '70'} BG): {n} Läufe (erwartet 10)")
    return out, info


def read_predictions(path, sheet, who, gt, pe, issues):
    """Nur Kennung und Vorhersage lesen – GT/Register/zulässige Labels der Datei werden nicht benutzt."""
    xl = pd.ExcelFile(path)
    sh = sheet if sheet in xl.sheet_names else xl.sheet_names[0]
    df = pd.read_excel(path, sheet_name=sh, dtype=str)
    cols = list(df.columns)
    c_sap, c_tc = E.find_col(cols, contains=["sap"]), E.find_col(cols, contains=["teamcenter"])
    c_pred, c_pe = E.find_col(cols, contains=["predicted"]), E.find_col(cols, contains=["prompt", "engineer"])
    if not c_pred or not (c_sap or c_tc):
        print(f"  ! {path.name}: keine Spalten SAP/Teamcenter + Predicted_Label – keine Ergebnisdatei, übersprungen")
        return {}
    run = {}
    for i, r in df.iterrows():
        if c_pe and str(r[c_pe]).strip().lower() == "yes":
            continue
        k = cm.match_key(r[c_sap] if c_sap else None, r[c_tc] if c_tc else None)
        if k is None:
            if not all(E.is_empty(r[c]) for c in (c_sap, c_tc) if c):
                issues.append(dict(Modell=who, Typ="BG nicht zuordenbar", SAP=str(r[c_sap] if c_sap else r[c_tc])))
            continue
        if k in pe:
            continue
        if k not in gt:
            issues.append(dict(Modell=who, Typ="BG nicht in R1", SAP=k))
            continue
        raw = "" if E.is_empty(r[c_pred]) else str(r[c_pred]).strip()
        if not raw or raw.upper() == "[EMPTY]":
            issues.append(dict(Modell=who, Typ="Leere Vorhersage (im Lauf nicht gewertet)", SAP=k, Detail=path.name))
            continue
        p = cm.canon(raw)
        if p is None or p.startswith("UNGÜLTIG"):
            issues.append(dict(Modell=who, Typ="Vorhersage nicht erkannt (als falsch gewertet)", SAP=k, Detail=raw))
            p = "UNGÜLTIG:" + raw
        if k in run:
            issues.append(dict(Modell=who, Typ="Doppelte Baugruppe (erste Zeile verwendet)", SAP=k, Detail=path.name))
            continue
        run[k] = p
    return run


def correct(gt, k, pred):
    return pred is not None and not str(pred).startswith("UNGÜLTIG") and pred in gt[k][1]


# ---------------------------------------------------------------- Kennzahlen
def macro_prf(pairs):
    """Standard-Macro-P/R/F1 (eindeutige BG): P über vorhergesagte, R über GT-Klassen, F1 über beide."""
    K, IDX = len(cm.CLASSES), cm.IDX
    gtc, pc, tp = np.zeros(K), np.zeros(K), np.zeros(K)
    for g, p in pairs:
        gtc[IDX[g]] += 1
        if p in IDX:
            pc[IDX[p]] += 1
            if p == g:
                tp[IDX[p]] += 1
    with np.errstate(divide="ignore", invalid="ignore"):
        P = np.where(pc > 0, tp / pc, np.nan)
        R = np.where(gtc > 0, tp / gtc, np.nan)
        F = np.where(gtc + pc > 0, 2 * tp / (gtc + pc), np.nan)
    return float(np.nanmean(P)), float(np.nanmean(R)), float(np.nanmean(F))


def subset_keys(gt, keys, which):
    if which == "alle":
        return list(keys)
    amb = which == "mehrdeutig"
    return [k for k in keys if (len(gt[k][1]) > 1) == amb]


def build_runs(runs_main, runs_supp, scope):
    if scope == "115":
        return [r for _, r in runs_main]
    n = min(len(runs_main), len(runs_supp))
    return [{**runs_main[i][1], **runs_supp[i][1]} for i in range(n)]


def evaluate(gt, runs_main, runs_supp, scope, rng):
    """scope: '115' oder '185'. Rückgabe: dict je Teilmenge."""
    runs = build_runs(runs_main, runs_supp, scope)
    strata = [set(cm.MAIN_115)]
    if not runs:
        return None
    allkeys = sorted(set().union(*runs))
    res = {}
    for which in ("alle", "eindeutig", "mehrdeutig"):
        keys = subset_keys(gt, allkeys, which)
        # je Lauf: Accuracy über die in diesem Lauf gültig vorhandenen BG
        accs = []
        for run in runs:
            ks = [k for k in keys if k in run]
            if ks:
                accs.append(np.mean([correct(gt, k, run[k]) for k in ks]))
        # je BG: Anteil korrekter Läufe (für Bootstrap)
        share = {k: np.mean([correct(gt, k, run[k]) for run in runs if k in run]) for k in keys
                 if any(k in run for run in runs)}
        # Bootstrap (bei 185 je Datensatz getrennt gezogen)
        if scope == "185":
            groups = [[k for k in share if k in strata[0]], [k for k in share if k not in strata[0]]]
        else:
            groups = [list(share)]
        groups = [np.array([share[k] for k in g]) for g in groups if g]
        boots = np.empty(B)
        for b in range(B):
            draws = [g[rng.integers(0, len(g), len(g))] for g in groups]
            boots[b] = np.concatenate(draws).mean()
        row = dict(n=len(share), runs=len(runs), acc=float(np.mean(accs)) if accs else np.nan,
                   sd=float(np.std(accs, ddof=1) * 100) if len(accs) > 1 else np.nan,
                   ci_lo=float(np.percentile(boots, 2.5)), ci_hi=float(np.percentile(boots, 97.5)),
                   acc_bg=float(np.mean(list(share.values()))))
        if which == "eindeutig":
            prf = []
            for run in runs:
                pairs = [(gt[k][0], run[k]) for k in keys if k in run]
                prf.append(macro_prf(pairs))
            row["prec"], row["rec"], row["f1"] = (float(np.mean([x[i] for x in prf])) for i in range(3))
        res[which] = row
    return res


# ---------------------------------------------------------------- Konfusionsmatrix (Stil Betreuer-Beispiel)
ABBR = {"Lineareinheit": "LE", "Rotationseinheit": "RE", "Greifer": "GR", "Multi-Achs-System (Gantry)": "MA",
        "Roboter": "RO", "Kombinierte Einheit": "KE", "Keine der verfügbaren Klassen": "SO"}
COL_ORDER = ["Lineareinheit", "Rotationseinheit", "Greifer", "Multi-Achs-System (Gantry)", "Roboter",
             "Kombinierte Einheit", "Keine der verfügbaren Klassen"]
LEGEND = ("LE = Lineareinheit, RE = Rotationseinheit, GR = Greifer, MA = Multi-Achs-System (Gantry), "
          "RO = Roboter, KE = Kombinierte Einheit, SO = Keine der verfügbaren Klassen")


def set_label(allowed):
    return "{" + ", ".join(ABBR[c] for c in COL_ORDER if c in allowed) + "}"


def confusion_data(gt, runs):
    """Mittlere Konfusionsmatrix über die Läufe (Zelle = mittlere Anzahl je Lauf).
    Zeilen: eindeutige Klassen (Primärlabel) und mehrdeutige Labelmengen; Spalten: Vorhersage."""
    R = len(runs)
    keys = sorted(set().union(*runs))
    rows = {}  # Zeilenschlüssel -> dict
    for k in keys:
        allowed = gt[k][1]
        rk = ("E", gt[k][0]) if len(allowed) == 1 else ("M", allowed)
        row = rows.setdefault(rk, {"cnt": {c: 0.0 for c in COL_ORDER}, "inv": 0.0, "miss": 0.0, "n": 0,
                                   "korrekt": 0.0, "allowed": allowed})
        row["n"] += 1
        for run in runs:
            if k not in run:
                row["miss"] += 1 / R
                continue
            p = run[k]
            if p in row["cnt"]:
                row["cnt"][p] += 1 / R
            else:
                row["inv"] += 1 / R
            if correct(gt, k, p):
                row["korrekt"] += 1 / R
    eind = [(c, rows[("E", c)]) for c in COL_ORDER if ("E", c) in rows]
    mehr = sorted([(rk[1], v) for rk, v in rows.items() if rk[0] == "M"], key=lambda x: (-x[1]["n"], set_label(x[0])))
    return eind, mehr


def write_confusion_sheet(wb, title, sheet_name, gt, runs):
    from openpyxl.utils import get_column_letter
    St = E.styles()
    Font = St["Font"]
    ws = wb.create_sheet(sheet_name[:31])
    ws.sheet_view.showGridLines = False
    eind, mehr = confusion_data(gt, runs)
    R = len(runs)
    fmt = "0" if R == 1 else "0.0"
    has_inv = any(v["inv"] > 0 for _, v in eind + mehr)
    has_miss = any(v["miss"] > 0 for _, v in eind + mehr)
    pred_cols = [ABBR[c] for c in COL_ORDER] + (["ungültig"] if has_inv else []) + (["fehlt"] if has_miss else [])
    head = ["Referenz ↓ / Vorhersage →"] + pred_cols + ["n", "korrekt", "Accuracy"]
    from openpyxl.styles import Alignment
    wrap = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.column_dimensions["A"].width = 2
    ws.column_dimensions["B"].width = 36
    for j in range(1, len(head)):
        ws.column_dimensions[get_column_letter(2 + j)].width = 9 if head[j] not in ("ungültig", "fehlt") else 10
    gap = 2 + len(head)
    ws.column_dimensions[get_column_letter(gap)].width = 3
    for j in range(len(COL_ORDER)):
        ws.column_dimensions[get_column_letter(gap + 1 + j)].width = 6

    def hdr(r, c, v, width=1):
        if width > 1:
            ws.merge_cells(start_row=r, start_column=c, end_row=r, end_column=c + width - 1)
        cell = ws.cell(r, c, v)
        cell.font = Font(bold=True, color="000000")
        cell.alignment = wrap
        for j in range(width):
            ws.cell(r, c + j).fill = St["fill"]("#D9D9D9")
            ws.cell(r, c + j).border = St["border"]

    ws.merge_cells(start_row=2, start_column=2, end_row=2, end_column=1 + len(head))
    t = ws.cell(2, 2, title)
    t.font = Font(bold=True, color="000000", size=13)
    for j in range(len(head)):
        ws.cell(2, 2 + j).fill = St["fill"]("#FFFFFF")
    hdr(3, gap + 1, "Zulässige Klassen je Zeile (1 = zulässig)", len(COL_ORDER))
    for j, h in enumerate(head):
        hdr(4, 2 + j, h)
    for j, c in enumerate(COL_ORDER):
        hdr(4, gap + 1 + j, ABBR[c])

    r = 5
    tot = {"E": [0.0, 0], "M": [0.0, 0]}
    for section, items in (("Eindeutig", [(ABBR[c], v) for c, v in eind]),
                           ("Mehrdeutig", [(set_label(a), v) for a, v in mehr])):
        ws.cell(r, 2, section).font = Font(bold=True, italic=True)
        r += 1
        for lab, v in items:
            ws.cell(r, 2, lab).border = St["border"]
            vals = [v["cnt"][c] for c in COL_ORDER] + ([v["inv"]] if has_inv else []) + ([v["miss"]] if has_miss else [])
            for j, x in enumerate(vals):
                cell = ws.cell(r, 3 + j, x)
                cell.number_format = fmt
                cell.alignment = St["center"]
                cell.border = St["border"]
                if j < len(COL_ORDER) and COL_ORDER[j] in v["allowed"]:
                    cell.font = Font(bold=True, color="1F4E9E")
            base = 3 + len(vals)
            for j, (x, f) in enumerate(((v["n"], "0"), (v["korrekt"], fmt), (v["korrekt"] / v["n"], "0.0%"))):
                cell = ws.cell(r, base + j, x)
                cell.number_format = f
                cell.alignment = St["right"]
                cell.border = St["border"]
            for j, c in enumerate(COL_ORDER):
                cell = ws.cell(r, gap + 1 + j, 1 if c in v["allowed"] else 0)
                cell.alignment = St["center"]
                cell.border = St["border"]
            key = "E" if section == "Eindeutig" else "M"
            tot[key][0] += v["korrekt"]
            tot[key][1] += v["n"]
            r += 1

    # Accuracy nach Teilmenge
    r += 2
    ws.cell(r, 2, "Accuracy nach Teilmenge").font = Font(bold=True)
    r += 1
    for j, h in enumerate(["Teilmenge", "korrekt", "n", "Accuracy"]):
        hdr(r, 2 + j, h)
    r += 1
    for lab, (k_, n_) in (("eindeutig", tot["E"]), ("mehrdeutig", tot["M"]),
                          ("alle (Allowed-Label-Set Accuracy)", [tot["E"][0] + tot["M"][0], tot["E"][1] + tot["M"][1]])):
        bold = lab.startswith("alle")
        for j, (x, f) in enumerate(((lab, None), (k_, fmt), (n_, "0"), (k_ / n_ if n_ else None, "0.0%"))):
            cell = ws.cell(r, 2 + j, x)
            cell.border = St["border"]
            cell.font = Font(bold=bold)
            if f:
                cell.number_format = f
        r += 1

    # Precision, Recall, F1 je Klasse (nur eindeutige)
    r += 2
    ws.cell(r, 2, "Precision, Recall und F1 je Klasse (nur eindeutige Baugruppen)").font = Font(bold=True)
    r += 1
    for j, h in enumerate(["Klasse", "TP", "vorhergesagt (Spaltensumme)", "Referenz (Zeilensumme)",
                           "Precision", "Recall", "F1"]):
        hdr(r, 2 + j, h)
    ws.row_dimensions[r].height = 45
    r += 1
    E_rows = dict(eind)
    P_, R_, F_ = [], [], []
    sums = [0.0, 0.0, 0.0]
    for c in COL_ORDER:
        tp = E_rows[c]["cnt"][c] if c in E_rows else 0.0
        pred = sum(v["cnt"][c] for _, v in eind)
        ref = (sum(E_rows[c]["cnt"].values()) + E_rows[c]["inv"]) if c in E_rows else 0.0
        P = tp / pred if pred else None
        Rr = tp / ref if ref else None
        F = 2 * tp / (pred + ref) if (pred + ref) else None
        if P is not None:
            P_.append(P)
        if Rr is not None:
            R_.append(Rr)
        if F is not None:
            F_.append(F)
        sums = [sums[0] + tp, sums[1] + pred, sums[2] + ref]
        for j, (x, f) in enumerate(((f"{ABBR[c]} – {c}", None), (tp, fmt), (pred, fmt), (ref, fmt),
                                    (P, "0.0%"), (Rr, "0.0%"), (F, "0.0%"))):
            cell = ws.cell(r, 2 + j, x if x is not None else "–")
            cell.border = St["border"]
            if f:
                cell.number_format = f
                cell.alignment = St["right"]
        r += 1
    macro = (float(np.mean(P_)) if P_ else None, float(np.mean(R_)) if R_ else None, float(np.mean(F_)) if F_ else None)
    for j, (x, f) in enumerate((("Macro (ungewichteter Mittelwert)", None), (sums[0], fmt), (sums[1], fmt),
                                (sums[2], fmt), (macro[0], "0.0%"), (macro[1], "0.0%"), (macro[2], "0.0%"))):
        cell = ws.cell(r, 2 + j, x)
        cell.border = St["border"]
        cell.font = Font(bold=True)
        if f:
            cell.number_format = f
    r += 2
    notes = [LEGEND,
             ("Zellen: mittlere Anzahl je Lauf über " + str(R) + " Läufe; " if R > 1 else "Zellen: Anzahl (1 Lauf); ")
             + "fett/blau = Vorhersage liegt in der zulässigen Labelmenge der Zeile.",
             "Mehrdeutige Zeilen: zulässige Labelmenge (ungeordnet, Primärlabel nicht unterschieden).",
             "Precision/Recall/F1 aus der mittleren Matrix der eindeutigen Baugruppen; Precision nur für vorhergesagte Klassen, "
             "Recall nur für Klassen mit Referenz; Macro = ungewichteter Mittelwert. Die Macro-Werte im Blatt "
             "'Wiederholläufe' sind dagegen je Lauf berechnet und gemittelt (kleine Abweichungen möglich)."]
    for i, txt in enumerate(notes):
        ws.cell(r + i, 2, txt).font = Font(italic=True, size=9, color="595959")


# ---------------------------------------------------------------- Excel
def write_excel(path, results, gt_name):
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter
    St = E.styles()
    Font = St["Font"]
    wb = Workbook()
    ws = wb.active
    ws.title = "Wiederholläufe"
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 2
    widths = [22, 9, 7, 14, 14, 20, 3, 14, 14, 20, 3, 14, 14, 20, 3, 12, 12, 12]
    for j, w in enumerate(widths):
        ws.column_dimensions[get_column_letter(2 + j)].width = w
    r = 2
    for scope, label in [("185", "185 Baugruppen"), ("115", "115 Baugruppen")]:
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=2 + len(widths) - 1)
        t = ws.cell(r, 2, f"Wiederholläufe (10 runs) mit {label} – Ground Truth {gt_name}, Allowed-Label-Set Accuracy")
        t.font = Font(bold=True, color="000000", size=13)
        t.alignment = St["left"]
        for j in range(len(widths)):
            ws.cell(r, 2 + j).fill = St["fill"]("#FFFFFF")
        # Kopf zweizeilig
        groups = [("Alle Baugruppen", 4), ("Eindeutige Baugruppen", 8), ("Mehrdeutige Baugruppen", 12),
                  ("Eindeutige: Macro (Mittel der Läufe)", 16)]
        for txt, c0 in groups:
            span = 3
            ws.merge_cells(start_row=r + 1, start_column=2 + c0 - 1 + (0 if c0 != 4 else 0),
                           end_row=r + 1, end_column=2 + c0 - 1 + span - 1 + (0 if c0 != 4 else 0))
        heads1 = ["Modell", "Läufe", "", "Alle Baugruppen", "", "", "", "Eindeutige Baugruppen", "", "", "",
                  "Mehrdeutige Baugruppen", "", "", "", "Eindeutige: Macro-Werte", "", ""]
        heads2 = ["", "", "", "Mittelwert", "SD (pp)", "95%-KI", "", "Mittelwert", "SD (pp)", "95%-KI", "",
                  "Mittelwert", "SD (pp)", "95%-KI", "", "Precision", "Recall", "F1"]
        for j, (h1, h2) in enumerate(zip(heads1, heads2)):
            for rr, h in ((r + 1, h1), (r + 2, h2)):
                c = ws.cell(rr, 2 + j, h if h else None)
                if widths[j] > 3:
                    c.font = Font(bold=True, color="000000")
                    c.fill = St["fill"]("#D9D9D9")
                    c.alignment = St["center"] if j else St["left"]
                    c.border = St["border"]
        # n-Zeile im Kopf
        rr = r + 3
        for i, m in enumerate([m for m in MODEL_ORDER if m in results] + [m for m in results if m not in MODEL_ORDER]):
            res = results[m].get(scope)
            bg = "#FFFFFF"
            vals = [m, res["alle"]["runs"] if res else "fehlt", None]
            for which in ("alle", "eindeutig", "mehrdeutig"):
                x = res[which] if res else None
                vals += [x["acc"] if x else None, x["sd"] if x else None,
                         f"[{x['ci_lo']*100:.1f}; {x['ci_hi']*100:.1f}]" if x else None, None]
            x = res["eindeutig"] if res else None
            vals += [x["prec"] if x else None, x["rec"] if x else None, x["f1"] if x else None]
            for j, v in enumerate(vals):
                if widths[j] <= 3:
                    continue
                if isinstance(v, float) and np.isnan(v):
                    v = None
                c = ws.cell(rr, 2 + j, v)
                c.fill, c.border = St["fill"](bg), St["border"]
                c.alignment = St["left"] if j == 0 else St["right"]
                hd = heads2[j]
                c.number_format = "0.0%" if hd in ("Mittelwert", "Precision", "Recall", "F1") else (
                    "0.00" if hd == "SD (pp)" else "General")
                c.font = Font(bold=hd == "Mittelwert" and j == 4)
            rr += 1
        # n
        any_res = next((results[m][scope] for m in results if results[m].get(scope)), None)
        if any_res:
            ws.cell(rr, 2, f"n: alle {any_res['alle']['n']}, eindeutig {any_res['eindeutig']['n']}, "
                           f"mehrdeutig {any_res['mehrdeutig']['n']} Baugruppen").font = Font(italic=True, size=9, color="595959")
        r = rr + 3
    notes = [
        "Mittelwert: Allowed-Label-Set Accuracy je Lauf, gemittelt über die Läufe. SD: Standardabweichung dieser Lauf-Werte (Prozentpunkte).",
        "95%-KI: Bootstrap über Baugruppen (2000 Wiederholungen, mit Zurücklegen, je BG alle Läufe; bei 185 BG getrennt nach Haupt- und Ergänzungsdatensatz).",
        "Eindeutig: keine weiteren zulässigen Labels (Allowed = Strict). Mehrdeutig: mindestens ein weiteres zulässiges Label.",
        "Macro-Precision/-Recall/-F1 nur auf eindeutigen Baugruppen (Standardformeln je Lauf, gemittelt). Precision über vorhergesagte Klassen, Recall über GT-Klassen, F1 = Mittel der Klassen-F1.",
        f"Ground Truth: {gt_name}; Prompt-Engineering-Baugruppen ausgeschlossen. Leere Vorhersagen zählen im jeweiligen Lauf nicht.",
    ]
    for i, txt in enumerate(notes):
        ws.cell(r + i, 2, txt).font = Font(italic=True, size=9, color="595959")

    # Tabellarische Rohwerte
    rows = []
    for m, sc in results.items():
        for scope, res in sc.items():
            if not res:
                continue
            for which, x in res.items():
                rows.append({"Modell": m, "Datensatz": scope, "Teilmenge": which, "n BG": x["n"], "Läufe": x["runs"],
                             "Accuracy Mittel (%)": round(x["acc"] * 100, 2), "SD (pp)": None if np.isnan(x["sd"]) else round(x["sd"], 2),
                             "KI unten (%)": round(x["ci_lo"] * 100, 2), "KI oben (%)": round(x["ci_hi"] * 100, 2),
                             "Accuracy je BG gemittelt (%)": round(x["acc_bg"] * 100, 2),
                             "Macro-P (%)": round(x["prec"] * 100, 2) if "prec" in x else None,
                             "Macro-R (%)": round(x["rec"] * 100, 2) if "rec" in x else None,
                             "Macro-F1 (%)": round(x["f1"] * 100, 2) if "f1" in x else None})
    ws2 = wb.create_sheet("Werte")
    df = pd.DataFrame(rows)
    ws2.append(list(df.columns))
    for v in df.itertuples(index=False):
        ws2.append(list(v))
    for c in ws2[1]:
        c.font = Font(bold=True)
    E.autosize(ws2)
    wb.save(path)
    return df


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", required=True, action="append",
                    help="Ordner mit den Konfigurationsordnern (115 und 70BG); mehrfach angebbar")
    ap.add_argument("--gt", required=True, help="R1.md oder Excel mit der Ground Truth")
    ap.add_argument("--gt-name", default="R1")
    ap.add_argument("--sheet", default="Sheet1")
    ap.add_argument("--out", default="Ergebnis_R1")
    a = ap.parse_args(argv)

    gt, pe, gt_issues = load_gt(a.gt)
    for i in gt_issues:
        print("! " + i)
    print(f"GT {a.gt_name}: {len(gt)} BG, davon Prompt-Engineering {len(pe)}; "
          f"mehrdeutig (ohne PE): {sum(len(v[1]) > 1 for k, v in gt.items() if k not in pe)}")
    issues = []
    data, info = collect(a.dir, a.sheet, gt, pe, issues)
    rng = np.random.default_rng(SEED)
    results = {}
    for m in [x for x in MODEL_ORDER if x in data] + [x for x in data if x not in MODEL_ORDER]:
        rm, rs = data[m]["main"], data[m]["supp"]
        print(f"\n{m}: {len(rm)} Läufe 115 BG, {len(rs)} Läufe 70 BG")
        for name, rr, exp in (("115", rm, 115), ("70", rs, 70)):
            for f, run in rr:
                if len(run) != exp:
                    print(f"  ! {name}: {f.name[-45:]} hat {len(run)} gewertete BG (erwartet {exp})")
        if rs and len(rs) != len(rm):
            print(f"  ! unterschiedliche Laufzahl (115: {len(rm)}, 70: {len(rs)}) – für 185 werden {min(len(rm), len(rs))} Paare genutzt")
        results[m] = {"115": evaluate(gt, rm, rs, "115", np.random.default_rng(SEED)) if rm else None,
                      "185": evaluate(gt, rm, rs, "185", np.random.default_rng(SEED)) if rm and rs else None}
        for scope in ("185", "115"):
            res = results[m][scope]
            if res:
                x = res["alle"]
                print(f"  {scope} BG: Accuracy {x['acc']*100:.1f} % (SD {x['sd']:.2f} pp, KI {x['ci_lo']*100:.1f}–{x['ci_hi']*100:.1f}), "
                      f"eindeutig {res['eindeutig']['acc']*100:.1f} %, mehrdeutig {res['mehrdeutig']['acc']*100:.1f} %, "
                      f"Macro-F1 eindeutig {res['eindeutig']['f1']*100:.1f} %")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    xlsx = out / f"Wiederhollaeufe_{a.gt_name}.xlsx"
    write_excel(xlsx, results, a.gt_name)
    from openpyxl import load_workbook
    wb = load_workbook(xlsx)
    short = {"Gemini 2.5 Pro": "Pro", "Gemini 2.5 Flash": "Flash", "Claude Haiku 4.5": "Haiku",
             "GPT-5.5": "GPT", "DeepSeek-V4-Flash": "DeepSeek"}
    for m in results:
        for scope in ("185", "115"):
            runs = build_runs(data[m]["main"], data[m]["supp"], scope)
            if not runs or (scope == "185" and not data[m]["supp"]):
                continue
            write_confusion_sheet(wb, f"{m} – {scope} Baugruppen, {len(runs)} Läufe, GT {a.gt_name}",
                                  f"KM_{short.get(m, m)}_{scope}", gt, runs)
    wb.save(xlsx)
    print(f"\nAusgabe: {xlsx}")
    shown = [i for i in issues if not i["Typ"].startswith("Info:") and "Register" not in i["Typ"]
             and "Allowed_Set_Status" not in i["Typ"]]
    if shown:
        print("Hinweise:")
        groups = {}
        for i in shown:
            groups.setdefault((i["Typ"], i.get("SAP"), i.get("Detail")), []).append(i.get("Modell"))
        for (typ, sap, det), who in groups.items():
            print("   - " + " | ".join(str(x) for x in [typ, sap, det, f"{len(who)} Dateien"] if x))
    return results


if __name__ == "__main__":
    main()
