# 12 — Validierung (70 BG) und Ergebnisse nach Regime (185 BG)

`evaluate_validation_regimes.py` erzeugt die Zahlen für Abschnitt 5.6 (offline, keine Modellaufrufe).

| Blatt | Inhalt |
|---|---|
| Tabelle_5_6 | E1+E2: 115 BG (Mittel über 10 Läufe) gegen 70 BG (1 Lauf), je Konfiguration, mit 95%-CI und Δ |
| Tabelle_5_7 | Alle 185 BG nach E1, E2, M; für M zusätzlich Anteil Primärlabel / weiteres zulässiges Label |
| M_im_70er_Satz | Vorhersagen für die einzige M-Baugruppe des Ergänzungsdatensatzes |
| Klassen_E1E2_115_vs_70 | Klassenweise Accuracy (E1+E2) in beiden Datensätzen |
| Pruefung_Regime | Regime-Verteilung gegen Erwartung (115: 51/34/30, 70: 59/10/1) |
| Pruefungen | Ungültige Labels, abweichende GT zwischen Dateien, EXCLUDED, durch finale GT ersetzte Werte |
| Fehler_BG | Jede Baugruppe mit mindestens einem Fehler: Vorhersagen je Konfiguration (k/n Läufe), Regime, ob unter den 57 BG der bisherigen Fehleranalyse |
| Fehler_GPT_DeepSeek | Wie Fehler_BG, nur Baugruppen mit Fehlern bei GPT-5.5 oder DeepSeek-V4-Flash |
| Konfusion_LLM_1Lauf | Alle Vorhersagen, ein Lauf je Baugruppe (115 BG: Lauf 1, 70 BG: einziger Lauf), Primärlabel × Vorhersage, Anzahl und Zeilenprozent; für den Vergleich mit der manuellen Klassifikation |
| Konfusion_Fehler | Fehlerhafte Vorhersagen: Primärlabel × Vorhersage, gesamt und je Konfiguration |

Zusammenführung: 115 BG je Baugruppe Anteil korrekter Läufe, 70 BG 0/1; Mittelwerte und
Bootstrap-CIs (B = 2000) über Baugruppen. Regime: M = mehr als ein zulässiges Label, sonst Spalte `Register`.

## Aufruf

Skript in den Ordner `test_claude` legen (dort liegen die vier 10-Lauf-Ordner), dann in VS Code:

```
python evaluate_validation_regimes.py --main . --supp ..\70BG_Ergebnisse
```

Der Ordner `gemini-2.5-flash_pdf_P3_10_runs` wird automatisch ignoriert.
