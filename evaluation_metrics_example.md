# Beispiel: Berechnung von Macro- und Weighted-Metriken

| Class | Ground Truth rows | Correct predictions | Accuracy | Precision | Recall | F1-score |
|---|---:|---:|---:|---:|---:|---:|
| Lineareinheit | 20 | 17 | 85,0 % | 0,94 | 0,85 | 0,89 |
| Gantry | 16 | 12 | 75,0 % | 0,86 | 0,75 | 0,80 |
| Greifer | 18 | 18 | 100,0 % | 1,00 | 1,00 | 1,00 |
| Umsetzeinheit | 20 | 17 | 85,0 % | 0,81 | 0,85 | 0,83 |
| Roboter | 18 | 18 | 100,0 % | 1,00 | 1,00 | 1,00 |
| Rotationseinheit | 16 | 12 | 75,0 % | 0,92 | 0,75 | 0,83 |
| Keine der verfügbaren Klassen | 7 | 7 | 100,0 % | 0,58 | 1,00 | 0,74 |
| **Gesamt** | **115** | **101** | **87,8 %** |  |  |  |

> **Platz für Abbildung:** Hier kann später ein Screenshot der zugehörigen Confusion Matrix eingefügt werden.

Die Tabelle beschreibt die strikte Bewertung mit dem primären Ground-Truth-Label. Die Werte wurden aus den Screenshots übernommen und auf Konsistenz geprüft. Für Gantry gilt: `12 / 16 = 0,75`; deshalb sind Accuracy und Recall jeweils 75,0 % und der F1-Score beträgt mit Precision 0,86 gerundet 0,80.

## Strikte Ergebnisse nach Regime

| Regime | Auswertbare Fälle | Fehler | Strikt korrekt | Strict Accuracy | Precision | Recall | F1-Score |
|---|---:|---:|---:|---:|---:|---:|---:|
| E1 | 56 | 2 | 54 | 96,4 % | noch nicht berechenbar | noch nicht berechenbar | noch nicht berechenbar |
| E2 | 35 | 5 | 30 | 85,7 % | noch nicht berechenbar | noch nicht berechenbar | noch nicht berechenbar |
| M | 24 | 6 | 18 | 75,0 % | noch nicht berechenbar | noch nicht berechenbar | noch nicht berechenbar |

```text
E1 strict Accuracy = 54 / 56 = 96,4 %
E2 strict Accuracy = 30 / 35 = 85,7 %
M strict Accuracy  = 18 / 24 = 75,0 %
```

Für Precision, Recall und F1-Score reichen die Fehlerzahlen allein nicht aus. Dafür wird je Regime die vollständige Zuordnung aus tatsächlicher Klasse und vorhergesagter Klasse benötigt, also die jeweilige Confusion Matrix bzw. die vollständige Ergebnisliste.

Die drei Regime enthalten zusammen 115 Fälle und 102 strikte korrekte Vorhersagen. Das weicht um einen Fall von der klassenweisen Tabelle oben ab (dort: 101 korrekte Vorhersagen). Vor einer gemeinsamen Gesamtkennzahl müssen diese beiden Quellen daher noch abgeglichen werden; die drei Regime-Werte selbst sind davon nicht betroffen.

## 1. Overall Accuracy

Die Overall Accuracy beantwortet die Frage: *Welcher Anteil aller auswertbaren Baugruppen wurde exakt mit dem primären Ground-Truth-Label klassifiziert?*

```text
Overall Accuracy = korrekte Vorhersagen / Anzahl auswertbarer Fälle
                 = 101 / 115
                 = 0,8783 = 87,8 %
```

## 2. Macro-Average

Beim Macro-Average erhält jede der sieben Funktionsklassen dasselbe Gewicht, unabhängig von ihrer Anzahl im Datensatz.

```text
Macro-Precision = (0,94 + 0,86 + 1,00 + 0,81 + 1,00 + 0,92 + 0,58) / 7
                = 0,873 = 87,3 %

Macro-Recall    = (0,85 + 0,75 + 1,00 + 0,85 + 1,00 + 0,75 + 1,00) / 7
                = 0,886 = 88,6 %

Macro-F1        = (0,89 + 0,80 + 1,00 + 0,83 + 1,00 + 0,83 + 0,74) / 7
                = 0,870 = 87,0 %
```

**Interpretation:** Macro-Werte zeigen, wie gleichmäßig das Modell über alle Funktionsklassen arbeitet. Die Klasse „Keine der verfügbaren Klassen“ mit sieben Fällen zählt dabei genauso stark wie eine Klasse mit 20 Fällen.

## 3. Weighted-Average

Beim Weighted-Average wird jede Klasse mit ihrer Anzahl an Ground-Truth-Fällen gewichtet. Häufigere Klassen beeinflussen das Ergebnis daher stärker.

```text
Weighted-Metric = (n1 × Metric1 + n2 × Metric2 + ... + n7 × Metric7) / N
```

```text
Weighted-Precision = (20×0,94 + 16×0,86 + 18×1,00 + 20×0,81
                      + 18×1,00 + 16×0,92 + 7×0,58) / 115
                   = 0,900 = 90,0 %

Weighted-Recall    = (20×0,85 + 16×0,75 + 18×1,00 + 20×0,85
                      + 18×1,00 + 16×0,75 + 7×1,00) / 115
                   = 101 / 115
                   = 0,878 = 87,8 %

Weighted-F1        = (20×0,89 + 16×0,80 + 18×1,00 + 20×0,83
                      + 18×1,00 + 16×0,83 + 7×0,74) / 115
                   = 0,884 = 88,4 %
```

Die Werte können geringfügig von einer Skriptausgabe abweichen, weil die klassenweisen Precision-, Recall- und F1-Werte in dieser Tabelle bereits gerundet sind. Das Skript sollte stets mit den ungerundeten TP-, FP- und FN-Werten rechnen.

**Interpretation:** Weighted-Werte beschreiben die Leistung unter Berücksichtigung der tatsächlichen Klassenverteilung dieses Datensatzes.

## Kurze Zusammenfassung der Literaturrecherche

Die Literatur beschreibt keine einzige, für jede Multi-Class-Aufgabe immer richtige Aggregationsmethode. Die Wahl hängt vom Evaluationsziel ab:

- **Macro-Average** ist passend, wenn alle Klassen gleich wichtig sind. Dies trifft hier auf die sieben Funktionsklassen zu.
- **Weighted-Average** berücksichtigt zusätzlich die beobachtete Klassenverteilung des Datensatzes.
- **Micro-Average** fasst alle Entscheidungen zusammen; bei vollständiger Single-Label-Multiclass-Klassifikation ist es identisch mit der Overall Accuracy.
- Bei ungleich verteilten Klassen sollte Accuracy nicht allein berichtet werden; klassenweise Kennzahlen und Macro-Werte machen mögliche Schwächen kleinerer Klassen sichtbar.
- Bei Macro-F1 muss die Formel eindeutig angegeben werden. In diesem Dokument ist Macro-F1 der arithmetische Mittelwert der klassenweisen F1-Scores.

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
