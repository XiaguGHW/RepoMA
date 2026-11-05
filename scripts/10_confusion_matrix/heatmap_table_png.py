"""Konfusionsmatrix als kompakte Heatmap-Tabelle mit Summenzeile/-spalte (PNG).

Zeilen = Ground Truth, Spalten = Vorhersage (Klassen A–G).
Diagonale grün, Fehlklassifikationen rot (Intensität nach Anzahl), Nullen weiß.

Aufruf:  python heatmap_table_png.py [ausgabe.png]
Matrix unten in CM anpassen (oder import und draw_table(cm, out) aufrufen).
"""
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.colors import to_rgb

CODES = list("ABCDEFG")
CM = np.array([
    #  A   B    C    D    E   F   G
    [106,  0,   0,   0,   3, 11,  0],   # A
    [  0, 99,   1,   5,   4, 14,  4],   # B
    [  0,  0, 127,   0,   0, 10,  0],   # C
    [  0,  4,   0, 119,   2,  6,  2],   # D
    [  3,  0,   0,   0, 126,  7,  4],   # E
    [ 26, 20,   0,   6,  27, 99,  3],   # F
    [  0,  0,   0,   1,   4,  0, 52],   # G
])

HEADER = "#2F5597"      # dunkelblau
DIAG = "#A9D18E"        # grün
ERR_MAX = "#B5452B"     # dunkelstes Rot
ERR_MIN = "#F2DCD5"     # hellstes Rosa
LABEL_BG = "#EEEEEE"
GRID = "#BFBFBF"
TEXT = "#333333"

# Spaltenbreiten (relative Einheiten): A–G um 30 %, Summe um 20 % schmaler als zuvor
CELL_W = 1.0 * 0.7
SUM_W = 1.48 * 0.8
LABEL_W = 1.3
ROW_H = 0.52
HEAD_H = 0.62


def _err_color(v, vmax):
    t = (v / vmax) ** 0.6
    a, b = np.array(to_rgb(ERR_MIN)), np.array(to_rgb(ERR_MAX))
    return tuple(a + (b - a) * t)


def _err_text(v, vmax):
    return "white" if (v / vmax) ** 0.6 > 0.75 else "#7F2A1A"


def draw_table(cm, out, header="GT \\ Pred"):
    k = len(cm)
    row_sum, col_sum = cm.sum(1), cm.sum(0)
    off = cm[~np.eye(k, dtype=bool)]
    vmax = max(off.max(), 1)
    W = LABEL_W + k * CELL_W + SUM_W
    H = HEAD_H + (k + 1) * ROW_H

    fig, ax = plt.subplots(figsize=(W * 0.95, H * 0.95), dpi=220)
    ax.set_xlim(0, W); ax.set_ylim(H, 0); ax.axis("off")
    xs = [0, LABEL_W] + [LABEL_W + (j + 1) * CELL_W for j in range(k)]

    def cell(x, y, w, h, fc, txt, **kw):
        ax.add_patch(Rectangle((x, y), w, h, facecolor=fc, edgecolor=GRID, lw=0.8))
        ax.text(x + w / 2 if kw.pop("center", True) else x + 0.12, y + h / 2, txt,
                va="center", ha=kw.pop("ha", "center"), fontsize=11, **kw)

    # Kopfzeile
    cell(0, 0, LABEL_W, HEAD_H, HEADER, header, color="white", fontweight="bold")
    for j, c in enumerate(CODES[:k]):
        cell(xs[j + 1], 0, CELL_W, HEAD_H, HEADER, c, color="white", fontweight="bold")
    cell(xs[-1], 0, SUM_W, HEAD_H, HEADER, "Summe", color="white", fontweight="bold")

    # Matrix
    for i in range(k):
        y = HEAD_H + i * ROW_H
        cell(0, y, LABEL_W, ROW_H, LABEL_BG, CODES[i], center=False, ha="left", color=TEXT)
        for j in range(k):
            v = cm[i, j]
            if i == j:
                fc, tc = DIAG, TEXT
            elif v == 0:
                fc, tc = "white", TEXT
            else:
                fc, tc = _err_color(v, vmax), _err_text(v, vmax)
            cell(xs[j + 1], y, CELL_W, ROW_H, fc, str(v), color=tc)
        cell(xs[-1], y, SUM_W, ROW_H, LABEL_BG, str(row_sum[i]), color="black", fontweight="bold")

    # Summenzeile
    y = HEAD_H + k * ROW_H
    cell(0, y, LABEL_W, ROW_H, LABEL_BG, "Summe", center=False, ha="left", color=TEXT)
    for j in range(k):
        cell(xs[j + 1], y, CELL_W, ROW_H, LABEL_BG, str(col_sum[j]), color="black", fontweight="bold")
    cell(xs[-1], y, SUM_W, ROW_H, LABEL_BG, str(cm.sum()), color="black", fontweight="bold")

    ax.add_patch(Rectangle((0, 0), W, H, fill=False, edgecolor="#404040", lw=1.2))
    fig.savefig(out, bbox_inches="tight", pad_inches=0.04, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "konfusionsmatrix_heatmap.png"
    draw_table(CM, out)
    print(f"gespeichert: {out}")
