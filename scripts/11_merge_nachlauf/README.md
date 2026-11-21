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

## Seit 2026-11: nur unvollständige Läufe ergänzen (Standard)

- Gepaart werden nur Originale, in denen eine Baugruppe der Nachlauf-Dateien fehlt oder keine gültige
  Vorhersage hat (EXCLUDED, leer, `[EMPTY]`, nicht zuordenbar, Processing-Fehler); je solchem Lauf eine
  eigene Nachlauf-Datei. Zu wenige Nachlauf-Dateien → Abbruch mit Hinweis, wie oft laufen lassen.
- Gültige Zeilen bleiben unverändert; fehlende Zeilen werden angehängt.
- Nicht betroffene Originale werden unverändert zurückkopiert.
- `--ueberschreiben`: altes Verhalten (alle Originale ↔ alle Nachlauf-Dateien, gleiche Anzahl).

## Ein Nachlauf je Modell genügt meist

Jede Lücke (Lauf × Baugruppe) bekommt ein eigenes Nachlauf-Ergebnis; ein Nachlauf kann Lücken in
verschiedenen Läufen füllen, solange jede Baugruppe nur einmal fehlt. Fehlt eine Baugruppe in k Läufen,
sind k Nachläufe nötig (Skript 16 zeigt das als „Wiederholungen nötig“). Nicht füllbare Lücken meldet das
Skript; nach weiteren Nachläufen einfach erneut ausführen (neuer Sicherungsordner `_backup_vor_merge_2`, …).
`--wiederverwenden` setzt notfalls dasselbe Ergebnis mehrfach ein (verfälscht die Streuung, nicht empfohlen).
