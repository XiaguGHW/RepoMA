# 5 Experimental Evaluation

The LLM-based classification is evaluated in this chapter using the ground truth established in Chapter 4 as the reference. After the experimental setup and the evaluation metrics, the chapter first reports the selection of prompt and input representation and then the performance, stability and errors of the final configurations. The chapter concludes by validating the final configurations on the supplementary set and comparing their cost and processing time with those of human classification.

本章以第 4 章建立的 Ground Truth 为参考，评价基于 LLM 的分类。在介绍实验设置和评价指标之后，本章先报告 Prompt 和输入形式的选择，再报告最终配置的表现、稳定性和错误。最后，在补充数据集上验证最终配置，并将其成本和处理时间与人工分类进行比较。

## 5.1 Setup and Configurations | 实验设置与配置

**① 评价数据集与预实验**

The experiments are based on the 199 assemblies described in Section 4.1. A preliminary experiment was conducted before the main experiments to establish what information the models should return for each assembly. Fourteen assemblies from the primary set, two per class, were classified with Gemini 2.5 Pro in four output formats, which requested either only the primary class or additional information such as alternative classes. The format requesting only the primary class achieved results at least as good as those of the other formats. It corresponds to the codebook rule of assigning exactly one class to each assembly (Section 4.2.1) and allows predictions to be evaluated directly against the allowed label sets without additional scoring rules. All subsequent experiments therefore adopted this output format (Appendix [X]). The 14 assemblies were excluded from the evaluation, which thus covers 185 assemblies: the remaining 115 of the primary set and the 70 of the supplementary set. The results are all based on the final ground truth, with its revision and distribution by class and ambiguity regime presented in Section 5.2.

实验以第 4.1 节介绍的 199 个装配体为基础。在主要实验之前，通过预实验确定模型对每个装配体应返回哪些信息。从主数据集中选取 14 个装配体，每类 2 个，使用 Gemini 2.5 Pro 按四种输出格式进行分类。这些格式分别要求仅返回主类别，或同时返回备选类别等补充信息。仅要求返回主类别的格式，其表现至少与其他格式相当。这一格式符合 Codebook 中每个装配体只归入一个类别的规则（第 4.2.1 节），也使预测结果能够直接与允许标签集合进行比较，无需额外的计分规则。因此，之后的所有实验均采用这一输出格式（附录 [X]）。这 14 个装配体不参与评价，评价因此涵盖 185 个装配体，即主数据集剩余的 115 个和补充数据集的 70 个。所有结果均基于最终版 Ground Truth，其修订以及各类别和歧义类别的分布见第 5.2 节。

**② 实验顺序**

Each experimental stage built on the preceding stage, following a fixed sequence (Table 5.1). Prompt variants and input representations were compared on the 115 assemblies with four models from two providers. The final configurations selected through these comparisons (Section 5.4) were each evaluated in ten runs on the same assemblies to assess performance and stability, as identical requests can produce different LLM outputs (Atil et al., 2024), and in one run on the supplementary set. Since the prompt and the input representation were selected on the primary set, the results on these assemblies may be optimistic. As the supplementary set was excluded from all selection steps, it provides a basis for checking whether the final configurations maintain their performance on additional assemblies (Cawley & Talbot, 2010).

实验按固定顺序进行，每个阶段均以前一阶段为基础（表 5.1）。Prompt 变体和输入形式的比较在这 115 个装配体上进行，使用来自两家厂商的四个模型。通过这些比较选出的最终配置（第 5.4 节）在同一批装配体上各运行十次，用于评价表现和稳定性，因为相同请求可能产生不同的 LLM 输出（Atil et al., 2024）。此外，每种最终配置还在补充数据集上运行一次。由于 Prompt 和输入形式均在主数据集上选定，这些装配体上的结果可能偏乐观。补充数据集未参与任何选择步骤，因此用来检验最终配置在其他装配体上能否保持其表现（Cawley & Talbot, 2010）。

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

## 待处理

### 5.1 待办

- [ ] **附录 [X]**：L1–L4 的结果，按最终版 GT 重算。
- [ ] **附录 [Y]**：接入方式、模型版本号、输入转换设置、生成参数。
- [ ] **GPT-5.5 的 temperature**：查请求日志确认确实是 0。

### 章节安排

输入形式的定义和四种最终配置放在第 5.4 节。
