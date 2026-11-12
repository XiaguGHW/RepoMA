# 5 Experimental Evaluation

The LLM-based classification is evaluated in this chapter using the ground truth established in Chapter 4 as the reference. After the experimental setup and the evaluation metrics, the chapter first reports the selection of prompt and input representation. It then examines the stability of the final configurations, reports their performance on all assemblies across the ambiguity regimes and analyses their errors. The chapter concludes by comparing their cost and processing time with those of human classification.

本章以第 4 章建立的 Ground Truth 为参考，评价基于 LLM 的分类。在介绍实验设置和评价指标之后，本章先报告 Prompt 和输入形式的选择，然后检验最终配置的稳定性，报告其在全部装配体上按歧义类别的表现，并分析其错误。最后，将其成本和处理时间与人工分类进行比较。

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
| Supplementary set / 补充数据集 | 70 | P3 | final / 最终配置 | 4 final configurations / 4 种最终配置 | 1 | 5.6 |

**③ 模型与运行方式**

Six models from four providers were used: Claude Haiku 4.5 and Claude Opus 4.8 (Anthropic), Gemini 2.5 Flash and Gemini 2.5 Pro (Google), GPT-5.5 (OpenAI) and DeepSeek-V4-Flash (DeepSeek) (access and model versions in Appendix B). A separate request was submitted for each assembly, with no information carried over from earlier requests. The temperature was set to 0 for all models. As the codebook rules define a single correct class for this decision task, the aim is to obtain the most probable output and avoid variation between outputs, while a temperature of 0 also supports reproducibility. Requests that returned an empty output were identified after each run and repeated individually. Once these requests had been repeated, a valid output was available for every assembly, and each output contained one of the seven class names. For some assemblies with extensive documentation, PDF documents had to be shortened to meet the request size limits of the platforms; this mainly affected long supplier catalogues and manuals. The token usage of each request was recorded for the cost analysis.

实验使用了来自四家厂商的六个模型，包括 Claude Haiku 4.5 和 Claude Opus 4.8（Anthropic）、Gemini 2.5 Flash 和 Gemini 2.5 Pro（Google）、GPT-5.5（OpenAI），以及 DeepSeek-V4-Flash（DeepSeek）（接入方式和模型版本见附录 B）。每个装配体通过单独的请求进行分类，不带入此前请求的信息。所有模型的 temperature 均设为 0。由于这一决策任务按 Codebook 规则只有一个正确类别，因此目标是获得最可能的输出并避免输出之间的变化，同时 temperature 为 0 也有助于提高可复现性。每轮运行后，找出输出为空的请求并单独重新运行。重新运行后，每个装配体均有有效输出，且每个输出都包含七个类别名称之一。对于少数资料篇幅很大的装配体，必须截断 PDF 资料，才能满足各平台对请求大小的限制；被截断的主要是篇幅较长的供应商样本和手册。每次请求的 token 用量均被记录，用于成本分析。

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

$$\text{Allowed Accuracy} = \frac{\left|\left\lbrace i : \hat{y}_i \in A_i \right\rbrace\right|}{N} \qquad (5.1)$$

设 $C$ 为七个类别的集合。对于每个装配体 $i$ （ $i = 1, \dots, N$ ）， $\hat{y}_i$ 表示预测类别， $y_i$ 表示主标签， $A_i$ 表示包含主标签的允许标签集合（ $y_i \in A_i$ ）。主要指标是 Allowed Accuracy，它沿用了每个样本有多个有效标签时的评价做法（Shankar et al., 2020; Beyer et al., 2020）。

Class-specific performance is described by Allowed Precision and Allowed Recall, which apply the standard definitions (Sokolova & Lapalme, 2009) to the allowed label sets:

$$\mathrm{AP}_c = \frac{\left|\left\lbrace i : \hat{y}_i = c \wedge c \in A_i \right\rbrace\right|}{\left|\left\lbrace i : \hat{y}_i = c \right\rbrace\right|} \qquad (5.2\text{a})$$

$$\mathrm{AR}_c = \frac{\left|\left\lbrace i : y_i = c \wedge \hat{y}_i \in A_i \right\rbrace\right|}{\left|\left\lbrace i : y_i = c \right\rbrace\right|} \qquad (5.2\text{b})$$

Allowed Macro-Precision and Allowed Macro-Recall are the equally weighted averages of the corresponding values across the seven classes. This extension ensures that a prediction counted as correct by the Allowed Accuracy is not counted as an error in precision or recall.

各类别的表现用 Allowed Precision 和 Allowed Recall 描述，即把标准定义（Sokolova & Lapalme, 2009）应用到允许标签集合上。将对应指标在七个类别上的数值分别等权平均，即得 Allowed Macro-Precision 和 Allowed Macro-Recall。这一扩展保证了被 Allowed Accuracy 计为正确的预测，在 Precision 和 Recall 中不会被计为错误。

Only strict F1 is reported because precision and recall under the allowed criterion can refer to different classes for a single prediction. Strict Macro-F1 is the mean of the class-wise F1 values (Opitz & Burst, 2019):

$$\text{Strict Macro-F1} = \frac{1}{|C|}\sum_{c \in C} \frac{2 \cdot \mathrm{P}_c \cdot \mathrm{R}_c}{\mathrm{P}_c + \mathrm{R}_c} \qquad (5.3)$$

where $\mathrm{P}_c$ and $\mathrm{R}_c$ follow from Equations 5.2a and 5.2b with $A_i$ replaced by $\lbrace y_i \rbrace$. This metric reflects how often predictions match the primary label and supports comparison with studies that use a single correct label. For configurations with ten runs, each metric is calculated per run and averaged across the runs.

