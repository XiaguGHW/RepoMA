# 错误原因归类（建议稿）

依据：`corrected_gt_zgt_error_records.md`（输入形式比较的 12 次运行：Haiku、Opus、Flash、Pro × 图片 / PDF / 文本）按最终版 GT 重新判断后仍然出错的 **44 个装配体**，以及 `fehler_analyse_detailed_records.md` 中的错误分析原文。每个装配体只归一个主要原因。本表为 Claude 根据原文给出的建议，需作者逐条确认。

## 类别定义

- **龙门判断错误**：龙门测试（Codebook 第 4 节）判断错误，例如把双侧导向和单侧悬臂混淆，或被零件名称误导。
- **信息过载**：主图纸淹没在供应商目录、手册、报价或数据表中，模型评价的不是主装配体。
- **资料不一致（CAD/BOM）**：图纸 / CAD 与 BOM 互相矛盾，或 3D 模型本身有误。
- **执行器计数错误**：执行器计数（Codebook 第 3 节）出错，包括把被动零件或末端执行器里的驱动算作主轴、虚构驱动、漏看或合并轴。原幻灯片中的“Antriebs-Halluzination”只覆盖虚构驱动，这里扩展为整个计数步骤。
- **其他**：GT 本身有争议或其他原因。目前没有装配体归入此类。
- **待定**：原文无法判断。

## 汇总

| 类别 | 装配体数 |
| --- | ---: |
| 龙门判断错误 | 10 |
| 信息过载 | 11 |
| 资料不一致（CAD/BOM） | 3 |
| 执行器计数错误 | 20 |
| 其他 | 0 |
| 待定 | 0 |
| **合计** | **44** |

## 明细

