"""
Füllt in der Liste der mehrdeutigen Baugruppen die Spalten „von Mensch markiert“ aus der
Workshop-Auswertung (Blatt „Klassifikation_Übersicht_Gesamt“ bzw. eine Datei mit nur diesem Blatt).

Gezählt wird jede Klassifikation einer Person: jede nicht leere Zelle in einer Spalte, deren
Überschrift mit „TN“ beginnt (z. B. „TN A …“, „TN_B_…“). Leere Zelle = diese Person hat die
Baugruppe nicht klassifiziert. Workshop-Spalte, Ground Truth und Spalten ohne „TN“ werden ignoriert.

- „Label n“ (Mensch) = „ja (n/N)“: n von N Personen haben dieses Label gewählt; „nein (0/N)“ = niemand.
- „andere Klassen“ (Mensch) = Klassen außerhalb der Labelmenge, z. B. „GR × 2, KE × 1“.
Klassennamen werden wie in der übrigen Auswertung vereinheitlicht (z. B. Gantry -> Multi-Achs-System (Gantry));
nicht erkannte Namen werden aufgelistet und als „ungültig“ gezählt.

Beispiel (in 00_Skripte), nach fill_mehrdeutig_llm.py:
  python fill_mehrdeutig_mensch.py --mensch "..\\06_Stammdaten\\Klassifikation_Uebersicht_Gesamt.xlsx"
         --ziel "..\\05_Ergebnisse_R2\\Mehrdeutige_Baugruppen_R2_LLM.xlsx"
         --out "..\\05_Ergebnisse_R2\\Mehrdeutige_Baugruppen_R2_LLM_Mensch.xlsx"
Die Zieldatei kann schon Screenshots enthalten; sie bleiben erhalten.
"""
import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.cell_range import MultiCellRange

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluate_pdf_results as E   # noqa: E402
import evaluate_r1 as R            # noqa: E402

cm = R.cm
ABBR = R.ABBR
AUTO = "DCE6F1"
TN = re.compile(r"^\s*TN[\s_]", re.I)


def abbr(lab):
    return ABBR.get(lab, lab)


