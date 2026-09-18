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
| **Gesamt (alle Anfragen)** | **115** | **101** | **87,8 %** |  |  |  |

| Regime | Ursprüngliche Fälle | Nicht auswertbar | Auswertbare Fälle | Fehler | Strikt korrekt | Strict Accuracy |
|---|---:|---:|---:|---:|---:|---:|
| E1 | 56 | 0 | 56 | 2 | 54 | 96,4 % |
| E2 | 35 | 1 (HTTP-Fehler) | 34 | 5 | 29 | 85,3 % |
| M | 24 | 0 | 24 | 6 | 18 | 75,0 % |
| **Gesamt** | **115** | **1** | **114** | **13** | **101** | **88,6 %** |

## Overall Accuracy

```text
Strict Overall Accuracy (auswertbare Fälle) = 101 / 114 = 88,6 %
Accuracy über alle Anfragen                  = 101 / 115 = 87,8 %
```

## Macro-Average

```text
Macro-Precision = (0,94 + 0,86 + 1,00 + 0,81 + 1,00 + 0,92 + 0,58) / 7
                = 0,873 = 87,3 %

Macro-Recall    = (0,85 + 0,75 + 1,00 + 0,85 + 1,00 + 0,75 + 1,00) / 7
                = 0,886 = 88,6 %

Macro-F1        = (0,89 + 0,80 + 1,00 + 0,83 + 1,00 + 0,83 + 0,74) / 7
                = 0,870 = 87,0 %
```

## Weighted-Average

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

## Kurze Zusammenfassung der Literaturrecherche

- **Macro-Average** ist passend, wenn alle Klassen gleich wichtig sind.
- **Weighted-Average** berücksichtigt zusätzlich die beobachtete Klassenverteilung.
- **Micro-Average** ist bei vollständiger Single-Label-Multiclass-Klassifikation identisch mit der Overall Accuracy.
- Bei ungleich verteilten Klassen sollten Accuracy und klassenweise Kennzahlen gemeinsam berichtet werden.

## Literatur

1. Grandini, M., Bagli, E. & Visani, G. (2020). *Metrics for Multi-Class Classification: An Overview*. arXiv:2008.05756. https://arxiv.org/abs/2008.05756
2. Sokolova, M. & Lapalme, G. (2009). *A Systematic Analysis of Performance Measures for Classification Tasks*. Information Processing & Management, 45(4), 427–437. https://doi.org/10.1016/j.ipm.2009.03.002
3. Opitz, J. & Burst, S. (2021). *Macro F1 and Macro F1*. arXiv:1911.03347. https://arxiv.org/abs/1911.03347
4. Branco, P., Torgo, L. & Ribeiro, R. P. (2016). *A Survey of Predictive Modelling under Imbalanced Distributions*. ACM Computing Surveys, 49(2), Article 31. https://doi.org/10.1145/2907070
