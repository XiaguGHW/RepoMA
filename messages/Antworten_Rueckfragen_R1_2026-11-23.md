# Antworten zu Jonas' Rückfragen (R1, 2026-11-23)

## Antworten zu den Rückfragen

(Antworten in Blau)

### 1. Metriken / Bootstrap bei Mehrfachdurchläufen

Ja, so ist es jetzt umgesetzt: Alle Metriken werden je Lauf berechnet und anschließend über die 10 Läufe gemittelt (Mittelwert und Standardabweichung über die Läufe).

Bootstrap: 2000 Wiederholungen. In jeder Wiederholung werden die Baugruppen mit Zurücklegen gezogen, jeweils mit allen 10 Läufen der gezogenen Baugruppe; daraus wird die mittlere Accuracy berechnet. Das 95%-Intervall ergibt sich aus dem 2,5- und 97,5-Perzentil. Bei 185 BG wird getrennt innerhalb der 115 und der 70 BG gezogen, damit das Verhältnis der beiden Datensätze gleich bleibt.

Dass es in den bisherigen Ergebnissen nicht stimmig war, lag daran, dass z. B. die Werte für E1/E2/M auf einem Einzellauf beruhten, während andere Werte aus den Wiederholungsläufen stammten. Jetzt gilt einheitlich: Wiederholungsläufe (115 und 185 BG) = Mittelwert über 10 Läufe; Prompt-Vergleich (P1–P4) und Input-Vergleich (pdf/Bild/text) = Einzellauf, da diese nur einmal durchgeführt wurden.

### 2. Mehrdeutige Baugruppen bei R1 und R2

Ausgewertet werden 185 Baugruppen (199 abzüglich der 14 aus der Label-Konfiguration). Baugruppen mit Register M, aber ohne weitere zulässige Labels (bei R1: 0804GE7738, 0804EN7325), werden als eindeutig gezählt.

| Datensatz | R1 eindeutig | R1 mehrdeutig | R2 eindeutig | R2 mehrdeutig |
|---|---|---|---|---|
| 115 BG | 93 | 22 | 85 | 30 |
| 185 BG | 162 | 23 | 154 | 31 |

Der Unterschied liegt vollständig in den 115 BG; bei den 70 BG ist jeweils nur eine Baugruppe mehrdeutig.

a) Verteilung der eindeutigen Labels

| Klasse | R1 115 | R1 185 | R2 115 | R2 185 |
|---|---|---|---|---|
| Lineareinheit | 18 | 27 | 14 | 23 |
| Rotationseinheit | 10 | 20 | 10 | 20 |
| Greifer | 12 | 22 | 12 | 22 |
| Multi-Achs-System (Gantry) | 14 | 19 | 11 | 16 |
| Roboter | 13 | 23 | 13 | 23 |
| Kombinierte Einheit | 19 | 24 | 18 | 23 |
| Keine der verfügbaren Klassen | 7 | 27 | 7 | 27 |
| Summe | 93 | 162 | 85 | 154 |

b) Kombinationen der mehrdeutigen Labels (zulässige Labelmenge)

| Zulässige Labelmenge | R1 115 | R1 185 | R2 115 | R2 185 |
|---|---|---|---|---|
| Roboter + Kombinierte Einheit | 5 | 5 | 5 | 5 |
| Lineareinheit + Kombinierte Einheit | 1 | 2 | 4 | 5 |
| Rotationseinheit + Kombinierte Einheit | 1 | 1 | 4 | 4 |
| Multi-Achs-System (Gantry) + Kombinierte Einheit | 3 | 3 | 3 | 3 |
| Rotationseinheit + Greifer | 3 | 3 | 3 | 3 |
| Lineareinheit + Greifer | 2 | 2 | 2 | 2 |
| Rotationseinheit + Keine der verfügbaren Klassen | 2 | 2 | 2 | 2 |
| Multi-Achs-System (Gantry) + Kombinierte Einheit + Keine der verfügbaren Klassen | 0 | 0 | 2 | 2 |
| Greifer + Keine der verfügbaren Klassen | 1 | 1 | 1 | 1 |
| Greifer + Kombinierte Einheit | 1 | 1 | 1 | 1 |
| Lineareinheit + Multi-Achs-System (Gantry) + Kombinierte Einheit | 1 | 1 | 1 | 1 |
| Lineareinheit + Keine der verfügbaren Klassen | 0 | 0 | 1 | 1 |
| Multi-Achs-System (Gantry) + Keine der verfügbaren Klassen | 0 | 0 | 1 | 1 |
| Lineareinheit + Rotationseinheit | 2 | 2 | 0 | 0 |
| Summe | 22 | 23 | 30 | 31 |

### 3. Allowed-Label-Set Metriken: Literatur oder selbst definiert?

Die Allowed-Label-Set Accuracy ist in der Literatur belegt (unter anderem Namen). Die Allowed-Varianten von Precision, Recall und F1 waren dagegen eine eigene Festlegung, die eine Konvention für das Hauptlabel braucht. Die Makro-Mittelung auf den eindeutigen Baugruppen folgt den Standardformeln (Precision über die vorhergesagten Klassen, Recall über die in der Referenz vorkommenden Klassen, F1 über beide).

### 4. Aussagekraft von Precision, Recall und F1

Ich stimme dir zu und habe es so umgesetzt: Auf allen Baugruppen sowie getrennt für eindeutige und mehrdeutige Baugruppen wird nur die Allowed-Label-Set Accuracy (mit Bootstrap) berichtet. Precision, Recall und F1 (Makro) werden nur auf den eindeutigen Baugruppen berichtet, vorerst ohne Bootstrap. Auf den eindeutigen Baugruppen gibt es genau eine Referenzklasse, daher sind dort die Standarddefinitionen anwendbar, und die Allowed-Label-Set Accuracy entspricht dort der normalen Accuracy.

### Update: E1/E2

Umgesetzt: E1 und E2 werden nicht mehr getrennt, sondern gemeinsam als „eindeutig“ ausgewertet.
