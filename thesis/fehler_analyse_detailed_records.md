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

## 第四部分 · Excel 第 13–15 行

来源为 `Fehler_Analyse` 工作表三张照片。根据行顺序及重叠列对应；部分模型输出列未完整拍到，暂参考同一工作簿 `Korrigierte GT&ZGT` 对应记录，待核对。Ground Truth、Register 和其他允许类别按本工作表照片记录。第 15 行错误分析已由后续照片补齐。

| Excel 行 | A · Error_Count | B · 表头未完整显示 | C · SAP-Nummer | D · Teamcenter | E · Register | F · Ground Truth | G · Weitere zulässige Ground Truth | claude-haiku-4-5_20251001 (image) | claude-haiku-4-5_20251001 (pdf) | claude-haiku-4-5_20251001 (text) | claude-opus-4-8 (image) | claude-opus-4-8 (pdf) | claude-opus-4-8 (text) | gemini-2.5-flash (image) | gemini-2.5-flash (pdf) | gemini-2.5-flash (text) | gemini-2.5-pro (image) | gemini-2.5-pro (pdf) | gemini-2.5-pro (text) | T · Fehleranalyse |
|---:|---:|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 13 | 6 | 0 | 0804KM9359 | AS00139165 | E2 | Rotationseinheit | — | — | Kombinierte Einheit | Kombinierte Einheit | Kombinierte Einheit | Kombinierte Einheit | Kombinierte Einheit | Kombinierte Einheit | — | — | — | — | — | [原文](#excel-第-13-行) |
| 14 | 6 | 0 | 0804KW8391 | AS00202949 | M | Multi-Achs-System (Gantry) | Kombinierte Einheit | — | Lineareinheit | Lineareinheit | — | — | Lineareinheit | — | — | Keine der verfügbaren Klassen | — | Lineareinheit | Keine der verfügbaren Klassen | [原文](#excel-第-14-行) |
| 15 | 6 | 0 | 0804LK3617 | AS00295735 | M | Rotationseinheit | Lineareinheit | — | Kombinierte Einheit | — | — | Kombinierte Einheit | Kombinierte Einheit | — | Kombinierte Einheit | — | Kombinierte Einheit | Kombinierte Einheit | — | [原文](#excel-第-15-行) |

### Excel 第 13 行

GT vor Review: Rotationseinheit | LLM: Kombinierte Einheit (Umsetzeinheit)
Analyse (Variante 1 - PDF/Text): Verbaut ist lediglich ein einziger Hauptaktor: eine pneumatische SCHUNK-Schwenkeinheit (Pos. 100, SRU-plus 63-W-180, 180° → R=1). Die daran montierte Greifereinheit (Pos. 10, 0804.KM9.320) mit einem 2-Finger-Parallelgreifer (Stufe 6, Pos. 100, SCHUNK) zählt als Endeffektor ebenso wenig mit wie die manuelle Verstellplatte (Pos. 3, 30 mm Einstellmaß) (T=0, vgl. Codebook Abschnitt 3). Das LLM wertet den Parallelgreifer bzw. die Verstellmöglichkeit fälschlicherweise als translatorische Achse (T=1).
Analyse (Variante 2 - 3D/Matrix): Verbaut sind lediglich eine pneumatische SCHUNK-Schwenkeinheit (Pos. 100, SRU-plus 63, 180° → R=1) und ein angebauter 2-Finger-Parallelgreifer (Stufe 6, Pos. 100, PGN-plus-P 160) als Endeffektor (T=0). Das LLM scheitert auf zwei Arten: Entweder wird das Doppelschaft-Gehäuse der Schwenkeinheit im 3D-Modell fälschlicherweise als lineare Hubeinheit/Doppelzylinder (T=1) halluziniert, oder das LLM ermittelt zwar korrekt R=1, T=0, setzt sich aber über die Entscheidungsmatrix hinweg, indem es „Schwenken + Greifen“ (in falscher Analogie zu Grenzfall 6.3) als heterogene Kinematik wertet.
Revidierte GT: Rotationseinheit (LLM korrekt: nein).

### Excel 第 14 行

Fehleranalyse: X/Y Bewegung und beidseitige Fixierung, aber keine Portalführung an beiden Enden der ersten Achse. Zweiter Aktor nicht Bestandteil der Baugruppe. Korrektur: Es sind überhaupt keine Aktoren vorhanden! Vertretbar ist daher Gantry, Kombiniert und Keine der verfügbaren Klassen. Das LLM entscheidet falsch!

### Excel 第 15 行

Fehleranalyse: Sehr schwierig: Eine Lineareinheit, die rotatorisch bewegt wird. Verbauter Aktor ist nur linear, aber Kettenrad und Lagerung für Rotation vorhanden. Kombinierte Einheit daher vertretbar, wenn Aktorkriterium weich ausgelegt wird. Rotationseinheit dann ebenfalls vertretbar, da die gesamte Baugruppe eine Rotation vollführt. Streng genommen aber eigentlich Lineareinheit. Rückblick: Rotation nicht vertretbar, da nur linearer Aktor verbaut ist! Dieser wird zwar durch Rotation angetrieben, aber bewegt sich linear. Zulässige Labels: Kombiniert, Linearaktor. LLM entscheidet korrekt!

## 第五部分 · Excel 第 16–17 行

来源为 `Fehler_Analyse` 工作表的三张照片。第 16 行的 Fehleranalyse 完整显示，第 17 行的 Fehleranalyse 已由后续照片补齐。部分模型列未拍全，表中对应位置参考 `Korrigierte GT&ZGT` 的记录，待核对。

| Excel 行 | A · Error_Count | B · 表头未完整显示 | C · SAP-Nummer | D · Teamcenter | E · Register | F · Ground Truth | G · Weitere zulässige Ground Truth | claude-haiku-4-5_20251001 (image) | claude-haiku-4-5_20251001 (pdf) | claude-haiku-4-5_20251001 (text) | claude-opus-4-8 (image) | claude-opus-4-8 (pdf) | claude-opus-4-8 (text) | gemini-2.5-flash (image) | gemini-2.5-flash (pdf) | gemini-2.5-flash (text) | gemini-2.5-pro (image) | gemini-2.5-pro (pdf) | gemini-2.5-pro (text) | T · Fehleranalyse |
|---:|---:|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 16 | 5 | 0 | `0804HZ8350` | `AS90317924` | E1 | Multi-Achs-System (Gantry) | — | Kombinierte Einheit | — | — | Kombinierte Einheit | — | Kombinierte Einheit | Kombinierte Einheit | — | — | Kombinierte Einheit | — | — | [原文](#excel-第-16-行) |
| 17 | 5 | 0 | `0804KY3585` | `AS00228511/03` | E1 | Multi-Achs-System (Gantry) | — | Lineareinheit | — | — | Kombinierte Einheit | — | Kombinierte Einheit | Lineareinheit | — | — | Lineareinheit | — | — | [原文](#excel-第-17-行) |

### Excel 第 16 行

GT vor Review: Multi-Achs-System (Gantry) | LLM: Kombinierte Einheit
Analyse: Eindeutiges 3-Achs-Gantry (R=0, T=3): Das Rexroth-Mehrachssystem (Pos. 0100, R115.800.975) besteht aus einer beidseitig geführten Portal-Basisachse (2x MKR-140 mit Synchronwelle, Hub 1750 mm), einer darüber als Brücke gelagerten Querachse (CKR-200, Hub 3220 mm) und einer vertikalen Z-Achse (CKK-145, Hub 420 mm). Das LLM scheitert aus zwei Gründen: Entweder übersieht es in der Unterstückliste die beiden MKR-140-Basismodule komplett und zählt nur T=2 (CKR-200 + CKK-145), oder es erkennt zwar T=3 inklusive 2x MKR-140, schließt aber aus dem Bauteilnamen „Kreuzplatte“ (Verbindung Y zu Z) fälschlicherweise auf eine einseitige Auslegerbauweise der Querachse und verneint so Kriterium (c).
Revidierte GT: Gantry (LLM korrekt: nein).

### Excel 第 17 行

GT vor Review: Multi-Achs-System (Gantry) | LLM: Kombinierte Einheit / Lineareinheit
Analyse: Eindeutiges 3-Achs-Gantry (R=0, T=3) auf 6 Ständern (Pos. 0010, H=1400 mm) mit X-Achse (Pos. 0020, beidseitig geführt über Fest- und Losseitenschlitten Pos. 0055–0070), zwei Y-Achsen (Pos. 0030, 0804.KX6.886) und einer Z-Achse (Pos. 0035, 0804.KX3.877). Das LLM scheitert an zwei typischen Fallstricken: Entweder betrachtet es isoliert nur die Unterstückliste der Z-Achse (0804.KX3.877 mit 1x Rexroth-Achse + Siemens-Motor → T=1) und klassifiziert fälschlich Lineareinheit, oder es erkennt zwar T=2 bzw. T=3, lässt sich aber durch das Einzelteil Pos. 0008 („Ausleger / Cantilever“ innerhalb der Z-Achse) in die Irre führen und schließt trotz der 6 Ständer und der expliziten Fest-/Loslager-Portalführung fälschlicherweise auf eine einseitige Auslegerbauweise der Gesamtstruktur (Kombinierte Einheit).
Revidierte GT: Gantry (LLM korrekt: nein).

## 第六部分 · Excel 第 18 行

来源为 `Fehler_Analyse` 工作表的三张照片。G 列文字在左侧照片边缘被裁切，可见开头与另一张表一致。部分模型列未拍全，参考同一工作簿 `Korrigierte GT&ZGT` 对应记录补录，待核对。

| Excel 行 | A · Error_Count | B · 表头未完整显示 | C · SAP-Nummer | D · Teamcenter | E · Register | F · Ground Truth | G · Weitere zulässige Ground Truth | claude-haiku-4-5_20251001 (image) | claude-haiku-4-5_20251001 (pdf) | claude-haiku-4-5_20251001 (text) | claude-opus-4-8 (image) | claude-opus-4-8 (pdf) | claude-opus-4-8 (text) | gemini-2.5-flash (image) | gemini-2.5-flash (pdf) | gemini-2.5-flash (text) | gemini-2.5-pro (image) | gemini-2.5-pro (pdf) | gemini-2.5-pro (text) | T · Fehleranalyse |
|---:|---:|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 18 | 4 | 0 | `0804CC2134` | `AS90419212/01` | M | Roboter | Kombinierte Einheit | Rotationseinheit | — | — | Keine der verfügbaren Klassen | — | — | Keine der verfügbaren Klassen | — | — | Greifer | — | — | [原文](#excel-第-18-行) |

### Excel 第 18 行

GT vor Review: Roboter, Kombinierte Einheit | LLM: Greifer / Keine der verfügbaren Klassen / Rotationseinheit
Analyse: Die Hauptbaugruppe umfasst einen 4-Achs-SCARA-Roboter (Pos. 0100, Stäubli TS60, R=3, T=1 mit 400 mm Pinolenhub) auf einem Standfuß (Pos. 0001) samt Vakuum-Ejektor (Pos. 0101) und SCHUNK-Schnellwechselkopf (Pos. 0102, SWK-011) – somit sind sowohl Roboter als auch Kombinierte Einheit (R ≥ 2, T=1) korrekt. Die Begründungen zeigen jedoch ein Dateninput-Problem: Dem LLM lagen im Kontext lediglich die Unterlagen des untergeordneten SCHUNK-Schnellwechselsystems (Pos. 0102, SWS/SWK 011) vor, während die Hauptzeichnung und Hauptstückliste mit dem Stäubli-Roboter fehlten. Isoliert auf den Schnellwechselkopf bezogen rieten die Modelle daher zwischen Keine der verfügbaren Klassen (R=0, T=0, Verriegelung als Hilfsfunktion), Greifer (Werkzeugklemmung als Greiffunktion gedeutet) und Rotationseinheit (4 × 90°-Anbaulagen als Drehachse fehlinterpretiert).
Revidierte GT: Roboter, Kombinierte Einheit (LLM korrekt: nein – bedingt durch unvollständigen Dokumenten-Input nur für Unterposition 0102).

## 第七部分 · Excel 第 19–20 行

来源为 `Fehler_Analyse` 工作表的三张照片。按行顺序和共同的 Ground Truth 列对应。部分模型输出列未拍全，参考同一工作簿 `Korrigierte GT&ZGT` 对应记录补录，待核对。两行其他允许类别栏均为空。

| Excel 行 | A · Error_Count | B · 表头未完整显示 | C · SAP-Nummer | D · Teamcenter | E · Register | F · Ground Truth | G · Weitere zulässige Ground Truth | claude-haiku-4-5_20251001 (image) | claude-haiku-4-5_20251001 (pdf) | claude-haiku-4-5_20251001 (text) | claude-opus-4-8 (image) | claude-opus-4-8 (pdf) | claude-opus-4-8 (text) | gemini-2.5-flash (image) | gemini-2.5-flash (pdf) | gemini-2.5-flash (text) | gemini-2.5-pro (image) | gemini-2.5-pro (pdf) | gemini-2.5-pro (text) | T · Fehleranalyse |
|---:|---:|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 19 | 4 | 0 | `0804EK1683` | `AS90152580/01` | E1 | Roboter | — | Rotationseinheit | — | — | Keine der verfügbaren Klassen | — | — | Keine der verfügbaren Klassen | — | — | Keine der verfügbaren Klassen | — | — | [原文](#excel-第-19-行) |
| 20 | 4 | 0 | `0804FT0436` | `AS90143556` | E1 | Lineareinheit | — | Kombinierte Einheit | Kombinierte Einheit | — | — | — | — | Kombinierte Einheit | — | — | Kombinierte Einheit | — | — | [原文](#excel-第-20-行) |

### Excel 第 19 行

GT vor Review: Roboter | LLM: Keine der verfügbaren Klassen / Rotationseinheit
Analyse: Eindeutiger 6-Achs-Knickarmroboter (R=6, T=0): Verbaut ist ein FANUC-Industrieroboter (Pos. 0100, LRM-200iD/7L) auf einer Grundplatte (Pos. 0001) mit SCHUNK-Schnellwechselkopf (Pos. 0101, SWK-011 / SWS 011). Wie die LLM-Begründungen belegen, liegt exakt dasselbe Dateninput-Problem wie bei 0804CC2134 vor: Dem LLM wurden im Kontext nur die Unterlagen des untergeordneten Schnellwechselsystems (SWS 011) ohne die Hauptzeichnung/Hauptstückliste des FANUC-Roboters übergeben. Isoliert auf das SWS 011 bezogen stuften drei Modelle das Bauteil folgerichtig als Hilfsfunktion ohne eigene Hauptachsen ein (R=0, T=0 → Keine der verfügbaren Klassen), während ein Modell die zylindersymmetrische Bauform samt Kolbenhubkontrolle fälschlicherweise als Rundschalttisch (R=1, T=0 → Rotationseinheit) halluzinierte.
Revidierte GT: Roboter (LLM korrekt: nein – bedingt durch fehlenden Input der Hauptbaugruppe; bewertet wurde nur Unterposition 0101).

### Excel 第 20 行

GT vor Review: Lineareinheit | LLM: Kombinierte Einheit
Analyse: Eindeutiger Fall von Grenzfall 6.1 („Greifer auf einer Hubachse“ → Lineareinheit): Verbaut ist genau eine vertikale Rexroth-Linearachse mit Motor (Stufe 6, Pos. 1, R040.563.545, Hub 455 mm → T=1), an deren Ausleger ein zylindrischer SCHUNK-Drei-Finger-Greifer (Pos. 102, PZN-plus 80) als Endeffektor montiert ist (R=0). Die LLM-Begründungen zeigen drei charakteristische Fehlermuster: (1) Das zylindrische Gehäuse des Drei-Finger-Greifers wird optisch als separate Schwenkeinheit (R=1) zwischen Hubachse und Greifbacken halluziniert; (2) die interne Keilhaken-Mechanik des PZN-plus 80-Datenblatts wird fälschlich als Hub-Schwenk-Kinematik (R=1, T=1) gedeutet; oder (3) das Modell ermittelt zwar völlig korrekt R=0, T=1 und zitiert sogar explizit Grenzfall 6.1, setzt sich aber wegen der Benennung „Handling“ sowie vorhandener Sensorik/Energiekette bewusst über die Regel hinweg.
Revidierte GT: Lineareinheit (LLM korrekt: nein).

## 第八部分 · Excel 第 21–23 行

来源为 `Fehler_Analyse` 工作表的三张照片，按行顺序及共同列对应。部分模型输出列未拍全，参考同一工作簿 `Korrigierte GT&ZGT` 对应记录补录，待核对。

| Excel 行 | A · Error_Count | B · 表头未完整显示 | C · SAP-Nummer | D · Teamcenter | E · Register | F · Ground Truth | G · Weitere zulässige Ground Truth | claude-haiku-4-5_20251001 (image) | claude-haiku-4-5_20251001 (pdf) | claude-haiku-4-5_20251001 (text) | claude-opus-4-8 (image) | claude-opus-4-8 (pdf) | claude-opus-4-8 (text) | gemini-2.5-flash (image) | gemini-2.5-flash (pdf) | gemini-2.5-flash (text) | gemini-2.5-pro (image) | gemini-2.5-pro (pdf) | gemini-2.5-pro (text) | T · Fehleranalyse |
|---:|---:|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 21 | 4 | 0 | `0804GD6171` | `AS90191800` | E1 | Roboter | — | Keine der verfügbaren Klassen | — | — | Keine der verfügbaren Klassen | — | — | Keine der verfügbaren Klassen | — | — | Keine der verfügbaren Klassen | — | — | [原文](#excel-第-21-行) |
| 22 | 3 | 0 | `0804FH4760` | `AS90308280/00` | E1 | Roboter | — | Keine der verfügbaren Klassen | — | — | Keine der verfügbaren Klassen | — | — | Keine der verfügbaren Klassen | — | — | — | — | — | [原文](#excel-第-22-行) |
| 23 | 3 | 0 | `0804HH8872` | `AS90105353` | E2 | Kombinierte Einheit | — | — | — | — | — | — | — | Gantry | Gantry | Gantry | — | — | — | [原文](#excel-第-23-行) |

### Excel 第 21 行

GT vor Review: Roboter | LLM: Keine der verfügbaren Klassen
Analyse (Dateninput-Bug): Eindeutiger 6-Achs-Knickarmroboter (R=6, T=0) von KUKA (Pos. 0100, KR10R900-2) auf einer Grundplatte (Pos. 0001) samt Greifer-Unterbaugruppe (Pos. 0002). Die Fehlklassifizierung als Keine der verfügbaren Klassen liegt an einem systematischen Dateninput-Fehler: Das LLM erhielt insgesamt 65 Bilder in 5 Batches à 15 Bildern, da für das untergeordnete SCHUNK-Schnellwechselsystem (SWS-005 in Pos. 0002) der mehrseitige Hersteller-Katalog mitextrahiert wurde. Die 1–2 Seiten der Hauptbaugruppe gingen in der Flut an SWS-Unterlagen komplett unter, weshalb das LLM fälschlicherweise nur die passive Schnittstelle isoliert bewertete (R=0, T=0 → Grenzfall 6.8).
Revidierte GT: Roboter (LLM korrekt: nein – bedingt durch unvollständigen/überfluteten Dokumenten-Input).

### Excel 第 22 行

GT vor Review: Roboter | LLM: Keine der verfügbaren Klassen
Analyse (Dateninput-Bug): Die Baugruppe ist eigentlich ein Stäubli 6-Achs-Roboter (Pos. 0100, RX160, R=6, T=0) mit montiertem Werkzeugwechsler (Pos. 0101, MPS32). Beim Datenexport wurde jedoch versehentlich das lange Hersteller-Handbuch des Werkzeugwechslers mitgeschickt. Dadurch hat das LLM die eigentliche Roboter-Hauptzeichnung übersehen und nur den passiven Werkzeugwechsler bewertet (R=0, T=0 → Grenzfall 6.8, gleicher Bug wie bei 0804GD6171).
Revidierte GT: Roboter (LLM korrekt: nein – Roboter-Zeichnung ging im Handbuch des Anbauteils unter).

### Excel 第 23 行

GT vor Review: Kombinierte Einheit (Umsetzeinheit) | LLM: Gantry
Analyse (Ausleger als Portalstruktur fehlinterpretiert): Die Baugruppe besteht aus zwei horizontalen Linearachsen (R=0, T=2: X-Achse Pos. 0100 und Y-Achse Pos. 0104). Es ist jedoch ein einseitig geführtes Auslegersystem (Grenzfall 6.4) und kein Gantry: Die obere Y-Achse ist nur einseitig am Schlitten der einzelnen X-Achse montiert und ragt frei aus. Das LLM begeht zwei Fehler: Erstens verwechselt es die Abstützung der einzelnen X-Achse auf zwei Standprofilen (Pos. 0102) mit einer beidseitigen Portalführung der Y-Achse (Gantry-Kriterium c verletzt, analog zu 0804306221). Zweitens zählt es fälschlicherweise den Frequenzumrichter (Pos. 0108, R030529477) als dritte Linearachse (T=3).
Revidierte GT: Kombinierte Einheit / Umsetzeinheit (LLM korrekt: nein – Auslegerbauweise mit Portalführung verwechselt, Kriterium c verletzt).


## 第九部分 · Excel 第 24–26 行

来源为 `Fehler_Analyse` 工作表照片，按行顺序及共同列对应。未拍全的模型输出参考同一工作簿 `Korrigierte GT&ZGT` 对应记录补录，待核对。第 26 行的 G 列在本次照片中为空；已整理的修正表中该项为 Kombinierte Einheit，两者可能反映修正前后状态，保留此差异。

| Excel 行 | A · Error_Count | B · 表头未完整显示 | C · SAP-Nummer | D · Teamcenter | E · Register | F · Ground Truth | G · Weitere zulässige Ground Truth（照片） | claude-haiku-4-5_20251001 (image) | claude-haiku-4-5_20251001 (pdf) | claude-haiku-4-5_20251001 (text) | claude-opus-4-8 (image) | claude-opus-4-8 (pdf) | claude-opus-4-8 (text) | gemini-2.5-flash (image) | gemini-2.5-flash (pdf) | gemini-2.5-flash (text) | gemini-2.5-pro (image) | gemini-2.5-pro (pdf) | gemini-2.5-pro (text) | T · Fehleranalyse |
|---:|---:|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 24 | 3 | 0 | `0804HX0679` | `AS90052795/01` | E2 | Rotationseinheit | — | — | — | — | Kombinierte Einheit | — | — | Kombinierte Einheit | — | — | Kombinierte Einheit | — | — | [原文](#excel-第-24-行) |
| 25 | 3 | 0 | `0804KE7723` | `AS00115515` | E1 | Multi-Achs-System (Gantry) | — | Kombinierte Einheit | — | Kombinierte Einheit | — | — | Kombinierte Einheit | — | — | — | — | — | — | [原文](#excel-第-25-行) |
| 26 | 3 | 0 | `0804KY7178` | `AS00217781` | E1 | Lineareinheit | — | — | `[EMPTY]` | — | — | — | — | — | — | Kombinierte Einheit | — | — | Kombinierte Einheit | [原文](#excel-第-26-行) |

### Excel 第 24 行

GT vor Review: Rotationseinheit | LLM: Kombinierte Einheit (Umsetzeinheit)
Analyse (Vertikaler Zahnriemenantrieb als Hubachse fehlinterpretiert): Die Baugruppe ist eine reine Rotationseinheit (R=1, T=0, Klasse 6): Der oben an einer statischen Standsäule (Pos. 0105) montierte Servomotor (Pos. 0109) treibt über einen vertikal verlaufenden Zahnriemen (Pos. 0114) lediglich die untere Schwenkachse mit den zwei Parallelgreifern an. Es gibt keine vertikale Hubbewegung. Das LLM hat die Kombination aus vertikaler Säule, obenliegendem Motor und Zahnriementrieb optisch als „vertikale Hubachse (T=1)“ halluziniert und die Baugruppe daher fälschlicherweise als Hub-Schwenk-Einheit (Grenzfall 6.3, R=1, T=1 → Kombinierte Einheit) eingestuft.
Revidierte GT: Rotationseinheit (LLM korrekt: nein – statische Säule mit vertikalem Zahnriementrieb fälschlicherweise als Hubachse T=1 gedeutet).

### Excel 第 25 行

GT vor Review: Multi-Achs-System (Gantry) | LLM: Kombinierte Einheit (Umsetzeinheit)
Analyse (Irreführung durch 9-seitigen Angebotstext): Eindeutiges 3-Achs-Portal (Gantry, R=0, T=3): Zwei parallele X-Achsen (Pos. 20/30, 2x MKR-110) führen beidseitig die Y-Brücke (Pos. 60, CKK-145) samt vertikaler Z-Achse (Pos. 80, CKK-145). Da dem LLM zusätzlich ein 9-seitiges Rexroth-Textangebot übergeben wurde, ging die 1-seitige Hauptzeichnung (DR00218359) unter. Im Angebot erkennt das LLM zwar die zwei parallelen X-Achsen und R=0, T=3, deutet aber den 2964 mm langen Portal-Brückenträger (Pos. 50) allein wegen seiner Benennung als Sonderverbindungswinkel fälschlicherweise als einseitigen Ausleger (Grenzfall 6.4) und verneint Kriterium (c).
Revidierte GT: Gantry (LLM korrekt: nein – durch 9-seitiges Angebot abgelenkt und Brückenträger Pos. 50 als Auslegerwinkel fehlinterpretiert).

### Excel 第 26 行

Grenzfall: Sperrzylinder Pos. 0101 auch als zweite Hauptachse interpretierbar. Die Baugruppe (Ausheber) besitzt neben dem vertikalen Hubzylinder (Pos. 0100, T₁=1) einen horizontalen Kompaktzylinder (Pos. 0101), der einen Schieber (Pos. 0013, pusher / Schieber) betätigt. Laut Schnitt A-A dient dieser intern als mechanische Verriegelung der Hubwelle (Hilfsfunktion zählt nicht → R=0, T=1, Lineareinheit); wegen der Benennung pusher ist er jedoch auch als zweite Linearachse (R=0, T=2 → Kombinierte Einheit) interpretierbar.
Revidierte GT: Lineareinheit, Kombinierte Einheit (LLM korrekt: ja – wegen der Doppelfunktion von Zylinder Pos. 0101 als Verriegelung bzw. Pusher sind beide Labels vertretbar).


## 第十部分 · Excel 第 27–29 行

来源为 `Fehler_Analyse` 工作表照片，按行顺序及共同列对应。未拍全的模型输出参考已整理的 `Korrigierte GT&ZGT` 对应记录补录，待核对。第 27、29 行的 G 列在本次照片中为空；修正表分别记录 Kombinierte Einheit、Keine der verfügbaren Klassen，错误分析中的修订结论也列出这些允许类别。

| Excel 行 | A · Error_Count | B · 表头未完整显示 | C · SAP-Nummer | D · Teamcenter | E · Register | F · Ground Truth | G · Weitere zulässige Ground Truth（照片） | claude-haiku-4-5_20251001 (image) | claude-haiku-4-5_20251001 (pdf) | claude-haiku-4-5_20251001 (text) | claude-opus-4-8 (image) | claude-opus-4-8 (pdf) | claude-opus-4-8 (text) | gemini-2.5-flash (image) | gemini-2.5-flash (pdf) | gemini-2.5-flash (text) | gemini-2.5-pro (image) | gemini-2.5-pro (pdf) | gemini-2.5-pro (text) | T · Fehleranalyse |
|---:|---:|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 27 | 3 | 0 | `0804KZ9027` | `AS00231844` | E1 | Lineareinheit | — | — | — | — | — | — | — | Kombinierte Einheit | — | — | Kombinierte Einheit | — | Kombinierte Einheit | [原文](#excel-第-27-行) |
| 28 | 2 | 0 | `0804AR3766` | `AS90165357/00` | M | Rotationseinheit | Greifer | — | — | — | — | Kombinierte Einheit | Kombinierte Einheit | — | — | — | — | — | — | [原文](#excel-第-28-行) |
| 29 | 2 | 0 | `0804DT6452` | `AS90466020` | E1 | Multi-Achs-System (Gantry) | — | — | — | — | — | — | Keine der verfügbaren Klassen | — | — | — | — | — | Keine der verfügbaren Klassen | [原文](#excel-第-29-行) |

### Excel 第 27 行

GT vor Review: Lineareinheit | LLM: Kombinierte Einheit (Umsetzeinheit)
Analyse (Vertretbarer Grenzfall Haupt- vs. Hilfsfunktion): Die Baugruppe (lifter / Ausheber) besitzt zwei orthogonal angeordnete Pneumatikzylinder: Pos. 0100 (Ø 32, Hub 125 mm) für den vertikalen Hub und Pos. 0103 (Ø 16, Hub 20 mm) für den horizontalen Schieber (Pos. 0013 pusher / Schieber). Wertet man den kleinen Querzylinder als reine Verriegelungs-/Hilfsfunktion (Abschnitt 3: nicht mitzählen), ergibt sich R=0, T=1 → Lineareinheit. Da aus den Unterlagen jedoch nicht eindeutig hervorgeht, ob der Schieber nur verriegelt oder aktiv zum Hauptbewegungsablauf gehört, ist die Argumentation des LLM (Pos. 100 + Pos. 103 als zwei unabhängige Linearachsen → R=0, T=2, Gantry-Test negativ wegen nur einer Horizontalachse → Kombinierte Einheit) vollkommen schlüssig.
Revidierte GT: Lineareinheit, Kombinierte Einheit (Umsetzeinheit) (LLM korrekt: ja – plausibler Grenzfall bei der Einordnung des zweiten Zylinders Pos. 0103).

### Excel 第 28 行

GT vor Review: Rotationseinheit, Greifer | LLM: Kombinierte Einheit (Umsetzeinheit)
Analyse (Greifer-Fingerhub als Hubachse missverstanden): Die Baugruppe ist eine reine Rotationseinheit (R=1, T=0, Klasse 6), basierend auf einer SMC Greiferdreheinheit (Pos. 0100, Typ MRHQ16D), die eine 90°-Schwenkbewegung ausführt (R=1). Das LLM begeht im Reasoning einen klaren Zählfehler: Es liest den „Fingerhub“ (die Schließbewegung der Greifbacken von 3 mm) aus dem Datenblatt aus und interpretiert diesen fälschlicherweise als aktive, translatorische Hubachse (T=1). Dadurch wendet es fälschlicherweise den Grenzfall 6.3 (Hub-Schwenk-Einheit) an. Nach Codebook Abschnitt 3 dürfen die Aktoren innerhalb eines Greifers für die Greifbewegung jedoch nicht als translatorische Hauptachsen mitgezählt werden (T=0).
Revidierte GT: Rotationseinheit, Greifer (LLM korrekt: nein – Fingerhub der Greiferdreheinheit fälschlicherweise als Haupt-Hubachse T=1 gewertet und fälschlich Grenzfall 6.3 angewendet).

### Excel 第 29 行

GT vor Review: Multi-Achs-System (Gantry) | LLM: Keine der verfügbaren Klassen
Analyse (Widerspruch zwischen 3D-CAD und Stückliste): Im 3D-CAD ist ein komplettes Portal (Gantry) samt Motoren sichtbar, weshalb die ursprüngliche GT Gantry lautet. In der 2D-Zeichnung sind die Achsen jedoch nur als Referenzgeometrie (Strich-Zweipunkt-Linien) angedeutet, und die Stückliste (machining parts and hardware for gantry system) enthält ausschließlich das passive Montagegestell (Alu-Profile Pos. 0001, Auflagebleche Pos. 0002–0007, Schrauben; R=0, T=0). Da 3D-Modell und Stückliste widersprüchlich sind, sind sowohl Gantry als auch Keine der verfügbaren Klassen (Schritt S1 / Grenzfall 6.8) vertretbar (analog zu 0804KW8391).
Revidierte GT: Gantry, Keine der verfügbaren Klassen (LLM korrekt: ja – wegen Diskrepanz zwischen 3D-Ansicht und Stückliste sind beide Labels korrekt).


## 第十一部分 · Excel 第 30–34 行

来源为 `Fehler_Analyse` 工作表照片，按行顺序及共同列对应。未拍全的模型输出参考已整理的 `Korrigierte GT&ZGT` 对应记录补录，待核对。`—` 表示来源中为空，不等同于明确显示的 `[EMPTY]`。第 31 行黄色高亮，T 列照片中为空；第 34 行的错误分析被照片下边缘截断，以下只记录可见文字。

| Excel 行 | A · Error_Count | B · 表头未完整显示 | C · SAP-Nummer | D · Teamcenter | E · Register | F · Ground Truth | G · Weitere zulässige Ground Truth | claude-haiku-4-5_20251001 (image) | claude-haiku-4-5_20251001 (pdf) | claude-haiku-4-5_20251001 (text) | claude-opus-4-8 (image) | claude-opus-4-8 (pdf) | claude-opus-4-8 (text) | gemini-2.5-flash (image) | gemini-2.5-flash (pdf) | gemini-2.5-flash (text) | gemini-2.5-pro (image) | gemini-2.5-pro (pdf) | gemini-2.5-pro (text) | T · Fehleranalyse |
|---:|---:|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 30 | 2 | 0 | `0804KB7256` | `AS00097350` | E2 | Rotationseinheit | — | — | — | — | Kombinierte Einheit | — | — | — | — | — | Kombinierte Einheit | — | — | [原文](#excel-第-30-行) |
| 31 | 2 | 0 | `0804KU2401` | `AS00177443` | E1 | Lineareinheit | — | — | `[EMPTY]` | — | — | — | — | — | `[EMPTY]` | — | — | — | — | 空白（黄色高亮） |
| 32 | 2 | 0 | `0804KY7179` | `AS00221603` | E1 | Lineareinheit | — | Kombinierte Einheit | `[EMPTY]` | — | — | — | — | — | — | — | — | — | — | [原文](#excel-第-32-行) |
| 33 | 2 | 0 | `0804KZ9488` | `AS00231836` | E2 | Kombinierte Einheit | — | Rotationseinheit | — | — | — | — | — | Rotationseinheit | — | — | — | — | — | [原文](#excel-第-33-行) |
| 34 | 2 | 0 | `0804LA7293` | `AS00242009` | E2 | Kombinierte Einheit | — | Greifer | — | — | — | — | — | Greifer | — | — | — | — | — | [原文](#excel-第-34-行) |

### Excel 第 30 行

GT vor Review: Rotationseinheit | LLM: Kombinierte Einheit
Analyse (Visuelle Fehlinterpretation der 2D-Zeichnung): Die Baugruppe besteht nur aus einem Servomotor (Pos. 0100), der über eine gelagerte Welle (Pos. 0002, 0105) einen Drei-Finger-Greifer (Pos. 0108, Endeffektor zählt nicht) dreht (R=1, T=0 → Rotationseinheit). Wegen der vertikalen 2D-Darstellung hat das LLM jedoch den Servomotor (Pos. 100) samt Stangen (Pos. 020) fälschlicherweise als vertikalen Hubzylinder (T=1) und die Flanschplatte (Pos. 001) als Drehantrieb interpretiert. Ein Linearaktor existiert nicht; die Einstufung als Hub-Schwenk-Einheit (R=1, T=1, Grenzfall 6.3) ist ein reiner Ablesefehler.
Revidierte GT: Rotationseinheit (LLM korrekt: nein – Servomotor Pos. 100 wurde in der 2D-Zeichnung als Hubzylinder T=1 fehlinterpretiert).

### Excel 第 32 行

GT vor Review: Lineareinheit | LLM: Kombinierte Einheit
Analyse (Visuelle Halluzination einer Schwenkachse): Die Baugruppe (lifter / Ausheber) besitzt nur einen vertikalen Pneumatikzylinder (Pos. 0100, Festo DSBC-40-80, R=0, T=1) mit zwei passiven Führungsstangen (Pos. 0002, 0006 → Lineareinheit). Im 3D-Bild hat das LLM jedoch die Führungsstangen als zwei Zylinder gedeutet und ein rötliches Anbauteil (Rückschlagventil Pos. 0103 bzw. Kupplung Pos. 0003/0004) fälschlicherweise als „Schwenkplatte mit Drehgelenk“ (R=1, Grenzfall 6.3) halluziniert. Ein Drehantrieb existiert nicht.
Revidierte GT: Lineareinheit (LLM korrekt: nein – rötliches Anbauteil wurde im 3D-Modell als Rotationsachse R=1 halluziniert).

### Excel 第 33 行

GT vor Review: Kombinierte Einheit | LLM: Rotationseinheit
Analyse (Dateninput-Bug): Die Baugruppe besteht aus einem Linearmodul (Pos. 0100, T=1), einer Schwenkeinheit (Pos. 0101, Schunk SRU-plus) und einer Greiferdreheinheit (Pos. 0102, R ≥ 1 → Kombinierte Einheit, Grenzfall 6.3). Da beim Export das Hersteller-Datenblatt der Schwenkeinheit (SRU-plus) mitgeschickt wurde, hat das LLM die Hauptzeichnung samt Linearmodul übersehen und nur das Unterbauteil Pos. 0101 (R=1, T=0) bewertet (analog zu 0804FH4760).
Revidierte GT: Kombinierte Einheit (LLM korrekt: nein – Hauptzeichnung ging im Datenblatt des Unterbauteils Pos. 0101 unter).

### Excel 第 34 行

GT vor Review: Kombinierte Einheit | LLM: Greifer
Analyse (Fehlinterpretation der 2D-Endlagenansichten): Die Baugruppe besteht aus einem Linearmodul (Pos. 0100, T=1), einer 180°-Schwenkeinheit (Pos. 0105, R=1) und einem Parallelgreifer (Pos. 0106 → Kombinierte Einheit, Grenzfall 6.3). Da die 2D-Zeichnung dieselbe Einheit zweimal in ihren beiden Endlagen zeigt, hat das LLM dies als „zwei Greifer“ missverstanden und die Hauptaktoren (Pos. 0100, 0105) fälschlicherweise als bloßen Greifbackenantrieb (R=0, T=0) gewertet.
Revidierte GT: Kombinierte Einheit (LLM korrekt: nein – Linearmodul Pos. 0100 und Schwenkeinheit Pos. 0105 wurden als Greifbackenantrieb fehlinterpretiert).


## 第十二部分 · Excel 第 35–37 行

来源为 `Fehler_Analyse` 工作表照片，按行顺序及共同列对应。未拍全的模型输出参考已整理的 `Korrigierte GT&ZGT` 对应记录补录，待核对。`—` 表示来源中为空，不等同于明确显示的 `[EMPTY]`。第 36 行黄色高亮，照片中 T 列为空。

| Excel 行 | A · Error_Count | B · 表头未完整显示 | C · SAP-Nummer | D · Teamcenter | E · Register | F · Ground Truth | G · Weitere zulässige Ground Truth | claude-haiku-4-5_20251001 (image) | claude-haiku-4-5_20251001 (pdf) | claude-haiku-4-5_20251001 (text) | claude-opus-4-8 (image) | claude-opus-4-8 (pdf) | claude-opus-4-8 (text) | gemini-2.5-flash (image) | gemini-2.5-flash (pdf) | gemini-2.5-flash (text) | gemini-2.5-pro (image) | gemini-2.5-pro (pdf) | gemini-2.5-pro (text) | T · Fehleranalyse |
|---:|---:|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 35 | 2 | 0 | `0804LH9239` | `AS00306708` | E1 | Keine der verfügbaren Klassen | — | Kombinierte Einheit | Lineareinheit | — | — | — | — | — | — | — | — | — | — | [原文](#excel-第-35-行) |
| 36 | 1 | 0 | `0804AF9667` | `AS90134089` | M | Multi-Achs-System (Gantry) | Kombinierte Einheit | — | `[EMPTY]` | — | — | — | — | — | — | — | — | — | — | 空白（黄色高亮） |
| 37 | 1 | 0 | `0804AY8008` | `AS90102714` | E2 | Kombinierte Einheit | — | Gantry | — | — | — | — | — | — | — | — | — | — | — | [原文](#excel-第-37-行) |

### Excel 第 35 行

GT vor Review: Keine der verfügbaren Klassen | LLM: Kombinierte Einheit / Lineareinheit
Analyse (Fehlinterpretation passiver Bauteile als Aktoren): Die Baugruppe (Bedienpultbefestigung) ist ein rein passiver HMI-Haltearm aus Alu-Profilen (Pos. 0101, 0102), Lagerböcken (Pos. 0100) und Zylinderschrauben (Pos. 0200). Ohne Aktoren und Handhabungsfunktion (R=0, T=0) greift Schritt S1 bzw. Grenzfall 6.8 (Keine der verfügbaren Klassen). Die LLMs haben passive Teile wie Schrauben (Pos. 0200), Alu-Profile und Lagerböcke fälschlicherweise als Hub-, Linear- bzw. Schwenkaktoren (T ≥ 1, R=1) gewertet.
Revidierte GT: Keine der verfügbaren Klassen (LLM korrekt: nein – passive Halterung ohne Aktoren; Schrauben und Alu-Profile wurden als Antriebe fehlinterpretiert).

### Excel 第 37 行

GT vor Review: Kombinierte Einheit | LLM: Gantry
Analyse (Halluzination einer zweiten Horizontalachse / Übersehen des Drehaktors): Die Baugruppe ist ein X/Z-Portal auf zwei festen Standfüßen (Pos. 0017), bestehend aus einer einzigen Horizontalachse (Pos. 0100, AFAG Portalmodul PMP, T₁=1), einem Vertikalschlitten (Pos. 0101, SMC MXQ16-100, T₂=1) und einem 180°-Drehgreifer (Pos. 0102, SMC MRHQ20C-180S, R=1 → Kombinierte Einheit). Getäuscht durch die beiden Standfüße und die Benennung Portalmodul hat das LLM eine nicht existente Y-Achse sowie beidseitige Führungen halluziniert (Verstoß gegen Gantry-Kriterium b, Grenzfall 6.6: X/Z-Portal) und zudem die Rotationsachse Pos. 0102 (R=1) übersehen.
Revidierte GT: Kombinierte Einheit (LLM korrekt: nein – nur eine Horizontalachse (X/Z-Portal, Grenzfall 6.6) plus Drehaktor Pos. 0102, R=1, T=2).


## 第十三部分 · Excel 第 38–40 行

来源为 `Fehler_Analyse` 工作表照片：A–G 列和 H–K 列可见；G、H–K 列均为空。L–S 列未拍到，按 SAP 和 Teamcenter 编号参考 `corrected_gt_zgt_error_records.md` 中 `Korrigierte GT&ZGT` 的对应记录补录，尚待与本工作表核对。`—` 表示对应来源中为空，不等同于明确显示的 `[EMPTY]`，也不能仅据此推断模型没有输出。T 列错误分析依据用户随后提供的文字补录；按 Ground Truth、模型类别和原有行顺序匹配，文字中未包含 SAP 或 Teamcenter 编号，待原照片进一步核对。第 40 行“×/Y/Z”按用户提供的文字保留，待核对。

| Excel 行 | A · Error_Count | B · 表头未完整显示 | C · SAP-Nummer | D · Teamcenter | E · Register | F · Ground Truth | G · Weitere zulässige Ground Truth | claude-haiku-4-5_20251001 (image) | claude-haiku-4-5_20251001 (pdf) | claude-haiku-4-5_20251001 (text) | claude-opus-4-8 (image) | claude-opus-4-8 (pdf) | claude-opus-4-8 (text) | gemini-2.5-flash (image) | gemini-2.5-flash (pdf) | gemini-2.5-flash (text) | gemini-2.5-pro (image) | gemini-2.5-pro (pdf) | gemini-2.5-pro (text) | T · Fehleranalyse |
|---:|---:|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 38 | 1 | 0 | `0804CE5532` | `AS90000201` | E2 | Kombinierte Einheit | — | — | — | — | — | — | — | — | Lineareinheit | — | — | — | — | [原文](#excel-第-38-行) |
| 39 | 1 | 0 | `0804EV7706` | `AS90158200/01` | E1 | Roboter | — | — | — | — | — | — | Kombinierte Einheit | — | — | — | — | — | — | [原文](#excel-第-39-行) |
| 40 | 1 | 0 | `0804FK2694` | `AS90037183` | E2 | Multi-Achs-System (Gantry) | — | — | — | — | — | — | — | Kombinierte Einheit | — | — | — | — | — | [原文](#excel-第-40-行) |


### Excel 第 38 行

GT vor Review: Kombinierte Einheit | LLM: Lineareinheit
Analyse (Fälschliche Zusammenfassung zweier orthogonaler Linearachsen zu T=1): Die Baugruppe (Handling) ist ein X/Z-Zweiachssystem aus einem horizontalen Schlitzzylinder (Pos. 0100, Hub 300 mm, T1=1), einem orthogonal daran montierten vertikalen Kompaktschlitten (Pos. 0105, Hub 100 mm, T2=1) und einem Parallelgreifer (Pos. 0106 → R=0, T=2, Kombinierte Einheit nach Grenzfall 6.6). Das LLM hat zwar beide Linearaktoren (Pos. 0100 und 0105) in der Stückliste erkannt, deren orthogonale Einbaulage (horizontal + vertikal) jedoch übersehen und sie fälschlicherweise zu einer einzigen vertikalen
Hubachse (T=1) zusammengefasst.
Revidierte GT: Kombinierte Einheit (LLM korrekt: nein - die orthogonalen Achsen Pos. 0100 und Pos.
0105 wurden fälschlicherweise als eine einzige Achse T=1 gezählt).

### Excel 第 39 行

GT vor Review: Roboter LLM: Kombinierte Einheit
Analyse (Verstoß gegen Zählregel für Endeffektoren): Die Baugruppe (robot unit) besteht aus einem 6-Achs-Knickarmroboter (Pos. 0104, KUKA, R=6, T=0) und einem am Flansch montierten Doppel-Vakuumgreifer (Unterbaugruppen Pos. 0001-0003). Obwohl das LLM die beiden pneumatischen Kompaktschlitten (Pos. 0104 in den Unterbaugruppen, R412.019.211, Hub 20 mm) explizit als Teil der Endeffektoren erkannt hat, hat es diese entgegen Abschnitt 3 (wonach Aktoren innerhalb von Endeffektoren/Greifern nicht mitzählen) fälschlicherweise als zusätzliche Hauptachsen (T ≥ 1) gewertet.
Revidierte GT: Roboter (LLM korrekt: nein - Kompaktschlitten innerhalb des Endeffektors wurden regelwidrig als Hauptachse T ≥ 1 mitgezählt).

### Excel 第 40 行

GT vor Review: Multi-Achs-System (Gantry) | LLM: Kombinierte Einheit
Analyse (Fehlbeurteilung des Gantry-Tests / Beidseitige Führung übersehen): Die Baugruppe (gantry / Portal) ist ein ×/Y/Z-Flächenportal (R=0, T=3) auf einem Portalgestell (Pos. 0001). Entgegen der Annahme des LLMs ist Gantry-Kriterium (c) eindeutig erfüllt: Die horizontale Basisachse wird beidseitig über zwei parallele Linearmodule geführt (Pos. 0002 mit Achsen Pos. 107/108 sowie Pos. 0005 mit Verbindungswelle Pos. 120 und Achsen Pos. 124/125). Das LLM ließ sich durch die Benennung der Querachse (Pick and Place links X-Achse Pos. 105) verwirren und hat die Brückenlagerung fälschlicherweise verneint.
Revidierte GT: Gantry (LLM korrekt: nein - Gantry-Kriterium c ist durch die parallelen Basisachsen Pos.
107/108 bzw. 124/125 erfüllt).


## 第十四部分 · Excel 第 41–43 行（待照片核对）

Excel 行号及 SAP、Teamcenter 编号由用户按顺序提供；编号配对与 `corrected_gt_zgt_error_records.md` 一致。以下 Register、Ground Truth、其他允许类别和模型列为修正表记录，尚未通过 `Fehler_Analyse` 工作表照片核对，不能视为该工作表对应字段已确认。修正表记录 SAP `0804FU6515` 对应黄色高亮，尚待核对本工作表的行颜色。A、B 列等待照片；第 41、43 行错误分析按用户提供的文字原样补录，第 42 行错误分析据用户说明为空。用户文字中的 `Tz=1` 和 `R=O, T=O` 保留原样，待核对；`—` 表示修正表来源为空，不等同于 `[EMPTY]`，不能据此推断模型未输出。

| Excel 行 | SAP-Nummer | Teamcenter | 修正表 Register | 修正表 Ground Truth | 修正表其他允许类别 | 修正表非空模型记录 | Fehleranalyse |
|---:|---|---|---|---|---|---|---|
| 41 | `0804FT6844` | `AS90412772` | E2 | Kombinierte Einheit | — | claude-haiku-4-5_20251001 (image): Lineareinheit | [原文](#excel-第-41-行) |
| 42 | `0804FU6515` | `AS90303031` | E2 | Kombinierte Einheit | — | gemini-2.5-flash (image): `[EMPTY]` | 空白（用户确认） |
| 43 | `0804GA4441` | `AS90245290` | E1 | Keine der verfügbaren Klassen | — | claude-haiku-4-5_20251001 (pdf): Kombinierte Einheit | [原文](#excel-第-43-行) |


### Excel 第 41 行

GT vor Review: Kombinierte Einheit LLM: Lineareinheit
Analyse (Variante 1 - Übersehene zweite Linearachse): Die Baugruppe ist ein zweiachsiges X/Z-Auslegersystem aus einer vertikalen Schlitteneinheit (Pos. 0101, Festo, Hub 200 mm, T1=1), einer orthogonal dazu montierten horizontalen Schlitteneinheit (Pos. 0105, Festo, Hub 150 mm, Tz=1) und einem Parallelgreifer mit Absaugstutzen (Pos. 0100, Schunk, Endeffektor zählt nicht). Da zwei orthogonale Linearachsen ohne Portalstruktur bzw. zweite Horizontalachse vorliegen (R=0, T=2, Gantry-Kriterien b und c verletzt, Grenzfall 6.4/6.6), gehört die Baugruppe eindeutig zur Klasse Kombinierte Einheit (genau wie das Schwesterbauteil 0804MB2849). Das LLM hat eine der beiden Schlitteneinheiten
(Pos. 0101 oder 0105) übersehen und fälschlicherweise T=1 angenommen.
Analyse (Variante 2 - Dateninput-Bug / Katalogblatt überlagert Hauptzeichnung): Da beim Export das Hersteller-Datenblatt des Festo-Minischlittens (Mini slides DGSL) mitgeschickt wurde, hat das LLM die eigentliche Hauptbaugruppe samt Greifer und zweiter Achse übersehen und ausschließlich einen einzelnen Katalog-Schlitten (R=0, T=1) bewertet (analog zu 0804FH4760).
Revidierte GT: Kombinierte Einheit (LLM korrekt: nein - zweite Schlitteneinheit übersehen bzw.
Hauptzeichnung ging im Festo-DGSL-Datenblatt unter).

### Excel 第 43 行

GT vor Review: Keine der verfügbaren Klassen | LLM: Kombinierte Einheit
Analyse (Passiver HMI-Tragarm als Aktorik fehlinterpretiert): Die Baugruppe (control panel fixing) ist ein rein passiver Bedienpult-Tragarm ohne Aktoren (R=0, T=0 → Keine der verfügbaren Klassen, Grenzfall 6.8, analog zu 0804LH9239). Das LLM hat das vertikale Tragprofil (Pos. 0002/0901) fälschlicherweise als Hubzylinder (T=1) und die manuell drehbare Kupplung (Pos. 0104, 0-320deg rotable) als Drehaktor (R=1) gewertet.
Revidierte GT: Keine der verfügbaren Klassen (LLM korrekt: nein - passiver HMI-Tragarm ohne Aktoren,
R=O, T=O).


## 第十五部分 · Excel 第 44–47 行（待照片核对）

行号、SAP、Teamcenter 及下表注明的字段由用户提供；编号配对均与 `corrected_gt_zgt_error_records.md` 一致。第 44 行 Ground Truth 用户提供为截断的 `Kombinierte Ei`；完整名称仅按修正表记录。第 47 行 Register 未提供，其 SAP 编号前的 `0` 所属列未确认。修正表记录该装配体黄色高亮，仍需核对 `Fehler_Analyse` 工作表行颜色。以下修正表的其他允许类别及模型记录尚未通过本工作表照片核对；空白与 `[EMPTY]` 不混同。第 44–46 行错误分析按用户文字补录，第 47 行错误分析据用户说明为空；用户提供的 `R-0` 和 `T-1` 原样保留，待核对。用户文字开头的 `gemini-2.5-pro (text)` 为表头，未据此推断该列的单元格内容。

| Excel 行 | SAP-Nummer | Teamcenter | 用户提供 Register | 用户提供 Ground Truth | 修正表 Register / Ground Truth | 修正表其他允许类别 | 修正表非空模型记录 | Fehleranalyse |
|---:|---|---|---|---|---|---|---|---|
| 44 | `0804GY2577` | `AS90283974` | E2 | Kombinierte Ei（截断） | E2 / Kombinierte Einheit | — | claude-haiku-4-5_20251001 (image): Rotationseinheit | [原文](#excel-第-44-行) |
| 45 | `0804GZ3046` | `AS90390673/00` | E1 | Rotationseinheit | E1 / Rotationseinheit | — | claude-opus-4-8 (image): Kombinierte Einheit | [原文](#excel-第-45-行) |
| 46 | `0804JL5526` | `AS00016496` | E2 | Lineareinheit | E2 / Lineareinheit | Keine der verfügbaren Klassen | claude-haiku-4-5_20251001 (image): Keine der verfügbaren Klassen | [原文](#excel-第-46-行) |
| 47 | `0804JU56371` | `AS00049479` | 未提供 | Roboter | M / Roboter | Kombinierte Einheit | gemini-2.5-flash (pdf): `[EMPTY]` | 空白（用户确认） |


### Excel 第 44 行

GT vor Review: Kombinierte Einheit | LLM: Rotationseinheit
Analyse (Übersehene Hubachse / Irreführende Bauteilbenennung): Trotz der Benennung turning unit / Wendeeinheit handelt es sich um eine Hub-Schwenk-Einheit (R=1, T=1 → Kombinierte Einheit, Grenzfall 6.3), bei der ein vertikaler Pneumatikzylinder (Pos. 0110, Festo ADN-32-120, T=1) eine 180°-Schwenkeinheit (Pos. 0112, Festo DRRD-25-180, R=1) samt Parallelgreifer (Pos. 0102) anhebt. Das LLM ließ sich vom Namen täuschen, hat eine „zylindrische Arbeitsplattform mit vertikaler Drehachse" halluziniert und sowohl den Hubzylinder (Pos. 0110) als auch den Greifer (Pos. 0102) komplett übersehen.
Revidierte GT: Kombinierte Einheit (LLM korrekt: nein - vertikaler Hubzylinder Pos. 0110 wurde
übersehen, R=1, T=1).

### Excel 第 45 行

GT vor Review: Rotationseinheit | LLM: Kombinierte Einheit
Analyse (Gefederte Werkstücknester auf Rundtisch als T=1 fehlinterpretiert): Die Baugruppe (rotation unit) ist ein Rundtisch (RT2 mit Teller, R=1, T=0 → Rotationseinheit, Grenzfall 6.2) mit vier Werkstückaufnahmen (Produktnest / swivel fixture) und Fixiergreifern. Das LLM hat die passiven Führungssäulen (GUIDE PILLAR) und Druckfedern (pressure springs) der Werkstücknester fälschlicherweise als aktive translatorische Hubachse (T=1) gewertet.
Revidierte GT: Rotationseinheit (LLM korrekt: nein - passive Führungssäulen und Federn der Produktnester wurden als Hubachse T=1 fehlinterpretiert).

### Excel 第 46 行

GT vor Review: Lineareinheit | LLM: Keine der verfügbaren Klassen
Analyse (Grenzfall zwischen linearer Positioniereinheit und Messfunktion nach S1): Die Baugruppe (Sensor / PowerMeter) besteht laut Stückliste im Kern aus einem pneumatischen Kompaktschlitten
(Pos. 0100, Aventics MSC-MG-HM, Hub 100 mm, R=0, T=1), der das in der 2D-Zeichnung nur als Referenzgeometrie angedeutete Messgerät (3843AY6685) linear verfährt (→ Lineareinheit). Das LLM hat den Minischlitten (R-0, T=1) zwar korrekt erkannt, die übergeordnete Hauptfunktion wegen des im 3D-CAD sichtbaren PowerMeters und der Benennung Sensor jedoch als „Messen/Prüfen" eingestuft und gemäß Schritt S1 ausgeschlossen. Da im Codebook sowohl die Einstufung als lineare Positioniereinheit eines Messkopfs als auch der Ausschluss als Messapplikation (S1) gut begründbar sind, sind beide
Labels vertretbar.
Revidierte GT: Lineareinheit, Keine der verfügbaren Klassen (LLM korrekt: ja - sowohl die Einstufung als lineare Zustelleinheit T-1 als auch der Ausschluss als Messbaugruppe nach S1 sind vertretbar).


## 第十六部分 · Excel 第 48–51 行（待照片核对）

以下编号配对与 `corrected_gt_zgt_error_records.md` 一致。第 48、49 行根据用户给出的顺序匹配；第 50、51 行的文字次序交错，暂参考修正表顺序匹配，行号须由照片确认。用户提供的 0、1 未能可靠归属到具体行和列，暂不填写。Register E1 为用户提供；Ground Truth 和模型信息来自修正表，尚未与本工作表核对。修正表标记 `0804KT1289` 为黄色高亮；本工作表的颜色待确认。`—` 与明确标记的 `[EMPTY]` 不等同。第 48–50 行错误分析按用户提供的文字原样补录，第 51 行据用户说明为空；第 48 行的 `R-0` 和第 49 行的 `T,=1` 原样保留，待核对。

| Excel 行 | SAP-Nummer | Teamcenter | Register（用户提供） | Ground Truth（修正表） | 其他允许类别（修正表） | 非空模型记录（修正表） | Fehleranalyse |
|---:|---|---|---|---|---|---|---|
| 48 | `0804KK0664` | `AS00127924` | E1 | Greifer | — | gemini-2.5-flash (pdf): Kombinierte Einheit | [原文](#excel-第-48-行) |
| 49 | `0804KM8175` | `AS00145823` | E1 | Lineareinheit | — | gemini-2.5-flash (image): Kombinierte Einheit | [原文](#excel-第-49-行) |
| 50（待核对） | `0804KS8037` | `AS00164441` | E1 | Multi-Achs-System (Gantry) | — | claude-opus-4-8 (image): Kombinierte Einheit | [原文](#excel-第-50-行) |
| 51（待核对） | `0804KT1289` | `AS00177742` | E1 | Lineareinheit | — | claude-haiku-4-5_20251001 (pdf): `[EMPTY]` | 空白（用户确认） |


### Excel 第 48 行

GT vor Review: Greifer | LLM: Kombinierte Einheit
Analyse (Dateninput-Bug / Katalog-Anwendungsbeispiel bewertet): Die Baugruppe ist ein reiner Parallelgreifer (Pos. 0100, Schunk PGN-plus 64-1) mit Schnellwechsler und Sensorik (R-0, T=0 → Greifer). Da das Schunk-Datenblatt (PGN-plus) mitgeliefert wurde, hat das LLM fälschlicherweise die generische Werbegrafik („Anwendungsbeispiel" mit Schwenkeinheit und Linearachsen, R=1, T=2) auf Seite 1 des Katalogs statt der eigentlichen Baugruppe klassifiziert.
Revidierte GT: Greifer (LLM korrekt: nein - Katalog-Anwendungsbeispiel auf dem Datenblatt-Deckblatt wurde statt der eigentlichen Baugruppe bewertet).

### Excel 第 49 行

GT vor Review: Lineareinheit | LLM: Kombinierte Einheit
Analyse (Fehlinterpretation der liegenden 3D-Ansicht / Doppelzählung der Achse): Die Baugruppe (Hubeinrichtung) besitzt nur eine einzige vertikale Linearachse (Pos. 0100, Rexroth CKK-145 mit Motor Pos. 0101, R=0, T=1 → Lineareinheit). Wegen der liegenden Darstellung im 3D-Bild hat das LLM diese Achse als „Horizontalachse" (T,=1) gelesen und allein aufgrund des Namens Hubeinrichtung eine zweite, „unsichtbare" Vertikalachse (T2=1) dazuhalluziniert.
Revidierte GT: Lineareinheit (LLM korrekt: nein - dieselbe Hubachse Pos. 0100 wurde wegen der liegenden 3D-Ansicht doppelt als Horizontal- und Vertikalachse T=2 gezählt).

### Excel 第 50 行

GT vor Review: Multi-Achs-System (Gantry) | LLM: Kombinierte Einheit
Analyse (Verwechslung von Basis- und Querachse beim Gantry-Test): Die Baugruppe (Achssystem / Gantry) ist ein klassisches zweiachsiges X/Y-Flächenportal (R=0, T=2) auf einem Standgestell (Pos. 0114).
Im Rexroth-Mehrachssystem (Pos. 0100, CKK-110-NN-1 + 2x MKR-065-NN-3) bilden die beiden parallelen Linearmodule (2x MKR-065) die beidseitig geführte horizontale Basisachse, auf der das CKK-110 als Querbrücke läuft (alle drei Gantry-Kriterien a, b, c erfüllt). Das LLM hat jedoch die Rollen der Achsen vertauscht, das einzelne CKK-110 fälschlicherweise für die Basisachse gehalten und das System irrig als einseitigen Ausleger (Grenzfall 6.4) eingestuft.
Revidierte GT: Gantry (LLM korrekt: nein - 2x MKR-065 bildet eindeutig eine beidseitig geführte
Portalbasis für die Querachse CKK-110).


## 第十七部分 · Excel 第 52–55 行（待照片核对）

行号、编号和可辨认的 Register 根据用户提供的文字暂按顺序匹配，SAP 与 Teamcenter 配对均与 `corrected_gt_zgt_error_records.md` 一致。第 54、55 行文字排列交错，行号及 Register 待照片确认；用户提供的 `Li` 截断且无法可靠确定所属字段，`0`、`1` 也无法可靠归属到具体行和列。下表修正表信息尚未与 `Fehler_Analyse` 本工作表核对；`—` 表示修正表中为空，与明确显示的 `[EMPTY]` 不同，不能据此推断模型没有输出。错误分析待提供。

| Excel 行 | SAP-Nummer | Teamcenter | Register（用户文字，待核对） | Ground Truth（修正表） | 其他允许类别（修正表） | 非空模型记录（修正表） | Fehleranalyse |
|---:|---|---|---|---|---|---|---|
| 52 | `0804KV2157` | `AS00190354` | E2 | Kombinierte Einheit | — | gemini-2.5-pro (image): Gantry | 待提供 |
| 53 | `0804KZ8712` | `AS00231951` | E1 | Lineareinheit | — | claude-haiku-4-5_20251001 (image): Kombinierte Einheit | 待提供 |
| 54（待核对） | `0804LB3626` | `AS00245227` | E1（暂配） | Lineareinheit | — | gemini-2.5-pro (image): Kombinierte Einheit | 待提供 |
| 55（待核对） | `0804LE2661` | `AS00260156` | M（暂配） | Greifer | Kombinierte Einheit | gemini-2.5-flash (image): Rotationseinheit | 待提供 |
