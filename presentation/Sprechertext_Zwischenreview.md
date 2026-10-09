# Sprechertext – Zwischenreview (Folien 1–13)

**Zeitbudget für diesen Abschnitt: ca. 5:00 Minuten**  
Die gesamte Präsentation bleibt damit bei etwa 15 Minuten. Die Zeitplanung ist eine kurze Einordnung; der inhaltliche Rahmen beginnt auf Folie 3.

## Folie 1 – Titel (ca. 0:15 | kumuliert: ca. 0:15)

Ich möchte Ihnen heute den aktuellen Stand meiner Masterarbeit vorstellen.  
Der Titel lautet: *Machine-Learning-Experimente zur Datenaufbereitung von Baugruppendaten für die Verbesserung der Wiederverwendung in der mechanischen Entwicklung.*

## Folie 2 – Zeitplan der Masterarbeit (ca. 0:20 | kumuliert: ca. 0:35)

Zunächst gebe ich einen kurzen Überblick über den Zeitplan meiner Masterarbeit. Der erste Schwerpunkt ist die LLM-gestützte Funktionsklassifikation; die Metadatenextraktion folgt im weiteren Verlauf.

Für diesen ersten Teil wurden die Baugruppendaten aufbereitet und vier Labeling-Workshops durchgeführt. Diese Grundlage und die anschließenden LLM-Experimente stelle ich jetzt vor.

## Folie 3 – Untersuchungslogik der LLM-gestützten Funktionsklassifikation (ca. 1:00 | kumuliert: ca. 1:35)

Das Ziel der Untersuchung ist zu prüfen, wie leistungsfähig eine automatisierte Funktionsklassifikation mit LLMs ist.

Die Untersuchung folgt fünf aufeinander aufbauenden Schritten. So wird die Grundlage geschaffen, um die LLM-Leistung nachvollziehbar zu messen.

Zunächst erstellen wir einen einheitlichen Testdatensatz und ein Codebook. Damit sind sowohl die Baugruppen als auch die Regeln für ihre Zuordnung für Menschen und LLMs eindeutig festgelegt.

Darauf aufbauend führen wir vier Labeling-Workshops durch, um das Klassenschema in der Anwendung zu überprüfen sowie menschliche Klassifikationsergebnisse und den dafür benötigten Zeitaufwand zu erfassen.

Anschließend werden diese Ergebnisse anhand des Codebooks geprüft. Dadurch wird festgelegt, welche Fälle eindeutig sind und bei welchen mehrere Labels zulässig sind. Diese Regeln bilden später die Grundlage für die LLM-Bewertung.

Erst dann testen wir verschiedene LLM-Modelle, Eingabeformate und Prompt-Konfigurationen unter vergleichbaren Bedingungen.

Zum Schluss werden die LLM-Vorhersagen mit den geprüften Ground Truths und zulässigen Alternativen verglichen. So lässt sich die Leistungsfähigkeit der Modelle auch bei mehrdeutigen Fällen nachvollziehbar einordnen.

Ich gehe diese fünf Schritte jetzt nacheinander durch. Zuerst zeige ich die gemeinsame Testbasis.

## Folie 4 – Testdatensatz & Codebook (ca. 1:05 | kumuliert: ca. 2:30)

Diese Testbasis wurde sowohl für die vier Labeling-Workshops als auch für die späteren LLM-Experimente verwendet. Dadurch beziehen sich menschliche und automatisierte Klassifikation auf dieselben Baugruppen und dieselben Regeln.

Der Datensatz umfasst 129 Baugruppen aus der Handhabungstechnik bei BMG. Die 129 Baugruppen verteilen sich auf sieben Funktionsklassen. Die Klassen und ihre jeweiligen Anzahlen sind links dargestellt.

Die sieben Klassen beschreiben jeweils die Hauptfunktion einer Baugruppe. Ein Greifer wird zum Beispiel der Klasse „Greifer“ zugeordnet, weil seine Hauptfunktion das Greifen und Halten von Bauteilen ist.

Je nach Baugruppe standen unterschiedliche Informationsquellen zur Verfügung, zum Beispiel DFC- und CAD-Screenshots, Zeichnungen, Stücklisten und Datenblätter.

Die verfügbaren Informationen wurden für jede Baugruppe manuell gesammelt und in einer einheitlichen Ordnerstruktur abgelegt.

Um eine einheitliche und nachvollziehbare Klassifikation durch Menschen und LLMs zu ermöglichen, wurde ein Codebook erstellt. Es enthält die sieben Klassendefinitionen und eine feste Entscheidungslogik. Sowohl die Teilnehmenden im Workshop als auch die LLMs klassifizieren nach diesem Regelwerk.

