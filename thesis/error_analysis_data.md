# 错误分析数据 | Fehleranalyse

## 第一部分 · P3 下按模型与输入形式统计

来源为 2026 年 10 月 15 日的幻灯片第 2 页及同页的两张表格近照。页面标题为 **Fehleranalyse (185 Baugruppe)**。四张模型表均标注 **57BG, P3, Alle Modalitäten**，输入形式为 Bild (Image)、PDF 和 Text。照片未说明标题中的 185 与各表 57BG 的关系。

### 原表数据

#### Claude Haiku 4.5

| Metrik | Bild (Image) | PDF | Text | Total (Gesamt) |
|---|---:|---:|---:|---:|
| Gesamtfehler (inkl. [EMPTY]) | 27 | 20 | 10 | 57 |
| Falschvorhersagen | 25 | 13 | 10 | 48 |
| Leere Ausgabe [EMPTY] | 2 | 7 | 0 | 9 |
| LLM korrekt (GT korrigiert) | 2 | 3 | 1 | 6 |

#### Claude Opus 4.8

| Metrik | Bild (Image) | PDF | Text | Total (Gesamt) |
|---|---:|---:|---:|---:|
| Gesamtfehler (inkl. [EMPTY]) | 19 | 8 | 14 | 41 |
| Falschvorhersagen | 17 | 7 | 14 | 38 |
| Leere Ausgabe [EMPTY] | 2 | 1 | 0 | 3 |
| LLM korrekt (GT korrigiert) | 2 | 4 | 5 | 11 |

#### Gemini 2.5 Pro

| Metrik | Bild (Image) | PDF | Text | Total (Gesamt) |
|---|---:|---:|---:|---:|
| Gesamtfehler (inkl. [EMPTY]) | 22 | 9 | 10 | 41 |
| Falschvorhersagen | 22 | 8 | 10 | 40 |
| Leere Ausgabe [EMPTY] | 0 | 1 | 0 | 1 |
| LLM korrekt (GT korrigiert) | 3 | 4 | 5 | 12 |

#### Gemini 2.5 Flash

| Metrik | Bild (Image) | PDF | Text | Total (Gesamt) |
|---|---:|---:|---:|---:|
| Gesamtfehler (inkl. [EMPTY]) | 26 | 15 | 10 | 51 |
| Falschvorhersagen | 25 | 11 | 10 | 46 |
| Leere Ausgabe [EMPTY] | 1 | 4 | 0 | 5 |
| LLM korrekt (GT korrigiert) | 2 | 4 | 5 | 11 |

### 四个模型合计

下表按模型相加，单位是各模型与输入形式下的预测记录。同一装配体可能计入多次。

| Metrik | Bild (Image) | PDF | Text | Total (Gesamt) |
|---|---:|---:|---:|---:|
| Gesamtfehler (inkl. [EMPTY]) | 94 | 52 | 44 | 190 |
| Falschvorhersagen | 89 | 39 | 44 | 172 |
| Leere Ausgabe [EMPTY] | 5 | 13 | 0 | 18 |
| LLM korrekt (GT korrigiert) | 9 | 15 | 16 | 40 |

### 幻灯片结论与复算

- 幻灯片称约 **21%** 的原判错误在修订 Ground Truth 后判为正确。按表中含 `[EMPTY]` 的总错误数复算，比例为 **40 / 190 = 21,05%**。
- 幻灯片称纯图片输入占约 **50%** 的错误。按四个模型汇总，图片输入的错误数为 **94 / 190 = 49,47%**，分母同样包含 `[EMPTY]`。
- 四张表的各行合计均等于三种输入形式之和。每个模型及输入形式下，`Gesamtfehler` 均等于 `Falschvorhersagen` 与 `Leere Ausgabe [EMPTY]` 之和。`LLM korrekt (GT korrigiert)` 记录经 Ground Truth 修订后改判为正确的情况。
