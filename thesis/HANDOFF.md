# 论文写作交接文档

> 用途：新对话开始时先读这份文档，再读 `thesis/chapter_4.md`，然后从 4.3 继续写。
> 更新日期：2026-11-10（含 4.3 草稿）

---

## 1 论文基本信息

- **题目**：LLM-based functional classification of engineering assemblies（Bosch Baugruppe 功能分类），硕士论文，英文撰写
- **研究所**：IKTD（Institut für Konstruktionstechnik und Technisches Design），与 BMG（Bosch Manufacturing Solutions）合作项目
- **导师（Betreuer）**：Jonas，互称 du
- **篇幅**：研究所一般规定 80 页，Jonas 认为少一些没关系；方法部分不用写太多，实验可以多一些。目标正文约 65–70 页
- **参考论文**：Anja 的硕士论文（同一导师、同一复用项目，研究 Handhabungsbaugruppen 的参数提取，用 Gemini 2.5 Pro）。她的写法是研究所认可的风格，可以引用她的论文作为前序工作（具体怎么引用问 Jonas）
- **研究流程（中期报告的五步）**：Testbasis & Codebook → Labeling-Workshop → Workshop-Auswertung → LLM-Experimente → Ergebnisbewertung

## 2 最终目录（正文约 68 页）

| 章 | 标题 | 页数 |
|---|---|---|
| 1 | Introduction（Motivation, Problem Statement, Objectives and Research Questions, Structure） | 4 |
| 2 | State of Research（2.1 Functional Classification and Reuse / 2.2 Technical Documentation / 2.3 LLMs and Multimodal Models / 2.4 Prompt Design / 2.5 Human Annotation and Reference Labels / 2.6 Related Work and Research Gap） | 13 |
| 3 | Methodology（3.1 Research Design，可简要对应 DRM / 3.2 Comparison Strategy / 3.3 Validity and Reproducibility） | 3 |
| 4 | Labeling Workshop and Ground Truth | 10 |
| 5 | Experimental Evaluation（5.1 Setup and Configurations / 5.2 Metrics and Output Processing / 5.3 Overall Performance and Stability / 5.4 Prompt Design and Model Selection / 5.5 Input Representation / 5.6 Performance Across E1, E2, M / 5.7 Error Analysis / 5.8 Validation on 70 Additional Assemblies / 5.9 Cost and Efficiency / 5.10 Summary） | 24 |
| 6 | Prototype: Bosch Assembly Assistant（Requirements / Architecture and Workflow / Core Functions / Verification and Scope） | 5 |
| 7 | Discussion（Answers to RQs / Role of Rules and Ambiguity / Comparison with State of Research / Implications for Practice / Limitations） | 7 |
| 8 | Conclusion and Outlook | 2 |

- 不写 BMG 现状调查（Jonas 说 Anja 写得太多了，这次不用）
- Workshop 单独一章（第 4 章），实验评价单独一章（第 5 章），这是 Jonas 的要求
- 研究所要求的论文结构是 DRM（RC / DS I / PS / DS II），但不按 DRM 重排目录，只在 3.1 用一两句话说明对应关系

## 3 第 4 章结构与进度

| 小节 | 内容 | 页数 | 状态 |
|---|---|---|---|
| 章节导语 | 目的 + 内容顺序，Anja 风格（一段 3–6 句，用 first / subsequently / concludes，不列小节编号），提到 GT 迭代形成、最终复核在第 5 章 | – | ✅ 已写 |
| 4.1 Assembly Dataset | ①概述 ②领域范围 ③选样标准 ④数据来源 ⑤类别分布（表 4.1）⑥初始标签 | 1.5 | ✅ 已写 |
| 4.2 Classification Scheme and Codebook | 4.2.1 Classes（图 4.1 七类示意图、表 4.2）/ 4.2.2 Decision Logic（图 4.2 流程图） | 2 | ✅ 已写 |
| 4.3 Workshop Design and Implementation | 设计：目标、Excel 模板（五个字段）、用时记录；实施：四次 Workshop、16 名参与者、流程 | 1.5 | 📝 草稿见第 8 节（尚未放入 chapter_4.md） |
| 4.4 Evaluation Procedure | 两人复核流程、E1/E2/M 判定规则、Krippendorff's α 的选用理由和计算范围 | 1.5 | ⏳ |
| 4.5 Results | 4.5.1 GT Review and Regime Distribution / 4.5.2 Inter-Annotator Agreement / 4.5.3 Annotation Time | 2.5 | ⏳ |
| 4.6 Implications for the LLM Evaluation | 按 Regime 分别评价、Allowed-Label-Set Accuracy、人工用时作基准、过渡到第 5 章 | 1 | ⏳ |

