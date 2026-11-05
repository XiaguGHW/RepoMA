# Notizen: Literatur und Mail an Jonas

Persönliche Arbeitsnotizen zum PDF `Update_Evaluationsmetriken.pdf`.

## Literatur im PDF zitiert

| Kurzzitat | Wofür |
|---|---|
| Sokolova & Lapalme (2009) | Standarddefinitionen von Precision, Recall, F1 |
| Opitz & Burst (2019) | Zwei Macro-F1-Varianten, Definition angeben |
| Efron & Tibshirani (1993) | Bootstrap-Konfidenzintervalle |
| Miller (2024) | Fehlerbalken / CIs für LLM-Evaluationen |
| Koehn (2004); Berg-Kirkpatrick et al. (2012) | Gepaarter Bootstrap für Modellvergleiche |
| Holm (1979) | Holm-Korrektur |
| Bender & Lange (2001) | Testfamilien festlegen, Korrektur je Metrik |

- Bender, R. & Lange, S. (2001). Adjusting for multiple testing—when and how? *Journal of Clinical Epidemiology*, 54(4), 343–349.
- Berg-Kirkpatrick, T., Burkett, D. & Klein, D. (2012). An Empirical Investigation of Statistical Significance in NLP. *Proceedings of EMNLP-CoNLL 2012*, 995–1005.
- Efron, B. & Tibshirani, R. J. (1993). *An Introduction to the Bootstrap*. New York: Chapman & Hall.
- Holm, S. (1979). A Simple Sequentially Rejective Multiple Test Procedure. *Scandinavian Journal of Statistics*, 6(2), 65–70.
- Koehn, P. (2004). Statistical Significance Tests for Machine Translation Evaluation. *Proceedings of EMNLP 2004*, 388–395.
- Miller, E. (2024). Adding Error Bars to Evals: A Statistical Approach to Language Model Evaluations. arXiv:2411.00640.
- Opitz, J. & Burst, S. (2019). Macro F1 and Macro F1. arXiv:1911.03347.
- Sokolova, M. & Lapalme, G. (2009). A systematic analysis of performance measures for classification tasks. *Information Processing & Management*, 45(4), 427–437.

## Weitere Literatur für die Arbeit (nicht im PDF)

| Kurzzitat | Wofür |
|---|---|
| Shankar et al. (2020); Beyer et al. (2020) | Accuracy mit mehreren zulässigen Labels (Allowed Accuracy) |
| Plank (2022) | Labelvariation als legitim, nicht nur Rauschen |
| Atil et al. (2024) | Schwankungen von LLMs auch bei deterministischen Einstellungen (Begründung für 10 Läufe) |
| Dror et al. (2018) | Signifikanztests in NLP oft vernachlässigt |
| Sclar et al. (2024) | Prompt-Sensitivität (Begründung für Prompt-Vergleiche) |
| Cawley & Talbot (2010) | Selektionsbias, wenn Prompt auf denselben Daten gewählt wird |
| Bouthillier et al. (2021) | Varianzquellen in ML-Benchmarks |
| Wilson (1927) | Wilson-Intervall für Anteile bei kleinen Stichproben |

- Atil, B. et al. (2024). Non-Determinism of "Deterministic" LLM Settings. arXiv:2408.04667.
- Beyer, L., Hénaff, O. J., Kolesnikov, A., Zhai, X. & van den Oord, A. (2020). Are we done with ImageNet? arXiv:2006.07159.
- Bouthillier, X. et al. (2021). Accounting for Variance in Machine Learning Benchmarks. *Proceedings of Machine Learning and Systems 3 (MLSys 2021)*.
- Cawley, G. C. & Talbot, N. L. C. (2010). On Over-fitting in Model Selection and Subsequent Selection Bias in Performance Evaluation. *Journal of Machine Learning Research*, 11, 2079–2107.
- Dror, R., Baumer, G., Shlomov, S. & Reichart, R. (2018). The Hitchhiker's Guide to Testing Statistical Significance in Natural Language Processing. *Proceedings of ACL 2018*, 1383–1392.
- Plank, B. (2022). The "Problem" of Human Label Variation: On Ground Truth in Data, Modeling and Evaluation. *Proceedings of EMNLP 2022*, 10671–10682.
- Sclar, M., Choi, Y., Tsvetkov, Y. & Suhr, A. (2024). Quantifying Language Models' Sensitivity to Spurious Features in Prompt Design or: How I learned to start worrying about prompt formatting. *ICLR 2024*. arXiv:2310.11324.
- Shankar, V., Roelofs, R., Mania, H., Fang, A., Recht, B. & Schmidt, L. (2020). Evaluating Machine Accuracy on ImageNet. *Proceedings of ICML 2020*, PMLR 119, 8634–8644.
- Wilson, E. B. (1927). Probable Inference, the Law of Succession, and Statistical Inference. *Journal of the American Statistical Association*, 22(158), 209–212.

Hinweise:
- Beyer et al., Opitz & Burst, Miller, Atil et al. sind arXiv-Preprints (nicht begutachtet).
- Bouthillier et al.: Autorenliste unterscheidet sich zwischen MLSys- und arXiv-Version.
- Miller (2024) empfiehlt für einfache Mittelwerte die CLT-Formel; Bootstrap ist für komplexe Schätzer wie Macro-F1 gedacht.

## Mail an Jonas

**Betreff:** Update zu den Evaluationsmetriken und nächste Schritte

Hi Jonas,

eigentlich wollte ich dir schon gestern schreiben, aber ich hatte Fieber, deshalb kommt die Mail erst jetzt. Das tut mir leid. Falls du ein Attest brauchst, kann ich es gerne nachreichen.

In den letzten Tagen habe ich mich beim Schreiben noch einmal intensiver mit der Literatur zu Evaluationsmetriken beschäftigt und möchte dir dazu ein kurzes Update geben (Details im Anhang). Auf dieser Grundlage habe ich die Auswertungsskripte überarbeitet und einige Fehler behoben.

Außerdem habe ich sichergestellt, dass die große Excel-Datei mit den 199 BGs die finale Ground Truth enthält, also bei allen Einträgen den aktuellen Stand nach meiner Fehleranalyse. Damit habe ich die Gesamtergebnisse der Stabilitätsläufe (5 Modelle × 10 Läufe) sowie der PDF-, Bild- und Text-Experimente noch einmal überprüft.

Heute würde ich einige Zahlen im 2-Pager aktualisieren und eine Grafik in deinem Layout neu erstellen. Passt das für dich?

Eigentlich wollte ich heute ins Büro kommen. Ich möchte aber weder dich noch die Kolleginnen und Kollegen anstecken – gerade vor deiner Reise wäre es ungünstig, wenn du krank wirst.

Mein Vorschlag für die nächsten Schritte: Ich schicke dir morgen das Kapitel zum Workshop und am Montag das Kapitel zu den LLM-Experimenten. Ist das für dich in Ordnung?

Viele Grüße
[Dein Name]
