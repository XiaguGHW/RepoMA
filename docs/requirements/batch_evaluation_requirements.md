# 修改需求：批量补齐 PDF 分类实验评价指标

请先读取当前项目的最新分类/评估脚本和一两个实际结果 Excel。不要根据旧版 RepoMA 脚本猜测列名、Sheet 名或已有的 regime-aware 逻辑。此任务**仅重新计算现有 Excel 中的结果；绝不调用 LLM/API，不重新上传 PDF，也不改变模型预测。**

## 目标和输入

当前有两类已经完成或正在完成的 PDF 实验结果：

1. **可重复性实验**：Gemini 2.5 Pro + `p3_optimized`（原 P5），同一数据集、相同条件运行 10 次，产生 10 个结果 Excel。
2. **跨模型／配置实验**：115 个 PDF BG，14 次完整运行，产生 14 个结果 Excel。

每个原始结果 Excel 的第一个 Sheet 都包含至少：`SAP-Nummer`、`Teamcenter`、`Ground Truth`、`Register`（E1 / E2 / M）、`Weitere zulässige Ground Truth`、`Predicted_Label`、`Confidence_Percent`、`Processing_Status`、`JSON_Parse_Status`、`Run_Model`、`Prompt_Config`。

目前已有总体准确率、Regime-aware 摘要、混淆矩阵和置信度分析；但逐类表中的 `Accuracy` 实际等同于 Recall，例如 Lineareinheit 是 15/20 = 75%。现需补齐/修正正式的逐类指标。

## 请新建一个独立脚本

建议文件名：`scripts/batch_evaluate_experiments.py`。

它必须复用当前项目已有的下列逻辑，而不要重写不一致的新规则：

- `clean_cell_text(...)`
- `canonical_class_label(...)`
- `LABEL_ALIASES`
- `CANONICAL_CLASS_ORDER`
- M 的 primary / accepted-label-set 定义

尤其注意：`Umsetzeinheit` 与 `Kombinierte Einheit` 的已有别名规则应被一致使用；不要把 Roboter 和 Kombinierte Einheit 全局等价化。

## 1. 输入、发现和安全性

脚本接受两个明确输入目录和一个输出目录，例如：

