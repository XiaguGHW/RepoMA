"""Generate Figure 4.3: simplified structure of the workshop classification template.

Ausgabe: fig_4_3_workshop_template.svg (+ .png und .pdf über rsvg-convert, falls vorhanden).

Ausgelegt für Word in voller Textbreite (ca. 16 cm): Breite ca. 1000 px, Schriftgrößen so gewählt,
dass Kopfzeilen etwa 9 pt und Hinweise etwa 7,5 pt groß erscheinen. Schrift: Arial
(Liberation Sans ist metrisch identisch und dient nur als Ersatz, wenn Arial fehlt).
"""
import shutil
import subprocess
from xml.sax.saxutils import escape

FONT = "Arial, 'Liberation Sans', Helvetica, sans-serif"
DARK = "#1F4E8C"; LINE = "#9FB3CF"; GREY_BG = "#F4F6F9"; BLUE_BG = "#DCE6F2"
TXT = "#222222"; MUTED = "#555555"

# Schriftgrößen (px im SVG; bei ca. 1000 px Breite in 16 cm Textbreite: px * 0.45 ≈ pt)
F_GROUP = 19      # Gruppenleiste
F_HEAD = 19       # Spaltenköpfe
F_CELL = 18       # „…“, „auto“
F_HINT = 16.5     # Hinweise unter der Tabelle

groups = [
    ("Provided for each assembly", GREY_BG, "#555555", [
        (["Assembly", "ID"], 112), (["Designation", "(EN/DE)"], 128), (["Image"], 92)]),
    ("Entered by the participant", BLUE_BG, DARK, [
        (["Class*"], 96), (["Confidence*"], 152), (["Second", "choice"], 100),
        (["Decisive", "source"], 110), (["Note"], 116)]),
    ("Recorded", GREY_BG, "#555555", [(["Timestamp"], 120)]),
]
hints = {
    "Class*": ["one of the", "seven", "classes"],
    "Confidence*": ["certain /", "rather certain /", "rather uncertain /", "uncertain"],
    "Second choice": ["if another", "class is", "plausible"],
    "Decisive source": ["if documents", "beyond the", "template", "were used"],
    "Note": ["if uncertain,", "class 7 or", "second choice"],
    "Timestamp": ["automatically", "for each entry"],
}
GAP = 12; X0 = 8; Y0 = 8
GROUP_H = 40; HEAD_H = 58; ROW_H = 46; N_ROWS = 3
LINE_H = F_HINT * 1.22

out = []


def rect(x, y, w, h, fill, stroke=LINE, sw=1.4):
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')


def text(x, y, s, size, weight="normal", color=TXT, style="normal", anchor="middle"):
    # Grundlinie so setzen, dass die Glyphen optisch auf y zentriert sind
    y = y + (size * 0.12 if s == "…" else size * 0.36)
    out.append(f'<text x="{x}" y="{y:.1f}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" '
               f'font-style="{style}" fill="{color}" text-anchor="{anchor}">{escape(s)}</text>')


def lines(x, yc, parts, size, **kw):
    """Mehrzeiliger Text, vertikal um yc zentriert."""
    lh = size * 1.18
    y = yc - (len(parts) - 1) * lh / 2
    for i, p in enumerate(parts):
        text(x, y + i * lh, p, size, **kw)


x = X0
table_top = Y0 + GROUP_H
table_bottom = table_top + HEAD_H + N_ROWS * ROW_H
max_hint = max(len(v) for v in hints.values())
for gi, (gname, gbg, gcol, cols) in enumerate(groups):
    gw = sum(w for _, w in cols)
    rect(x, Y0, gw, GROUP_H - 7, gcol, gcol)
    text(x + gw / 2, Y0 + (GROUP_H - 7) / 2, gname, F_GROUP, "bold", "white")
    cx = x
    for cparts, w in cols:
        cname = " ".join(cparts)
        rect(cx, table_top, w, HEAD_H, gbg)
        lines(cx + w / 2, table_top + HEAD_H / 2, cparts, F_HEAD, weight="bold", color=gcol)
        for r in range(N_ROWS):
            ry = table_top + HEAD_H + r * ROW_H
            rect(cx, ry, w, ROW_H, "white")
            last = r == N_ROWS - 1
            if gi == 0 and cname == "Image" and not last:     # Bildplatzhalter
                px, py, pw, ph = cx + 20, ry + 7, w - 40, ROW_H - 14
                rect(px, py, pw, ph, "#E3E6EA", "#B8BEC6", 1)
                out.append(f'<polygon points="{px+5},{py+ph-5} {px+pw*0.42},{py+ph*0.35} '
                           f'{px+pw*0.62},{py+ph*0.62} {px+pw*0.75},{py+ph*0.48} {px+pw-5},{py+ph-5}" fill="#B8BEC6"/>')
                out.append(f'<circle cx="{px+pw*0.75}" cy="{py+ph*0.28}" r="3.5" fill="#B8BEC6"/>')
            elif gi == 2:
                text(cx + w / 2, ry + ROW_H / 2, "…" if last else "auto", F_CELL, color=MUTED, style="italic")
            elif gi == 0 or last:
                text(cx + w / 2, ry + ROW_H / 2, "…", F_CELL, color=MUTED)
        if cname in hints:
            for li, h in enumerate(hints[cname]):
                text(cx + w / 2, table_bottom + 16 + li * LINE_H, h, F_HINT, color=MUTED, style="italic")
        cx += w
    x += gw + GAP

width = round(x - GAP + X0)
foot_y = table_bottom + 16 + max_hint * LINE_H + 6
text(X0, foot_y, "* mandatory field", F_HINT, color=MUTED, anchor="start")
height = round(foot_y + F_HINT)

svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
       f'<rect width="100%" height="100%" fill="white"/>' + "".join(out) + "</svg>")
open("fig_4_3_workshop_template.svg", "w", encoding="utf-8").write(svg)
print("SVG", width, "x", height)

# PNG (300 dpi bei 16 cm Breite ≈ 1890 px) und PDF
if shutil.which("rsvg-convert"):
    subprocess.run(["rsvg-convert", "-w", "1890", "-b", "white", "-o", "fig_4_3_workshop_template.png",
                    "fig_4_3_workshop_template.svg"], check=True)
    subprocess.run(["rsvg-convert", "-f", "pdf", "-o", "fig_4_3_workshop_template.pdf",
                    "fig_4_3_workshop_template.svg"], check=True)
    print("PNG und PDF erzeugt")
