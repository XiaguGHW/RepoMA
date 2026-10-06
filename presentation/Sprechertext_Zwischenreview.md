# Sprechertext – Zwischenreview (Folien 1–11)

**Zeitbudget für diesen Abschnitt: ca. 5:00 Minuten**  
Die gesamte Präsentation bleibt damit bei etwa 15 Minuten. Die Zeitplanung ist eine kurze Einordnung; der inhaltliche Rahmen beginnt auf Folie 3.

## Folie 1 – Titel (ca. 0:15 | kumuliert: ca. 0:15)

Ich möchte Ihnen heute den aktuellen Stand meiner Masterarbeit vorstellen.  
Der Titel lautet: *Machine-Learning-Experimente zur Datenaufbereitung von Baugruppendaten für die Verbesserung der Wiederverwendung in der mechanischen Entwicklung.*

## Folie 2 – Zeitplan der Masterarbeit (ca. 0:20 | kumuliert: ca. 0:35)

Zuerst möchte ich Ihnen kurz den Zeitplan meiner Masterarbeit zeigen. Der bisherige Schwerpunkt liegt auf der LLM-gestützten Funktionsklassifikation. Die Metadatenextraktion ist der zweite Teil der Arbeit und folgt im weiteren Verlauf.

Für die Funktionsklassifikation wurden zunächst die Baugruppendaten aufbereitet und vier Labeling-Workshops durchgeführt. Diese Vorbereitung und die anschließenden LLM-Experimente stelle ich im Folgenden vor.

## Folie 3 – Untersuchungslogik der LLM-gestützten Funktionsklassifikation (ca. 0:50 | kumuliert: ca. 1:25)

Das Ziel der Untersuchung ist zu prüfen, wie leistungsfähig eine automatisierte Funktionsklassifikation mit LLMs ist.

Dafür folgt die Untersuchung fünf aufeinander aufbauenden Schritten.

Erstens wurden ein einheitlicher Testdatensatz und ein Codebook erstellt. Das Codebook definiert die Klassen und die Regeln für die Zuordnung.

Zweitens wurden vier Labeling-Workshops durchgeführt. Dabei wurden menschliche Klassifikationen und der Zeitaufwand erfasst.

Drittens wurden die Workshop-Ergebnisse ausgewertet und geprüft. Dadurch konnten die Ground Truths überprüft und die Baugruppen drei Regimen zugeordnet werden.

Auf dieser Grundlage folgen viertens die LLM-Experimente. Dabei werden Modelle, Eingabeformate und Prompt-Konfigurationen verglichen.

Am Ende werden die Ergebnisse bewertet und die Leistungsfähigkeit der LLMs eingeordnet.

Ich gehe diese fünf Schritte jetzt nacheinander durch. Zuerst zeige ich die gemeinsame Testbasis.

## Folie 4 – Testdatensatz & Codebook (ca. 1:05 | kumuliert: ca. 2:30)

Diese Testbasis wurde sowohl für die vier Labeling-Workshops als auch für die späteren LLM-Experimente verwendet. Dadurch beziehen sich menschliche und automatisierte Klassifikation auf dieselben Baugruppen und dieselben Regeln.

Der Datensatz umfasst 129 Baugruppen aus der Handhabungstechnik bei BMG. Die 129 Baugruppen verteilen sich auf sieben Funktionsklassen. Die Klassen und ihre jeweiligen Anzahlen sind links dargestellt.

Die sieben Klassen beschreiben jeweils die Hauptfunktion einer Baugruppe. Ein Greifer wird zum Beispiel der Klasse „Greifer“ zugeordnet, weil seine Hauptfunktion das Greifen und Halten von Bauteilen ist.

Je nach Baugruppe standen unterschiedliche Informationsquellen zur Verfügung, zum Beispiel DFC- und CAD-Screenshots, Zeichnungen, Stücklisten und Datenblätter.

Die verfügbaren Informationen wurden für jede Baugruppe manuell gesammelt und in einer einheitlichen Ordnerstruktur abgelegt.

