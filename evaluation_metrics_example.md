# Beispiel: Berechnung von Macro- und Weighted-Metriken

| Class | Ground Truth rows | Correct predictions | Accuracy / Recall | Precision | Recall | F1-score |
|---|---:|---:|---:|---:|---:|---:|
| Lineareinheit | 20 | 15 | 75,0 % | nicht bestimmbar | 0,75 | nicht bestimmbar |
| Gantry | 16 | 10 | 62,5 % | nicht bestimmbar | 0,625 | nicht bestimmbar |
| Greifer | 18 | 18 | 100,0 % | nicht bestimmbar | 1,00 | nicht bestimmbar |
| Umsetzeinheit | 20 | 16 | 80,0 % | nicht bestimmbar | 0,80 | nicht bestimmbar |
| Roboter | 18 | 18 | 100,0 % | nicht bestimmbar | 1,00 | nicht bestimmbar |
| Rotationseinheit | 16 | 11 | 68,75 % | nicht bestimmbar | 0,6875 | nicht bestimmbar |
| Keine der verfügbaren Klassen | 7 | 7 | 100,0 % | nicht bestimmbar | 1,00 | nicht bestimmbar |
| **Gesamt** | **115** | **95** | **82,6 %** |  |  |  |

> **Platz für Abbildung:** Hier kann später ein Screenshot der zugehörigen Confusion Matrix eingefügt werden.

Die Tabelle wurde aus dem zweiten Screenshot übernommen. Der Quotient `Correct predictions / Ground Truth rows` ist der **Recall** der jeweiligen Klasse. Die Bezeichnung „Accuracy / Recall“ dient hier nur dazu, die direkt sichtbare Quote verständlich zu machen.

## 1. Overall Accuracy

Die Overall Accuracy beantwortet die Frage: *Welcher Anteil aller auswertbaren Baugruppen wurde exakt mit dem primären Ground-Truth-Label klassifiziert?*

```text
Overall Accuracy = korrekte Vorhersagen / Anzahl auswertbarer Fälle
                 = 95 / 115
                 = 0,8261 = 82,6 %
```

## 2. Macro-Average

Beim Macro-Average erhält jede der sieben Funktionsklassen dasselbe Gewicht, unabhängig von ihrer Anzahl im Datensatz.

Aus den in diesem Screenshot sichtbaren Daten lässt sich nur der Macro-Recall exakt berechnen:

```text
Macro-Recall = (0,75 + 0,625 + 1,00 + 0,80 + 1,00 + 0,6875 + 1,00) / 7
             = 0,8375 = 83,8 %
```

Macro-Precision und Macro-F1 sind mit dieser Tabelle **nicht bestimmbar**. Dafür werden zusätzlich die False Positives jeder Klasse benötigt; diese stehen in einer vollständigen Confusion Matrix oder in der vollständigen Ergebnisliste.

**Interpretation:** Der Macro-Recall gibt jeder Klasse dasselbe Gewicht. Die Klasse „Keine der verfügbaren Klassen“ mit sieben Fällen zählt daher genauso stark wie eine Klasse mit 20 Fällen.

## 3. Weighted-Average

Beim Weighted-Average wird jede Klasse mit ihrer Anzahl an Ground-Truth-Fällen gewichtet. Häufigere Klassen beeinflussen das Ergebnis daher stärker.

```text
Weighted-Metric = (n1 × Metric1 + n2 × Metric2 + ... + n7 × Metric7) / N
```

Für den Recall ergibt sich:

```text
Weighted-Recall = (20×0,75 + 16×0,625 + 18×1,00 + 20×0,80
                   + 18×1,00 + 16×0,6875 + 7×1,00) / 115
                = 95 / 115
                = 0,8261 = 82,6 %
```

Bei einer vollständigen Single-Label-Multiclass-Klassifikation ist der Weighted-Recall gleich der Overall Accuracy. Weighted-Precision und Weighted-F1 sind aus dem Screenshot ebenfalls nicht bestimmbar.

## Kurze Zusammenfassung der Literaturrecherche

Die Literatur beschreibt keine einzige, für jede Multi-Class-Aufgabe immer richtige Aggregationsmethode. Die Wahl hängt vom Evaluationsziel ab:

- **Macro-Average** ist passend, wenn alle Klassen gleich wichtig sind. Dies trifft hier auf die sieben Funktionsklassen zu.
- **Weighted-Average** berücksichtigt zusätzlich die beobachtete Klassenverteilung des Datensatzes.
- **Micro-Average** fasst alle Entscheidungen zusammen; bei vollständiger Single-Label-Multiclass-Klassifikation ist es identisch mit der Overall Accuracy.
- Bei ungleich verteilten Klassen sollte Accuracy nicht allein berichtet werden; klassenweise Kennzahlen und Macro-Werte machen mögliche Schwächen kleinerer Klassen sichtbar.
- Bei Macro-F1 muss die Formel eindeutig angegeben werden. Macro-F1 ist der arithmetische Mittelwert der klassenweisen F1-Scores.

## Literatur

1. Grandini, M., Bagli, E. & Visani, G. (2020). *Metrics for Multi-Class Classification: An Overview*. arXiv:2008.05756. https://arxiv.org/abs/2008.05756
2. Sokolova, M. & Lapalme, G. (2009). *A Systematic Analysis of Performance Measures for Classification Tasks*. Information Processing & Management, 45(4), 427–437. https://doi.org/10.1016/j.ipm.2009.03.002
3. Opitz, J. & Burst, S. (2021). *Macro F1 and Macro F1*. arXiv:1911.03347. https://arxiv.org/abs/1911.03347
4. Branco, P., Torgo, L. & Ribeiro, R. P. (2016). *A Survey of Predictive Modelling under Imbalanced Distributions*. ACM Computing Surveys, 49(2), Article 31. https://doi.org/10.1145/2907070

## Bild einfügen

Ein Bild kann später direkt unter der gewünschten Überschrift eingefügt werden. Bei einer lokalen Markdown-Datei reicht zum Beispiel:

```markdown
![Confusion Matrix des Beispiel-Laufs](images/confusion_matrix_beispiel.png)
```

Die Bilddatei sollte dann im Unterordner `images` liegen. In GitHub, VS Code und vielen Markdown-Viewern wird sie automatisch angezeigt.
