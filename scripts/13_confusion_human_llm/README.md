# 13 — Konfusionsmatrizen Mensch vs. LLM (115 BG, Abschnitt 5.7)

`confusion_human_llm.py` vergleicht die manuelle Klassifikation im Workshop mit den vier finalen
LLM-Konfigurationen auf den 115 Baugruppen des Primärdatensatzes (129 ohne die 14 des Vorversuchs).
Offline, keine Modellaufrufe.

| Matrix | Quelle |
|---|---|
| Mensch | Blatt `Klassifikation_Übersicht_Gesamt` der Workshop-Auswertung; jede Zelle in einer Spalte `TN_…` = eine Klassifikation |
| Claude Haiku 4.5 (PDF), Gemini 2.5 Pro (PDF) | Lauf des Input-Vergleichs (PDF, P3) |
| GPT-5.5 (Image), DeepSeek-V4-Flash (Text) | Lauf 1 des Stabilitätsexperiments (`test_claude`) |

- Zeilen = Primärlabel der **finalen GT** (`FINAL_GT` aus `../12_validation_regimes`), Spalten = vergebene Klasse.
  Die GT in den Ergebnisdateien und die Spalte `Ground Truth` der Workshop-Tabelle werden nicht verwendet;
  Abweichungen stehen in `Pruefung_GT_ersetzt`.
- Klassencodes: A = Gantry, B = Rotationseinheit, C = Roboter, D = Greifer, E = Lineareinheit,
  F = Kombinierte Einheit, G = Keine der verfügbaren Klassen.
- Darstellung Variante A1: Diagonale blau (Primärlabel); sonst geteilt, links rot = nicht zulässig,
  rechts grün = weiteres zulässiges Label (nur M); leere Hälfte graue 0; Zelle ganz 0 = graue 0. Absolute Zahlen.
- SAP-Nummern ohne führende Null (`804306221`), Teamcenter als Ersatzschlüssel, Schreibweisen
  `Gantry`, `Multi-Achs-System (Gantry)`, `Umsetzeinheit`, Kodierungsfehler bei „verfügbaren“ werden erkannt.

## Aufruf (PowerShell, Conda-Umgebung `thesis`)

```
conda activate thesis
cd <Repo>\scripts\13_confusion_human_llm
python confusion_human_llm.py `
  --workshop "C:\...\Workshop_Auswertung.xlsx" `
  --haiku    "C:\...\<PDF-Ordner>\<haiku-Datei>.xlsx" `
  --gemini   "C:\...\<PDF-Ordner>\<gemini-2.5-pro-Datei>.xlsx" `
  --gpt      "C:\...\test_claude\gpt-5.5_image_P3_10_runs\<Run_1>.xlsx" `
  --deepseek "C:\...\test_claude\deepseek..._text_P3_10_runs\<Run_1>.xlsx" `
  --out Konfusion_Mensch_LLM
```

Optional: `--sheet <Blattname>`, `--lang de` (Abbildungen deutsch; Standard englisch).

## Ausgabe (`--out`)

- `konfusion_gesamt.png`: links 2×2 LLM, rechts Mensch; Legende und Hinweis darunter.
- `konfusion_mensch.png`, `konfusion_haiku.png`, `konfusion_gemini.png`, `konfusion_gpt.png`, `konfusion_deepseek.png`.
- `Konfusion_Mensch_LLM.xlsx`:
  `Uebersicht` (n, Diagonale/grün/rot, Allowed/Strict Accuracy je Matrix), `M_…` (Gesamt-, Rot- und Grün-Matrix),
  `Lang` (alle Zellen), `Pruefung_Zusammenfassung` (Anzahl Klassifikationen, Personen je BG, Regime 51/34/30,
  Vergleichszahl 129 BG für die frühere Matrix mit 895), `Pruefung_BG` (115 Zeilen: Personen, Vorhersagen,
  `PRÜFEN` außerhalb 5–10), `Pruefung_Teilnehmer`, `Pruefung_GT_ersetzt`, `Pruefung_Labels_unbekannt`,
  `Pruefung_Hinweise` (alles), `Legende`.

Hinweis: Die Zellen der Workshop-Tabelle sind Formeln mit externen Verknüpfungen. Gelesen werden die
in Excel gespeicherten Werte; vorsichtshalber eine Kopie mit „Werte einfügen“ verwenden.

## Selbsttest

```
python selftest_confusion_human_llm.py
```

Simulierte Workshop-Tabelle und LLM-Dateien (inkl. fehlender Nullen, Synonymen, unbekanntem Label,
doppelter Zeile, alter GT, EXCLUDED); vergleicht alle Matrizen mit einer unabhängigen Berechnung und prüft
die Farben der geteilten Zellen per Pixel. Ausgabe in `_selftest/` (nicht versioniert).
