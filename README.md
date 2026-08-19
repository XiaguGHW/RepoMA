# RepoMA

Arbeitsrepository für die Masterarbeit zur Aufbereitung und Klassifikation von Baugruppendaten.

## Ordner

- `scripts/`: alle Python-Skripte sowie zugehörige Code-Erklärungen und Notizen
- `messages/`: alle E-Mails, Teams-Nachrichten und Einladungen
- `workshop/`: Workshop-Unterlagen
- `presentations/`: Präsentationen

Das aktuelle Hauptprogramm ist `scripts/run_classification.py`.

## Start

1. Abhängigkeiten installieren:

   ```bash
   pip install -r requirements.txt
   ```

2. `.env.example` nach `.env` kopieren und Zugangsdaten sowie `BG_DATA_ROOT` eintragen.
3. Die Excel-Eingabedateien lokal unter `input/` ablegen.
4. Die intern bereitgestellte `llm_connector.py` ebenfalls unter `scripts/` ablegen.
5. Testlauf starten:

   ```bash
   python scripts/run_classification.py --max-rows 10
   ```

`input/`, `output/`, `outputs/` und `.env` werden nicht auf GitHub hochgeladen.
