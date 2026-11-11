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

## 第二部分 · Excel 第 7–11 行

来源为 `Fehler_Analyse` 工作表的四张照片。第 9 行在照片中为黄色高亮。部分模型列在这批照片中被裁切，表中对应位置参考同一工作簿 `Korrigierte GT&ZGT` 工作表的相同行转录，尚需核对。第 11 行 Fehleranalyse 已根据后续照片补齐。

| Excel 行 | A · Error_Count | B · 表头未完整显示 | C · SAP-Nummer | D · Teamcenter | E · Register | F · Ground Truth | G · Weitere zulässige Ground Truth | claude-haiku-4-5_20251001 (image) | claude-haiku-4-5_20251001 (pdf) | claude-haiku-4-5_20251001 (text) | claude-opus-4-8 (image) | claude-opus-4-8 (pdf) | claude-opus-4-8 (text) | gemini-2.5-flash (image) | gemini-2.5-flash (pdf) | gemini-2.5-flash (text) | gemini-2.5-pro (image) | gemini-2.5-pro (pdf) | gemini-2.5-pro (text) | T · Fehleranalyse |
|---:|---:|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 7 | 8 | 0 | `0804GT0312` | `AS90082305` | E2 | Kombinierte Einheit | — | Lineareinheit | Gantry | Lineareinheit | — | — | Lineareinheit | Gantry | Gantry | — | Lineareinheit | Gantry | — | [原文](#excel-第-7-行) |
| 8 | 8 | 0 | `0804MB2849` | `AS00394314` | E1 | Lineareinheit | — | Kombinierte Einheit | Kombinierte Einheit | — | Kombinierte Einheit | Kombinierte Einheit | — | — | Kombinierte Einheit | Kombinierte Einheit | — | Kombinierte Einheit | Kombinierte Einheit | [原文](#excel-第-8-行) |
| 9 | 7 | 0 | `0804DN9616` | `AS90430781` | E2 | Multi-Achs-System (Gantry) | — | — | `[EMPTY]` | — | Lineareinheit | `[EMPTY]` | — | Lineareinheit | `[EMPTY]` | — | Lineareinheit | `[EMPTY]` | — | [原文](#excel-第-9-行) |
| 10 | 6 | 0 | `0804EB6690` | `AS90347860` | E2 | Kombinierte Einheit | — | Greifer | Rotationseinheit | Rotationseinheit | Greifer | — | — | Greifer | — | — | Greifer | — | — | [原文](#excel-第-10-行) |
| 11 | 6 | 0 | `0804GT5112` | `AS90282232` | E1 | Kombinierte Einheit | — | Gantry | Gantry | Gantry | — | — | — | Gantry | — | — | Gantry | — | Gantry | [原文](#excel-第-11-行) |

### Excel 第 7 行

Fehleranalyse: Eindeutig KE, aber 3D fehlerhaft. Zuordnung daher schwierig. Entscheidung für LE mit 3D ist nachvollziehbar. Urteil: Hier macht das LLM einen Fehler! Es gibt nur 2 Translationen in X/Z. Das ist eindeutig eine Kombinierte Einheit.

### Excel 第 8 行

Fehleranalyse: Eindeutig eine Lineareinheit und keine abweichenden Annotationen (E1). Prüfung: Das ist eine Kombinierte Einheit mit zwei Linearaktoren! Das LLM ist richtig! !! Alle 4 Annotationen + Ground Truth sagen Lineareinheit, aber das ist falsch !!

### Excel 第 9 行

Kontext ist zu groß, es kann keine Verarbeitung durchgeführt werden. Es wird kein Label vergeben.

### Excel 第 10 行

GT vor Review: Kombinierte Einheit (Umsetzeinheit) | LLM: Greifer / Rotationseinheit
Analyse: Beide LLM-Vorschläge sind falsch. Verbaut sind ein translatorischer AVENTICS-Kompaktschlitten (Pos. 0102, Hub 30 mm → T=1), eine rotatorische SCHUNK-Schwenkeinheit (Pos. 0104, 90° → R=1) sowie zwei Winkelgreifer (Pos. 0105) als Endeffektoren. Das LLM lässt sich durch die irreführende Benennung („Rotationseinheit“) bzw. die vorhandenen Greifer täuschen und übersieht die Kombination aus Hub- und Schwenkachse (R=1, T=1, vgl. Codebook Grenzfall 6.3). Revidierte GT: Kombinierte Einheit / Umsetzeinheit (LLM korrekt: nein).

### Excel 第 11 行

GT vor Review: Kombinierte Einheit (Umsetzeinheit) | LLM: Gantry
Analyse: Verbaut sind genau zwei translatorische Achsen (R=0, T=2): ein Festo-Kompaktschlitten (Pos. 0001, D=16, Hub 100 mm) und eine Lineareinheit (Pos. 0006, D=25, Hub 250 mm), verbunden über Adapterstück (Pos. 0002) und Verbindungssatz (Pos. 0003). Das LLM lässt sich durch die Benennung „gantry axle / Portalachse“ täuschen: Ein Zweiachsensystem ohne zwei Horizontalachsen mit beidseitig geführter Portalstruktur fällt im Gantry-Test (Codebook Abschnitt 4, Fall B sowie Grenzfall 6.4 / 6.6) durch und ist zwingend als Kombinierte Einheit (Umsetzeinheit) einzustufen.
Revidierte GT: Kombinierte Einheit / Umsetzeinheit (LLM korrekt: nein).

## 第三部分 · Excel 第 12 行

来源为 `Fehler_Analyse` 工作表的照片。G 列在照片中为空。模型输出完整显示为六个非空值，与 `Error_Count` 一致。

| Excel 行 | A · Error_Count | B · 表头未完整显示 | C · SAP-Nummer | D · Teamcenter | E · Register | F · Ground Truth | G · Weitere zulässige Ground Truth | claude-haiku-4-5_20251001 (image) | claude-haiku-4-5_20251001 (pdf) | claude-haiku-4-5_20251001 (text) | claude-opus-4-8 (image) | claude-opus-4-8 (pdf) | claude-opus-4-8 (text) | gemini-2.5-flash (image) | gemini-2.5-flash (pdf) | gemini-2.5-flash (text) | gemini-2.5-pro (image) | gemini-2.5-pro (pdf) | gemini-2.5-pro (text) | T · Fehleranalyse |
|---:|---:|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 12 | 6 | 0 | `0804JX6656` | `AS00057035` | E2 | Multi-Achs-System (Gantry) | — | — | — | Lineareinheit | Kombinierte Einheit | Lineareinheit | Keine der verfügbaren Klassen | — | — | Keine der verfügbaren Klassen | Lineareinheit | — | — | [原文](#excel-第-12-行) |

### Excel 第 12 行

GT vor Review: Multi-Achs-System (Gantry) | LLM: Lineareinheit / Kombinierte Einheit / Keine der verfügbaren Klassen
Analyse: Diskrepanz zwischen Zeichnung/CAD und Stückliste (analog zu 0804KW8391): In der Zeichnung sind zwei orthogonale Horizontalachsen inklusive Motoren und Energieführungsketten als Referenz-/Störkontur (Strich-Zweipunkt-Linie) dargestellt, in der Stückliste (0804JX6656) sind diese Antriebe jedoch nicht enthalten – verbaut sind nur das Gestell (Pos. 0001–0010), Spannstücke (Pos. 0101) zur Klemmung des externen Linearmoduls sowie zwei orthogonale Führungsschienen (Pos. 0102, Pos. 0103) mit Führungswagen (Pos. 0104). Bezieht man die in CAD/Zeichnung dargestellten zwei Motorachsen (R=0, T=2) ein, sind Gantry (X/Y-System mit paralleler Stützschiene Pos. 0102) und Kombinierte Einheit (Umsetzeinheit) vertretbar; wertet man streng nach Stückliste ohne eigene Aktoren (R=0, T=0), gilt Keine der verfügbaren Klassen. Lineareinheit (T=1) ist in jedem Fall falsch.
Revidierte GT: Gantry, Kombinierte Einheit (Umsetzeinheit), Keine der verfügbaren Klassen (LLM korrekt bei „Kombinierte Einheit“ und „Keine der verfügbaren Klassen“, falsch bei „Lineareinheit“).
