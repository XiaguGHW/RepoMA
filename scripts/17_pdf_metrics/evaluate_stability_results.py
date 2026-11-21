"""Stabilitätsexperiment: vier finale Konfigurationen × 10 Läufe (P3, 115 BG).

Erwartet einen Ordner mit je einem Unterordner pro Konfiguration, z. B.
    claude_haiku_pdf_P3_10_runs/, gemini-2.5-pro_pdf_P3_10_runs/,
    gpt-5.5_image_P3_10_runs/, deepseek-v4-flash_text_P3_10_runs/
mit je 10 Ergebnisdateien (Blatt Sheet1). Modell und Eingabeform aus dem Ordnernamen.
Backup_Original, __pycache__ und eigene Ausgaben werden übersprungen.

Ausgabe <out>/Stabilitaet_Metriken.xlsx, Blatt Metriken_2x2: je Konfiguration eine Tabelle,
Spalten E1, E2, M, E (E1+E2), Total (n = Baugruppen), Zeilen:
    Allowed Acc., Strict Macro-F1, Allowed Macro-Prec., Allowed Macro-Rec., Strict Acc.
        -> je Lauf berechnet, dann Mittel über die Läufe (wie Tabelle 5.5 / Skript 09)
    SD Allowed Acc. (pp)            -> Standardabweichung der Lauf-Werte (ddof = 1), Prozentpunkte
    BG mit wechselnder Vorhersage   -> Baugruppen mit mindestens zwei verschiedenen gültigen Labels

Leere Vorhersagen zählen im jeweiligen Lauf nicht (wie Skript 09); nicht erkannte Labels zählen als falsch.
Benötigt im selben Ordner: evaluate_pdf_results.py, evaluate_70bg_results.py, evaluate_prompt_results.py,
confusion_human_llm.py, evaluate_validation_regimes.py.

Aufruf (PowerShell):
    python evaluate_stability_results.py --dir "C:\\...\\pdf" --out "C:\\...\\Ergebnis_Stabilitaet" [--nur-sheet1]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evaluate_pdf_results as E  # noqa: E402
import evaluate_70bg_results as S  # noqa: E402  (input_label)

cm = E.cm
SKIP_DIRS = {"backup_original", "__pycache__", "_backup_vor_merge", "nachlauf"}


def strict_acc(recs):
    return sum(r["strict"] for r in recs) / len(recs) if recs else np.nan


def config_stats(runs):
    """runs: Liste von recs (je Lauf). Rückgabe je Teilmenge: Mittelwerte, SD, wechselnde BG."""
    out = {}
    for s in E.SUBSETS:
        per = [E.subset(r, s) for r in runs]
        mets = [E.metrics(p) for p in per]
        row = {k: float(np.nanmean([m[k] for m in mets])) for k in ("acc", "f1", "prec", "rec")}
        row["sacc"] = float(np.nanmean([strict_acc(p) for p in per]))
        accs = [m["acc"] for m in mets if not np.isnan(m["acc"])]
        row["sd"] = float(np.std(accs, ddof=1) * 100) if len(accs) > 1 else np.nan
        preds = {}
        for p in per:
            for r in p:
                preds.setdefault(r["SAP"], set()).add(r["pred"] if r["pred"] is not None else "UNGÜLTIG:" + r["pred_raw"])
        row["var"] = sum(len(v) > 1 for v in preds.values())
        row["n"] = len(preds)
        out[s] = row
    return out


ROWS = [  # (Schlüssel, Beschriftung, Zahlenformat, hervorgehoben)
    ("acc", "Allowed Acc.", "0.0%", True),
    ("f1", "Strict Macro-F1", "0.0%", False),
    ("prec", "Allowed Macro-Prec.", "0.0%", False),
    ("rec", "Allowed Macro-Rec.", "0.0%", False),
    ("sacc", "Strict Acc.", "0.0%", False),
    ("sd", "SD Allowed Acc. (pp)", "0.00", False),
    ("var", "BG mit wechselnder Vorhersage", "0", False),
]


def write_sheet(wb, items):
    from openpyxl.utils import get_column_letter
    St = E.styles()
    Font = St["Font"]
    ws = wb.create_sheet("Metriken_2x2")
    ws.sheet_view.showGridLines = False
    ncol, nrow, gapc, gapr = 6, 2 + len(ROWS), 1, 2
    ws.column_dimensions["A"].width = 2
    for k, (title, stats) in enumerate(items):
        r0 = 2 + (k // 2) * (nrow + gapr)
        c0 = 2 + (k % 2) * (ncol + gapc)
        ws.merge_cells(start_row=r0, start_column=c0, end_row=r0, end_column=c0 + ncol - 1)
        t = ws.cell(r0, c0, title)
        t.font = Font(bold=True, color="FFFFFF", size=12)
        t.alignment = St["center"]
        for j in range(ncol):
            ws.cell(r0, c0 + j).fill = St["fill"](cm.NAVY)
        ws.row_dimensions[r0].height = 22
        heads = ["Metrik"] + [f"{E.SUBSET_HEAD[s]} (n={stats[s]['n']})" for s in E.SUBSETS]
        for j, h in enumerate(heads):
            c = ws.cell(r0 + 1, c0 + j, h)
            c.font = Font(bold=True, color="FFFFFF")
            c.fill, c.border = St["fill"](cm.HEAD), St["border"]
            c.alignment = St["left"] if j == 0 else St["center"]
        for i, (key, label, fmt, hi) in enumerate(ROWS):
            rr = r0 + 2 + i
            bg = E.ACC_ROW_BG if hi else (E.ODD_ROW_BG if i % 2 else "#FFFFFF")
            c = ws.cell(rr, c0, label)
            c.font = Font(bold=hi, color=E._xl(cm.DARK_TXT) if hi else "000000")
            c.fill, c.alignment, c.border = St["fill"](bg), St["left"], St["border"]
            for j, s in enumerate(E.SUBSETS):
                v = stats[s][key]
                c = ws.cell(rr, c0 + 1 + j, None if (isinstance(v, float) and np.isnan(v)) else v)
                c.number_format = fmt
                c.font = Font(bold=hi or s == "Total")
                c.fill, c.alignment, c.border = St["fill"](bg), St["right"], St["border"]
    for k in range(2):
        c0 = 2 + k * (ncol + gapc)
        ws.column_dimensions[get_column_letter(c0)].width = 29
        for j in range(1, ncol):
            ws.column_dimensions[get_column_letter(c0 + j)].width = 17
        ws.column_dimensions[get_column_letter(c0 + ncol)].width = 3
    nr = 2 + ((len(items) + 1) // 2) * (nrow + gapr) - 1
    notes = [
        "Werte in %: je Lauf berechnet, dann Mittel über die Läufe. SD: Standardabweichung der Allowed Acc. über die Läufe (Prozentpunkte).",
        "BG mit wechselnder Vorhersage: Baugruppen, für die über die Läufe mindestens zwei verschiedene Labels vergeben wurden.",
        "Strict Macro-F1 und Strict Acc.: nur das Primärlabel zählt. Allowed Macro-Prec./-Rec.: Formel 5.2a/5.2b.",
        "Regime: M ohne weiteres zulässiges Label zählt als E2. GT, Register und zulässige Labels aus Sheet1 der jeweiligen Datei.",
    ]
    for i, txt in enumerate(notes):
        ws.cell(nr + i, 2, txt).font = Font(italic=True, size=9, color="595959")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", required=True, help="Ordner mit den Konfigurations-Unterordnern")
    ap.add_argument("--sheet", default="Sheet1")
    ap.add_argument("--out", default="Ergebnis_Stabilitaet")
    ap.add_argument("--nur-sheet1", action="store_true",
                    help="danach in allen Lauf-Dateien alle Blätter außer --sheet löschen "
                         "(Sicherung in <out>/<Konfigurationsordner>/Backup_Original)")
    a = ap.parse_args(argv)

    root = Path(a.dir)
    configs, issues = [], []
    for d in sorted(p for p in root.iterdir() if p.is_dir() and p.name.lower() not in SKIP_DIRS
                    and not p.name.lower().startswith("_backup_vor_merge")):
        files = sorted(f for f in d.rglob("*") if f.suffix.lower() in (".xlsx", ".xlsm")
                       and not E.is_output_or_backup(f))
        if not files:
            continue
        name, inp = E.model_name(d), S.input_label(d)
        runs = [E.read_file(f, a.sheet, f"{name} | {f.name}", issues) for f in files]
        configs.append((name, inp, d, runs, files))
    if not configs:
        sys.exit(f"Keine Unterordner mit Ergebnisdateien in {root.resolve()}")
    configs.sort(key=lambda x: E.model_rank(x[0]))

    from openpyxl import Workbook
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    wb.remove(wb.active)
    items = []
    print("Konfigurationen:")
    for name, inp, d, runs, _ in configs:
        st = config_stats(runs)
        items.append((f"{name} (115BG, P3, {inp}, {len(runs)} runs)", st))
        t = st["Total"]
        ns = " / ".join(str(st[s]["n"]) for s in ["E1", "E2", "M"])
        print(f"  {name:<20} {inp:<6} {len(runs):>2} Läufe  ({d.name})")
        print(f"      n={t['n']} (E1/E2/M {ns})  Allowed Acc {t['acc']*100:.1f}  Strict Acc {t['sacc']*100:.1f}  "
              f"Strict Macro-F1 {t['f1']*100:.1f}  SD {t['sd']:.2f}  wechselnd {t['var']} (M {st['M']['var']})")
        lens = [len(r) for r in runs]
        if min(lens) != max(lens):
            print(f"      ! gewertete BG je Lauf unterschiedlich: {lens}")
    write_sheet(wb, items)
    xlsx = out / "Stabilitaet_Metriken.xlsx"
    wb.save(xlsx)
    print(f"Ausgabe: {xlsx}")

    shown = [i for i in issues if not i["Typ"].startswith("Info:")]
    if shown:
        print("Hinweise (gleiche Hinweise zusammengefasst):")
        groups = {}
        for i in shown:
            groups.setdefault((i["Typ"], i.get("SAP"), i.get("Detail")), []).append(i.get("Modell"))
        for (typ, sap, det), who in groups.items():
            where = f"{len(who)} Dateien" if len(who) > 2 else ", ".join(who)
            print("   - " + " | ".join(str(x) for x in [typ, sap, det, where] if x))
    if a.nur_sheet1:
        for name, inp, d, runs, files in configs:
            # eigener Sicherungsordner je Konfiguration (Dateinamen wie Run_01.xlsx wiederholen sich)
            E.keep_only_sheet(files, a.sheet, out / d.name)
    return configs


if __name__ == "__main__":
    main()
