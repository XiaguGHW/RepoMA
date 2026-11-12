# 第 4、5 章引用文献（Zotero 导入用）

整理日期：2026-11-12。第 4 章正文没有文献引用（只引用了本文第 2.5 节等章节）；以下 16 条全部来自第 5 章。

Zotero 导入方式：
- 有 DOI 或 arXiv 编号的：Zotero 工具栏的魔术棒「Add Item by Identifier」，粘贴 DOI 或 arXiv 编号。
- 只有网址的：在浏览器里打开链接，用 Zotero Connector 保存。

| # | 正文引用 | 文献 | 导入用标识 / 链接 | 注意 |
|---|---|---|---|---|
| 1 | Anthropic, 2026 | Anthropic. *PDF support*. Claude Docs. | https://platform.claude.com/docs/en/build-with-claude/pdf-support | 网页；类型选 Web Page，填访问日期 |
| 2 | Atil et al., 2024 | Atil, B. et al. Non-Determinism of "Deterministic" LLM Settings. arXiv. | arXiv:2408.04667 · https://arxiv.org/abs/2408.04667 | 早期版本标题为 “LLM Stability: A detailed analysis with some surprises”；导入后确认年份为 2024（首次提交） |
| 3 | Bender & Lange, 2001 | Adjusting for multiple testing—when and how? *Journal of Clinical Epidemiology*, 54(4), 343–349. | DOI 10.1016/S0895-4356(00)00314-0 | |
| 4 | Berg-Kirkpatrick et al., 2012 | An Empirical Investigation of Statistical Significance in NLP. *EMNLP-CoNLL 2012*, 995–1005. | https://aclanthology.org/D12-1091/ | 无 DOI |
| 5 | Beyer et al., 2020 | Are we done with ImageNet? arXiv. | arXiv:2006.07159 · https://arxiv.org/abs/2006.07159 | 预印本 |
| 6 | Cawley & Talbot, 2010 | On Over-fitting in Model Selection and Subsequent Selection Bias in Performance Evaluation. *JMLR*, 11(70), 2079–2107. | https://jmlr.org/papers/v11/cawley10a.html | 无 DOI |
| 7 | Efron & Tibshirani, 1993 | *An Introduction to the Bootstrap*. Chapman & Hall. | DOI 10.1201/9780429246593 | 导入后年份可能显示 1994（CRC 电子版），正文写的是 1993，二者需统一 |
| 8 | Google, 2026 | Google. *Document understanding*. Gemini API Docs. | https://ai.google.dev/gemini-api/docs/document-processing | 网页；类型选 Web Page，填访问日期 |
| 9 | Holm, 1979 | A Simple Sequentially Rejective Multiple Test Procedure. *Scandinavian Journal of Statistics*, 6(2), 65–70. | https://www.jstor.org/stable/4615733 | |
| 10 | Koehn, 2004 | Statistical Significance Tests for Machine Translation Evaluation. *EMNLP 2004*, 388–395. | https://aclanthology.org/W04-3250/ | 无 DOI |
| 11 | Miller, 2024 | Adding Error Bars to Evals: A Statistical Approach to Language Model Evaluations. arXiv. | arXiv:2411.00640 · https://arxiv.org/abs/2411.00640 | 预印本 |
| 12 | Opitz & Burst, 2019 | Macro F1 and Macro F1. arXiv. | arXiv:1911.03347 · https://arxiv.org/abs/1911.03347 | 最新版 v3 为 2021 年，导入后年份可能显示 2021；正文写的是 2019 |
| 13 | Sclar et al., 2024 | Quantifying Language Models' Sensitivity to Spurious Features in Prompt Design … *ICLR 2024*. | arXiv:2310.11324 · https://arxiv.org/abs/2310.11324 | arXiv 导入为 2023 年预印本；需手动改为 ICLR 2024 会议论文 |
| 14 | Shankar et al., 2020 | Evaluating Machine Accuracy on ImageNet. *ICML 2020*, PMLR 119, 8634–8644. | https://proceedings.mlr.press/v119/shankar20c.html | |
| 15 | Smith, 2007 | An Overview of the Tesseract OCR Engine. *ICDAR 2007*, 629–633. | https://ieeexplore.ieee.org/document/4376991 | 不同数据库给出的 DOI 不一致，建议用 IEEE Xplore 页面导入 |
| 16 | Sokolova & Lapalme, 2009 | A systematic analysis of performance measures for classification tasks. *Information Processing & Management*, 45(4), 427–437. | DOI 10.1016/j.ipm.2009.03.002 | |

## Zotero 批量导入（魔术棒 “Eintrag über Identifier hinzufügen”）

第一步：以下 8 条一次粘贴（先按 Shift + Enter 展开多行输入框），回车导入。依次为 Bender & Lange、Efron & Tibshirani、Sokolova & Lapalme、Atil et al.、Beyer et al.、Miller、Opitz & Burst、Sclar et al.

```
10.1016/S0895-4356(00)00314-0
10.1201/9780429246593
10.1016/j.ipm.2009.03.002
arXiv:2408.04667
arXiv:2006.07159
arXiv:2411.00640
arXiv:1911.03347
arXiv:2310.11324
```

结果（2026-11-12）：3 条 DOI 导入成功（Bender & Lange、Efron & Tibshirani、Sokolova & Lapalme）；5 条 arXiv 编号未能导入（可能是公司网络屏蔽了 arXiv 接口）。改用 arXiv 的 DOI 再试：

```
10.48550/arXiv.2408.04667
10.48550/arXiv.2006.07159
10.48550/arXiv.2411.00640
10.48550/arXiv.1911.03347
10.48550/arXiv.2310.11324
```

依次为 Atil et al.、Beyer et al.、Miller、Opitz & Burst、Sclar et al.。导入后检查文献类型（可能显示为 Preprint 或 Dataset）和年份。若仍失败：在浏览器中打开 arXiv 页面用 Zotero Connector 保存，或点绿色加号手动新建（Preprint；Sclar et al. 选 Konferenz-Paper）。

第二步：以下 2 条逐条尝试（Holm；Smith），找不到时改用第三步。

```
10.2307/4615733
```

```
10.1109/ICDAR.2007.4376991
```

第三步：其余 6 条没有可用的 DOI，用浏览器的 Zotero Connector 保存，或在 Zotero 中点绿色加号手动新建：Berg-Kirkpatrick et al.（Konferenz-Paper）、Koehn（Konferenz-Paper）、Cawley & Talbot（Zeitschriftenartikel）、Shankar et al.（Konferenz-Paper）、Google 和 Anthropic（Webseite，填访问日期）。链接见上表。

导入后检查：Efron & Tibshirani（年份 1993/1994）、Opitz & Burst（2019/2021）、Sclar et al.（改为 ICLR 2024 会议论文）、Atil et al.（年份 2024）、Smith（来源与 DOI）。
