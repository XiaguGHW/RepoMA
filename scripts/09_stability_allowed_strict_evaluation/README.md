# 09 — Stabilitätsanalyse: Allowed- und Strict-Metriken mit Konfidenzintervallen

`evaluate_allowed_strict.py` wertet die 10 Wiederholungsläufe je Modell offline aus
(keine Modellaufrufe). Es berechnet Allowed- und Strict-Metriken, 95%-Konfidenzintervalle
per Bootstrap über Baugruppen, gepaarte Modellvergleiche, Ausfälle (EXCLUDED) und
Datenprüfungen.

## Verwendung

Skript in denselben Ordner legen wie die Modellordner:

```
<Ordner>/
    evaluate_allowed_strict.py
    claude_haiku_pdf_P3_10_runs/
    gemini-2.5-pro_pdf_P3_10_runs/
    gemini-2.5-flash_pdf_P3_10_runs/
    deepseek-v4-flash_text_P3_10_runs/
    gpt-5.5_image_P3_10_runs/
```

```
python evaluate_allowed_strict.py
```

Ausgabe: `Evaluation_Allowed_Strict.xlsx` im selben Ordner. Benötigt `pandas`, `numpy`, `openpyxl`.

## Eingabe (Sheet1 je Lauf-Datei)

Verwendete Spalten: `SAP-Nummer`, `Ground Truth`, `Weitere zulässige Ground Truth`
(kommagetrennt), `Predicted_Label`, `Allowed_Set_Status`, `Register` (nur für Prüfungen).

- Modellname und Eingabeformat: aus dem Ordnernamen.
- Laufreihenfolge: `Run_XX` im Dateinamen, sonst Zeitstempel.
- `EXCLUDED` bzw. leere Vorhersage (HTTP-Fehler) wird je Lauf nicht gewertet.
- Synonyme laut Codebook in `SYNONYMS` (Gantry, Umsetzeinheit, Kodierungsfehler bei „verfügbaren“).

## Ausgabe-Tabellenblätter

| Blatt | Inhalt |
|---|---|
| Hauptergebnis | Allowed/Strict Accuracy, Macro-P/R, Strict Macro-F1 mit 95%-CI |
| Klassen_Allowed_Recall / _Precision | Klassenweise Allowed-Metriken mit n |
| Klassen_Strict_F1 / _Precision / _Recall | Strict-Vergleich |
| Paarvergleich | Gepaarter Bootstrap zwischen Modellen |
| Robustheit_gemeinsam | Nur Baugruppen mit Ausgabe in allen Läufen aller Modelle |
| Accuracy_CLT | Analytisches CI für Accuracy |
| Run_to_run_SD, Pro_Lauf | Stabilität über Läufe |
| Ausfaelle_pro_Lauf / _pro_SAP | EXCLUDED-Statistik |
| Stabilitaet | Baugruppen mit wechselnder Vorhersage |
| Pruefungen | Abweichungen zu `Allowed_Set_Status`, Register-/ZGT-Konsistenz, ungültige Labels |
| Hinweise | Definitionen der Metriken |
