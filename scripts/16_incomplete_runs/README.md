# 16 – Unvollständige Läufe finden

`find_incomplete_runs.py` listet je Ergebnisdatei die Baugruppen ohne gültige Vorhersage
(fehlt / leer / ungültig / Fehler). Referenz: alle Baugruppen, die in den durchsuchten Dateien
desselben Datensatzes vorkommen (`70BG` im Namen → 70er-Satz, sonst Hauptsatz), oder `--reference`.

```powershell
python find_incomplete_runs.py --root C:\Users\...\Downloads\test_claude
python find_incomplete_runs.py --root <Prompt-Ordner> --root <Input-Ordner> --reference <vollständige 115er-Datei>
```

Benötigt `evaluate_validation_regimes.py` (Skript 12) im selben Ordner für die Klassen-Normalisierung.
Ausgabe: `Unvollstaendige_Laeufe.xlsx` (Uebersicht, Fehlende_BG).