本文仅报告严格形式的 F1，因为按允许标签准则计算时，同一个预测在 Precision 和 Recall 中可能对应不同的类别。Strict Macro-F1 是各类别 F1 的平均值（Opitz & Burst, 2019）。其中 $\mathrm{P}_c$ 和 $\mathrm{R}_c$ 由公式 5.2a 和 5.2b 将 $A_i$ 替换为 $\lbrace y_i \rbrace$ 得到。这一指标反映预测与主标签匹配的频率，可用于和仅采用一个正确标签的研究进行比较。对于运行十次的配置，每个指标按每次运行分别计算，再在各次运行之间取平均。

> **公式 5.1–5.3 的 LaTeX 原文（供复制到 Word / Overleaf，不属于正文）**
>
> ```latex
> % (5.1)
> \text{Allowed Accuracy} = \frac{\left|\left\{ i : \hat{y}_i \in A_i \right\}\right|}{N}
>
> % (5.2a)
> \mathrm{AP}_c = \frac{\left|\left\{ i : \hat{y}_i = c \wedge c \in A_i \right\}\right|}{\left|\left\{ i : \hat{y}_i = c \right\}\right|}
>
> % (5.2b)
> \mathrm{AR}_c = \frac{\left|\left\{ i : y_i = c \wedge \hat{y}_i \in A_i \right\}\right|}{\left|\left\{ i : y_i = c \right\}\right|}
>
> % (5.3)
> \text{Strict Macro-F1} = \frac{1}{|C|} \sum_{c \in C} \frac{2\,\mathrm{P}_c\,\mathrm{R}_c}{\mathrm{P}_c + \mathrm{R}_c}
>
> % 正文中的行内符号
> C,\quad i = 1, \dots, N,\quad \hat{y}_i,\quad y_i,\quad A_i,\quad y_i \in A_i,\quad \mathrm{P}_c,\quad \mathrm{R}_c,\quad \{y_i\}
> ```
>
> 说明：代码框里是标准 LaTeX，可原样复制到 Overleaf 的 `equation` 环境中，或粘贴到 Word 公式编辑器（Alt + =，选择 LaTeX 输入格式）。正文上方的公式为了在 Markdown 预览中正确显示，用 `\lbrace`、`\rbrace` 代替了 `\{`、`\}`，并去掉了 `\,`，含义相同。编号 (5.1)–(5.3) 用 Word 或 LaTeX 的公式编号功能另加。

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

The input representation specifies the form in which an assembly's documentation is provided to the model. Three representations were compared, each containing the same documentation in a different file format. The PDF representation contains all PDF files, the image representation contains the CAD screenshots, the DFC structure and PDF pages converted to images, and the text representation consists of raw text extracted from these files, using the open-source OCR engine Tesseract to extract text from images (Smith, 2007). Prompt P3 was used for the comparison, with the same four models and one run for each configuration. The PDF configuration was run independently of the prompt comparison, so its results differ slightly from those for P3 in Table 5.3.

输入形式规定了装配体资料提供给模型时所采用的形式。本研究比较了三种输入形式，它们包含同一份资料，只是文件格式不同。PDF 形式包含全部 PDF 文件，图片形式包含 CAD 截图、DFC 结构和转换为图片的 PDF 页面。文本形式由从这些文件中提取的原始文本组成，图片中的文字使用开源 OCR 工具 Tesseract 提取（Smith, 2007）。该比较使用 Prompt P3 和相同的四个模型，每种配置运行一次。PDF 配置与 Prompt 比较是分开独立运行的，因此其结果与表 5.3 中 P3 的结果略有不同。

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

The strict metrics, which count only the primary label as correct, lead to a different order. Only assemblies in regime M have an allowed label other than the primary label, so the gap between Allowed Accuracy and Strict Accuracy indicates how often a configuration predicted such an alternative. This difference amounted to 10.6 percentage points for Gemini 2.5 Pro and 6.6 for GPT-5.5, but only 2.6 for Claude Haiku 4.5 and 1.7 for DeepSeek-V4-Flash. Claude Haiku 4.5 therefore had the highest Strict Macro-F1 at 89.2 %, while Gemini 2.5 Pro achieved 85.2 %. The advantage of Gemini 2.5 Pro under the allowed criterion is therefore based mainly on the assemblies in regime M, which are examined in Section 5.6.

只把主标签计为正确的严格指标得出了不同的排序。只有 M 中的装配体具有主标签以外的允许标签，因此 Allowed Accuracy 与 Strict Accuracy 的差值反映了配置预测此类备选允许类别的频率。这一差值在 Gemini 2.5 Pro 上为 10.6 个百分点，在 GPT-5.5 上为 6.6 个百分点，而在 Claude Haiku 4.5 和 DeepSeek-V4-Flash 上分别只有 2.6 和 1.7 个百分点。因此，Claude Haiku 4.5 的 Strict Macro-F1 最高，达到 89.2%，Gemini 2.5 Pro 则为 85.2%。由此可见，Gemini 2.5 Pro 在允许标签准则下的优势主要来自 M 中的装配体，这将在第 5.6 节中分析。

**Table 5.5. Results of the final configurations (115 assemblies, ten runs) / 表 5.5 最终配置的结果（115 个装配体，十次运行）**

| Metric / 指标 | Claude Haiku 4.5 (PDF) | DeepSeek-V4-Flash (Text) | Gemini 2.5 Pro (PDF) | GPT-5.5 (Image) |
| --- | ---: | ---: | ---: | ---: |
| Allowed Accuracy | 91.7 [86.5–96.5] | 89.7 [84.2–94.8] | **96.4** [93.3–98.8] | 91.7 [86.7–96.3] |
| Allowed Macro-Precision | 92.0 [87.0–96.5] | 90.7 [85.7–95.4] | **97.1** [94.7–99.0] | 90.5 [85.0–96.0] |
| Allowed Macro-Recall | 92.7 [88.3–96.9] | 90.5 [86.0–95.0] | **96.7** [94.0–99.0] | 91.2 [85.7–96.1] |
| Strict Accuracy | **89.1** [83.5–94.3] | 87.9 [81.9–93.5] | 85.7 [79.7–91.4] | 85.0 [78.7–91.3] |
| Strict Macro-F1 | **89.2** [82.9–94.3] | 88.6 [83.3–93.4] | 85.2 [78.4–90.8] | 84.0 [76.7–90.2] |
| Standard deviation of Allowed Accuracy / Allowed Accuracy 的标准差 | 0.46 | 0.86 | 0.90 | 0.93 |
| Assemblies with varying prediction / 预测有变化的装配体 | 1 | 6 | 13 | 10 |
| of which in regime M / 其中属于 M | 0 | 1 | 7 | 6 |

