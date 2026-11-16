"""Ergänzungsdatensatz (70 BG): vier finale Konfigurationen, je ein Lauf, P3.

Typisch: pdf_only_70BG_P3_claude-haiku…, pdf_only_70BG_P3_gemini-2.5-pro…, image_only_70BG_P3_gpt-5.5…,
text_only_70BG_P3_deepseek-v4-flash… . Eingabeform aus dem Dateinamen (pdf_/image_/text_),
Modell wie in evaluate_pdf_results.py. Mit --dir werden nur Dateien mit "70BG" im Namen gelesen.

Die Dateien brauchen keine Spalte Allowed_Set_Status: korrekt/falsch wird aus Ground Truth und
"Weitere zulässige Ground Truth" berechnet (wie in den anderen Skripten).

Benötigt im selben Ordner: evaluate_pdf_results.py, evaluate_prompt_results.py,
confusion_human_llm.py, evaluate_validation_regimes.py.

Ausgabe <out>/70BG_Metriken_Konfusion.xlsx (Metriken_2x2, Konfusion_2x2) und konfusion_70bg_2x2.png.

Aufruf (PowerShell):
    python evaluate_70bg_results.py --dir "C:\\...\\pdf" --out "C:\\...\\Ergebnis_70BG" [--nur-sheet1]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evaluate_pdf_results as E  # noqa: E402
import evaluate_prompt_results as P  # noqa: E402


def input_label(path):
    s = Path(path).name.lower()
    for key, lab in [("pdf", "PDF"), ("image", "Image"), ("img", "Image"), ("text", "Text"), ("txt", "Text")]:
        if re.match(rf"{key}[_\-]", s) or f"_{key}_" in s or f"-{key}-" in s:
            return lab
    return "?"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*")
    ap.add_argument("--dir", help="Ordner; gelesen werden nur .xlsx mit '70BG' im Namen")
    ap.add_argument("--sheet", default="Sheet1")
    ap.add_argument("--out", default="Ergebnis_70BG")
    ap.add_argument("--lang", choices=["en", "de"], default="en")
    ap.add_argument("--height", type=float, default=0.7)
    ap.add_argument("--no-png", action="store_true")
    ap.add_argument("--nur-sheet1", action="store_true",
                    help="danach in den Ergebnisdateien alle Blätter außer --sheet löschen (Sicherung in <out>/Backup_Original)")
    a = ap.parse_args(argv)

    files = [Path(f) for f in a.files]
    if a.dir:
        files += sorted(p for p in Path(a.dir).glob("*")
                        if p.suffix.lower() in (".xlsx", ".xlsm") and "70bg" in p.name.lower()
                        and not E.is_output_or_backup(p))
    if not files:
        ap.error("keine 70BG-Dateien gefunden (Dateien oder --dir)")
    print(f"{len(files)} Datei(en):")
    for f in files:
        print(f"  {f.name}")

    issues, results = [], []
    for f in files:
        name, inp = E.model_name(f), input_label(f)
        if any(n == name for n, _, _ in results):
            sys.exit(f"Modell '{name}' doppelt erkannt ({f.name}). Dateinamen prüfen.")
        recs = E.read_file(f, a.sheet, name, issues)
        results.append((name, inp, recs))
    results.sort(key=lambda x: E.model_rank(x[0]))

    from openpyxl import Workbook
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    wb.remove(wb.active)
    m_items = [(f"{n} (70BG, P3, {inp})", recs) for n, inp, recs in results]
    c_items = []
    for n, inp, recs in results:
        mat = E.matrix_for(recs)
        c_items.append((f"{n} ({inp}), n = {mat['n']}", mat))
    P.write_metric_grid(wb, m_items, 2)
    P.write_confusion_grid(wb, c_items, 2, a.lang)
    wb["Metriken_4x4"].title = "Metriken_2x2"
    wb["Konfusion_4x4"].title = "Konfusion_2x2"
    xlsx = out / "70BG_Metriken_Konfusion.xlsx"
    wb.save(xlsx)
    if not a.no_png:
        P.save_png(c_items, 2, out / "konfusion_70bg_2x2.png", a.lang, a.height)

    print(f"Ausgabe: {xlsx}")
    for n, inp, recs in results:
        tot = E.metrics(recs)
        ns = " / ".join(str(len(E.subset(recs, s))) for s in ["E1", "E2", "M"])
        print(f"  {n:<20} {inp:<6} n={tot['n']:>3} (E1/E2/M {ns})  Allowed Acc {tot['acc']*100:5.1f}%  "
              f"Strict Macro-F1 {tot['f1']*100:5.1f}%")
    shown = [i for i in issues if not i["Typ"].startswith("Info:")]
    if shown:
        print("  Hinweise (gleiche Hinweise zusammengefasst):")
        groups = {}
        for i in shown:
            groups.setdefault((i["Typ"], i.get("SAP"), i.get("Detail")), []).append(i.get("Modell"))
        for (typ, sap, det), who in groups.items():
            where = "alle Dateien" if len(who) == len(results) and len(results) > 1 else ", ".join(who)
            print("   - " + " | ".join(str(x) for x in [typ, sap, det, where] if x))
    if a.nur_sheet1:
        E.keep_only_sheet(files, a.sheet, out)
    return results


if __name__ == "__main__":
    main()