Das Codebook bildet die einheitliche Grundlage: Es enthält die sieben Klassendefinitionen und eine feste Entscheidungslogik. Damit wird nachvollziehbar festgelegt, wie eine Baugruppe klassifiziert werden soll.

Auf dieser Testbasis wurden anschließend vier Labeling-Workshops durchgeführt.

## Folie 5 – Labeling-Workshop: Durchführung (ca. 1:15 | kumuliert: ca. 3:45)

Das Ziel der vier Workshops war erstens, das Klassenschema in der Anwendung zu überprüfen. Zweitens sollten menschliche Klassifikationen und der dafür benötigte Zeitaufwand erfasst werden.

Insgesamt haben 16 Personen teilgenommen: davon vier Ingenieurinnen und Ingenieure sowie zwölf Studierende.

Zu Beginn haben alle Teilnehmenden das Codebook für ungefähr zehn Minuten gelesen. So hatten alle dieselbe Grundlage für die Klassifikation.

Danach klassifizierte jede Person die Baugruppen eigenständig in einer Excel-Vorlage. Pflichtangaben waren die gewählte Klasse und die Konfidenz. Die Konfidenz beschreibt, wie sicher die Teilnehmenden bei ihrer Entscheidung waren. Eine Zweitwahl sowie die für die Entscheidung verwendete Quelle konnten zusätzlich angegeben werden.

Als Informationsquellen standen allen Teilnehmenden DFC und Teamcenter zur Verfügung. Alle dort verfügbaren Informationen konnten zur Klassifikation genutzt werden.

Über Zeitstempel wurde außerdem die Bearbeitungszeit automatisch erfasst, um später den Zeitaufwand berechnen zu können.

## Folie 6 – Auswertung der Workshops (ca. 1:15 | kumuliert: ca. 5:00)

Nach den vier Workshops haben Jonas und ich die Annotationsergebnisse ausgewertet und geprüft. Dabei wurden auch die ursprünglichen Ground Truths anhand des Codebooks überprüft.

Danach wurden die Baugruppen in drei Regime eingeteilt. E1 bezeichnet eindeutige Fälle mit einer einheitlichen Zuordnung. Bei E2 gibt es einzelne abweichende Meinungen, aber die Ground Truth bleibt nach der Prüfung Codebook-konform.

Bei M, also mehrdeutigen Fällen, gab es ebenfalls abweichende Einzelmeinungen. Nach der Prüfung waren mehrere Labels nach dem Codebook zulässig. Das bedeutet, dass die ursprüngliche Ground Truth eines der vertretbaren Labels ist.

Aus den Workshop-Ergebnissen konnte außerdem ein wichtiger Kennwert berechnet werden: Krippendorffs Alpha. Es ist ein Maß für die Übereinstimmung zwischen mehreren Personen. Je näher der Wert bei 1 liegt, desto stärker stimmen ihre Klassifikationen überein.

Für die eindeutigen Fälle, also E1 und E2, beträgt Alpha 0,806. Damit liegt die Übereinstimmung über dem von Krippendorff vorgeschlagenen Richtwert von 0,800 für zuverlässige Schlussfolgerungen.

Über alle Fälle einschließlich der mehrdeutigen Fälle beträgt der Wert 0,751. Der Wert zeigt, dass die Zuordnungen auch über alle Baugruppen hinweg weitgehend übereinstimmen. Durch die mehrdeutigen Baugruppen ist die Übereinstimmung aber etwas geringer.

Auch der Zeitaufwand wurde ausgewertet: Ingenieurinnen und Ingenieure benötigten im Mittel 0,5 Minuten pro Baugruppe, Studierende 0,85 Minuten. Die Ingenieurinnen und Ingenieure waren damit im Mittel deutlich schneller. Das könnte mit ihrer größeren Erfahrung und Vertrautheit mit den Baugruppen zusammenhängen.

Damit ist die Auswertung der vier Workshops abgeschlossen.