*Note: Values in % (mean over ten runs); values in brackets are 95 % bootstrap confidence intervals (Section 5.2). Standard deviation across the ten runs in percentage points. Class-wise results in Appendix D.*

注：数值单位为 %（十次运行的平均值）；方括号内为 95% Bootstrap 置信区间（第 5.2 节）。标准差为十次运行之间的标准差，单位为百分点。各类别的结果见附录 D。

**③ 配置之间的差异**

Although Table 5.5 shows differences between configurations, differences on a set of 115 assemblies can also occur by chance. Each pair of configurations was therefore compared with the paired bootstrap test described in Section 5.2. After correction for multiple comparisons, only one tested difference remained significant: Gemini 2.5 Pro had a 6.4 percentage point higher Allowed Macro-Precision than DeepSeek-V4-Flash (p = 0.042). Even the largest difference in Allowed Accuracy, 6.7 percentage points between Gemini 2.5 Pro and DeepSeek-V4-Flash, was significant only before the correction (p = 0.014) and not after it (p = 0.084), and the configurations did not differ in Strict Macro-F1 (Appendix D). These assemblies therefore do not provide a reliable basis for ranking the four configurations.

尽管表 5.5 显示各配置存在差异，但在包含 115 个装配体的数据集中，这些差异也可能由偶然因素产生。因此，每两种配置之间都用第 5.2 节介绍的配对 Bootstrap 检验进行比较。经多重比较校正后，所检验的差异中只有一项仍具有统计显著性：Gemini 2.5 Pro 的 Allowed Macro-Precision 比 DeepSeek-V4-Flash 高 6.4 个百分点（p = 0.042）。即使是 Allowed Accuracy 上最大的差异，即 Gemini 2.5 Pro 与 DeepSeek-V4-Flash 之间的 6.7 个百分点，也只在校正前显著（p = 0.014），校正后不再显著（p = 0.084）；各配置在 Strict Macro-F1 上也没有差异（附录 D）。因此，这些装配体无法为四种配置提供可靠的排序依据。

**④ 稳定性**

The variation between runs was small for all configurations (Table 5.5). For every configuration, the standard deviation of Allowed Accuracy was below one percentage point, corresponding to less than one assembly, and was considerably smaller than the differences between configurations and the widths of the confidence intervals. Claude Haiku 4.5 assigned the same class in all ten runs to all but one assembly, whereas the predictions of the other configurations varied for between 6 and 13 assemblies. For Gemini 2.5 Pro and GPT-5.5, over half of these assemblies belong to regime M, where the documentation supports more than one class, and most assemblies with varying predictions had Combined Unit as their primary or an allowed label.

所有配置在不同运行之间的波动都很小（表 5.5）。各配置的 Allowed Accuracy 标准差均低于一个百分点，相当于不到一个装配体，明显小于配置之间的差异和置信区间的宽度。Claude Haiku 4.5 除一个装配体外，在全部十次运行中都给出了相同的类别；其他配置则有 6 至 13 个装配体的预测发生变化。对于 Gemini 2.5 Pro 和 GPT-5.5，这些装配体中有一半以上属于 M，即资料支持多个类别。大多数预测发生变化的装配体都以组合单元作为主标签或允许标签。

**⑤ 过渡**

The results are based on the primary set used to select the prompt and input representation. Section 5.6 therefore combines them with the results on the supplementary set and reports the performance in the individual ambiguity regimes.

这些结果基于主数据集，Prompt 和输入形式也是在该数据集上选定的。因此，第 5.6 节将其与补充数据集上的结果合并，并报告各配置在不同歧义类别中的表现。

## 5.6 Performance Across Ambiguity Regimes | 各歧义类别中的表现

**① 数据与合并方法**

The results of the final configurations for all 185 assemblies are presented separately for each ambiguity regime in this section. Since the assemblies of the primary set were classified in ten runs and those of the supplementary set in one, each assembly was weighted equally: for the primary set, the share of correct runs was used, and for the supplementary set, the single result. Confidence intervals were calculated by resampling assemblies within each regime. Before the two sets were combined, the results on the supplementary set, which was not involved in any selection step, were compared with those on the primary set for the assemblies in regimes E1 and E2. No configuration achieved a lower accuracy on the supplementary set, and the two sets are not compared further because the supplementary set contains a considerably higher proportion of assemblies in regime E1.

本节按歧义类别分别呈现最终配置在全部 185 个装配体上的结果。由于主数据集的装配体运行了十次，而补充数据集的装配体只运行了一次，每个装配体按相同权重计算：主数据集取十次运行中分类正确的比例，补充数据集取单次运行的结果。置信区间通过在每个歧义类别内对装配体进行重抽样计算得出。在合并两个数据集之前，先比较了 E1 和 E2 装配体在补充数据集和主数据集上的结果。补充数据集未参与任何选择步骤。没有一种配置在补充数据集上的准确率低于主数据集。由于补充数据集中 E1 装配体所占比例明显更高，两个数据集不再作进一步比较。

**② E1 与 E2**

In regime E1, all configurations classified at least 93 % of the assemblies correctly (Table 5.6). All workshop participants assigned the same class to these assemblies, so the remaining errors of 2.5 to 6.8 % represent departures from a clear human judgement. In regime E2, the accuracy was lower for all configurations, by between 3.0 and 9.0 percentage points. For these assemblies, individual participants chose a different class, and the class is determined only by applying the codebook rules. The models thus encountered difficulties with the same assemblies as the human annotators. Because regime E2 contains only 44 assemblies, the confidence intervals are wide, and the decrease is not certain for each configuration individually, although its occurrence across all four configurations indicates that these assemblies are more difficult to classify.

