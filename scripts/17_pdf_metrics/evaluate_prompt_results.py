"""Prompt-Vergleich: P1–P4 × vier Modelle (PDF, 115 BG, je ein Lauf) = 16 Ergebnisdateien.

Nutzt evaluate_pdf_results.py (gleicher Ordner, ebenso confusion_human_llm.py und
evaluate_validation_regimes.py); dieselben Regeln für GT, Regime, Normalisierung und Metriken.

Ausgabe <out>/Prompt_Metriken_Konfusion.xlsx:
    Uebersicht      Allowed Acc. und Strict Macro-F1 je Modell × Prompt (wie Tabelle 5.3), mit n
    Metriken_4x4    16 Tabellen wie Metriken_2x2; Zeilen = Modelle, Spalten = P1–P4
    Konfusion_4x4   16 Konfusionsmatrizen in derselben Anordnung
und <out>/konfusion_prompt_4x4.png.

Prompt und Modell werden aus dem Dateinamen erkannt (P1…P4, haiku/opus/gemini-2.5-pro/gemini-2.5-flash),
ersatzweise aus den Namen der übergeordneten Ordner. --dir sucht auch in Unterordnern.

Aufruf (PowerShell):
    python evaluate_prompt_results.py --dir "C:\\pdf\\prompt" --out "C:\\pdf\\Ergebnis_Prompt"
    (optional --nur-sheet1, --lang de, --height 0.7, --no-png, --input-label PDF)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evaluate_pdf_results as E  # noqa: E402

cm = E.cm
PROMPTS = ["P1", "P2", "P3", "P4"]
MODEL_ORDER = ["Claude Haiku 4.5", "Claude Opus 4.8", "Gemini 2.5 Flash", "Gemini 2.5 Pro"]  # wie Tabelle 5.3
KNOWN = {n for _, n in E.MODELS}


def detect_prompt(path):
    for part in [path.name] + [p.name for p in path.parents][:3]:
        m = re.findall(r"(?<![a-z0-9])p([1-4])(?![0-9])", part.lower())
        if len(set(m)) == 1:
            return f"P{m[0]}"
    return None


def detect_model(path):
    for part in [path] + list(path.parents)[:3]:
        n = E.model_name(part)
        if n in KNOWN:
            return n
    return None


# ---------------------------------------------------------------- Excel
def write_overview(wb, grid, models, input_label):
    S = E.styles()
    Font = S["Font"]
    ws = wb.create_sheet("Uebersicht")
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 2
    ws.column_dimensions["B"].width = 22
    r = 2
    for key, label in [("acc", "Allowed Accuracy"), ("f1", "Strict Macro-F1")]:
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=2 + len(PROMPTS))
        t = ws.cell(r, 2, f"{label} (%) by prompt variant ({input_label} input, 115 assemblies)")
        t.font = Font(bold=True, color="FFFFFF", size=12)
        t.alignment = S["center"]
        for j in range(len(PROMPTS) + 1):
            ws.cell(r, 2 + j).fill = S["fill"](cm.NAVY)
        for j, h in enumerate(["Model"] + PROMPTS):
            c = ws.cell(r + 1, 2 + j, h)
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = S["fill"](cm.HEAD)
            c.alignment = S["left"] if j == 0 else S["center"]
            c.border = S["border"]
        vals = {}
        for i, m in enumerate(models + ["Mean"]):
            rr = r + 2 + i
            bg = E.ACC_ROW_BG if m == "Mean" else (E.ODD_ROW_BG if i % 2 else "#FFFFFF")
            c = ws.cell(rr, 2, m)
            c.font = Font(bold=m == "Mean")
            c.fill, c.alignment, c.border = S["fill"](bg), S["left"], S["border"]
            for j, p in enumerate(PROMPTS):
                if m == "Mean":
                    xs = [vals[(mm, p)] for mm in models if not np.isnan(vals.get((mm, p), np.nan))]
                    v = float(np.mean(xs)) if len(xs) == len(models) else None
                    txt = v
                else:
                    recs = grid.get((m, p))
                    v = E.metrics(recs)[key] if recs else np.nan
                    vals[(m, p)] = v
                    txt = None if np.isnan(v) else float(v)
                c = ws.cell(rr, 3 + j, txt)
                c.number_format = "0.0%"
                c.font = Font(bold=m == "Mean")
                c.fill, c.alignment, c.border = S["fill"](bg), S["right"], S["border"]
        # n je Zelle (Kontrolle)
        nr = r + 2 + len(models) + 1
        ws.cell(nr, 2, "n (gewertete Baugruppen)").font = Font(italic=True, size=9, color="595959")
        for i, m in enumerate(models):
            ws.cell(nr + 1 + i, 2, m).font = Font(size=9, color="595959")
            for j, p in enumerate(PROMPTS):
                recs = grid.get((m, p))
                ws.cell(nr + 1 + i, 3 + j, len(recs) if recs else "fehlt").font = Font(size=9, color="595959")
        r = nr + 1 + len(models) + 2
    for j in range(len(PROMPTS)):
        ws.column_dimensions[chr(ord("C") + j)].width = 13


def write_metric_grid(wb, items, ncols):
    """items: Liste von (Titel, recs oder None) zeilenweise im Raster mit ncols Spalten."""
    from openpyxl.utils import get_column_letter
    S = E.styles()
    Font = S["Font"]
    ws = wb.create_sheet("Metriken_4x4")
    ws.sheet_view.showGridLines = False
    ncol, nrow, gapc, gapr = 6, 6, 1, 2
    ws.column_dimensions["A"].width = 2
    for k, (title, recs) in enumerate(items):
        r0 = 2 + (k // ncols) * (nrow + gapr)
        c0 = 2 + (k % ncols) * (ncol + gapc)
        ws.merge_cells(start_row=r0, start_column=c0, end_row=r0, end_column=c0 + ncol - 1)
        t = ws.cell(r0, c0, title if recs else f"{title} – Datei fehlt")
        t.font = Font(bold=True, color="FFFFFF", size=12)
        t.alignment = S["center"]
        for j in range(ncol):
            ws.cell(r0, c0 + j).fill = S["fill"](cm.NAVY)
        ws.row_dimensions[r0].height = 22
        if not recs:
            continue
        mets = {s: E.metrics(E.subset(recs, s)) for s in E.SUBSETS}
        heads = ["Metrik"] + [f"{E.SUBSET_HEAD[s]} (n={mets[s]['n']})" for s in E.SUBSETS]
        for j, h in enumerate(heads):
            c = ws.cell(r0 + 1, c0 + j, h)
            c.font = Font(bold=True, color="FFFFFF")
            c.fill, c.border = S["fill"](cm.HEAD), S["border"]
            c.alignment = S["left"] if j == 0 else S["center"]
        for i, (key, label) in enumerate(E.METRIC_ROWS):
            rr = r0 + 2 + i
            bg = E.ACC_ROW_BG if key == "acc" else (E.ODD_ROW_BG if i % 2 else "#FFFFFF")
            c = ws.cell(rr, c0, label)
            c.font = Font(bold=key == "acc", color=E._xl(cm.DARK_TXT) if key == "acc" else "000000")
            c.fill, c.alignment, c.border = S["fill"](bg), S["left"], S["border"]
            for j, s in enumerate(E.SUBSETS):
                v = mets[s][key]
                c = ws.cell(rr, c0 + 1 + j, None if np.isnan(v) else float(v))
                c.number_format = "0.0%"
                c.font = Font(bold=key == "acc" or s == "Total")
                c.fill, c.alignment, c.border = S["fill"](bg), S["right"], S["border"]
    for k in range(ncols):
        c0 = 2 + k * (ncol + gapc)
        ws.column_dimensions[get_column_letter(c0)].width = 21
        for j in range(1, ncol):
            ws.column_dimensions[get_column_letter(c0 + j)].width = 17
        ws.column_dimensions[get_column_letter(c0 + ncol)].width = 3
    nr = 2 + ((len(items) + ncols - 1) // ncols) * (nrow + gapr) - 1
    notes = [
        "Allowed Acc.: Vorhersage im zulässigen Label-Set ({GT} ∪ weitere zulässige).",
        "Strict Macro-F1: nur das Primärlabel zählt; Mittel der Klassen-F1 über Klassen, die in GT oder Vorhersage vorkommen.",
        "Allowed Macro-Prec./-Rec.: Formel 5.2a/5.2b; Precision gemittelt über vorhergesagte Klassen, Recall über Klassen der GT.",
        "Regime: M ohne weiteres zulässiges Label zählt als E2. GT, Register und zulässige Labels aus Sheet1 der jeweiligen Datei.",
    ]
    for i, txt in enumerate(notes):
        ws.cell(nr + i, 2, txt).font = Font(italic=True, size=9, color="595959")


def write_confusion_grid(wb, items, ncols, lang):
    from openpyxl.utils import get_column_letter
    S = E.styles()
    Font = S["Font"]
    K = E.K
    ws = wb.create_sheet("Konfusion_4x4")
    ws.sheet_view.showGridLines = False
    ncol, nrow, gapc, gapr = 1 + 2 * K, 2 + K, 1, 2
    ws.column_dimensions["A"].width = 2

    def put(r, c, v, bg="#FFFFFF", color="000000", bold=False, span=1, size=11):
        if span > 1:
            ws.merge_cells(start_row=r, start_column=c, end_row=r, end_column=c + span - 1)
        cell = ws.cell(r, c, v)
        cell.font = Font(bold=bold, color=E._xl(color), size=size)
        cell.alignment = S["center"]
        for j in range(span):
            x = ws.cell(r, c + j)
            x.fill = S["fill"](bg)
            x.border = S["border"]

    for k, (title, m) in enumerate(items):
        r0 = 2 + (k // ncols) * (nrow + gapr)
        c0 = 2 + (k % ncols) * (ncol + gapc)
        put(r0, c0, title if m else f"{title} – Datei fehlt", cm.NAVY, "#FFFFFF", True, span=ncol, size=12)
        ws.row_dimensions[r0].height = 22
        for j in range(ncol):
            ws.column_dimensions[get_column_letter(c0 + j)].width = 9 if j == 0 else 4.2
        ws.column_dimensions[get_column_letter(c0 + ncol)].width = 3
        if not m:
            continue
        put(r0 + 1, c0, cm.TXT_HEAD, cm.HEAD, "#FFFFFF", True, size=9)
        for j, code in enumerate(cm.CODES):
            put(r0 + 1, c0 + 1 + 2 * j, code, cm.HEAD, "#FFFFFF", True, span=2)
        for i, code in enumerate(cm.CODES):
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
    t = cm.TXT[lang]
    lr = 2 + ((len(items) + ncols - 1) // ncols) * (nrow + gapr) - 1
    for i, (bg, lab) in enumerate([(cm.BLUE_BG, t["diag"]), (cm.RED_BG, t["red"]), (cm.GREEN_BG, t["green"])]):
        c = 2 + i * 5
        ws.cell(lr, c).fill = S["fill"](bg)
        ws.cell(lr, c).border = S["border"]
        ws.cell(lr, c + 1, lab).font = Font(size=10)
    ws.cell(lr + 1, 2, cm.codes_line(lang)).font = Font(size=10)


def save_png(items, ncols, path, lang, hf):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rows = (len(items) + ncols - 1) // ncols
    fig = plt.figure(figsize=(5.5 * ncols, 4.2 * hf * rows + 1.0))
    gs = fig.add_gridspec(rows + 1, ncols, height_ratios=[4.2 * hf] * rows + [1.0], hspace=0.08, wspace=0.05)
    for k, (title, m) in enumerate(items):
        ax = fig.add_subplot(gs[k // ncols, k % ncols])
        if m:
            cm.draw_matrix(ax, m, title, fs=0.92)
        else:
            ax.axis("off")
            ax.text(0.5, 0.5, f"{title}\n(Datei fehlt)", ha="center", va="center")
    cm.draw_legend(fig.add_subplot(gs[rows, :]), lang, fs=1.6)
    fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# ---------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*")
    ap.add_argument("--dir", help="Ordner mit den 16 Ergebnisdateien (auch Unterordner)")
    ap.add_argument("--sheet", default="Sheet1")
    ap.add_argument("--out", default="Prompt_Metriken")
    ap.add_argument("--input-label", default="PDF")
    ap.add_argument("--lang", choices=["en", "de"], default="en")
    ap.add_argument("--height", type=float, default=0.7)
    ap.add_argument("--no-png", action="store_true")
    ap.add_argument("--nur-sheet1", action="store_true",
                    help="danach in den Ergebnisdateien alle Blätter außer --sheet löschen (Sicherung in <out>/Backup_Original)")
    a = ap.parse_args(argv)

    out = Path(a.out)
    files = [Path(f) for f in a.files]
    if a.dir:
        files += sorted(p for p in Path(a.dir).rglob("*.xlsx") if not E.is_output_or_backup(p))
    if not files:
        ap.error("keine Dateien angegeben (Dateien oder --dir)")

    grid, src, issues, unknown = {}, {}, [], []
    for f in files:
        p, m = detect_prompt(f), detect_model(f)
        if not p or not m:
            unknown.append(f"{f}  (Prompt: {p or '?'}, Modell: {m or '?'})")
            continue
        if (m, p) in grid:
            sys.exit(f"Doppelt: {m} {p}\n  {src[(m, p)]}\n  {f}")
        grid[(m, p)] = E.read_file(f, a.sheet, f"{m} {p}", issues)
        src[(m, p)] = f
    if unknown:
        print("Nicht zugeordnet (ignoriert):")
        for u in unknown:
            print("  " + u)
    if not grid:
        sys.exit("Keine Datei zugeordnet.")
    models = [m for m in MODEL_ORDER if any((m, p) in grid for p in PROMPTS)]
    models += sorted({m for m, _ in grid} - set(models))

    from openpyxl import Workbook
    out.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    wb.remove(wb.active)
    write_overview(wb, grid, models, a.input_label)
    m_items, c_items = [], []
    for m in models:
        for p in PROMPTS:
            recs = grid.get((m, p))
            m_items.append((f"{m} (115BG, {p}, {a.input_label})", recs))
            mat = E.matrix_for(recs) if recs else None
            c_items.append((f"{m} ({p}), n = {mat['n']}" if mat else f"{m} ({p})", mat))
    write_metric_grid(wb, m_items, len(PROMPTS))
    write_confusion_grid(wb, c_items, len(PROMPTS), a.lang)
    xlsx = out / "Prompt_Metriken_Konfusion.xlsx"
    wb.save(xlsx)
    if not a.no_png:
        save_png(c_items, len(PROMPTS), out / "konfusion_prompt_4x4.png", a.lang, a.height)

    # Konsole
    print(f"Ausgabe: {xlsx}")
    print(f"  Allowed Accuracy (%), n in Klammern")
    print(f"  {'':<18}" + "".join(f"{p:>14}" for p in PROMPTS))
    for m in models:
        row = ""
        for p in PROMPTS:
            recs = grid.get((m, p))
            row += f"{E.metrics(recs)['acc']*100:>8.1f} ({len(recs):>3})" if recs else f"{'fehlt':>14}"
        print(f"  {m:<18}{row}")
    missing = [f"{m} {p}" for m in models for p in PROMPTS if (m, p) not in grid]
    if missing:
        print("  Fehlende Kombinationen: " + ", ".join(missing))
    shown = [i for i in issues if not i["Typ"].startswith("Info:")]
    dev = [i for i in shown if i["Typ"] == "Allowed_Set_Status weicht ab"]
    print(f"  Abweichungen Allowed_Set_Status: {len(dev)}")
    if shown:
        print("  Hinweise (gleiche Hinweise zusammengefasst):")
        groups = {}
        for i in shown:
            k = (i["Typ"], i.get("SAP"), i.get("Detail"))
            groups.setdefault(k, []).append(i.get("Modell"))
        for (typ, sap, det), who in groups.items():
            where = "alle 16 Dateien" if len(who) == len(grid) and len(grid) > 1 else ", ".join(who)
            parts = [typ, sap, det, where]
            print("   - " + " | ".join(str(x) for x in parts if x))
    if a.nur_sheet1:
        E.keep_only_sheet(list(src.values()), a.sheet, out)
    return grid


if __name__ == "__main__":
    main()
