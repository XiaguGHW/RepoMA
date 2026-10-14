# Sprechertext – Zwischenreview (Folien 1–13)

**Zeitbudget für diesen Abschnitt: ca. 5:00 Minuten**  
Die gesamte Präsentation bleibt damit bei etwa 15 Minuten. Die Zeitplanung ist eine kurze Einordnung; der inhaltliche Rahmen beginnt auf Folie 3.

## Folie 1 – Titel (ca. 0:15 | kumuliert: ca. 0:15)

Ich möchte euch heute den aktuellen Stand meiner Masterarbeit vorstellen.  
Der Titel lautet: *Machine-Learning-Experimente zur Datenaufbereitung von Baugruppendaten für die Verbesserung der Wiederverwendung in der mechanischen Entwicklung.*

## Folie 2 – Zeitplan der Masterarbeit (ca. 0:20 | kumuliert: ca. 0:35)

Zunächst gebe ich einen kurzen Überblick über den Zeitplan meiner Masterarbeit. Der erste Schwerpunkt ist die LLM-gestützte Funktionsklassifikation; die Metadatenextraktion folgt im weiteren Verlauf.

Für diesen ersten Teil wurden die Baugruppendaten aufbereitet und vier Labeling-Workshops durchgeführt. Diese Grundlage und die anschließenden LLM-Experimente stelle ich jetzt vor.

## Folie 3 – Untersuchungslogik der LLM-gestützten Funktionsklassifikation (ca. 1:00 | kumuliert: ca. 1:35)

Das Ziel der Untersuchung ist zu prüfen, wie leistungsfähig eine automatisierte Funktionsklassifikation mit LLMs ist.

Die Untersuchung folgt fünf aufeinander aufbauenden Schritten.

Um die Klassifikationsergebnisse von Menschen und LLMs für dieselben Baugruppen unter denselben Regeln vergleichen zu können, benötigen wir eine einheitliche Grundlage. Deshalb erstellen wir zunächst einen Testdatensatz und ein Codebook.

Dann führen wir vier Labeling-Workshops durch, um die Trennschärfe des Klassenschemas zu überprüfen und menschliche Klassifikationsergebnisse sowie den dafür benötigten Zeitaufwand zu erfassen.

Anschließend werden diese Ergebnisse anhand des Codebooks geprüft. Dadurch wird festgelegt, welche Baugruppen eindeutig und welche mehrdeutig sind. Diese validierte Datenbasis bildet später die Grundlage für die LLM-Bewertung.

Erst dann testen wir verschiedene LLM-Modelle, die Eingabeformate PDF, Bild und Text sowie unterschiedliche Prompt-Konfigurationen unter vergleichbaren Bedingungen.

Zum Schluss werden die LLM-Vorhersagen mit den geprüften Ground Truths und zulässigen Alternativen verglichen. Daraus berechnen wir für jedes Modell und jede Konfiguration die jeweilige Accuracy und bewerten damit die Leistungsfähigkeit.

Ich gehe diese fünf Schritte jetzt nacheinander durch.

## Folie 4 – Testdatensatz & Codebook (ca. 1:05 | kumuliert: ca. 2:30)

Zuerst zeige ich die gemeinsame Testbasis.

Sie besteht aus einem Testdatensatz und einem Codebook.

Der Datensatz umfasst 129 Baugruppen aus der Handhabungstechnik bei BMG.

Je nach Baugruppe standen unterschiedliche Informationsquellen zur Verfügung, zum Beispiel DFC- und CAD-Screenshots, Zeichnungen, Stücklisten und Datenblätter. Die verfügbaren Informationen wurden für jede Baugruppe manuell gesammelt und in einer einheitlichen Ordnerstruktur abgelegt.

Die 129 Baugruppen verteilen sich auf sieben Funktionsklassen. Die Klassen und ihre jeweiligen Anzahlen sind links dargestellt.

Die sieben Klassen beschreiben jeweils die Hauptfunktion einer Baugruppe. Eine Greifeinheit wird zum Beispiel der Klasse „Greifer“ zugeordnet, weil ihre Hauptfunktion das Greifen und Halten von Bauteilen ist.

Um eine einheitliche und nachvollziehbare Klassifikation durch Menschen und LLMs zu ermöglichen, wurde ein Codebook als gemeinsames Regelwerk erstellt. Es enthält die Definitionen der sieben Klassen und zeigt Schritt für Schritt, wie man anhand der Aktoren einer Baugruppe und weiterer Kriterien zur passenden Klasse kommt.

