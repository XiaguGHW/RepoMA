"""
Erzeugt die Vorlage „Mehrdeutige_Baugruppen_R2_Begruendung.xlsx“ aus R2.md.

  python make_vorlage_mehrdeutig.py --gt R2.md --out Mehrdeutige_Baugruppen_R2_Begruendung.xlsx
"""
import argparse
import re
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as gl
from openpyxl.worksheet.datavalidation import DataValidation

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluate_r1 as R   # noqa: E402

cm = R.cm
GREY, RED, YEL, NA = "D9D9D9", "C00000", "FFF2CC", "F2F2F2"
thin, thick = Side(style="thin", color="BFBFBF"), Side(style="medium", color=RED)
ABBR = R.ABBR

# (Kopf Zeile 2, Breite); Gruppen in Zeile 1
COLS = [("Nr.", 5), ("SAP Nr", 15), ("Teamcenter", 14), ("Datensatz", 16), ("Screenshot", 28),
        ("Label 1", 22), ("Grund Label 1", 40), ("Label 2", 22), ("Grund Label 2", 40),
        ("Label 3", 22), ("Grund Label 3", 40),
        ("Label 1", 11), ("Label 2", 11), ("Label 3", 11), ("andere Klassen", 24),
        ("Label 1", 11), ("Label 2", 11), ("Label 3", 11), ("andere Klassen", 24)]
GROUPS = [(2, 6, ""), (7, 12, "Zulässige Labels und Begründung"),
          (13, 16, "von Mensch markiert"), (17, 20, "von LLM markiert")]


def read_gt_rows(path):
    L = Path(path).read_text(encoding="utf-8").splitlines()
    hi = next(i for i, l in enumerate(L) if l.startswith("|") and "SAP-Nummer" in l)
    rows = []
    for l in L[hi + 2:]:
        if not l.startswith("|"):
            continue
        c = [x.strip() for x in l.strip().strip("|").split("|")] + [""] * 6
        alts = [a.strip() for a in re.split(r"[,;]", c[4]) if a.strip()]
        if c[3] == "M" and alts:
            k = cm.match_key(c[0] or None, c[1] or None)
            rows.append(dict(sap=c[0], tc=c[1], labels=[c[2]] + alts, lk=c[5].lower() == "yes",
                             main=k in set(cm.MAIN_115)))
    rows.sort(key=lambda r: (r["lk"], not r["main"]))
    return rows