正文写在 `thesis/chapter_4.md`，图在 `thesis/figures/`。

## 4 已确认的事实

### 数据集
- 共 199 个装配体：主数据集 129 个（主要实验）+ 补充数据集 70 个（补充实验）
- 领域：BMG 的 Handhabungstechnik；BMG 自行设计制造的非标主装配体和子装配体，不含整个工位和外购件
- 来源：Teamcenter 和 DFC，近约五年的项目，来自德国、中国、土耳其等多国 BMG 项目
- 选样要求：必须有 CAD 数据、技术图纸、结构化 BOM；大多数还有决定主功能的执行器（Aktor）的数据表（不是传感器）
- 补充数据集是为了让整体类别分布更均衡（Jonas 的指令：从主装配体清单中随机选取，按名称识别类别，标签按 Codebook 而非名称确定）。正文只写一句，不展开
- 每个装配体的资料：德文和英文名称、至少 5 张 CAD 截图（1 张等轴测视图 + 4 张从四角拍摄的视图）、技术图纸、BOM、数据表
- DFC = Documentation Tool for Customers：把 SAP 和 Autodesk Vault 中的 BOM、项目结构与技术文档关联起来（有官方文件可引用）。DFC 缺少文档时，从 Teamcenter 生成图纸、导出 BOM
- 人和 LLM 获得的信息相同（名称 + 资料），LLM 的资料只是转换成不同文件格式，并尽量保证各格式信息量一致

### 类别分布（表 4.1，最终分布之后可能还会微调）

| 类别 | 主数据集 | 补充数据集 | 合计 |
|---|---|---|---|
| Gripper | 20 | 10 | 30 |
| Linear Unit | 21 | 10 | 31 |
| Rotary Unit | 18 | 10 | 28 |
| Robot | 20 | 10 | 30 |
| Multi-Axis System (Gantry) | 17 | 5 | 22 |
| Combined Unit | 24 | 5 | 29 |
| None of the Available Classes | 9 | 20 | 29 |
| 合计 | 129 | 70 | 199 |

### Codebook（`workshop/Codebook_Baugruppenklassifikation_V2.md`）
- 七个类别；类别名称最终改回 **Kombinierte Einheit → Combined Unit**（V2 文件中叫 Umsetzeinheit，论文不用这个名称）
- 按主导主功能（dominierende Hauptfunktion）分类；统计旋转执行器 R 和平移执行器 T，按决策表确定类别；Case A（R=0, T=0：判断有无夹持功能）、Case B（R=0, T≥2：龙门测试三项）；八个边界案例
- 四次 Workshop 都用同一版本，**论文不提版本更迭和修订次数**（是否写“与导师共同制定”之后问 Jonas）
- Codebook 规定的五个记录字段：① Baugruppenklasse（必填）② Konfidenz：sicher / eher sicher / eher unsicher / unsicher（必填）③ Zweitwahl（有歧义时）④ Ausschlaggebende Quelle（未仅凭 Excel 列表判断时）⑤ Notiz（不确定、选第 7 类或填了第二选择时）
- 时间预算：每个装配体约 2 分钟
- 最低信息要求：仅凭名称和图片不够，至少查阅一种 Teamcenter / DFC 资料
- 第 7 类不能作为困难或歧义情况的退路
- 第 7 类的典型例子：机架、旋转支臂上的操作面板、传感器单元

### Workshop
- 共四次 Workshop，16 名参与者：4 名工程师、12 名学生（与中期报告一致）
  - 前三次：11 人（4 名工程师、7 名学生），每人标注 129 个中的一部分，合起来覆盖全部 129 个
  - 第四次：另外 5 名学生（不在前三次的 7 人中），每人标注全部 70 个
- 论文整体描述 16 人，不单独强调第四次（流程、Codebook、模板都相同）
- 每个装配体由 5–10 人独立标注（已核实；正文只写这一句，不展开分组。工程师只标注了主数据集中的 32 个装配体，比较工程师和学生用时时注意这一点）
- 先用约 10 分钟阅读 Codebook，再分类；可以在 Teamcenter 和 DFC 中查资料
- 用时由 Excel 模板自动记录时间戳；没有剔除异常值，也没有计算中位数。4.3 只写“由时间戳得出处理时间”，不写计算细节；4.5.3 暂定只报告平均值，用户之后审阅数据再决定是否补充
- Excel 模板实际有备注（Notiz）列；PPT 里的模板图没有这一列，图 4.3 需补一列或在图题中注明是简化示意
- 正文用 “individually” 即可，不用强调参与者之间不讨论
- Workshop 目标：验证分类体系 + 记录人工分类结果和用时

