"""
Füllt die Vorlage „Mehrdeutige_Baugruppen_R2_Begruendung.xlsx“ aus allen LLM-Ergebnisdateien vor.

Für jede mehrdeutige Baugruppe und jedes Label der Labelmenge:
- „Label n von LLM markiert“ = „ja (n/N)“: n von N gültigen Vorhersagen (alle Modelle, alle Läufe) sind dieses Label;
  „nein (0/N)“ = nie vorhergesagt.
- „andere Klassen“ (LLM) = Vorhersagen außerhalb der Labelmenge, z. B. „GR × 2, RO × 1“ (Summe aller Zahlen = N).
- Blatt „LLM-Häufigkeiten“: dasselbe je Modell. „Grund Label n“ und die Mensch-Spalten bleiben unverändert.
- Blatt „LLM-Reasoning“: alle Läufe zu den mehrdeutigen Baugruppen mit vollständigem Reasoning.
Die Spalten „von Mensch markiert“ und „Screenshot“ werden nicht verändert.

Beispiel (in 00_Skripte):
  python fill_mehrdeutig_llm.py --dir "..\\01_Prompt_P1-P4" --dir "..\\02_Input_P3" --dir "..\\03_Wiederholung_10runs"
         --vorlage Mehrdeutige_Baugruppen_R2_Begruendung.xlsx --out "..\\05_Ergebnisse_R2\\Mehrdeutige_Baugruppen_R2_LLM.xlsx"
"""
import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.cell_range import MultiCellRange

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluate_pdf_results as E          # noqa: E402
import evaluate_r1 as R                    # noqa: E402
import evaluate_r1_ergebnisse as X         # noqa: E402

cm = R.cm
ABBR = R.ABBR
MODEL_PRIO = ["Gemini 2.5 Pro", "Claude Opus 4.8", "Gemini 2.5 Flash", "GPT-5.5", "Claude Haiku 4.5", "DeepSeek-V4-Flash"]
AUTO = "DCE6F1"     # hellblau = automatisch vorbefüllt
MAX_GRUND = 600
_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def clean(v):
    """Text für Excel: Steuerzeichen entfernen, auf Zellgrenze kürzen."""
    if not isinstance(v, str):
        return v
    v = _ILLEGAL.sub(" ", v)
    return v if len(v) <= 32000 else v[:32000] + " …"


def norm(pred):
    """Alle nicht erkannten Vorhersagen zu einer Kategorie „ungültig“ zusammenfassen."""
    return "ungültig" if str(pred).startswith("UNGÜLTIG") else pred


def put(ws, r, c, v):
    """Wert als Text schreiben (auch wenn er mit „=“ beginnt – keine Formel)."""
    cell = ws.cell(r, c, clean(v))
    if isinstance(v, str) and v.startswith("="):
        cell.data_type = "s"
    return cell


def split_classes(v):
    if v is None or E.is_empty(v):
        return []
    s = str(v).strip()
    try:
        j = json.loads(s)
        items = j if isinstance(j, list) else [j]
    except Exception:
        items = re.split(r"[,;|\n]", s.strip("[]"))
    out = []
    for x in items:
        x = str(x).strip().strip("'\"")
        c = cm.canon(x) if x else None
        if c and not c.startswith("UNGÜLTIG"):
            out.append(c)
    return out


