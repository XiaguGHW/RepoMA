# 5 Experimental Evaluation

The LLM-based classification is evaluated in this chapter using the ground truth established in Chapter 4 as the reference. After the experimental setup and the evaluation metrics, the chapter first reports the selection of prompt and input representation and then the performance, stability and errors of the final configurations. The chapter concludes by validating the final configurations on the supplementary set and comparing their cost and processing time with those of human classification.

本章以第 4 章建立的 Ground Truth 为参考，评价基于 LLM 的分类。在介绍实验设置和评价指标之后，本章先报告 Prompt 和输入形式的选择，再报告最终配置的表现、稳定性和错误。最后，在补充数据集上验证最终配置，并将其成本和处理时间与人工分类进行比较。

## 5.1 Setup and Configurations | 实验设置与配置

**① 评价数据集与预实验**

The experiments are based on the 199 assemblies described in Section 4.1. A preliminary experiment was conducted before the main experiments to establish what information the models should return for each assembly. Fourteen assemblies from the primary set, two per class, were classified with Gemini 2.5 Pro in four output formats, which requested either only the primary class or additional information such as alternative classes. The format requesting only the primary class achieved results at least as good as those of the other formats. It corresponds to the codebook rule of assigning exactly one class to each assembly (Section 4.2.1) and allows predictions to be evaluated directly against the allowed label sets without additional scoring rules. All subsequent experiments therefore adopted this output format (Appendix [X]). The 14 assemblies were excluded from the evaluation, which thus covers 185 assemblies: the remaining 115 of the primary set and the 70 of the supplementary set. The results are all based on the final ground truth, with its revision and distribution by class and ambiguity regime presented in Section 5.2.

实验以第 4.1 节介绍的 199 个装配体为基础。在主要实验之前，通过预实验确定模型对每个装配体应返回哪些信息。从主数据集中选取 14 个装配体，每类 2 个，使用 Gemini 2.5 Pro 按四种输出格式进行分类。这些格式分别要求仅返回主类别，或同时返回备选类别等补充信息。仅要求返回主类别的格式，其表现至少与其他格式相当。这一格式符合 Codebook 中每个装配体只归入一个类别的规则（第 4.2.1 节），也使预测结果能够直接与允许标签集合进行比较，无需额外的计分规则。因此，之后的所有实验均采用这一输出格式（附录 [X]）。这 14 个装配体不参与评价，评价因此涵盖 185 个装配体，即主数据集剩余的 115 个和补充数据集的 70 个。所有结果均基于最终版 Ground Truth，其修订以及各类别和歧义类别的分布见第 5.2 节。

**② 实验顺序**

Each experimental stage built on the preceding stage, following a fixed sequence (Table 5.1). Prompt variants and input representations were compared on the 115 assemblies with four models from two providers. The final configurations selected through these comparisons (Section 5.5) were each evaluated in ten runs on the same assemblies to assess performance and stability, as identical requests can produce different LLM outputs (Atil et al., 2024), and in one run on the supplementary set. Since the prompt and the input representation were selected on the primary set, the results on these assemblies may be optimistic. As the supplementary set was excluded from all selection steps, it provides a basis for checking whether the final configurations maintain their performance on additional assemblies (Cawley & Talbot, 2010).

实验按固定顺序进行，每个阶段均以前一阶段为基础（表 5.1）。Prompt 变体和输入形式的比较在这 115 个装配体上进行，使用来自两家厂商的四个模型。通过这些比较选出的最终配置（第 5.5 节）在同一批装配体上各运行十次，用于评价表现和稳定性，因为相同请求可能产生不同的 LLM 输出（Atil et al., 2024）。此外，每种最终配置还在补充数据集上运行一次。由于 Prompt 和输入形式均在主数据集上选定，这些装配体上的结果可能偏乐观。补充数据集未参与任何选择步骤，因此用来检验最终配置在其他装配体上能否保持其表现（Cawley & Talbot, 2010）。

**Table 5.1. Experimental stages / 表 5.1 实验阶段**