### Ground Truth（三阶段迭代）
1. **初始标签**：根据 Teamcenter 中的名称和资料，经人工初步审核得出（一部分由导师提供、一部分由作者整理；论文只统一写一句，不区分来源）
2. **Workshop 后复核**：两人对照 Codebook 和原始资料复核，划分 E1/E2/M → 第 4 章的 α 和 Regime 分布基于这一版
3. **LLM 实验后复核**：发现有些 GT 是 LLM 对了而当时复核遗漏的，又修正了一些 → 写在 5.2，需透明说明：触发条件、复核规则（依据资料而不是 LLM 答案）、修改数量、统一用于所有配置；建议做修正前后的敏感性分析；Limitations 里说明可能偏向 LLM

### Regime（歧义分类）
- **E1（eindeutig）**：全体一致，复核后确认 GT 符合 Codebook
- **E2（eindeutig）**：有少数不同意见，复核后仍判定为明确，GT 符合 Codebook
- **M（mehrdeutig）**：有不同意见，复核后允许多个标签
- 英文用词要统一，建议用 “ambiguity regime” 或 “agreement category”，并在第一次出现时定义；要说清 E2 和 M 的区别
- M 类的多个允许标签：对意见不一致的装配体，人工对照资料和 Codebook 分析得出

### 结果数据
- Krippendorff's α 基于全部 199 个装配体（中期报告 PPT 标注为 129 个是错的）：E1+E2 = 0.806；E1+E2+M = 0.751；M 单独 = 0.463（不一定写进论文）
- 平均用时（基于 199 个，含第四次研讨会）：工程师 31 秒/个，学生 42 秒/个
- 典型歧义案例：**Hubeinheit**（不是 Codebook 里的例子，是复核时遇到的）——名称暗示 Linear Unit，但有一个次要旋转部件间接实现升降，所以是 M，允许 Linear Unit 和 Combined Unit → 放在 4.5.1

## 5 写作规则与风格决定

- **语言**：英文；不用 I/we/man，用被动语态或 “this thesis / this study”；避免填充词和最高级（also, very, extremely, clearly …）
- **交付格式**：每段英文后附中文对照（用户要求）
- **章节导语**：Anja 风格，一段，先说目的，再用顺序词概述内容，不列小节编号
- **段落开头**：不用加粗的引导词，用清楚的主题句开头
- **缩写**：第一次正式讨论时写“全称（缩写）”，不写 hereinafter；BMG、LLM 等在第 1 章已定义，第 4 章直接用缩写；DFC 在 4.1 定义；顺带提到的术语只写全称
- **三级标题**：只在内容超过约 2 页、有并列部分时使用（第 4 章只有 4.2 和 4.5 分三级）
- **结构**：方法与结果分开写（4.4 评价方法 / 4.5 结果），不完全照搬演讲顺序
- **类别名称与顺序全文统一**：Gripper, Linear Unit, Rotary Unit, Robot, Multi-Axis System (Gantry), Combined Unit, None of the Available Classes（表 4.1、表 4.2 都按这个顺序；正文第一次写 “Multi-Axis System (Gantry)”，之后可简称 Gantry）
- **Krippendorff's α 分三处写**：第 2 章（2.5）介绍概念和阈值（≥ 0.800 可靠，0.667–0.800 只能得出初步结论）；4.4 写选用理由和设置（多名标注者、每个装配体标注者不同、名义尺度、计算范围）；4.5 报告结果和解释。建议同时报告全部 199 个的原始 α 作为对照，因为只对 E1+E2 计算会偏高
- **Limitations**：集中写在 Discussion 的局限小节，按数据集 / Workshop 与 GT / 实验 / 原型组织；结果章节中只用一句话提醒前提
- **图表位置**：放在第一次引用的段落之后

## 6 图表

| 编号 | 内容 | 文件 / 状态 |
|---|---|---|
| 表 4.1 | 类别分布（主 / 补充 / 合计） | chapter_4.md |
| 图 4.1 | 七类示意图（用户自己的 PPT 图）。**需要改**：N 值仍是 129 个时的数字（改成 199 个的数字或删掉 N）；“Multi-Achs-System” 改成英文 “Multi-Axis System”；类别顺序与表 4.1、4.2 统一 | 用户自制 |
| 表 4.2 | 类别、判据（R/T）、主功能；表注说明 R、T 的含义并指向 4.2.2 和附录 A | chapter_4.md |
| 图 4.2 | 分类决策流程图（竖版，R 和 T 都按降序，类别统一为浅蓝底深蓝粗体） | `thesis/figures/fig_4_2_decision_flowchart.*`（.dot 是 Graphviz 源文件） |

