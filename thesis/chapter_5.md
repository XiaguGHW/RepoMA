# 5 Experimental Evaluation

The LLM-based classification is evaluated in this chapter using the ground truth established in Chapter 4 as the reference. After the experimental setup and the evaluation metrics, the chapter first reports the selection of prompt and input representation. It then examines the stability of the final configurations, validates them on the supplementary set, reports their performance across the ambiguity regimes and analyses their errors. The chapter concludes by comparing their cost and processing time with those of human classification.

本章以第 4 章建立的 Ground Truth 为参考，评价基于 LLM 的分类。在介绍实验设置和评价指标之后，本章先报告 Prompt 和输入形式的选择，然后检验最终配置的稳定性，在补充数据集上对其进行验证，报告其在各歧义类别中的表现，并分析其错误。最后，将其成本和处理时间与人工分类进行比较。

## 5.1 Setup and Configurations | 实验设置与配置

**① 评价数据集与预实验**

The experiments are based on the 199 assemblies of the dataset. A preliminary experiment was conducted before the main experiments to establish what information the models should return for each assembly. Fourteen assemblies from the primary set, two per class, were classified with Gemini 2.5 Pro in four output formats, which requested either only the primary class or additional information such as alternative classes. The format requesting only the primary class achieved results at least as good as those of the other formats. It corresponds to the codebook rule of assigning exactly one class to each assembly and allows predictions to be evaluated directly against the allowed label sets without additional scoring rules. All subsequent experiments therefore adopted this output format. The 14 assemblies were excluded from the evaluation, which thus covers 185 assemblies: the remaining 115 of the primary set and the 70 of the supplementary set. The results are all based on the final ground truth, with its revision and distribution by class and ambiguity regime presented in Section 5.2.

实验以数据集中的 199 个装配体为基础。在主要实验之前，通过预实验确定模型对每个装配体应返回哪些信息。从主数据集中选取 14 个装配体，每类 2 个，使用 Gemini 2.5 Pro 按四种输出格式进行分类。这些格式分别要求仅返回主类别，或同时返回备选类别等补充信息。仅要求返回主类别的格式，其表现至少与其他格式相当。这一格式符合 Codebook 中每个装配体只归入一个类别的规则，也使预测结果能够直接与允许标签集合进行比较，无需额外的计分规则。因此，之后的所有实验均采用这一输出格式。这 14 个装配体不参与评价，评价因此涵盖 185 个装配体，即主数据集剩余的 115 个和补充数据集的 70 个。所有结果均基于最终版 Ground Truth，其修订以及各类别和歧义类别的分布见第 5.2 节。

**② 实验顺序**

Each experimental stage built on the preceding stage, following a fixed sequence (Table 5.1). Prompt variants and input representations were compared on the 115 assemblies with four models from two providers. The final configurations selected through these comparisons were each evaluated in ten runs on the same assemblies to assess performance and stability, as identical requests can produce different LLM outputs (Atil et al., 2024), and in one run on the supplementary set. Since the prompt and the input representation were selected on the primary set, the results on these assemblies may be optimistic. As the supplementary set was excluded from all selection steps, it provides a basis for checking whether the final configurations maintain their performance on additional assemblies (Cawley & Talbot, 2010).

实验按固定顺序进行，每个阶段均以前一阶段为基础（表 5.1）。Prompt 变体和输入形式的比较在这 115 个装配体上进行，使用来自两家厂商的四个模型。通过这些比较选出的最终配置在同一批装配体上各运行十次，用于评价表现和稳定性，因为相同请求可能产生不同的 LLM 输出（Atil et al., 2024）。此外，每种最终配置还在补充数据集上运行一次。由于 Prompt 和输入形式均在主数据集上选定，这些装配体上的结果可能偏乐观。补充数据集未参与任何选择步骤，因此用来检验最终配置在其他装配体上能否保持其表现（Cawley & Talbot, 2010）。

