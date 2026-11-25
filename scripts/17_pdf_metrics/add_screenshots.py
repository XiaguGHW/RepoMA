"""
Kopiert die CAD-Screenshots aus einer Stammdaten-Tabelle (Spalte „Abbildung“) in die Spalte „Screenshot“
einer Zieltabelle (z. B. Mehrdeutige_Baugruppen_R2_Begruendung.xlsx bzw. die mit fill_mehrdeutig_llm.py
vorbefüllte Datei). Zuordnung über SAP-Nummer bzw. Teamcenter.

Die Bilder werden mit Seitenverhältnis in die Zelle eingepasst (mit Rand, zentriert) und mit der Zelle
verankert – sie überdecken keine Nachbarzellen, egal ob quadratisch, hoch oder breit.

Erkannt werden in der Quelle beide Arten von Bildern:
- „über den Zellen“ eingefügte Bilder (normales Einfügen), zugeordnet über die Zeile, in der das Bild liegt;
- „in der Zelle platzierte“ Bilder (Einfügen > Bild in Zelle platzieren).

Beispiel (in 00_Skripte):
  python add_screenshots.py --quelle "..\\06_Stammdaten\\<Tabelle>.xlsx"
         --ziel "..\\05_Ergebnisse_R2\\Mehrdeutige_Baugruppen_R2_LLM.xlsx"
         --out "..\\05_Ergebnisse_R2\\Mehrdeutige_Baugruppen_R2_LLM_Bilder.xlsx"
Bitte als letzten Schritt ausführen (nach fill_mehrdeutig_llm.py).
"""
import argparse
import io
import posixpath
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from openpyxl import load_workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, OneCellAnchor
from openpyxl.drawing.xdr import XDRPositiveSize2D
from openpyxl.utils import column_index_from_string, get_column_letter
from openpyxl.utils.units import pixels_to_EMU
from PIL import Image as PILImage

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluate_r1 as R   # noqa: E402

cm = R.cm
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
      "rv": "http://schemas.microsoft.com/office/spreadsheetml/2017/richdata",
      "rvr": "http://schemas.microsoft.com/office/spreadsheetml/2022/richvaluerel",
      "xlrd": "http://schemas.microsoft.com/office/spreadsheetml/2017/richdata"}


def find_header(ws, names, max_rows=15):
    """Zeile und Spalten der gesuchten Überschriften (Teilstring, ohne Groß/Klein)."""
    for r in range(1, max_rows + 1):
        found = {}
        for c in range(1, ws.max_column + 1):
            v = ws.cell(r, c).value
            if v is None:
                continue
            t = str(v).strip().lower()
            for key, pats in names.items():
                if key not in found and any(p in t for p in pats):
                    found[key] = c
        if "sap" in found or "tc" in found:
            return r, found
    raise SystemExit(f"Keine Kopfzeile mit SAP/Teamcenter in „{ws.title}“ gefunden.")


# ---------------------------------------------------------------- Bilder „in der Zelle“
def in_cell_images(path, sheet_name):
    """{(zeile, spalte): bytes} für Bilder, die per „Bild in Zelle platzieren“ eingefügt wurden."""
    try:
        return _in_cell_images(path, sheet_name)
    except Exception as e:     # unbekannte Variante des Dateiformats -> nur die übrigen Bilder verwenden
        print(f"  ! Bilder in Zellen konnten nicht gelesen werden ({type(e).__name__}: {e})")
        return {}