在 E1 中，所有配置都至少正确分类了 93% 的装配体（表 5.6）。所有 Workshop 参与者都为这些装配体选择了相同的类别，因此剩余 2.5% 至 6.8% 的错误体现了对明确人工判断的偏离。在 E2 中，所有配置的准确率都更低，下降 3.0 至 9.0 个百分点。对于这些装配体，个别参与者选择了不同的类别，类别只能通过应用 Codebook 规则确定。因此，模型和人工标注者在同样的装配体上遇到了困难。由于 E2 只有 44 个装配体，置信区间较宽，不能确定每种配置的准确率都确实下降。四种配置均出现下降，这表明这些装配体更难分类。

**Table 5.6. Allowed Accuracy by ambiguity regime (185 assemblies) / 表 5.6 各歧义类别的 Allowed Accuracy（185 个装配体）**

| Regime / 类别 | Claude Haiku 4.5 (PDF) | DeepSeek-V4-Flash (Text) | Gemini 2.5 Pro (PDF) | GPT-5.5 (Image) |
| --- | ---: | ---: | ---: | ---: |
| E1 (n = 110) | 93.2 [88.2–97.3] | 94.9 [90.5–98.5] | **97.5** [94.6–99.6] | 96.5 [92.8–99.2] |
| E2 (n = 44) | 88.6 [79.5–97.7] | 85.9 [74.8–94.8] | **94.5** [88.2–99.5] | 91.1 [82.3–98.0] |
| M (n = 31) | 93.5 [83.9–100.0] | 93.2 [83.5–100.0] | **99.7** [99.0–100.0] | 94.2 [85.2–100.0] |
| – of which primary label predicted / 其中预测为主标签 | 80.6 | 86.8 | 60.3 | 66.5 |
| – of which other allowed label predicted / 其中预测为其他允许标签 | 12.9 | 6.5 | 39.4 | 27.7 |
| All, Allowed Accuracy / 全部，Allowed Accuracy | 92.2 [88.1–95.7] | 92.5 [88.5–96.1] | **97.2** [95.0–99.0] | 94.8 [91.1–97.7] |
| All, Strict Accuracy / 全部，Strict Accuracy | 90.0 [85.4–94.1] | **91.4** [87.4–95.1] | 90.6 [86.7–94.1] | 90.2 [85.9–94.2] |

*Note: Values in %; values in brackets are 95 % bootstrap confidence intervals. Primary set: share of correct runs per assembly (ten runs); supplementary set: one run. The two rows below M divide its Allowed Accuracy according to whether the primary label or another allowed label was predicted.*

注：数值单位为 %；方括号内为 95% Bootstrap 置信区间。主数据集：每个装配体十次运行中分类正确的比例；补充数据集：运行一次。M 下面的两行把它的 Allowed Accuracy 按预测的是主标签还是其他允许标签拆分开。

**③ M**

Each configuration predicted an allowed class for at least 93 % of the assemblies in regime M, while Gemini 2.5 Pro did so for almost all assemblies in this regime. The configurations differed, however, in which allowed class they chose. The share of these assemblies for which a class other than the primary label was predicted was 39.4 % for Gemini 2.5 Pro and 27.7 % for GPT-5.5, compared with 12.9 % for Claude Haiku 4.5 and 6.5 % for DeepSeek-V4-Flash. For Gemini 2.5 Pro, almost all of the 99.7 % in regime M were correct, but only 60.3 % matched the primary label; under the strict criterion, the remaining 39.4 % are counted as errors although they are allowed classes. For assemblies in regime M, the documentation and the codebook support all allowed labels, so the primary label is no more correct than the others (Section 4.4). The differences in the strict metrics in Section 5.5 therefore reflect which of the valid classes a configuration preferred rather than additional errors. For all 185 assemblies, the four configurations' Strict Accuracy values were within 1.4 percentage points of one another, while their Allowed Accuracy ranged from 92.2 to 97.2 %.

在 M 中，每种配置都对至少 93% 的装配体预测出了允许类别，Gemini 2.5 Pro 对该类别中几乎所有装配体都预测出了允许类别。不过，各配置选择哪个允许类别有所不同。在这些装配体中，Gemini 2.5 Pro 和 GPT-5.5 预测为主标签以外类别的比例分别为 39.4% 和 27.7%，Claude Haiku 4.5 和 DeepSeek-V4-Flash 则分别为 12.9% 和 6.5%。对于 Gemini 2.5 Pro，M 中 99.7% 的预测几乎全部正确，但只有 60.3% 与主标签一致；按严格标准，其余 39.4% 尽管属于允许的类别，仍被计为错误。对于 M 中的装配体，所有允许标签均得到资料和 Codebook 的支持，因此主标签并不比其他允许标签更正确（第 4.4 节）。所以，第 5.5 节中严格指标的差异反映的是配置更倾向于哪个有效类别，而不是更多的错误。在全部 185 个装配体上，四种配置的 Strict Accuracy 相差不超过 1.4 个百分点，Allowed Accuracy 则介于 92.2% 和 97.2% 之间。

## 5.7 Error Analysis | 错误分析

**① Scope and method / 范围与方法**

The misclassifications examined in this section occurred with prompt P3 during the input comparison (Section 5.4) and with the final configurations (Sections 5.5 and 5.6). A prediction counts as an error if it is not contained in the allowed label set of the final ground truth. A total of 58 assemblies were misclassified at least once, comprising 44 of the 115 assemblies in the twelve input comparison runs and 38 of the 185 assemblies with the final configurations, with 24 assemblies common to both groups. For each of these assemblies, the reasoning of the erroneous runs was read and one primary cause was assigned. The analysis counts assemblies rather than runs because repeated runs of the same configuration often produced the same error.