| Stage / 阶段 | Assemblies / 装配体 | Prompt | Input / 输入 | Models / 模型 | Runs / 次数 | Section / 节 |
| --- | --- | --- | --- | --- | --- | --- |
| Prompt comparison / Prompt 比较 | 115 | P1–P4 | PDF | Haiku 4.5, Opus 4.8, Gemini 2.5 Flash, Gemini 2.5 Pro | 1 | 5.3 |
| Input comparison / 输入形式比较 | 115 | P3 | PDF, image, text | as above / 同上 | 1 | 5.4 |
| Performance and stability / 表现与稳定性 | 115 | P3 | final / 最终配置 | 4 final configurations / 4 种最终配置 | 10 | 5.5–5.7 |
| Validation / 验证 | 70 | P3 | final / 最终配置 | 4 final configurations / 4 种最终配置 | 1 | 5.8 |

**③ 模型与运行方式**

Six models from four providers were used: Claude Haiku 4.5 and Claude Opus 4.8 (Anthropic), Gemini 2.5 Flash and Gemini 2.5 Pro (Google), GPT-5.5 (OpenAI) and DeepSeek-V4-Flash (DeepSeek) (access and model versions in Appendix [Y]). A separate request was submitted for each assembly, with no information carried over from earlier requests. The temperature was set to 0 for all models. As the codebook rules define a single correct class for this decision task, the aim is to obtain the most probable output and avoid variation between outputs, while a temperature of 0 also supports reproducibility. Requests that returned an empty output were identified after each run and repeated individually. Once these requests had been repeated, a valid output was available for every assembly, and each output contained one of the seven class names. The token usage of each request was recorded for the cost analysis.

实验使用了来自四家厂商的六个模型，包括 Claude Haiku 4.5 和 Claude Opus 4.8（Anthropic）、Gemini 2.5 Flash 和 Gemini 2.5 Pro（Google）、GPT-5.5（OpenAI），以及 DeepSeek-V4-Flash（DeepSeek）（接入方式和模型版本见附录 [Y]）。每个装配体通过单独的请求进行分类，不带入此前请求的信息。所有模型的 temperature 均设为 0。由于这一决策任务按 Codebook 规则只有一个正确类别，因此目标是获得最可能的输出并避免输出之间的变化，同时 temperature 为 0 也有助于提高可复现性。每轮运行后，找出输出为空的请求并单独重新运行。重新运行后，每个装配体均有有效输出，且每个输出都包含七个类别名称之一。每次请求的 token 用量均被记录，用于成本分析。

## 5.2 Ground Truth Revision and Evaluation Metrics | Ground Truth 修订与评价指标

This section presents the final revision of the ground truth before introducing the metrics and statistical methods used in the following sections.

本节先介绍 Ground Truth 的最终修订，再说明后续各节采用的评价指标和统计方法。

**① 修订的触发**

The LLM experiments led to a final review of the ground truth. Following the procedure in Section 4.4, the review covered every assembly for which at least one configuration predicted a class outside its allowed label set.

LLM 实验之后，对 Ground Truth 进行了最终复核。只要至少一种配置对某个装配体预测了其允许标签集合以外的类别，就按第 4.4 节的流程对该装配体重新复核。

**② 修订结果**

The review reassigned the primary label of one assembly from Linear Unit to Combined Unit and that of another from Combined Unit to Rotary Unit, retaining the previous label as an allowed label in both cases. Seven assemblies were moved to regime M, five from E1 and two from E2, and for three further assemblies in regime M the set of allowed labels was changed. Every change was made within the primary set. Across all 199 assemblies, the final ground truth comprises 117 assemblies in regime E1, 47 in E2 and 35 in M. The final ground truth was used for every configuration and experimental stage.

复核后，一个装配体的主标签由直线单元改为组合单元，另一个由组合单元改为旋转单元。两个装配体的原标签均保留为允许标签。有七个装配体改为 M，其中五个原属 E1，两个原属 E2。另有三个原属 M 的装配体调整了允许标签集合。这些修改均发生在主数据集。在全部 199 个装配体中，最终版 Ground Truth 有 117 个属于 E1、47 个属于 E2、35 个属于 M。所有配置和实验阶段均采用最终版 Ground Truth。

**③ 评价数据集的分布**

Table 5.2 shows the distribution of the 185 evaluated assemblies across classes and ambiguity regimes according to the final ground truth.

表 5.2 列出了 185 个参与评价的装配体按最终版 Ground Truth 在各类别和歧义类别中的分布。

**Table 5.2. Evaluated assemblies by class and ambiguity regime (final ground truth) / 表 5.2 参与评价的装配体按类别和歧义类别的分布（最终版 Ground Truth）**