def read_mensch(path, sheet=None):
    """{key: [(person, klasse_oder_UNGÜLTIG, rohwert, excelzeile)]}, Infos."""
    xl = pd.ExcelFile(path)
    names = xl.sheet_names
    if sheet:
        cand = [sheet]
    else:
        pref = [n for n in names if "bersicht" in n.lower() and "gesamt" in n.lower()]
        cand = pref + [n for n in names if n not in pref]
    for sh in cand:
        if sh not in names:
            raise SystemExit(f"Blatt „{sh}“ nicht gefunden. Vorhandene Blätter: {names}")
        raw = xl.parse(sh, header=None, dtype=str, nrows=15)
        hr = None
        for i in range(len(raw)):
            vals = [str(v) for v in raw.iloc[i].tolist() if isinstance(v, str)]
            if any("sap" in v.lower() for v in vals) and any(TN.match(v) for v in vals):
                hr = i
                break
        if hr is not None:
            break
    else:
        raise SystemExit(f"Kein Blatt mit Spalten SAP/Teamcenter und TN… gefunden. Blätter: {names}")
    df = xl.parse(sh, header=hr, dtype=str)
    cols = [str(c) for c in df.columns]
    df.columns = cols
    c_sap = E.find_col(cols, contains=["sap"])
    c_tc = E.find_col(cols, contains=["teamcenter"])
    tn_cols = [c for c in cols if TN.match(c)]
    out, seen, dup, unknown_rows, unk_names = defaultdict(list), {}, [], [], Counter()
    for i, row in df.iterrows():
        xrow = i + hr + 2
        vals = {c: str(row[c]).strip() for c in tn_cols if not E.is_empty(row[c]) and str(row[c]).strip()}
        if not vals:
            continue
        k = cm.match_key(None if E.is_empty(row[c_sap]) else row[c_sap],
                         None if (c_tc is None or E.is_empty(row[c_tc])) else row[c_tc])
        if k is None:
            unknown_rows.append((xrow, row[c_sap], len(vals)))
            continue
        for p, v in vals.items():
            if (k, p) in seen:
                dup.append((k, p, seen[(k, p)], xrow))
                continue
            seen[(k, p)] = xrow
            lab = cm.canon(v)
            if lab.startswith("UNGÜLTIG"):
                unk_names[v] += 1
                lab = "ungültig"
            out[k].append((p, lab, v, xrow))
    info = dict(sheet=sh, header_row=hr + 1, tn_cols=tn_cols, dup=dup, unknown_rows=unknown_rows,
                unk_names=unk_names, raw_names=Counter(v for lst in out.values() for _, _, v, _ in lst))
    return out, info


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mensch", required=True, help="Excel mit den Klassifikationen der Teilnehmenden (TN…)")
    ap.add_argument("--blatt", help="Blattname (Standard: automatisch)")
    ap.add_argument("--ziel", required=True, help="Liste der mehrdeutigen BG (Vorlage oder vorbefüllt)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    ann, info = read_mensch(a.mensch, a.blatt)
    if not ann:
        raise SystemExit("Keine Klassifikationen gefunden. Falls die TN-Zellen Formeln auf andere Blätter enthalten, "
                         "das Blatt bitte als Werte einfügen (Kopieren > Einfügen als Werte) und erneut versuchen.")
    print(f"Mensch: Blatt „{info['sheet']}“, Kopfzeile {info['header_row']}, {len(info['tn_cols'])} TN-Spalten, "
          f"{sum(len(v) for v in ann.values())} Klassifikationen zu {len(ann)} Baugruppen")
    print("Klassennamen in der Tabelle -> vereinheitlicht:")
    for raw, n in sorted(info["raw_names"].items(), key=lambda x: -x[1]):
        c = cm.canon(raw)
        print(f"  {raw!r:45} -> {'UNGÜLTIG (nicht erkannt)' if c.startswith('UNGÜLTIG') else c}  ({n}×)")
    if info["unk_names"]:
        print(f"  ! nicht erkannte Klassennamen (als „ungültig“ gezählt): {dict(info['unk_names'])}")
    if info["dup"]:
        print(f"  ! {len(info['dup'])} doppelte Klassifikationen derselben Person (zweite ignoriert), "
              f"z. B. {info['dup'][0][0]} {info['dup'][0][1]} Zeilen {info['dup'][0][2]}/{info['dup'][0][3]}")
    if info["unknown_rows"]:
        print(f"  ! {len(info['unknown_rows'])} Zeilen ohne bekannte SAP/Teamcenter ignoriert, "
              f"z. B. Excel-Zeile {info['unknown_rows'][0][0]} ({info['unknown_rows'][0][1]})")

    wb = load_workbook(a.ziel)
    ws = wb.worksheets[0]
    hr = next(r for r in range(1, 20) if ws.cell(r, 3).value == "SAP Nr")
    c_sap = next(c for c in range(1, ws.max_column + 1) if ws.cell(hr, c).value == "SAP Nr")
    c_tc = next(c for c in range(1, ws.max_column + 1) if ws.cell(hr, c).value == "Teamcenter")
    c_lab = [next(c for c in range(1, ws.max_column + 1) if ws.cell(hr, c).value == f"Label {i}") for i in (1, 2, 3)]
    grp, cur = {}, None
    for c in range(1, ws.max_column + 1):
        v = ws.cell(hr - 1, c).value
        if v:
            cur = str(v)
        grp[c] = cur or ""
    hum = [c for c in range(1, ws.max_column + 1) if "Mensch" in grp[c]]
    if not hum:
        raise SystemExit("Spaltengruppe „von Mensch markiert“ im Ziel nicht gefunden.")
    c_h = [next(c for c in hum if ws.cell(hr, c).value == f"Label {i}") for i in (1, 2, 3)]
    c_ho = next(c for c in hum if ws.cell(hr, c).value == "andere Klassen")

    # ja/nein-Auswahl von den Mensch-Zellen entfernen (dort steht jetzt „ja (n/N)“)
    hcols = {get_column_letter(c) for c in c_h}
    for dv in ws.data_validations.dataValidation:
        keep = [rg for rg in str(dv.sqref).split() if re.match(r"[A-Z]+", rg).group(0) not in hcols]
        dv.sqref = MultiCellRange(" ".join(keep)) if keep else MultiCellRange()
    ws.data_validations.dataValidation = [d for d in ws.data_validations.dataValidation if str(d.sqref).strip()]

    r, filled, none = hr + 1, 0, []
    while ws.cell(r, c_sap).value or ws.cell(r, c_tc).value:
        k = cm.match_key(ws.cell(r, c_sap).value, ws.cell(r, c_tc).value)
        labs = [ws.cell(r, c).value for c in c_lab]
        labs = [cm.canon(x) if x and x != "–" else None for x in labs]
        lst = ann.get(k, [])
        N = len(lst)
        cnt = Counter(lab for _, lab, _, _ in lst)
        for n, lab in enumerate(labs):
            if not lab:
                continue
            c = ws.cell(r, c_h[n], (f"ja ({cnt[lab]}/{N})" if cnt[lab] else f"nein (0/{N})") if N else "–")
            c.fill = PatternFill("solid", fgColor=AUTO)
            c.alignment = Alignment(horizontal="center", vertical="top", wrap_text=True)
        other = {l_: n_ for l_, n_ in cnt.items() if l_ not in labs}
        txt = ", ".join(f"{abbr(l_)} × {n_}" for l_, n_ in sorted(other.items(), key=lambda x: (-x[1], x[0])))
        c = ws.cell(r, c_ho, (txt or "–") if N else "–")
        c.fill = PatternFill("solid", fgColor=AUTO)
        c.alignment = Alignment(horizontal="center", vertical="top", wrap_text=True)
        if N:
            filled += 1
        else:
            none.append(str(ws.cell(r, c_sap).value or ws.cell(r, c_tc).value))
        r += 1

    if "Hinweise" in wb.sheetnames:
        h = wb["Hinweise"]
        rr = h.max_row + 2
        for t in ["„von Mensch markiert“: ja (n/N) = n von N Personen (Workshop) haben dieses Label gewählt; "
                  "nein (0/N) = niemand; „andere Klassen“ = Wahl außerhalb der Labelmenge. Die Zahlen ergeben zusammen N. "
                  "„–“ = keine Klassifikation durch Personen vorhanden."]:
            h.cell(rr, 2, t).alignment = Alignment(wrap_text=True)
            rr += 1

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    print(f"Ziel: {filled} Baugruppen mit Klassifikationen gefüllt"
          + (f"; ohne Klassifikation durch Personen: {', '.join(none)}" if none else ""))
    print(f"Ausgabe: {out}")


if __name__ == "__main__":
    main()