本节分析使用 Prompt P3 时在输入形式比较（第 5.4 节）和最终配置（第 5.5、5.6 节）中出现的错误分类。预测不在最终版 Ground Truth 的允许标签集合内即算作错误。共有 58 个装配体至少被错误分类一次。其中，输入形式比较的十二次运行涉及的 115 个装配体里有 44 个出错，最终配置涉及的 185 个装配体里有 38 个出错，两组有 24 个装配体重叠。对每个装配体，阅读出错运行的推理，并归入一个主要原因。统计以装配体为单位，因为同一配置的多次运行经常产生相同的错误。

**② Confusion patterns / 混淆模式**

Figure 5.1 compares the confusion matrices of the four final configurations with that of the individual workshop annotations. Sixteen of the 35 model errors involve assemblies with Combined Unit as their primary label, including ten predictions of Multi-Axis System (Gantry). A further 11 errors concern assemblies with the primary label Gantry, which were mainly predicted as Linear Unit or Combined Unit. The human annotators likewise made most of their errors on Combined Unit assemblies (66 of 98), most frequently predicting Linear Unit (26), followed by Gantry (20) and Rotary Unit (11). The boundary between Combined Unit and the classes with a single type of motion was therefore the main difficulty for both, whereas confusions between Gantry and Combined Unit were more frequent for the models. Both made few errors on grippers and robots, and the three errors in the Robot row came from GPT-5.5 and are explained below.

图 5.1 把四种最终配置的混淆矩阵和 Workshop 中各条人工标注的混淆矩阵放在一起比较。模型的 35 次错误中，有 16 次涉及主标签为组合单元的装配体，其中 10 次被预测为多轴系统（龙门）。另有 11 次涉及主标签为龙门的装配体，主要被预测为直线单元或组合单元。人工标注者的错误同样主要集中在组合单元上（98 次中有 66 次），最常预测为直线单元（26 次），其次为龙门（20 次）和旋转单元（11 次）。因此，对两者来说，组合单元与只有一种运动形式的类别之间的边界都是主要难点；而龙门与组合单元之间的混淆在模型中更常见。两者在夹爪和机器人上都很少出错。机器人一行的三个错误均来自 GPT-5.5，原因见下文。

**Figure 5.1. Confusion matrices of the final configurations (115 assemblies) and of the individual workshop annotations / 图 5.1 最终配置（115 个装配体）与 Workshop 人工标注的混淆矩阵**

*[konfusion_gesamt.png，脚本 13 输出]*

*Note: Rows show the primary label of the final ground truth, columns the prediction. Off-diagonal cells are split into misclassifications (left) and other allowed labels (right).*

注：行为最终版 Ground Truth 的主标签，列为预测。非对角线格子分为错误分类（左）和其他允许标签（右）。

**③ Causes / 错误原因**

The primary causes are listed in Table 5.7. Actuator miscounting is the largest category in both groups and accounts for 29 of the 58 assemblies. For these assemblies, the actuators were not counted correctly according to the codebook. Most often, the models counted too many actuators (23 assemblies), for example by treating passive parts such as guide rods, profiles or bearings, or actuators belonging to the end effector, as actuators of the main function. For six assemblies, the models overlooked actuators or counted two actuators with different directions of motion as one. Information overload (12 assemblies) occurred when the main drawing was outnumbered by supplier catalogues, manuals, quotations or data sheets, so that the model classified a purchased component instead of the assembly. Two observations show that this cause occurred more frequently with image input. First, in the input comparison, where the same models were run with all three input representations, errors of this kind occurred mainly in the image runs. Second, among the final configurations, these errors occurred most frequently with GPT-5.5, the only configuration using image input.

主要原因列于表 5.7。在两组中，执行器计数错误都是最大的一类，占 58 个装配体中的 29 个。对于这些装配体，模型没有按照 Codebook 正确统计执行器。最常见的是模型数出的执行器太多（23 个装配体），例如把导杆、型材、轴承等被动零件，或属于末端执行器的执行器，当成实现主功能的执行器。在 6 个装配体中，模型遗漏了执行器，或将两个运动方向不同的执行器计为一个。信息过载（12 个装配体）出现在主图纸被供应商目录、手册、报价或数据表淹没的时候，模型分类的是外购件，而不是装配体本身。两项观察表明，这一原因在图片输入中出现得更频繁。第一，在输入形式比较中，同一批模型分别使用了三种输入形式，这类错误主要出现在图片输入的运行中。第二，在最终配置中，这类错误最常发生在 GPT-5.5 上，它是唯一使用图片输入的配置。

The gantry test was misapplied in ten assemblies. For these assemblies, the models confused double-sided guidance and a single-sided cantilever, or were misled by part names such as “Portalachse”. In five assemblies, the cause lay in the documentation itself: drawings and bill of materials contradicted each other, the 3D model was faulty, or the component that determines the class was missing. Consequently, these errors do not reflect faulty model reasoning. In the remaining two assemblies, the models did not recognise handling as the main function; for example, Gemini 2.5 Pro classified a gantry with a dosing head as a dosing unit.

十个装配体的龙门判断出了错。对于这些装配体，模型混淆了双侧导向和单侧悬臂，或受到“Portalachse”等零件名称的误导。五个装配体的错误原因在于资料本身：图纸和 BOM 互相矛盾，3D 模型有误，或者决定类别的部件不在资料中。因此，这些错误不能反映模型推理存在问题。其余两个装配体中，模型没有把搬运识别为主功能。例如，Gemini 2.5 Pro 把一个装有计量头的龙门当成了计量装置。

**Table 5.7. Primary causes of misclassification (number of assemblies) / 表 5.7 错误分类的主要原因（装配体数）**

