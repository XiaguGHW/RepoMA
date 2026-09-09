# Task 3 – Prompt Development (14 Baugruppen)

Dieses Dokument beschreibt den ersten Entwicklungsschritt für die LLM-Klassifikation. Es betrifft nur die 14 manuell ausgewählten Baugruppen mit `prompt_engineering = yes`.

## Lokale Projektstruktur

    Task3_Prompt_Development/
    ├── .env
    ├── llm_connector.py
    ├── run_prompt_development.py
    ├── input/
    │   └── classification_experiment_dataset.xlsx
    ├── prompts/
    │   ├── P1.txt
    │   ├── P2.txt
    │   └── P3.txt
    └── outputs/

`llm_connector.py` und `.env` stammen aus dem bisherigen Multi-Model-Projekt. Sie werden nicht verändert.

## Ziel des Prompt Development

Ein Modell wird zunächst bei Temperature = 0 mit denselben 14 Baugruppen getestet. P1, P2 und P3 unterscheiden nur die Information im System Prompt:

- P1: nur Klassenbezeichnungen
- P2: Klassenbezeichnungen plus kurze Funktionsbeschreibungen
- P3: vollständiges Codebook einschließlich Entscheidungsregeln und Grenzfälle

Das Ziel ist nicht der endgültige Modellvergleich, sondern ein stabiles JSON-Format und klar verständliche Klassifikationsregeln. Erst danach werden die Prompt-Versionen eingefroren und die formalen Multi-Model-Experimente gestartet.

## P1 – Inhalt von `prompts/P1.txt`

    Du bist ein erfahrener Konstrukteur im Sondermaschinenbau und Experte für Handhabungstechnik, Baugruppenfunktionen sowie technische Zeichnungen.

    Klassifiziere die bereitgestellte Baugruppe anhand der beigefügten Kontextdaten, z. B. CAD-Screenshots, Zeichnungen, Stücklisten und Datenblätter.

    Beurteile die tatsächliche dominante Hauptfunktion und den Bewegungsablauf der Baugruppe. Verwende die Benennung nur als Hinweis, nicht als alleinige Entscheidungsgrundlage.

    Ordne jede Baugruppe genau einer primären Funktionsklasse zu. Verwende ausschließlich exakt eine der folgenden Klassenbezeichnungen:

    - Lineareinheit
    - Gantry
    - Greifer
    - Umsetzeinheit
    - Roboter
    - Rotationseinheit
    - Keine der verfügbaren Klassen

    Antworte ausschließlich mit einem gültigen JSON-Objekt, ohne Markdown, ohne einleitenden oder abschließenden Text:

    {
      "class_label": "exakte Klassenbezeichnung",
      "reasoning": "kurze fachliche Begründung auf Deutsch",
      "confidence_percent": 0,
      "possible_classes_if_ambiguous": []
    }

    Regeln für die Felder:
    - class_label: genau eine der sieben Klassenbezeichnungen.
    - reasoning: maximal 2–3 kurze Sätze.
    - confidence_percent: ganze Zahl von 0 bis 100.
    - possible_classes_if_ambiguous: leere Liste, wenn keine ernsthafte Alternative besteht; sonst Liste weiterer möglicher Klassenbezeichnungen. class_label darf nicht erneut in dieser Liste stehen.

## Testlauf

Zuerst nur einen BG testen:

    python .\run_prompt_development.py --prompt-config P1 --model gemini-2.5-pro --max-rows 1

Der Lauf liest standardmäßig `input/classification_experiment_dataset.xlsx`, filtert `prompt_engineering = yes` und verwendet die dortige Spalte `Data_Folder_Path`. Das Ergebnis wird als neue Excel-Datei in `outputs/` gespeichert.

Nach erfolgreicher Kontrolle des JSON-Formats und der verwendeten Dateien werden alle 14 Entwicklungs-BGs ausgeführt:

    python .\run_prompt_development.py --prompt-config P1 --model gemini-2.5-pro

## Ergebnisdatei

Die Ergebnisdatei enthält unter anderem:

- die ursprünglichen Ground-Truth- und Register-Spalten,
- `Predicted_Label`,
- `Reasoning`,
- `Confidence_Percent`,
- `Possible_Classes_If_Ambiguous`,
- `Raw_Model_Response` und `JSON_Parse_Status`,
- Modell, Prompt-Konfiguration, Temperatur sowie die verwendeten Dateien.

## Wichtige Label-Konsistenz

Codebook V2 verwendet `Gantry` und `Umsetzeinheit`. Die bestehende Ground Truth enthält teilweise noch die älteren Namen `Multi-Achs-System (Gantry)` und `Kombinierte Einheit`. Vor der automatischen formalen Auswertung muss diese Bezeichnung per Mapping vereinheitlicht werden.