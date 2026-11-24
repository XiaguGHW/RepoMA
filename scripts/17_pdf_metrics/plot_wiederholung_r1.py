"""Diagramme „Mittelwert und Stabilität der Accuracy“ (fester Stil wie in der Präsentation) für die
Wiederholungsläufe unter R1: je Modell und Datensatz (185 / 115 BG) ein Diagramm mit
  - Run-by-Run Accuracy (Linie mit Punkten, #122B63),
  - Mittelwert (gestrichelt, #C00304),
  - Band Mittelwert ± Standardabweichung (#B6D2DD).
Accuracy = Allowed-Label-Set Accuracy unter R1 über alle Baugruppen des Laufs (wie evaluate_r1.py).

Ausgabe in --out:
  Wiederholung_<185|115>BG_<Modell>.png   (300 dpi, einzeln)
  Wiederholung_<185|115>BG_alle.png        (alle Modelle untereinander)
  Accuracy_je_Lauf_R1.xlsx                 (Werte je Lauf – zum Nachrechnen)

Aufruf:
    python plot_wiederholung_r1.py --dir "..\\03_Wiederholung_10runs" --gt R1.md --out "..\\05_Ergebnisse\\Diagramme"
Benötigt im selben Ordner: evaluate_r1.py und dessen Abhängigkeiten.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evaluate_r1 as R  # noqa: E402

BAND, MEAN, LINE, BG = "#B6D2DD", "#C00304", "#122B63", "#FFFFFF"
TITLE_NAME = {"Gemini 2.5 Pro": "Gemini-2.5-pro", "Gemini 2.5 Flash": "Gemini-2.5-flash",
              "Claude Haiku 4.5": "Claude-Haiku-4.5", "GPT-5.5": "GPT-5.5", "DeepSeek-V4-Flash": "DeepSeek-V4-Flash"}


def run_accuracies(gt, runs):
    return [float(np.mean([R.correct(gt, k, r[k]) for k in r])) * 100 for r in runs]


def draw(ax, accs, model, fs=1.0):
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    from matplotlib.ticker import FuncFormatter, MaxNLocator
    x = np.arange(1, len(accs) + 1)
    m = float(np.mean(accs))
    sd = float(np.std(accs, ddof=1)) if len(accs) > 1 else 0.0
    ax.set_facecolor(BG)
    ax.axhspan(m - sd, m + sd, color=BAND, zorder=1, lw=0)
    ax.axhline(m, color=MEAN, ls=(0, (4, 3)), lw=1.6 * fs, zorder=2)
    ax.plot(x, accs, color=LINE, lw=1.8 * fs, marker="o", ms=5 * fs, zorder=3)
    lo, hi = min(min(accs), m - sd), max(max(accs), m + sd)
    pad = max(0.4, (hi - lo) * 0.18)
    ax.set_ylim(lo - pad, hi + pad)
    ax.set_xlim(0.85, len(accs) + 0.15)
    ax.set_xticks(x)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=6, steps=[1, 2, 2.5, 5, 10]))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.1f}%"))
    ax.set_ylabel("Accuracy", fontweight="bold", fontsize=12 * fs)
    ax.tick_params(labelsize=10 * fs, length=0)
    ax.grid(axis="y", color="#E6E6E6", lw=0.8, zorder=0)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#BFBFBF")
    handles = [Patch(color=BAND, label=f"Std. Dev. (±{sd:.2f}%)"),
               Line2D([], [], color=MEAN, ls=(0, (4, 3)), lw=1.6, label=f"Mean Acc. ({m:.2f}%)"),
               Line2D([], [], color=LINE, lw=1.8, marker="o", ms=5, label="Run-by-Run Acc.")]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3, frameon=False,
              fontsize=11 * fs, handlelength=2.4, columnspacing=4)
    return m, sd


def title_below(fig, ax, model, n_runs, fs=1.0):
    """Titel unter dem Diagramm: 'Mittelwert und Stabilität der Accuracy (**Modell**, 10 Durchläufe)'."""
    fig.canvas.draw()
    bb = ax.get_tightbbox(fig.canvas.get_renderer()).transformed(fig.transFigure.inverted())
    y = bb.y0 - 0.02
    parts = [("Mittelwert und Stabilität der Accuracy (", "normal"), (TITLE_NAME.get(model, model), "bold"),
             (f", {n_runs} Durchläufe)", "normal")]
    r = fig.canvas.get_renderer()
    texts = [fig.text(0, y, t, fontsize=15 * fs, fontweight=w, va="top") for t, w in parts]
    widths = [t.get_window_extent(r).transformed(fig.transFigure.inverted()).width for t in texts]
    x = 0.5 - sum(widths) / 2
    for t, w in zip(texts, widths):
        t.set_x(x)
        x += w


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, action="append")
    ap.add_argument("--gt", required=True)
    ap.add_argument("--out", default="Diagramme")
    ap.add_argument("--gt-name", default=None)
    a = ap.parse_args()
    if not a.gt_name:
        import re as _re
        a.gt_name = (_re.match(r"(R\d+)", Path(a.gt).stem, _re.I) or [Path(a.gt).stem])[0].upper()
    gt, pe, _ = R.load_gt(a.gt)
    data, _ = R.collect(a.dir, "Sheet1", gt, pe, [])
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    models = [m for m in R.MODEL_ORDER if m in data] + [m for m in data if m not in R.MODEL_ORDER]
    rows = []
    for scope in ("185", "115"):
        series = []
        for m in models:
            if scope == "185" and not data[m]["supp"]:
                print(f"! {m}: keine 70BG-Läufe – kein Diagramm für 185 BG")
                continue
            runs = R.build_runs(data[m]["main"], data[m]["supp"], scope)
            if not runs:
                continue
            accs = run_accuracies(gt, runs)
            series.append((m, accs))
            for i, v in enumerate(accs, 1):
                rows.append({"Datensatz": f"{scope} BG", "Modell": m, "Lauf": i, "Accuracy (%)": round(v, 4)})
            fig = plt.figure(figsize=(11, 4.6), facecolor=BG)
            ax = fig.add_axes([0.09, 0.30, 0.88, 0.66])
            mm, sd = draw(ax, accs, m)
            title_below(fig, ax, m, len(runs))
            name = TITLE_NAME.get(m, m)
            fig.savefig(out / f"Wiederholung_{scope}BG_{name}.png", dpi=300, facecolor=BG)
            plt.close(fig)
            print(f"{scope} BG  {m:<20} Mittel {mm:6.2f} %  SD {sd:.2f} pp  ({len(runs)} Läufe)")
        if series:
            # Gesamtbild: Einzeldiagramme untereinander (gleiches Layout wie die Einzelbilder)
            from PIL import Image
            ims = [Image.open(out / f"Wiederholung_{scope}BG_{TITLE_NAME.get(m, m)}.png") for m, _ in series]
            W = max(i.width for i in ims)
            canvas = Image.new("RGB", (W, sum(i.height for i in ims)), "white")
            y = 0
            for im in ims:
                canvas.paste(im, (0, y))
                y += im.height
            canvas.save(out / f"Wiederholung_{scope}BG_alle.png", dpi=(300, 300))
    pd.DataFrame(rows).to_excel(out / f"Accuracy_je_Lauf_{a.gt_name}.xlsx", index=False)
    write_excel(out, models, rows, a.gt_name)
    print(f"Ausgabe: {out}")


def write_excel(out, models, rows, gt_name="R1"):
    """Alle Diagramme in eine Excel-Datei: je Datensatz ein Blatt (Diagramme untereinander), dazu die Werte je Lauf."""
    from openpyxl import Workbook
    from openpyxl.drawing.image import Image as XLImage
    from openpyxl.styles import Font
    wb = Workbook()
    wb.remove(wb.active)
    for scope in ("185", "115"):
        files = [(m, out / f"Wiederholung_{scope}BG_{TITLE_NAME.get(m, m)}.png") for m in models]
        files = [(m, f) for m, f in files if f.is_file()]
        if not files:
            continue
        ws = wb.create_sheet(f"Diagramme {scope} BG")
        ws.sheet_view.showGridLines = False
        ws["B2"] = f"Mittelwert und Stabilität der Accuracy – 10 Läufe mit {scope} Baugruppen (Ground Truth {gt_name})"
        ws["B2"].font = Font(bold=True, size=14)
        row = 4
        for m, f in files:
            img = XLImage(str(f))
            w = 900                      # Anzeigebreite in Pixel (Bild bleibt in voller Auflösung eingebettet)
            img.height = int(img.height * w / img.width)
            img.width = w
            ws.add_image(img, f"B{row}")
            row += int(img.height / 20) + 2   # Standardzeilenhöhe ≈ 20 px
    ws = wb.create_sheet("Werte je Lauf")
    df = pd.DataFrame(rows)
    if len(df):
        piv = df.pivot_table(index=["Datensatz", "Modell"], columns="Lauf", values="Accuracy (%)").reset_index()
        runs = [c for c in piv.columns if isinstance(c, (int, np.integer))]
        piv["Mittelwert"] = piv[runs].mean(axis=1)
        piv["SD (pp)"] = piv[runs].std(axis=1, ddof=1)
        ws.append([str(c) if not isinstance(c, str) else c for c in piv.columns])
        for r in piv.itertuples(index=False):
            ws.append([round(v, 2) if isinstance(v, float) else v for v in r])
        for c in ws[1]:
            c.font = Font(bold=True)
        ws.column_dimensions["A"].width = 12
        ws.column_dimensions["B"].width = 22
    wb.save(out / f"Diagramme_Wiederholung_{gt_name}.xlsx")
    print(f"Excel mit allen Diagrammen: {out / f'Diagramme_Wiederholung_{gt_name}.xlsx'}")


if __name__ == "__main__":
    main()