## Folie 7 – LLM-Experimente: Untersuchungsrahmen (ca. 0:45 | kumuliert: ca. 5:45)

Im nächsten Teil stelle ich die LLM-Experimente vor. Ziel ist es zu untersuchen, welchen Einfluss unterschiedliche Randbedingungen auf die Klassifikationsleistung von LLMs haben.

Damit die Ergebnisse vergleichbar bleiben, bleiben zwei Punkte konstant: Alle Experimente verwenden denselben Testdatensatz wie in den vier Workshops. Außerdem ist die Ausgabe-Konfiguration immer gleich: Das Modell gibt pro Baugruppe genau eine Funktionsklasse aus.

Verglichen werden drei Randbedingungen. Erstens der Umfang der Codebook-Informationen im Prompt. Zweitens unterschiedliche LLM-Modelle. Drittens unterschiedliche Eingabeformate: PDF, Bild und Text.

Für die Bewertung verwende ich hauptsächlich drei Metriken. Die Strict Accuracy zählt eine Vorhersage nur dann als korrekt, wenn sie genau der manuell überprüften Ground Truth entspricht.

Im Mittelpunkt steht die Allowed-Label-Set Accuracy. Sie berücksichtigt zusätzlich die in den Workshops und anhand des Codebooks bestätigten zulässigen Alternativen. Das ist besonders wichtig für die mehrdeutigen Baugruppen. In den folgenden Ergebnisfolien wird diese Metrik deshalb kurz als Accuracy bezeichnet.

Ergänzend verwende ich den Macro-F1-Score. Er bewertet alle Klassen gleich stark und verhindert damit, dass häufigere Klassen das Ergebnis dominieren.

In den folgenden Folien zeige ich diese Vergleiche und die jeweiligen Ergebnisse.

## Folie 8 – Prompt-Konfigurationen im Vergleich (ca. 0:55 | kumuliert: ca. 6:40)

Zuerst betrachte ich den Einfluss der Prompt-Konfiguration. Die Frage ist: Welcher Prompt führt zur besten Klassifikationsleistung?

Die vier Prompt-Varianten bauen schrittweise aufeinander auf. P1 enthält nur die Klassennamen. P2 ergänzt die Klassendefinitionen aus dem Codebook. P3 ergänzt zusätzlich die Entscheidungslogik aus dem Codebook. P4 enthält darüber hinaus Beispiele und Ausnahmen.

Die Balken zeigen die Allowed-Label-Set Accuracy für vier Modelle. Über alle Modelle hinweg liefert P3 die beste und zugleich konsistenteste Leistung: Bei Claude Opus, Gemini Flash und Gemini Pro ist P3 jeweils die beste Variante. Nur bei Claude Haiku liegt P4 geringfügig vor P3.

Die zentrale Erkenntnis ist daher: Die Entscheidungslogik aus dem Codebook ist besonders hilfreich. Zusätzliche Beispiele und Ausnahmen in P4 verbessern das Ergebnis dagegen nicht durchgängig.

Für die folgenden Vergleiche wird deshalb P3 als feste Prompt-Konfiguration verwendet.

## Folie 9 – Eingabeformate im Vergleich (ca. 0:45 | kumuliert: ca. 7:25)

Als Nächstes vergleiche ich die Eingabeformate bei gleicher Prompt-Konfiguration P3. Die Frage ist: Welches Datenformat führt zur besten Klassifikationsleistung?

Bei PDF erhalten die Modelle die verfügbaren PDF-Dateien einer Baugruppe, zum Beispiel Zeichnungen, Stücklisten und Datenblätter. Beim Bildformat werden CAD- und DFC-Screenshots sowie in Bilder umgewandelte PDF-Seiten verwendet. Beim Textformat werden die aus PDF- und Bilddateien extrahierten Rohtexte verwendet.

