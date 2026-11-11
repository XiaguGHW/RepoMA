# 14 – Reasoning der falschen Läufe sammeln (Fehleranalyse 5.7)

`collect_error_reasoning.py` liest alle Ergebnisdateien der vier finalen Konfigurationen
(115 BG × 10 Läufe, 70 BG × 1 Lauf), bewertet jede Vorhersage gegen die finale GT
(zulässige Labelmenge) und schreibt die Reasoning-Texte der falschen Läufe in eine Datei.

Benötigt `evaluate_validation_regimes.py` (Skript 12) im selben Ordner.

```powershell
conda activate thesis
cd C:\...\Downloads\test_claude
python collect_error_reasoning.py --main . --supp ..\70BG_Ergebnisse
# alle fehlerhaften Baugruppen statt der Prüfliste (17 BG):
python collect_error_reasoning.py --main . --supp ..\70BG_Ergebnisse --alle --out Fehler_Reasoning_alle.xlsx
```

Ausgabe:

| Datei / Blatt | Inhalt |
|---|---|
| `Fehler_Reasoning.xlsx` → `Zu_pruefen` | je Baugruppe × Konfiguration ein Beispiel-Lauf (häufigste falsche Vorhersage, kleinste Laufnummer) mit Reasoning; Spalten `Kategorie` und `Notiz` zum Ausfüllen |
| `Fehler_Reasoning.xlsx` → `Alle_Fehllaeufe` | jeder falsche Lauf mit Reasoning |
| `Fehler_Reasoning.md` | Inhalt von `Zu_pruefen` als Text |

Die Prüfliste (`ZU_PRUEFEN`) entspricht `thesis/error_cause_mapping.md`, Abschnitt
„最终配置中的出错装配体“.
