# Expert Review – Organisation und offene Punkte

## Ziel

Das Expert Review prüft, ob die Funktionsklassen und die Zuordnungsregeln im Codebook für unterschiedliche Personen verständlich und nachvollziehbar sind.

Die Teilnehmenden ordnen ausgewählte Baugruppen anhand des Codebooks jeweils einer Funktionsklasse zu. Unklare Fälle oder Anmerkungen können in der Excel-Datei ergänzt werden.

## Organisation

Da ein gemeinsamer Termin für alle Beteiligten schwer zu finden ist, wird das Review asynchron durchgeführt:

1. Die Unterlagen werden über einen gemeinsamen Teams-Chat verteilt.
2. Jede teilnehmende Person bearbeitet die Excel-Datei selbstständig.
3. Die ausgefüllte Datei wird anschließend im Chat zurückgesendet.

**Geplante Frist:** 07.09.

## Unterlagen für die Teilnehmenden

- PDF-Datei mit Codebook und Klassendefinitionen
- Excel-Datei mit den zu klassifizierenden Baugruppen
- kurze Erklärung in der Teams-Nachricht, wie die Excel-Datei auszufüllen ist

## Teilnehmende und Kommunikation

Jonas hat Berk und Peter als mögliche Teilnehmende genannt. Die Abstimmung erfolgt in einem gemeinsamen Teams-Chat.

Erste Nachricht im Gruppenchat:

> Vielleicht können wir uns hier gemeinsam besser abstimmen.
>
> Vielen Dank, dass ihr an meinem Expert Review teilnehmt! Es geht um die funktionale Klassifikation einiger Baugruppen anhand eines Codebooks. Da es schwierig ist, einen gemeinsamen Termin zu finden, würde ich euch die Unterlagen (PDF und Excel-Datei) direkt hier schicken.
>
> Könntet ihr die Excel-Datei bitte bis zum 07.09. ausfüllen und mir anschließend zurückschicken? Bei Fragen könnt ihr natürlich jederzeit hier schreiben.

## Zusätzliches Thema: Prompt Caching mit Berk

Jonas hat außerdem vorgeschlagen, Berk zu Prompt Caching zu befragen. Sein Hinweis:

> Das spart viele Kosten beim Durchlauf der Modelle, insbesondere für Claude Opus ist das wichtig, damit es günstig bleibt. Batch-Durchläufe können ebenfalls hilfreich sein.

### Aktueller technischer Kontext

- Die Klassifikation läuft über einen LLM Connector, über den verschiedene Modelle angesprochen werden können.
- Pro Baugruppe wird ein eigener Klassifikations-Prompt gesendet.
- Das vollständige Codebook bzw. der konstante Prompt-Teil wird dabei für jede Baugruppe erneut mitgesendet.
- Daher soll geklärt werden, ob dieser wiederkehrende Prompt-Teil gecacht werden kann, um Kosten und Laufzeit bei vielen Baugruppen zu reduzieren.
- Zusätzlich soll geprüft werden, ob Batch-Durchläufe vom verwendeten Connector bzw. den verfügbaren Modellen unterstützt werden und sinnvoll sind.

### Nachricht an Berk

> Hi Berk, Jonas hat mich neben dem Workshop auch gebeten, mich bei dir kurz über Prompt Caching zu informieren. Er meinte, dass dadurch bei wiederholten Modelldurchläufen Kosten gespart werden können – besonders bei Claude Opus – und dass eventuell auch Batch-Durchläufe hilfreich sein könnten.
>
> Ich arbeite aktuell mit einem LLM Connector, über den ich verschiedene Modelle ansprechen kann. Für die Klassifikation schicke ich pro Baugruppe einen Prompt, wobei das Codebook jedes Mal erneut mitgegeben wird. Daher wollte ich verstehen, ob und wie man diesen wiederkehrenden Teil cachen könnte.
>
> Hättest du vielleicht irgendwann kurz Zeit, mir zu erklären, wie ihr das bisher gemacht habt bzw. worauf ich dabei achten sollte?

## Offene Fragen für das Gespräch mit Berk

- Unterstützt der verwendete LLM Connector Prompt Caching direkt?
- Welche Modelle unterstützen es in der vorhandenen Bosch-Umgebung?
- Wie muss der Prompt aufgebaut sein, damit das Codebook als konstanter Teil wiederverwendet werden kann?
- Wie werden Cache-Nutzung, Kosten und Laufzeit sichtbar bzw. gemessen?
- Sind Batch-Durchläufe möglich? Falls ja: für welche Modelle, mit welchen Einschränkungen und welchem erwarteten Kostenvorteil?
- Gibt es bereits interne Beispiele oder bestehende Skripte, an denen man sich orientieren kann?
