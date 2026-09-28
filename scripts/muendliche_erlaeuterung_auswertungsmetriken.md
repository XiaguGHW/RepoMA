# Mündliche Erläuterung der Auswertung

## 1. Überarbeitung des Auswertungsskripts

Erstens habe ich das Skript zur Auswertung der Experimentergebnisse noch einmal überarbeitet. Ich habe jetzt eine zusätzliche Validierung eingebaut: Die Kennzahlen werden zunächst mit eigener, expliziter Code-Logik berechnet und anschließend noch einmal mit `scikit-learn`. Nur wenn beide Ergebnisse übereinstimmen, werden sie ausgegeben.

Dabei berücksichtige ich auch die Zuordnung zwischen den ausgegebenen Klassennamen und den Ground-Truth-Labels. So ist sichergestellt, dass jede Klasse korrekt erkannt und in die Berechnung einbezogen wird.

## 2. Einordnung von TP, TN, FP und FN

Zweitens hatte ich Ihren Hinweis zu den sehr vielen True Negatives noch einmal genauer untersucht und dazu Literatur gelesen. TP, TN, FP und FN stammen ursprünglich aus binären Klassifikationsaufgaben, also aus Entscheidungen mit genau zwei möglichen Ergebnissen, zum Beispiel „defekt oder nicht defekt“.

Bei unserem Mehrklassenproblem werden diese Werte für jede Klasse im One-vs-Rest-Verfahren berechnet: Eine Klasse wird jeweils gegen alle anderen Klassen betrachtet. Dadurch entstehen sehr viele True Negatives. Eine klassenweise Accuracy ist deshalb hier wenig aussagekräftig, weil sie trotz einzelner Fehlklassifikationen noch sehr hoch bleiben kann.

## 3. Relevante Kennzahlen

Für unsere Aufgabe ist daher vor allem die strikte Gesamt-Accuracy wichtig: also der Anteil aller Baugruppen, deren vorhergesagte Klasse exakt dem primären Ground Truth entspricht. Zusätzlich berichte ich die Allowed-Set-Accuracy für die mehrdeutigen Fälle.

Als ergänzende Kennzahl verwende ich Macro F1. Der F1-Score basiert auf Precision und Recall und berücksichtigt keine True Negatives. Er wird deshalb nicht durch die hohe Anzahl von TN-Werten beeinflusst. Für Macro F1 wird zunächst für jede Funktionsklasse ein eigener F1-Score berechnet und anschließend werden alle sieben Klassen gleich gewichtet gemittelt.

Macro F1 ist hier besonders sinnvoll, weil alle sieben Funktionsklassen fachlich gleich relevant sind. Dadurch kann eine häufig vorkommende Klasse das Gesamtergebnis nicht dominieren, und mögliche Schwächen bei seltenen Klassen bleiben sichtbar.

Weighted F1 habe ich ebenfalls betrachtet, würde diese Kennzahl aber nicht in den Vordergrund stellen. Sie gewichtet die Klassen nach ihrer Häufigkeit in unserem Testdatensatz. Da die Verteilung der zufällig ausgewählten Baugruppen nicht zwingend die tatsächliche Klassenverteilung im gesamten Unternehmensbestand repräsentiert, ist Macro F1 für den Vergleich der Funktionsklassen aussagekräftiger.