Auf dieser Testbasis wurden anschließend vier Labeling-Workshops durchgeführt.

## Folie 5 – Labeling-Workshop: Durchführung (ca. 1:15 | kumuliert: ca. 3:45)

Das Ziel der vier Workshops war erstens, das Klassenschema in der Anwendung zu überprüfen. Zweitens sollten menschliche Klassifikationen und der dafür benötigte Zeitaufwand erfasst werden.

Insgesamt haben 16 Personen teilgenommen: davon vier Ingenieurinnen und Ingenieure sowie zwölf Studierende.

Zu Beginn haben alle Teilnehmenden das Codebook für ungefähr zehn Minuten gelesen. So hatten alle dieselbe Grundlage für die Klassifikation.

Danach klassifizierte jede Person die Baugruppen eigenständig in einer Excel-Vorlage. Pflichtangaben waren die gewählte Klasse und die Konfidenz. Die Konfidenz beschreibt, wie sicher die Teilnehmenden bei ihrer Entscheidung waren. Eine Zweitwahl sowie die für die Entscheidung verwendete Quelle konnten zusätzlich angegeben werden.

Als Informationsquellen standen allen Teilnehmenden DFC und Teamcenter zur Verfügung. Alle dort verfügbaren Informationen konnten zur Klassifikation genutzt werden.

Über Zeitstempel wurde außerdem die Bearbeitungszeit automatisch erfasst, um später den Zeitaufwand berechnen zu können.

## Folie 6 – Herleitung der Regime E1, E2 und M (ca. 0:50 | kumuliert: ca. 4:35)

Bei der Auswertung zeigte sich, dass einige Baugruppen mehrdeutig sein können. Deshalb wurden die Fälle in E1, E2 und M eingeteilt. So können wir die Ergebnisse der anschließenden LLM-Experimente für eindeutige und mehrdeutige Baugruppen getrennt betrachten.

Im ersten Beispiel ordnen alle drei Teilnehmenden die Baugruppe als „Roboter“ ein. Es besteht Konsens, und die Ground Truth „Roboter“ wird nach der Prüfung bestätigt. Das ist E1: ein eindeutiger Fall mit einheitlicher Zuordnung.

Im zweiten Beispiel wählen zwei Teilnehmende keine der verfügbaren Klassen. Teilnehmer C ordnet die Baugruppe als „Greifer“ ein; sie wurde möglicherweise aufgrund ihrer Form so wahrgenommen. Die Ground Truth bleibt nach der Prüfung Codebook-konform. Das ist E2: eindeutig, aber mit einer abweichenden Einzelmeinung.

Im dritten Beispiel gibt es unterschiedliche Zuordnungen. Die Ground Truth lautet „Lineareinheit“, aber nach der Prüfung ist auch „Rotationseinheit“ zulässig, weil die Baugruppe zusätzlich einen Rotationsaktor enthält. Das ist M: ein mehrdeutiger Fall. Die Ground Truth ist dabei nicht falsch, sondern eine der zulässigen Antworten.

## Folie 7 – Auswertung der Workshops (ca. 0:55 | kumuliert: ca. 5:30)

Nach den vier Workshops haben Jonas und ich die Annotationsergebnisse ausgewertet und geprüft. Dabei wurden auch die ursprünglichen Ground Truths anhand des Codebooks überprüft.

Danach wurden die Baugruppen in die drei gerade erläuterten Regime eingeteilt.

Bei M, also mehrdeutigen Fällen, gab es ebenfalls abweichende Einzelmeinungen. Nach der Prüfung waren mehrere Labels nach dem Codebook zulässig. Das bedeutet, dass die ursprüngliche Ground Truth eines der vertretbaren Labels ist.

Aus den Workshop-Ergebnissen konnte außerdem ein wichtiger Kennwert berechnet werden: Krippendorffs Alpha. Es ist ein Maß für die Übereinstimmung zwischen mehreren Personen. Je näher der Wert bei 1 liegt, desto stärker stimmen ihre Klassifikationen überein.

Für die eindeutigen Fälle, also E1 und E2, beträgt Alpha 0,806. Damit liegt die Übereinstimmung über dem von Krippendorff vorgeschlagenen Richtwert von 0,800 für zuverlässige Schlussfolgerungen.

Für die mehrdeutigen Fälle ist Krippendorffs Alpha dagegen nicht aussagekräftig. Dort können mehrere Labels nach dem Codebook korrekt sein. Unterschiedliche Zuordnungen bedeuten deshalb nicht automatisch, dass die Teilnehmenden oder das Codebook uneinheitlich sind.

