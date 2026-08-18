# RepoMA

Arbeitsrepository für die Masterarbeit zur Aufbereitung und Klassifikation von Baugruppendaten.

## Ordner

- `messages/`: alle E-Mails, Teams-Nachrichten und Einladungen
- `workshop/`: Klassendefinition und Workshop-Auswertung
- `scripts/`: aktuelle Hilfsskripte
- `experiments/`: verschiedene Klassifikationstests
- `notes/`: ergänzende Erklärungen und Code-Notizen
- `presentations/`: Präsentationen
- `old/`: ältere, nicht mehr aktive Skripte

Das aktuelle Hauptprogramm `run_classification.py` liegt direkt im Hauptordner.

## Start

1. Abhängigkeiten installieren:

   ```bash
   pip install -r requirements.txt
   ```

2. `.env.example` nach `.env` kopieren und Zugangsdaten sowie `HBG_DATA_ROOT` eintragen.
3. Die Excel-Eingabedateien lokal unter `input/` ablegen.
4. Die intern bereitgestellte `llm_connector.py` neben `run_classification.py` ablegen.
5. Testlauf starten:

   ```bash
   python run_classification.py --max-rows 10
   ```

`input/`, `output/`, `outputs/` und `.env` werden nicht auf GitHub hochgeladen.