def _in_cell_images(path, sheet_name):
    out = {}
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        if "xl/richData/rdrichvalue.xml" not in names:
            return out
        # Arbeitsblatt-Datei des gewünschten Blatts
        wbx = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        if "xl/metadata.xml" not in names or "xl/richData/richValueRel.xml" not in names:
            return out
        rid = next(s_.get(f"{{{NS['r']}}}id") for s_ in wbx.findall("m:sheets/m:sheet", NS) if s_.get("name") == sheet_name)
        target = next(x.get("Target") for x in rels if x.get("Id") == rid)
        sheet_path = target.lstrip("/") if target.startswith("/") else posixpath.join("xl", target)
        # vm -> Rich-Value-Index
        meta = ET.fromstring(z.read("xl/metadata.xml"))
        fut = []
        for fm in meta.findall("m:futureMetadata", NS):
            if fm.get("name") == "XLRICHVALUE":
                for bk in fm.findall("m:bk", NS):
                    rvb = bk.find(".//xlrd:rvb", NS)
                    fut.append(int(rvb.get("i")) if rvb is not None else None)
        vm_to_rv = []
        vmeta = meta.find("m:valueMetadata", NS)
        for bk in (vmeta.findall("m:bk", NS) if vmeta is not None else []):
            rc = bk.find("m:rc", NS)
            v = int(rc.get("v")) if rc is not None else None
            vm_to_rv.append(fut[v] if v is not None and v < len(fut) else None)
        # Rich Value -> Bild-Relation
        # Position des Schlüssels „_rvRel:LocalImageIdentifier“ je Struktur (meist 0)
        key_pos = []
        if "xl/richData/rdrichvaluestructure.xml" in names:
            sx_ = ET.fromstring(z.read("xl/richData/rdrichvaluestructure.xml"))
            for st in sx_.findall("rv:s", NS):
                ks = [k.get("n") for k in st.findall("rv:k", NS)]
                key_pos.append(ks.index("_rvRel:LocalImageIdentifier") if "_rvRel:LocalImageIdentifier" in ks else None)
        rvx = ET.fromstring(z.read("xl/richData/rdrichvalue.xml"))
        rv_first = []
        for rv in rvx.findall("rv:rv", NS):
            vs = rv.findall("rv:v", NS)
            si = int(rv.get("s", 0))
            pos = key_pos[si] if si < len(key_pos) else 0
            v = vs[pos] if pos is not None and pos < len(vs) else None
            rv_first.append(int(v.text) if v is not None and (v.text or "").strip().isdigit() else None)
        relx = ET.fromstring(z.read("xl/richData/richValueRel.xml"))
        rel_ids = [x.get(f"{{{NS['r']}}}id") for x in relx]
        rr = ET.fromstring(z.read("xl/richData/_rels/richValueRel.xml.rels"))
        rel_target = {x.get("Id"): posixpath.normpath(posixpath.join("xl/richData", x.get("Target"))) for x in rr}
        sx = ET.fromstring(z.read(sheet_path))
        for c in sx.iter(f"{{{NS['m']}}}c"):
            vm = c.get("vm")
            if not vm:
                continue
            try:
                rv_i = vm_to_rv[int(vm) - 1]
                img_i = rv_first[rv_i]
                media = rel_target[rel_ids[img_i]]
            except (IndexError, KeyError, TypeError):
                continue
            m = re.match(r"([A-Z]+)(\d+)", c.get("r"))
            out[(int(m.group(2)), column_index_from_string(m.group(1)))] = z.read(media)
    return out


# ---------------------------------------------------------------- Bilder „über den Zellen“
def floating_images(ws):
    """[(zeile_oben, zeile_mitte, spalte, bytes)] (1-basiert)."""
    out = []
    for img in ws._images:
        a = img.anchor
        fr = getattr(a, "_from", None)
        if fr is None:
            continue
        r0, c0 = fr.row + 1, fr.col + 1
        to = getattr(a, "to", None)
        if to is not None:
            mid = (fr.row + to.row) / 2 + 1
        else:                                   # OneCellAnchor: Mitte über die Bildhöhe bestimmen
            ext = getattr(a, "ext", None)
            half = (ext.height / 9525 / 2 if ext is not None and ext.height else 0) + fr.rowOff / 9525
            mid, acc = r0, 0
            while acc + row_px(ws, mid) < half and mid < r0 + 50:
                acc += row_px(ws, mid)
                mid += 1
        data = img._data()
        out.append((r0, round(mid), c0, data))
    return out


def col_px(ws, col):
    w = ws.column_dimensions[get_column_letter(col)].width or 8.43
    return int(w * 7 + 5)


