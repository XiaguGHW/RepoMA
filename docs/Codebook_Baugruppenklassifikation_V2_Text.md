Codebook
Klassifikationsworkshop Handhabungstechnik · Annotationsleitfaden für die Einzelarbeit

# 1 Vorgehen je Baugruppe

Jede Baugruppe wird genau einer Klasse zugeordnet, anhand ihrer dominierenden Hauptfunktion, in absoluter Einzelarbeit. Die Reihenfolge der Schritte ist einzuhalten.

1. Bewegungsablauf verstehen. Was bewegt sich wohin, in welcher Reihenfolge, relativ wozu?
2. Hauptfunktion bestimmen. Wofür existiert die Baugruppe im Prozess?
3. Aktoren zählen nach Abschnitt 3 → zwei Zahlen: R = rotatorischer Aktor, T = translatorischer Aktor
4. Klasse bestimmen über den Entscheidungsablauf in Abschnitt 4.
5. Gegenprüfen an der Klassendefinition (Abschnitt 5) und an den Grenzfällen (Abschnitt 6).
6. Fünf Felder in Excel eintragen nach Abschnitt 2.

**Mindest-Informationsstand.** Benennung und Abbildung allein sind nicht ausreichend. Vor der Entscheidung ist mindestens eine Quelle aus Teamcenter/DFC heranzuziehen (3D-Ansicht, Zeichnung oder Stückliste), außer der Bewegungsablauf ist aus der Abbildung zweifelsfrei erkennbar.

**Zeitbudget.** ca. 1–2 Minuten pro Baugruppe.

**Achtung:** Die Benennung gibt häufig einen Hinweis, ersetzt aber unter keinen Umständen die Prüfung der Klassenkriterien. Es gibt Baugruppen, bei denen Benennung und tatsächliche Klasse nicht zusammenpassen.

# 2 Was einzutragen ist

Pro Baugruppe werden fünf Felder erfasst. Die Felder 1 und 2 sind immer auszufüllen, die Felder 3 bis 5 nur unter der genannten Bedingung.

| Feld | Werte | Auszufüllen |
|---|---|---|
| 1 Baugruppenklasse | Klasse 1 – 7 | immer |
| 2 Konfidenz | sicher · eher sicher · eher unsicher · unsicher | immer |
| 3 Zweitwahl | Klasse 1 – 7 | wenn die Zuordnung mehrdeutig ist und eine zweite Klasse ernsthaft in Frage kommt |
| 4 Ausschlaggebende Quelle | z. B. Teamcenter 3D-Ansicht, Zeichnung, Stückliste, DFC | wenn die Entscheidung nicht allein aus der Excel-Liste getroffen wurde |
| 5 Notiz | Freitext, ein bis zwei Sätze | wenn Konfidenz = eher unsicher / unsicher, oder Klasse 7 gewählt, oder Feld 3 ausgefüllt ist |

**Zweitwahl.** Kein Ersatz für eine Entscheidung. In Feld 1 steht immer die Klasse, die als beste vertretbare gilt; Feld 3 hält nur fest, welche Klasse ebenfalls plausibel gewesen wäre.

**Notiz.** Bei Klasse 7 sind zwei Dinge anzugeben: (a) die tatsächliche Hauptfunktion der Baugruppe und (b) warum keine der Klassen 1 – 6 greift. In den übrigen Fällen genügt der Grund für Unsicherheit oder Mehrdeutigkeit.

# 3 Zählregeln für Aktoren

Ergebnis dieses Schritts sind zwei Zahlen: R = Anzahl rotatorischer Aktoren, T = Anzahl translatorischer Aktoren.

## Mitzählen

**Achtung:** Nur Aktoren, die die Hauptfunktion „Bewegungsablauf ermöglichen“ realisieren. Ein Aktor zählt nur dann separat, wenn er eine eigene, unabhängige Bewegungsrichtung ermöglicht.

## Nicht mitzählen

- Hilfsfunktionen: Auswerfer, Fixierungen, Spanner, Klemmungen, Verriegelungen, Abdeckungen
- Endeffektoren: Aktoren innerhalb von Greifer, Sauger, Werkzeuge, Sensorik
- Aktoren innerhalb eines Greifers, die die Greifbewegung erzeugen
- Manuelle Einstell- und Justageachsen, die im Prozess nicht bewegt werden

Als ein Aktor zählen. Mehrere Aktoren mit derselben Bewegungsrichtung (z. B. zwei parallele Zylinder für einen Hub → T = 1) sowie mechanisch zwangsgekoppelte Bewegungen aus einem Antrieb.

# 4 Entscheidungsablauf

Voraussetzung: R und T sind nach Abschnitt 3 bestimmt. Sobald eine Klasse erreicht ist, endet der Durchlauf.