Auch der Zeitaufwand wurde ausgewertet: Ingenieurinnen und Ingenieure benötigten im Mittel 29 Sekunden pro Baugruppe, Studierende 51 Sekunden. Die Ingenieurinnen und Ingenieure waren damit im Mittel deutlich schneller. Das könnte mit ihrer größeren Erfahrung und Vertrautheit mit den Baugruppen zusammenhängen.

Damit ist die Auswertung der vier Workshops abgeschlossen.

## Folie 8 – LLM-Experimente: Untersuchungsrahmen (ca. 0:45 | kumuliert: ca. 6:15)

Im nächsten Teil stelle ich die LLM-Experimente vor. Ziel ist es zu untersuchen, welchen Einfluss unterschiedliche Randbedingungen auf die Klassifikationsleistung von LLMs haben.

Damit die Ergebnisse vergleichbar bleiben, bleiben zwei Punkte konstant: Alle Experimente verwenden denselben Testdatensatz wie in den vier Workshops. Außerdem ist die Ausgabe-Konfiguration immer gleich: Das Modell gibt pro Baugruppe genau eine Funktionsklasse aus.

Verglichen werden drei Randbedingungen. Erstens der Umfang der Codebook-Informationen im Prompt. Zweitens unterschiedliche LLM-Modelle. Drittens unterschiedliche Eingabeformate: PDF, Bild und Text.

Als Bewertungsmetrik verwende ich die Allowed-Label-Set Accuracy, im Folgenden kurz Accuracy. Eine Vorhersage gilt dabei als korrekt, wenn sie der Ground Truth oder einer anhand des Codebooks zulässigen Alternative entspricht. Das ist besonders wichtig für die mehrdeutigen Fälle.

Im Folgenden zeige ich zunächst die Stabilität der Ergebnisse bei wiederholter Durchführung.

## Folie 9 – Ergebnisstabilität im Vergleich (ca. 0:55 | kumuliert: ca. 7:10)

Bevor ich die Prompt- und Formatvergleiche zeige, prüfe ich zunächst die Ergebnisstabilität bei wiederholter Durchführung. Dadurch lässt sich später besser einordnen, ob Unterschiede zwischen Bedingungen tatsächlich belastbar sind oder innerhalb der natürlichen Modellschwankung liegen.

Dafür wurden Gemini 2.5 Pro und Claude Haiku 4.5 jeweils zehnmal unter denselben Bedingungen mit PDF und dem vollständigen Codebook im Prompt ausgeführt. Bewertet wird die Allowed-Label-Set Accuracy.

Gemini 2.5 Pro erreicht mit 90,66 Prozent den höheren mittleren Accuracy-Wert. Die Standardabweichung beträgt jedoch 2,05 Prozentpunkte. Die Ergebnisse schwanken damit sichtbar zwischen 86,8 und 93,7 Prozent.

Bei Claude Haiku 4.5 liegt der Mittelwert mit 89,35 Prozent nur 1,31 Prozentpunkte darunter. Die Standardabweichung beträgt aber lediglich 0,47 Prozentpunkte. Die zehn Durchläufe liegen deshalb sehr nah beieinander, zwischen 88,9 und 89,8 Prozent.

Claude Haiku 4.5 liefert damit deutlich konstantere Ergebnisse. Diese Schwankungsbreiten berücksichtige ich nun bei der Interpretation der weiteren Vergleiche.

## Folie 10 – Prompt-Konfigurationen im Vergleich (ca. 0:55 | kumuliert: ca. 8:05)

Zuerst betrachte ich den Einfluss der Prompt-Konfiguration. Die Frage ist: Welcher Prompt führt zur besten Klassifikationsleistung?

Die vier Prompt-Varianten bauen schrittweise aufeinander auf. P1 enthält nur die Klassennamen. P2 ergänzt die Klassendefinitionen aus dem Codebook. P3 ergänzt zusätzlich die Entscheidungslogik aus dem Codebook. P3 erweitert enthält darüber hinaus Beispiele und Ausnahmen.

Die Balken zeigen die Accuracy für vier Modelle. Bei Claude Haiku steigt die Leistung mit zunehmendem Informationsumfang deutlich an. Da die Schwankung dieses Modells gering ist, lässt sich dieser Effekt plausibel auf die Prompt-Konfiguration zurückführen.

Bei Gemini 2.5 Pro ist der Unterschied von P2 zu P3 größer als die zuvor gezeigte Schwankung. Kleinere Unterschiede zwischen den übrigen Prompt-Varianten können dagegen auch durch die natürliche Modellschwankung entstanden sein.