## 7 待确认 / 待补充

- [ ] DFC 官方文件的引用格式；Teamcenter 与 Autodesk Vault 的关系（BMG 是否两者都在用）
- [ ] 4.1 中“操作类装配体是 BMG 非标设备的核心组成部分”这一理由，向 Jonas 确认
- [ ] 4.2 是否写“Codebook 由作者与导师共同制定”，问 Jonas
- [x] 表 4.1 保留复核前的原始分布，不修改；4.5.1 不报告复核后的类别分布范围。类别 × regime 的表只在第 5 章放一次（最终版 GT）
- [x] 每个装配体由 5–10 人标注（已核实）
- [x] α 和 Regime 分布已基于 199 个（α 见第 5 节“结果数据”，Regime 分布见 `thesis/classification_data_and_revision_statistics.md`）
- [x] 用时 31 秒 / 42 秒已基于 199 个
- [ ] 4.4：α 是在 Excel 中用公式手动搭建计算的（名义尺度，按 Krippendorff 的方法）。用 Python（如 `krippendorff` 包）独立复核一次，确认两边结果一致；正文写 “calculated in Excel following Krippendorff's procedure for nominal data”，复核后可补 “verified with …”
- [ ] 讨论点（4.6 不写，放第 7 章 Role of Rules and Ambiguity）：组合单元 27 个中有 20 个是 E2（个别参与者选了其他类别，但复核后按 Codebook 仍归为组合单元）。4.5.1 只报告数字；另一个可讨论的点：M 有 27 个在主数据集，补充数据集只有 1 个
- [x] 4.4 ⑦ / 4.5.3：工程师只标注了主数据集中的 32 个装配体。决定：正文不说明；按 regime 比较用时也不写
- [x] 第 5 章实验设计（已确认）：
  - 预实验：14 个主数据集装配体（7 E1 / 4 E2 / 3 M），比较输出格式 L1–L4（L1 只输出主标签；L2 + 备选标签和歧义判断；L3 + “无法判断”选项；L4 合并龙门与组合单元），选定 L1。这 14 个之后不参与评价 → 第 5 章评价基于 185 个（主数据集 115 + 补充数据集 70），5.1 必须说明与第 4 章 199 个的差别
  - Prompt 比较：P1 基础（类名）/ P2 + 类别定义 / P3 + 决策逻辑 / P4 + 例子和例外，在 115 个上比较，模型为 Claude Haiku 4.5、Claude Opus 4.8、Gemini 2.5 Flash、Gemini 2.5 Pro → 选定 P3
  - 输入形式比较（P3）：PDF（全部 PDF 文件）/ 图片（CAD 截图、DFC 结构、PDF 转成的页面）/ 文本（从 PDF 和图片中提取的原始文本），同样 4 个模型；图片中的文本用开源 OCR 工具 Tesseract 提取
  - 稳定性：P3，各 10 次：Claude Haiku 4.5 PDF、Gemini 2.5 Pro PDF、GPT-5.5 图片、DeepSeek V4 Flash 文本（Gemini 2.5 Flash PDF 也跑了，用户不打算写）
  - 模型接入（Bosch 内部模型目录）：GPT-5.5 和 DeepSeek-V4-Flash 通过 Azure OpenAI 端点调用；Claude 和 Gemini 通过 Vertex AI 调用。GPT-5.5 用图片输入的理由：Azure OpenAI 上 PDF 输入在服务器端被转成提取文本 + 页面图片，处理过程不透明（且部分端点会忽略 PDF），所以在本地把 PDF 页面转成图片；DeepSeek-V4-Flash 是导师要求纳入的开源（open-weight，MIT 许可）模型，只支持文本输入和输出，所以用文本输入。实验用的版本是 2026-04-23 的（文件名 deepseek-v4-flash-2026-04-23，即 4 月发布的版本，不是 7 月的 0731 正式版）
  - 补充数据集验证：上述 4 种配置在 70 个上各运行一次；合并结果为 `185BG_Ergebnisse/PPT_Ready_185BG_4_Models.xlsx`
  - 章节顺序：Prompt → 输入形式 → 总体表现与稳定性 → E1/E2/M → 错误分析 → 70 个验证 → 成本 → 小结
  - 中期报告 PPT 中的准确率基于旧 GT，论文中要用最终版 GT 重新计算的结果（可能是 `Evaluation_Allowed_Strict.xlsx`）
