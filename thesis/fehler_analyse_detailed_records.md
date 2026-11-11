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