Auf dieser Testbasis wurden anschließend vier Labeling-Workshops durchgeführt.

## Folie 5 – Labeling-Workshop: Durchführung (ca. 1:15 | kumuliert: ca. 3:45)

Das Ziel der vier Workshops war erstens, die Trennschärfe des Klassenschemas in der Anwendung zu überprüfen. Zweitens sollten menschliche Klassifikationen und der dafür benötigte Zeitaufwand erfasst werden.

Insgesamt haben wir 16 Teilnehmer: vier Ingenieurinnen und Ingenieure sowie zwölf Studierende.

Der Workshop läuft so ab: Zunächst haben die Teilnehmenden etwa zehn Minuten Zeit, das Codebook zu lesen und zu verstehen. So haben alle dieselbe Grundlage für die Klassifikation.

Danach klassifiziert jede Person die Baugruppen eigenständig in einer Excel-Vorlage. Pflichtangaben sind die gewählte Klasse und die Konfidenz, also wie sicher die Teilnehmenden bei ihrer Entscheidung sind. Eine Zweitwahl sowie die für die Entscheidung verwendete Quelle können zusätzlich angegeben werden.

Als Informationsquellen stehen DFC und Teamcenter zur Verfügung. Alle dort verfügbaren Informationen können zur Klassifikation genutzt werden.

Außerdem wird die Bearbeitungszeit über Zeitstempel automatisch in der Excel-Vorlage erfasst, um später den Zeitaufwand berechnen zu können.

## Folie 6 – Herleitung der Regime E1, E2 und M (ca. 0:50 | kumuliert: ca. 4:35)

Jetzt haben wir sowohl die Baugruppen als auch die menschlichen Klassifikationsergebnisse vorliegen. Wenn wir diese Ergebnisse mit der ursprünglichen Ground Truth vergleichen, sehen wir: Nicht für jede Baugruppe gibt es genau eine eindeutige richtige Klasse. Einige Baugruppen können mehrdeutig sein.

Deshalb wurden alle Baugruppen in die drei Regime E1, E2 und M eingeteilt. So können wir die Ergebnisse der anschließenden LLM-Experimente für eindeutige und mehrdeutige Baugruppen getrennt betrachten. Jetzt schauen wir uns an, wie diese drei Regime festgelegt wurden.

Im ersten Beispiel sehen wir einen Industrieroboter. Alle drei Teilnehmenden ordnen die Baugruppe als „Roboter“ ein. Es besteht Konsens, und die Ground Truth „Roboter“ wird nach der Prüfung bestätigt. Das ist E1: ein eindeutiger Fall mit einheitlicher Zuordnung.

Im zweiten Beispiel handelt es sich um ein Befestigungsteil. Bei dieser Baugruppe wählen zwei Teilnehmende keine der verfügbaren Klassen. Teilnehmer C ordnet die Baugruppe als „Greifer“ ein; sie wurde möglicherweise aufgrund ihrer Form so wahrgenommen. Nach der Prüfung bleibt die Ground Truth aber richtig. Das ist E2: eindeutig, aber mit einer abweichenden Einzelmeinung.

Im dritten Beispiel sehen wir eine Hubeinheit. Einige Teilnehmende wählen „Lineareinheit“, einer aber „Kombinierte Einheit“. Die Ground Truth lautet „Lineareinheit“, aber nach der Prüfung ist auch „Kombinierte Einheit“ zulässig, weil die Baugruppe neben einem linearen Aktor zusätzlich einen Rotationsaktor enthält. Nach der Entscheidungslogik im Codebook ist die Zuordnung als „Kombinierte Einheit“ ebenfalls nachvollziehbar. Das ist M: ein mehrdeutiger Fall. Die Ground Truth ist dabei nicht falsch, sondern eine der zulässigen Antworten.

Die hier gezeigte Prüfung und Einteilung gehören zu den ersten beiden Schritten der gesamten Auswertung.

## Folie 7 – Auswertung der Workshops (ca. 0:55 | kumuliert: ca. 5:30)

So haben Jonas und ich die Annotationsergebnisse aus 4 Workshops ausgewertet und die ursprünglichen Ground Truths anhand des Codebooks geprüft. Alle 129 Baugruppen wurden den Regimen E1, E2 und M zugeordnet.