def read_file(f):
    try:
        xl = pd.ExcelFile(f)
        sh = "Sheet1" if "Sheet1" in xl.sheet_names else xl.sheet_names[0]
        df = xl.parse(sh, dtype=str)
    except Exception as e:
        print(f"  ! {f.name}: nicht lesbar ({e})")
        return []
    cols = list(df.columns)
    c_sap, c_tc = E.find_col(cols, contains=["sap"]), E.find_col(cols, contains=["teamcenter"])
    c_pred = E.find_col(cols, contains=["predicted"])
    c_rea = E.find_col(cols, contains=["reasoning"])
    c_pos = E.find_col(cols, contains=["possible"])
    if not c_pred or not (c_sap or c_tc):
        return []
    rows = []
    for _, r in df.iterrows():
        k = cm.match_key(r[c_sap] if c_sap else None, r[c_tc] if c_tc else None)
        if k is None:
            continue
        raw = "" if E.is_empty(r[c_pred]) else str(r[c_pred]).strip()
        pred = cm.canon(raw) if raw and raw.upper() != "[EMPTY]" else None
        if pred and pred.startswith("UNGÜLTIG"):
            pred = f"UNGÜLTIG: {raw}"           # nicht erkannte Klasse: zählt als „andere Klasse“ (ungültig)
        rea = "" if (not c_rea or E.is_empty(r[c_rea])) else str(r[c_rea]).strip()
        rows.append((k, pred, split_classes(r[c_pos]) if c_pos else [], rea))
    return rows