Insgesamt zeigt der Vergleich, dass die Entscheidungslogik im Codebook eine wichtige Information für die Klassifikation ist. Für die folgenden Vergleiche verwende ich deshalb P3 als feste Prompt-Konfiguration.

## Folie 11 – Eingabeformate im Vergleich (ca. 0:45 | kumuliert: ca. 8:50)

Als Nächstes vergleiche ich die Eingabeformate bei gleicher Prompt-Konfiguration P3. Die Frage ist: Welches Datenformat führt zur besten Klassifikationsleistung?

Bei PDF erhalten die Modelle die verfügbaren PDF-Dateien einer Baugruppe, zum Beispiel Zeichnungen, Stücklisten und Datenblätter. Beim Bildformat werden CAD- und DFC-Screenshots sowie in Bilder umgewandelte PDF-Seiten verwendet. Beim Textformat werden die aus PDF- und Bilddateien extrahierten Rohtexte verwendet.

Das reine Bildformat liegt bei allen vier Modellen unter PDF und Text. Welche der beiden anderen Varianten besser ist, hängt vom Modell ab. Daher lässt sich kein genereller Vorteil von PDF gegenüber Text ableiten. Beide Formate sind insgesamt vergleichbar.

## Folie 12 – LLM-Ergebnisse nach Regime (ca. 0:45 | kumuliert: ca. 9:35)

Zum Schluss betrachte ich die Ergebnisse getrennt nach den Regimen E1, E2 und M. Die Bedingungen sind für alle Modelle gleich: PDF als Eingabe und P3, also das vollständige Codebook, als Prompt.

Jedes Modell wird hier mit vier Balken dargestellt: E1, E2, M und Gesamt. Der Gesamtwert entspricht dem zuvor verwendeten Gesamtergebnis.

Die Aufteilung zeigt, ob sich die Leistung zwischen eindeutigen und mehrdeutigen Baugruppen unterscheidet. Dadurch bleibt die im Workshop festgestellte Mehrdeutigkeit auch in der LLM-Bewertung sichtbar und geht nicht im Gesamtwert verloren.

Für M wird dabei die Allowed-Label-Set Accuracy verwendet. Eine Vorhersage wird also als korrekt gewertet, wenn sie einer der nach dem Codebook zulässigen Klassen entspricht.

## Folie 13 – Fazit & Ausblick (ca. 1:00 | kumuliert: ca. 10:35)

Aus Gründen der Übersichtlichkeit zeige ich in dieser Präsentation nur eine Auswahl der getesteten Modelle und jeweils einen zentralen Bewertungsindikator. Die Gesamtauswertung umfasst weitere Modelle und Metriken; die dargestellten Ergebnisse zeigen jedoch bereits die wesentlichen Tendenzen und stützen die genannten Schlussfolgerungen.

Aus den Experimenten lässt sich folgende Aussage ableiten: Unter klar definierten Randbedingungen erreichen LLMs eine hohe Klassifikationsleistung bei der Funktionsklassifikation von Baugruppen.

Für die Prompt-Gestaltung zeigt sich: Die Entscheidungslogik aus dem Codebook ist besonders wichtig. Bei Claude Haiku ist der Einfluss zusätzlicher Codebook-Informationen klar erkennbar. Bei Gemini 2.5 Pro müssen kleinere Unterschiede wegen der größeren Modellschwankung vorsichtig interpretiert werden.

Beim Vergleich der Eingabeformate sind PDF und Text insgesamt besser geeignet als reine Bilder. Das beste Format hängt jedoch auch vom eingesetzten Modell ab.

Bei den untersuchten Modellen erreicht Claude Opus 4.8 die höchsten Werte in den Prompt- und Formatvergleichen. Claude Haiku 4.5 liefert dagegen die stabilsten Ergebnisse bei wiederholter Durchführung und ist zugleich ein kostengünstiger Kompromiss.

Im weiteren Verlauf erweitere ich den Datensatz um 70 Baugruppen auf insgesamt 199 Baugruppen. Danach überprüfe ich die Ergebnisse erneut auf dieser größeren Testbasis.

Der zweite Schwerpunkt der Arbeit ist die LLM-gestützte Metadatenextraktion. Abschließend werden beide Arbeitspakete gemeinsam ausgewertet und in der Masterarbeit verschriftlicht.

Damit bin ich am Ende meiner Präsentation. Vielen Dank.

## Kurze Übungsregel

Bis einschließlich Folie 12 beträgt die geplante Sprechzeit etwa 9:35 Minuten. Mit Folie 13 liegt sie bei etwa 10:35 Minuten. Die Folien nicht vorlesen: nur die obenstehenden Sätze sprechen und bei den sieben Klassen kurz über die Karten zeigen.
