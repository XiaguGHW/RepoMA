# 10 — Prüfung Allowed_Set_Status und Konfusionsmatrizen

`check_allowed_and_confusion_matrix.py` arbeitet offline auf den Ergebnisdateien (Sheet1) der
Einzel-Experimente (PDF/Bild/Text, verschiedene Prompts).

1. **Prüfung:** Für jede Zeile wird neu berechnet, ob die Vorhersage in
   {Ground Truth} ∪ {Weitere zulässige Ground Truth} liegt (kommagetrennt, Synonyme laut Codebook:
   Gantry, Umsetzeinheit, Kodierungsfehler bei „verfügbaren“), und mit `Allowed_Set_Status` verglichen.
   Leere Vorhersagen müssen `EXCLUDED` sein. Zeilen mit `prompt_engineering = yes` werden nicht gewertet
   (`EXCLUDE_PROMPT_ENGINEERING`).
2. **Konfusionsmatrix:** Nur für Dateien ohne Abweichungen (oder mit `--force`).
   Zeilen = Ground Truth (Primärlabel), Spalten = Vorhersage, Klassen A–G.
   Titel: `Modell (nBG, Prompt, Eingabe)`, n = ausgewertete Baugruppen (ohne EXCLUDED).

## Aufruf

```
python check_allowed_and_confusion_matrix.py                    # alle .xlsx unterhalb des Skriptordners
python check_allowed_and_confusion_matrix.py <Ordner|Datei> ...
python check_allowed_and_confusion_matrix.py --force <Ordner>   # Matrizen auch bei Abweichungen
```

Modell, Prompt und Eingabeformat werden aus Datei- und Ordnernamen erkannt
(z. B. Ordner `gpt-5.5_image_P3_...` → GPT 5.5, P3, Bild).

## Ausgabe (im aktuellen Arbeitsordner)

- `Konfusionsmatrizen.xlsx`: Blätter `Pruefung` (je Datei), `Abweichungen` (mit Excel-Zeile),
  `Konfusionsmatrizen` (Blau-Layout, zwei Matrizen nebeneinander), `Legende` (A–G).
- `konfusionsmatrizen_png/`: je Matrix ein PNG (nur wenn `matplotlib` installiert ist).

Benötigt: `pandas`, `numpy`, `openpyxl` (optional `matplotlib`).