**Table 5.1. Experimental stages / 表 5.1 实验阶段**

| Stage / 阶段 | Assemblies / 装配体 | Prompt | Input / 输入 | Models / 模型 | Runs / 次数 | Section / 节 |
| --- | --- | --- | --- | --- | --- | --- |
| Prompt comparison / Prompt 比较 | 115 | P1–P4 | PDF | Haiku 4.5, Opus 4.8, Gemini 2.5 Flash, Gemini 2.5 Pro | 1 | 5.3 |
| Input comparison / 输入形式比较 | 115 | P3 | PDF, image, text | as above / 同上 | 1 | 5.4 |
| Performance and stability / 表现与稳定性 | 115 | P3 | final / 最终配置 | 4 final configurations / 4 种最终配置 | 10 | 5.5 |
| Validation / 验证 | 70 | P3 | final / 最终配置 | 4 final configurations / 4 种最终配置 | 1 | 5.6 |

**③ 模型与运行方式**

Six models from four providers were used: Claude Haiku 4.5 and Claude Opus 4.8 (Anthropic), Gemini 2.5 Flash and Gemini 2.5 Pro (Google), GPT-5.5 (OpenAI) and DeepSeek-V4-Flash (DeepSeek) (access and model versions in Appendix B). A separate request was submitted for each assembly, with no information carried over from earlier requests. The temperature was set to 0 for all models. As the codebook rules define a single correct class for this decision task, the aim is to obtain the most probable output and avoid variation between outputs, while a temperature of 0 also supports reproducibility. Requests that returned an empty output were identified after each run and repeated individually. Once these requests had been repeated, a valid output was available for every assembly, and each output contained one of the seven class names. The token usage of each request was recorded for the cost analysis.

实验使用了来自四家厂商的六个模型，包括 Claude Haiku 4.5 和 Claude Opus 4.8（Anthropic）、Gemini 2.5 Flash 和 Gemini 2.5 Pro（Google）、GPT-5.5（OpenAI），以及 DeepSeek-V4-Flash（DeepSeek）（接入方式和模型版本见附录 B）。每个装配体通过单独的请求进行分类，不带入此前请求的信息。所有模型的 temperature 均设为 0。由于这一决策任务按 Codebook 规则只有一个正确类别，因此目标是获得最可能的输出并避免输出之间的变化，同时 temperature 为 0 也有助于提高可复现性。每轮运行后，找出输出为空的请求并单独重新运行。重新运行后，每个装配体均有有效输出，且每个输出都包含七个类别名称之一。每次请求的 token 用量均被记录，用于成本分析。

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

With $C$ denoting the set of seven classes, each assembly $i$ ($i = 1, \dots, N$) has a predicted class $\hat{y}_i$, a primary label $y_i$ and a set of allowed labels $A_i$ that contains $y_i$ ($y_i \in A_i$). The main metric is the Allowed Accuracy, which follows evaluation practice for datasets with several valid labels per item (Shankar et al., 2020; Beyer et al., 2020):

$$\text{Allowed Accuracy} = \frac{1}{N} \sum_{i=1}^{N} \mathbb{1}\left[\hat{y}_i \in A_i\right] \tag{5.1}$$

设 $C$ 为七个类别的集合。对于每个装配体 $i$（$i = 1, \dots, N$），$\hat{y}_i$ 表示预测类别，$y_i$ 表示主标签，$A_i$ 表示包含主标签的允许标签集合（$y_i \in A_i$）。主要指标是 Allowed Accuracy，它沿用了每个样本有多个有效标签时的评价做法（Shankar et al., 2020; Beyer et al., 2020）。

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

