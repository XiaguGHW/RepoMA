# Korrigierte GT&ZGT | 装配体错误记录

## Excel 第 2–41 行

来源为 Excel 工作表 `Korrigierte GT&ZGT` 的两批截图。Excel 第 1 行为表头，第 2–21 行和第 22–41 行按原表顺序合并为一张表，共 40 条装配体记录，涵盖 A–S 列。模型列按截图中的模型标识和输入形式命名。

- `—` 表示截图中的空白单元格，`[EMPTY]` 是工作表中明确记录的值。模型输出中的 `Gantry` 按原文转录。
- 已录入的黄色高亮行对应 `0804DN9616`、`0804KU2401` 和 `0804AF9667`。截图中 Ground Truth 和其他允许类别的粗体已保留。
- `0804306221 | AS90101734` 在原表 `BG_ID` 中带前导零，独立的 `SAP-Nummer` 列显示 `804306221`，两列分别照录。
- 这份表保留该工作表中的 Register、Ground Truth 和其他允许类别。每行 12 个模型与输入形式列中的非空值数量均与 `Error_Count` 一致，前 20 条有 133 个非空值，其中 9 个为 `[EMPTY]`。后 20 条有 40 个非空值，其中 5 个为 `[EMPTY]`。累计 173 个非空值，其中 14 个为 `[EMPTY]`。

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
| 3 | `0804FH4760 \| AS90308280/00` | `0804FH4760` | `AS90308280/00` | E1 | Roboter | — | Keine der verfügbaren Klassen | — | — | Keine der verfügbaren Klassen | — | — | Keine der verfügbaren Klassen | — | — | — | — | — |
| 3 | `0804HH8872 \| AS90105353` | `0804HH8872` | `AS90105353` | E2 | Kombinierte Einheit | — | — | — | — | — | — | — | Gantry | Gantry | Gantry | — | — | — |
| 3 | `0804HX0679 \| AS90052795/01` | `0804HX0679` | `AS90052795/01` | E2 | Rotationseinheit | — | — | — | — | Kombinierte Einheit | — | — | Kombinierte Einheit | — | — | Kombinierte Einheit | — | — |
| 3 | `0804KE7723 \| AS00115515` | `0804KE7723` | `AS00115515` | E1 | Multi-Achs-System (Gantry) | — | Kombinierte Einheit | — | Kombinierte Einheit | — | — | Kombinierte Einheit | — | — | — | — | — | — |
| 3 | `0804KY7178 \| AS00217781` | `0804KY7178` | `AS00217781` | E1 | Lineareinheit | **Kombinierte Einheit** | — | `[EMPTY]` | — | — | — | — | — | — | Kombinierte Einheit | — | — | Kombinierte Einheit |
| 3 | `0804KZ9027 \| AS00231844` | `0804KZ9027` | `AS00231844` | E1 | Lineareinheit | **Kombinierte Einheit** | — | — | — | — | — | — | Kombinierte Einheit | — | — | Kombinierte Einheit | — | Kombinierte Einheit |
| 2 | `0804AR3766 \| AS90165357/00` | `0804AR3766` | `AS90165357/00` | M | Rotationseinheit | Greifer | — | — | — | — | Kombinierte Einheit | Kombinierte Einheit | — | — | — | — | — | — |
| 2 | `0804DT6452 \| AS90466020` | `0804DT6452` | `AS90466020` | E1 | Multi-Achs-System (Gantry) | **Keine der verfügbaren Klassen** | — | — | — | — | — | Keine der verfügbaren Klassen | — | — | — | — | — | Keine der verfügbaren Klassen |
| 2 | `0804KB7256 \| AS00097350` | `0804KB7256` | `AS00097350` | E2 | Rotationseinheit | — | — | — | — | Kombinierte Einheit | — | — | — | — | — | Kombinierte Einheit | — | — |
| 2 | `0804KU2401 \| AS00177443` | `0804KU2401` | `AS00177443` | E1 | Lineareinheit | — | — | `[EMPTY]` | — | — | — | — | — | `[EMPTY]` | — | — | — | — |
| 2 | `0804KY7179 \| AS00221603` | `0804KY7179` | `AS00221603` | E1 | Lineareinheit | — | Kombinierte Einheit | `[EMPTY]` | — | — | — | — | — | — | — | — | — | — |
| 2 | `0804KZ9488 \| AS00231836` | `0804KZ9488` | `AS00231836` | E2 | Kombinierte Einheit | — | Rotationseinheit | — | — | — | — | — | Rotationseinheit | — | — | — | — | — |
| 2 | `0804LA7293 \| AS00242009` | `0804LA7293` | `AS00242009` | E2 | Kombinierte Einheit | — | Greifer | — | — | — | — | — | Greifer | — | — | — | — | — |
| 2 | `0804LH9239 \| AS00306708` | `0804LH9239` | `AS00306708` | E1 | Keine der verfügbaren Klassen | — | Kombinierte Einheit | Lineareinheit | — | — | — | — | — | — | — | — | — | — |
| 1 | `0804AF9667 \| AS90134089` | `0804AF9667` | `AS90134089` | M | Multi-Achs-System (Gantry) | Kombinierte Einheit | — | `[EMPTY]` | — | — | — | — | — | — | — | — | — | — |
| 1 | `0804AY8008 \| AS90102714` | `0804AY8008` | `AS90102714` | E2 | Kombinierte Einheit | — | Gantry | — | — | — | — | — | — | — | — | — | — | — |
| 1 | `0804CE5532 \| AS90000201` | `0804CE5532` | `AS90000201` | E2 | Kombinierte Einheit | — | — | — | — | — | — | — | — | Lineareinheit | — | — | — | — |
| 1 | `0804EV7706 \| AS90158200/01` | `0804EV7706` | `AS90158200/01` | E1 | Roboter | — | — | — | — | — | — | Kombinierte Einheit | — | — | — | — | — | — |
| 1 | `0804FK2694 \| AS90037183` | `0804FK2694` | `AS90037183` | E2 | Multi-Achs-System (Gantry) | — | — | — | — | — | — | — | Kombinierte Einheit | — | — | — | — | — |
| 1 | `0804FT6844 \| AS90412772` | `0804FT6844` | `AS90412772` | E2 | Kombinierte Einheit | — | Lineareinheit | — | — | — | — | — | — | — | — | — | — | — |
