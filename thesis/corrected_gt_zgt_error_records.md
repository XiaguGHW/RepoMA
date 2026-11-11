# Korrigierte GT&ZGT | 装配体错误记录

## 第一部分

来源为 Excel 工作表 `Korrigierte GT&ZGT` 的七张截图。按原表顺序合并 A–S 列，共 20 条装配体记录，从 `0804EN7325` 到 `0804GD6171`。模型列按截图中的模型标识和输入形式命名。

- `—` 表示截图中的空白单元格，`[EMPTY]` 是工作表中明确记录的值。模型输出中的 `Gantry` 按原文转录。
- 黄色高亮对应 `0804DN9616`。截图中 Ground Truth 和其他允许类别的粗体已保留。
- `0804306221 | AS90101734` 在原表 `BG_ID` 中带前导零，独立的 `SAP-Nummer` 列显示 `804306221`，两列分别照录。
- 这份表保留该工作表中的 Register、Ground Truth 和其他允许类别。每行 12 个模型与输入形式列中的非空值数量均与 `Error_Count` 一致，共 133 个非空值，其中 9 个为 `[EMPTY]`。

| Error_Count | BG_ID | SAP-Nummer | Teamcenter | Register | Ground Truth | Weitere zulässige Ground Truth | claude-haiku-4-5_20251001 (image) | claude-haiku-4-5_20251001 (pdf) | claude-haiku-4-5_20251001 (text) | claude-opus-4-8 (image) | claude-opus-4-8 (pdf) | claude-opus-4-8 (text) | gemini-2.5-flash (image) | gemini-2.5-flash (pdf) | gemini-2.5-flash (text) | gemini-2.5-pro (image) | gemini-2.5-pro (pdf) | gemini-2.5-pro (text) |
| ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 11 | `0804EN7325 \| AS90118452/01` | `0804EN7325` | `AS90118452/01` | M | Kombinierte Einheit | — | Gantry | Gantry | Gantry | Gantry | — | Gantry | Gantry | Gantry | Gantry | Gantry | Gantry | Gantry |
| 10 | `0804FC1588 \| AS90011709` | `0804FC1588` | `AS90011709` | E1 | **Multi-Achs-System (Gantry)** | **Kombinierte Einheit** | `[EMPTY]` | `[EMPTY]` | — | `[EMPTY]` | Kombinierte Einheit | — | Keine der verfügbaren Klassen | Kombinierte Einheit | Kombinierte Einheit | Keine der verfügbaren Klassen | Kombinierte Einheit | Kombinierte Einheit |
| 10 | `0804LV8630 \| AS00371812` | `0804LV8630` | `AS00371812` | M | Rotationseinheit | **Kombinierte Einheit** | `[EMPTY]` | — | — | `[EMPTY]` | Kombinierte Einheit | Kombinierte Einheit | Kombinierte Einheit | Kombinierte Einheit | Kombinierte Einheit | Kombinierte Einheit | Kombinierte Einheit | Kombinierte Einheit |
| 9 | `0804306221 \| AS90101734` | `804306221` | `AS90101734` | E2 | Kombinierte Einheit | — | Gantry | Gantry | Gantry | — | — | — | Gantry | Gantry | Gantry | Gantry | Gantry | Gantry |
| 8 | `0804GE7738 \| AS90109419` | `0804GE7738` | `AS90109419` | M | **Rotationseinheit** | **Kombinierte Einheit** | Lineareinheit | Rotationseinheit | Rotationseinheit | Lineareinheit | — | Rotationseinheit | Lineareinheit | — | Rotationseinheit | Lineareinheit | — | — |
| 8 | `0804GT0312 \| AS90082305` | `0804GT0312` | `AS90082305` | E2 | Kombinierte Einheit | — | Lineareinheit | Gantry | Lineareinheit | — | — | Lineareinheit | Gantry | Gantry | — | Lineareinheit | Gantry | — |
| 8 | `0804MB2849 \| AS00394314` | `0804MB2849` | `AS00394314` | E1 | **Kombinierte Einheit** | **Lineareinheit** | Kombinierte Einheit | Kombinierte Einheit | — | Kombinierte Einheit | Kombinierte Einheit | — | — | Kombinierte Einheit | Kombinierte Einheit | — | Kombinierte Einheit | Kombinierte Einheit |
| 7 | `0804DN9616 \| AS90430781` | `0804DN9616` | `AS90430781` | E2 | Multi-Achs-System (Gantry) | — | — | `[EMPTY]` | — | Lineareinheit | `[EMPTY]` | — | Lineareinheit | `[EMPTY]` | — | Lineareinheit | `[EMPTY]` | — |
| 6 | `0804EB6690 \| AS90347860` | `0804EB6690` | `AS90347860` | E2 | Kombinierte Einheit | — | Greifer | Rotationseinheit | Rotationseinheit | Greifer | — | — | Greifer | — | — | Greifer | — | — |
| 6 | `0804GT5112 \| AS90282232` | `0804GT5112` | `AS90282232` | E1 | Kombinierte Einheit | — | Gantry | Gantry | Gantry | — | — | — | Gantry | — | — | Gantry | — | Gantry |
| 6 | `0804JX6656 \| AS00057035` | `0804JX6656` | `AS00057035` | E2 | Multi-Achs-System (Gantry) | Kombinierte Einheit, Keine der verfügbaren Klassen | — | — | Lineareinheit | Kombinierte Einheit | Lineareinheit | Keine der verfügbaren Klassen | — | — | Keine der verfügbaren Klassen | Lineareinheit | — | — |
| 6 | `0804KM9359 \| AS00139165` | `0804KM9359` | `AS00139165` | E2 | Rotationseinheit | — | — | Kombinierte Einheit | Kombinierte Einheit | Kombinierte Einheit | Kombinierte Einheit | Kombinierte Einheit | Kombinierte Einheit | — | — | — | — | — |
| 6 | `0804KW8391 \| AS00202949` | `0804KW8391` | `AS00202949` | M | Multi-Achs-System (Gantry) | **Kombinierte Einheit, Keine der verfügbaren Klassen** | — | Lineareinheit | Lineareinheit | — | — | Lineareinheit | — | — | Keine der verfügbaren Klassen | — | Lineareinheit | Keine der verfügbaren Klassen |
| 6 | `0804LK3617 \| AS00295735` | `0804LK3617` | `AS00295735` | M | Rotationseinheit | **Kombinierte Einheit** | — | Kombinierte Einheit | — | — | Kombinierte Einheit | Kombinierte Einheit | — | Kombinierte Einheit | — | Kombinierte Einheit | Kombinierte Einheit | — |
| 5 | `0804HZ8350 \| AS90317924` | `0804HZ8350` | `AS90317924` | E1 | Multi-Achs-System (Gantry) | — | Kombinierte Einheit | — | — | Kombinierte Einheit | — | Kombinierte Einheit | Kombinierte Einheit | — | — | Kombinierte Einheit | — | — |
| 5 | `0804KY3585 \| AS00228511/03` | `0804KY3585` | `AS00228511/03` | E1 | Multi-Achs-System (Gantry) | — | Lineareinheit | — | — | Kombinierte Einheit | — | Kombinierte Einheit | Lineareinheit | — | — | Lineareinheit | — | — |
| 4 | `0804CC2134 \| AS90419212/01` | `0804CC2134` | `AS90419212/01` | M | Roboter | Kombinierte Einheit | Rotationseinheit | — | — | Keine der verfügbaren Klassen | — | — | Keine der verfügbaren Klassen | — | — | Greifer | — | — |
| 4 | `0804EK1683 \| AS90152580/01` | `0804EK1683` | `AS90152580/01` | E1 | Roboter | — | Rotationseinheit | — | — | Keine der verfügbaren Klassen | — | — | Keine der verfügbaren Klassen | — | — | Keine der verfügbaren Klassen | — | — |
| 4 | `0804FT0436 \| AS90143556` | `0804FT0436` | `AS90143556` | E1 | Lineareinheit | — | Kombinierte Einheit | Kombinierte Einheit | — | — | — | — | Kombinierte Einheit | — | — | Kombinierte Einheit | — | — |
| 4 | `0804GD6171 \| AS90191800` | `0804GD6171` | `AS90191800` | E1 | Roboter | — | Keine der verfügbaren Klassen | — | — | Keine der verfügbaren Klassen | — | — | Keine der verfügbaren Klassen | — | — | Keine der verfügbaren Klassen | — | — |
