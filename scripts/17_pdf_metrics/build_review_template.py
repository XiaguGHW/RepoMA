"""
Review-Template (Format wie „BG-Label Template“ von Jonas) für
  - alle Baugruppen mit Register E2 (Ground Truth R2) und
  - alle Baugruppen mit Register E1, bei denen mindestens ein LLM-Lauf ein anderes Label vergeben hat.

Eine Zeile je Kombination aus Baugruppe und Label. Labels = GT-Label + alle Klassen, die von Menschen
(Workshop, Spalten „TN …“) oder LLMs (alle Modelle und Läufe) vergeben wurden.
Begründung = Auszug aus dem Reasoning eines LLM-Laufs mit diesem Label (bei rein menschlichen Labels leer).
Labels je Baugruppe in fester Klassenreihenfolge (die Position verrät nicht, welches Label bisher
Ground Truth war). Spalte „Review“ (passed/failed) und „Anmerkung“ bleiben leer. Hilfsspalten S–AA sind ausgeblendet
(Teamcenter, Datensatz, von Mensch/LLM vergeben, Herkunft, Label-Nr., Register).

Aufbau aus der Vorlage von Jonas (nur Formatierung wird übernommen, keine Inhalte):
  python build_review_template.py --vorlage Review_M_Regime_Template.xlsx --gt R2.md
         --dir "..\\01_Prompt_P1-P4" --dir "..\\02_Input_P3" --dir "..\\03_Wiederholung_10runs"
         --mensch $ws --out "..\\05_Ergebnisse_R2\\Review_E2_E1_Template.xlsx"
Danach Screenshots:
  python add_screenshots.py --quelle $ws --blatt "R1_Ground_Truth_Abb" --ziel <out> --out <out_mit_Bildern>
"""
import argparse
import re
import sys
from collections import Counter, defaultdict
from copy import copy
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.formatting.formatting import ConditionalFormattingList
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter as gl
from openpyxl.worksheet.cell_range import MultiCellRange

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluate_r1 as R                    # noqa: E402
import eval_input_regime_r1 as G           # noqa: E402  (registers)
import fill_mehrdeutig_llm as F            # noqa: E402
import fill_mehrdeutig_mensch as H         # noqa: E402

cm = R.cm
MAX_GRUND = 450
MODEL_PRIO = F.MODEL_PRIO


def excerpt(text):
    """Kurzfassung: vollständiger Text, wenn kurz genug; sonst Anfang + „…“ + Schlusssatz,
    damit die Schlussfolgerung (welche Klasse und warum) sichtbar bleibt."""
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(t) <= MAX_GRUND:
        return t
    sents = re.split(r"(?<=[.!?])\s+", t)
    tail = sents[-1] if len(sents[-1]) <= MAX_GRUND // 2 else sents[-1][:MAX_GRUND // 2].rsplit(" ", 1)[0] + " …"
    head, used = "", len(tail) + 5
    for x in sents[:-1]:
        if used + len(head) + len(x) + 1 > MAX_GRUND:
            break
        head = (head + " " + x).strip()
    if not head:
        head = t[:MAX_GRUND - used].rsplit(" ", 1)[0]
    return f"{head} … {tail}"


