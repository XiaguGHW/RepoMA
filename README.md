# RepoMA

Arbeitsrepository für die Masterarbeit zur ML-/LLM-gestützten Aufbereitung und Klassifikation von Baugruppendaten.

## Repository-Struktur

| Pfad | Inhalt |
| --- | --- |
| `run_classification.py` | Hauptskript für die Klassifikation mit allen unterstützten Dateien |
| `scripts/` | Wiederverwendbare Hilfsskripte für Datensammlung, Inventar und PDF-Konvertierung |
| `experiments/` | Abgegrenzte Testläufe und Varianten der Gemini-Klassifikation |
| `workshop/` | Workshop-Auswertung, Klassendefinitionen und fachliche Notizen |
| `docs/` | Kommunikationsentwürfe und ergänzende Code-Dokumentation |
| `presentations/` | Präsentationen zum Arbeitsstand |
| `archive/` | Ältere oder nicht mehr aktive Skriptvarianten |

## Schnellstart

1. Virtuelle Umgebung erstellen und aktivieren.
2. Abhängigkeiten installieren:

   ```bash
   pip install -r requirements.txt
   ```

3. `.env.example` nach `.env` kopieren und die lokalen Bosch-Zugangsdaten sowie `HBG_DATA_ROOT` eintragen.
4. Die lokalen Eingabedateien unter `input/` ablegen:

   - `all_HBG_random_no_label.xlsx`
   - `Functional_classes.xlsx`

5. Die intern bereitgestellte `llm_connector.py` neben `run_classification.py` ablegen.
6. Zunächst einen kleinen Testlauf starten:

   ```bash
   python run_classification.py --max-rows 10
   ```

Ohne `--max-rows` werden alle Zeilen verarbeitet. Weitere Optionen zeigt:

```bash
python run_classification.py --help
```

## Hinweise

- `input/`, `output/`, `outputs/` und `.env` bleiben lokal und werden nicht versioniert.
- Zugangsdaten oder firmenspezifische Datensätze dürfen nicht in das Repository hochgeladen werden.
- Die Skripte in `experiments/` bilden konkrete Versuchsstände ab und sind nicht der Hauptworkflow.
- Die Dateien in `archive/` bleiben zur Nachvollziehbarkeit erhalten, werden aber nicht aktiv gepflegt.
