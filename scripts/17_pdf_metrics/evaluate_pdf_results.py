"""Metriktabellen und Konfusionsmatrizen für die PDF-Ergebnisdateien (vier Modelle, ein Lauf, 115 BG).

Offline, keine Modellaufrufe. GT, Register und weitere zulässige Labels kommen aus Blatt "Sheet1"
der jeweiligen Ergebnisdatei (nicht aus FINAL_GT); FINAL_GT aus Skript 12 dient nur zur Kontrolle.

Blatt 1 "Metriken_2x2"  : je Modell eine Tabelle (Zeilen = Metriken, Spalten = E1, E2, M, E1+E2, Total)
                          - Allowed Acc.        Vorhersage in {GT} ∪ weitere zulässige
                          - Strict Macro-F1     nur Primärlabel; Mittel über Klassen in GT ∪ Vorhersage
                          - Allowed Macro-Prec. Formel 5.2a; Mittel über vorhergesagte Klassen
                          - Allowed Macro-Rec.  Formel 5.2b; Mittel über Klassen in der GT
                          (dieselbe Klassenauswahl wie Skript 09, damit die Zahlen zu Tabelle 5.5 passen)
Blatt 2 "Konfusion_2x2" : Konfusionsmatrizen im Stil von Abbildung 5.x (Diagonale blau, links rot =
                          nicht zulässig, rechts grün = weiteres zulässiges Label), zusätzlich als PNG.
Hinweise (Status-Abgleich, Label, Register) erscheinen in der Konsole.
Mit --nur-sheet1 werden in den Ergebnisdateien danach alle Blätter außer Sheet1 gelöscht
(Sicherungskopie in <out>/Backup_Original).

Regime: M mit nur einem zulässigen Label (z. B. 0804EN7325) zählt als E2, wie in der Arbeit.

Aufruf (PowerShell):
    python evaluate_pdf_results.py "...\\haiku.xlsx" "...\\opus.xlsx" "...\\flash.xlsx" "...\\pro.xlsx" `
        --out PDF_Metriken
    python evaluate_pdf_results.py --dir "...\\PDF_Ordner" --out PDF_Metriken
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "13_confusion_human_llm"))
import confusion_human_llm as cm  # noqa: E402  (canon, Klassen, Farben, Matrix-Zeichnung)

ev = cm.ev
canon = cm.canon
is_empty = ev.is_empty
find_col = ev.find_col
CLASSES, CODES, IDX, K = cm.CLASSES, cm.CODES, cm.IDX, len(cm.CLASSES)

# ---------------------------------------------------------------- Modelle (Dateiname -> Anzeigename)
# Reihenfolge = Position im 2×2-Raster (zeilenweise): oben Haiku | Gemini Pro, unten Opus | Gemini Flash
MODELS = [
    ("haiku", "Claude Haiku 4.5"),
    ("gemini-2.5-pro", "Gemini 2.5 Pro"),
    ("opus", "Claude Opus 4.8"),
    ("gemini-2.5-flash", "Gemini 2.5 Flash"),
    ("gpt", "GPT-5.5"),
    ("deepseek", "DeepSeek-V4-Flash"),
]


def model_name(path):
    s = re.sub(r"[\s_]+", "-", Path(path).name.lower())
    if "deepseek" in s:
        return "DeepSeek-V4-Flash"
    for key, name in MODELS:
        if key in s:
            return name
    if "gemini" in s and "flash" in s:
        return "Gemini 2.5 Flash"
    if "gemini" in s and "pro" in s:
        return "Gemini 2.5 Pro"
    return Path(path).stem


def model_rank(name):
    names = [n for _, n in MODELS]
    return names.index(name) if name in names else len(names)


# ---------------------------------------------------------------- Einlesen
SUBSETS = ["E1", "E2", "M", "E", "Total"]
SUBSET_HEAD = {"E1": "E1", "E2": "E2", "M": "M", "E": "E (E1+E2)", "Total": "Total"}


def split_alts(x):
    if is_empty(x):
        return []
    return [a.strip() for a in re.split(r"[,;\n|]", str(x)) if a.strip() and not is_empty(a)]


def read_file(path, sheet, model, issues):
    path = Path(path)
    xl = pd.ExcelFile(path)
    sh = sheet if sheet in xl.sheet_names else xl.sheet_names[0]
    if sh != sheet:
        issues.append(dict(Modell=model, Typ=f"Blatt '{sheet}' fehlt, erstes Blatt verwendet", Detail=sh))
    df = pd.read_excel(path, sheet_name=sh, dtype=str)
    cols = list(df.columns)
    c = dict(
        sap=find_col(cols, contains=["sap"]),
        tc=find_col(cols, contains=["teamcenter"]),
        gt=find_col(cols, exact="Ground Truth"),
        alt=find_col(cols, contains=["weitere"]),
        reg=find_col(cols, exact="Register") or find_col(cols, contains=["regist"]),
        pred=find_col(cols, contains=["predicted"]),
        stat=find_col(cols, contains=["allowed", "status"]),
        pe=find_col(cols, contains=["prompt", "engineer"]),
    )
    if not (c["sap"] and c["gt"] and c["pred"]):
        sys.exit(f"Spalten SAP / Ground Truth / Predicted_Label nicht gefunden in {path.name}: {cols}")
    if c["reg"] is None:
        issues.append(dict(Modell=model, Typ="Spalte Register fehlt: Regime aus FINAL_GT"))
    if c["stat"] is None:
        issues.append(dict(Modell=model, Typ="Spalte Allowed_Set_Status fehlt: kein Abgleich möglich"))

    recs, seen = [], set()
    for i, row in df.iterrows():
        xrow = i + 2
        if is_empty(row[c["gt"]]):
            continue
        if c["pe"] and not is_empty(row[c["pe"]]) and str(row[c["pe"]]).strip().lower() == "yes":
            issues.append(dict(Modell=model, Typ="prompt_engineering = yes (Vorversuch, ignoriert)", Zeile=xrow))
            continue
        sap_raw = row[c["sap"]]
        tc_raw = row[c["tc"]] if c["tc"] else None
        key = cm.match_key(sap_raw, tc_raw)
        sap = key or ("" if is_empty(sap_raw) else str(sap_raw).strip())
        if sap in seen:
            issues.append(dict(Modell=model, Typ="Doppelte Baugruppe (zweite Zeile ignoriert)", Zeile=xrow, SAP=sap))
            continue
        seen.add(sap)

        gt_raw = str(row[c["gt"]]).strip()
        gt = canon(gt_raw)
        alts_raw = split_alts(row[c["alt"]]) if c["alt"] else []
        alts = [canon(a) for a in alts_raw]
        for raw, lab in [(gt_raw, gt)] + list(zip(alts_raw, alts)):
            if lab is None or lab.startswith("UNGÜLTIG"):
                issues.append(dict(Modell=model, Typ="GT-Label nicht erkannt", Zeile=xrow, SAP=sap, Detail=raw))
        if gt is None or gt.startswith("UNGÜLTIG"):
            continue
        alts = [a for a in alts if a and not a.startswith("UNGÜLTIG") and a != gt]
        allowed = frozenset([gt] + alts)

        reg_raw = "" if c["reg"] is None or is_empty(row[c["reg"]]) else str(row[c["reg"]]).strip().upper()
        if not reg_raw and key:
            reg_raw = cm.FINAL_GT[key][1]
        reg = ev.regime(allowed, reg_raw)
        if reg_raw == "M" and reg == "E2":
            issues.append(dict(Modell=model, Typ="Register M ohne weiteres zulässiges Label -> als E2 gewertet",
                               Zeile=xrow, SAP=sap))
        if reg_raw in ("E1", "E2") and len(allowed) > 1:
            issues.append(dict(Modell=model, Typ=f"Register {reg_raw}, aber weitere zulässige Labels -> als M gewertet",
                               Zeile=xrow, SAP=sap, Detail=", ".join(alts)))
        if reg == "?":
            issues.append(dict(Modell=model, Typ="Register unbekannt (nur in Total)", Zeile=xrow, SAP=sap,
                               Detail=reg_raw))

        pred_raw = "" if is_empty(row[c["pred"]]) else str(row[c["pred"]]).strip()
        pred = canon(pred_raw) if pred_raw else None
        if pred is None:
            issues.append(dict(Modell=model, Typ="Leere Vorhersage (nicht gewertet)", Zeile=xrow, SAP=sap))
            continue
        valid_label = not pred.startswith("UNGÜLTIG")
        if not valid_label:
            issues.append(dict(Modell=model, Typ="Vorhersage nicht erkannt (als falsch gewertet, nicht in Matrix)",
                               Zeile=xrow, SAP=sap, Detail=pred_raw))
        hit = valid_label and pred in allowed

        stat = "" if c["stat"] is None or is_empty(row[c["stat"]]) else str(row[c["stat"]]).strip().upper()
        if stat:
            file_ok = stat.startswith("CORRECT")
            if file_ok != hit:
                issues.append(dict(Modell=model, Typ="Allowed_Set_Status weicht ab", Zeile=xrow, SAP=sap,
                                   Detail=f"Datei: {stat} | neu: {'CORRECT' if hit else 'INCORRECT'} | "
                                          f"GT {gt} | zulässig {', '.join(alts) or '—'} | Vorhersage {pred_raw}"))

        if key and not key.startswith("TC:"):
            fgt, freg, falts = cm.FINAL_GT[key]
            fallowed = frozenset([canon(fgt)] + [canon(a) for a in falts])
            if canon(fgt) != gt or fallowed != allowed:
                issues.append(dict(Modell=model, Typ="Info: GT der Datei weicht von FINAL_GT (Skript 12) ab",
                                   Zeile=xrow, SAP=sap,
                                   Detail=f"Datei: {gt} | {', '.join(alts) or '—'}  /  FINAL_GT: {fgt} | "
                                          f"{', '.join(falts) or '—'}"))
        elif not key:
            issues.append(dict(Modell=model, Typ="Info: SAP nicht in FINAL_GT", Zeile=xrow, SAP=sap))

        recs.append(dict(Modell=model, Zeile=xrow, SAP=sap, gt=gt, allowed=allowed, alts=alts,
                         register_datei=reg_raw, regime=reg, pred=pred if valid_label else None,
                         pred_raw=pred_raw, hit=hit, strict=valid_label and pred == gt, status_datei=stat))
    return recs


# ---------------------------------------------------------------- Metriken
def metrics(recs):
    """Wie Skript 09: P über vorhergesagte Klassen, R über GT-Klassen, Strict-F1 über GT ∪ Vorhersage."""
    n = len(recs)
    if n == 0:
        return dict(n=0, acc=np.nan, f1=np.nan, prec=np.nan, rec=np.nan)
    gtc, pc, tp, ap, ar = (np.zeros(K) for _ in range(5))
    for r in recs:
        g = IDX[r["gt"]]
        gtc[g] += 1
        if r["hit"]:
            ar[g] += 1
        if r["pred"] is not None:
            p = IDX[r["pred"]]
            pc[p] += 1
            if r["pred"] in r["allowed"]:
                ap[p] += 1
            if p == g:
                tp[p] += 1
    with np.errstate(divide="ignore", invalid="ignore"):
        P = np.where(pc > 0, ap / pc, np.nan)
        R = np.where(gtc > 0, ar / gtc, np.nan)
        F = np.where(gtc + pc > 0, 2 * tp / (gtc + pc), np.nan)
    return dict(n=n, acc=sum(r["hit"] for r in recs) / n,
                f1=np.nanmean(F), prec=np.nanmean(P), rec=np.nanmean(R))


def subset(recs, s):
    if s == "Total":
        return recs
    if s == "E":
        return [r for r in recs if r["regime"] in ("E1", "E2")]
    return [r for r in recs if r["regime"] == s]


METRIC_ROWS = [("acc", "Allowed Acc."), ("f1", "Strict Macro-F1"),
               ("prec", "Allowed Macro-Prec."), ("rec", "Allowed Macro-Rec.")]


# ---------------------------------------------------------------- Excel-Formatierung
def _xl(c):
    return c.lstrip("#").upper()


def styles():
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    thin = Side(style="thin", color=_xl(cm.GRID))
    S = dict(
        fill=lambda c: PatternFill("solid", fgColor=_xl(c)),
        border=Border(left=thin, right=thin, top=thin, bottom=thin),
        center=Alignment(horizontal="center", vertical="center"),
        right=Alignment(horizontal="right", vertical="center", indent=1),
        left=Alignment(horizontal="left", vertical="center", indent=1),
        Font=Font,
    )
    return S


ACC_ROW_BG = "#DCE6F1"
ODD_ROW_BG = "#F2F5F9"


def write_metric_sheet(wb, results, subtitle):
    from openpyxl.utils import get_column_letter
    S = styles()
    Font = S["Font"]
    ws = wb.create_sheet("Metriken_2x2")
    ws.sheet_view.showGridLines = False
    ncol, nrow, gapc, gapr = 6, 6, 1, 2
    ws.column_dimensions["A"].width = 2
    for k, (name, recs) in enumerate(results):
        r0 = 2 + (k // 2) * (nrow + gapr)
        c0 = 2 + (k % 2) * (ncol + gapc)
        subs = {s: subset(recs, s) for s in SUBSETS}
        mets = {s: metrics(subs[s]) for s in SUBSETS}
        # Titel
        ws.merge_cells(start_row=r0, start_column=c0, end_row=r0, end_column=c0 + ncol - 1)
        t = ws.cell(r0, c0, f"{name} ({subtitle})")
        t.font = Font(bold=True, color="FFFFFF", size=12)
        t.alignment = S["center"]
        for j in range(ncol):
            ws.cell(r0, c0 + j).fill = S["fill"](cm.NAVY)
        ws.row_dimensions[r0].height = 22
        # Kopf
        heads = ["Metrik"] + [f"{SUBSET_HEAD[s]} (n={mets[s]['n']})" for s in SUBSETS]
        for j, h in enumerate(heads):
            cell = ws.cell(r0 + 1, c0 + j, h)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = S["fill"](cm.HEAD)
            cell.alignment = S["left"] if j == 0 else S["center"]
            cell.border = S["border"]
        # Werte
        for i, (key, label) in enumerate(METRIC_ROWS):
            rr = r0 + 2 + i
            bg = ACC_ROW_BG if key == "acc" else (ODD_ROW_BG if i % 2 else "#FFFFFF")
            cell = ws.cell(rr, c0, label)
            cell.font = Font(bold=key == "acc", color=_xl(cm.DARK_TXT) if key == "acc" else "000000")
            cell.fill = S["fill"](bg)
            cell.alignment = S["left"]
            cell.border = S["border"]
            for j, s in enumerate(SUBSETS):
                v = mets[s][key]
                cell = ws.cell(rr, c0 + 1 + j, None if np.isnan(v) else float(v))
                cell.number_format = "0.0%"
                cell.font = Font(bold=key == "acc" or s == "Total")
                cell.fill = S["fill"](bg)
                cell.alignment = S["right"]
                cell.border = S["border"]
    for k in range(2):
        c0 = 2 + k * (ncol + gapc)
        ws.column_dimensions[get_column_letter(c0)].width = 21
        for j in range(1, ncol):
            ws.column_dimensions[get_column_letter(c0 + j)].width = 17
        ws.column_dimensions[get_column_letter(c0 + ncol)].width = 3
    note_r = 2 + ((len(results) + 1) // 2) * (nrow + gapr) - 1
    notes = [
        "Allowed Acc.: Vorhersage im zulässigen Label-Set ({GT} ∪ weitere zulässige).",
        "Strict Macro-F1: nur das Primärlabel zählt; Mittel der Klassen-F1 über Klassen, die in GT oder Vorhersage vorkommen.",
        "Allowed Macro-Prec./-Rec.: Formel 5.2a/5.2b; Precision gemittelt über vorhergesagte Klassen, Recall über Klassen der GT.",
        "Strict Macro-F1 ist daher nicht das harmonische Mittel der beiden Allowed-Werte darüber.",
        "Regime: M ohne weiteres zulässiges Label zählt als E2. GT, Register und zulässige Labels aus Sheet1 der jeweiligen Datei.",
    ]
    for i, txt in enumerate(notes):
        ws.cell(note_r + i, 2, txt).font = Font(italic=True, size=9, color="595959")
    ws.freeze_panes = None


def matrix_for(recs):
    return cm.build_matrix([r for r in recs if r["pred"] is not None])


def write_confusion_sheet(wb, mats, lang):
    """Native Excel-Darstellung: je Klasse zwei Spalten (links rot, rechts grün); Diagonale verbunden blau."""
    from openpyxl.utils import get_column_letter
    S = styles()
    Font = S["Font"]
    ws = wb.create_sheet("Konfusion_2x2")
    ws.sheet_view.showGridLines = False
    ncol = 1 + 2 * K
    nrow = 2 + K
    gapc, gapr = 1, 2
    ws.column_dimensions["A"].width = 2

    def put(r, c, v, bg="#FFFFFF", color="000000", bold=False, span=1, size=11):
        if span > 1:
            ws.merge_cells(start_row=r, start_column=c, end_row=r, end_column=c + span - 1)
        cell = ws.cell(r, c, v)
        cell.font = Font(bold=bold, color=_xl(color), size=size)
        cell.alignment = S["center"]
        for j in range(span):
            x = ws.cell(r, c + j)
            x.fill = S["fill"](bg)
            x.border = S["border"]

    for k, (title, m) in enumerate(mats):
        r0 = 2 + (k // 2) * (nrow + gapr)
        c0 = 2 + (k % 2) * (ncol + gapc)
        put(r0, c0, title, cm.NAVY, "#FFFFFF", True, span=ncol, size=12)
        ws.row_dimensions[r0].height = 22
        put(r0 + 1, c0, cm.TXT_HEAD, cm.HEAD, "#FFFFFF", True, size=9)
        for j, code in enumerate(CODES):
            put(r0 + 1, c0 + 1 + 2 * j, code, cm.HEAD, "#FFFFFF", True, span=2)
        for i, code in enumerate(CODES):
            rr = r0 + 2 + i
            put(rr, c0, code, cm.ROWLAB_BG, cm.DARK_TXT, True)
            for j in range(K):
                cc = c0 + 1 + 2 * j
                parts = cm.cell_spec(m, i, j)
                if parts[0][0] == "full":
                    _, bg, n, col, bold = parts[0]
                    put(rr, cc, n, bg, col, bold, span=2)
                else:
                    for off, (_, bg, n, col, bold) in enumerate(parts):
                        put(rr, cc + off, n, bg, col, bold)
        for j in range(ncol):
            ws.column_dimensions[get_column_letter(c0 + j)].width = 9 if j == 0 else 4.2
        ws.column_dimensions[get_column_letter(c0 + ncol)].width = 3
    # Legende
    t = cm.TXT[lang]
    lr = 2 + ((len(mats) + 1) // 2) * (nrow + gapr) - 1
    for i, (bg, lab) in enumerate([(cm.BLUE_BG, t["diag"]), (cm.RED_BG, t["red"]), (cm.GREEN_BG, t["green"])]):
        c = 2 + i * 5
        ws.cell(lr, c).fill = S["fill"](bg)
        ws.cell(lr, c).border = S["border"]
        ws.cell(lr, c + 1, lab).font = Font(size=10)
    ws.cell(lr + 1, 2, cm.codes_line(lang)).font = Font(size=10)


def save_png(mats, path, lang, hf=0.7):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rows = (len(mats) + 1) // 2
    fig = plt.figure(figsize=(11, 4.2 * hf * rows + 1.0))
    gs = fig.add_gridspec(rows + 1, 2, height_ratios=[4.2 * hf] * rows + [1.0], hspace=0.08, wspace=0.05)
    for k, (title, m) in enumerate(mats):
        cm.draw_matrix(fig.add_subplot(gs[k // 2, k % 2]), m, title, fs=0.92)
    cm.draw_legend(fig.add_subplot(gs[rows, :]), lang, fs=1.2)
    fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def autosize(ws, maxw=80):
    from openpyxl.utils import get_column_letter
    for col in ws.columns:
        w = max((len(str(c.value)) for c in col if c.value is not None), default=8)
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(maxw, max(8, w + 2))


# ---------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", help="Ergebnisdateien (.xlsx)")
    ap.add_argument("--dir", help="Ordner mit Ergebnisdateien (alle .xlsx, ohne ~$-Dateien)")
    ap.add_argument("--sheet", default="Sheet1")
    ap.add_argument("--out", default="PDF_Metriken", help="Ausgabeordner")
    ap.add_argument("--subtitle", default="115BG, P3, PDF", help="Zusatz im Titel der Metriktabellen")
    ap.add_argument("--input-label", default="PDF", help="Eingabeform im Titel der Matrizen")
    ap.add_argument("--lang", choices=["en", "de"], default="en", help="Sprache der Legende")
    ap.add_argument("--height", type=float, default=0.7, help="Höhenfaktor der PNG-Matrizen")
    ap.add_argument("--no-png", action="store_true")
    ap.add_argument("--nur-sheet1", action="store_true",
                    help="nach der Auswertung in den Ergebnisdateien alle Blätter außer --sheet löschen "
                         "(Sicherung in <out>/Backup_Original)")
    a = ap.parse_args(argv)

    files = [Path(f) for f in a.files]
    if a.dir:
        files += sorted(p for p in Path(a.dir).glob("*.xlsx") if not p.name.startswith("~$"))
    if not files:
        ap.error("keine Dateien angegeben (Dateien oder --dir)")

    issues, results = [], []
    for f in files:
        if not f.is_file():
            sys.exit(f"Datei nicht gefunden: {f}")
        name = model_name(f)
        if any(name == n for n, _ in results):
            sys.exit(f"Modell '{name}' doppelt erkannt ({f.name}). Dateinamen prüfen.")
        recs = read_file(f, a.sheet, name, issues)
        issues.insert(0, dict(Modell=name, Typ="Datei", Detail=str(f)))
        results.append((name, recs))
    results.sort(key=lambda x: model_rank(x[0]))

    from openpyxl import Workbook
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    wb.remove(wb.active)
    write_metric_sheet(wb, results, a.subtitle)
    mats = []
    for name, recs in results:
        m = matrix_for(recs)
        mats.append((f"{name} ({a.input_label}), n = {m['n']}", m))
    write_confusion_sheet(wb, mats, a.lang)

    xlsx = out / "PDF_Metriken_Konfusion.xlsx"
    wb.save(xlsx)
    if not a.no_png:
        save_png(mats, out / "konfusion_2x2.png", a.lang, a.height)

    # Konsole
    print(f"Ausgabe: {xlsx}")
    for name, recs in results:
        tot = metrics(recs)
        ns = " / ".join(str(len(subset(recs, s))) for s in ["E1", "E2", "M"])
        print(f"  {name:<20} n={tot['n']:>3} (E1/E2/M {ns})  Allowed Acc {tot['acc']*100:5.1f}%  "
              f"Strict Macro-F1 {tot['f1']*100:5.1f}%")
    shown = [i for i in issues if i["Typ"] != "Datei" and not i["Typ"].startswith("Info:")]
    dev = [i for i in shown if i["Typ"] == "Allowed_Set_Status weicht ab"]
    print(f"  Abweichungen Allowed_Set_Status: {len(dev)}")
    if shown:
        print("  Hinweise:")
        for i in shown:
            parts = [i.get("Modell"), i["Typ"]]
            parts += [f"Zeile {i['Zeile']}" if i.get("Zeile") else None, i.get("SAP"), i.get("Detail")]
            print("   - " + " | ".join(str(x) for x in parts if x))
    global LAST_ISSUES
    LAST_ISSUES = issues

    if a.nur_sheet1:
        keep_only_sheet(files, a.sheet, out)
    return results


def keep_only_sheet(files, sheet, out):
    """Löscht in den Ergebnisdateien alle Blätter außer `sheet`. Vorher Sicherungskopie in <out>/Backup_Original."""
    import shutil
    from openpyxl import load_workbook
    backup = out / "Backup_Original"
    backup.mkdir(parents=True, exist_ok=True)
    print(f"Nur '{sheet}' behalten (Sicherung in {backup}):")
    for f in files:
        try:
            wb = load_workbook(f)
        except PermissionError:
            print(f"  ! {f.name}: Datei ist geöffnet oder gesperrt, übersprungen")
            continue
        if sheet not in wb.sheetnames:
            print(f"  ! {f.name}: Blatt '{sheet}' fehlt, nichts gelöscht")
            continue
        others = [n for n in wb.sheetnames if n != sheet]
        if not others:
            print(f"  {f.name}: nur '{sheet}' vorhanden")
            continue
        shutil.copy2(f, backup / f.name)
        for n in others:
            del wb[n]
        wb.active = 0
        try:
            wb.save(f)
            print(f"  {f.name}: gelöscht {', '.join(others)}")
        except PermissionError:
            print(f"  ! {f.name}: Speichern nicht möglich (Datei in Excel geöffnet?)")


LAST_ISSUES = []


if __name__ == "__main__":
    main()
