# Fehler_Analyse | 错误分析明细

## 第一部分 · Excel 第 2–6 行

来源为工作表 `Fehler_Analyse` 的五张照片。按各截图重叠列和行顺序对应，保留该工作表显示的 Ground Truth、Register 和其他允许类别。

- `—` 表示截图中可见的空白单元格，`[EMPTY]` 为原表明确标记的值。B 列表头被遮挡，五行显示的值均为 0，暂不推断其名称。
- H–J 列表头被列宽截断，表格中的完整模型和输入形式名称参考同一工作簿的 `Korrigierte GT&ZGT` 对应列。第 3 行 N、Q 列的类别文字末尾可能被截断，按可见内容标注。
- 第 5 行 SAP-Nummer 显示为 `804306221`，按照片原样记录。
- 每行 12 个模型列的非空值数与 `Error_Count` 一致。T 列为错误分析原文；下方内容按照片转录。

| Excel 行 | A · Error_Count | B · 表头未完整显示 | C · SAP-Nummer | D · Teamcenter | E · Register | F · Ground Truth | G · Weitere zulässige Ground Truth | claude-haiku-4-5_20251001 (image) | claude-haiku-4-5_20251001 (pdf) | claude-haiku-4-5_20251001 (text) | claude-opus-4-8 (image) | claude-opus-4-8 (pdf) | claude-opus-4-8 (text) | gemini-2.5-flash (image) | gemini-2.5-flash (pdf) | gemini-2.5-flash (text) | gemini-2.5-pro (image) | gemini-2.5-pro (pdf) | gemini-2.5-pro (text) | T · Fehleranalyse |
| ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | 11 | 0 | 0804EN7325 | AS90118452/01 | M | Kombinierte Einheit | — | Gantry | Gantry | Gantry | Gantry | — | Gantry | Gantry | Gantry | Gantry | Gantry | Gantry | Gantry | [原文](#excel-第-2-行) |
| 3 | 10 | 0 | 0804FC1588 | AS90011709 | E1 | Multi-Achs-System (Gantry) | — | `[EMPTY]` | `[EMPTY]` | — | `[EMPTY]` | Kombinierte Einheit | — | Keine der verfügbaren Klasse（末尾可能截断） | Kombinierte Einheit | Kombinierte Einheit | Keine der verfügbaren Klasse（末尾可能截断） | Kombinierte Einheit | Kombinierte Einheit | [原文](#excel-第-3-行) |
| 4 | 10 | 0 | 0804LV8630 | AS00371812 | M | Rotationseinheit | Lineareinheit | `[EMPTY]` | — | — | `[EMPTY]` | Kombinierte Einheit | Kombinierte Einheit | Kombinierte Einheit | Kombinierte Einheit | Kombinierte Einheit | Kombinierte Einheit | Kombinierte Einheit | Kombinierte Einheit | [原文](#excel-第-4-行) |
| 5 | 9 | 0 | 804306221 | AS90101734 | E2 | Kombinierte Einheit | — | Gantry | Gantry | Gantry | — | — | — | Gantry | Gantry | Gantry | Gantry | Gantry | Gantry | [原文](#excel-第-5-行) |
| 6 | 8 | 0 | 0804GE7738 | AS90109419 | M | Kombinierte Einheit | — | Lineareinheit | Rotationseinheit | Rotationseinheit | Lineareinheit | — | Rotationseinheit | Lineareinheit | — | Rotationseinheit | Lineareinheit | — | — | [原文](#excel-第-6-行) |

### Excel 第 2 行

Fehleranalyse: Keine X/Y Bewegung vorhanden. Nur Z/X. Aber beidseitige Führung. Daher kombinierte Einheit korrekt nach Schema, aber Gantry vertretbar. Alternativantwort hier allerdings strittig im Rückblick! Das ist klar eine kombinierte Einheit! Zudem erkennt das LLM 3 Achsen, obwohl es nur zwei gibt. LLM entscheidet falsch!

### Excel 第 3 行

Die Baugruppe „gantry“ 0804FC1588 wird in der Ground Truth und von allen Annotatoren als Gantry gelabelt. Allerdings ist die lineare Z-Achse auf einen Drehaktor aufgesetzt (in Zeichnung erkennbar), sodass es sich eindeutig um eine Kombinierte Einheit handelt. Sowohl Claude Opus 4-8 als auch Gemini 2.5 Pro haben dies im Lauf P3 (pdf) korrekt erkannt.

### Excel 第 4 行

Gemini 2.5 Pro sagt, dass es Kombinierte Einheit ist. Das ist vertretbar, da Rotation & Teleskop-Translation überlagert wird. Bisher zulässiges Alternativlabel „Lineareinheit“ passt aber nicht, da es klar eine Rotation gibt.

### Excel 第 5 行

Hier entscheidet das LLM falsch, aber es ist eine Feinheit. Die beidseitige Führung wird falsch ausgelegt.

### Excel 第 6 行

GT vor Review: Kombinierte Einheit | LLM: Rotationseinheit (oder Lineareinheit). Analyse: Hauptantrieb ist ein SCHUNK-Rundschalttisch (Pos. 0100, R=1), ergänzt durch einen AVENTICS-Führungszylinder (Pos. 0102, Hub 10 mm) als Ausheber zur Positionierung/Kontaktierung. Wertet man den 10 mm-Hub als Hilfsfunktion (T=0), gilt Rotationseinheit; zählt man beide unabhängigen Aktoren (R=1, T=1), gilt Kombinierte Einheit. Wegen der eindeutigen Rotation ist „Lineareinheit“ ausgeschlossen. Revidierte GT: Rotationseinheit, Kombinierte Einheit (LLM korrekt bei Rotationseinheit).