Aus den Workshop-Ergebnissen konnte außerdem ein wichtiger Kennwert berechnet werden: Krippendorffs Alpha. Es ist ein Maß für die Übereinstimmung zwischen mehreren Personen. Je näher der Wert bei 1 liegt, desto stärker stimmen ihre Klassifikationen überein.

Für die eindeutigen Fälle, also E1 und E2, beträgt Alpha 0,806. Der Wert liegt damit über der Grenze von 0,8 und gilt als zuverlässig.

Für die mehrdeutigen Fälle ist Krippendorffs Alpha dagegen nicht aussagekräftig. Dort können mehrere Labels nach dem Codebook zulässig sein.

Auch der Zeitaufwand wurde ausgewertet: Ingenieurinnen und Ingenieure benötigen im Mittel 31 Sekunden pro Baugruppe, Studierende 42 Sekunden. Die Ingenieurinnen und Ingenieure sind damit etwas schneller, was vermutlich mit ihrer größeren Erfahrung und Vertrautheit mit den Baugruppen zusammenhängt.

Jetzt haben wir die menschlichen Klassifikationsergebnisse. Als Nächstes schauen wir uns an, wie die LLMs abschneiden.

## Folie 8 – LLM-Experimente: Untersuchungsrahmen (ca. 0:45 | kumuliert: ca. 6:15)

Das Ziel der gesamten LLM-Experimente ist es, zu untersuchen, welchen Einfluss unterschiedliche Randbedingungen auf die Klassifikationsleistung von LLMs haben.

Damit die Ergebnisse vergleichbar sind, halten wir zwei Punkte konstant: Alle Experimente verwenden denselben Testdatensatz wie in den Workshops. Außerdem ist die Ausgabe-Konfiguration immer gleich: Das Modell darf pro Baugruppe nur eine Funktionsklasse ausgeben.

Verglichen werden drei Randbedingungen. Erstens der Umfang der Codebook-Informationen im Prompt. Zweitens unterschiedliche LLM-Modelle. Drittens unterschiedliche Eingabeformate: PDF, Bild und Text.

Als Bewertungsmetrik verwende ich die Allowed-Label-Set Accuracy, im Folgenden kurz Accuracy. Eine Vorhersage gilt dabei als korrekt, wenn sie der Ground Truth oder einer weiteren geprüften Alternative entspricht.

## Folie 9 – Ergebnisstabilität im Vergleich (ca. 0:55 | kumuliert: ca. 7:10)

Bevor ich die Prompt- und Formatvergleiche zeige, möchte ich zunächst die Ergebnisse der Stabilitätsanalyse vorstellen. Dadurch lässt sich später besser einordnen, ob Unterschiede zwischen Bedingungen tatsächlich belastbar sind oder innerhalb der natürlichen Modellschwankung liegen.

Die Frage ist: Wie stabil ist die Klassifikationsleistung bei wiederholter Durchführung?

Dafür wurden Gemini 2.5 Pro und Claude Haiku 4.5 jeweils zehnmal unter denselben Bedingungen ausgeführt. Als Eingabe verwenden wir PDF und das vollständige Codebook im Prompt. Die PDF-Dateien enthalten den größten Teil der verfügbaren Informationen zu einer Baugruppe, zum Beispiel technische Zeichnungen, Stücklisten und Datenblätter wichtiger Komponenten.

Die obere und die untere Grafik zeigen jeweils die Ergebnisse von Gemini 2.5 Pro und Claude Haiku 4.5. Die rote gestrichelte Linie zeigt jeweils den Mittelwert.

Gemini 2.5 Pro erreicht im Durchschnitt eine Accuracy von 90,66 Prozent. Die Standardabweichung beträgt jedoch circa 2 Prozentpunkte. Die Ergebnisse schwanken damit sichtbar zwischen 87 und knapp 94 Prozent.

Bei Claude Haiku 4.5 liegt der Mittelwert bei 89,35 Prozent und damit nur leicht unter dem von Gemini. Die Standardabweichung beträgt aber lediglich 0,47 Prozentpunkte. Die zehn Durchläufe liegen deshalb sehr nah beieinander, zwischen 89 und knapp 90 Prozent.

Claude Haiku 4.5 liefert damit deutlich konstantere Ergebnisse. Diese Schwankungen werden bei der Interpretation der weiteren Vergleiche berücksichtigt.

**【中文备注：这一页需要相应修改 PPT。】**

