# 11 — Nachlauf zusammenführen

`merge_nachlauf.py` ersetzt in den ursprünglichen Lauf-Dateien die Zeilen der erneut ausgeführten
Baugruppen (zuvor EXCLUDED) durch die Ergebnisse der Nachlauf-Dateien. Danach liegen wieder
10 vollständige Lauf-Dateien vor. Keine Modellaufrufe.

## Voraussetzungen

- Im Modellordner liegen die 10 Originaldateien und 10 Nachlauf-Dateien mit Präfix `nachlauf_`.
- Zuordnung: beide Gruppen werden nach Zeitstempel im Dateinamen sortiert und der Reihe nach gepaart.

## Aufruf

```
python merge_nachlauf.py --dry-run <Ordner>   # nur prüfen
python merge_nachlauf.py <Ordner>             # zusammenführen
python merge_nachlauf.py                      # alle Unterordner des Skriptordners mit Nachlauf-Dateien
```

## Verhalten

- Gemeinsame Spalten (Ground Truth, Register, Weitere zulässige Ground Truth, Predicted_Label,
  Reasoning, …) werden aus der Nachlauf-Datei übernommen; die korrigierte GT gilt also auch hier.
- `Allowed_Set_Status` wird neu berechnet (Synonyme laut Codebook). Ein manuell eingetragener Status
  wird geprüft; bei Abweichung gilt der berechnete Wert und es erscheint ein Hinweis.
- Formatierung (z. B. Farbe der Status-Zelle) und weitere Tabellenblätter der Originale bleiben erhalten.
  Die übrigen Blätter (Prompt_Evaluation, Confusion_Matrix, …) werden nicht neu berechnet.
- Originale und Nachlauf-Dateien werden nach `_backup_vor_merge/` verschoben,
  `merge_protokoll.xlsx` dort listet jede ersetzte Zeile und alle Hinweise.
