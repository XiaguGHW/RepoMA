"""Generate Figure 4.4: examples of the three ambiguity regimes (E1, E2, M).

Horizontal layout, one row per example. Sized so that, scaled to a text width
of about 16 cm, body text appears at roughly 10 pt (thesis body: Arial 12 pt).
Liberation Sans is metric-compatible with Arial. The image cells are left
blank; the portrait CAD screenshots are inserted later.
"""
from xml.sax.saxutils import escape
from PIL import ImageFont

FONT = "Liberation Sans, Arial"
FONT_FILES = {"normal": "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
              "bold": "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
              "italic": "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf"}
DARK = "#1F4E8C"; LINE = "#9FB3CF"; HEAD_BG = "#DCE6F2"; TXT = "#222222"
REG = {"E1": ("#E3EFD9", "#6A9A4B"), "E2": ("#F6EBC8", "#B8922A"), "M": ("#F4DCCB", "#B5643A")}

SIZE = 29          # body text  (~10 pt at 16 cm width)
HEAD_SIZE = 28     # header text
PAD = 16           # horizontal padding inside a cell
IMG_H = 230        # blank space reserved for a portrait image
X0 = Y0 = 10

cols = [("Example", 225), ("Initial label", 210), ("Participant classifications (votes)", 275),
        ("Review finding", 285), ("Allowed labels after review", 250), ("Regime", 125)]

examples = [
    {"name": "Articulated robot", "initial": "Robot", "votes": ["Robot (3/3)"],
     "finding": "Unanimous classification; label consistent with the codebook",
     "allowed": "{Robot}", "regime": "E1"},
    {"name": "Machine frame", "initial": "None of the Available Classes",
     "votes": ["None of the Available Classes (2/3)", "Gripper (1/3)"],
     "finding": "Dissenting vote not supported: no gripping function (R = 0, T = 0)",
     "allowed": "{None of the Available Classes}", "regime": "E2"},
    {"name": "Lifting unit", "initial": "Linear Unit",
     "votes": ["Linear Unit (2/3)", "Combined\u00a0Unit (1/3)"],
     "finding": "Secondary rotary component; both classes consistent with the codebook",
     "allowed": "{Linear Unit, Combined\u00a0Unit}", "regime": "M"},
]

_fonts = {}
def width(s, size, weight):
    key = (size, weight)
    if key not in _fonts:
        _fonts[key] = ImageFont.truetype(FONT_FILES[weight], size)
    return _fonts[key].getlength(s)

def wrap(s, size, weight, maxw):
    lines, cur = [], ""
    for word in s.split(" "):
        test = (cur + " " + word).strip()
        if width(test, size, weight) <= maxw or not cur:
            cur = test
        else:
            lines.append(cur); cur = word
    lines.append(cur)
    return lines

out = []
def rect(x, y, w, h, fill, stroke=LINE, sw=1.2, rx=0):
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" '
               f'stroke="{stroke}" stroke-width="{sw}"/>')
def text_block(cx, cy, ls, size, weight="normal", color=TXT):
    lh = size * 1.22
    n = len(ls)
    style = "italic" if weight == "italic" else "normal"
    fw = "bold" if weight == "bold" else "normal"
    for i, s in enumerate(ls):
        y = cy + (i - (n - 1) / 2) * lh + size * 0.36
        out.append(f'<text x="{cx:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{size}" '
                   f'font-weight="{fw}" font-style="{style}" fill="{color}" '
                   f'text-anchor="middle">{escape(s)}</text>')

# header
head_lines = [wrap(n, HEAD_SIZE, "bold", w - 2 * PAD) for n, w in cols]
head_h = max(len(l) for l in head_lines) * HEAD_SIZE * 1.22 + 30
x = X0
for (name, w), ls in zip(cols, head_lines):
    rect(x, Y0, w, head_h, HEAD_BG)
    text_block(x + w / 2, Y0 + head_h / 2, ls, HEAD_SIZE, "bold", DARK)
    x += w
W = x + X0

# body
y = Y0 + head_h
min_row_h = IMG_H + SIZE * 1.5 + 24
for e in examples:
    w_ = [w - 2 * PAD for _, w in cols]
    cell = {
        1: (wrap(e["initial"], SIZE, "normal", w_[1]), "normal", TXT),
        2: (sum((wrap(v, SIZE, "normal", w_[2]) for v in e["votes"]), []), "normal", TXT),
        3: (wrap(e["finding"], SIZE, "normal", w_[3]), "normal", TXT),
        4: (wrap(e["allowed"], SIZE, "bold", w_[4]), "bold", DARK),
    }
    h = max(min_row_h, max(len(c[0]) for c in cell.values()) * SIZE * 1.22 + 40)
    x = X0
    for ci, (_, w) in enumerate(cols):
        rect(x, y, w, h, "white")
        cx, cy = x + w / 2, y + h / 2
        if ci == 0:   # blank image area, name at the bottom
            text_block(cx, y + h - 16 - SIZE * 0.5, [e["name"]], SIZE - 3, "italic")
        elif ci == 5:
            fill, stroke = REG[e["regime"]]
            rect(cx - 40, cy - 25, 80, 50, fill, stroke, 1.8, rx=7)
            text_block(cx, cy, [e["regime"]], 31, "bold")
        else:
            ls, weight, color = cell[ci]
            text_block(cx, cy, ls, SIZE, weight, color)
        x += w
    y += h

H = y + Y0
svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H:.0f}" '
       f'viewBox="0 0 {W} {H:.0f}"><rect width="100%" height="100%" fill="white"/>'
       + "".join(out) + "</svg>")
open("fig_4_4_regime_examples.svg", "w", encoding="utf-8").write(svg)
print(W, round(H), f"body ≈ {SIZE * 453 / W:.1f} pt at 16 cm")