| Class / 类别 | Primary (115) E1 / E2 / M | Supplementary (70) E1 / E2 / M | Total / 合计 |
| --- | --- | --- | ---: |
| Gripper / 夹爪 | 9 / 3 / 6 | 7 / 3 / 0 | 28 |
| Linear Unit / 直线单元 | 11 / 3 / 5 | 7 / 2 / 1 | 29 |
| Rotary Unit / 旋转单元 | 5 / 5 / 7 | 9 / 1 / 0 | 27 |
| Robot / 机器人 | 13 / 0 / 5 | 10 / 0 / 0 | 28 |
| Multi-Axis System (Gantry) / 多轴系统（龙门） | 8 / 3 / 5 | 4 / 1 / 0 | 21 |
| Combined Unit / 组合单元 | 1 / 17 / 2 | 3 / 2 / 0 | 25 |
| None of the Available Classes / 不属于任何可用类别 | 4 / 3 / 0 | 19 / 1 / 0 | 27 |
| **Total / 合计** | **51 / 34 / 30** | **59 / 10 / 1** | **185** |

*Note: Classes refer to the primary label.*

注：类别指主标签。

**④ 指标**

With $C$ denoting the set of seven classes, each assembly $i$ ($i = 1, \dots, N$) has a predicted class $\hat{y}_i$, a primary label $y_i$ and a set of allowed labels $A_i$ that contains $y_i$ ($y_i \in A_i$). The main metric is the Allowed Accuracy defined in Section 4.6, which follows evaluation practice for datasets with several valid labels per item (Shankar et al., 2020; Beyer et al., 2020):

$$\text{Allowed Accuracy} = \frac{1}{N} \sum_{i=1}^{N} \mathbb{1}\left[\hat{y}_i \in A_i\right] \tag{5.1}$$

设 $C$ 为七个类别的集合。对于每个装配体 $i$（$i = 1, \dots, N$），$\hat{y}_i$ 表示预测类别，$y_i$ 表示主标签，$A_i$ 表示包含主标签的允许标签集合（$y_i \in A_i$）。主要指标是第 4.6 节定义的 Allowed Accuracy，它沿用了每个样本有多个有效标签时的评价做法（Shankar et al., 2020; Beyer et al., 2020）。

Class-specific performance is described by Allowed Precision and Allowed Recall, which apply the standard definitions (Sokolova & Lapalme, 2009) to the allowed label sets:

$$\text{AP}_c = \frac{\left|\{\, i : \hat{y}_i = c \,\wedge\, c \in A_i \,\}\right|}{\left|\{\, i : \hat{y}_i = c \,\}\right|} \qquad \text{AR}_c = \frac{\left|\{\, i : y_i = c \,\wedge\, \hat{y}_i \in A_i \,\}\right|}{\left|\{\, i : y_i = c \,\}\right|} \tag{5.2}$$

Allowed Macro-Precision and Allowed Macro-Recall are the equally weighted averages of the corresponding values across the seven classes. This extension ensures that a prediction counted as correct by the Allowed Accuracy is not counted as an error in precision or recall.

各类别的表现用 Allowed Precision 和 Allowed Recall 描述，即把标准定义（Sokolova & Lapalme, 2009）应用到允许标签集合上。将对应指标在七个类别上的数值分别等权平均，即得 Allowed Macro-Precision 和 Allowed Macro-Recall。这一扩展保证了被 Allowed Accuracy 计为正确的预测，在 Precision 和 Recall 中不会被计为错误。

Only strict F1 is reported because precision and recall under the allowed criterion can refer to different classes for a single prediction. Strict Macro-F1 is the mean of the class-wise F1 values (Opitz & Burst, 2019):

$$\text{Strict Macro-F1} = \frac{1}{|C|} \sum_{c \in C} \frac{2\, \text{P}_c\, \text{R}_c}{\text{P}_c + \text{R}_c} \tag{5.3}$$

where $\text{P}_c$ and $\text{R}_c$ follow from Equation 5.2 with $A_i$ replaced by $\{y_i\}$. This metric reflects how often predictions match the primary label and supports comparison with studies that use a single correct label. For configurations with ten runs, each metric is calculated per run and averaged across the runs.

本文仅报告严格形式的 F1，因为按允许标签准则计算时，同一个预测在 Precision 和 Recall 中可能对应不同的类别。Strict Macro-F1 是各类别 F1 的平均值（Opitz & Burst, 2019）。其中 $\text{P}_c$ 和 $\text{R}_c$ 由公式 5.2 将 $A_i$ 替换为 $\{y_i\}$ 得到。这一指标反映预测与主标签匹配的频率，可用于和仅采用一个正确标签的研究进行比较。对于运行十次的配置，每个指标按每次运行分别计算，再在各次运行之间取平均。

