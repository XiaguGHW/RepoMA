# Grouped_By_BG_Sorted | 按装配体分组的错误明细

## 第一批截图 · Excel 第 2–3 行

两张照片通过 J、L、M、P 列的重叠内容对齐。第 2、3 行对应同一个装配体的两条预测记录。表中 `—` 表示照片中可见的空白单元格。截图中未展示的列未转录。

| Excel 行 | D · SAP-Nummer | E · Teamcenter | G · Register | H · Ground Truth | I · Weitere zulässige Ground Truth | J · Predicted Label | L · Model | M · Input_File Type | P · Pages_Sent_Status | Q · Reasoning |
|---:|---|---|---|---|---|---|---|---|---|---|
| 2 | `0804EN7325` | `AS90118452/01` | M | Kombinierte Einheit | — | Gantry | `claude-haiku-4-5_`（显示部分） | image | Sent 40 images in 3 batch(es) of size 15 | [原文](#excel-第-2-行) |
| 3 | `0804EN7325` | `AS90118452/01` | M | Kombinierte Einheit | — | Gantry | `claude-opus-4-8` | image | Sent 40 images in 3 batch(es) of size 15 | [原文](#excel-第-3-行) |

- 第 2 行的模型标识被列宽截断。上一张工作表中该装配体对应的图片预测列为 `claude-haiku-4-5_20251001 (image)`，可作为对照。
- 第一张照片的名称框显示 `R3`，公式栏显示 `P3`，因此可确认 R3 的值为 `P3`。R 列表头与 R2 未显示。
- 第 4 行在照片底部只露出 Q 列开头，原文为 `Die Baugruppe trägt den Namen 'gantry Portal', was direkt auf die`，该行待补拍后录入。
- 以下 Reasoning 为工作表中的模型输出原文。

### Excel 第 2 行

Die Baugruppe ist ein Gantry-Portal nach Bosch-Dokumentation (Stückliste 0804.EN7.325, Bezeichnung 'gantry Portal'). Die kinematische Analyse zeigt R=0 (keine Rotationsachsen) und T≥2 (mehrere translatorische Achsen). Der Gantry-Test bestätigt alle drei Kriterien: (a) Die Linearachsen sind orthogonal zueinander und spannen einen kartesischen Arbeitsraum auf (X-, Y-, Z-Achsen möglich); (b) Mindestens zwei horizontale Achsen sind vorhanden (X und Y); (c) Die X-Achse ist als Portal-/Brückenstruktur beidseitig geführt und gelagert (erkennbar aus den Führungsschienen R160 520 331 und der symmetrischen Lagerung). Die Stückliste enthält Linearführungen (Zylinderstifte, Scheiben), Pneumatik-Schaltelelemente und Hall-Sensoren für Positionierung, was ein motorisches Antriebssystem mit Endlagen-Erkennung bestätigt. Dies entspricht exakt der Definition eines Gantry-Systems für kartesische Positionierung und Transport im Arbeitsraum.

### Excel 第 3 行

Die Baugruppe ist als 'gantry / Portal' benannt. Die Stückliste und Datenblätter enthalten mehrere Kugelschienenführungen (R160520331, R162222320), Antriebs- und Führungskomponenten sowie pneumatische Klemm-/Bremselemente, was auf ein Mehrachs-Linearsystem mit kartesischem Arbeitsraum hindeutet (R=0, T>=2). Der Gantry-Test ist erfüllt: orthogonale Linearachsen, horizontale Basisachse und beidseitig geführte Portal-/Brückenstruktur. Damit erfolgt die Zuordnung als Gantry.