Because prompt design can substantially affect LLM performance (Sclar et al., 2024), the amount of codebook information in the prompt was varied to identify what the models need to classify the assemblies. Four prompt variants were defined, each extending the previous one. Starting with the class names in P1, the variants successively add the class definitions in P2, the decision logic in P3 (actuator counting rules, decision table and gantry test), and examples and exceptions in the form of borderline cases in P4. All other parts of the prompt, including the output format and the instruction to base the decision on the documentation rather than on the designation alone, were identical across the variants (Appendix C).

Prompt 的设计可能显著影响 LLM 的表现（Sclar et al., 2024）。本研究通过改变 Prompt 中提供的 Codebook 信息量，确定模型对装配体分类时需要哪些信息。本研究定义了四种 Prompt 变体，每种都在前一种的基础上扩展。P1 只包含类别名称。P2 增加类别定义，P3 增加决策逻辑，包括执行器计数规则、决策表和龙门测试，P4 再以边界案例的形式补充例子和例外。各变体中 Prompt 的其他部分都相同，包括输出格式，以及要求依据资料而不是只凭名称作出判断的说明（附录 C）。

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

*Note: One run per configuration; 95 % confidence intervals in Appendix D.*

注：每种配置运行一次；95% 置信区间见附录 D。

**③ 选择 P3**

The mean Allowed Accuracy across the four models was highest with P3. Since P4 did not improve the results consistently, the additional examples and exceptions were not adopted, and P3 was used in all subsequent experiments. The results suggest that the codebook's decision logic contributes more to the models' ability to apply the classification rules than the class definitions or individual examples.

使用 P3 时，四个模型的平均 Allowed Accuracy 最高。由于 P4 没有带来一致的提升，例子和例外没有采用，之后的所有实验都使用 P3。结果表明，与类别定义或个别例子相比，Codebook 的决策逻辑更有助于模型应用分类规则。

## 5.4 Input Representation | 输入形式

**① 三种输入形式**

The input representation specifies the form in which an assembly's documentation is provided to the model. Three representations were compared, each containing the same documentation in a different file format. The PDF representation contains all PDF files, the image representation contains the CAD screenshots, the DFC structure and PDF pages converted to images, and the text representation consists of raw text extracted from these files, using the open-source OCR engine Tesseract to extract text from images (Smith, 2007). Details of the conversion are given in Appendix B. Prompt P3 was used for the comparison, with the same four models and one run for each configuration. The PDF configuration was run independently of the prompt comparison, so its results differ slightly from those for P3 in Table 5.3.

输入形式规定了装配体资料提供给模型时所采用的形式。本研究比较了三种输入形式，它们包含同一份资料，只是文件格式不同。PDF 形式包含全部 PDF 文件，图片形式包含 CAD 截图、DFC 结构和转换为图片的 PDF 页面。文本形式由从这些文件中提取的原始文本组成，图片中的文字使用开源 OCR 工具 Tesseract 提取（Smith, 2007）。转换的具体设置见附录 B。该比较使用 Prompt P3 和相同的四个模型，每种配置运行一次。PDF 配置与 Prompt 比较是分开独立运行的，因此其结果与表 5.3 中 P3 的结果略有不同。

**② 结果**

Table 5.4 shows that the image representation yielded the lowest Allowed Accuracy for all four models, between 9 and 14 percentage points below the PDF representation. Text input produced slightly higher values for three models, while the largest difference between it and PDF input occurred for Claude Opus 4.8 and favoured PDF input, so neither representation was consistently superior. On average, both representations reached a similar level of 94.8 % and 94.6 %.

表 5.4 显示，图片输入在四个模型上的 Allowed Accuracy 都最低，比 PDF 输入低 9 至 14 个百分点。PDF 和文本输入各有优势。文本输入在三个模型上得到略高的数值，而两种输入形式之间最大的差异出现在 Claude Opus 4.8 上，PDF 输入的结果更高。平均而言，两种输入形式达到相近的水平，分别为 94.8% 和 94.6%。

**Table 5.4. Allowed Accuracy (%) by input representation (P3, 115 assemblies) / 表 5.4 各输入形式的 Allowed Accuracy（%）（P3，115 个装配体）**

