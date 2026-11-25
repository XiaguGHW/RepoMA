"""
Füllt die Vorlage „Mehrdeutige_Baugruppen_R2_Begruendung.xlsx“ aus allen LLM-Ergebnisdateien vor.

Für jede mehrdeutige Baugruppe und jedes Label der Labelmenge:
- „Label n von LLM markiert“ = ja, wenn das Label in mindestens einem Lauf irgendeines Modells
  als Predicted_Label vorhergesagt wurde, sonst nein. Ein Kommentar an der Zelle zeigt je Modell,
  wie oft vorhergesagt / Anzahl gültiger Vorhersagen dieses Modells für die Baugruppe.
- „Grund Label n“ bleibt leer (Begründung der Ground Truth durch den Menschen). Als Hilfe hängt an der
  Zelle ein Kommentar mit einem Auszug aus dem Reasoning eines LLM-Laufs, der dieses Label vorhergesagt hat.
- Blatt „LLM-Reasoning“: alle Läufe zu den mehrdeutigen Baugruppen mit vollständigem Reasoning.
Die Spalten „von Mensch markiert“ und „Screenshot“ werden nicht verändert.

Beispiel (in 00_Skripte):
  python fill_mehrdeutig_llm.py --dir "..\\01_Prompt_P1-P4" --dir "..\\02_Input_P3" --dir "..\\03_Wiederholung_10runs"
         --vorlage Mehrdeutige_Baugruppen_R2_Begruendung.xlsx --out "..\\05_Ergebnisse_R2\\Mehrdeutige_Baugruppen_R2_LLM.xlsx"
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluate_pdf_results as E          # noqa: E402
import evaluate_r1 as R                    # noqa: E402
import evaluate_r1_ergebnisse as X         # noqa: E402

cm = R.cm
MODEL_PRIO = ["Gemini 2.5 Pro", "Claude Opus 4.8", "Gemini 2.5 Flash", "GPT-5.5", "Claude Haiku 4.5", "DeepSeek-V4-Flash"]
AUTO = "DCE6F1"     # hellblau = automatisch vorbefüllt
MAX_GRUND = 600


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
        df = pd.read_excel(f, sheet_name=0, dtype=str)
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
            pred = None
        rea = "" if (not c_rea or E.is_empty(r[c_rea])) else str(r[c_rea]).strip()
        rows.append((k, pred, split_classes(r[c_pos]) if c_pos else [], rea))
    return rows


def model_of(f):
    m, p, i = X.tokens(f)
    if m is None:
        for d in [f.parent, *f.parents]:
            m = R.model_from_name(d.name) if hasattr(R, "model_from_name") else None
            if m:
                break
    return m or "?", p or "P3", i or X.PREF.get(m, "pdf")


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
    c_llm = [col["Label 1"][1], col["Label 2"][1], col["Label 3"][1]]           # zweites Vorkommen = LLM
    bg = {}
    r = hr + 1
    while ws.cell(r, c_sap).value or ws.cell(r, c_tc).value:
        k = cm.match_key(ws.cell(r, c_sap).value, ws.cell(r, c_tc).value)
        labs = [ws.cell(r, c).value for c in c_lab]
        bg[k] = (r, [cm.canon(x) if x and x != "–" else None for x in labs])
        r += 1
    print(f"Vorlage: {len(bg)} Baugruppen")

    # Ergebnisdateien lesen
    hits = defaultdict(list)   # k -> [(modell, prompt, eingabe, datei, pred, possible, reasoning)]
    nfiles, seen = 0, set()
    src = {}            # Dateiname -> Experiment
    for root in a.dir:
        rn = Path(root).resolve().name.lower()
        exp = ("Wiederholungsläufe" if ("wiederhol" in rn or rn.startswith("03")) else
               "Prompt-Vergleich" if ("prompt" in rn or rn.startswith("01")) else
               "Input-Vergleich" if ("input" in rn or rn.startswith("02")) else Path(root).name)
        for f in sorted(Path(root).rglob("*.xlsx")):
            if E.is_output_or_backup(f):
                continue
            if f.name in seen:          # gleiche Datei in mehreren Ordnern (z. B. 01 und 02) nur einmal
                print(f"  Hinweis: {f.name} mehrfach vorhanden – nur einmal gezählt")
                continue
            seen.add(f.name)
            rows = read_file(f)
            if not rows:
                continue
            nfiles += 1
            m, p, i = model_of(f)
            src[f.name] = (exp, p, i)
            for k, pred, pos, rea in rows:
                if k in bg:
                    hits[k].append((m, p, i, f.name, pred, pos, rea))
    print(f"Ergebnisdateien gelesen: {nfiles}; Baugruppen mit LLM-Läufen: {len(hits)} von {len(bg)}")

    thin = Side(style="thin", color="BFBFBF")
    no_llm = []
    for k, (row, labs) in bg.items():
        runs = hits.get(k, [])
        if not runs:
            no_llm.append(k)
        for n, lab in enumerate(labs):
            if not lab:
                continue
            pred_cnt = Counter(m for m, *_r in runs if _r[3] == lab)
            tot = Counter(m for m, *_r in runs if _r[3])          # nur gültige Vorhersagen
            marked = bool(pred_cnt)
            c = ws.cell(row, c_llm[n], "ja" if marked else "nein")
            c.fill = PatternFill("solid", fgColor=AUTO)
            txt = [f"{lab}:"]
            for m in MODEL_PRIO + sorted(set(tot) - set(MODEL_PRIO)):
                if tot.get(m):
                    txt.append(f"{m}: vorhergesagt {pred_cnt.get(m, 0)}/{tot[m]}"
                               )
            if len(txt) == 1:
                txt.append("keine LLM-Läufe gefunden")
            c.comment = Comment("\n".join(txt), "Auswertung")
            c.comment.width, c.comment.height = 320, 20 + 16 * len(txt)
            # Grund-Entwurf
            g = ws.cell(row, c_grund[n])
            if g.value not in (None, ""):
                continue
            cand = [x for x in runs if x[4] == lab and x[6]]
            if cand:
                cand.sort(key=lambda x: (MODEL_PRIO.index(x[0]) if x[0] in MODEL_PRIO else 99, x[1] != "P3", x[3]))
                m, p, i, fn, pr, pos, rea = cand[0]
                rea = re.sub(r"\s+", " ", rea)
                if len(rea) > MAX_GRUND:
                    rea = rea[:MAX_GRUND].rsplit(" ", 1)[0] + " …"
                g.comment = Comment(f"LLM-Reasoning ({m}, {p}, {fn}):\n{rea}", "Auswertung")
                g.comment.width, g.comment.height = 420, 60 + 14 * (len(rea) // 60)

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
            "(Einzellauf); Input-Vergleich = P3 mit pdf/Bild/text (Einzellauf). Dieselbe Datei in mehreren Ordnern "
            "wird nur einmal gezählt. Unterschiedliche Zeilen je Modell = abweichende Anzahl bei einzelnen Baugruppen."
            ).font = Font(size=9, italic=True)

    # Blatt LLM-Reasoning
    if "LLM-Reasoning" in wb.sheetnames:
        del wb["LLM-Reasoning"]
    s = wb.create_sheet("LLM-Reasoning")
    head = ["SAP Nr", "Teamcenter", "Labelmenge (R2)", "Modell", "Prompt", "Eingabe", "Datei",
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
            vals = [sap, tc, ", ".join(x for x in labs if x), m, p, i, fn, pr or "(leer)",
                    "ja" if pr in labs else "nein", ", ".join(pos), rea]
            for j, v in enumerate(vals, 1):
                c = s.cell(rr, j, v)
                c.border = Border(left=thin, right=thin, top=thin, bottom=thin)
                c.alignment = Alignment(wrap_text=j == 11, vertical="top")
            rr += 1
    s.freeze_panes = "C2"
    s.auto_filter.ref = f"A1:K{max(rr - 1, 1)}"

    # Hinweis ergänzen
    if "Hinweise" in wb.sheetnames:
        h = wb["Hinweise"]
        r = h.max_row + 2
        for t in ["Automatisch vorbefüllt (hellblau):",
                  "„von LLM markiert“ = ja, wenn ein LLM das Label in mindestens einem Lauf als Predicted_Label "
                  "vorhergesagt hat; Häufigkeit je Modell im Kommentar der Zelle.",
                  "„Grund Label n“: Begründung, warum das Label für die Baugruppe zulässig ist (Ground Truth). Als Hilfe "
                  "enthält der Kommentar der Zelle einen Auszug aus einem LLM-Reasoning; alle Reasonings im Blatt „LLM-Reasoning“."]:
            h.cell(r, 2, t).alignment = Alignment(wrap_text=True)
            r += 1
        h.cell(h.max_row - 2, 2).font = Font(bold=True)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
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
        print(f"  ! keine LLM-Läufe gefunden für: {', '.join(no_llm)}")
    print(f"LLM-Läufe zu mehrdeutigen BG: {sum(len(v) for v in hits.values())}")
    print(f"Ausgabe: {out}")


if __name__ == "__main__":
    main()