## Tabelle S1: Ist die Hauptfunktion eine Bewegungs- oder Greiffunktion im Sinne der Handhabungstechnik?

|  |  |
|---|---|
| JA | → weiter mit S2 (Tabelle) |
| NEIN | → KLASSE 7 Keine der verfügbaren Klassen |

## Tabelle S2: Klasse in der Tabelle ablesen – R = Anzahl rotatorischer Aktoren, T = Anzahl translatorischer Aktoren.

|  | T = 0 | T = 1 | T ≥ 2 |
|---|---|---|---|
| R = 0 | → Fall A | → KLASSE 1 Lineareinheit | → Fall B |
| R = 1 | → KLASSE 6 Rotationseinheit | → KLASSE 4 Umsetzeinheit | → KLASSE 4 Umsetzeinheit |
| R ≥ 2 | → KLASSE 5 Roboter | → KLASSE 4 Umsetzeinheit | → KLASSE 4 Umsetzeinheit |

## Tabelle S3: Nur bei Fall A oder Fall B: Fallunterscheidung durchführen.

### FALL A: R = 0 und T = 0 – Liegt eine Greiffunktion vor (Greifbacken, Greiffinger, Vakuum)?

|  |  |
|---|---|
| JA | → KLASSE 3 Greifer |
| NEIN (z. B. Gestell, Aufnahme, passive Zuführschiene) | → KLASSE 7 Keine der verfügbaren Klassen |

### FALL B: R = 0 und T ≥ 2 – Gantry-Test: alle drei Kriterien müssen erfüllt sein

(a) Die Linearachsen stehen orthogonal zueinander und spannen einen kartesischen Arbeitsraum auf.

(b) Mindestens zwei Achsen sind horizontal (X und Y), es entsteht ein flächiger horizontaler Arbeitsraum. Eine dritte, vertikale Achse (Z) ist zulässig, nicht erforderlich.

(c) Die erste horizontale Achse (X) ist beidseitig geführt: Anfangs- und Endpunkt der Y-Achse werden entlang X geführt (Portal- bzw. Brückenstruktur).

alle drei JA → KLASSE 2 Gantry

mindestens eines NEIN → KLASSE 4 Umsetzeinheit

# 5 Klassendefinitionen

Die Tabelle in Abschnitt 4 entscheidet. Die Definitionen dienen der Gegenprüfung und beschreiben, was die Klasse jeweils physisch ausmacht.

## Klasse 1: Lineareinheit

R = 0 & T = 1

**Hauptfunktion.** Lineares Transportieren, Verfahren oder Positionieren eines Bauteils, Werkzeugs oder einer weiteren Baugruppe entlang genau einer Richtung.

- Lineare Führung oder Schlitten
- Antrieb häufig Pneumatikzylinder, Spindel- oder Zahnriemenantrieb

## Klasse 2: Gantry

R = 0 & T ≥ 2 & Gantry-Test bestanden

**Hauptfunktion.** Positionieren, Transportieren oder Handhaben von Bauteilen, Werkzeugen oder Greifern in einem frei adressierbaren, kartesischen Arbeitsraum.

- X/Y- oder X/Y/Z-Bewegung; die erste Horizontalachse ist beidseitig geführt (Portal- bzw. Brückenstruktur)
- Tendenziell großer Bauraum, Abstützung häufig über mehrere Standfüße, sofern die Abstützung Bestandteil der Baugruppe ist

## Klasse 3: Greifer

R = 0 & T = 0 & mit Greiffunktion

**Hauptfunktion.** Werkstücke greifen, halten, klemmen, fixieren, aufnehmen oder ablegen mit direktem Werkstückkontakt.

- System mit Greifbacken, Greiffingern oder Vakuum
- Aktoren, die die Greifbewegung erzeugen, dürfen enthalten sein und zählen nicht
- Mehrere Greifer in einer Baugruppe sind möglich (Doppel-/Mehrfachgreifer)

**Verwechslungsgefahr.** Wird der Greifer als Ganzes im Arbeitsraum bewegt, ist er Endeffektor. Dann entscheiden R und T über die Klasse (siehe Grenzfall 6.1).

## Klasse 4: Umsetzeinheit/Kombinierte Einheit

T ≥ 1 & R + T ≥ 2 & kein Gantry

**Hauptfunktion.** Werkstücke innerhalb eines Prozesses aufnehmen, umsetzen, wenden, ausrichten, übergeben oder positionieren.