| Model / 模型 | PDF | Image / 图片 | Text / 文本 |
| --- | ---: | ---: | ---: |
| Claude Haiku 4.5 | 91.3 | 80.0 | 92.2 |
| Claude Opus 4.8 | 97.4 | 87.0 | 92.2 |
| Gemini 2.5 Flash | 93.9 | 79.8 | 96.5 |
| Gemini 2.5 Pro | 96.5 | 83.5 | 97.4 |
| Mean / 平均 | **94.8** | 82.6 | 94.6 |

*Note: One run per configuration; 95 % confidence intervals in Appendix D.*

注：每种配置运行一次；95% 置信区间见附录 D。

**③ 图片输入准确率较低的原因**

Of the 129 incorrect classifications produced by the four models in the input comparison, 80 occurred with image input. The reasoning of these classifications points to two causes that occurred only with this representation. First, each document page was supplied as a separate image, allowing extensive supplier documentation to dominate the input. For four robots whose documentation included the multi-page catalogue or manual of a mounted quick-change system, these pages shifted the focus of the models to the quick-change system. As a result, the models primarily considered this passive interface instead of the robot when classifying the assemblies and assigned None of the Available Classes or Rotary Unit, while the same assemblies were classified correctly with PDF and text input. Second, technical drawings were misread: for two rotary units, a vertical belt drive and a vertically drawn servo motor were interpreted as lifting axes, which led to the class Combined Unit.

四个模型在输入形式比较中共产生 129 个错误分类，其中 80 个发生在图片输入下。这些分类的推理过程指向两个只在这种输入形式下出现的原因。第一，每一页资料都作为单独的图片传入，篇幅较大的供应商资料可能占据输入的主要部分。有四个机器人的资料中包含安装在其上的快换装置的多页目录或手册。这些页面使模型的关注点转移到快换装置上。因此，模型分类时主要考虑了这个被动接口而非机器人，并将装配体归为“不属于任何可用类别”或旋转单元。同样的装配体在 PDF 和文本输入下都分类正确。第二，技术图纸被误读：在两个旋转单元中，竖向同步带传动和竖向绘制的伺服电机被理解为升降轴，因此被归为组合单元。

## 5.5 Final Configurations and Stability | 最终配置与稳定性

**① 最终配置**

Four final configurations were defined using the results in Sections 5.3 and 5.4, comprising one model per provider and one open-weight model. They were used for the repeated runs on the primary set and for the validation on the supplementary set:

- **Claude Haiku 4.5** with PDF input. It was chosen instead of Claude Opus 4.8, since the cost of Opus is not justifiable for repeated runs (Section 5.8). Text input correctly classified only one more assembly than PDF input, a difference within the variation between independent runs, while PDF input achieved the highest mean accuracy and requires no separate extraction step.
- **Gemini 2.5 Pro** with PDF input. Its results were higher than those of Gemini 2.5 Flash in both comparisons, and PDF input was retained for the same reasons as for Claude Haiku 4.5.
- **GPT-5.5** with image input. Since PDF files submitted via Azure OpenAI are converted on the server side in a way that cannot be controlled, the PDF pages were converted into images beforehand. This choice ensures that all three input representations are covered by the final configurations.
- **DeepSeek-V4-Flash** with text input. The model was included as an open-weight model released under the MIT licence and supports only text input, which achieved results similar to those of PDF input in Section 5.4.

Since each configuration combines a specific model with a specific input representation, differences between the configurations cannot be attributed to the model or the input alone.

依据第 5.3 和 5.4 节的结果，确定了四种最终配置，包括每家厂商一个模型和一个开放权重模型。它们用于主数据集上的重复运行，以及补充数据集上的验证：

