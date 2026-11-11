# 15 – Kosten je Baugruppe (Abschnitt 5.8)

`summarize_costs.py` liest `Token_Usage_JSON` (Blatt Sheet1) der Ergebnisdateien der vier finalen
Konfigurationen, erkennt das Format (Gemini, Anthropic, OpenAI, DeepSeek; bei der Connector-Hülle
werden die Rohdaten in `raw_usage` verwendet) und rechnet mit der Preistabelle `PRICES` im Skript.
Gemini-Thinking-Token zählen als Output. Für Claude Opus 4.8 wird eine Schätzung mit den Token von
Claude Haiku 4.5 ausgegeben.

Zeit: Falls keine Dauer-Spalte existiert, wird der Abstand zwischen den Zeitstempeln (`Run_Time`)
aufeinanderfolgender Anfragen verwendet (nur Abstände unter 15 min); Median robuster als Mittel.

```powershell
python summarize_costs.py --dir ..\70BG_Ergebnisse
```

Ausgabe `Kosten_5_8.xlsx`: Zusammenfassung, Je_Baugruppe, Preise, Hinweise.
**Preise vor der Verwendung prüfen** (Stand der Experimente, Zugangsweg).