~~~powershell
python scripts/batch_evaluate_experiments.py `
  --repeatability-dir "outputs/repeatability_gemini25pro_p3_optimized" `
  --cross-model-dir "outputs/pdf_cross_model" `
  --output-dir "evaluation_results/batch"
~~~

- 递归发现两个目录中的 `.xlsx`，忽略临时 Excel 文件（如 `~$...xlsx`）和此前生成的汇总 Excel；按文件名排序，保证顺序可复现。
- 每个工作簿读取原始结果数据 Sheet；默认第一个 Sheet，但若第一个不是数据 Sheet，要能明确报错或允许 `--data-sheet` 参数。
- 验证必需列。每个文件记录：原始 BG 行数、可评价行数、缺失预测数、无效/未知标签数、重复 SAP/Teamcenter 数、以及未匹配/跳过原因。
- 不修改第一个 Sheet，不修改模型输出、Ground Truth、Register 或 `Weitere zulässige Ground Truth`。
- 只允许替换/新建名为 `Class_Metrics` 的 Sheet；保留 `Prompt_Evaluation`、`Confusion_Matrix`、`Confidence_Analysis` 和其他所有原 Sheet。
- 写入前使用临时文件并成功后原子替换；一个文件失败时记录异常并继续处理其他文件。

## 2. 可评价行与两种正确性

1. 逐行 canonicalize Ground Truth、预测标签和 M 的允许标签。
2. 严格主标签正确性：`prediction == primary_ground_truth`。
3. M 接受标签集正确性：预测属于该行 `primary + Weitere zulässige Ground Truth`。
4. E1/E2 不扩展允许标签集，故其 accepted-set 与严格结果相同。
5. 普通单标签的 TP/TN/FP/FN、混淆矩阵和每类指标必须只采用**严格主标签**；不要将 M 的多标签接受逻辑硬塞进单标签混淆矩阵。

只有 Ground Truth 和预测都能 canonicalize 的行才进入严格分类指标分母。请清楚输出总数，例如本轮虽然选择 115 个 BG，但某个工作簿可能只有 114 个可评价记录；原因必须保留。

## 3. 每个原始 Excel 新增/更新 `Class_Metrics` Sheet

该 Sheet 至少包含以下两个严格主标签表：

1. `All strict primary-label cases`：E1 + E2 + M；
2. `E1+E2 strict primary-label cases`：仅明确案例。

每个表每个类别一行，输出：

| Class | Evaluated N | Support | TP | TN | FP | FN | Accuracy | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|

~~~text
Support   = TP + FN
Accuracy  = (TP + TN) / Evaluated N
Precision = TP / (TP + FP)
Recall    = TP / (TP + FN)
F1        = 2 * Precision * Recall / (Precision + Recall)
~~~

- 分母为 0 时显示空白或 `N/A`，不得崩溃，也不要伪造 0% 的模型表现。
- 每个表增加 macro / weighted Precision、Recall、F1 和 overall strict accuracy 摘要。
- 不要静默改变旧 `Prompt_Evaluation` 里把 Recall 标为 Accuracy 的历史含义。在 `Class_Metrics` 中明确使用正确公式，并注明 `Accuracy uses (TP + TN) / N; not the legacy class-wise recall`。
- 可保留或增加 Regime-aware 摘要：E1 strict、E2 strict、M strict、M accepted-label-set、All accepted-label-set。

## 4. 产生两个独立的总结 Excel

请不要把可重复性实验和跨模型/配置实验混成一个报告。

### A. `repeatability_gemini25pro_p3_optimized_summary.xlsx`

输入：10 个 Gemini 2.5 Pro + `p3_optimized` 结果 Excel。

包含至少：

1. `Run_Summary`：每次运行一行（文件名、run ID/时间、可评价 N、overall strict accuracy、E1/E2/M strict accuracy、M accepted-set accuracy、macro/weighted P/R/F1）；最后添加10次的 mean / std dev / min / max。
2. `Per_Class_Metrics`：每次运行 × 每个类别一行，含完整 TP/TN/FP/FN/Accuracy/Precision/Recall/F1。
3. `BG_Reproducibility`：每个 BG 一行，列出 Run_01 ... Run_10 预测、不同预测标签数、modal label、modal count、是否10/10完全一致；并汇总完全一致 BG 数/比例、至少一次变化 BG 数/比例和预测标签集合。
4. `Errors`：每次运行的严格错误行，含 BG ID、Register、Ground Truth、Predicted_Label、Confidence_Percent；M 另附 Accepted_Set_Status。

核心不是只比较十个 Accuracy，而是检验相同条件下每个 BG 的预测是否重复一致。

### B. `pdf_cross_model_config_comparison.xlsx`

输入：14 个跨模型/配置 Excel（全部为同一批115个 PDF BG）。

包含至少：

1. `Run_Summary`：每轮一行，含模型、Prompt_Config、文件名、可评价 N、总体 strict accuracy、E1/E2/M strict accuracy、M accepted-set accuracy、All accepted-set accuracy、macro/weighted P/R/F1。
2. `Per_Class_Metrics`：每轮 × 每类一行，含完整 TP/TN/FP/FN/Accuracy/Precision/Recall/F1。
3. `Errors`：每轮严格错误行，保留 BG、Regime、Ground Truth、预测、置信度和 M accepted-set 状态。
4. `Coverage_Check`：对14轮列出实际 BG ID 集合；指出是否与基准115个 BG 集合完全一致，哪些 BG 缺失/额外，及可评价数为何不是115。

## 5. 完成后请反馈

请告知：

- 新建/修改了哪些 Python 文件；
- 准确可复制的运行命令；
- 脚本识别到的每个目录/文件数量（应分别为10和14，若不是应明确报告）；
- 每个工作簿是否成功新增 `Class_Metrics`；
- 两个汇总 Excel 的实际路径；
- 哪些记录被排除及原因；
- 是否真的运行了批量评估，还是只完成脚本和一个/少数 smoke test。