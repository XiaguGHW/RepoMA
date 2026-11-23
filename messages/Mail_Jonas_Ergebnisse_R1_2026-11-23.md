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
- Die Accuracy wird je Lauf berechnet und anschließend über die 10 Läufe gemittelt. Du hattest gefragt, ob wir den Mittelwert verwenden sollen – ich habe das so umgesetzt. Passt das für dich?
- Bootstrap: 2000 Wiederholungen, Ziehen der Baugruppen mit Zurücklegen (jeweils mit allen Läufen); bei 185 BG werden die 115 und 70 BG getrennt gezogen.
- Makro-Mittelung: Precision über die vorhergesagten Klassen, Recall über die in der GT vorkommenden Klassen, F1 über beide zusammen.
- Die 14 Baugruppen aus dem Prompt Engineering sind ausgeschlossen.
- P1–P4 und der Vergleich pdf/Bild/text beruhen jeweils auf einem Einzellauf. Für Claude Opus gibt es keine Wiederholungsläufe, dort sind auch eindeutig/mehrdeutig/gesamt Einzelläufe (gelb markiert). Für GPT-5.5 und DeepSeek fehlen P1, P2 und P4 noch.

Nachläufe:
Ich habe alle Ergebnisdateien mit einem Skript auf fehlende Vorhersagen geprüft und die fehlenden Baugruppen nachlaufen lassen und ergänzt. Damit sind alle Läufe vollständig.

Ablage:
Den gesamten Code dieser Auswertung sowie alle Ergebnisdateien, nach Experimenten geordnet, habe ich in folgendem OneDrive-Ordner abgelegt: [Link]
Struktur: 00_Skripte (Code), 01_Prompt_P1-P4, 02_Input_P3, 03_Wiederholung_10runs (Rohergebnisse), 05_Ergebnisse (ausgewertete Tabellen und Diagramme).

Abweichung zum Zwischenbericht:
Die Werte sind mit dem Zwischenbericht nicht direkt vergleichbar. Gründe:
1. Prompt: Der Zwischenbericht beruht auf P1, die aktuellen Ergebnisse auf P3. Mit P1 unter R1 ergeben sich nahezu dieselben Gesamtwerte (Haiku 80,0 % ggü. 81,5 %, Opus 90,4 % ggü. 90,4 %, Flash 86,1 % ggü. 85,8 %, Pro 84,3 % ggü. 84,2 %).
2. Ground Truth: Damals galt der vorherige GT-Stand, jetzt R1. Dadurch sind einige Baugruppen anders zugeordnet (E1/E2/M) bzw. haben andere zulässige Labels. Die 115 Baugruppen selbst sind gleich geblieben.
3. Teilmengen: Die mehrdeutige Teilmenge nach R1 ist nicht identisch mit der früheren Gruppe M. Bei n = 22 entspricht eine Baugruppe bereits ca. 4,5 Prozentpunkten.
4. Einzellauf vs. Mittelwert über 10 Läufe.

Die Konfusionsmatrizen in deiner Darstellungsform habe ich ebenfalls vorbereitet und schicke sie dir separat, sobald die übrigen Punkte passen.

Viele Grüße
Duanni