- **Claude Haiku 4.5**，使用 PDF 输入。选择它而不是 Claude Opus 4.8，是因为 Opus 的成本不适合重复运行（第 5.8 节）。文本输入比 PDF 输入仅多正确分类一个装配体，这一差异处于独立运行之间的波动范围内。PDF 输入的平均准确率最高，且不需要单独的提取步骤。
- **Gemini 2.5 Pro**，使用 PDF 输入。它在两项比较中的结果均高于 Gemini 2.5 Flash，保留 PDF 输入的理由与 Claude Haiku 4.5 相同。
- **GPT-5.5**，使用图片输入。由于通过 Azure OpenAI 提交的 PDF 文件会在服务器端以无法控制的方式转换，PDF 页面事先已转换为图片。这一选择使最终配置涵盖了全部三种输入形式。
- **DeepSeek-V4-Flash**，使用文本输入。它作为以 MIT 许可发布的开放权重模型纳入，且只支持文本输入。第 5.4 节显示，文本输入的结果与 PDF 输入相近。

由于每种配置都是某个模型与某种输入形式的组合，配置之间的差异不能单独归因于模型或输入形式。

**② 总体表现**

Table 5.5 presents the final configurations' results averaged across ten runs. Gemini 2.5 Pro achieved the highest Allowed Accuracy at 96.4 %, followed by Claude Haiku 4.5 and GPT-5.5 at 91.7 % each and DeepSeek-V4-Flash at 89.7 %. The same order is observed for Allowed Macro-Precision and Allowed Macro-Recall. The results of Claude Haiku 4.5 and Gemini 2.5 Pro correspond to their single runs with PDF input in Section 5.4 within less than one percentage point. Because the input comparison in Section 5.4 covered only the Claude and Gemini models, its finding of lower results for image input cannot be applied directly to GPT-5.5.

表 5.5 给出了最终配置在十次运行中的平均结果。Gemini 2.5 Pro 的 Allowed Accuracy 最高，为 96.4%；其次是 Claude Haiku 4.5 和 GPT-5.5，均为 91.7%；DeepSeek-V4-Flash 为 89.7%。Allowed Macro-Precision 和 Allowed Macro-Recall 的排序也相同。Claude Haiku 4.5 和 Gemini 2.5 Pro 的结果与第 5.4 节中 PDF 输入的单次运行相差不到一个百分点。由于第 5.4 节的输入形式比较只涵盖 Claude 和 Gemini 模型，其中图片输入结果较低的发现不能直接用于 GPT-5.5。

The strict metrics, which count only the primary label as correct, lead to a different order. Only assemblies in regime M have an allowed label other than the primary label, so the gap between Allowed Accuracy and Strict Accuracy indicates how often a configuration predicted such an alternative. This difference amounted to 10.6 percentage points for Gemini 2.5 Pro and 6.6 for GPT-5.5, but only 2.6 for Claude Haiku 4.5 and 1.7 for DeepSeek-V4-Flash. Claude Haiku 4.5 therefore had the highest Strict Macro-F1 at 89.2 %, while Gemini 2.5 Pro achieved 85.2 %. The advantage of Gemini 2.5 Pro under the allowed criterion is therefore based mainly on the assemblies in regime M, which are examined in Section 5.6.2.

只把主标签计为正确的严格指标得出了不同的排序。只有 M 中的装配体具有主标签以外的允许标签，因此 Allowed Accuracy 与 Strict Accuracy 的差值反映了配置预测此类备选允许类别的频率。这一差值在 Gemini 2.5 Pro 上为 10.6 个百分点，在 GPT-5.5 上为 6.6 个百分点，而在 Claude Haiku 4.5 和 DeepSeek-V4-Flash 上分别只有 2.6 和 1.7 个百分点。因此，Claude Haiku 4.5 的 Strict Macro-F1 最高，达到 89.2%，Gemini 2.5 Pro 则为 85.2%。由此可见，Gemini 2.5 Pro 在允许标签准则下的优势主要来自 M 中的装配体，这将在第 5.6.2 节中分析。

