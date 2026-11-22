# Beispiel-Konfusionsmatrix mit Labelmengen (fiktive Werte)

> 根据四张 Excel 照片还原，重叠区域已合并。以下均为原表的虚构示例值，不是论文实验结果。保留德文原文、类别缩写、数值和加粗标记；原表因列宽产生的单词换行已合并。工作表名称：Konfusionsmatrix。

## Konfusionsmatrix

Referenz ↓ / Vorhersage →

> 行为参考类别或允许标签集，列为预测类别。加粗数字表示预测属于该行允许标签集的数量。

### Eindeutig

| Referenz ↓ / Vorhersage → | LE | RE | GR | MA | RO | KE | SO | n | korrekt | Accuracy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| LE | **26** | 0 | 1 | 2 | 0 | 1 | 0 | 30 | 26 | 86,7% |
| RE | 0 | **15** | 1 | 0 | 0 | 1 | 1 | 18 | 15 | 83,3% |
| GR | 1 | 0 | **25** | 0 | 0 | 1 | 1 | 28 | 25 | 89,3% |
| MA | 2 | 0 | 0 | **16** | 2 | 2 | 0 | 22 | 16 | 72,7% |
| RO | 0 | 0 | 0 | 2 | **13** | 0 | 0 | 15 | 13 | 86,7% |
| KE | 2 | 1 | 2 | 2 | 0 | **12** | 1 | 20 | 12 | 60,0% |
| SO | 1 | 0 | 1 | 0 | 0 | 1 | **19** | 22 | 19 | 86,4% |

### Mehrdeutig

| Referenz ↓ / Vorhersage → | LE | RE | GR | MA | RO | KE | SO | n | korrekt | Accuracy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| {LE, GR} | **4** | 0 | **5** | 0 | 0 | 1 | 0 | 10 | 9 | 90,0% |
| {MA, KE} | 0 | 0 | 0 | **3** | 2 | **2** | 0 | 7 | 5 | 71,4% |
| {GR, SO} | 0 | 0 | **3** | 0 | 0 | 1 | **1** | 5 | 4 | 80,0% |
| {LE, KE} | **1** | 0 | 0 | 1 | 0 | **2** | 0 | 4 | 3 | 75,0% |
| {RE, GR} | 0 | **2** | **1** | 0 | 0 | 0 | 1 | 4 | 3 | 75,0% |

## Zulässige Klassen je Zeile (1 = zulässig)

| Referenz | LE | RE | GR | MA | RO | KE | SO |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| LE | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| RE | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| GR | 0 | 0 | 1 | 0 | 0 | 0 | 0 |
| MA | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| RO | 0 | 0 | 0 | 0 | 1 | 0 | 0 |
| KE | 0 | 0 | 0 | 0 | 0 | 1 | 0 |
| SO | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| {LE, GR} | 1 | 0 | 1 | 0 | 0 | 0 | 0 |
| {MA, KE} | 0 | 0 | 0 | 1 | 0 | 1 | 0 |
| {GR, SO} | 0 | 0 | 1 | 0 | 0 | 0 | 1 |
| {LE, KE} | 1 | 0 | 0 | 0 | 0 | 1 | 0 |
| {RE, GR} | 0 | 1 | 1 | 0 | 0 | 0 | 0 |

## Accuracy nach Teilmenge

| Teilmenge | korrekt | n | Accuracy |
| --- | ---: | ---: | ---: |
| eindeutig | 126 | 155 | 81,3% |
| mehrdeutig | 24 | 30 | 80,0% |
| **alle (Allowed-Label-Set Accuracy)** | **150** | **185** | **81,1%** |

## Precision, Recall und F1 je Klasse (nur eindeutige Baugruppen)

| Klasse | TP | vorhergesagt (Spaltensumme) | Referenz (Zeilensumme) | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| LE – Lineareinheit | 26 | 32 | 30 | 81,3% | 86,7% | 83,9% |
| RE – Rotationseinheit | 15 | 16 | 18 | 93,8% | 83,3% | 88,2% |
| GR – Greifer | 25 | 30 | 28 | 83,3% | 89,3% | 86,2% |
| MA – Multi-Achs-System | 16 | 22 | 22 | 72,7% | 72,7% | 72,7% |
| RO – Roboter | 13 | 15 | 15 | 86,7% | 86,7% | 86,7% |
| KE – Kombinierte Einheit | 12 | 18 | 20 | 66,7% | 60,0% | 63,2% |
| SO – Sonstiges | 19 | 22 | 22 | 86,4% | 86,4% | 86,4% |
| **Macro (ungewichteter Mittelwert)** | **126** | **155** | **155** | **81,5%** | **80,7%** | **81,0%** |

## 核对说明

- 混淆矩阵共 12 个数据行：7 行 Eindeutig、5 行 Mehrdeutig；各行预测数量之和均与原表 n 一致。
- korrekt 等于该行所有允许类别列的计数之和；Accuracy = korrekt / n。
- 明确分类样本合计 155 个，其中正确 126 个；多义样本合计 30 个，其中正确 24 个；整体 150 / 185 = 81,1%。
- 最后一张表仅使用 Eindeutig 的 7 行；TP、行列合计、Precision、Recall、F1 和 Macro 均已复算，与照片保留一位小数的结果一致。
- Macro 行的 TP、vorhergesagt、Referenz 三项按原表保留，分别为数量合计；最后三项为七个类别各自指标的非加权平均值。
- SO – Sonstiges 是照片原有名称，未替换为论文中的其他类别表述。