def row_px(ws, row):
    h = ws.row_dimensions[row].height or 15
    return int(h * 96 / 72)



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
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quelle", required=True, help="Tabelle mit SAP-Nummer, Teamcenter und Abbildung")
    ap.add_argument("--ziel", required=True, help="Tabelle mit Spalte „Screenshot“")
    ap.add_argument("--out", required=True)
    ap.add_argument("--blatt", help="Blatt der Quelle (Standard: erstes Blatt mit Spalte „Abbildung“)")
    ap.add_argument("--rand", type=int, default=4, help="Rand in Pixeln (Standard 4)")
    ap.add_argument("--zeilenhoehe", type=float, default=None,
                    help="Zeilenhöhe der Zielzeilen in pt setzen (z. B. 110 für größere Bilder)")
    a = ap.parse_args(argv)

    # Quelle
    qwb = load_workbook(a.quelle)
    q_idx = None
    for i_, sh in enumerate(qwb.worksheets):
        if a.blatt and sh.title != a.blatt:
            continue
        try:
            hr_, cols_ = find_header(sh, {"sap": ["sap"], "tc": ["teamcenter"], "img": ["abbildung"]})
        except SystemExit:
            continue
        if "img" in cols_:
            q_idx, q_hr, q_cols = i_, hr_, cols_
            break
    if q_idx is None:
        raise SystemExit("In der Quelle kein Blatt mit den Spalten SAP-Nummer/Teamcenter und „Abbildung“ gefunden"
                         + (f" (gesucht: „{a.blatt}“; vorhanden: {', '.join(qwb.sheetnames)})" if a.blatt else "") + ".")
    qws = qwb.worksheets[q_idx]
    if len(qwb.worksheets) > 1:
        print(f"Quelle: Blatt „{qws.title}“")
    c_img = q_cols["img"]
    key_of_row = {}
    for r in range(q_hr + 1, qws.max_row + 1):
        sap = qws.cell(r, q_cols["sap"]).value if "sap" in q_cols else None
        tc = qws.cell(r, q_cols["tc"]).value if "tc" in q_cols else None
        k = cm.match_key(sap, tc)
        if k:
            key_of_row[r] = k
    pics = {}
    for (r, c), data in in_cell_images(a.quelle, qws.title).items():
        if c == c_img and r in key_of_row:
            pics.setdefault(key_of_row[r], data)
    n_cell = len(pics)
    off_col, dup = 0, []
    for r0, mid, c, data in floating_images(qws):
        if abs(c - c_img) > 1:
            off_col += 1
            continue
        r = mid if mid in key_of_row else r0
        if r in key_of_row:
            if key_of_row[r] in pics:
                dup.append(key_of_row[r])
            pics.setdefault(key_of_row[r], data)
    print(f"Quelle: {len(key_of_row)} Baugruppen, {len(pics)} mit Bild "
          f"({n_cell} in Zellen, {len(pics) - n_cell} über den Zellen)"
          + (f"; {off_col} Bilder außerhalb der Spalte „Abbildung“ ignoriert" if off_col else ""))
    if dup:
        print(f"  ! mehrere Bilder für: {', '.join(sorted(set(dup)))} – jeweils das erste verwendet")

    # Ziel
    wb = load_workbook(a.ziel)
    ws = wb.worksheets[0]
    t_hr, t_cols = find_header(ws, {"sap": ["sap nr", "sap-nummer", "sap"], "tc": ["teamcenter"], "img": ["screenshot"]})
    if "img" not in t_cols:
        raise SystemExit("Spalte „Screenshot“ im Ziel nicht gefunden.")
    c_shot = t_cols["img"]
    # vorhandene Bilder in der Screenshot-Spalte entfernen (bei erneutem Lauf)
    ws._images = [im for im in ws._images if getattr(im.anchor, "_from", None) is None
                  or im.anchor._from.col + 1 != c_shot]
    placed, missing = 0, []
    r = t_hr + 1
    while ws.cell(r, t_cols.get("sap", 1)).value or ws.cell(r, t_cols.get("tc", 1)).value:
        k = cm.match_key(ws.cell(r, t_cols["sap"]).value if "sap" in t_cols else None,
                         ws.cell(r, t_cols["tc"]).value if "tc" in t_cols else None)
        data = pics.get(k)
        if a.zeilenhoehe:
            ws.row_dimensions[r].height = a.zeilenhoehe
        if not data:
            missing.append(str(ws.cell(r, t_cols["sap"]).value or ws.cell(r, t_cols["tc"]).value))
            r += 1
            continue
        try:
            pil = PILImage.open(io.BytesIO(data))
            pil.load()
        except Exception as e:
            missing.append(f"{ws.cell(r, t_cols['sap']).value or ws.cell(r, t_cols['tc']).value} (Bildformat nicht lesbar: {e})")
            r += 1
            continue
        w0, h0 = pil.size
        box_w, box_h = col_px(ws, c_shot) - 2 * a.rand, row_px(ws, r) - 2 * a.rand
        s = min(box_w / w0, box_h / h0)
        w, h = max(1, int(w0 * s)), max(1, int(h0 * s))
        pil = pil.convert("RGBA" if pil.mode in ("RGBA", "LA", "P") else "RGB")
        if pil.width > 3 * w:                       # Datei klein halten, 3-fache Auflösung bleibt scharf
            pil = pil.resize((3 * w, max(1, int(3 * w * h0 / w0))), PILImage.LANCZOS)
        buf = io.BytesIO()
        pil.save(buf, format="PNG")
        buf.seek(0)
        img = XLImage(buf)
        img.width, img.height = w, h
        off_x = a.rand + (box_w - w) // 2
        off_y = a.rand + (box_h - h) // 2
        marker = AnchorMarker(col=c_shot - 1, colOff=pixels_to_EMU(off_x), row=r - 1, rowOff=pixels_to_EMU(off_y))
        img.anchor = OneCellAnchor(_from=marker, ext=XDRPositiveSize2D(pixels_to_EMU(w), pixels_to_EMU(h)))
        ws.add_image(img)
        ws.cell(r, c_shot).value = None
        placed += 1
        r += 1
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out = save_safe(wb, out)
    print(f"Ziel: {placed} Bilder eingefügt" + (f"; ohne Bild: {', '.join(missing)}" if missing else ""))
    print(f"Ausgabe: {out}")


if __name__ == "__main__":
    main()