**Table 5.5. Results of the final configurations (115 assemblies, ten runs) / 表 5.5 最终配置的结果（115 个装配体，十次运行）**

| Metric / 指标 | Claude Haiku 4.5 (PDF) | DeepSeek-V4-Flash (Text) | Gemini 2.5 Pro (PDF) | GPT-5.5 (Image) |
| --- | ---: | ---: | ---: | ---: |
| Allowed Accuracy | 91.7 [86.5–96.5] | 89.7 [84.2–94.8] | **96.4** [93.3–98.8] | 91.7 [86.7–96.3] |
| Allowed Macro-Precision | 92.0 [87.0–96.5] | 90.7 [85.7–95.4] | **97.1** [94.7–99.0] | 90.5 [85.0–96.0] |
| Allowed Macro-Recall | 92.7 [88.3–96.9] | 90.5 [86.0–95.0] | **96.7** [94.0–99.0] | 91.2 [85.7–96.1] |
| Strict Accuracy | **89.1** [83.5–94.3] | 87.9 [81.9–93.5] | 85.7 [79.7–91.4] | 85.0 [78.7–91.3] |
| Strict Macro-F1 | **89.2** [82.9–94.3] | 88.6 [83.3–93.4] | 85.2 [78.4–90.8] | 84.0 [76.7–90.2] |
| *Stability across ten runs / 十次运行的稳定性* | | | | |
| SD of Allowed Accuracy (pp) / Allowed Accuracy 标准差（百分点） | 0.46 | 0.86 | 0.90 | 0.93 |
| Assemblies with varying prediction / 预测有变化的装配体 | 1 | 6 | 13 | 10 |
| of which in regime M / 其中属于 M | 0 | 1 | 7 | 6 |

*Note: Values in % (mean over ten runs); values in brackets are 95 % bootstrap confidence intervals (Section 5.2). Class-wise results in Appendix D.*

注：数值单位为 %（十次运行的平均值）；方括号内为 95% Bootstrap 置信区间（第 5.2 节）。各类别的结果见附录 D。

**③ 配置之间的差异**

Although Table 5.5 shows differences between configurations, differences on a set of 115 assemblies can also occur by chance. Each pair of configurations was therefore compared with the paired bootstrap test described in Section 5.2. After correction for multiple comparisons, only one tested difference remained significant: Gemini 2.5 Pro had a 6.4 percentage point higher Allowed Macro-Precision than DeepSeek-V4-Flash (p = 0.042). Even the largest difference in Allowed Accuracy, 6.7 percentage points between Gemini 2.5 Pro and DeepSeek-V4-Flash, was significant only before the correction (p = 0.014) and not after it (p = 0.084), and the configurations did not differ in Strict Macro-F1 (Appendix D). These assemblies therefore do not provide a reliable basis for ranking the four configurations.

尽管表 5.5 显示各配置存在差异，但在包含 115 个装配体的数据集中，这些差异也可能由偶然因素产生。因此，每两种配置之间都用第 5.2 节介绍的配对 Bootstrap 检验进行比较。经多重比较校正后，所检验的差异中只有一项仍具有统计显著性：Gemini 2.5 Pro 的 Allowed Macro-Precision 比 DeepSeek-V4-Flash 高 6.4 个百分点（p = 0.042）。即使是 Allowed Accuracy 上最大的差异，即 Gemini 2.5 Pro 与 DeepSeek-V4-Flash 之间的 6.7 个百分点，也只在校正前显著（p = 0.014），校正后不再显著（p = 0.084）；各配置在 Strict Macro-F1 上也没有差异（附录 D）。因此，这些装配体无法为四种配置提供可靠的排序依据。

**④ 稳定性**

