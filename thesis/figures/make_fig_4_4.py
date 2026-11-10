"""Generate Figure 4.4: examples of the three ambiguity regimes (E1, E2, M).

Image cells are left blank (space for portrait images); the CAD screenshots are inserted later.
"""
from xml.sax.saxutils import escape

FONT = "Liberation Sans"
DARK = "#1F4E8C"; LINE = "#9FB3CF"; HEAD_BG = "#DCE6F2"
TXT = "#222222"; MUTED = "#666666"

cols = [("Example", 180), ("Initial label", 185), ("Participant\nclassifications", 250),
        ("Review finding", 330), ("Allowed labels\nafter review", 240), ("Regime", 115)]

# regime: (label, fill, stroke)
REG = {"E1": ("#E3EFD9", "#6A9A4B"), "E2": ("#F6EBC8", "#B8922A"), "M": ("#F4DCCB", "#B5643A")}

rows = [
    {"name": "Articulated robot",
     "initial": ["Robot"],
     "votes": ["Robot ×3"],
     "finding": ["Unanimous classification;", "label consistent with", "the codebook"],
     "allowed": ["{Robot}"],
     "regime": "E1"},
    {"name": "Machine frame",
     "initial": ["None of the", "Available Classes"],
     "votes": ["None of the Available", "Classes ×2, Gripper ×1"],
     "finding": ["Dissenting vote not supported:", "no gripping function", "(R = 0, T = 0)"],
     "allowed": ["{None of the", "Available Classes}"],
     "regime": "E2"},
    {"name": "Lifting unit",
     "initial": ["Linear Unit"],
     "votes": ["Linear Unit ×2,", "Combined Unit ×1"],
     "finding": ["Secondary rotary component;", "both classes consistent", "with the codebook"],
     "allowed": ["{Linear Unit,", "Combined Unit}"],
     "regime": "M"},
]

X0 = 20; Y0 = 20; HEAD_H = 70; ROW_H = 200; LH = 24
out = []

def rect(x, y, w, h, fill, stroke=LINE, sw=1.2, rx=0):
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" '
               f'stroke="{stroke}" stroke-width="{sw}"/>')

def lines(cx, cy, ls, size=19, weight="normal", color=TXT, style="normal"):
    """Draw lines centred horizontally at cx and vertically around cy."""
    n = len(ls)
    for i, s in enumerate(ls):
        y = cy + (i - (n - 1) / 2) * LH + size * 0.36
        out.append(f'<text x="{cx}" y="{y:.1f}" font-family="{FONT}" font-size="{size}" '
                   f'font-weight="{weight}" font-style="{style}" fill="{color}" '
                   f'text-anchor="middle">{escape(s)}</text>')

# header
x = X0
for name, w in cols:
    rect(x, Y0, w, HEAD_H, HEAD_BG)
    lines(x + w / 2, Y0 + HEAD_H / 2, name.split("\n"), 18.5, "bold", DARK)
    x += w
width = x + X0

# body
for r, row in enumerate(rows):
    y = Y0 + HEAD_H + r * ROW_H
    cy = y + ROW_H / 2
    x = X0
    for ci, (name, w) in enumerate(cols):
        rect(x, y, w, ROW_H, "white")
        cx = x + w / 2
        if ci == 0:  # blank space for a portrait image, name at the bottom
            lines(cx, y + ROW_H - 22, [row["name"]], 17.5, color=TXT, style="italic")
        elif ci == 1:
            lines(cx, cy, row["initial"])
        elif ci == 2:
            lines(cx, cy, row["votes"])
        elif ci == 3:
            lines(cx, cy, row["finding"], 18)
        elif ci == 4:
            lines(cx, cy, row["allowed"], 19, "bold", DARK)
        else:
            fill, stroke = REG[row["regime"]]
            rect(cx - 36, cy - 24, 72, 48, fill, stroke, 1.5, rx=6)
            lines(cx, cy, [row["regime"]], 22, "bold", TXT)
        x += w

height = Y0 + HEAD_H + len(rows) * ROW_H + X0
svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
       f'viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="white"/>'
       + "".join(out) + "</svg>")
open("fig_4_4_regime_examples.svg", "w", encoding="utf-8").write(svg)
print(width, height)