def save_safe(wb, out):
    """Speichern; ist die Datei in Excel geöffnet, unter neuem Namen mit Uhrzeit speichern."""
    try:
        wb.save(out)
        return out
    except PermissionError:
        import datetime
        alt = out.with_name(f"{out.stem}_{datetime.datetime.now():%H-%M-%S}{out.suffix}")
        print(f"  ! {out.name} ist geöffnet (Excel?) – gespeichert als {alt.name}")
        wb.save(alt)
        return alt

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--gt", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    gt_name = (re.match(r"(R\d+)", Path(a.gt).stem, re.I) or [Path(a.gt).stem])[0].upper()
    rows = read_gt_rows(a.gt)

    wb = Workbook()
    ws = wb.active
    ws.title = f"Mehrdeutige BG ({gt_name})"
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 2
    ws.cell(2, 2, f"Mehrdeutige Baugruppen (Ground Truth {gt_name}) – Begründung der zulässigen Labels").font = Font(bold=True, size=13)
    ws.cell(3, 2, f"{len(rows)} Baugruppen mit mehreren zulässigen Labels; Label 1 = Hauptlabel in {gt_name}, "
                  "Label 2/3 = weitere zulässige Labels. Gelb = auszufüllen.").font = Font(size=10, italic=True)
    hr = 5
    for c1, c2, txt in GROUPS:
        if txt:
            ws.merge_cells(start_row=hr, start_column=c1, end_row=hr, end_column=c2)
        for j in range(c1, c2 + 1):
            c = ws.cell(hr, j)
            c.fill = PatternFill("solid", fgColor=GREY)
            c.border = Border(left=thin, right=thin, top=thin, bottom=thin)
        ws.cell(hr, c1, txt or None).font = Font(bold=True)
        ws.cell(hr, c1).alignment = Alignment(horizontal="center", vertical="center")
    for j, (h, w) in enumerate(COLS):
        col = 2 + j
        ws.column_dimensions[gl(col)].width = w
        c = ws.cell(hr + 1, col, h)
        c.font, c.fill = Font(bold=True), PatternFill("solid", fgColor=GREY)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = Border(left=thin, right=thin, top=thin, bottom=thick)
    ws.row_dimensions[hr + 1].height = 30

    dv = DataValidation(type="list", formula1='"ja,nein"', allow_blank=True)
    ws.add_data_validation(dv)
    first = hr + 2
    for i, r in enumerate(rows):
        rr = first + i
        labs = r["labels"] + [""] * (3 - len(r["labels"]))
        has3 = bool(labs[2])
        ds = "Label-Konfig." if r["lk"] else ("115 BG" if r["main"] else "70 BG")
        vals = [i + 1, r["sap"] or None, r["tc"] or None, ds, None,
                labs[0], None, labs[1], None, labs[2] or "–", None if has3 else "–",
                None, None, None if has3 else "–", None,
                None, None, None if has3 else "–", None]
        for j, v in enumerate(vals):
            col = 2 + j
            c = ws.cell(rr, col, v)
            c.border = Border(left=thin, right=thin, top=thin, bottom=thin)
            center = col in (2, 5) or col >= 13
            c.alignment = Alignment(horizontal="center" if center else "left", vertical="top",
                                    wrap_text=True, indent=0 if center else 1)
            missing3 = (not has3) and col in (11, 12, 15, 19)
            if missing3:
                c.fill = PatternFill("solid", fgColor=NA)
            elif col in (6, 8, 10, 12, 13, 14, 15, 16, 17, 18, 19, 20):
                c.fill = PatternFill("solid", fgColor=YEL)
                if col in (13, 14, 15, 17, 18, 19):
                    dv.add(c)
        ws.row_dimensions[rr].height = 150
    last = first + len(rows) - 1
    for j in range(2, 2 + len(COLS)):
        ws.cell(last, j).border = Border(left=thin, right=thin, top=thin, bottom=thick)
    ws.freeze_panes = ws.cell(first, 7)
    ws.auto_filter.ref = f"B{hr + 1}:{gl(1 + len(COLS))}{last}"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"{hr}:{hr + 1}"

    h = wb.create_sheet("Hinweise")
    h.sheet_view.showGridLines = False
    h.column_dimensions["A"].width = 2
    h.column_dimensions["B"].width = 110
    abbr = ", ".join(f"{v} = {k}" for k, v in ABBR.items())
    notes = [("Hinweise zum Ausfüllen", True),
             (f"Grundlage: Ground Truth {gt_name}. Aufgeführt sind alle Baugruppen mit Register M und weiteren zulässigen Labels.", False),
             ("Datensatz: 115 BG / 70 BG = in der Auswertung enthalten; „Label-Konfig.“ = eine der 14 Baugruppen aus der "
              "Label-Konfiguration (nicht ausgewertet, am Ende der Liste).", False),
             (f"Label 1 = Hauptlabel in {gt_name}; Label 2 und 3 = weitere zulässige Labels.", False),
             ("Screenshot: Bild in die Zelle einfügen (Einfügen > Bilder > Bild in Zelle platzieren) oder Dateiname/Link eintragen.", False),
             ("Grund Label n: Begründung, warum das Label für diese Baugruppe zulässig ist.", False),
             ("von LLM / von Mensch markiert, Label n: ja/nein, ob das Label vergeben wurde.", False),
             ("andere Klassen: welche Klassen außerhalb der Labelmenge vergeben wurden und wie oft, z. B. „GR × 2, RO × 1“.", False),
             (f"Kürzel: {abbr}.", False),
             ("Gelbe Zellen sind auszufüllen. Grau mit „–“ = kein Label 3.", False)]
    for i, (t, b) in enumerate(notes):
        c = h.cell(2 + i, 2, t)
        c.font = Font(bold=b, size=13 if b else 11)
        c.alignment = Alignment(wrap_text=True, vertical="top")

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out = save_safe(wb, out)
    print(f"{len(rows)} Baugruppen -> {out}")


if __name__ == "__main__":
    main()