| Cause / 原因 | Input comparison / 输入形式比较 | Final configurations / 最终配置 | Total, distinct / 合计（去重） |
| --- | ---: | ---: | ---: |
| Actuator miscounting / 执行器计数错误 | 20 | 18 | 29 |
| Information overload / 信息过载 | 11 | 8 | 12 |
| Gantry test misapplied / 龙门判断错误 | 10 | 5 | 10 |
| Incomplete or inconsistent documentation / 资料不完整或不一致 | 3 | 5 | 5 |
| Other / 其他 | 0 | 2 | 2 |
| **Total / 合计** | **44** | **38** | **58** |

**④ Examples / 典型案例**

The following three assemblies illustrate the causes. For the rotary unit 0804GE7738, all four models described only the purchased guided cylinder from its data sheet when given image input and classified the assembly as Linear Unit; Claude Opus 4.8 even stated that the designation “Rotationseinheit” contradicted the documentation. The rotary module was recognised when PDF and text input were used. For 0804EN7325, the four final configurations predicted Gantry in 38 of 40 runs. The models treated the gantry criteria as satisfied because they interpreted the double-sided guidance as a portal structure and assumed a third axis, although the assembly has only two linear axes. The robot 0804KF8538 shows a case of incomplete documentation: its bill of materials lists the robot base, plates, centring sleeves, clamps and hose fittings, but not the robot itself, which appears only as a reference contour in the drawing. This graphical information was lost when text input was used. DeepSeek-V4-Flash noted the designation “Roboter” but, finding no actuator in the bill of materials, predicted None of the Available Classes.

以下三个装配体说明了这些原因。对于旋转单元 0804GE7738，四个模型在图片输入下都只根据数据表描述了外购的导向气缸，并把装配体判为直线单元；Claude Opus 4.8 甚至指出名称“Rotationseinheit”与资料矛盾。采用 PDF 和文本输入时，模型识别出了旋转模块。对于 0804EN7325，四种最终配置在 40 次运行中有 38 次预测为龙门。模型将双侧导向理解为门式结构并假设存在第三根轴，因此认为龙门条件已满足，但装配体实际上只有两根直线轴。机器人 0804KF8538 是资料不完整的例子：它的 BOM 列出了机器人底座、板件、定心套、夹子和软管附件，但没有机器人本体；机器人本体只以参考轮廓的形式出现在图纸中。采用文本输入时，这部分图形信息丢失了。DeepSeek-V4-Flash 注意到了名称“Roboter”，但由于在 BOM 中找不到执行器，预测为“不属于任何可用类别”。

**⑤ Summary / 小结**

Most errors arose before the decision matrix was applied: in counting the actuators and in identifying which documents describe the assembly. Errors involving the application of the class rules themselves, such as the gantry test, occurred less often. This points to the preparation of the input documents and the guidance for counting actuators as the main starting points for improvement.

大多数错误发生在应用决策矩阵之前：统计执行器，以及判断哪些资料描述的是装配体本身。类别规则本身的应用错误较少，例如龙门判断错误。因此，改进的主要切入点在于输入资料的整理，以及执行器计数规则的说明。

## 5.8 Average Cost per Assembly | 每个装配体的平均成本

The cost of LLM-based classification was calculated using the token counts reported by the APIs and the list prices of the platforms at the time of the experiments. Table 5.8 shows the means per assembly for the 70 assemblies of the supplementary set. For the final configurations, the cost per assembly ranged from USD 0.004 with DeepSeek-V4-Flash to USD 0.098 with GPT-5.5, corresponding to a cost of USD 0.77 to USD 18.14 for classifying all 185 assemblies.

LLM 分类成本依据 API 报告的 token 数量和实验期间所用平台的公开标价计算。表 5.8 列出了补充数据集 70 个装配体的每个装配体平均值。最终配置的每个装配体成本从 DeepSeek-V4-Flash 的 0.004 美元到 GPT-5.5 的 0.098 美元不等，分类全部 185 个装配体的成本相应为 0.77 至 18.14 美元。

The number of input tokens depended on the one hand on the extent of the documentation and on the other hand on how each provider processes the input. For all providers, image token counts depend on resolution rather than content, while text token counts depend on text length. PDF documents, however, are processed differently: Gemini treats each page as an image with a fixed number of tokens, whereas Claude receives the text extracted from each page in addition to the page image (Google, 2026; Anthropic, 2026). Consequently, the input token count for Gemini 2.5 Pro was only about one fifth of that for the two Claude models when processing the same PDF documents. At the same time, Gemini 2.5 Pro generated about 2,000 reasoning tokens per assembly, so its cost arose mainly from output tokens. Text input used more tokens than the image-based input of Gemini 2.5 Pro and GPT-5.5, with DeepSeek-V4-Flash receiving approximately 22,000 input tokens per assembly, more than twice the number for Gemini 2.5 Pro. Two reasons contribute to this. First, text input includes the full text of all documents, including lengthy data sheets, so its token count increases with the amount of text, while a page processed as an image is counted equally regardless of its text content. Second, the text files were small enough to be sent in full, whereas some large PDF documents had to be shortened to meet the request size limits.

输入 token 的数量一方面取决于资料的多少，另一方面取决于各厂商处理输入的方式。所有厂商的图片 token 数量取决于分辨率，与内容无关，文本 token 数量则取决于文本长度。但 PDF 的处理方式不同：Gemini 把每一页当作一张图片，按固定数量的 token 计；Claude 则在每页图片之外，还额外接收从该页提取的文本（Google, 2026; Anthropic, 2026）。因此，处理相同的 PDF 资料时，Gemini 2.5 Pro 的输入 token 数量仅为两个 Claude 模型的约五分之一。与此同时，Gemini 2.5 Pro 每个装配体生成约 2,000 个推理 token，因此它的成本主要来自输出 token。文本输入使用的 token 多于 Gemini 2.5 Pro 和 GPT-5.5 基于图片的输入。DeepSeek-V4-Flash 每个装配体约接收 22,000 个输入 token，是 Gemini 2.5 Pro 的两倍多。这有两个原因。第一，文本输入包含全部资料的完整文本，包括篇幅较长的数据表，因此 token 数量随文本量增加。作为图片处理的页面，无论包含多少文字，计数均相同。第二，文本文件足够小，可以完整发送；而部分较大的 PDF 资料必须截断，才能满足请求大小的限制。