The variation between runs was small for all configurations (Table 5.5). For every configuration, the standard deviation of Allowed Accuracy was below one percentage point, corresponding to less than one assembly, and was considerably smaller than the differences between configurations and the widths of the confidence intervals. Claude Haiku 4.5 assigned the same class in all ten runs to all but one assembly, whereas the predictions of the other configurations varied for between 6 and 13 assemblies. For Gemini 2.5 Pro and GPT-5.5, over half of these assemblies belong to regime M, where the documentation supports more than one class, and most assemblies with varying predictions had Combined Unit as their primary or an allowed label.

所有配置在不同运行之间的波动都很小（表 5.5）。各配置的 Allowed Accuracy 标准差均低于一个百分点，相当于不到一个装配体，明显小于配置之间的差异和置信区间的宽度。Claude Haiku 4.5 除一个装配体外，在全部十次运行中都给出了相同的类别；其他配置则有 6 至 13 个装配体的预测发生变化。对于 Gemini 2.5 Pro 和 GPT-5.5，这些装配体中有一半以上属于 M，即资料支持多个类别。大多数预测发生变化的装配体都以组合单元作为主标签或允许标签。

**⑤ 过渡**

The results are based on the primary set used to select the prompt and input representation. Section 5.6 therefore examines whether they are maintained on the supplementary set and how the configurations perform in the individual ambiguity regimes.

这些结果基于主数据集，Prompt 和输入形式也是在该数据集上选定的。因此，第 5.6 节检验这些结果在补充数据集上能否保持，以及各配置在不同歧义类别中的表现。

## 待处理

### 5.1 待办

- [ ] 后续补充预实验 L1–L4 结果的附录，结果需按最终版 GT 重算。
- [ ] **附录 B**：接入方式、模型版本号、输入转换设置、生成参数。
- [ ] **GPT-5.5 的 temperature**：查请求日志确认确实是 0。

### 5.2 待办

- [ ] **p 值的算法**：对照 `evaluate_allowed_strict.py` 确认配对 Bootstrap 的 p 值如何得出。
- [ ] **偏向说明**：只复核了预测错误的装配体，修订可能使 LLM 结果偏好。问过 Jonas 后决定写在 5.2 还是第 7 章，以及是否做修订前 GT 的敏感性分析（附录 E）。

### 5.3 待办

- [ ] **置信区间**：表 5.3 各值的 95% CI，放附录 D；补上后可改成带误差棒的分组柱状图（图 5.1），表移到附录。
- [ ] **分母**：Prompt 比较中 Opus（114）、Flash（111–113）、Pro（113–114）的分母不是 115（空输出未补跑；Haiku 已重跑，为 115）。问过 Jonas 后在表注中说明，或补跑。5.1 ③ 暂不改。
- [ ] **可选核对**：Strict Macro-F1 的趋势是否也支持 P3；一致则加一句 “Strict Macro-F1 showed the same pattern (Appendix D)”。
- 已确认：数字基于最终版 GT；P4 的例子为作者自拟，不取自数据集；P3 + PDF 在 5.3 和 5.4 中是两次独立运行，5.4 开头需说明数字略有不同的原因。

### 5.4 待办

- [ ] **Flash 文本输入的错误数**：按 `corrected_gt_zgt_error_records.md` 换算为 3 个，表 5.4（96.5%）对应 4 个。对照原表核对转录。
- [ ] **表 5.4 分母**：Flash 图片输入为 114（1 个空输出未补跑），与 5.3 的分母问题一起问 Jonas。
- [ ] **置信区间**：放附录 D。
- 依据：③ 中 80 / 129 来自表 5.4（图片 23+15+23+19；PDF 10+3+7+4；文本 9+9+4+3）。四个机器人为 `0804CC2134`、`0804EK1683`、`0804GD6171`、`0804FH4760`（Fehler_Analyse 第 18、19、21、22 行），两个旋转单元为 `0804HX0679`、`0804KB7256`（第 24、30 行），这些装配体只在图片输入下出错。图片按每批 15 张发送，但每个装配体仍是一次请求。两个三轴龙门（`0804HZ8350`、`0804KY3585`）在文本输入下也出错，留给 5.7。

