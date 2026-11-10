"""Generate Figure 4.4: examples of the three ambiguity regimes (E1, E2, M).

Transposed layout: one column per example, one row per attribute, so that
portrait CAD images fit and the text can be set large. The image cells are
left blank; the screenshots are inserted later.
"""
from xml.sax.saxutils import escape
from PIL import ImageFont

FONT = "Liberation Sans"
FONT_FILES = {"normal": "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
              "bold": "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
              "italic": "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf"}
DARK = "#1F4E8C"; LINE = "#9FB3CF"; HEAD_BG = "#DCE6F2"; TXT = "#222222"
REG = {"E1": ("#E3EFD9", "#6A9A4B"), "E2": ("#F6EBC8", "#B8922A"), "M": ("#F4DCCB", "#B5643A")}

SIZE = 44          # body text
HEAD_SIZE = 42     # row labels
LABEL_W = 340      # width of the row-label column
COL_W = 420        # width of each example column
PAD = 26           # horizontal padding inside a cell
IMG_H = 470        # blank space reserved for a portrait image
X0 = Y0 = 20

examples = [
    {"name": "Articulated robot", "initial": "Robot", "votes": ["Robot\u00a0×3"],
     "finding": "Unanimous classification; label consistent with the codebook",
     "allowed": "{Robot}", "regime": "E1"},
    {"name": "Machine frame", "initial": "None of the Available Classes",
     "votes": ["None of the Available Classes\u00a0×2", "Gripper\u00a0×1"],
     "finding": "Dissenting vote not supported: no gripping function (R = 0, T = 0)",
     "allowed": "{None of the Available Classes}", "regime": "E2"},
    {"name": "Lifting unit", "initial": "Linear Unit",
     "votes": ["Linear Unit\u00a0×2", "Combined Unit\u00a0×1"],
     "finding": "Secondary rotary component; both classes consistent with the codebook",
     "allowed": "{Linear Unit, Combined Unit}", "regime": "M"},
]
row_labels = ["Example", "Initial label", "Participant classifications",
              "Review finding", "Allowed labels after review", "Regime"]

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
def rect(x, y, w, h, fill, stroke=LINE, sw=1.6, rx=0):
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
    return n * lh

inner = COL_W - 2 * PAD
# lines for every cell
cells = []
for e in examples:
    votes = sum((wrap(v, SIZE, "normal", inner) for v in e["votes"]), [])
    cells.append({
        "initial": (wrap(e["initial"], SIZE, "normal", inner), SIZE, "normal", TXT),
        "votes": (votes, SIZE, "normal", TXT),
        "finding": (wrap(e["finding"], SIZE, "normal", inner), SIZE, "normal", TXT),
        "allowed": (wrap(e["allowed"], SIZE, "bold", inner), SIZE, "bold", DARK),
    })
label_lines = [wrap(l, HEAD_SIZE, "bold", LABEL_W - 2 * PAD) for l in row_labels]

def row_h(key, li):
    n = max([len(c[key][0]) for c in cells] + [len(label_lines[li])])
    return n * SIZE * 1.22 + 2 * 34

heights = [IMG_H + SIZE * 1.6 + 30, row_h("initial", 1), row_h("votes", 2),
           row_h("finding", 3), row_h("allowed", 4), 130]

y = Y0
for ri, h in enumerate(heights):
    # row label
    rect(X0, y, LABEL_W, h, HEAD_BG)
    text_block(X0 + LABEL_W / 2, y + h / 2, label_lines[ri], HEAD_SIZE, "bold", DARK)
    for ci, e in enumerate(examples):
        x = X0 + LABEL_W + ci * COL_W
        cx = x + COL_W / 2
        rect(x, y, COL_W, h, "white")
        if ri == 0:   # blank image area, name at the bottom
            text_block(cx, y + h - 30 - SIZE * 0.5, [e["name"]], SIZE, "italic")
        elif ri == 5:
            fill, stroke = REG[e["regime"]]
            rect(cx - 70, y + h / 2 - 40, 140, 80, fill, stroke, 2.4, rx=10)
            text_block(cx, y + h / 2, [e["regime"]], 50, "bold")
        else:
            key = ["initial", "votes", "finding", "allowed"][ri - 1]
            ls, size, weight, color = cells[ci][key]
            text_block(cx, y + h / 2, ls, size, weight, color)
    y += h

W = X0 * 2 + LABEL_W + 3 * COL_W
H = y + Y0
svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H:.0f}" '
       f'viewBox="0 0 {W} {H:.0f}"><rect width="100%" height="100%" fill="white"/>'
       + "".join(out) + "</svg>")
open("fig_4_4_regime_examples.svg", "w", encoding="utf-8").write(svg)
print(W, round(H))
