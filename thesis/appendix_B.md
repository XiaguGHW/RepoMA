# Appendix B Experimental Setup | 附录 B 实验设置（初稿）

> 状态：初稿（2026-11-12）。依据仓库中的脚本（`llm_connector_with_prompt_caching.py`、`run_prompt_development.py`、`create_visual_context_pdfs.py`、`build_raw_text_only_inputs.py`）、结果文件和作者说明整理。标 **[待确认]** 的内容需作者核对；脚本可能不是最终运行时的版本。

## B.1 Access and Model Versions | 接入方式与模型版本

All models were accessed through their application programming interfaces (APIs) on the platforms listed in Table B.1, using the internal model gateway of the company **[待确认：是否写明 Bosch Model Farm]**.

所有模型都通过表 B.1 所列平台的 API 调用，经由公司内部的模型网关接入 **[待确认：是否写明 Bosch Model Farm]**。

**Table B.1. Models, versions and platforms / 表 B.1 模型、版本与平台**

| Model / 模型 | Version / 版本 | Platform / 平台 | Used in / 用于 |
| --- | --- | --- | --- |
| Claude Haiku 4.5 | claude-haiku-4-5@20251001 | Google Vertex AI | 5.3, 5.4, final configuration |
| Claude Opus 4.8 | claude-opus-4-8 **[待确认版本号]** | Google Vertex AI | 5.3, 5.4, cost (5.8) |
| Gemini 2.5 Flash | gemini-2.5-flash **[待确认版本号]** | Google Vertex AI | 5.3, 5.4 |
| Gemini 2.5 Pro | gemini-2.5-pro **[待确认版本号]** | Google Vertex AI | 5.3, 5.4, final configuration |
| GPT-5.5 | gpt-5.5-2026-04-24 | Azure OpenAI | final configuration |
| DeepSeek-V4-Flash | deepseek-v4-flash-2026-04-23 | Azure AI Foundry | final configuration |

## B.2 Generation Parameters | 生成参数

Each assembly was classified in a separate request containing the system prompt, the designation of the assembly and its documentation. The temperature was set to 0 for all models **[待确认：旧版 connector 对 Claude Opus 等思考模型不发送 temperature；GPT-5.5 需查请求日志]**. The maximum number of output tokens was 4,096 **[待确认]**. For the Gemini models, top-p was set to 0.95 and one candidate was requested. DeepSeek-V4-Flash was used without reasoning mode, while Gemini 2.5 Pro and GPT-5.5 generated reasoning tokens with their default settings **[待确认]**. The system prompt was cached where the platform supported prompt caching. Requests that returned an empty output were repeated individually.

每个装配体通过一次单独的请求分类，请求包含系统 Prompt、装配体名称及其资料。所有模型的 temperature 均设为 0 **[待确认：旧版 connector 对 Claude Opus 等思考模型不发送 temperature；GPT-5.5 需查请求日志]**。最大输出 token 数为 4,096 **[待确认]**。Gemini 模型的 top-p 设为 0.95，只请求一个候选输出。DeepSeek-V4-Flash 未开启推理模式；Gemini 2.5 Pro 和 GPT-5.5 按默认设置生成推理 token **[待确认]**。在平台支持的情况下，对系统 Prompt 使用了 Prompt 缓存。返回空输出的请求单独重新运行。

## B.3 Input Conversion | 输入转换

- **PDF:** all PDF files of the assembly (drawings, bills of materials, data sheets, quotations) plus one additional PDF per assembly containing the first eight CAD screenshots and all DFC structure screenshots.
- **Image:** the same documents, with each PDF page rendered as an image at 200 dpi, together with the CAD and DFC screenshots. The images of one assembly were sent in one request, in groups of 15 images **[待确认]**.
- **Text:** the text of all PDF files of the assembly, combined into one text file. Pages with fewer than 20 characters of embedded text were rendered at 200 dpi and read with Tesseract OCR (Smith, 2007; languages German and English, page segmentation mode 6). The additional PDF with the screenshots was not included.

- **PDF：** 装配体的全部 PDF 文件（图纸、BOM、数据表、报价等），另加每个装配体一份 PDF，内含前八张 CAD 截图和全部 DFC 结构截图。
- **图片：** 同样的资料，每页 PDF 以 200 dpi 渲染成图片，再加上 CAD 和 DFC 截图。一个装配体的图片在一次请求中发送，每组 15 张 **[待确认]**。
- **文本：** 装配体全部 PDF 的文本，合并成一个文本文件。嵌入文本少于 20 个字符的页面以 200 dpi 渲染，用 Tesseract OCR 识别（Smith, 2007；德语和英语，页面分割模式 6）。含截图的附加 PDF 不包括在内。

## B.4 Request Size Limits | 请求大小限制

Requests that exceeded the size limits of a platform were reduced in three stages. First, if the PDF documents of an assembly exceeded 100 pages, individually or in total, all PDFs with more than ten pages were cut to their first ten pages before the first request. Second, if a request was rejected as too large, PDFs with more than ten pages were cut to ten pages, and the largest PDFs were then shortened page by page to a minimum of four pages. Third, if the request still exceeded the limit, the largest PDF was omitted. All reductions were recorded in the result files.

超过平台大小限制的请求分三个阶段缩减。第一，如果某个装配体的 PDF 单个或合计超过 100 页，则在首次请求前把所有超过十页的 PDF 截为前十页。第二，如果请求因过大被拒绝，先把超过十页的 PDF 截为十页，再从最大的 PDF 开始逐页缩减，最少到四页。第三，如果请求仍然超限，则丢弃最大的 PDF。所有缩减都记录在结果文件中。

## B.5 Prices | 价格

**Table B.2. List prices used for the cost calculation (USD per million tokens) / 表 B.2 成本计算所用的标价（美元/百万 token）**

| Model / 模型 | Platform / 平台 | Input / 输入 | Output / 输出 |
| --- | --- | ---: | ---: |
| Claude Haiku 4.5 | Vertex AI | 1.00 | 5.00 |
| Claude Opus 4.8 | Vertex AI | 5.00 | 25.00 |
| Gemini 2.5 Pro (≤ 200,000 input tokens) | Vertex AI | 1.25 | 10.00 |
| GPT-5.5 | Azure OpenAI | 5.00 | 30.00 |
| DeepSeek-V4-Flash | Azure AI Foundry | 0.19 | 0.51 |

*Note: Prices at the time of the experiments (2026). Output tokens include reasoning tokens. Claude prices refer to the global endpoint [待确认]; GPT-5.5 price taken from the price list used in the experiments [待确认 Azure 价格].*

注：实验期间的价格（2026 年）。输出 token 包含推理 token。Claude 的价格按全局端点计 [待确认]；GPT-5.5 的价格取自实验所用的价格表 [待确认 Azure 价格]。