- **Aufgabenbindung:** fester, auf eine konkrete Handhabungsaufgabe zugeschnittener Bewegungsablauf statt eines frei adressierbaren Arbeitsraums
- **Heterogene Kinematik:** Translation kombiniert mit Rotation, oder mehrere Translationen
- **Integrierter Endeffektor:** Greifer, Sensor oder Werkzeug ist häufig Bestandteil
- **Bauform:** kompakt, eigengefertigt oder modular aus Katalogkomponenten zusammengesetzt (z. B. Hubachse + Schwenkeinheit + Greifer)

## Klasse 5: Roboter

R ≥ 2 & T = 0

**Hauptfunktion.** Flexible Handhabung, Positionierung oder Bearbeitung durch frei programmierbare Bewegungen über mindestens zwei rotatorische Gelenke.

- Ausschließlich rotatorische Aktoren
- Industrieroboter oder Roboterarm, meist von einem Lieferanten zugekauft
- Kontaktstellen an den Drehgelenken gut abgedichtet

**Verwechslungsgefahr.** Kommt eine translatorische Prozessachse hinzu (z. B. Verfahrachse), ist es Klasse 4 (siehe Grenzfall 6.5).

## Klasse 6: Rotationseinheit

R = 1 & T = 0

**Hauptfunktion.** Drehen, Schwenken, Wenden oder Ausrichten eines Bauteils, Werkzeugs oder Werkstückträgers um genau eine Drehachse.

- Antrieb häufig pneumatisch oder elektrisch
- Rundtische sind ebenfalls Rotationseinheiten, auch mit mehreren Aufnahmen oder Greifern auf dem Tisch

## Klasse 7: Keine der verfügbaren Klassen

**Notiz verpflichtend**

**Zweck.** Erfasst Baugruppen außerhalb des Schemas und macht dadurch die Abdeckung des Schemas messbar.

**Zu verwenden, wenn**

- die Hauptfunktion keine Handhabungsfunktion ist (z. B. Fügen, Prüfen, Messen, Zuführen ohne Aktorik, Schutzeinhausung, Gestell, Verkettungselement), oder
- die Baugruppe eine Handhabungsfunktion hat, deren Kinematik von keiner der Klassen 1 – 6 sinnvoll erfasst wird.

**Verwechslungsgefahr.** Klasse 7 ist kein Ausweichfeld für schwierige oder mehrdeutige Fälle. Unsicherheit gehört in Feld 2, Mehrdeutigkeit in Feld 3.

# 6 Grenzfälle

| Fall | Situation | Entscheidung |
|---|---|---|
| 6.1 Greifer auf einer Hubachse | Greifer sitzt auf einem Pneumatikzylinder, beides Teil der Baugruppe. | Hubachse zählt, Greifer nicht. R = 0, T = 1 → Klasse 1 Lineareinheit |
| 6.2 Rundtisch mit sechs Greifern | Ein Drehantrieb bewegt den Tisch, die Greifer öffnen und schließen. | Greifaktoren zählen nicht. R = 1, T = 0 → Klasse 6 Rotationseinheit |
| 6.3 Hub-Schwenk-Einheit mit Greifer | Zylinder für den Hub, Schwenkantrieb für die Drehung, Greifer als Endeffektor. | R = 1, T = 1 → Klasse 4 Umsetzeinheit |
| 6.4 Einseitig geführtes Zweiachs-System | Horizontale Verfahrachse, daran auskragend eine zweite Achse. | Gantry-Kriterium (c) nicht erfüllt → Klasse 4 Umsetzeinheit |
| 6.5 Roboter mit zusätzlicher Linearachse | Zugekaufter Knickarmroboter auf einer Verfahrachse, beides in einer Baugruppe. | Nicht ausschließlich rotatorisch → Klasse 4 Umsetzeinheit |
| 6.6 X/Z-Portal | Zwei orthogonale Linearachsen, aber nur eine davon horizontal. | Gantry-Kriterium (b) nicht erfüllt → Klasse 4 Umsetzeinheit |
| 6.7 Zwei parallele Zylinder für denselben Hub | Zwei Antriebe, eine Bewegungsrichtung. | Gleiche Richtung, T = 1 statt 2 → Klasse 1 Lineareinheit |
| 6.8 Baugruppe ohne jede Aktorik oder Greiffunktion | Aufnahme, Gestell, Schutzeinhausung, passive Schiene. | Keine Greif-, keine Bewegungsfunktion → Klasse 7 |

# 7 Kurzreferenz

1. Bewegungsablauf verstehen! Benennung nur als Indikator verwenden.
2. Aktoren zählen: Hilfsfunktionen, Endeffektoren und Greifbewegungen zählen nicht; gleiche Richtung = ein Aktor.
3. R und T in der Tabelle nachschlagen; bei Fall A oder B die Fallunterscheidung durchführen.
4. Klasse und Konfidenz eintragen; Zweitwahl, Quelle und Notiz nach Abschnitt 2 ergänzen.