**⑤ 统计方法**

Given the size of the dataset, the results depend on which assemblies it contains. To reflect this dependence, 95 % bootstrap confidence intervals are reported for all values (Efron & Tibshirani, 1993; Miller, 2024). In each of 2,000 resamples, the assemblies were drawn with replacement, each together with its predictions from all runs, and all metrics were recalculated; the 2.5th and 97.5th percentiles of the resulting values form the interval. A paired bootstrap was used to test differences between final configurations by evaluating the two configurations in each comparison on the same resampled assemblies (Koehn, 2004; Berg-Kirkpatrick et al., 2012). The test covers Allowed Accuracy, Allowed Macro-Precision, Allowed Macro-Recall and Strict Macro-F1. The Holm procedure (Holm, 1979) was used to adjust the p-values for the six pairwise comparisons per metric, with a separate adjustment for each metric because they address different questions (Bender & Lange, 2001).

由于数据集规模有限，结果取决于数据集中包含哪些装配体。为反映这种依赖关系，所有数值均报告通过 Bootstrap 得到的 95% 置信区间（Efron & Tibshirani, 1993; Miller, 2024）。在 2000 次重抽样中，每次都有放回地抽取装配体，每个装配体带上它在所有运行中的预测，并重新计算所有指标。所得数值的第 2.5 和第 97.5 百分位数构成置信区间。最终配置之间的差异采用配对 Bootstrap 检验，每次比较的两种配置都在同一批重抽样的装配体上评价（Koehn, 2004; Berg-Kirkpatrick et al., 2012）。检验涵盖 Allowed Accuracy、Allowed Macro-Precision、Allowed Macro-Recall 和 Strict Macro-F1。每个指标的六组两两比较所得 p 值采用 Holm 方法校正（Holm, 1979）。各指标回答不同的问题，因此分别进行校正（Bender & Lange, 2001）。

## 5.3 Prompt Design | Prompt 设计

**① 目的与 Prompt 变体**

Because prompt design can substantially affect LLM performance (Sclar et al., 2024), the amount of codebook information in the prompt was varied to identify what the models need to classify the assemblies. Four prompt variants were defined, each extending the previous one. Starting with the class names in P1, the variants successively add the class definitions in P2, the decision logic in P3 (actuator counting rules, decision table and gantry test), and examples and exceptions in the form of borderline cases in P4. All other parts of the prompt, including the output format and the instruction to base the decision on the documentation rather than on the designation alone, were identical across the variants (Appendix [W]).

Prompt 的设计可能显著影响 LLM 的表现（Sclar et al., 2024）。本研究通过改变 Prompt 中提供的 Codebook 信息量，确定模型对装配体分类时需要哪些信息。本研究定义了四种 Prompt 变体，每种都在前一种的基础上扩展。P1 只包含类别名称。P2 增加类别定义，P3 增加决策逻辑，包括执行器计数规则、决策表和龙门测试，P4 再以边界案例的形式补充例子和例外。各变体中 Prompt 的其他部分都相同，包括输出格式，以及要求依据资料而不是只凭名称作出判断的说明（附录 [W]）。

**② 结果**

Table 5.3 shows the Allowed Accuracy of the four models with PDF input. The largest change occurred when P3 added the decision logic, raising Allowed Accuracy by 2.6 to 8.8 percentage points across the four models compared with P2. In contrast, adding the class definitions in P2 did not yield a consistent improvement over P1; the accuracy increased for Claude Haiku 4.5, remained almost unchanged for the two Gemini models and decreased for Claude Opus 4.8. The effect of the examples and exceptions in P4 also varied by model, with accuracy rising for Claude Haiku 4.5 and Gemini 2.5 Pro and falling for Claude Opus 4.8 and Gemini 2.5 Flash, with each change corresponding to at most two assemblies.

表 5.3 列出了四个模型使用 PDF 输入时的 Allowed Accuracy。加入决策逻辑的 P3 带来的变化最大。与 P2 相比，四个模型的 Allowed Accuracy 均提高了 2.6 至 8.8 个百分点。相比之下，P2 加入类别定义后，相对于 P1 没有带来一致的提升：Claude Haiku 4.5 的准确率提高，两个 Gemini 模型基本不变，Claude Opus 4.8 则有所下降。P4 中的例子和例外对各模型的影响也不同。Claude Haiku 4.5 和 Gemini 2.5 Pro 的准确率提高，Claude Opus 4.8 和 Gemini 2.5 Flash 的准确率下降。各模型正确分类的装配体数量变化均不超过两个。

