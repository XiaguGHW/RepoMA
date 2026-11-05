#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_allowed_and_confusion_matrix.py

1) Prüft je Ergebnisdatei, ob die Spalte "Allowed_Set_Status" stimmt
   (Vorhersage ∈ {Ground Truth} ∪ {Weitere zulässige Ground Truth}, inkl. Synonyme laut Codebook).
2) Erstellt für jede Datei ohne Abweichungen eine Konfusionsmatrix
   (Zeilen = Ground Truth / Primärlabel, Spalten = Vorhersage, Klassen A–G)
   im Blau-Layout der bisherigen Auswertungstabellen.

Aufruf (keine Modellaufrufe, rein offline):
    python check_allowed_and_confusion_matrix.py                 # alle .xlsx unterhalb des Skriptordners
    python check_allowed_and_confusion_matrix.py <Ordner|Datei> ...
    python check_allowed_and_confusion_matrix.py --force ...     # Matrix auch bei Abweichungen erzeugen

Ausgabe (im aktuellen Arbeitsordner):
    Konfusionsmatrizen.xlsx  – Blätter "Pruefung", "Abweichungen", "Konfusionsmatrizen", "Legende"
    konfusionsmatrizen_png/  – je Matrix ein PNG (falls matplotlib installiert ist)

Benötigt: pandas, numpy, openpyxl (optional: matplotlib)
"""

import argparse
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------------
# Einstellungen
# ----------------------------------------------------------------------------
SHEET_NAME = "Sheet1"
OUTPUT_XLSX = "Konfusionsmatrizen.xlsx"
OUTPUT_PNG_DIR = "konfusionsmatrizen_png"
MATRICES_PER_ROW = 2

# Zeilen mit prompt_engineering = yes (Prompt-Entwicklungsset) nicht auswerten
EXCLUDE_PROMPT_ENGINEERING = True
PE_YES = {"yes", "ja", "y", "x", "1", "true", "wahr"}

SKIP_PREFIX = ("~$", "PPT_", "Evaluation_Summary", "Evaluation_Allowed_Strict", "Konfusionsmatrizen")

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
# Kurznamen für die Legende unter den Matrizen
LEGEND_NAMES = ["Lineareinheit", "Greifer", "Roboter", "Rotationseinheit", "Gantry",
                "Kombinierte Einheit", "Keine der verfügbaren Klassen"]
LEGEND_TEXT = "Klassencode: " + " | ".join(f"{c} = {n}" for c, n in zip(CODES, LEGEND_NAMES))
K = len(CLASSES)

# Synonyme laut Codebook (Schlüssel in Kleinbuchstaben)
SYNONYMS = {
    "gantry": "Multi-Achs-System (Gantry)",
    "umsetzeinheit": "Kombinierte Einheit",
    "keine der verfgbaren klassen": "Keine der verfügbaren Klassen",
}

MODEL_NAMES = {
    "claude-haiku-4-5": "Claude Haiku 4.5",
    "claude_haiku": "Claude Haiku 4.5",
    "gemini-2.5-pro": "Gemini 2.5 Pro",
    "gemini-2.5-flash": "Gemini 2.5 Flash",
    "gpt-5.5": "GPT 5.5",
    "gpt-5-5": "GPT 5.5",
    "deepseek-v4-flash": "DeepSeek V4 Flash",
}
INPUT_NAMES = {"pdf": "PDF", "image": "Bild", "bild": "Bild", "text": "Text"}

# Farben (wie bisherige Tabellen)
NAVY, BLUE = "1F3864", "2F5597"
DIAG_FILL, ERR_FILL = "DCE6F1", "F8DCDC"
ERR_FONT, ZERO_FONT = "C00000", "A6A6A6"


# ----------------------------------------------------------------------------
# Hilfsfunktionen
# ----------------------------------------------------------------------------
def _norm(s):
    s = unicodedata.normalize("NFC", str(s)).replace(" ", " ")
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
    return K


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


def describe(path):
    """Titel 'Modell (nBG, Prompt, Eingabe)' aus Datei- und Ordnernamen."""
    text = (str(path.parent.name) + " " + path.name).lower()
    model = next((v for k, v in MODEL_NAMES.items() if k in text), None)
    if model is None:
        m = re.search(r"P\d+_(.+?)_(?:caching|\d{4}-\d{2}-\d{2})", path.name)
        model = m.group(1) if m else path.stem
    prompt = re.search(r"(?:^|[_\-])(P\d+)(?:[_\-]|$)", path.name + "_" + path.parent.name)
    prompt = prompt.group(1) if prompt else "?"
    inp = next((v for k, v in INPUT_NAMES.items() if re.search(rf"(^|[_\-]){k}([_\-]|$)", text.replace(" ", "_"))), "?")
    return model, prompt, inp


def collect_files(args):
    targets = [Path(a) for a in args] or [Path(__file__).resolve().parent]
    files = []
    for t in targets:
        if t.is_file() and t.suffix.lower() == ".xlsx":
            files.append(t)
        elif t.is_dir():
            files += sorted(p for p in t.rglob("*.xlsx"))
    return [f for f in dict.fromkeys(files) if not f.name.startswith(SKIP_PREFIX)]


# ----------------------------------------------------------------------------
# Prüfung und Matrix je Datei
# ----------------------------------------------------------------------------
def process(path):
    df = pd.read_excel(path, sheet_name=SHEET_NAME, dtype=str)
    cols = list(df.columns)
    c_sap = find_col(cols, contains=["sap"])
    c_gt = find_col(cols, exact="Ground Truth")
    c_alt = find_col(cols, contains=["weitere"])
    c_pred = find_col(cols, contains=["predicted"])
    c_stat = find_col(cols, contains=["allowed"])
    c_pe = find_col(cols, contains=["prompt_engineer"])
    if not (c_gt and c_pred and c_stat):
        raise ValueError(f"Spalten nicht gefunden: {cols}")

    cm = np.zeros((K, K), int)
    issues = []
    n_rows = n_pe = n_excl = n_eval = n_alt_hit = 0
    for i, row in df.iterrows():
        if is_empty(row[c_gt]):
            continue
        n_rows += 1
        sap = "" if c_sap is None or is_empty(row[c_sap]) else str(row[c_sap]).strip()
        excel_row = i + 2
        if EXCLUDE_PROMPT_ENGINEERING and c_pe is not None and not is_empty(row[c_pe]) \
                and _norm(row[c_pe]) in PE_YES:
            n_pe += 1
            continue

        gt = label_index(row[c_gt])
        alt_raw = "" if c_alt is None or is_empty(row[c_alt]) else str(row[c_alt])
        alts = [label_index(a) for a in alt_raw.split(",") if a.strip()]
        pred = label_index(row[c_pred])
        status = "" if is_empty(row[c_stat]) else str(row[c_stat]).strip().upper()

        def issue(typ, expected=""):
            issues.append({"Datei": path.name, "Excel-Zeile": excel_row, "SAP-Nummer": sap, "Typ": typ,
                           "Ground Truth": row[c_gt], "Weitere zulässige GT": alt_raw,
                           "Predicted_Label": "" if is_empty(row[c_pred]) else row[c_pred],
                           "Status in Datei": status, "Status erwartet": expected})

        if gt == K or K in alts:
            issue("GT/ZGT nicht zuordenbar")
            continue
        if pred is None:
            if status != "EXCLUDED":
                issue("Leere Vorhersage, Status nicht EXCLUDED", "EXCLUDED")
            n_excl += 1
            continue
        if pred == K:
            issue("Vorhersage nicht zuordenbar (als falsch gewertet)", "INCORRECT")

        allowed = {gt} | {a for a in alts if a is not None and a != K}
        expected = "CORRECT" if pred in allowed else "INCORRECT"
        if status != expected:
            issue("Abweichung Allowed_Set_Status", expected)

        n_eval += 1
        if pred != K:
            cm[gt, pred] += 1
            if pred != gt and pred in allowed:
                n_alt_hit += 1

    model, prompt, inp = describe(path)
    acc_allowed = (np.trace(cm) + n_alt_hit) / n_eval if n_eval else np.nan
    acc_strict = np.trace(cm) / n_eval if n_eval else np.nan
    summary = {"Datei": path.name, "Ordner": path.parent.name, "Modell": model, "Prompt": prompt, "Eingabe": inp,
               "Zeilen": n_rows, "prompt_engineering (ausgeschl.)": n_pe, "EXCLUDED": n_excl,
               "Ausgewertet": n_eval, "Abweichungen": len(issues),
               "Allowed Accuracy": acc_allowed, "Strict Accuracy": acc_strict,
               "Prüfung": "OK" if not issues else "Abweichungen"}
    title = f"{model} ({n_eval}BG, {prompt}, {inp})"
    return summary, issues, cm, title


# ----------------------------------------------------------------------------
# Ausgabe Excel
# ----------------------------------------------------------------------------
def write_matrix(ws, top, left, title, cm):
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    white = Side(style="thin", color="FFFFFF")
    grid = Side(style="thin", color="E3E3E3")
    center = Alignment(horizontal="center", vertical="center")

    ws.merge_cells(start_row=top, start_column=left, end_row=top, end_column=left + K)
    c = ws.cell(row=top, column=left, value=title)
    c.font = Font(name="Calibri", size=12, bold=True, color="FFFFFF")
    c.fill = PatternFill("solid", fgColor=NAVY)
    c.alignment = center
    ws.row_dimensions[top].height = 24

    hdr = ["GT \\ Pred"] + CODES
    for j, h in enumerate(hdr):
        cell = ws.cell(row=top + 1, column=left + j, value=h)
        cell.font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=BLUE)
        cell.alignment = center
        cell.border = Border(left=white, right=white, top=white, bottom=white)

    for i in range(K):
        r = top + 2 + i
        lab = ws.cell(row=r, column=left, value=CODES[i])
        lab.font = Font(name="Calibri", size=11, bold=True)
        lab.alignment = center
        lab.border = Border(bottom=grid)
        for j in range(K):
            v = int(cm[i, j])
            cell = ws.cell(row=r, column=left + 1 + j, value=v)
            cell.alignment = center
            cell.border = Border(left=grid, right=grid, top=grid, bottom=grid)
            if i == j:
                cell.fill = PatternFill("solid", fgColor=DIAG_FILL)
                cell.font = Font(name="Calibri", size=11, bold=True)
            elif v > 0:
                cell.fill = PatternFill("solid", fgColor=ERR_FILL)
                cell.font = Font(name="Calibri", size=11, bold=True, color=ERR_FONT)
            else:
                cell.font = Font(name="Calibri", size=11, color=ZERO_FONT)


def style_table(ws, df, title):
    from openpyxl.styles import Alignment, Font, PatternFill

    ws.cell(row=1, column=1, value=title).font = Font(name="Calibri", size=13, bold=True, color="FFFFFF")
    ws.cell(row=1, column=1).fill = PatternFill("solid", fgColor=NAVY)
    if df.shape[1] > 1:
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=df.shape[1])
    for j, col in enumerate(df.columns, 1):
        h = ws.cell(row=2, column=j)
        h.font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        h.fill = PatternFill("solid", fgColor=BLUE)
        h.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        width = max([len(str(col))] + [len(str(v)) for v in df[col].tolist()]) if len(df) else len(str(col))
        ws.column_dimensions[h.column_letter].width = min(max(10, width + 2), 60)
    for i in range(len(df)):
        fill = PatternFill("solid", fgColor="DCE6F1" if i % 2 == 0 else "EEF3FA")
        for j in range(1, df.shape[1] + 1):
            ws.cell(row=i + 3, column=j).fill = fill
    ws.freeze_panes = "A3"


def write_excel(out, summaries, issues, matrices):
    from openpyxl.utils import get_column_letter

    sm = pd.DataFrame(summaries)
    for c in ("Allowed Accuracy", "Strict Accuracy"):
        sm[c] = sm[c].map(lambda x: "–" if pd.isna(x) else f"{x*100:.2f}%".replace(".", ","))
    iss = pd.DataFrame(issues) if issues else pd.DataFrame([{"Typ": "Keine Abweichungen"}])
    legend = pd.DataFrame({"Code": CODES, "Klasse": CLASSES, "Kurzname (Legende)": LEGEND_NAMES})

    with pd.ExcelWriter(out, engine="openpyxl") as xw:
        sm.to_excel(xw, sheet_name="Pruefung", index=False, startrow=1)
        style_table(xw.book["Pruefung"], sm, "Prüfung der Spalte Allowed_Set_Status je Datei")
        iss.to_excel(xw, sheet_name="Abweichungen", index=False, startrow=1)
        style_table(xw.book["Abweichungen"], iss, "Abweichungen (Zeile, Erwartung laut Neuberechnung)")

        ws = xw.book.create_sheet("Konfusionsmatrizen")
        ws.sheet_view.showGridLines = False
        block_w, block_h = K + 2, K + 4
        for n, (title, cm) in enumerate(matrices):
            top = 1 + (n // MATRICES_PER_ROW) * block_h
            left = 1 + (n % MATRICES_PER_ROW) * block_w
            write_matrix(ws, top, left, title, cm)
        for col in range(1, MATRICES_PER_ROW * block_w + 1):
            ws.column_dimensions[get_column_letter(col)].width = 7.5
        for b in range(MATRICES_PER_ROW):
            ws.column_dimensions[get_column_letter(1 + b * block_w)].width = 11
        if matrices:
            from openpyxl.styles import Font
            n_rows = (len(matrices) + MATRICES_PER_ROW - 1) // MATRICES_PER_ROW
            lr = 1 + n_rows * block_h - 1
            ws.cell(row=lr, column=1, value=LEGEND_TEXT).font = Font(name="Calibri", size=11)
        else:
            ws.cell(row=1, column=1, value="Keine Matrix erzeugt (Abweichungen vorhanden, siehe Blatt 'Abweichungen').")

        legend.to_excel(xw, sheet_name="Legende", index=False, startrow=1)
        style_table(xw.book["Legende"], legend, "Klassen-Codes (Zeilen = Ground Truth/Primärlabel, Spalten = Vorhersage)")


# ----------------------------------------------------------------------------
# Ausgabe PNG (optional)
# ----------------------------------------------------------------------------
def _draw(ax, x0, y0, title, cm):
    """Zeichnet eine Matrix mit linker oberer Ecke (x0, y0) in Datenkoordinaten."""
    from matplotlib.patches import Rectangle
    col = lambda h: "#" + h
    W = 1.4
    ax.add_patch(Rectangle((x0, y0 - 1), K + W, 1, color=col(NAVY)))
    ax.text(x0 + (K + W) / 2, y0 - 0.5, title, ha="center", va="center", color="white", fontsize=12, fontweight="bold")
    ax.add_patch(Rectangle((x0, y0 - 2), K + W, 1, color=col(BLUE)))
    ax.text(x0 + W / 2, y0 - 1.5, "GT \\ Pred", ha="center", va="center", color="white", fontsize=10, fontweight="bold")
    for j in range(K):
        ax.text(x0 + W + j + 0.5, y0 - 1.5, CODES[j], ha="center", va="center", color="white", fontsize=11, fontweight="bold")
    for i in range(K):
        y = y0 - 3 - i
        ax.text(x0 + W / 2, y + 0.5, CODES[i], ha="center", va="center", fontsize=11, fontweight="bold")
        for j in range(K):
            v = int(cm[i, j])
            if i == j:
                ax.add_patch(Rectangle((x0 + W + j, y), 1, 1, color=col(DIAG_FILL)))
                kw = dict(color="black", fontweight="bold")
            elif v > 0:
                ax.add_patch(Rectangle((x0 + W + j, y), 1, 1, color=col(ERR_FILL)))
                kw = dict(color=col(ERR_FONT), fontweight="bold")
            else:
                kw = dict(color=col(ZERO_FONT))
            ax.add_patch(Rectangle((x0 + W + j, y), 1, 1, fill=False, edgecolor="#E3E3E3", lw=0.6))
            ax.text(x0 + W + j + 0.5, y + 0.5, str(v), ha="center", va="center", fontsize=11, **kw)
    return K + W


def write_png(outdir, matrices):
    """Je Matrix ein PNG sowie eine Gesamtgrafik (MATRICES_PER_ROW nebeneinander), jeweils mit Legende."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    outdir.mkdir(exist_ok=True)
    bw, bh, gap = K + 1.4, K + 2, 0.8

    def save(items, cols, name):
        rows = (len(items) + cols - 1) // cols
        width = cols * bw + (cols - 1) * gap
        height = rows * bh + (rows - 1) * gap + (1.4 if cols == 1 else 1.0)
        fig, ax = plt.subplots(figsize=(width * 0.75, height * 0.62), dpi=200)
        ax.set_xlim(0, width)
        ax.set_ylim(-height, 0)
        ax.axis("off")
        for n, (title, cm) in enumerate(items):
            r, c = divmod(n, cols)
            _draw(ax, c * (bw + gap), -r * (bh + gap), title, cm)
        if cols == 1:  # Einzelmatrix: Legende zweizeilig, damit sie nicht breiter als die Matrix ist
            parts = [f"{c} = {n}" for c, n in zip(CODES, LEGEND_NAMES)]
            legend = "Klassencode: " + " | ".join(parts[:4]) + "\n" + " | ".join(parts[4:])
            ax.text(0, -height + 0.2, legend, ha="left", va="center", fontsize=8.5, linespacing=1.5)
        else:
            ax.text(0, -height + 0.35, LEGEND_TEXT, ha="left", va="center", fontsize=11)
        fig.savefig(outdir / name, bbox_inches="tight", facecolor="white")
        plt.close(fig)

    for title, cm in matrices:
        save([(title, cm)], 1, re.sub(r"[^\w.\-]+", "_", title).strip("_") + ".png")
    if len(matrices) > 1:
        save(matrices, MATRICES_PER_ROW, "Konfusionsmatrizen_gesamt.png")
    return True


# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pfade", nargs="*", help="Ordner oder .xlsx-Dateien (Standard: Skriptordner)")
    ap.add_argument("--force", action="store_true", help="Matrix auch bei Abweichungen erzeugen")
    a = ap.parse_args()

    files = collect_files(a.pfade)
    if not files:
        sys.exit("Keine .xlsx-Dateien gefunden.")

    summaries, issues, matrices = [], [], []
    for f in files:
        try:
            s, iss, cm, title = process(f)
        except Exception as e:  # Datei ohne passendes Format überspringen
            print(f"  übersprungen: {f.name} ({e})")
            continue
        summaries.append(s)
        issues += iss
        ok = not iss
        if ok or a.force:
            matrices.append((title, cm))
        print(f"{'OK ' if ok else 'ABW'}  {title:<45} Abweichungen: {len(iss)}")

    if not summaries:
        sys.exit("Keine auswertbaren Dateien.")
    out = Path.cwd() / OUTPUT_XLSX
    write_excel(out, summaries, issues, matrices)
    png_ok = write_png(Path.cwd() / OUTPUT_PNG_DIR, matrices) if matrices else False
    print(f"\n{len(summaries)} Dateien geprüft, {sum(s['Abweichungen'] == 0 for s in summaries)} ohne Abweichungen.")
    print(f"Gespeichert: {out}")
    if png_ok:
        print(f"PNG-Dateien: {Path.cwd() / OUTPUT_PNG_DIR}")
    elif matrices:
        print("Hinweis: matplotlib nicht installiert, daher keine PNG-Dateien.")


if __name__ == "__main__":
    main()
