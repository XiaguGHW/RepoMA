"""Generate Figure 4.3: simplified structure of the workshop classification template."""
from xml.sax.saxutils import escape

FONT = "Liberation Sans"
DARK = "#1F4E8C"; LINE = "#9FB3CF"; GREY_BG = "#F4F6F9"; BLUE_BG = "#DCE6F2"
TXT = "#222222"; MUTED = "#666666"

groups = [
    ("Provided for each assembly", GREY_BG, "#555555", [
        ("Assembly ID", 130), ("Designation (EN/DE)", 170), ("Image", 100)]),
    ("Entered by the participant", BLUE_BG, DARK, [
        ("Class*", 120), ("Confidence*", 128), ("Second choice", 122),
        ("Decisive source", 122), ("Note", 132)]),
    ("Recorded automatically", GREY_BG, "#555555", [("Timestamp", 180)]),
]
hints = {
    "Class*": ["one of the", "seven classes"],
    "Confidence*": ["certain / rather certain /", "rather uncertain / uncertain"],
    "Second choice": ["if another class", "is plausible"],
    "Decisive source": ["if documents beyond", "the template were used"],
    "Note": ["if uncertain, class 7", "or second choice"],
    "Timestamp": ["for each entry"],
}
GAP = 16; X0 = 20; Y0 = 20
GROUP_H = 34; HEAD_H = 48; ROW_H = 62; N_ROWS = 3; HINT_H = 50

out = []
def rect(x, y, w, h, fill, stroke=LINE, sw=1.2):
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')
def text(x, y, s, size=15, weight="normal", color=TXT, style="normal", anchor="middle"):
    # place baseline so the glyphs are visually centred on y
    y = y + (size * 0.12 if s == "…" else size * 0.36)
    out.append(f'<text x="{x}" y="{y:.1f}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" '
               f'font-style="{style}" fill="{color}" text-anchor="{anchor}">{escape(s)}</text>')

x = X0
table_top = Y0 + GROUP_H
table_bottom = table_top + HEAD_H + N_ROWS * ROW_H
for gi, (gname, gbg, gcol, cols) in enumerate(groups):
    gw = sum(w for _, w in cols)
    # group label bar
    rect(x, Y0, gw, GROUP_H - 6, gcol, gcol)
    text(x + gw / 2, Y0 + (GROUP_H - 6) / 2, gname, 14, "bold", "white")
    cx = x
    for cname, w in cols:
        # header cell
        rect(cx, table_top, w, HEAD_H, gbg)
        text(cx + w / 2, table_top + HEAD_H / 2, cname, 14, "bold", gcol)
        for r in range(N_ROWS):
            ry = table_top + HEAD_H + r * ROW_H
            rect(cx, ry, w, ROW_H, "white")
            last = r == N_ROWS - 1
            if gi == 0:
                if cname == "Image":
                    if not last:  # simple image placeholder
                        px, py, pw, ph = cx + 22, ry + 9, w - 44, ROW_H - 18
                        rect(px, py, pw, ph, "#E3E6EA", "#B8BEC6", 1)
                        out.append(f'<polygon points="{px+6},{py+ph-6} {px+pw*0.42},{py+ph*0.35} '
                                   f'{px+pw*0.62},{py+ph*0.62} {px+pw*0.75},{py+ph*0.48} {px+pw-6},{py+ph-6}" fill="#B8BEC6"/>')
                        out.append(f'<circle cx="{px+pw*0.75}" cy="{py+ph*0.28}" r="4" fill="#B8BEC6"/>')
                    else:
                        text(cx + w / 2, ry + ROW_H / 2, "…", 15, color=MUTED)
                else:
                    text(cx + w / 2, ry + ROW_H / 2, "…", 15, color=MUTED)
            elif gi == 2:
                text(cx + w / 2, ry + ROW_H / 2, "…" if last else "auto", 14, color=MUTED, style="italic")
            elif last:
                text(cx + w / 2, ry + ROW_H / 2, "…", 15, color=MUTED)
        # hint below table
        if cname in hints:
            for li, line in enumerate(hints[cname]):
                text(cx + w / 2, table_bottom + 18 + li * 17, line, 12.5, color=MUTED, style="italic")
        cx += w
    x += gw + GAP

width = x - GAP + X0
foot_y = table_bottom + HINT_H + 10
text(X0, foot_y, "* mandatory field", 12.5, color=MUTED, anchor="start")
height = foot_y + 18

svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
       f'<rect width="100%" height="100%" fill="white"/>' + "".join(out) + "</svg>")
open("fig_4_3_workshop_template.svg", "w", encoding="utf-8").write(svg)
print(width, height)
