# 装配体分类数据与三阶段修订统计

本文汇总同一批 199 个装配体在三个时间点的记录，其中主数据集 129 个，补充数据集 70 个。

| 阶段 | 时间点 | 数据来源 |
|---|---|---|
| A | 首次修订前，Workshop 前 | 原始文件夹的类别与装配体编号 |
| B | 第一次修订后，Workshop 后、LLM 实验前 | Excel 工作表 `Final_Ground_Truth_before_Review` 的照片 |
| C | 第二次修订后，LLM 实验后 | Excel 工作表 `Final_Ground_Truth_after_Review` 的照片 |

## 七类数量

A 按原始文件夹类别计数，B 和 C 按 Ground Truth 列计数。每个阶段每个装配体计一次，M 行的其他允许类别保留在明细中。变化列为后一个阶段减前一个阶段。

| 类别 | A（199 条） | B（199 条） | C（199 条） | A → B 变化 | B → C 变化 | 主数据集（A → B → C） | 补充数据集（A → B → C） |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Greifer | 30 | 30 | 30 | 0 | 0 | 20 → 20 → 20 | 10 → 10 → 10 |
| Lineareinheit | 31 | 32 | 31 | +1 | −1 | 21 → 22 → 21 | 10 → 10 → 10 |
| Rotationseinheit | 28 | 28 | 29 | 0 | +1 | 18 → 18 → 19 | 10 → 10 → 10 |
| Roboter | 30 | 30 | 30 | 0 | 0 | 20 → 20 → 20 | 10 → 10 → 10 |
| Multi-Achs-System (Gantry) | 22 | 23 | 23 | +1 | 0 | 17 → 18 → 18 | 5 → 5 → 5 |
| Kombinierte Einheit | 29 | 27 | 27 | −2 | 0 | 24 → 22 → 22 | 5 → 5 → 5 |
| Keine der verfügbaren Klassen | 29 | 29 | 29 | 0 | 0 | 9 → 9 → 9 | 20 → 20 → 20 |
| **合计** | 199 | 199 | 199 | 0 | 0 | 129 → 129 → 129 | 70 → 70 → 70 |

### 类别发生变化的记录

| 修订 | Excel 行 | SAP-Nummer | 修订前类别 | 修订后类别 |
| --- | --- | --- | --- | --- |
| A → B | 60 | 0804DU5389 | Kombinierte Einheit | Multi-Achs-System (Gantry) |
| A → B | 106 | 0804LW3879 | Kombinierte Einheit | Lineareinheit |
| B → C | 8 | 0804KZ9027 | Lineareinheit | Kombinierte Einheit |
| B → C | 43 | 0804GE7738 | Kombinierte Einheit | Rotationseinheit |

C 中的 Kombinierte Einheit 与 B 同为 27 条，其中一条转入、一条转出。

## E1、E2、M 数量

A 阶段的原始文件夹记录没有 Register。B 和 C 的 Register 取自各自的表格。

| Register | A | B（199 条） | C（199 条） | B → C 变化 | 主数据集（B → C） | 补充数据集（B → C） |
| --- | --- | --- | --- | --- | --- | --- |
| E1 | 无记录 | 122 | 117 | −5 | 63 → 58 | 59 → 59 |
| E2 | 无记录 | 48 | 46 | −2 | 38 → 36 | 10 → 10 |
| M | 无记录 | 29 | 36 | +7 | 28 → 35 | 1 → 1 |
| **合计** | 无记录 | 199 | 199 | 0 | 129 → 129 | 70 → 70 |

B → C 共有 7 条 Register 变化，均在主数据集中。

| 变化 | 数量 | SAP-Nummer |
| --- | --- | --- |
| E1 → M | 5 | `0804FC1588`、`0804KZ9027`、`0804DT6452`、`0804KY7178`、`0804MB2849` |
| E2 → M | 2 | `0804JL5526`、`0804JX6656` |

## 字段与转录备注

- 明细保留 Excel 原表的行顺序。ID、SAP-Nummer、Teamcenter、英德文名称和 Baugruppenebene 在 B、C 的转录中一致，因此各列只列一次。A 的照片提供了原始分类和装配体编号。
- 空白单元格用 `—` 表示。部分 SAP 或 Teamcenter 编号确实没有，按原表留空。ID 是 Betreuer 在不同 Workshop 中分别使用的编号，重复值可以忽略。
- M 行的其他允许类别按 Betreuer 的规定照录，包括原表的空白。
- C 的 Ground Truth 列有 29 行在照片中只显示到 `Keine der verfügbaren Klasse`，明细和统计统一写作类别名 `Keine der verfügbaren Klassen`。涉及 Excel 行 68、73、77、78、87、104、105、117、120、138、139、141、142、143、145、152、153、157、158、160、161、162、169、172、180、192、195、196、197。
- C 的照片中，第 24、44、57、58、60、64、67、70 行的 Teamcenter 编号尾部，以及第 77、78、94、124 行的英文名称被列宽遮挡，明细沿用 B 的转录。德文名称栏中的 `4461`、`52`、`14`、`124`、`51` 是 Excel 复制粘贴造成的错误，原值照录，分析时可忽略。
- 三阶段以 SAP 编号对应。SAP 为空的三条以 Teamcenter 编号对应。核对结果为 199 条一一匹配，各阶段类别合计均为 199，B、C 的 Register 合计也均为 199。各类别和 Register 的数量变化与逐条转入、转出结果一致。

## 199 条装配体明细