### 5.5 待办

- [ ] **四舍五入核对**：表 5.5 中 Gemini 2.5 Pro 的 Allowed Macro-Precision 为 97,05%，写作 97.1；GPT-5.5 和 Haiku 的 Allowed Accuracy 为 91,65% 和 91,74%，均写作 91.7。按 Excel 完整数值核对。
- [ ] **GPT-5.5 的 temperature**：查请求日志确认为 0（5.1 ③ 写的是所有模型均为 0）。
- [ ] **M 类装配体上的变化**：④ 只写了这些装配体属于 M，未核对是否都在允许类别之间切换；如需更强的说法，查 `Pro_Lauf` 或各次运行的逐个预测。
- 数据来源：`Evaluation_Allowed_Strict.xlsx`（2026-11-11 用新版脚本、四种配置重跑；Hauptergebnis、Paarvergleich 24 行、Run_to_run_SD、Stabilitaet）。EXCLUDED 为 0，M 为 30（26.1%）。Holm 校正后唯一显著：Pro − DeepSeek 的 Allowed Macro-Precision（Δ 6.37，p 0.042）。
- 预测有变化的装配体：Haiku `0804FZ8322`；DeepSeek 6 个（1 个 M）；Pro 13 个（7 个 M）；GPT-5.5 10 个（6 个 M，含 5.4 ③ 中的机器人 `0804EK1683`）。
- 额外的 GPT 系列图片实验（各运行一次）未写入正文；如 Jonas 需要，可放附录。

### 章节安排

第 5 章结构（2026-11-11 调整）：5.1 Setup and Configurations / 5.2 Ground Truth Revision and Evaluation Metrics / 5.3 Prompt Design / 5.4 Input Representation / 5.5 Final Configurations and Stability（115 个 × 10 次）/ 5.6 Validation and Performance Across Ambiguity Regimes（5.6.1 Validation on the Supplementary Set：70 个的 E1+E2 对比 115 个的 E1+E2，那 1 个 M 一句话说明；5.6.2 Performance in Regimes E1, E2 and M：185 个合并，E1、E2、M 分开报告，按装配体计算——115 个取 10 次运行中分对的比例，70 个取 0/1，再对 185 个求平均，Bootstrap 也按 185 个装配体抽样；脚本 09 不能直接这样算，需单独计算）/ 5.7 Error Analysis / 5.8 Cost and Efficiency / 5.9 Summary。

章节引用原则：只保留读者需要跳转查看的引用（如 5.1 ① 指向 5.2 的 GT 修订、5.2 ① 指向 4.4 的复核流程）；实验阶段与小节的对应只在表 5.1 的 Section 列中给出。

- 5.4：三种输入形式的定义（含 Tesseract，Smith, 2007）和比较结果（表 5.4）；说明 PDF 这组与 5.3 的 P3 是两次独立运行。
- 5.5 开头：四种最终配置，每个模型一点，写明输入形式和选择理由（Haiku 不选 Opus 因成本；Pro 优于 Flash；Haiku 和 Pro 选 PDF 而非文本：只差一个装配体、PDF 平均最高、无需单独提取步骤；GPT-5.5 因 Azure OpenAI 的 PDF 转换不可控而用图片；DeepSeek 只支持文本）。
- 附录 B：接入方式、模型版本、输入转换设置、生成参数；附录 C：Prompt 原文；附录 D：各阶段置信区间、完整指标。

| 附录 | 内容 |
| --- | --- |
| A | Codebook 全文，含八个边界案例 |
| B | 实验设置，包括接入方式、模型版本、输入转换设置和生成参数 |
| C | Prompt P1–P4 全文 |
| D | 表 5.3 和表 5.4 的置信区间及完整指标 |
| E | 修订前 GT 的敏感性分析 |
