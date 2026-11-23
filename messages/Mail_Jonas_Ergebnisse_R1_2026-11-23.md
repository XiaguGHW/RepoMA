# Mail an Jonas – Ergebnisse unter R1 (2026-11-23)

**Betreff:** Ergebnisse unter R1 – Wiederholungsläufe und Ergebnistabelle

**Anhänge:** Wiederhollaeufe_R1.xlsx, Ergebnisse_unter_R1.xlsx, Diagramme_Wiederholung_R1.xlsx, R1.md, Antworten_Rueckfragen_R1 (Word, Antworten auf deine Rückfragen)

---

Hallo Jonas,

anbei wie besprochen die Ergebnisse unter R1:

1. Wiederhollaeufe_R1.xlsx – Wiederholungsläufe (115 BG und 185 BG, je 10 Läufe): Allowed-Label-Set Accuracy mit Mittelwert, Standardabweichung und 95%-Bootstrap-Intervall, getrennt nach gesamt / eindeutig / mehrdeutig; Precision, Recall und F1 nur auf den eindeutigen Baugruppen.
2. Ergebnisse_unter_R1.xlsx – die Tabelle „Ergebnisse unter R1“ (6 Modelle × P1–P4 / pdf, Bild, text / eindeutig, mehrdeutig, gesamt).
3. Diagramme_Wiederholung_R1.xlsx – Mittelwert und Streuung der Accuracy über die 10 Läufe je Modell.
4. R1.md – die verwendete Ground Truth (R1) als Tabelle.

Deine Rückfragen habe ich direkt in deinem Word-Dokument beantwortet (ebenfalls im Anhang).

Kurz zum Vorgehen:
- Die Allowed-Label-Set Accuracy (gesamt, eindeutig, mehrdeutig) sowie Precision, Recall und F1 (eindeutig) werden je Lauf berechnet und anschließend über die 10 Läufe gemittelt. Du hattest gefragt, ob wir den Mittelwert verwenden sollen – ich habe das so umgesetzt. Passt das für dich?
- Bootstrap: 2000 Wiederholungen, Ziehen der Baugruppen mit Zurücklegen (jeweils mit allen Läufen); bei 185 BG werden die 115 und 70 BG getrennt gezogen.
- Precision, Recall und F1 (Makro) wie von dir vorgeschlagen nur auf den eindeutigen Baugruppen, vorerst ohne Bootstrap. Makro-Mittelung: Precision über die vorhergesagten Klassen, Recall über die in der GT vorkommenden Klassen, F1 über beide zusammen.
- Die 14 Baugruppen aus der Label-Konfiguration sind ausgeschlossen.

Nachläufe:
Ich habe alle Ergebnisdateien mit einem Skript auf fehlende Vorhersagen geprüft und die fehlenden Baugruppen nachlaufen lassen und ergänzt. Damit sind alle Läufe vollständig.

Ablage:
Den gesamten Code dieser Auswertung sowie alle Ergebnisdateien, nach Experimenten geordnet, habe ich in folgendem OneDrive-Ordner abgelegt: [Link]
Struktur: 00_Skripte (Code), 01_Prompt_P1-P4, 02_Input_P3, 03_Wiederholung_10runs (Rohergebnisse), 05_Ergebnisse (ausgewertete Tabellen und Diagramme).

Die Konfusionsmatrizen in deiner Darstellungsform habe ich ebenfalls vorbereitet und schicke sie dir separat, sobald die übrigen Punkte passen.

Viele Grüße
Duanni

---

Hinweis in Ergebnisse_unter_R1.xlsx (Zelle mit Erläuterung):
> Die Werte für eindeutig/mehrdeutig/gesamt sind Mittelwerte über 10 Läufe (P3). Sie weichen teils deutlich vom Zwischenbericht ab, insbesondere bei Haiku. Die Berechnung habe ich geprüft. Die damalige Regime-Auswertung beruhte vermutlich noch nicht auf R1, sondern auf einem früheren GT-Stand. Dadurch waren die Werte für mehrdeutig dort niedriger.