| SAP | Fehler_Analyse 行 | 最终版 GT | 其他允许标签 | 错误预测（次数） | 出错的输入形式 | 建议类别 | 依据（原文要点） | 把握 |
| --- | ---: | --- | --- | --- | --- | --- | --- | --- |
| `0804EN7325` | 2 | Kombinierte Einheit | — | Multi-Achs-System (Gantry) ×11 | 图片 4, PDF 3, 文本 4 | 龙门判断错误 | 把双侧导向误判为龙门的门式结构，并多数出一根轴（实际只有 Z/X 两轴） | 确定 |
| `0804306221` | 5 | Kombinierte Einheit | — | Multi-Achs-System (Gantry) ×9 | 图片 3, PDF 3, 文本 3 | 龙门判断错误 | “双侧导向”判断错误，原文称为细节问题（Feinheit） | 确定 |
| `0804GT5112` | 11 | Kombinierte Einheit | — | Multi-Achs-System (Gantry) ×6 | 图片 3, PDF 1, 文本 2 | 龙门判断错误 | 被名称“gantry axle / Portalachse”误导；两轴系统未通过龙门测试 | 确定 |
| `0804HZ8350` | 16 | Multi-Achs-System (Gantry) | — | Kombinierte Einheit ×5 | 图片 4, 文本 1 | 龙门判断错误 | 漏看下级 BOM 的两根基础轴，或被零件名“Kreuzplatte”误导，否定了龙门条件 c | 确定 |
| `0804KY3585` | 17 | Multi-Achs-System (Gantry) | — | Lineareinheit ×3, Kombinierte Einheit ×2 | 图片 4, 文本 1 | 龙门判断错误 | 只看 Z 轴的下级 BOM，或被零件名“Ausleger”误导，误判为单侧悬臂 | 确定 |
| `0804HH8872` | 23 | Kombinierte Einheit | — | Multi-Achs-System (Gantry) ×3 | 图片 1, PDF 1, 文本 1 | 龙门判断错误 | 把单侧悬臂（两根立柱支撑的 X 轴）误判为门式结构；另把变频器算作第三根轴 | 确定 |
| `0804AY8008` | 37 | Kombinierte Einheit | — | Multi-Achs-System (Gantry) ×1 | 图片 1 | 龙门判断错误 | 被两个支脚和名称“Portalmodul”误导，虚构出 Y 轴和双侧导向；漏看旋转轴 | 确定 |
| `0804FK2694` | 40 | Multi-Achs-System (Gantry) | — | Kombinierte Einheit ×1 | 图片 1 | 龙门判断错误 | 被横轴名称误导，否定了已满足的龙门条件 c | 确定 |
| `0804KS8037` | 50 | Multi-Achs-System (Gantry) | — | Kombinierte Einheit ×1 | 图片 1 | 龙门判断错误 | 混淆基础轴和横轴，误判为单侧悬臂 | 确定（行号待照片核对） |
| `0804KV2157` | 52 | Kombinierte Einheit | — | Multi-Achs-System (Gantry) ×1 | 图片 1 | 龙门判断错误 | 违反龙门条件 c（单侧悬臂）并漏看旋转轴 | 确定 |
| `0804DN9616` | 9 | Multi-Achs-System (Gantry) | — | Lineareinheit ×3 | 图片 3 | 信息过载 | 上下文过大，无法处理（Kontext ist zu groß） | 较确定：原文只说上下文过大 |
| `0804FC1588` | 3 | Multi-Achs-System (Gantry) | Kombinierte Einheit | Keine der verfügbaren Klassen ×2 | 图片 2 | 信息过载 | 图片输入共 142 张图，分 10 批发送；Flash 和 Pro 都把装配体描述为机器人工具快换系统，并据此判为不属于任何可用类别。PDF 和文本输入都识别出门架加摆动轴。来源：作者补充的各次运行推理 | 确定 |
| `0804GE7738` | 6 | Rotationseinheit | Kombinierte Einheit | Lineareinheit ×4 | 图片 4 | 信息过载 | 图片输入共 41 张图，分 3 批发送；四个模型都只描述了外购的 Aventics GPC-BV 导向气缸（数据表），按单根平移轴判为直线单元，漏掉了 SCHUNK 旋转单元。PDF 和文本输入都识别出旋转单元。来源：作者补充的各次运行推理 | 确定 |
| `0804CC2134` | 18 | Roboter | Kombinierte Einheit | Rotationseinheit ×1, Keine der verfügbaren Klassen ×2, Greifer ×1 | 图片 4 | 信息过载 | 只拿到快换装置的资料，缺主图纸和主 BOM | 确定 |
| `0804EK1683` | 19 | Roboter | — | Rotationseinheit ×1, Keine der verfügbaren Klassen ×3 | 图片 4 | 信息过载 | 同 CC2134，只看到快换装置的资料 | 确定 |
| `0804GD6171` | 21 | Roboter | — | Keine der verfügbaren Klassen ×4 | 图片 4 | 信息过载 | 65 张图片，主装配体的 1–2 页淹没在快换装置目录里 | 确定 |
| `0804FH4760` | 22 | Roboter | — | Keine der verfügbaren Klassen ×3 | 图片 3 | 信息过载 | 快换装置的长篇手册一起发送，主图纸被忽略 | 确定 |
| `0804KE7723` | 25 | Multi-Achs-System (Gantry) | — | Kombinierte Einheit ×3 | 图片 1, 文本 2 | 信息过载 | 9 页报价文本盖过了 1 页主图纸；其次还把横梁误读为悬臂（龙门） | 主要原因定为信息过载，次要原因为龙门判断 |
| `0804KZ9488` | 33 | Kombinierte Einheit | — | Rotationseinheit ×2 | 图片 2 | 信息过载 | 摆动单元的厂商数据表一起发送，主图纸和直线模块被忽略 | 确定 |
| `0804FT6844` | 41 | Kombinierte Einheit | — | Lineareinheit ×1 | 图片 1 | 信息过载 | 原文给出两种解释：漏看第二根轴，或 Festo 数据表盖过主图纸；只在图片输入下出错 | 待确认：也可归为执行器计数错误 |
| `0804KK0664` | 48 | Greifer | — | Kombinierte Einheit ×1 | PDF 1 | 信息过载 | 按数据表封面的应用示例图分类，而不是实际装配体 | 确定 |
| `0804JX6656` | 12 | Multi-Achs-System (Gantry) | Kombinierte Einheit, Keine der verfügbaren Klassen | Lineareinheit ×3 | 文本 1, PDF 1, 图片 1 | 资料不一致（CAD/BOM） | 图纸里画有两根带电机的轴（作为参考轮廓），BOM 里却没有这些驱动 | 确定 |
| `0804KW8391` | 14 | Multi-Achs-System (Gantry) | Kombinierte Einheit, Keine der verfügbaren Klassen | Lineareinheit ×4 | PDF 2, 文本 2 | 资料不一致（CAD/BOM） | 同 JX6656：第二个执行器不属于本装配体，实际没有执行器 | 确定 |
| `0804GT0312` | 7 | Kombinierte Einheit | — | Lineareinheit ×4, Multi-Achs-System (Gantry) ×4 | 图片 3, PDF 3, 文本 2 | 资料不一致（CAD/BOM） | 原文：“eindeutig KE, aber 3D fehlerhaft”，3D 模型有误导致难以判断 | 待确认：也可归为“其他” |
| `0804EB6690` | 10 | Kombinierte Einheit | — | Greifer ×4, Rotationseinheit ×2 | 图片 4, PDF 1, 文本 1 | 执行器计数错误 | 被名称“Rotationseinheit”和夹爪误导，漏看升降轴与摆动轴的组合 | 确定 |
| `0804KM9359` | 13 | Rotationseinheit | — | Kombinierte Einheit ×6 | PDF 2, 文本 2, 图片 2 | 执行器计数错误 | 把平行夹爪或手动调节板当成平移轴（T=1） | 确定 |
| `0804FT0436` | 20 | Lineareinheit | — | Kombinierte Einheit ×4 | 图片 3, PDF 1 | 执行器计数错误 | 把三爪夹爪的圆柱外壳看成摆动单元，或被名称“Handling”误导 | 确定 |
| `0804HX0679` | 24 | Rotationseinheit | — | Kombinierte Einheit ×3 | 图片 3 | 执行器计数错误 | 把立柱、顶置电机和竖向同步带看成升降轴 | 确定 |
| `0804AR3766` | 28 | Rotationseinheit | Greifer | Kombinierte Einheit ×2 | PDF 1, 文本 1 | 执行器计数错误 | 把夹爪 3 mm 的手指行程当成平移轴 | 确定 |
| `0804KB7256` | 30 | Rotationseinheit | — | Kombinierte Einheit ×2 | 图片 2 | 执行器计数错误 | 竖向画法的伺服电机在 2D 图纸里被看成升降气缸 | 确定 |
| `0804KY7179` | 32 | Lineareinheit | — | Kombinierte Einheit ×1 | 图片 1 | 执行器计数错误 | 把导杆看成两个气缸，把红色附件看成摆动板 | 确定 |
| `0804LA7293` | 34 | Kombinierte Einheit | — | Greifer ×2 | 图片 2 | 执行器计数错误 | 把同一单元两个终点位置的画法看成两个夹爪，漏算主执行器 | 确定 |
| `0804LH9239` | 35 | Keine der verfügbaren Klassen | — | Kombinierte Einheit ×1, Lineareinheit ×1 | 图片 1, PDF 1 | 执行器计数错误 | 把螺钉、铝型材、轴承座等被动零件当成执行器 | 确定 |
| `0804CE5532` | 38 | Kombinierte Einheit | — | Lineareinheit ×1 | PDF 1 | 执行器计数错误 | 把两根正交的直线轴合并成一根（T=1） | 确定 |
| `0804EV7706` | 39 | Roboter | — | Kombinierte Einheit ×1 | 文本 1 | 执行器计数错误 | 把末端执行器里的紧凑滑台算作主轴，违反 Codebook 第 3 节 | 确定 |
| `0804GA4441` | 43 | Keine der verfügbaren Klassen | — | Kombinierte Einheit ×1 | PDF 1 | 执行器计数错误 | 把被动的 HMI 支臂当成升降气缸和旋转执行器 | 确定 |
| `0804GY2577` | 44 | Kombinierte Einheit | — | Rotationseinheit ×1 | 图片 1 | 执行器计数错误 | 被名称“turning unit”误导，漏看升降气缸和夹爪 | 确定 |
| `0804GZ3046` | 45 | Rotationseinheit | — | Kombinierte Einheit ×1 | 图片 1 | 执行器计数错误 | 把工件夹具的被动导柱和弹簧当成升降轴 | 确定 |
| `0804KM8175` | 49 | Lineareinheit | — | Kombinierte Einheit ×1 | 图片 1 | 执行器计数错误 | 3D 图横躺，同一根轴被算了两次 | 确定 |
| `0804KZ8712` | 53 | Lineareinheit | — | Kombinierte Einheit ×1 | 图片 1 | 执行器计数错误 | 把真空发生器看成摆动单元 | 确定（第 53/54 行配对待核对，两者都属于这一类） |
| `0804LB3626` | 54 | Lineareinheit | — | Kombinierte Einheit ×1 | 图片 1 | 执行器计数错误 | 把被动导轨当成第二根驱动轴 | 确定（同上） |
| `0804LE2661` | 55 | Greifer | Kombinierte Einheit | Rotationseinheit ×1 | 图片 1 | 执行器计数错误 | 把固定的基体看成旋转轴 | 确定（行号待照片核对） |
| `0804LZ1241` | 56 | Rotationseinheit | — | Kombinierte Einheit ×1 | PDF 1 | 执行器计数错误 | 把标准螺钉看成第二个伺服电机和直线轴 | 确定 |
| `3842998383` | 57 | Keine der verfügbaren Klassen | — | Lineareinheit ×1 | 图片 1 | 执行器计数错误 | 把被动滚道的输送方向算作平移轴，违反边界案例 6.8 | 确定 |


## 待作者确认

1. `0804FC1588`、`0804GE7738`：已按作者补充的各次运行推理归为信息过载。
2. `0804FT6844`（信息过载或执行器计数错误）、`0804GT0312`（资料不一致或其他）、`0804KE7723`（信息过载或龙门判断错误）的主要原因。
3. 执行器计数错误这一类是否沿用原幻灯片的名称“Antriebs-Halluzination”，还是按扩展后的范围改名（例如“Fehler bei der Aktorzählung”）。
4. 本表只覆盖输入形式比较的运行；最终配置中 GPT-5.5 和 DeepSeek-V4-Flash 新出现的出错装配体（脚本 12 的 `Fehler_BG` 中标为 NEU）尚需另行归类。