def model_of(f):
    m, p, i = X.tokens(f)          # aus Dateiname, ersatzweise aus den Ordnernamen darüber
    return m or "?", p or "P3", i or X.PREF.get(m, "pdf")



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
    ap.add_argument("--dir", action="append", required=True, help="Ordner mit LLM-Ergebnissen (mehrfach möglich)")
    ap.add_argument("--vorlage", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    wb = load_workbook(a.vorlage)
    ws = wb.worksheets[0]
    # Kopfzeile finden
    hr = next(r for r in range(1, 20) if ws.cell(r, 3).value == "SAP Nr")
    col = {}
    for c in range(2, ws.max_column + 1):
        v = ws.cell(hr, c).value
        if v:
            col.setdefault(v, []).append(c)
    c_sap, c_tc = col["SAP Nr"][0], col["Teamcenter"][0]
    c_lab = [col["Label 1"][0], col["Label 2"][0], col["Label 3"][0]]          # erste Vorkommen = Labelspalten
    c_grund = [col[f"Grund Label {i}"][0] for i in (1, 2, 3)]
    # Gruppe je Spalte aus der Zeile darüber („von LLM markiert“ / „von Mensch markiert“)
    grp, cur = {}, None
    for c in range(2, ws.max_column + 1):
        v = ws.cell(hr - 1, c).value
        if v:
            cur = str(v)
        grp[c] = cur or ""
    llm = [c for c in range(2, ws.max_column + 1) if "LLM" in grp[c]]
    c_llm = [next(c for c in llm if ws.cell(hr, c).value == f"Label {i}") for i in (1, 2, 3)]
    c_other_llm = next(c for c in llm if ws.cell(hr, c).value == "andere Klassen")
    bg = {}
    r = hr + 1
    while ws.cell(r, c_sap).value or ws.cell(r, c_tc).value:
        k = cm.match_key(ws.cell(r, c_sap).value, ws.cell(r, c_tc).value)
        labs = [ws.cell(r, c).value for c in c_lab]
        bg[k] = (r, [cm.canon(x) if x and x != "–" else None for x in labs])
        r += 1
    print(f"Vorlage: {len(bg)} Baugruppen")
    for rr_ in range(r, min(r + 6, ws.max_row + 1)):
        if str(ws.cell(rr_, 2).value or "").startswith("Anzahl der LLM-Vorhersagen"):
            raise SystemExit("Die Vorlage ist bereits eine vorbefüllte Ausgabe – bitte die leere Vorlage "
                             "(Mehrdeutige_Baugruppen_R2_Begruendung.xlsx) als --vorlage angeben.")

    # Ergebnisdateien lesen
    hits = defaultdict(list)   # k -> [(modell, prompt, eingabe, datei, pred, possible, reasoning)]
    nfiles, seen = 0, {}
    src = {}            # Dateiname -> Experiment
    cand = []          # (exp, datei, modell, prompt, eingabe, datensatz, rows)
    main115 = set(cm.MAIN_115)
    for root in a.dir:
        rn = Path(root).resolve().name.lower()
        exp = ("Wiederholungsläufe" if ("wiederhol" in rn or rn.startswith("03")) else
               "Prompt-Vergleich" if ("prompt" in rn or rn.startswith("01")) else
               "Input-Vergleich" if ("input" in rn or rn.startswith("02")) else Path(root).name)
        for f in X.files_in([root]):
            h_ = (exp, hashlib.md5(f.read_bytes()).hexdigest())   # identische Kopie im selben Experiment nur einmal
            if h_ in seen:
                print(f"  Hinweis: {f.name} ist eine identische Kopie von {seen[h_]} ({exp}) – nur einmal gezählt")
                continue
            seen[h_] = f.name
            rows = read_file(f)
            if not rows:
                continue
            m, p, i = model_of(f)
            if m == "?":
                print(f"  ! {f.name}: Modell nicht erkannt – unter „?“ gezählt")
            n115 = sum(1 for k, *_ in rows if k in main115)
            ds = "115" if n115 >= len(rows) / 2 else "70"
            cand.append((exp, f, m, p, i, ds, rows))
    # Einzelläufe: je Experiment zählt jede Konfiguration (Modell, Prompt, Eingabe, Datensatz) einmal.
    # P3 im Prompt-Vergleich und pdf/Bild/text im Input-Vergleich werden getrennt gezählt (P1–P4 = 4, pdf/Bild/text = 3).
    groups = defaultdict(list)
    for c_ in cand:
        if c_[0] == "Wiederholungsläufe":
            groups[("W", id(c_))].append(c_)
        else:
            groups[(c_[0], c_[2], c_[3], c_[4], c_[5])].append(c_)
    used = []
    for key, lst in groups.items():
        if len(lst) > 1:
            lst.sort(key=lambda c_: -sum(1 for _, pr, _, _ in c_[6] if pr))
            print(f"  Hinweis: {key[0]}: {key[1]} {key[2]} {key[3]} {key[4]} BG liegt {len(lst)}× vor – gezählt einmal "
                  f"({lst[0][1].name}, {lst[0][0]}); ignoriert: {', '.join(c_[1].name for c_ in lst[1:])}")
        used.append(lst[0])
    for exp, f, m, p, i, ds, rows in used:
        nfiles += 1
        fid = str(f)
        src[fid] = (exp, p, i)
        for k, pred, pos, rea in rows:
            if k in bg:
                hits[k].append((m, p, i, fid, pred, pos, rea))
    print(f"Ergebnisdateien gelesen: {nfiles}; Baugruppen mit LLM-Läufen: {len(hits)} von {len(bg)}")

    thin = Side(style="thin", color="BFBFBF")
    no_llm = []
    c_other = c_other_llm
    # Datenüberprüfung ja/nein von den LLM-Zellen entfernen (dort steht jetzt „ja (n/N)“)
    llm_cols = {get_column_letter(c) for c in c_llm}
    for dv in ws.data_validations.dataValidation:
        keep = [rg for rg in str(dv.sqref).split() if re.match(r"[A-Z]+", rg).group(0) not in llm_cols]
        dv.sqref = MultiCellRange(" ".join(keep)) if keep else MultiCellRange()
    ws.data_validations.dataValidation = [d for d in ws.data_validations.dataValidation if str(d.sqref).strip()]
    detail = {}
    for k, (row, labs) in bg.items():
        runs = [x for x in hits.get(k, []) if x[4]]           # nur gültige Vorhersagen
        if not runs:
            no_llm.append(k)
        tot = len(runs)
        cnt = Counter(norm(x[4]) for x in runs)
        for n, lab in enumerate(labs):
            if not lab:
                continue
            c = ws.cell(row, c_llm[n], (f"ja ({cnt[lab]}/{tot})" if cnt[lab] else f"nein (0/{tot})") if tot else "–")
            c.fill = PatternFill("solid", fgColor=AUTO)
        other = {lab_: n_ for lab_, n_ in cnt.items() if lab_ not in labs}
        txt = ", ".join(f"{ABBR.get(l_, l_)} × {n_}" for l_, n_ in sorted(other.items(), key=lambda x: (-x[1], x[0])))
        c = ws.cell(row, c_other, (txt or "–") if tot else "–")
        c.fill = PatternFill("solid", fgColor=AUTO)
        # je Modell für Blatt „LLM-Häufigkeiten“
        per = defaultdict(Counter)
        for x in runs:
            per[x[0]][norm(x[4])] += 1
        detail[k] = (row, labs, per)

    # Tabelle unter der Liste: Zusammensetzung der LLM-Vorhersagen je Modell
    EXPS = ["Wiederholungsläufe", "Prompt-Vergleich", "Input-Vergleich"]
    comp = defaultdict(Counter)       # Modell -> Counter(Zusammensetzung je BG)
    for k in bg:
        per = defaultdict(list)
        for m, p, i, fn, pr, pos, rea in hits.get(k, []):
            if pr:
                per[m].append(src.get(fn, ("?", p, i)))
        for m, lst in per.items():
            sig = []
            for e in EXPS + sorted({x[0] for x in lst} - set(EXPS)):
                sel = [x for x in lst if x[0] == e]
                if e == "Prompt-Vergleich":
                    det = ", ".join(sorted({x[1] for x in sel}))
                elif e == "Input-Vergleich":
                    det = ", ".join(x for x in ("pdf", "image", "text") if x in {y[2] for y in sel})
                else:
                    det = ""
                sig.append((e, len(sel), det))
            comp[m][tuple(sig)] += 1
    last = max(r for r, _ in bg.values())
    ncols = ws.max_column
    tr = last + 3
    t = ws.cell(tr, 2, "Anzahl der LLM-Vorhersagen je Baugruppe (Nenner in „von LLM markiert“)")
    t.font = Font(bold=True, size=12)
    heads = ["Modell", "Wiederholungsläufe", "Prompt-Vergleich", "", "Input-Vergleich", "", "Vorhersagen je BG", "Baugruppen"]
    spans = [(2, 3), (4, 4), (5, 5), (6, 6), (7, 7), (8, 8), (9, 9), (10, 10)]
    sub = ["", "Anzahl", "Anzahl", "Prompts", "Anzahl", "Eingaben", "gesamt", "mit dieser Anzahl"]
    thick = Side(style="medium", color="C00000")
    hdr_r = tr + 1
    for (c1, c2), h, sh in zip(spans, heads, sub):
        if c2 > c1:
            ws.merge_cells(start_row=hdr_r, start_column=c1, end_row=hdr_r, end_column=c2)
            ws.merge_cells(start_row=hdr_r + 1, start_column=c1, end_row=hdr_r + 1, end_column=c2)
        for rr_, txt in ((hdr_r, h), (hdr_r + 1, sh)):
            for cc in range(c1, c2 + 1):
                c = ws.cell(rr_, cc)
                c.fill, c.font = PatternFill("solid", fgColor="D9D9D9"), Font(bold=True)
                c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                c.border = Border(left=thin, right=thin, top=thin, bottom=thick if rr_ == hdr_r + 1 else thin)
            ws.cell(rr_, c1, txt or None)
    for c1 in (5, 7):
        ws.merge_cells(start_row=hdr_r, start_column=c1, end_row=hdr_r, end_column=c1 + 1)
    rr_ = hdr_r + 2
    first_t = rr_
    for m in MODEL_PRIO + sorted(set(comp) - set(MODEL_PRIO)):
        if m not in comp:
            continue
        for sig, nbg in comp[m].most_common():
            d = {e: (n, det) for e, n, det in sig}
            tot_n = sum(n for _, n, _ in sig)
            vals = [(2, m), (4, d.get("Wiederholungsläufe", (0, ""))[0]),
                    (5, d.get("Prompt-Vergleich", (0, ""))[0]), (6, d.get("Prompt-Vergleich", (0, ""))[1] or "–"),
                    (7, d.get("Input-Vergleich", (0, ""))[0]), (8, d.get("Input-Vergleich", (0, ""))[1] or "–"),
                    (9, tot_n), (10, nbg)]
            ws.merge_cells(start_row=rr_, start_column=2, end_row=rr_, end_column=3)
            for cc in range(2, 11):
                c = ws.cell(rr_, cc)
                c.border = Border(left=thin, right=thin, top=thin, bottom=thin)
                c.alignment = Alignment(horizontal="left" if cc == 2 else "center", vertical="center", indent=1 if cc == 2 else 0)
            for cc, v in vals:
                ws.cell(rr_, cc, v)
            ws.cell(rr_, 9).font = Font(bold=True)
            ws.row_dimensions[rr_].height = 18
            rr_ += 1
    for cc in range(2, 11):
        c = ws.cell(rr_ - 1, cc)
        c.border = Border(left=thin, right=thin, top=thin, bottom=thick)
    ws.cell(rr_ + 1, 2, "Wiederholungsläufe = 10 Läufe mit P3 und bevorzugter Eingabe; Prompt-Vergleich = P1–P4 "
            "(Einzellauf); Input-Vergleich = P3 mit pdf/Bild/text (Einzellauf). P3 zählt im Prompt- und im Input-Vergleich "
            "jeweils mit. Unterschiedliche Zeilen je Modell = abweichende Anzahl bei einzelnen Baugruppen."
            ).font = Font(size=9, italic=True)

    # Blatt LLM-Reasoning
    if "LLM-Reasoning" in wb.sheetnames:
        del wb["LLM-Reasoning"]
    s = wb.create_sheet("LLM-Reasoning")
    head = ["SAP Nr", "Teamcenter", "Labelmenge", "Modell", "Prompt", "Eingabe", "Datei",
            "Predicted_Label", "in Labelmenge", "Possible_Classes_If_Ambiguous", "Reasoning"]
    widths = [14, 13, 40, 18, 7, 8, 30, 24, 10, 30, 110]
    for j, (h, w) in enumerate(zip(head, widths), 1):
        c = s.cell(1, j, h)
        c.font, c.fill = Font(bold=True), PatternFill("solid", fgColor="D9D9D9")
        c.border = Border(left=thin, right=thin, top=thin, bottom=Side(style="medium", color="C00000"))
        s.column_dimensions[c.column_letter].width = w
    rr = 2
    for k, (row, labs) in bg.items():
        sap, tc = ws.cell(row, c_sap).value, ws.cell(row, c_tc).value
        for m, p, i, fn, pr, pos, rea in sorted(hits.get(k, []), key=lambda x: (
                MODEL_PRIO.index(x[0]) if x[0] in MODEL_PRIO else 99, x[1], x[2], x[3])):
            vals = [sap, tc, ", ".join(x for x in labs if x), m, p, i, Path(fn).name, pr or "(leer)",
                    "ja" if pr in labs else "nein", ", ".join(pos), rea]
            for j, v in enumerate(vals, 1):
                c = put(s, rr, j, v)
                c.border = Border(left=thin, right=thin, top=thin, bottom=thin)
                c.alignment = Alignment(wrap_text=j == 11, vertical="top")
            rr += 1
    s.freeze_panes = "C2"
    s.auto_filter.ref = f"A1:K{max(rr - 1, 1)}"

    # Blatt LLM-Häufigkeiten: je Baugruppe und Modell, welche Klassen wie oft
    if "LLM-Häufigkeiten" in wb.sheetnames:
        del wb["LLM-Häufigkeiten"]
    q = wb.create_sheet("LLM-Häufigkeiten")
    q.sheet_view.showGridLines = False
    models = [m for m in MODEL_PRIO if any(m in d[2] for d in detail.values())]
    models += sorted({m for d in detail.values() for m in d[2]} - set(models))
    head = ["SAP Nr", "Teamcenter", "Datensatz", "Labelmenge"] + models
    q.column_dimensions["A"].width = 2
    for j, h_ in enumerate(head):
        c = q.cell(2, 2 + j, h_)
        c.font, c.fill = Font(bold=True), PatternFill("solid", fgColor="D9D9D9")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = Border(left=thin, right=thin, top=thin, bottom=Side(style="medium", color="C00000"))
        q.column_dimensions[get_column_letter(2 + j)].width = [14, 13, 13, 16][j] if j < 4 else 26
    rr = 3
    c_ds = col["Datensatz"][0]
    for k, (row, labs, per) in detail.items():
        vals = [ws.cell(row, c_sap).value, ws.cell(row, c_tc).value, ws.cell(row, c_ds).value,
                ", ".join(ABBR.get(x, x) for x in labs if x)]
        for m in models:
            cn = per.get(m)
            if not cn:
                vals.append("–")
                continue
            inside = [f"{ABBR.get(l_, l_)} × {cn[l_]}" for l_ in labs if l_ and cn.get(l_)]
            outside = [f"{ABBR.get(l_, l_)} × {n_}" for l_, n_ in sorted(cn.items(), key=lambda x: (-x[1], x[0])) if l_ not in labs]
            vals.append(", ".join(inside + outside) + f"  (N = {sum(cn.values())})")
        for j, v in enumerate(vals):
            c = q.cell(rr, 2 + j, v)
            c.border = Border(left=thin, right=thin, top=thin, bottom=thin)
            c.alignment = Alignment(horizontal="left" if j < 4 else "center", vertical="center", indent=1 if j < 4 else 0)
        rr += 1
    for j in range(len(head)):
        q.cell(rr - 1, 2 + j).border = Border(left=thin, right=thin, top=thin, bottom=Side(style="medium", color="C00000"))
    q.cell(rr + 1, 2, "Je Modell: Klassen der Labelmenge zuerst, dann andere Klassen; N = gültige Vorhersagen des Modells "
                      "für die Baugruppe. Kürzel: " + ", ".join(f"{v} = {k_}" for k_, v in ABBR.items())).font = Font(size=9, italic=True)
    q.freeze_panes = "F3"

    # Hinweis ergänzen
    if "Hinweise" in wb.sheetnames:
        h = wb["Hinweise"]
        r = h.max_row + 2
        for t in ["Automatisch vorbefüllt (hellblau):",
                  "„von LLM markiert“: ja (n/N) = in n von N gültigen LLM-Vorhersagen (alle Modelle und Läufe) wurde dieses Label "
                  "vorhergesagt; nein (0/N) = nie. „andere Klassen“ = Vorhersagen außerhalb der Labelmenge, z. B. GR × 2. "
                  "Die Zahlen ergeben zusammen N. Aufschlüsselung je Modell im Blatt „LLM-Häufigkeiten“.",
                  "„Grund Label n“ bleibt für die Begründung der Ground Truth frei; alle LLM-Reasonings im Blatt „LLM-Reasoning“."]:
            h.cell(r, 2, t).alignment = Alignment(wrap_text=True)
            r += 1
        h.cell(h.max_row - 2, 2).font = Font(bold=True)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out = save_safe(wb, out)
    # Kontrolle: gleiche Anzahl gültiger Vorhersagen je Modell über alle Baugruppen?
    per_model = defaultdict(Counter)
    for k in bg:
        for m, n in Counter(m for m, *_r in hits.get(k, []) if _r[3]).items():
            per_model[m][n] += 1
    print("Gültige Vorhersagen je Baugruppe (Modell: Anzahl → wie viele BG):")
    for m in MODEL_PRIO + sorted(set(per_model) - set(MODEL_PRIO)):
        if m in per_model:
            v = per_model[m]
            flag = "" if len(v) == 1 else "   ! unterschiedlich – bitte prüfen"
            print(f"  {m}: " + ", ".join(f"{n} → {c} BG" for n, c in sorted(v.items())) + flag)
    if no_llm:
        print(f"  ! keine gültigen LLM-Vorhersagen für: {', '.join(no_llm)}")
    print(f"LLM-Läufe zu mehrdeutigen BG: {sum(len(v) for v in hits.values())}")
    print(f"Ausgabe: {out}")


if __name__ == "__main__":
    main()