Das Ergebnis ist klar: Das reine Bildformat liegt bei allen vier Modellen unter PDF und Text. Welche der beiden anderen Varianten besser ist, hängt vom Modell ab. Insgesamt zeigen PDF und Text die besseren Ergebnisse; bei Gemini Pro erreichen beide Formate 91,3 Prozent.

## Folie 10 – Ergebnisstabilität im Vergleich (ca. 0:45 | kumuliert: ca. 8:10)

Zum Schluss prüfe ich die Ergebnisstabilität bei wiederholter Durchführung. Dafür wurden Gemini 2.5 Pro und Claude Haiku 4.5 jeweils zehnmal unter denselben Bedingungen mit der Prompt-Konfiguration P3 ausgeführt. Bewertet wird die Allowed-Label-Set Accuracy.

Gemini 2.5 Pro erreicht mit 90,66 Prozent den höheren mittleren Accuracy-Wert. Die Standardabweichung beträgt jedoch 2,05 Prozentpunkte. Die Ergebnisse schwanken damit sichtbar zwischen 86,8 und 93,7 Prozent.

Bei Claude Haiku 4.5 liegt der Mittelwert mit 89,35 Prozent nur 1,31 Prozentpunkte darunter. Die Standardabweichung beträgt aber lediglich 0,47 Prozentpunkte. Die zehn Durchläufe liegen deshalb sehr nah beieinander, zwischen 88,9 und 89,8 Prozent.

Im direkten Stabilitätsvergleich liefert Claude Haiku 4.5 damit deutlich konstantere Ergebnisse, während Gemini 2.5 Pro den höheren durchschnittlichen Wert erreicht.

## Folie 11 – Fazit & Ausblick (ca. 1:00 | kumuliert: ca. 9:10)

Aus Gründen der Übersichtlichkeit zeige ich in dieser Präsentation nur eine Auswahl der getesteten Modelle und jeweils einen zentralen Bewertungsindikator. Die Gesamtauswertung umfasst weitere Modelle und Metriken; die dargestellten Ergebnisse zeigen jedoch bereits die wesentlichen Tendenzen und stützen die genannten Schlussfolgerungen.

Aus den Experimenten lässt sich folgende Aussage ableiten: Unter klar definierten Randbedingungen erreichen LLMs eine hohe Klassifikationsleistung bei der Funktionsklassifikation von Baugruppen.

Für die Prompt-Gestaltung zeigt sich: Die Entscheidungslogik aus dem Codebook ist besonders wichtig. Mit der Konfiguration P3 wurden über die Modelle hinweg die besten und zugleich konsistentesten Ergebnisse erreicht. Zusätzliche Beispiele und Ausnahmen haben die Leistung dagegen nicht durchgängig verbessert.

Beim Vergleich der Eingabeformate sind PDF und Text insgesamt besser geeignet als reine Bilder. Das beste Format hängt jedoch auch vom eingesetzten Modell ab.

Bei den untersuchten Modellen erreicht Claude Opus 4.8 die höchsten Werte in den Prompt- und Formatvergleichen. Claude Haiku 4.5 liefert dagegen die stabilsten Ergebnisse bei wiederholter Durchführung und ist zugleich ein kostengünstiger Kompromiss.

Im weiteren Verlauf erweitere ich den Datensatz um 70 Baugruppen auf insgesamt 199 Baugruppen. Danach überprüfe ich die Ergebnisse erneut auf dieser größeren Testbasis.

Der zweite Schwerpunkt der Arbeit ist die LLM-gestützte Metadatenextraktion. Abschließend werden beide Arbeitspakete gemeinsam ausgewertet und in der Masterarbeit verschriftlicht.

Damit bin ich am Ende meiner Präsentation. Vielen Dank.

## Kurze Übungsregel

Bis einschließlich Folie 10 beträgt die geplante Sprechzeit etwa 8:10 Minuten. Mit Folie 11 liegt sie bei etwa 9:10 Minuten. Die Folien nicht vorlesen: nur die obenstehenden Sätze sprechen und bei den sieben Klassen kurz über die Karten zeigen.