| Excel 行 | 数据集 | ID | SAP-Nummer | Teamcenter | Benennung (E) | Benennung (D) | Baugruppenebene | A 原始类别 | B Ground Truth | B Register | B 其他允许类别 | C Ground Truth | C Register | C 其他允许类别 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | 主数据集 | 1 | 0804FC1588 | AS90011709 | gantry | Portal | Hauptbaugruppe | Multi-Achs-System (Gantry) | Multi-Achs-System (Gantry) | E1 | — | Multi-Achs-System (Gantry) | M | Kombinierte Einheit |
| 3 | 主数据集 | 2 | 0804FA3834 | AS90468773 | rotation unit | Rotationseinheit | Unterbaugruppe | Rotationseinheit | Rotationseinheit | E1 | — | Rotationseinheit | E1 | — |
| 4 | 主数据集 | 4 | 0804BR4641 | AS90482550 | robot | Roboter | Hauptbaugruppe | Roboter | Roboter | E1 | — | Roboter | E1 | — |
| 5 | 主数据集 | 8 | 0804KM9320 | AS00139942 | gripper unit | Greifeinheit | Unterbaugruppe | Greifer | Greifer | E1 | — | Greifer | E1 | — |
| 6 | 主数据集 | 10 | 0804FZ8322 | AS90418178 | Lifting Unit | Hubeinheit | Hauptbaugruppe | Lineareinheit | Lineareinheit | E1 | — | Lineareinheit | E1 | — |
| 7 | 主数据集 | 16 | 0804FM8785 | AS90240070 | robot | Roboter | Hauptbaugruppe | Roboter | Roboter | E1 | — | Roboter | E1 | — |
| 8 | 主数据集 | 20 | 0804KZ9027 | AS00231844 | Lifter | Hubgerät | Hauptbaugruppe | Lineareinheit | Lineareinheit | E1 | — | Kombinierte Einheit | M | Lineareinheit |
| 9 | 主数据集 | 22 | 0804KK0664 | AS00127924 | gripper | Greifer | Unterbaugruppe | Greifer | Greifer | E1 | — | Greifer | E1 | — |
| 10 | 主数据集 | 24 | 0804CW9430 | AS90361633 | robot | Roboter | Hauptbaugruppe | Roboter | Roboter | E1 | — | Roboter | E1 | — |
| 11 | 主数据集 | 27 | 0804KZ1155 | AS00231492 | gripper unit | Greifeinheit | Unterbaugruppe | Greifer | Greifer | E1 | — | Greifer | E1 | — |
| 12 | 主数据集 | 28 | 0804HZ8350 | AS90317924 | axis system | Achssystem | Hauptbaugruppe | Multi-Achs-System (Gantry) | Multi-Achs-System (Gantry) | E1 | — | Multi-Achs-System (Gantry) | E1 | — |
| 13 | 主数据集 | 29 | 0804KZ8712 | AS00231951 | Lifter | Hubgerät | Hauptbaugruppe | Lineareinheit | Lineareinheit | E1 | — | Lineareinheit | E1 | — |
| 14 | 主数据集 | 30 | 0804KE7723 | AS00115515 | axis system | Achssystem | Hauptbaugruppe | Multi-Achs-System (Gantry) | Multi-Achs-System (Gantry) | E1 | — | Multi-Achs-System (Gantry) | E1 | — |
| 15 | 主数据集 | 31 | 0804JL8049 | AS00012357 | gripper | Greifer | Hauptbaugruppe | Greifer | Greifer | E1 | — | Greifer | E1 | — |
| 16 | 主数据集 | 33 | 0804JU4254 | AS00042552 | rotation unit | Rotationseinheit | Hauptbaugruppe | Rotationseinheit | Rotationseinheit | E1 | — | Rotationseinheit | E1 | — |
| 17 | 主数据集 | 36 | 0804KW6842 | AS00198144 | gripper | Greifer | Unterbaugruppe | Greifer | Greifer | E1 | — | Greifer | E1 | — |
| 18 | 主数据集 | 42 | 0804KT1289 | AS00177742 | Lifting Unit | Hubeinheit | Hauptbaugruppe | Lineareinheit | Lineareinheit | E1 | — | Lineareinheit | E1 | — |
| 19 | 主数据集 | 44 | 0804KW1502 | AS00198389 | Lifting Device | Hubvorrichtung | Hauptbaugruppe | Lineareinheit | Lineareinheit | E1 | — | Lineareinheit | E1 | — |
| 20 | 主数据集 | 45 | 0804KY7179 | AS00221603 | Lifter | Hubgerät | Unterbaugruppe | Lineareinheit | Lineareinheit | E1 | — | Lineareinheit | E1 | — |
| 21 | 主数据集 | 47 | 0804FF2025 | AS90027990 | robot | Roboter | Hauptbaugruppe | Roboter | Roboter | E1 | — | Roboter | E1 | — |
| 22 | 主数据集 | 48 | 0804KM8175 | AS00145823 | Lifting Device | Hubvorrichtung | Unterbaugruppe | Lineareinheit | Lineareinheit | E1 | — | Lineareinheit | E1 | — |
| 23 | 主数据集 | 50 | 0804KR0143 | AS00159812 | axis system | Achssystem | Hauptbaugruppe | Multi-Achs-System (Gantry) | Multi-Achs-System (Gantry) | E1 | — | Multi-Achs-System (Gantry) | E1 | — |
| 24 | 主数据集 | 52 | 0804KY3585 | AS00228511/03 | axis system | 4461 | — | Multi-Achs-System (Gantry) | Multi-Achs-System (Gantry) | E1 | — | Multi-Achs-System (Gantry) | E1 | — |
| 25 | 主数据集 | 53 | 0804DT6452 | AS90466020 | gantry | Portal | Hauptbaugruppe | Multi-Achs-System (Gantry) | Multi-Achs-System (Gantry) | E1 | — | Multi-Achs-System (Gantry) | M | Keine der verfügbaren Klassen |
| 26 | 主数据集 | 54 | 0804FR1463 | AS90280706 | rotation unit | Rotationseinheit | Unterbaugruppe | Rotationseinheit | Rotationseinheit | E1 | — | Rotationseinheit | E1 | — |
| 27 | 主数据集 | 56 | 0804EC1049 | AS90040285 | robot | Roboter | Unterbaugruppe | Roboter | Roboter | E1 | — | Roboter | E1 | — |
| 28 | 主数据集 | 58 | 0804LG8766 | AS00287914 | suction gripper | Sauggreifer | Unterbaugruppe | Greifer | Greifer | E1 | — | Greifer | E1 | — |
| 29 | 主数据集 | 59 | 0804GD6171 | AS90191800 | robot | Roboter | Hauptbaugruppe | Roboter | Roboter | E1 | — | Roboter | E1 | — |
| 30 | 主数据集 | 5 | 0804JD0275 | AS90202403 | gripper | Greifer | Unterbaugruppe | Greifer | Greifer | E2 | — | Greifer | E2 | — |
| 31 | 主数据集 | 6 | 0804FK2694 | AS90037183 | gantry | Portal | Hauptbaugruppe | Multi-Achs-System (Gantry) | Multi-Achs-System (Gantry) | E2 | — | Multi-Achs-System (Gantry) | E2 | — |
| 32 | 主数据集 | 12 | 0804JL8434 | AS00026831 | robot | Roboter | Hauptbaugruppe | Roboter | Roboter | M | Kombinierte Einheit | Roboter | M | Kombinierte Einheit |
| 33 | 主数据集 | 13 | 0804KB2225 | AS00092334 | rotation unit | Rotationseinheit | Hauptbaugruppe | Rotationseinheit | Rotationseinheit | M | Keine der verfügbaren Klassen | Rotationseinheit | M | Keine der verfügbaren Klassen |
| 34 | 主数据集 | 15 | 0804KY5559 | AS00221429 | Gripper Unit | Greifeinheit | Unterbaugruppe | Greifer | Greifer | E2 | — | Greifer | E2 | — |
| 35 | 主数据集 | 17 | 0804HK5576 | AS90212293 | robot | Roboter | Hauptbaugruppe | Roboter | Roboter | M | Kombinierte Einheit | Roboter | M | Kombinierte Einheit |
| 36 | 主数据集 | 21 | 0804KR6993 | AS00156452 | Lifter | Hubgerät | Hauptbaugruppe | Lineareinheit | Lineareinheit | E2 | — | Lineareinheit | E2 | — |
| 37 | 主数据集 | 23 | 0804LH5422 | AS00289859 | handling device | Handhabungsgerät | Hauptbaugruppe | Kombinierte Einheit | Kombinierte Einheit | E2 | — | Kombinierte Einheit | E2 | — |
| 38 | 主数据集 | 26 | 0804KZ5637 | AS00212374 | gripper | Greifer | Unterbaugruppe | Greifer | Greifer | E2 | — | Greifer | E2 | — |
| 39 | 主数据集 | 32 | 0804KR9668 | AS00199755 | gripper module | Greifermodul | Unterbaugruppe | Greifer | Greifer | M | Keine der verfügbaren Klassen | Greifer | M | Keine der verfügbaren Klassen |
| 40 | 主数据集 | 34 | 0804JU56371 | AS00049479 | robot unit | Roboter-Einheit | Unterbaugruppe | Roboter | Roboter | M | Kombinierte Einheit | Roboter | M | Kombinierte Einheit |
| 41 | 主数据集 | 35 | 0804AY8008 | AS90102714 | handling | Handhabung | Hauptbaugruppe | Kombinierte Einheit | Kombinierte Einheit | E2 | — | Kombinierte Einheit | E2 | — |
| 42 | 主数据集 | 37 | 0804EU0861 | AS90247946 | robot | Roboter | Hauptbaugruppe | Roboter | Roboter | M | Kombinierte Einheit | Roboter | M | Kombinierte Einheit |
| 43 | 主数据集 | 40 | 0804GE7738 | AS90109419 | rotation unit | Rotationseinheit | Hauptbaugruppe | Kombinierte Einheit | Kombinierte Einheit | M | — | Rotationseinheit | M | Kombinierte Einheit |
| 44 | 主数据集 | 41 | 0804DU5323 | AS90495989/00 | axis system | 52 | — | Multi-Achs-System (Gantry) | Multi-Achs-System (Gantry) | E2 | — | Multi-Achs-System (Gantry) | E2 | — |
| 45 | 主数据集 | 43 | 0804GV7647 | AS90294354 | handling | Handhabung | Hauptbaugruppe | Kombinierte Einheit | Kombinierte Einheit | E2 | — | Kombinierte Einheit | E2 | — |
| 46 | 主数据集 | 46 | 0804EB6690 | AS90347860 | rotation unit | Rotationseinheit | Hauptbaugruppe | Kombinierte Einheit | Kombinierte Einheit | E2 | — | Kombinierte Einheit | E2 | — |
| 47 | 主数据集 | 49 | 0804306221 | AS90101734 | gantry | Portal | Hauptbaugruppe | Kombinierte Einheit | Kombinierte Einheit | E2 | — | Kombinierte Einheit | E2 | — |
| 48 | 主数据集 | 55 | 0804KZ9209 | AS00231833 | Lifter | Hubgerät | Unterbaugruppe | Lineareinheit | Lineareinheit | E2 | — | Lineareinheit | E2 | — |
| 49 | 主数据集 | 57 | 0804DN9616 | AS90430781 | gantry | Portal | Hauptbaugruppe | Multi-Achs-System (Gantry) | Multi-Achs-System (Gantry) | E2 | — | Multi-Achs-System (Gantry) | E2 | — |
| 50 | 主数据集 | 60 | 0804LB1151 | AS00238335 | Lifter | Hubgerät | Unterbaugruppe | Lineareinheit | Lineareinheit | M | Multi-Achs-System (Gantry), Kombinierte Einheit | Lineareinheit | M | Multi-Achs-System (Gantry), Kombinierte Einheit |
| 51 | 主数据集 | 3 | 0804CE5532 | AS90000201 | handling | Handhabung | Hauptbaugruppe | Kombinierte Einheit | Kombinierte Einheit | E2 | — | Kombinierte Einheit | E2 | — |
| 52 | 主数据集 | 7 | 0804FU6515 | AS90303031 | handling | Handhabung | Hauptbaugruppe | Kombinierte Einheit | Kombinierte Einheit | E2 | — | Kombinierte Einheit | E2 | — |
| 53 | 主数据集 | 9 | 0804GY2576 | AS90308365 | gantry | Portal | Hauptbaugruppe | Kombinierte Einheit | Kombinierte Einheit | M | Multi-Achs-System (Gantry) | Kombinierte Einheit | M | Multi-Achs-System (Gantry) |
| 54 | 主数据集 | 11 | 0804KM9359 | AS00139165 | turning unit | Wendevorrichtung | Hauptbaugruppe | Rotationseinheit | Rotationseinheit | E2 | — | Rotationseinheit | E2 | — |
| 55 | 主数据集 | 39 | 0804CH8012 | AS90513297 | Handling | Handhabung | Hauptbaugruppe | Kombinierte Einheit | Kombinierte Einheit | E2 | — | Kombinierte Einheit | E2 | — |
| 56 | 主数据集 | 51 | 0804KB7256 | AS00097350 | rotation unit | Rotationseinheit | Hauptbaugruppe | Rotationseinheit | Rotationseinheit | E2 | — | Rotationseinheit | E2 | — |
| 57 | 主数据集 | 14 | 0804AR3766 | AS90165357/00 | rotation unit | 14 | — | Rotationseinheit | Rotationseinheit | M | Greifer | Rotationseinheit | M | Greifer |
| 58 | 主数据集 | 18 | 0804HX0679 | AS90052795/01 | rotation unit | 124 | — | Rotationseinheit | Rotationseinheit | E2 | — | Rotationseinheit | E2 | — |
| 59 | 主数据集 | 19 | 0804KZ9488 | AS00231836 | handling device | Handhabungsgerät | Unterbaugruppe | Kombinierte Einheit | Kombinierte Einheit | E2 | — | Kombinierte Einheit | E2 | — |
| 60 | 主数据集 | 25 | 0804DU5389 | AS90327677/00 | axis system | 51 | — | Kombinierte Einheit | Multi-Achs-System (Gantry) | M | Kombinierte Einheit | Multi-Achs-System (Gantry) | M | Kombinierte Einheit |
| 61 | 主数据集 | 38 | 0804GY2577 | AS90283974 | turning unit | Wendevorrichtung | Hauptbaugruppe | Kombinierte Einheit | Kombinierte Einheit | E2 | — | Kombinierte Einheit | E2 | — |
| 62 | 主数据集 | 9 | 0804LG6553 | AS00234620 | gantry axle | Portalachse | — | Multi-Achs-System (Gantry) | Multi-Achs-System (Gantry) | E1 | — | Multi-Achs-System (Gantry) | E1 | — |
| 63 | 主数据集 | 27 | 0804KY6491 | AS00226737 | Lifting Unit | Hubeinheit | — | Lineareinheit | Lineareinheit | E1 | — | Lineareinheit | E1 | — |
| 64 | 主数据集 | 34 | 0804FH4760 | AS90308280/00 | robot | Roboter | — | Roboter | Roboter | E1 | — | Roboter | E1 | — |
| 65 | 主数据集 | 4 | 0804KS8037 | AS00164441 | axis system | Achssystem | — | Multi-Achs-System (Gantry) | Multi-Achs-System (Gantry) | E1 | — | Multi-Achs-System (Gantry) | E1 | — |
| 66 | 主数据集 | 2 | 0804KR9943 | AS00156329 | handling unit | Handlingseinheit | — | Kombinierte Einheit | Kombinierte Einheit | E1 | — | Kombinierte Einheit | E1 | — |
| 67 | 主数据集 | 29 | 0804EK1683 | AS90152580/01 | robot | Roboter | — | Roboter | Roboter | E1 | — | Roboter | E1 | — |
| 68 | 主数据集 | 28 | 0804LU7362 | AS00354920 | supporting frame | Gestell | — | Keine der verfügbaren Klassen | Keine der verfügbaren Klassen | E1 | — | Keine der verfügbaren Klassen | E1 | — |
| 69 | 主数据集 | 25 | 0804KT2332 | AS00150269 | gripper unit | Greifereinheit | — | Greifer | Greifer | E1 | — | Greifer | E1 | — |
| 70 | 主数据集 | 7 | 0804EV7706 | AS90158200/01 | robot unit | Robotereinheit | — | Roboter | Roboter | E1 | — | Roboter | E1 | — |
| 71 | 主数据集 | 20 | 0804KY9594 | AS00219172 | Lifting Unit | Hubeinheit | — | Lineareinheit | Lineareinheit | E1 | — | Lineareinheit | E1 | — |
| 72 | 主数据集 | 24 | 0804KU2401 | AS00177443 | Lifting Device | Hubeinrichtung | — | Lineareinheit | Lineareinheit | E1 | — | Lineareinheit | E1 | — |
| 73 | 主数据集 | 1 | 0804LH9239 | AS00306708 | control panel | Steuertafel | — | Keine der verfügbaren Klassen | Keine der verfügbaren Klassen | E1 | — | Keine der verfügbaren Klassen | E1 | — |
| 74 | 主数据集 | 6 | 0804LB3626 | AS00245227 | Lifter | Ausheber | — | Lineareinheit | Lineareinheit | E1 | — | Lineareinheit | E1 | — |
| 75 | 主数据集 | 8 | 0804KW6429 | AS00243076 | axis system | Achssystem | — | Multi-Achs-System (Gantry) | Multi-Achs-System (Gantry) | E1 | — | Multi-Achs-System (Gantry) | E1 | — |
| 76 | 主数据集 | 22 | 0804KB9919 | AS00084317 | gripper unit | Greifereinheit | — | Greifer | Greifer | E1 | — | Greifer | E1 | — |
| 77 | 主数据集 | 18 | 0804KU7061 | AS00199717 | supporting frame | Gestell | — | Keine der verfügbaren Klassen | Keine der verfügbaren Klassen | E1 | — | Keine der verfügbaren Klassen | E1 | — |
| 78 | 主数据集 | 12 | 0804JT7787 | AS00046110 | supporting frame | Gestell | — | Keine der verfügbaren Klassen | Keine der verfügbaren Klassen | E1 | — | Keine der verfügbaren Klassen | E1 | — |
| 79 | 主数据集 | 33 | 0804EA6409 | AS90439710/01 | robot | Roboter | — | Roboter | Roboter | E1 | — | Roboter | E1 | — |
| 80 | 主数据集 | 55 | 0804FR8437 | AS90092024/01 | robot | Roboter | — | Roboter | Roboter | E1 | — | Roboter | E1 | — |
| 81 | 主数据集 | 63 | 0804CC3075 | AS90234041/00 | robot | Roboter | — | Roboter | Roboter | E1 | — | Roboter | E1 | — |
| 82 | 主数据集 | 64 | 0804KU9472 | — | gripper unit | Greifereinheit | — | Greifer | Greifer | E1 | — | Greifer | E1 | — |
| 83 | 主数据集 | 43 | 0804LY4947 | AS00378575 | Lifting Unit | Hubeinheit | — | Lineareinheit | Lineareinheit | E1 | — | Lineareinheit | E1 | — |
| 84 | 主数据集 | 35 | 0804KT8575 | AS00185495/01 | robot | Roboter | — | Roboter | Roboter | E1 | — | Roboter | E1 | — |
| 85 | 主数据集 | 31 | 0804MA9380 | AS00397895 | Lifting Unit | Hubeinheit | — | Lineareinheit | Lineareinheit | E2 | — | Lineareinheit | E2 | — |
| 86 | 主数据集 | 21 | 0804LY8514 | AS00378154 | rotate unit | Dreheinheit | — | Rotationseinheit | Rotationseinheit | E2 | — | Rotationseinheit | E2 | — |
| 87 | 主数据集 | 5 | 0804MA7037 | AS00391134 | holder | Befestigung | — | Keine der verfügbaren Klassen | Keine der verfügbaren Klassen | E2 | — | Keine der verfügbaren Klassen | E2 | — |
| 88 | 主数据集 | 23 | 0804KV4964 | — | gripper unit | Greifereinheit | — | Greifer | Greifer | M | Keine der verfügbaren Klassen | Greifer | M | Keine der verfügbaren Klassen |
| 89 | 主数据集 | 26 | 0804JK8878 | AS00037979 | gripper unit | Greifereinheit | — | Greifer | Greifer | M | Lineareinheit | Greifer | M | Lineareinheit |
| 90 | 主数据集 | 61 | 0804LZ1241 | AS00379611 | rotate unit | Dreheinheit | — | Rotationseinheit | Rotationseinheit | E1 | — | Rotationseinheit | E1 | — |
| 91 | 主数据集 | 65 | 3843CE1617 | AS00277646/01 | axis system | Achssystem | — | Multi-Achs-System (Gantry) | Multi-Achs-System (Gantry) | E1 | — | Multi-Achs-System (Gantry) | E1 | — |
| 92 | 主数据集 | 62 | 0804GZ3046 | AS90390673/00 | rotation unit | Rotationseinheit | — | Rotationseinheit | Rotationseinheit | E1 | — | Rotationseinheit | E1 | — |
| 93 | 主数据集 | 66 | 0804DY2146 | AS90489451/00 | rotation unit | Rotationseinheit | — | Rotationseinheit | Rotationseinheit | E1 | — | Rotationseinheit | E1 | — |
| 94 | 主数据集 | 42 | 0804JX5741 | AS00066414 | gantry axis system | Portalachssystem | — | Multi-Achs-System (Gantry) | Multi-Achs-System (Gantry) | E1 | — | Multi-Achs-System (Gantry) | E1 | — |
| 95 | 主数据集 | 53 | 0804LC3026 | AS00234653 | gripper unit | Greifereinheit | — | Greifer | Greifer | E1 | — | Greifer | E1 | — |
| 96 | 主数据集 | 38 | 0804FL5283 | AS90000589/00 | robot | Roboter | — | Roboter | Roboter | E1 | — | Roboter | E1 | — |
| 97 | 主数据集 | 10 | 0804FT6844 | AS90412772 | handling | Handling | — | Kombinierte Einheit | Kombinierte Einheit | E2 | — | Kombinierte Einheit | E2 | — |
| 98 | 主数据集 | 11 | 0804EZ0597 | AS90254883 | handling | Handling | — | Kombinierte Einheit | Kombinierte Einheit | E2 | — | Kombinierte Einheit | E2 | — |
| 99 | 主数据集 | 15 | 0804KX4663 | AS00210838/01 | robot | Roboter | — | Roboter | Roboter | M | Kombinierte Einheit | Roboter | M | Kombinierte Einheit |
| 100 | 主数据集 | 44 | 0804JX5476 | AS00060502 | rotation unit | Rotationseinheit | — | Rotationseinheit | Rotationseinheit | M | Keine der verfügbaren Klassen | Rotationseinheit | M | Keine der verfügbaren Klassen |
| 101 | 主数据集 | 3 | 0804KV0861 | AS00185760 | gripper unit | Greifereinheit | — | Greifer | Greifer | M | Rotationseinheit | Greifer | M | Rotationseinheit |
| 102 | 主数据集 | 19 | 0804HL3088 | AS90196761 | rotate unit | Dreheinheit | — | Rotationseinheit | Rotationseinheit | E2 | — | Rotationseinheit | E2 | — |
| 103 | 主数据集 | 69 | 0804HH8872 | AS90105353 | handling unit | Handlingseinheit | — | Kombinierte Einheit | Kombinierte Einheit | E2 | — | Kombinierte Einheit | E2 | — |
| 104 | 主数据集 | 51 | 0804JX8777 | AS00071851 | control panel | Bedienungstafel | — | Keine der verfügbaren Klassen | Keine der verfügbaren Klassen | E2 | — | Keine der verfügbaren Klassen | E2 | — |
| 105 | 主数据集 | 30 | 0804LM2565 | AS00324657 | sensor | Sensor | — | Keine der verfügbaren Klassen | Keine der verfügbaren Klassen | E2 | — | Keine der verfügbaren Klassen | E2 | — |
| 106 | 主数据集 | 32 | 0804LW3879 | AS00365660 | Lifting Unit | Hubeinheit | — | Kombinierte Einheit | Lineareinheit | M | Kombinierte Einheit | Lineareinheit | M | Kombinierte Einheit |
| 107 | 主数据集 | 45 | 0804HK2005 | AS90238554 | gripper unit | Greifereinheit | — | Greifer | Greifer | M | Rotationseinheit | Greifer | M | Rotationseinheit |
| 108 | 主数据集 | 60 | 0804LM8093 | AS00324179 | rotate unit | Dreheinheit | — | Rotationseinheit | Rotationseinheit | E2 | — | Rotationseinheit | E2 | — |
| 109 | 主数据集 | 50 | 0804KY7178 | AS00217781 | Lifter | Ausheber | — | Lineareinheit | Lineareinheit | E1 | — | Lineareinheit | M | Kombinierte Einheit |
| 110 | 主数据集 | 14 | 0804LA7293 | AS00242009 | handling unit | Handlingseinheit | — | Kombinierte Einheit | Kombinierte Einheit | E2 | — | Kombinierte Einheit | E2 | — |
| 111 | 主数据集 | 36 | 0804CM8667 | AS90308571/00 | rotation unit | Rotationseinheit | — | Rotationseinheit | Rotationseinheit | M | Kombinierte Einheit | Rotationseinheit | M | Kombinierte Einheit |
| 112 | 主数据集 | 37 | 0804EN7325 | AS90118452/01 | gantry | Portal | — | Kombinierte Einheit | Kombinierte Einheit | M | — | Kombinierte Einheit | M | — |
| 113 | 主数据集 | 41 | 0804LK3617 | AS00295735 | rotate unit | Dreheinheit | — | Rotationseinheit | Rotationseinheit | M | Lineareinheit | Rotationseinheit | M | Kombinierte Einheit |
| 114 | 主数据集 | 17 | 0804GT0312 | AS90082305 | handling unit | Handlingseinheit | — | Kombinierte Einheit | Kombinierte Einheit | E2 | — | Kombinierte Einheit | E2 | — |
| 115 | 主数据集 | 54 | 0804MB2849 | AS00394314 | Lifting Unit | Hubeinheit | — | Lineareinheit | Lineareinheit | E1 | — | Lineareinheit | M | Kombinierte Einheit |
| 116 | 主数据集 | 48 | 0804KU1528 | AS00184530 | gripper unit | Greifereinheit | — | Greifer | Greifer | M | Lineareinheit | Greifer | M | Lineareinheit |
| 117 | 主数据集 | 57 | 3842998383 | PT00412992 | conveyor track | Förderbahn | — | Keine der verfügbaren Klassen | Keine der verfügbaren Klassen | E2 | — | Keine der verfügbaren Klassen | E2 | — |
| 118 | 主数据集 | 56 | 0804KV2157 | AS00190354 | handling unit | Handlingseinheit | — | Kombinierte Einheit | Kombinierte Einheit | E2 | — | Kombinierte Einheit | E2 | — |
| 119 | 主数据集 | 47 | 0804GT5112 | AS90282232 | handling unit | Handlingseinheit | — | Kombinierte Einheit | Kombinierte Einheit | E1 | — | Kombinierte Einheit | E1 | — |
| 120 | 主数据集 | 70 | 0804GA4441 | AS90245290 | control panel | Steuertafel | — | Keine der verfügbaren Klassen | Keine der verfügbaren Klassen | E1 | — | Keine der verfügbaren Klassen | E1 | — |
| 121 | 主数据集 | 59 | 0804LR0554 | AS00331111 | Lifting Unit | Hubeinheit | — | Lineareinheit | Lineareinheit | M | Kombinierte Einheit | Lineareinheit | M | Kombinierte Einheit |
| 122 | 主数据集 | 68 | 0804JL5526 | AS00016496 | sensor | Sensor | — | Lineareinheit | Lineareinheit | E2 | — | Lineareinheit | M | Keine der verfügbaren Klassen |
| 123 | 主数据集 | 52 | 0804LE2661 | AS00260156 | gripper unit | Greifereinheit | — | Greifer | Greifer | M | Kombinierte Einheit | Greifer | M | Kombinierte Einheit |
| 124 | 主数据集 | 49 | 0804AF9667 | AS90134089 | gantry axis system | Portalachssystem | — | Multi-Achs-System (Gantry) | Multi-Achs-System (Gantry) | M | Kombinierte Einheit | Multi-Achs-System (Gantry) | M | Kombinierte Einheit |
| 125 | 主数据集 | 67 | 0804LV8630 | AS00371812 | rotate unit | Dreheinheit | — | Rotationseinheit | Rotationseinheit | M | Lineareinheit | Rotationseinheit | M | Kombinierte Einheit |
| 126 | 主数据集 | 40 | 0804BD5654 | AS90338060 | lift turning unit | Hub-Dreheinheit | — | Kombinierte Einheit | Kombinierte Einheit | E2 | — | Kombinierte Einheit | E2 | — |
| 127 | 主数据集 | 39 | 0804CC2134 | AS90419212/01 | robot | Roboter | — | Roboter | Roboter | M | Kombinierte Einheit | Roboter | M | Kombinierte Einheit |
| 128 | 主数据集 | 58 | 0804JX6656 | AS00057035 | axis system | Achssystem | — | Multi-Achs-System (Gantry) | Multi-Achs-System (Gantry) | E2 | — | Multi-Achs-System (Gantry) | M | Kombinierte Einheit, Keine der verfügbaren Klassen |
| 129 | 主数据集 | 46 | 0804KW8391 | AS00202949 | axis system | Achssystem | — | Multi-Achs-System (Gantry) | Multi-Achs-System (Gantry) | M | Kombinierte Einheit | Multi-Achs-System (Gantry) | M | Kombinierte Einheit, Keine der verfügbaren Klassen |
| 130 | 主数据集 | 13 | 0804FT0436 | AS90143556 | handling | Handling | — | Lineareinheit | Lineareinheit | E1 | — | Lineareinheit | E1 | — |
| 131 | 补充数据集 | — | 0804JK3979 | AS00010335 | lifting unit | Hubeinheit | — | Lineareinheit | Lineareinheit | E1 | — | Lineareinheit | E1 | — |
| 132 | 补充数据集 | — | 0804AG8297 | AS90104129 | lifting unit | Hubeinheit | — | Lineareinheit | Lineareinheit | E1 | — | Lineareinheit | E1 | — |
| 133 | 补充数据集 | — | 0804LM7661 | AS00326025 | gantry module | PORTALMODUL | — | Multi-Achs-System (Gantry) | Multi-Achs-System (Gantry) | E1 | — | Multi-Achs-System (Gantry) | E1 | — |
| 134 | 补充数据集 | — | 0804KE6397 | AS00114947 | robot | ROBOTER | — | Roboter | Roboter | E1 | — | Roboter | E1 | — |
| 135 | 补充数据集 | — | 0804KV5835 | AS00189642 | lifting unit | Hubeinheit | — | Lineareinheit | Lineareinheit | E2 | — | Lineareinheit | E2 | — |
| 136 | 补充数据集 | — | 0804LC5647 | AS00253628 | lift-turning unit | Hub-Dreheinheit | — | Kombinierte Einheit | Kombinierte Einheit | E2 | — | Kombinierte Einheit | E2 | — |
| 137 | 补充数据集 | — | 0804LW4010 | AS00365833 | rotate unit | Dreheinheit | — | Rotationseinheit | Rotationseinheit | E1 | — | Rotationseinheit | E1 | — |
| 138 | 补充数据集 | — | — | AS00235507 | control box | BEDIENUNGSKASTEN | — | Keine der verfügbaren Klassen | Keine der verfügbaren Klassen | E1 | — | Keine der verfügbaren Klassen | E1 | — |
| 139 | 补充数据集 | — | 0804358312 | AS90057078 | sensor | SENSOR | — | Keine der verfügbaren Klassen | Keine der verfügbaren Klassen | E2 | — | Keine der verfügbaren Klassen | E2 | — |
| 140 | 补充数据集 | — | 0804LR7381 | AS00335256 | gripper | GREIFER | — | Greifer | Greifer | E1 | — | Greifer | E1 | — |
| 141 | 补充数据集 | — | 0804LW5713 | AS00366888 | control box | BEDIENUNGSTAFEL | — | Keine der verfügbaren Klassen | Keine der verfügbaren Klassen | E1 | — | Keine der verfügbaren Klassen | E1 | — |
| 142 | 补充数据集 | — | 0804KC4801 | AS00099579 | base frame | GRUNDGESTELL | — | Keine der verfügbaren Klassen | Keine der verfügbaren Klassen | E1 | — | Keine der verfügbaren Klassen | E1 | — |
| 143 | 补充数据集 | — | 0804LD6387 | AS00258437 | base frame | GRUNDGESTELL | — | Keine der verfügbaren Klassen | Keine der verfügbaren Klassen | E1 | — | Keine der verfügbaren Klassen | E1 | — |
| 144 | 补充数据集 | — | 0804LS4641 | AS00129566 | rotate unit | Dreheinheit | — | Rotationseinheit | Rotationseinheit | E1 | — | Rotationseinheit | E1 | — |
| 145 | 补充数据集 | — | 0804KL2297 | AS00131203 | control box | BEDIENUNGSKASTEN | — | Keine der verfügbaren Klassen | Keine der verfügbaren Klassen | E1 | — | Keine der verfügbaren Klassen | E1 | — |
| 146 | 补充数据集 | — | 0804MA1736 | AS00394604 | robot | ROBOTER | — | Roboter | Roboter | E1 | — | Roboter | E1 | — |
| 147 | 补充数据集 | — | 0804MA6689 | AS00395784 | robot | ROBOTER | — | Roboter | Roboter | E1 | — | Roboter | E1 | — |
| 148 | 补充数据集 | — | 0804LN1286 | AS00326573 | gripper | GREIFER | — | Greifer | Greifer | E1 | — | Greifer | E1 | — |
| 149 | 补充数据集 | — | 0804LN1294 | AS00327751 | gripper | GREIFER | — | Greifer | Greifer | E1 | — | Greifer | E1 | — |
| 150 | 补充数据集 | — | 0804LN1297 | AS00327933 | gripper | GREIFER | — | Greifer | Greifer | E1 | — | Greifer | E1 | — |
| 151 | 补充数据集 | — | 0804FE3750 | AS90229004 | lifting unit | Hubeinheit | — | Lineareinheit | Lineareinheit | E2 | — | Lineareinheit | E2 | — |
| 152 | 补充数据集 | — | — | AS00215660 | control box | Bedienungskasten | — | Keine der verfügbaren Klassen | Keine der verfügbaren Klassen | E1 | — | Keine der verfügbaren Klassen | E1 | — |
| 153 | 补充数据集 | — | 1800257228 | AS90039077 | base frame | Gestellunterbau | — | Keine der verfügbaren Klassen | Keine der verfügbaren Klassen | E1 | — | Keine der verfügbaren Klassen | E1 | — |
| 154 | 补充数据集 | — | 0804LK4678 | AS00309775 | lift-turning unit | Hub-Dreheinheit | — | Kombinierte Einheit | Kombinierte Einheit | E1 | — | Kombinierte Einheit | E1 | — |
| 155 | 补充数据集 | — | 0804MB2648 | AS00397363 | robot | ROBOTER | — | Roboter | Roboter | E1 | — | Roboter | E1 | — |
| 156 | 补充数据集 | — | 0804LG2192 | AS00275275 | robot | ROBOTER | — | Roboter | Roboter | E1 | — | Roboter | E1 | — |
| 157 | 补充数据集 | — | 1800257479 | AS90101074 | control box | BEDIENUNGSKASTEN | — | Keine der verfügbaren Klassen | Keine der verfügbaren Klassen | E1 | — | Keine der verfügbaren Klassen | E1 | — |
| 158 | 补充数据集 | — | 3843AV9602 | PT90876568 | sensor | SENSOR | — | Keine der verfügbaren Klassen | Keine der verfügbaren Klassen | E1 | — | Keine der verfügbaren Klassen | E1 | — |
| 159 | 补充数据集 | — | 3843AB4237 | PT91921631 | robot | ROBOTER | — | Roboter | Roboter | E1 | — | Roboter | E1 | — |
| 160 | 补充数据集 | — | 1800257202 | AS90130333 | top frame | Gestellunterbau | — | Keine der verfügbaren Klassen | Keine der verfügbaren Klassen | E1 | — | Keine der verfügbaren Klassen | E1 | — |
| 161 | 补充数据集 | — | 0804JS9252 | AS00040582 | control box | BEDIENUNGSKASTEN | — | Keine der verfügbaren Klassen | Keine der verfügbaren Klassen | E1 | — | Keine der verfügbaren Klassen | E1 | — |
| 162 | 补充数据集 | — | 1800257521 | AS90283097 | base frame | Gestellunterbau | — | Keine der verfügbaren Klassen | Keine der verfügbaren Klassen | E1 | — | Keine der verfügbaren Klassen | E1 | — |
| 163 | 补充数据集 | — | 0804LE7880 | AS00261423 | gantry module | PORTALMODUL | — | Multi-Achs-System (Gantry) | Multi-Achs-System (Gantry) | E2 | — | Multi-Achs-System (Gantry) | E2 | — |
| 164 | 补充数据集 | — | 0804KU1103 | AS00184388 | gripper | GREIFER | — | Greifer | Greifer | E2 | — | Greifer | E2 | — |
| 165 | 补充数据集 | — | 0804AT5037 | AS90418491 | lift-turning unit | Hub-Dreheinheit | — | Kombinierte Einheit | Kombinierte Einheit | E1 | — | Kombinierte Einheit | E1 | — |
| 166 | 补充数据集 | — | 0804LB4468 | AS00237554 | rotate unit | Dreheinheit | — | Rotationseinheit | Rotationseinheit | E1 | — | Rotationseinheit | E1 | — |
| 167 | 补充数据集 | — | 0804LU7693 | AS00361757 | lifting unit | Hubeinheit | — | Lineareinheit | Lineareinheit | M | Kombinierte Einheit | Lineareinheit | M | Kombinierte Einheit |
| 168 | 补充数据集 | — | 0804BN2123 | AS90387128 | lifting unit | Hubeinheit | — | Lineareinheit | Lineareinheit | E1 | — | Lineareinheit | E1 | — |
| 169 | 补充数据集 | — | 3843106114 | AS90124618 | holder | Befestigung | — | Keine der verfügbaren Klassen | Keine der verfügbaren Klassen | E1 | — | Keine der verfügbaren Klassen | E1 | — |
| 170 | 补充数据集 | — | 0804LL3638 | AS00309641 | gantry module | PORTALMODUL | — | Multi-Achs-System (Gantry) | Multi-Achs-System (Gantry) | E1 | — | Multi-Achs-System (Gantry) | E1 | — |
| 171 | 补充数据集 | — | 0804EM7937 | AS90316069 | lifting unit | Hubeinheit | — | Lineareinheit | Lineareinheit | E1 | — | Lineareinheit | E1 | — |
| 172 | 补充数据集 | — | 3843CD1070 | PT00465587 | sensor | SENSOR | — | Keine der verfügbaren Klassen | Keine der verfügbaren Klassen | E1 | — | Keine der verfügbaren Klassen | E1 | — |
| 173 | 补充数据集 | — | 0804LZ1881 | AS00384097 | rotate unit | Dreheinheit | — | Rotationseinheit | Rotationseinheit | E1 | — | Rotationseinheit | E1 | — |
| 174 | 补充数据集 | — | 0804LL8077 | AS00321604 | robot | ROBOTER | — | Roboter | Roboter | E1 | — | Roboter | E1 | — |
| 175 | 补充数据集 | — | 0804KA8953 | AS00088214 | rotate unit | Dreheinheit | — | Rotationseinheit | Rotationseinheit | E2 | — | Rotationseinheit | E2 | — |
| 176 | 补充数据集 | — | 0804KF8538 | AS00103837 | robot | ROBOTER | — | Roboter | Roboter | E1 | — | Roboter | E1 | — |
| 177 | 补充数据集 | — | 0804LF6209 | AS00279564 | gripper | GREIFER | — | Greifer | Greifer | E1 | — | Greifer | E1 | — |
| 178 | 补充数据集 | — | 0804MB8153 | AS00407159 | gripper | GREIFER | — | Greifer | Greifer | E2 | — | Greifer | E2 | — |
| 179 | 补充数据集 | — | 0804LX7355 | AS00371228 | gantry module | PORTALMODUL | — | Multi-Achs-System (Gantry) | Multi-Achs-System (Gantry) | E1 | — | Multi-Achs-System (Gantry) | E1 | — |
| 180 | 补充数据集 | — | 3843AZ5880 | PT90997121 | sensor | SENSOR | — | Keine der verfügbaren Klassen | Keine der verfügbaren Klassen | E1 | — | Keine der verfügbaren Klassen | E1 | — |
| 181 | 补充数据集 | — | 0804GR4842 | AS90210608 | gripper | GREIFER | — | Greifer | Greifer | E2 | — | Greifer | E2 | — |
| 182 | 补充数据集 | — | 0804KB9727 | AS00089987 | rotate unit | Dreheinheit | — | Rotationseinheit | Rotationseinheit | E1 | — | Rotationseinheit | E1 | — |
| 183 | 补充数据集 | — | 0804MC3545 | AS00400675 | lifting unit | HUBEINRICHTUNG | — | Lineareinheit | Lineareinheit | E1 | — | Lineareinheit | E1 | — |
| 184 | 补充数据集 | — | 0804JF2622 | AX90412617 | lifting unit | Hubeinheit | — | Lineareinheit | Lineareinheit | E1 | — | Lineareinheit | E1 | — |
| 185 | 补充数据集 | — | 0804LS3667 | AS00338083 | rotate unit | Dreheinheit | — | Rotationseinheit | Rotationseinheit | E1 | — | Rotationseinheit | E1 | — |
| 186 | 补充数据集 | — | 0804LN1289 | AS00327503 | gripper | GREIFER | — | Greifer | Greifer | E1 | — | Greifer | E1 | — |
| 187 | 补充数据集 | — | 0804KD4277 | AS00108129 | rotate unit | Dreheinheit | — | Rotationseinheit | Rotationseinheit | E1 | — | Rotationseinheit | E1 | — |
| 188 | 补充数据集 | — | 0804LN1287 | AS00326685 | gripper | GREIFER | — | Greifer | Greifer | E1 | — | Greifer | E1 | — |
| 189 | 补充数据集 | — | 0804AF6207 | AS90316722 | lift-turning unit | Hub-Dreheinheit | — | Kombinierte Einheit | Kombinierte Einheit | E1 | — | Kombinierte Einheit | E1 | — |
| 190 | 补充数据集 | — | 0804JC9184 | AS00106958 | robot | ROBOTER | — | Roboter | Roboter | E1 | — | Roboter | E1 | — |
| 191 | 补充数据集 | — | 0804LM0799 | AS00323299 | lifting unit | Hubeinheit | — | Lineareinheit | Lineareinheit | E1 | — | Lineareinheit | E1 | — |
| 192 | 补充数据集 | — | 0804LH2249 | AS00293172 | control box | STEUERSCHRANK | — | Keine der verfügbaren Klassen | Keine der verfügbaren Klassen | E1 | — | Keine der verfügbaren Klassen | E1 | — |
| 193 | 补充数据集 | — | 0804LK3474 | AS00310188 | rotate unit | Dreheinheit | — | Rotationseinheit | Rotationseinheit | E1 | — | Rotationseinheit | E1 | — |
| 194 | 补充数据集 | — | 0804HD4595 | AS90011576 | rotate unit | Dreheinheit | — | Rotationseinheit | Rotationseinheit | E1 | — | Rotationseinheit | E1 | — |
| 195 | 补充数据集 | — | 0804JR9924 | AS00047619 | control box | BEDIENUNGSTAFEL | — | Keine der verfügbaren Klassen | Keine der verfügbaren Klassen | E1 | — | Keine der verfügbaren Klassen | E1 | — |
| 196 | 补充数据集 | — | — | AX01253877 | control box | BEDIENUNGSKASTEN | — | Keine der verfügbaren Klassen | Keine der verfügbaren Klassen | E1 | — | Keine der verfügbaren Klassen | E1 | — |
| 197 | 补充数据集 | — | 1800257200 | AS90074111 | machine frame | Maschinengestell | — | Keine der verfügbaren Klassen | Keine der verfügbaren Klassen | E1 | — | Keine der verfügbaren Klassen | E1 | — |
| 198 | 补充数据集 | — | 0804KX6885 | AS00220520 | gantry module | PORTALMODUL | — | Multi-Achs-System (Gantry) | Multi-Achs-System (Gantry) | E1 | — | Multi-Achs-System (Gantry) | E1 | — |
| 199 | 补充数据集 | — | 0804JW4969 | AS00058246 | robot | ROBOTER | — | Roboter | Roboter | E1 | — | Roboter | E1 | — |
| 200 | 补充数据集 | — | 0804AH9298 | AS90166730 | lift-turning unit | Hub-Dreheinheit | — | Kombinierte Einheit | Kombinierte Einheit | E2 | — | Kombinierte Einheit | E2 | — |
