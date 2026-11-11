# 15 – Kosten je Baugruppe (Abschnitt 5.8)

`summarize_costs.py` liest `Token_Usage_JSON` (Blatt Sheet1) der Ergebnisdateien der vier finalen
Konfigurationen, erkennt das Format (Gemini, Anthropic, OpenAI, DeepSeek; bei der Connector-Hülle
werden die Rohdaten in `raw_usage` verwendet) und rechnet mit der Preistabelle `PRICES` im Skript.
Gemini-Thinking-Token zählen als Output.
Claude Opus 4.8 wird aus der eigenen Ergebnisdatei (115 BG, P3) gelesen.

Zeit: Vorrang hat die von der API gemeldete Latenz (`latency_checkpoint.service_ttlt_ms`, nur GPT-5.5 über Azure). Sonst, falls keine Dauer-Spalte existiert, wird der Abstand zwischen den Zeitstempeln (`Run_Time`)
aufeinanderfolgender Anfragen verwendet (nur Abstände unter 15 min); Median robuster als Mittel.

```powershell
python summarize_costs.py --dir $HOME\Downloads\Token
```

Ausgabe `Kosten_5_8.xlsx`: Zusammenfassung, Je_Baugruppe, Preise, Hinweise.
**Preise vor der Verwendung prüfen** (Stand der Experimente, Zugangsweg).

Zeit aus den Läufen: `--runs <Ordner mit den 10-Lauf-Ordnern>` nimmt je Ergebnisdatei die Startzeit
(`Run_Time`) und teilt den Abstand zum Start des nächsten Laufs derselben Konfiguration durch die Zahl
der Baugruppen (nur Abstände unter 6 h). Setzt voraus, dass die Läufe direkt nacheinander gestartet
wurden; Blatt `Zeit_aus_Laeufen` zeigt jeden Abstand zur Kontrolle.

```powershell
python summarize_costs.py --dir $HOME\Downloads\Token --runs .
```