## Folie 10 – Prompt-Konfigurationen im Vergleich (ca. 0:55 | kumuliert: ca. 8:05)

Zuerst betrachte ich den Einfluss der Prompt-Konfiguration. Die Frage ist: Welcher Prompt führt zur besten Klassifikationsleistung?

Die vier Prompt-Varianten bauen schrittweise aufeinander auf. P1 enthält nur die Klassennamen. P2 ergänzt die Klassendefinitionen aus dem Codebook. P3 ergänzt zusätzlich die Entscheidungslogik aus dem Codebook. P3 erweitert enthält darüber hinaus Beispiele und Ausnahmen.

Die Balken zeigen die Accuracy für vier Modelle. Bei Claude Haiku steigt die Accuracy mit jeder zusätzlichen Prompt-Information weiter an. Da dieses Modell in der Stabilitätsanalyse nur geringe Schwankungen zeigte, spricht dieser Anstieg dafür, dass ein größerer Informationsumfang die Klassifikationsleistung tatsächlich verbessert. Bei den drei anderen Modellen bleibt P3 jedoch besser.

Bei Gemini 2.5 Pro ist der Unterschied von P2 zu P3 größer als die zuvor gezeigte Schwankung. Kleinere Unterschiede zwischen den übrigen Prompt-Varianten können dagegen auch durch die natürliche Modellschwankung entstanden sein.

Insgesamt zeigt der Vergleich, dass die Entscheidungslogik im Codebook eine wichtige Information für die Klassifikation ist. Für die folgenden Vergleiche verwende ich deshalb P3 als feste Prompt-Konfiguration.

## Folie 11 – LLM-Ergebnisse nach Regime (ca. 0:50 | kumuliert: ca. 8:55)

Jetzt betrachte ich die Ergebnisse getrennt nach den drei bereits erläuterten Regimen. Die Bedingungen sind für alle Modelle gleich: PDF als Eingabe und P3, also das vollständige Codebook, als Prompt. So wird sichtbar, ob sich die Leistung zwischen eindeutigen und mehrdeutigen Baugruppen unterscheidet.

Zunächst sehen wir E1: eindeutige Fälle mit einheitlicher Zuordnung. Hier erreichen die Modelle zwischen 82,4 und 94,6 Prozent.

Als Nächstes folgt E2. Auch diese Fälle sind nach der Prüfung eindeutig, aber es gab eine abweichende Einzelmeinung. Die Werte liegen bei allen vier Modellen unter den E1-Werten.

Bei M sind mehrere Labels zulässig. Auch hier wird eine nach dem Codebook zulässige Alternative als korrekt gewertet. Trotzdem sind die Werte bei allen Modellen am niedrigsten, besonders bei den Gemini-Modellen. Mehrdeutige Baugruppen bleiben damit für die LLMs anspruchsvoller.

Der letzte Balken zeigt jeweils das Gesamtergebnis über alle Baugruppen. Dadurch wird deutlich, dass der Gesamtwert die Unterschiede zwischen den Regimen verdeckt. Genau deshalb betrachten wir die Regime getrennt.

## Folie 12 – Eingabeformate im Vergleich (ca. 0:50 | kumuliert: ca. 9:45)

Als Nächstes vergleiche ich die Eingabeformate bei gleicher Prompt-Konfiguration P3. Die Frage ist: Welches Datenformat führt zur besten Klassifikationsleistung?

Zunächst sehen wir das PDF-Format. Die Modelle erhalten dabei alle verfügbaren PDF-Dateien einer Baugruppe, zum Beispiel Stücklisten, Datenblätter und Zeichnungen. Die Accuracy liegt je nach Modell zwischen 88,0 und 93,9 Prozent.

Beim Bildformat erhalten die Modelle CAD-Screenshots, die DFC-Struktur und in Bilder umgewandelte PDF-Seiten. Die Werte liegen bei allen vier Modellen unter denen des PDF-Formats.

Beim Textformat werden die aus PDF- und Bilddateien extrahierten Rohtexte verwendet. Bei Claude Haiku und Gemini 2.5 Flash liegt Text über PDF; bei Claude Opus und Gemini 2.5 Pro liegt PDF dagegen höher.

Insgesamt ist das reine Bildformat am schwächsten. Zwischen PDF und Text gibt es keinen einheitlichen Gewinner: Welches der beiden Formate besser ist, hängt vom Modell ab.

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
