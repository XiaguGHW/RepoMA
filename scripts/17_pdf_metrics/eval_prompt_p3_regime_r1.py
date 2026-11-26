"""P3-Einzelläufe aus 01_Prompt_P1-P4 unter R1 nach Teilmengen auswerten (wie eval_input_regime_r1.py).

Je Modell (P3 mit bevorzugter Eingabe: pdf, GPT-5.5 Bild, DeepSeek text) × Datensatz (115 / 185 BG):
Allowed und Strict Accuracy für alle / eindeutig / mehrdeutig / E1 / E2 / M (R1-Register).

Aufruf:
    python eval_prompt_p3_regime_r1.py --prompt "..\\01_Prompt_P1-P4" --gt R1.md --out "..\\05_Ergebnisse_R1\\Prompt_P3_Teilmengen_R1.xlsx"
Benötigt im selben Ordner: eval_input_regime_r1.py, evaluate_r1_ergebnisse.py, evaluate_r1.py (+ Abhängigkeiten).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eval_input_regime_r1 as M  # noqa: E402

if __name__ == "__main__":
    M.main(kind="prompt", default_out="Prompt_P3_Teilmengen_R1.xlsx", only_pref=True)
