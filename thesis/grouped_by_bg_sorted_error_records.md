# Grouped_By_BG_Sorted | 按装配体分组的错误明细

## Excel 第 2–6 行

两批截图按重叠的模型、输入类型和相邻 Reasoning 内容对齐。第 2–6 行对应同一个装配体的五条预测记录。表中 `—` 表示照片中可见的空白单元格。截图中未展示的列未转录。

| Excel 行 | D · SAP-Nummer | E · Teamcenter | G · Register | H · Ground Truth | I · Weitere zulässige Ground Truth | J · Predicted Label | L · Model | M · Input_File Type | P · Pages_Sent_Status | Q · Reasoning |
|---:|---|---|---|---|---|---|---|---|---|---|
| 2 | `0804EN7325` | `AS90118452/01` | M | Kombinierte Einheit | — | Gantry | `claude-haiku-4-5_`（显示部分） | image | Sent 40 images in 3 batch(es) of size 15 | [原文](#excel-第-2-行) |
| 3 | `0804EN7325` | `AS90118452/01` | M | Kombinierte Einheit | — | Gantry | `claude-opus-4-8` | image | Sent 40 images in 3 batch(es) of size 15 | [原文](#excel-第-3-行) |
| 4 | `0804EN7325` | `AS90118452/01` | M | Kombinierte Einheit | — | Gantry | `gemini-2.5-flash` | image | Sent 40 images in 3 batch(es) of size 15 | [原文](#excel-第-4-行) |
| 5 | `0804EN7325` | `AS90118452/01` | M | Kombinierte Einheit | — | Gantry | `gemini-2.5-pro` | image | Sent 40 images in 3 batch(es) of size 15 | [原文](#excel-第-5-行) |
| 6 | `0804EN7325` | `AS90118452/01` | M | Kombinierte Einheit | — | Gantry | `claude-haiku-4-5_`（显示部分） | pdf | Full Document | [原文](#excel-第-6-行) |

- 第 2、6 行的模型标识被列宽截断。上一张工作表中该装配体对应的图片和 PDF 预测列均使用 `claude-haiku-4-5_20251001`，可作为对照。
- 第一张照片的名称框显示 `R3`，公式栏显示 `P3`，因此可确认 R3 的值为 `P3`。R 列表头与 R2 未显示。
- 第 5 行在截图中为浅绿色。第 7 行只露出 Q 列开头 `Die Baugruppe ist ein Mehrachssystem mit drei translatorischen Achsen`，待补拍后录入。
- 以下 Reasoning 为工作表中的模型输出原文。

### Excel 第 2 行

Die Baugruppe ist ein Gantry-Portal nach Bosch-Dokumentation (Stückliste 0804.EN7.325, Bezeichnung 'gantry Portal'). Die kinematische Analyse zeigt R=0 (keine Rotationsachsen) und T≥2 (mehrere translatorische Achsen). Der Gantry-Test bestätigt alle drei Kriterien: (a) Die Linearachsen sind orthogonal zueinander und spannen einen kartesischen Arbeitsraum auf (X-, Y-, Z-Achsen möglich); (b) Mindestens zwei horizontale Achsen sind vorhanden (X und Y); (c) Die X-Achse ist als Portal-/Brückenstruktur beidseitig geführt und gelagert (erkennbar aus den Führungsschienen R160 520 331 und der symmetrischen Lagerung). Die Stückliste enthält Linearführungen (Zylinderstifte, Scheiben), Pneumatik-Schaltelelemente und Hall-Sensoren für Positionierung, was ein motorisches Antriebssystem mit Endlagen-Erkennung bestätigt. Dies entspricht exakt der Definition eines Gantry-Systems für kartesische Positionierung und Transport im Arbeitsraum.

### Excel 第 3 行

Die Baugruppe ist als 'gantry / Portal' benannt. Die Stückliste und Datenblätter enthalten mehrere Kugelschienenführungen (R160520331, R162222320), Antriebs- und Führungskomponenten sowie pneumatische Klemm-/Bremselemente, was auf ein Mehrachs-Linearsystem mit kartesischem Arbeitsraum hindeutet (R=0, T>=2). Der Gantry-Test ist erfüllt: orthogonale Linearachsen, horizontale Basisachse und beidseitig geführte Portal-/Brückenstruktur. Damit erfolgt die Zuordnung als Gantry.

### Excel 第 4 行

Die Baugruppe trägt den Namen 'gantry Portal', was direkt auf die Klassifizierung hinweist. Die Stückliste und Datenblätter bestätigen die Existenz von linearen Führungskomponenten (Kugelschienenführungen, Laufwagen). Es wird angenommen, dass die Baugruppe mindestens zwei translatorische Achsen (T>=2) besitzt, die orthogonal zueinander angeordnet sind und einen kartesischen Arbeitsraum aufspannen (R=0). Der 'Gantry-Test' wird bestanden, da die Bezeichnung 'Portal' impliziert, dass die erste horizontale Achse beidseitig geführt ist, und mindestens zwei Achsen horizontal ausgerichtet sind. Die Hauptfunktion ist eine Handhabungsfunktion (Positionierung, Transport).

### Excel 第 5 行

Die Baugruppe ist explizit als 'gantry Portal' benannt. Die Stückliste und Datenblätter belegen die Verwendung von Linearführungskomponenten (Führungsschienen, Führungswagen), was auf eine rein translatorische Kinematik hindeutet. Ein Portal-System hat per Definition mindestens zwei translatorische Achsen (T>=2) und keine rotatorische Achse (R=0). Die Bezeichnung 'Portal' impliziert eine beidseitig geführte Brückenstruktur, wodurch alle drei Kriterien des Gantry-Tests (Abschnitt 4, Fall B) als erfüllt gelten.

### Excel 第 6 行

Die Baugruppe ist ein Portal-Gantry-System mit folgenden Charakteristiken: (1) Sie besitzt mehrere orthogonal angeordnete Linearachsen (R=0, T>=2). Aus der Stückliste sind zwei Linearachsen identifiziert (0100: CKK-200-NN mit Kugelspindel, 900mm Hub; 0101: CKR-145-NN mit Riemenantrieb, 820mm Hub), die in X- und Y-Richtung arbeiten. (2) Die technischen Zeichnungen und 3D-CAD-Renderings zeigen eine klassische Portal-/Brückenstruktur mit beidseitig geführten und gelagerten Linearachsen. (3) Die Führungsschienen (0107, 0108: KSA-025-SNS-H-MA-AK, Größe 25) sind beidseitig angeordnet und ermöglichen eine stabile Portal-Konfiguration. (4) Die Laufwagen (0110: KWD-025-SNS-C2-H-1, 6 Stück) und Klemmelemente (0109: UBPS2505AS1A, 2 Stück) bestätigen die beidseitige Führung. (5) Das System spannt einen kartesischen Arbeitsraum auf mit mindestens zwei horizontalen Achsen (X und Y). Alle drei Gantry-Test-Kriterien sind erfüllt: (a) Orthogonale Achsenanordnung, (b) Mindestens zwei horizontale Achsen, (c) Beidseitig geführte Portal-/Brückenstruktur.
