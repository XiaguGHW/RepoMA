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

## Nachlauf-Experimente erzeugen

Mit `--input-dataset` und/oder `--input-dir` legt das Skript je unvollständiger Ergebnisdatei einen
Ordner unter `--rerun-out` (Standard `Nachlauf`) an:

- `--input-dataset <xlsx>`: sucht die fehlenden Baugruppen über SAP-Nummer **oder** Teamcenter-Nummer
  in der vollständigen Eingabeliste (Blatt `Experiment_Dataset`, sonst erstes Blatt; anders mit
  `--sheet-name`) und schreibt die vollständigen Zeilen nach `nachlauf_dataset.xlsx` (gleiche Spalten,
  gleicher Blattname; `prompt_engineering` wird auf `yes` gesetzt, damit der Standardlauf sie auswählt).
- `--input-dir <Ordner>`: kopiert den Baugruppen-Ordner, dessen Name die SAP- oder Teamcenter-Nummer
  enthält, in den Nachlauf-Ordner.
- Vergleich ohne Groß-/Kleinschreibung, Punkte, Leerzeichen und führende Nullen (`0804.BR4.641` = `804BR4641`).
- `--nur-leer`: nur leere Ausgaben und ERROR, nicht fehlende Zeilen oder ungültige Labels.

`Nachlauf/Nachlauf_Uebersicht.xlsx` listet jede Baugruppe mit gefundener Zeile, kopiertem Ordner und
Spalte `Gefunden` (False = nicht zugeordnet, bitte prüfen).

```powershell
python find_incomplete_runs.py --root <Prompt-Ordner> --input-dataset <...\classification_experiment_dataset.xlsx> --input-dir <BG-Eingabeordner>
python run_prompt_development.py --prompt-config P2 --model gemini-2.5-flash --input-excel Nachlauf\<Ordner>\nachlauf_dataset.xlsx
```

## Eine Nachlauf-Eingabe je Modell (`--pro-modell`)

Für Wiederholungsläufe (Ordner `*_10_runs`): statt je Ergebnisdatei ein Ordner je Modellordner mit
**einer** `nachlauf_dataset.xlsx` (alle fehlenden BG aller Läufe, Spalten wie die Eingabeliste,
`prompt_engineering = yes`). Die Konsole zeigt „Wiederholungen nötig“ = Anzahl unvollständiger Läufe:
so oft wird die Eingabe ausgeführt. Die Ergebnisse mit Präfix `nachlauf_` in den Modellordner legen und
mit Skript 11 zusammenführen; es ergänzt je unvollständigem Lauf nur die fehlenden/ungültigen Zeilen.

```powershell
python find_incomplete_runs.py --root <Ordner mit *_10_runs> --reference <vollständige Datei> `
  --input-dataset <classification_experiment_dataset_v2.xlsx> --pro-modell
```
