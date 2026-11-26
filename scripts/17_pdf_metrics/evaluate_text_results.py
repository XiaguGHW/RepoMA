"""Wie evaluate_pdf_results.py, aber für die Text-Ergebnisdateien (alle Modelle in --dir, P3, 115 BG).

Nutzt evaluate_pdf_results.py unverändert (muss im selben Ordner liegen, ebenso
confusion_human_llm.py und evaluate_validation_regimes.py) und benennt nur Titel und Ausgabedateien um:
    Titel Metriken : "<Modell> (115BG, P3, Text)"
    Titel Matrizen : "<Modell> (Text), n = …"
    Ausgabe        : Text_Metriken_Konfusion.xlsx, konfusion_text_2x2.png

Aufruf (PowerShell):
    python evaluate_text_results.py --dir "C:\\pdf\\text" --out "C:\\pdf\\Ergebnis_Text"
Weitere Optionen wie bei evaluate_pdf_results.py (--lang, --height, --no-png, --sheet).
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evaluate_pdf_results as E  # noqa: E402

LABEL = "Text"


def has_opt(argv, name):
    return any(a == name or a.startswith(name + "=") for a in argv)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not has_opt(argv, "--subtitle"):
        argv += ["--subtitle", f"115BG, P3, {LABEL}"]
    if not has_opt(argv, "--input-label"):
        argv += ["--input-label", LABEL]
    if not has_opt(argv, "--out"):
        argv += ["--out", f"{LABEL}_Metriken"]
    out = Path(argv[argv.index("--out") + 1]) if "--out" in argv else Path(
        next(a for a in argv if a.startswith("--out=")).split("=", 1)[1])

    res = E.main(argv)

    renames = [("PDF_Metriken_Konfusion.xlsx", f"{LABEL}_Metriken_Konfusion.xlsx"),
               ("konfusion_2x2.png", f"konfusion_{LABEL.lower()}_2x2.png")]
    for old, new in renames:
        src = out / old
        if src.is_file():
            src.replace(out / new)
            print(f"  -> {out / new}")
    return res


if __name__ == "__main__":
    main()