**Table 5.3. Allowed Accuracy (%) by prompt variant (PDF input, 115 assemblies) / 表 5.3 各 Prompt 变体的 Allowed Accuracy（%）（PDF 输入，115 个装配体）**

| Model / 模型 | P1 | P2 | P3 | P4 |
| --- | ---: | ---: | ---: | ---: |
| Claude Haiku 4.5 | 85.2 | 87.8 | 90.4 | 92.2 |
| Claude Opus 4.8 | 93.9 | 91.2 | **97.4** | 95.6 |
| Gemini 2.5 Flash | 89.4 | 89.3 | **93.7** | 92.0 |
| Gemini 2.5 Pro | 87.7 | 87.7 | 96.5 | 97.4 |
| Mean / 平均 | 89.0 | 89.0 | **94.5** | 94.3 |

*Note: One run per configuration; 95 % confidence intervals in Appendix [W].*

注：每种配置运行一次；95% 置信区间见附录 [W]。

**③ 选择 P3**

The mean Allowed Accuracy across the four models was highest with P3. Since P4 did not improve the results consistently, the additional examples and exceptions were not adopted, and P3 was used in all subsequent experiments. The results suggest that the codebook's decision logic contributes more to the models' ability to apply the classification rules than the class definitions or individual examples. As P3 was selected on the 115 assemblies of the primary set, its performance is examined on the supplementary set in Section 5.8.

使用 P3 时，四个模型的平均 Allowed Accuracy 最高。由于 P4 没有带来一致的提升，例子和例外没有采用，之后的所有实验都使用 P3。结果表明，与类别定义或个别例子相比，Codebook 的决策逻辑更有助于模型应用分类规则。由于 P3 是在主数据集的 115 个装配体上选定的，第 5.8 节将在补充数据集上检验它的表现。

## 待处理

### 5.1 待办

- [ ] **附录 [X]**：L1–L4 的结果，按最终版 GT 重算。
- [ ] **附录 [Y]**：接入方式、模型版本号、输入转换设置、生成参数。
- [ ] **GPT-5.5 的 temperature**：查请求日志确认确实是 0。

### 5.2 待办

- [ ] **p 值的算法**：对照 `evaluate_allowed_strict.py` 确认配对 Bootstrap 的 p 值如何得出。
- [ ] **偏向说明**：只复核了预测错误的装配体，修订可能使 LLM 结果偏好。问过 Jonas 后决定写在 5.2 还是第 7 章，以及是否做修订前 GT 的敏感性分析（附录 [Z]）。

### 5.3 待办

- [ ] **置信区间**：表 5.3 各值的 95% CI，放附录 [W]；补上后可改成带误差棒的分组柱状图（图 5.1），表移到附录。
- [ ] **分母**：Prompt 比较中 Opus（114）、Flash（111–113）、Pro（113–114）的分母不是 115（空输出未补跑；Haiku 已重跑，为 115）。问过 Jonas 后在表注中说明，或补跑。5.1 ③ 暂不改。
- [ ] **可选核对**：Strict Macro-F1 的趋势是否也支持 P3；一致则加一句 “Strict Macro-F1 showed the same pattern (Appendix [W])”。
- 已确认：数字基于最终版 GT；P4 的例子为作者自拟，不取自数据集；P3 + PDF 在 5.3 和 5.4 中是两次独立运行，5.4 开头需说明数字略有不同的原因。

### 章节安排

- 5.4：三种输入形式的定义（含 Tesseract，Smith, 2007）和比较结果（表 5.4）；说明 PDF 这组与 5.3 的 P3 是两次独立运行。
- 5.5 开头：四种最终配置，每个模型一点，写明输入形式和选择理由（Haiku 不选 Opus 因成本；Pro 优于 Flash；Haiku 和 Pro 选 PDF 而非文本：只差一个装配体、PDF 平均最高、无需单独提取步骤；GPT-5.5 因 Azure OpenAI 的 PDF 转换不可控而用图片；DeepSeek 只支持文本）。
- 附录 [X]：预实验 L1–L4 结果；[Y]：接入方式、模型版本、输入转换设置、生成参数；[W]：Prompt 原文、各阶段置信区间、完整指标。
