"""Blatt „Ergebnisse unter R1“ (Vorlage des Betreuers): 6 Modelle × P1–P4 / pdf, Bild, text / eindeutig,
mehrdeutig, Gesamt – für 185 und 115 Baugruppen, Ground Truth R1.

Je Zelle (nach Absprache 22.11.2026):
  - Allowed-Label-Set Accuracy mit 95%-Bootstrap-Intervall (2000 Wiederholungen, Baugruppen mit Zurücklegen;
    bei 185 BG getrennt nach Haupt- und Ergänzungsdatensatz gezogen),
  - Macro-Precision / -Recall / -F1 nur auf eindeutigen Baugruppen (ohne Bootstrap).

Spalten und Läufe (Vorgaben des Betreuers):
  P1–P4          Prompt-Vergleich, Eingabe pdf (GPT-5.5: Bild, DeepSeek: text), Einzellauf      -> --prompt
  pdf/Bild/text  Input-Vergleich mit P3, Einzellauf                                            -> --input
  eindeutig/mehrdeutig/Gesamt  P3 + bevorzugte Eingabe; Wiederholungsläufe (Mittel der Läufe)  -> --zehn
Fehlt ein Einzellauf für P3 bzw. die bevorzugte Eingabe, wird Lauf 1 der Wiederholungsläufe verwendet
(gelb markiert). Fehlen die 10 Läufe auf den 70 BG, werden für 185 BG die vorhandenen Ergänzungsläufe
verwendet (gelb markiert).

Ordner (jeweils mehrfach angebbar, Unterordner werden durchsucht):
  --prompt  Ergebnisdateien P1–P4 (115 und/oder 70 BG)
  --input   Ergebnisdateien pdf/Bild/text mit P3 (115 und/oder 70 BG)
  --zehn    Ordner mit den Wiederholungsläufen (je Konfiguration ein Ordner, 115 und 70 BG)
Modell, Prompt und Eingabe aus Datei- und Ordnernamen; Haupt- oder Ergänzungsdatensatz aus den Baugruppen.
Eine Datei kann in --prompt und --input zugleich liegen (z. B. pdf_only_70BG_P3_…).

Aufruf (PowerShell):
    python evaluate_r1_ergebnisse.py --gt "...\\R1.md" `
        --prompt "...\\prompt_vergleich" --input "...\\input_vergleich" --input "...\\70BG_einzel" `
        --prompt "...\\70BG_einzel" --zehn "...\\stability" --out "...\\Ergebnis_R1"
Benötigt im selben Ordner: evaluate_r1.py, evaluate_pdf_results.py, evaluate_70bg_results.py,
evaluate_prompt_results.py, confusion_human_llm.py, evaluate_validation_regimes.py.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evaluate_r1 as R  # noqa: E402

E, cm = R.E, R.cm
B, SEED = 2000, 42
MODELS = ["Gemini 2.5 Pro", "Gemini 2.5 Flash", "Claude Haiku 4.5", "Claude Opus 4.8", "GPT-5.5", "DeepSeek-V4-Flash"]
ROWNAME = {"Gemini 2.5 Pro": "Gemini Pro", "Gemini 2.5 Flash": "Gemini Flash", "Claude Haiku 4.5": "Claude Haiku",
           "Claude Opus 4.8": "Claude Opus", "GPT-5.5": "GPT 5.5", "DeepSeek-V4-Flash": "Deepseek"}
PREF = {"GPT-5.5": "image", "DeepSeek-V4-Flash": "text"}           # sonst pdf
NOT_APPLICABLE = {("GPT-5.5", "pdf"), ("DeepSeek-V4-Flash", "pdf"), ("DeepSeek-V4-Flash", "image")}
OPTIONAL = {("GPT-5.5", p) for p in ("P1", "P2", "P4")} | {("DeepSeek-V4-Flash", p) for p in ("P1", "P2", "P4")}
COLS = [("P1", "prompt"), ("P2", "prompt"), ("P3", "prompt"), ("P4", "prompt"),
        ("pdf", "input"), ("image", "input"), ("text", "input"),
        ("eindeutig", "regime"), ("mehrdeutig", "regime"), ("Gesamt", "regime")]
HEAD = {"image": "Bild"}

# Stil wie die Vorlage des Betreuers: weiß, Kopf hellgrau, Rahmen dunkelrot, Hinweise dunkelrot
GREY, RED, BLUE, YELLOW, NA = "D9D9D9", "C00000", "1F4E9E", "FFF2CC", "F2F2F2"


def pref(model):
    return PREF.get(model, "pdf")


# ---------------------------------------------------------------- Dateien zuordnen
def tokens(path):
    """(Modell, Prompt, Eingabe) aus Dateiname, ersatzweise aus den Ordnernamen darüber."""
    def find(text):
        t = re.sub(r"[\s_]+", "-", text.lower())
        model = E.model_name(Path(text))
        model = model if model in MODELS else None
        pr = re.findall(r"(?<![a-z0-9])p([1-4])(?![0-9])", t)
        prompt = f"P{pr[0]}" if len(set(pr)) == 1 else None
        inp = next((lab for key, lab in (("pdf", "pdf"), ("image", "image"), ("bild", "image"), ("img", "image"),
                                          ("text", "text"), ("txt", "text"))
                    if re.search(rf"(?<![a-z]){key}(?![a-z])", t)), None)
        return [model, prompt, inp]
    res = find(path.name)
    for parent in list(path.parents)[:3]:
        for i, v in enumerate(find(parent.name)):
            res[i] = res[i] or v
    return tuple(res)


def files_in(dirs):
    out = []
    for d in dirs or []:
        for f in sorted(Path(d).rglob("*")):
            if f.suffix.lower() in (".xlsx", ".xlsm") and not E.is_output_or_backup(f) \
                    and not any(p.lower().startswith("_backup_vor_merge") for p in f.parts):
                out.append(f)
    return out


def load_runs(files, gt, pe, issues, kind):
    """{(Modell, Prompt, Eingabe, Datensatz): [(Datei, Lauf)]}"""
    main_keys = set(cm.MAIN_115)
    groups, unknown = {}, []
    for f in files:
        model, prompt, inp = tokens(f)
        if kind == "zehn":
            prompt = prompt or "P3"
        if model is None:
            unknown.append(f"{f} (Modell nicht erkannt)")
            continue
        inp = inp or pref(model)
        if kind == "prompt" and prompt is None:
            unknown.append(f"{f} (Prompt nicht erkannt)")
            continue
        if kind == "input":
            prompt = prompt or "P3"
        run = R.read_predictions(f, "Sheet1", f"{model} | {f.name}", gt, pe, issues)
        if not run:
            continue
        # Datei kann beide Datensätze enthalten (z. B. pdf_only_185BG_…): nach Baugruppen aufteilen
        parts = {"main": {k: v for k, v in run.items() if k in main_keys},
                 "supp": {k: v for k, v in run.items() if k not in main_keys}}
        for ds, part in parts.items():
            if part:
                groups.setdefault((model, prompt, inp, ds), []).append((f, part))
        if parts["main"] and parts["supp"]:
            print(f"  Hinweis: {f.name} enthält beide Datensätze ({len(parts['main'])} + {len(parts['supp'])} BG) – aufgeteilt")
    return groups, unknown


# ---------------------------------------------------------------- Kennzahlen
def stats(gt, runs_by_ds, keys_filter=None, rng=None):
    """runs_by_ds: {"main": [Lauf...], "supp": [Lauf...]} (1 oder mehrere Läufe je Datensatz).
    Wert je BG = Anteil korrekter Läufe; Accuracy = Mittel über BG; KI: Bootstrap je Datensatz getrennt."""
    shares = {}
    for ds, runs in runs_by_ds.items():
        keys = sorted(set().union(*runs)) if runs else []
        if keys_filter is not None:
            keys = [k for k in keys if keys_filter(k)]
        shares[ds] = np.array([np.mean([R.correct(gt, k, r[k]) for r in runs if k in r]) for k in keys])
    groups = [v for v in shares.values() if len(v)]
    if not groups:
        return None
    allv = np.concatenate(groups)
    boots = np.empty(B)
    for b in range(B):
        boots[b] = np.concatenate([g[rng.integers(0, len(g), len(g))] for g in groups]).mean()
    return dict(acc=float(allv.mean()), lo=float(np.percentile(boots, 2.5)), hi=float(np.percentile(boots, 97.5)),
                n=int(len(allv)))


def prf(gt, runs_by_ds):
    """Macro-P/R/F1 auf eindeutigen BG; bei mehreren Läufen je Lauf berechnet und gemittelt
    (Lauf i des Hauptdatensatzes mit Lauf i der Ergänzung; ist dort nur 1 Lauf, wird er für alle verwendet)."""
    main, supp = runs_by_ds.get("main", []), runs_by_ds.get("supp", [])
    n = max(len(main), len(supp))
    vals = []
    for i in range(n):
        run = {}
        if main:
            run.update(main[min(i, len(main) - 1)])
        if supp:
            run.update(supp[min(i, len(supp) - 1)])
        pairs = [(gt[k][0], run[k]) for k in run if len(gt[k][1]) == 1]
        if pairs:
            vals.append(R.macro_prf(pairs))
    if not vals:
        return None
    return tuple(float(np.nanmean([v[j] for v in vals])) for j in range(3))


def pick_single(groups, key, note, issues_out):
    lst = groups.get(key, [])
    if len(lst) > 1:
        names = ", ".join(f.name for f, _ in lst)
        issues_out.append(f"{key}: {len(lst)} Einzelläufe gefunden ({names}) – der letzte (nach Dateiname) wird verwendet")
    return [lst[-1]] if lst else []


def cell_data(model, col, kind, scope, P, I, Z, issues_out):
    """Liefert (runs_by_ds, Quellen, gelb?) oder None, wenn Daten fehlen."""
    pin = pref(model)
    dss = ["main"] if scope == "115" else ["main", "supp"]
    out, src, fallback = {}, [], False
    for ds in dss:
        runs = []
        if kind == "prompt":
            runs = pick_single(P, (model, col, pin, ds), "", issues_out)
            if not runs and col == "P3":
                runs = pick_single(I, (model, "P3", pin, ds), "", issues_out)
        elif kind == "input":
            runs = pick_single(I, (model, "P3", col, ds), "", issues_out)
            if not runs and col == pin:
                runs = pick_single(P, (model, "P3", pin, ds), "", issues_out)
        if kind in ("prompt", "input") and not runs and ((kind == "prompt" and col == "P3") or
                                                         (kind == "input" and col == pin)):
            z = Z.get((model, "P3", pin, ds), [])
            if z:
                runs, fallback = [z[0]], True          # Lauf 1 der Wiederholungsläufe
        if kind == "regime":
            runs = Z.get((model, "P3", pin, ds), [])
            if len(runs) < 2:                          # keine Wiederholungsläufe: Einzellauf
                single = pick_single(P, (model, "P3", pin, ds), "", issues_out) or \
                    pick_single(I, (model, "P3", pin, ds), "", issues_out)
                if single:
                    runs, fallback = single, True
        if not runs:
            return None, f"{'70' if ds == 'supp' else '115'} BG fehlen", False
        out[ds] = [r for _, r in runs]
        src.append(f"{'115' if ds == 'main' else '70'}: " + (f"{len(runs)} Läufe ({runs[0][0].parent.name})"
                                                              if len(runs) > 1 else runs[0][0].name))
    return out, "; ".join(src), fallback


# ---------------------------------------------------------------- Excel
def de(x, nd=1):
    return f"{x * 100:.{nd}f}".replace(".", ",")


def write(path, tables, gt_name):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    thin, thick = Side(style="thin", color="BFBFBF"), Side(style="medium", color=RED)
    fill = lambda c: PatternFill("solid", fgColor=c)  # noqa: E731
    wb = Workbook()
    ws = wb.active
    ws.title = f"Ergebnisse unter {gt_name}"
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 16
    for j in range(len(COLS)):
        ws.column_dimensions[get_column_letter(2 + j)].width = 17
    src_rows = []
    r = 1
    for scope in ("185", "115"):
        T = tables[scope]
        ws.cell(r, 1, f"Ergebnisse (auf {gt_name}) für {scope} Baugruppen").font = Font(bold=True, size=14)
        r += 2
        for title, key, cols in (
                ("Allowed-Label-Set Accuracy", "acc", COLS),
                ("95%-Bootstrap-Intervall der Allowed-Label-Set Accuracy", "ci", COLS),
                ("Macro-Precision / Macro-Recall / Macro-F1 (nur eindeutige Baugruppen)", "prf",
                 [c for c in COLS if c[0] not in ("mehrdeutig", "Gesamt")])):
            ws.cell(r, 1, title).font = Font(bold=True, size=11)
            r += 1
            ws.cell(r, 1, "Modelle").font = Font(bold=True)
            for j, (c, _) in enumerate(cols):
                cell = ws.cell(r, 2 + j, HEAD.get(c, c))
                cell.font = Font(bold=True)
                cell.fill = fill(GREY)
                cell.alignment = Alignment(horizontal="center")
                cell.border = Border(top=thin, bottom=thin, left=thin, right=thin)
            ws.cell(r, 1).fill = fill(GREY)
            ws.cell(r, 1).border = Border(top=thin, bottom=thin, left=thin, right=thin)
            r += 1
            top = r
            for m in MODELS:
                ws.cell(r, 1, ROWNAME[m]).border = Border(top=thin, bottom=thin, left=thin, right=thin)
                for j, (c, kind) in enumerate(cols):
                    d = T.get((m, c))
                    cell = ws.cell(r, 2 + j)
                    cell.alignment = Alignment(horizontal="center")
                    if (m, c) in NOT_APPLICABLE:
                        cell.fill = fill(NA)
                    elif d is None or d.get("missing"):
                        cell.value = "?" if (m, c) in OPTIONAL else "fehlt"
                        cell.font = Font(italic=True, color="808080")
                    elif key == "acc":
                        cell.value = d["acc"]
                        cell.number_format = "0.0%"
                    elif key == "ci":
                        cell.value = f"[{de(d['lo'])}; {de(d['hi'])}]"
                    else:
                        p = d.get("prf")
                        cell.value = " / ".join(de(x) for x in p) if p else "–"
                    if d and d.get("fallback") and (m, c) not in NOT_APPLICABLE:
                        cell.fill = fill(YELLOW)
                    sides = dict(top=thin, bottom=thin, left=thin, right=thin)
                    if r == top:
                        sides["top"] = thick
                    if m == MODELS[-1]:
                        sides["bottom"] = thick
                    if j == 0:
                        sides["left"] = thick
                    if j == len(cols) - 1:
                        sides["right"] = thick
                    cell.border = Border(**sides)
                r += 1
            r += 1
        # n
        any_d = next((d for d in T.values() if d and not d.get("missing")), None)
        ns = {c: next((d["n"] for (m, cc), d in T.items() if cc == c and d and not d.get("missing")), None)
              for c in ("eindeutig", "mehrdeutig", "Gesamt")}
        if any_d:
            ws.cell(r, 1, f"n Baugruppen: Gesamt {ns['Gesamt']}, eindeutig {ns['eindeutig']}, mehrdeutig {ns['mehrdeutig']}") \
                .font = Font(italic=True, size=9)
            r += 1
        for (m, c), d in T.items():
            if d:
                src_rows.append([scope, ROWNAME[m], HEAD.get(c, c), d.get("src", ""), "ja" if d.get("fallback") else "",
                                 None if d.get("missing") else d.get("n")])
        r += 2
    notes = [
        ("P1–P4: Einzellauf auf pdf (GPT 5.5: Bild, Deepseek: text). pdf/Bild/text: Einzellauf mit P3. "
         "eindeutig/mehrdeutig/Gesamt: P3 mit bevorzugter Eingabe, Mittel der Wiederholungsläufe (10 runs).", False),
        ("Accuracy je Zelle mit 95%-Bootstrap-Intervall (2000 Wiederholungen, Baugruppen mit Zurücklegen, je BG alle "
         "Läufe; bei 185 BG getrennt nach Haupt- und Ergänzungsdatensatz). Macro-P/R/F1 nur auf eindeutigen "
         "Baugruppen (Standardformeln; bei Wiederholungsläufen je Lauf berechnet und gemittelt), ohne Bootstrap.", True),
        (f"Eindeutig: keine weiteren zulässigen Labels in {gt_name}; mehrdeutig: mindestens ein weiteres zulässiges Label. "
         "Prompt-Engineering-Baugruppen ausgeschlossen.", False),
        ("Gelb: Ersatzquelle (Lauf 1 der Wiederholungsläufe statt Einzellauf bzw. Einzellauf statt 10 runs). "
         "Grau: nicht vorgesehen. „?“: optional, noch nicht gelaufen. „fehlt“: Daten fehlen.", False),
    ]
    for txt, red in notes:
        c = ws.cell(r, 1, txt)
        c.font = Font(bold=red, color=RED if red else "000000", size=10)
        r += 1
    ws2 = wb.create_sheet("Quellen")
    ws2.append(["Datensatz", "Modell", "Spalte", "Quelle", "Ersatzquelle", "n BG"])
    for row in src_rows:
        ws2.append(row)
    for c in ws2[1]:
        c.font = Font(bold=True)
        c.fill = fill(GREY)
    E.autosize(ws2, maxw=110)
    wb.save(path)


# ---------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gt", required=True)
    ap.add_argument("--gt-name", default=None, help="Standard: aus Dateiname, z. B. R2.md -> R2")
    ap.add_argument("--prompt", action="append", default=[], help="Ordner mit P1–P4-Ergebnissen")
    ap.add_argument("--input", action="append", default=[], help="Ordner mit pdf/Bild/text-Ergebnissen (P3)")
    ap.add_argument("--zehn", action="append", default=[], help="Ordner mit den Wiederholungsläufen")
    ap.add_argument("--out", default="Ergebnis_R1")
    a = ap.parse_args(argv)
    if not a.gt_name:
        import re as _re
        a.gt_name = (_re.match(r"(R\d+)", Path(a.gt).stem, _re.I) or [Path(a.gt).stem])[0].upper()

    gt, pe, gi = R.load_gt(a.gt)
    for i in gi:
        print("! " + i)
    issues, notes = [], []
    P, u1 = load_runs(files_in(a.prompt), gt, pe, issues, "prompt")
    I, u2 = load_runs(files_in(a.input), gt, pe, issues, "input")
    Z, u3 = load_runs(files_in(a.zehn), gt, pe, issues, "zehn")
    for u in u1 + u2 + u3:
        print("  ! nicht zugeordnet: " + u)
    for name, G in (("Prompt", P), ("Input", I), ("Wiederholung", Z)):
        print(f"{name}: " + ", ".join(f"{ROWNAME.get(m, m)}/{p}/{i}/{'115' if ds == 'main' else '70'}×{len(v)}"
                                       for (m, p, i, ds), v in sorted(G.items())))
    for (m, p, i, ds), v in Z.items():
        if len(v) != 10:
            print(f"  ! Wiederholungsläufe {m} {p} {i} ({'115' if ds == 'main' else '70'} BG): {len(v)} Läufe (erwartet 10)")

    tables = {}
    for scope in ("185", "115"):
        T = {}
        for m in MODELS:
            for c, kind in COLS:
                if (m, c) in NOT_APPLICABLE:
                    T[(m, c)] = None
                    continue
                data, src, fb = cell_data(m, "Gesamt" if kind == "regime" else c, kind, scope, P, I, Z, notes)
                if data is None:
                    T[(m, c)] = {"missing": True, "src": src}
                    continue
                rng = np.random.default_rng(SEED)
                if kind == "regime" and c != "Gesamt":
                    amb = c == "mehrdeutig"
                    st = stats(gt, data, lambda k: (len(gt[k][1]) > 1) == amb, rng)
                else:
                    st = stats(gt, data, None, rng)
                d = dict(st or {}, src=src, fallback=fb)
                if c != "mehrdeutig" and c != "Gesamt":
                    d["prf"] = prf(gt, data)
                T[(m, c)] = d if st else {"missing": True, "src": src}
        tables[scope] = T

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    xlsx = out / f"Ergebnisse_unter_{a.gt_name}.xlsx"
    write(xlsx, tables, a.gt_name)

    for scope in ("185", "115"):
        print(f"\n{scope} BG – Allowed-Label-Set Accuracy (%):")
        print(f"  {'':<14}" + "".join(f"{HEAD.get(c, c):>11}" for c, _ in COLS))
        for m in MODELS:
            row = ""
            for c, _ in COLS:
                d = tables[scope].get((m, c))
                row += f"{'':>11}" if d is None else (f"{'fehlt':>11}" if d.get("missing") else
                                                      f"{d['acc'] * 100:>10.1f}{'*' if d.get('fallback') else ' '}")
            print(f"  {ROWNAME[m]:<14}{row}")
    print("  (* = Ersatzquelle, gelb im Excel)")
    for n in dict.fromkeys(notes):
        print("  ! " + n)
    shown = [i for i in issues if i["Typ"].startswith(("Leere", "Vorhersage nicht", "BG nicht"))]
    if shown:
        groups = {}
        for i in shown:
            groups.setdefault((i["Typ"], i.get("SAP")), []).append(i.get("Modell"))
        print("Hinweise:")
        for (typ, sap), who in groups.items():
            print(f"   - {typ} | {sap} | {len(who)} Datei(en): {', '.join(sorted(set(w.split(' | ')[-1][-40:] for w in who)))[:200]}")
    print(f"\nAusgabe: {xlsx}")
    return tables


if __name__ == "__main__":
    main()