- [ ] 第 5 章待确认：Gemini 2.5 Flash 是整章不写还是只在稳定性中不写，以及理由；GPT-5.5 当时是否实际试过 PDF 输入；稳定性 10 次运行用的是哪批装配体
- [ ] 第 5 章：实验是否在 Bosch Assembly Assistant 中运行（影响第 6 章的位置和写法）
- [x] 第三阶段 GT 修正的数量（见 `thesis/classification_data_and_revision_statistics.md`）：B → C 有 2 个主标签改类别（Excel 行 8、43），7 个 regime 变为 M（5 个 E1 → M，2 个 E2 → M，均在主数据集），另有几行 M 的其他允许类别有变化（如行 113、125、129）
- [x] Excel 行 112（0804EN7325）：原表在 B 和 C 中都标为 M，但没有其他允许类别（原表就是空白）。决定：按 E2 处理，GT 为 Kombinierte Einheit。调整后 B 阶段为 E1 122 / E2 49 / M 28，C 阶段为 E1 117 / E2 47 / M 35
- [x] Excel 行 43（0804GE7738）在 B 阶段也是 M 且没有其他允许类别。决定：B 阶段保持 M，因为 C 阶段确认它有歧义（C：Rotationseinheit + Kombinierte Einheit）
- [ ] 德文名称栏显示为数字的行（24、44、57、58、60）：确认研讨会模板和 LLM 输入里这一栏是否也是数字；如果是，第 5 章说明输入信息不完整
- [ ] 研究问题（RQ）还没定，可以根据实验拟 2–3 个
- [ ] Jonas 的 2-Pager 用了用户的实验结果，论文中如何引用，问 Jonas

## 8 4.3 草稿（已与用户讨论确认）

**4.3 Workshop Design and Implementation**

The labeling workshop pursued two objectives: to validate the classification scheme on real assemblies and to record human classifications together with the time required for each assembly. The recorded classifications form the basis of the ground truth, while the processing times serve as a reference for assessing the efficiency of the LLM-based classification in Chapter 5.

标注 Workshop 有两个目标：用真实装配体验证分类体系，以及记录人工分类结果和每个装配体所需的时间。记录的分类结果是参考标签的基础，用时则作为第 5 章评价 LLM 分类效率的参照。

Classifications were recorded in an Excel template with one row per assembly (Figure 4.3). For each assembly, participants had to enter the class and their confidence on a four-level scale ranging from *certain* to *uncertain*. If a second class was also plausible, it was entered as a second choice; if the decision was based on documents beyond the information provided in the template, the decisive source, such as the 3D view, the drawing or the bill of materials, was noted. A short note was required for uncertain classifications, for the class *None of the Available Classes* and whenever a second choice was given. The confidence thus captures uncertainty, whereas the second choice captures ambiguity between classes. A timestamp was recorded automatically for each entry, from which the processing time per assembly was derived.

分类结果记录在 Excel 模板中，每个装配体一行（图 4.3）。参与者必须为每个装配体填写类别和置信度，置信度分为从“确定”到“不确定”四个等级。如果另一个类别也合理，就填入“第二选择”；如果判断依据超出了模板中提供的信息，就注明起决定作用的资料来源，例如 3D 视图、图纸或物料清单。对于不确定的分类、归入“不属于任何可用类别”的装配体，以及填写了第二选择的情况，还需写一条简短备注。因此，置信度记录的是不确定性，第二选择记录的是类别之间的歧义。每条记录都会自动生成时间戳，由此得出每个装配体的处理时间。

The workshop was conducted in four sessions with a total of 16 participants, comprising four engineers and 12 students. All sessions followed the same procedure. Participants first read the codebook for approximately ten minutes to establish a common basis for the classification. They then classified the assemblies individually, using Teamcenter and DFC for further research where required, with a time budget of approximately two minutes per assembly. Each participant classified a subset of the assemblies, so that each assembly was classified independently by five to ten participants.

Workshop 分四次进行，共 16 名参与者，其中 4 名工程师、12 名学生。各次 Workshop 采用相同的流程。参与者先用约 10 分钟阅读 Codebook，为分类建立统一基础；随后独立对装配体分类，必要时可在 Teamcenter 和 DFC 中查阅资料，每个装配体的时间预算约为 2 分钟。每名参与者分类一部分装配体，每个装配体由 5 至 10 名参与者独立分类。

*Figure 4.3: Simplified structure of the classification template used in the labeling workshop*（用 PPT 中的模板示意图，去掉 BMG 页眉页脚；补上 Note 列或保留“Simplified”）