def njn(n, N):
    return "–" if not N else (f"ja ({n}/{N})" if n else f"nein (0/{N})")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vorlage", required=True, help="Template von Jonas (Blatt „BG-Label Template“)")
    ap.add_argument("--gt", required=True, help="R2.md")
    ap.add_argument("--dir", action="append", required=True, help="LLM-Ergebnisordner (mehrfach)")
    ap.add_argument("--mensch", required=True, help="Workshop-Datei (Blatt Klassifikation_Übersicht_Gesamt)")
    ap.add_argument("--blatt-mensch", default=None)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    gt, pe, _ = R.load_gt(a.gt)
    reg = G.registers(a.gt)
    # Rohzeilen (SAP/Teamcenter wie in der GT-Datei) und Reihenfolge
    order, raw = [], {}
    L = Path(a.gt).read_text(encoding="utf-8").splitlines()
    hi = next(i for i, l in enumerate(L) if l.startswith("|") and "SAP" in l)
    for l in L[hi + 2:]:
        if l.startswith("|"):
            c = [x.strip() for x in l.strip().strip("|").split("|")] + [""] * 6
            k = cm.match_key(c[0] or None, c[1] or None)
            if k and k not in raw:
                raw[k] = (c[0], c[1])
                order.append(k)

    print("LLM-Ergebnisse lesen …")
    hits, src, nfiles = F.collect_llm(a.dir, set(gt))
    print(f"  {nfiles} Ergebnisdateien")
    print("Workshop-Klassifikationen lesen …")
    ann, info = H.read_mensch(a.mensch, a.blatt_mensch)
    print(f"  {sum(len(v) for v in ann.values())} Klassifikationen zu {len(ann)} Baugruppen")

    sel = []
    for k in order:
        r_ = reg.get(k)
        llm = [x for x in hits.get(k, []) if x[4] and not str(x[4]).startswith("UNGÜLTIG")]
        dev = sum(1 for x in llm if x[4] != gt[k][0])
        if r_ == "E2":
            sel.append((k, "E2", dev))
        elif r_ == "E1" and dev > 0:
            sel.append((k, "E1", dev))
    sel.sort(key=lambda x: (x[1] != "E2", x[0] in pe))
    print(f"Ausgewählt: {sum(1 for s in sel if s[1] == 'E2')} BG mit E2, "
          f"{sum(1 for s in sel if s[1] == 'E1')} BG mit E1 und abweichender LLM-Vorhersage")

    # ------------------------------------------------ Vorlage: nur Formatierung übernehmen
    wb = load_workbook(a.vorlage)
    ws = wb["BG-Label Template"]
    for n in list(wb.sheetnames):
        if n != ws.title:
            del wb[n]
    hr, first = 5, 6
    ncol = max(ws.max_column, 27)
    style = {c: ws.cell(first, c)._style for c in range(1, ncol + 1)}
    height = ws.row_dimensions[first].height or 100
    cf_rules = [(str(cf.sqref), list(cf.rules)) for cf in ws.conditional_formatting]
    dvs = list(ws.data_validations.dataValidation)
    ws._images = []
    old_max = ws.max_row
    ws.delete_rows(first, old_max - first + 1)
    for rr in range(first, old_max + 1):          # alte Zeilenhöhen entfernen
        if rr in ws.row_dimensions:
            del ws.row_dimensions[rr]
    ws.cell(hr, 27, "Register (R2)")._style = copy(ws.cell(hr, 26)._style)
    ws.cell(2, 2).value = "Review: Baugruppe × vergebenes Label (Register E2 sowie E1 mit abweichender LLM-Vorhersage, Ground Truth R2)"
    ws.cell(3, 2).value = ("Eine Zeile je Kombination aus Baugruppe und Label (Ground-Truth-Label sowie alle von Menschen "
                           "oder LLMs vergebenen Klassen). Begründung = Auszug aus einer LLM-Begründung für dieses Label.")

    r = first
    reasoning_rows = []
    for nr, (k, rg, dev) in enumerate(sel, 1):
        sap, tc = raw[k]
        llm = [x for x in hits.get(k, []) if x[4]]
        llm_cnt = Counter(F.norm(x[4]) for x in llm)
        hum = ann.get(k, [])
        hum_cnt = Counter(lab for _, lab, _, _ in hum)
        gl_labels = [gt[k][0]] + sorted(gt[k][1] - {gt[k][0]})
        others = [l_ for l_, _ in (llm_cnt + hum_cnt).most_common() if l_ not in gl_labels and l_ != "ungültig"]
        ds = "Label-Konfig." if k in pe else ("115 BG" if k in set(cm.MAIN_115) else "70 BG")
        # feste Klassenreihenfolge, damit die Position nicht verrät, welches Label bisher Ground Truth war
        CLS = ["Lineareinheit", "Rotationseinheit", "Greifer", "Multi-Achs-System (Gantry)", "Roboter",
               "Kombinierte Einheit", "Keine der verfügbaren Klassen"]
        labs_all = sorted(gl_labels + others, key=lambda x: CLS.index(x) if x in CLS else 99)
        for lab in labs_all:
            j = gl_labels.index(lab) if lab in gl_labels else len(gl_labels)
            cand = [x for x in llm if x[4] == lab and x[6] and len(str(x[6]).strip()) > 40]
            # bevorzugt: Begründung, die vollständig in die Zelle passt; dann Modellreihenfolge, P3, Dateiname
            cand.sort(key=lambda x: (len(re.sub(r"\s+", " ", str(x[6]))) > MAX_GRUND,
                                     MODEL_PRIO.index(x[0]) if x[0] in MODEL_PRIO else 99, x[1] != "P3", x[3]))
            if cand:
                grund = excerpt(cand[0][6])
            elif llm_cnt[lab]:
                grund = "Von LLMs vergeben, aber keine verwertbare Begründung vorhanden."
            else:   # wie im M-Template von Jonas: rein menschliche Labels kennzeichnen
                n_h = hum_cnt[lab]
                grund = (f"Nur von {'einem menschlichen Annotator' if n_h == 1 else f'{n_h} menschlichen Annotatoren'} "
                         "markiert; es liegt keine Begründung vor und die Klasse wurde von keinem LLM vergeben.")
            labnr = f"Label {j + 1}" if j < len(gl_labels) else "weitere Klasse"
            vals = {2: nr, 3: sap or tc or None, 5: lab, 6: grund,     # ohne SAP: Teamcenter-Nr. anzeigen
                    19: tc or None, 20: ds, 21: njn(hum_cnt[lab], len(hum)), 22: njn(llm_cnt[lab], len(llm)),
                    23: "nein" if j < len(gl_labels) else "ja", 24: labnr, 27: rg}
            for c in range(1, ncol + 1):
                cell = ws.cell(r, c)
                cell._style = copy(style.get(c, style[ncol]))
                if c in vals:
                    cell.value = F.clean(vals[c]) if isinstance(vals[c], str) else vals[c]
            ws.row_dimensions[r].height = height
            r += 1
        for m, p, i, fid, pr, pos, rea in llm:
            reasoning_rows.append([sap, tc, rg, m, p, i, Path(fid).name, pr, rea])
    last = r - 1

    # bedingte Formatierung und Auswahlliste auf den neuen Bereich übertragen
    ws.conditional_formatting = ConditionalFormattingList()
    for sq, rules in cf_rules:
        new = " ".join(re.sub(r"\d+$", str(last), re.sub(r"^([A-Z]+)\d+", rf"\g<1>{first}", part, count=1))
                       for part in sq.split())
        for rule in rules:
            ws.conditional_formatting.add(new, rule)
    for dv in dvs:
        dv.sqref = MultiCellRange(" ".join(f"{re.match(r'[A-Z]+', p).group(0)}{first}:{re.match(r'[A-Z]+', p).group(0)}{last}"
                                           for p in str(dv.sqref).split()))
    # Hilfsspalten ausblenden (unabhängiges Review)
    for c in range(19, 28):
        ws.column_dimensions[gl(c)].hidden = True
    ws.freeze_panes = f"A{first}"

    # Blatt LLM-Reasoning
    s = wb.create_sheet("LLM-Reasoning")
    head = ["SAP Nr", "Teamcenter", "Register", "Modell", "Prompt", "Eingabe", "Datei", "Predicted_Label", "Reasoning"]
    for j, h in enumerate(head, 1):
        c = s.cell(1, j, h)
        c.font, c.fill = Font(bold=True), PatternFill("solid", fgColor="D9D9D9")
        s.column_dimensions[gl(j)].width = [14, 13, 9, 18, 7, 8, 30, 24, 110][j - 1]
    for i_, row in enumerate(reasoning_rows, 2):
        for j, v in enumerate(row, 1):
            F.put(s, i_, j, v)
        s.cell(i_, 9).alignment = Alignment(wrap_text=False, vertical="top")
    s.freeze_panes = "C2"
    s.auto_filter.ref = f"A1:I{max(len(reasoning_rows) + 1, 1)}"

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out = F.save_safe(wb, out)
    n_e2 = sum(1 for s_ in sel if s_[1] == "E2")
    print(f"Zeilen (BG × Label): {last - first + 1}  –  {n_e2} E2-BG, {len(sel) - n_e2} E1-BG")
    print(f"Ausgabe: {out}")


if __name__ == "__main__":
    main()