The configuration with Gemini 2.5 Pro achieved the highest Allowed Accuracy (Table 5.6) and had the second lowest cost. DeepSeek-V4-Flash cost about one eighth as much, but its Allowed Accuracy across the 185 assemblies was 4.7 percentage points lower. Claude Opus 4.8 was excluded from the final configurations because of its cost (Section 5.5), which was USD 0.28 per assembly, or 5.3 times the cost of Claude Haiku 4.5 for a similar number of tokens, reflecting the difference in list prices. For the 1,150 requests of the stability experiment, this would have amounted to about USD 320 instead of about USD 60.

Gemini 2.5 Pro 配置的 Allowed Accuracy 最高（表 5.6），成本则为第二低。DeepSeek-V4-Flash 的成本约为它的八分之一，但在 185 个装配体上的 Allowed Accuracy 低 4.7 个百分点。Claude Opus 4.8 因成本原因未纳入最终配置（第 5.5 节）。它的每个装配体成本为 0.28 美元，在 token 数量相近时是 Claude Haiku 4.5 成本的 5.3 倍，反映了两者公开标价的差异。按稳定性实验的 1,150 次请求计算，这意味着约 320 美元，而 Haiku 约为 60 美元。

**Table 5.8. Mean token usage and cost per assembly (supplementary set, 70 assemblies) / 表 5.8 每个装配体的平均 token 用量和成本（补充数据集，70 个装配体）**

| Configuration / 配置 | Input tokens / 输入 token | Output tokens / 输出 token | Cost per assembly (USD) / 每个装配体成本（美元） | Cost for 185 assemblies (USD) / 185 个装配体成本（美元） |
| --- | ---: | ---: | ---: | ---: |
| Claude Haiku 4.5 (PDF) | 50,836 | 361 | 0.053 | 9.74 |
| DeepSeek-V4-Flash (Text) | 22,201 | 143 | 0.004 | 0.77 |
| Gemini 2.5 Pro (PDF) | 9,983 | 2,167 | 0.034 | 6.32 |
| GPT-5.5 (Image) | 17,747 | 310 | 0.098 | 18.14 |
| Claude Opus 4.8 (PDF) | 54,700 | 385 | 0.280 | 51.84 |

*Note: Means per assembly, one request each. Output tokens include reasoning tokens. Token counts refer to the input actually sent, after any shortening. Cost for 185 assemblies extrapolated from the mean cost per assembly.*

注：每个装配体的平均值，每个装配体一次请求。输出 token 包含推理 token。token 数量指实际发送的输入，即截断后的输入。185 个装配体的成本由每个装配体的平均成本推算。

## 5.9 Summary | 小结

The LLM-based classification of handling assemblies was evaluated against the revised ground truth, covering the selection of prompt and input representation and the final configurations on all 185 assemblies. The main results are as follows:

本章以修订后的 Ground Truth 为参考，评价了基于 LLM 的操作类装配体分类，涵盖 Prompt 和输入形式的选择，以及最终配置在全部 185 个装配体上的表现。主要结果如下：

- **Prompt and input.** Including the decision logic in P3 increased Allowed Accuracy by 2.6 to 8.8 percentage points, while the examples and exceptions in P4 did not produce a consistent further improvement. PDF and text input performed similarly, while image input was 9 to 14 percentage points below PDF input.

  **Prompt 与输入形式。** 在 P3 中加入决策逻辑使 Allowed Accuracy 提高了 2.6 至 8.8 个百分点，而 P4 中的例子和例外没有带来一致的进一步提升。PDF 和文本输入的结果相近，图片输入则比 PDF 输入低 9 至 14 个百分点。

- **Final configurations.** Across the 115 assemblies in the primary set, the four final configurations achieved Allowed Accuracy values from 89.7 % to 96.4 %, with Gemini 2.5 Pro obtaining the highest result. After Holm correction, only one difference between configurations was significant. Across ten runs, the results were stable, with standard deviations no greater than 0.93 percentage points.

  **最终配置。** 在主数据集的 115 个装配体上，四种最终配置的 Allowed Accuracy 介于 89.7% 和 96.4% 之间，Gemini 2.5 Pro 的结果最高。经 Holm 校正后，配置之间只有一处差异显著。十次运行的结果稳定，标准差最高为 0.93 个百分点。

- **Ambiguity regimes.** All configurations performed worse in regime E2 than in E1, by 3.0 to 9.0 percentage points, so the models encountered difficulties with the same assemblies as the human annotators. For regime M, all configurations achieved high Allowed Accuracy, while the proportion of predictions choosing another allowed label ranged from 6.5 % to 39.4 %.

  **歧义类别。** 所有配置在 E2 上的准确率都比 E1 低 3.0 至 9.0 个百分点，模型和人工标注者在同样的装配体上遇到了困难。在 M 中，所有配置的 Allowed Accuracy 都较高，预测为其他允许标签的比例介于 6.5% 和 39.4% 之间。

- **Errors.** Half of the 58 assemblies that were misclassified at least once were affected by errors in counting the actuators. Information overload was more frequent with image input, and deficient documentation caused five errors. Most errors thus arose before the decision matrix was applied.

  **错误。** 至少出错一次的 58 个装配体中，有一半的错误出在执行器计数上。信息过载在图片输入中更常见，资料本身的缺陷导致了五个错误。因此，大多数错误发生在应用决策矩阵之前。

- **Cost.** The cost per assembly for the final configurations ranged from USD 0.004 to USD 0.098. Gemini 2.5 Pro, the most accurate configuration, was also the second least expensive.

  **成本。** 最终配置的每个装配体成本介于 0.004 和 0.098 美元之间。准确率最高的 Gemini 2.5 Pro，成本也是第二低的。

