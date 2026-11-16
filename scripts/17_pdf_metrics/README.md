# 17 — Metriktabellen und Konfusionsmatrizen der PDF-Ergebnisse (115 BG, P3)

`evaluate_pdf_results.py` liest je Modell eine Ergebnisdatei (Blatt `Sheet1`) und erzeugt:

- **Metriken_2x2**: vier Tabellen im 2×2-Raster (oben Haiku | Gemini Pro, unten Opus | Gemini Flash),
  Spalten E1, E2, M, E (E1+E2), Total mit n; Zeilen Allowed Acc., Strict Macro-F1, Allowed Macro-Prec., Allowed Macro-Rec.
- **Konfusion_2x2**: Konfusionsmatrizen wie in der Arbeit (Diagonale blau, links rot = nicht zulässig,
  rechts grün = weiteres zulässiges Label), dazu `konfusion_2x2.png` (300 dpi).
- Nur diese zwei Blätter; Hinweise (Abweichungen von `Allowed_Set_Status`, Register, unbekannte Labels) erscheinen in der Konsole.
- Option `--nur-sheet1`: löscht danach in den Ergebnisdateien alle Blätter außer `Sheet1` (Sicherungskopie in `<out>/Backup_Original`). Gilt auch für die Image-/Text-Varianten.

Regeln:
- GT, Register und weitere zulässige Labels aus `Sheet1` der Datei; FINAL_GT (Skript 12) nur als Info-Abgleich.
- `Allowed_Set_Status` wird nicht übernommen, sondern neu berechnet und abgeglichen (Abweichungen in der Konsole).
- Register M ohne weiteres zulässiges Label (z. B. 0804EN7325) zählt als E2.
- Klassenmittel wie Skript 09: Precision über vorhergesagte Klassen, Recall über Klassen der GT,
  Strict-F1 über Klassen in GT oder Vorhersage.
- Schreibweisen wie `Gantry`, `Umsetzeinheit`, Kodierungsfehler werden über `canon` (Skript 13/12) vereinheitlicht.
- Modellname aus dem Dateinamen (`haiku`, `opus`, `gemini-2.5-pro`, `gemini-2.5-flash`, `gpt`, `deepseek`).

## Aufruf (PowerShell)

```
conda activate thesis
cd <Repo>\scripts\17_pdf_metrics
python evaluate_pdf_results.py "...\haiku.xlsx" "...\gemini-2.5-pro.xlsx" "...\opus.xlsx" "...\gemini-2.5-flash.xlsx" --out PDF_Metriken
# oder
python evaluate_pdf_results.py --dir "...\PDF_Ordner" --out PDF_Metriken
```

Optionen: `--subtitle "115BG, P3, PDF"`, `--input-label PDF`, `--lang de`, `--height 0.7`, `--no-png`, `--sheet Sheet1`.

## Selbsttest

```
python selftest_evaluate_pdf_results.py
```

## Image-Ergebnisse

`evaluate_image_results.py` ruft `evaluate_pdf_results.py` unverändert auf (gleicher Ordner) und setzt nur Titel `(115BG, P3, Image)` / `(Image)` sowie die Dateinamen `Image_Metriken_Konfusion.xlsx` und `konfusion_image_2x2.png`.

```
python evaluate_image_results.py --dir "C:\pdf\image" --out "C:\pdf\Ergebnis_Image"
```

## Text-Ergebnisse

`evaluate_text_results.py` wie oben, Titel `(115BG, P3, Text)` / `(Text)`, Ausgabe `Text_Metriken_Konfusion.xlsx` und `konfusion_text_2x2.png`.

```
python evaluate_text_results.py --dir "C:\pdf\text" --out "C:\pdf\Ergebnis_Text"
```

## Prompt-Vergleich (P1–P4 × 4 Modelle)

`evaluate_prompt_results.py`: 16 Dateien (auch in Unterordnern), Prompt und Modell aus Datei- bzw. Ordnernamen. Ausgabe `Prompt_Metriken_Konfusion.xlsx` mit `Uebersicht` (Allowed Accuracy und Strict Macro-F1 je Modell × Prompt wie Tabelle 5.3, mit n), `Metriken_4x4`, `Konfusion_4x4`, dazu `konfusion_prompt_4x4.png`. Fehlende Kombinationen und Hinweise in der Konsole.

```
python evaluate_prompt_results.py --dir "C:\pdf\prompt" --out "C:\pdf\Ergebnis_Prompt" [--nur-sheet1]
```