## 待处理

### 5.1 待办

- [ ] 后续补充预实验 L1–L4 结果的附录，结果需按最终版 GT 重算。
- [ ] **附录 B**：接入方式、模型版本号、输入转换设置、生成参数。
- [ ] 5.4 开头原有一句“Details of the conversion are given in Appendix B.”（中文“转换细节见附录 B”），作者暂时删除，之后决定是否加回。
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

### 5.6 待办

- 数据来源：`scripts/12_validation_regimes/evaluate_validation_regimes.py` 的输出 `Validation_Regimes.xlsx`（2026-11-11）。脚本内置最终版 GT；`Pruefungen` 中 44 条均已核对：40 条为 `0804EN7325` 的 Register M → E2（按第 112 行的处理决定，结果不受影响），4 条为 `0804LU7693`（补充数据集结果文件中主标签为旧值组合单元，最终版为直线单元，ZGT 组合单元）。
- 验证（未出表，正文一句话）：E1+E2 上 70 个对 115 个，Haiku 92.8 / 91.2，DeepSeek 97.1 / 88.5，Pro 98.6 / 95.2，GPT-5.5 100.0 / 90.8；E1 比例 86% 对 60%。补充数据集唯一的 M（`0804LU7693`）四种配置均在允许范围内（Haiku、GPT-5.5 预测组合单元，DeepSeek、Pro 预测直线单元）。
- [x] 5.7 需分析三个 regime 中剩余的全部错误（包括 M 中约 0.3–6.8% 的错误）：已纳入 5.7 的 58 个装配体。

### 5.7 待办

- 数据来源：`thesis/error_cause_mapping.md`（58 个装配体的归类，均已由作者确认）；最终配置的错误来自脚本 12 的 `Fehler_BG` / `Fehler_GPT_DeepSeek`，推理由脚本 14 汇总。
- 图 5.1 的数字从 `konfusion_gesamt.png`（脚本 13）读取：模型 35 个错误（Haiku 10、Pro 4、GPT-5.5 9、DeepSeek 12），人工 98 个错误 / 789 条标注。GPT-5.5 矩阵 A 行和 C 行的拆分需对照原始数据核对。
- [ ] 图 5.1 中各张 LLM 矩阵来自哪次运行（Haiku、Pro：输入形式比较的 PDF 运行；GPT-5.5、DeepSeek：稳定性实验第 1 次运行），待定写在图注还是附录。
- [ ] `0804EN7325`：“只有两根直线轴”依据原错误分析（Z/X 两轴），请确认；38/40 = Haiku 10、DeepSeek 10、Pro 8、GPT-5.5 10。
- 人工与模型的错误率不作比较（GT 由人工标注得出，且人工为单个标注者的判断）。

### 5.8 待办

- 数据来源：`scripts/15_cost_summary/summarize_costs.py` 的输出 `Kosten_5_8.xlsx`（2026-11-11），五个 70BG 结果文件（含 Opus 4.8 重跑，PDF）。价格：Haiku 4.5 Vertex AI 1 / 5（全局端点；区域端点 +10%）；Gemini 2.5 Pro Vertex AI 1.25 / 10（≤ 200k）；GPT-5.5 Azure OpenAI 5 / 30（取自 model_pricing.json，未另行核对）；DeepSeek-V4-Flash Azure AI Foundry 0.19 / 0.51；Opus 4.8 5 / 25。
- 用时不报告：只有 GPT-5.5 有 API 延迟（中位数 5.4 s）；其他配置的 `Run_Time` 是整次运行的开始时间，10 次运行为手动启动、中间有间隔。
- [ ] 第 4 章有两处说 Workshop 用时作为第 5 章的人工基准（4.3、4.6）；5.8 暂不提人工用时，之后需决定改第 4 章还是在 5.8 加一句（工程师 31 s，185 个约 1.6 h）。
- [ ] 附录 D（可选）：输入形式比较的 token 表（Gemini 2.5 Flash / Pro × 图片 / PDF / 文本，115 个装配体；Gemini 2.5 Pro 文本约 26,600、PDF 约 9,300、图片约 4,000 个输入 token）。正文已不再引用。
- 注意：各厂商分词器不同，DeepSeek 与 Gemini 的 token 数只能粗略比较。
- [ ] 参考文献：Google (2026) Gemini API – Document understanding（https://ai.google.dev/gemini-api/docs/document-processing，“Each document page is equivalent to 258 tokens”）；Anthropic (2026) PDF support（https://platform.claude.com/docs/en/build-with-claude/pdf-support，每页转换为图片并附上提取的文本）。访问日期待补。
- [ ] 价格表和截断规则（三阶段：100 页预截断到 10 页；过大时封顶 10 页再逐页减到 4 页；仍过大则丢弃最大 PDF）暂不放附录 B，之后再定。
- DeepSeek-V4-Flash 未开启思考（reasoning_tokens = 0）；GPT-5.5 每个装配体平均 174 个推理 token，Gemini 2.5 Pro 2,018 个。

### 章节安排

第 5 章结构（2026-11-11 调整）：5.1 Setup and Configurations / 5.2 Ground Truth Revision and Evaluation Metrics / 5.3 Prompt Design / 5.4 Input Representation / 5.5 Final Configurations and Stability（115 个 × 10 次）/ 5.6 Performance Across Ambiguity Regimes（不分三级标题；与 115 个的 E1+E2 比较只用一句话交代，不出表；185 个合并，E1、E2、M 分开报告，按装配体计算——115 个取 10 次运行中分对的比例，70 个取 0/1，再对 185 个求平均，Bootstrap 也按 185 个装配体抽样；脚本 09 不能直接这样算，需单独计算）/ 5.7 Error Analysis / 5.8 Average Cost per Assembly / 5.9 Summary。

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
