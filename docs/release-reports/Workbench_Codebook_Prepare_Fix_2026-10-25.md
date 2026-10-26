# Workbench 修复：分类规则（Codebook）准备的可观测性、max_tokens 恢复与 TXT 支持

日期：2026-10-25（Europe/Berlin）。分支：`fix/codebook-prepare-observability-txt`（基于 main `4e26c19`）。
状态：**已实现并通过合成数据测试；等待确认后再合并 main。** 未在真实 Bosch Farm 与真实 Codebook PDF 上验证。

## 1 问题与根因

| 现象 | 根因 |
|---|---|
| 点击“准备分类规则”弹出 `127.0.0.1:8765 says` 原生 prompt | `prepareCodebook()` 使用 `prompt()` 读取模型 ID |
| 确认后页面无进度、阶段或结果 | 准备是一次同步长请求；抽屉内状态卡片是打开时复制的静态 HTML，过程中不刷新 |
| 右侧卡片显示被截断的英文内部异常 | 卡片直接取 `#codebookstatus` 文本，CSS 两行截断（`-webkit-line-clamp:2`） |
| 第 3 页 `Error: incomplete Claude response (max_tokens)` 使整份规则失败 | 每页固定 2200 输出 token，提示词要求完整转写页面与表格；遇到 max_tokens 无任何恢复 |
| TXT 被拒绝 | 后端白名单仅 `.pdf`、`.docx` |
| “固定规则分类”像下拉框但点不开 | 真实存在两种模式（固定规则分类 / 解释性追问），但没有已锁定规则和已确认材料时该 `<select>` 被禁用，外观仍是可点击的下拉胶囊 |

## 2 修改文件

| 文件 | 内容 |
|---|---|
| `local_llm_chat_bot/chat_workbench.py` | 规则解析预算配置、可观测任务记录、分块/递增重试、失败分类、后台任务与 `/api/codebook/task`、TXT 流程、前端规则准备面板、页内模型控件、页内确认框、右侧卡片摘要、真实回答模式切换 |
| `local_llm_chat_bot/local_document_library.py` | `decode_text_bytes()` / `read_local_text()`（BOM、UTF-8、UTF-16、Windows-1252、空/二进制/未知编码识别）；PDF 规则提取进度回调 |
| `local_llm_chat_bot/llm_connector_with_prompt_caching.py` | OpenAI 非流式未完成响应附带 `finish_reason`，使 `length` 可被识别为输出上限 |
| `local_llm_chat_bot/workbench_i18n.json` | 新增 120 个中/英/德键（`rulejob.*`、`answer.*`、`confirm.*` 等）；规则文件文案改为 PDF / DOCX / TXT；删除不再使用的 `rulews.model_prompt` |
| `local_llm_chat_bot/ui_copy_inventory.json` | 登记规则准备面板与回答模式两个界面单元 |
| `local_llm_chat_bot/tests/test_codebook_preparation.py` | 新增 19 个后端测试 |
| `local_llm_chat_bot/tests/browser_release.py` | 新增 5 个浏览器测试；辅助函数改用页内模型字段与页内确认框 |
| `local_llm_chat_bot/tests/fixture_support.py` | 本地 mock 同时支持 Claude（rawPredict）响应格式，可模拟真实的 `stop_reason: max_tokens` |

未修改分类校验、材料确认、会话持久化、成本记账和取消协议的既有逻辑；未新增运行时依赖或打包文件，ZIP 未重建（按既有手动工作流在合并后进行）。

## 3 逐项实现说明

### 3.1 准备过程可见、连续、可恢复

- `POST /api/codebook/prepare` 新增 `background: true`：校验路径、类型、模型并占用模型槽后立即返回 `202` 与任务记录，在后台线程执行。不带该参数的 API 调用保持原有阻塞语义（现有测试与脚本兼容）。
- 新增 `GET /api/codebook/task`：返回最近一次任务（运行中或最终状态）、默认/推荐模型与预算摘要。该接口不取全局锁，运行中可随时读取。
- 任务记录包含：真实阶段（读取 → 提取 PDF 原文/OCR/页面图像或 DOCX/TXT → 逐页/逐文本块组解析 → 合并并校验 → 保存）、当前页/总页数或文本块范围/总组数、模型、开始/完成时间、模型调用次数、处理日志（最多 200 条）、最终结果或分类后的失败。不显示百分比。
- 记录同时写入 `AI_Bot_State/codebook_task.json`。刷新页面或重开抽屉时直接显示最近状态；程序在运行中被关闭后，残留的“运行中”记录会被标记为“准备被中断，未保存任何规则”。
- 刷新时若规则准备仍在运行，页面以只读方式接入当前会话（此前 `/api/setup` 会因“忙碌”报错），继续显示进度。
- 前端每秒轮询；运行期间禁用准备、选择/修改规则文件、修改模型、查看、更换、锁定和编辑草稿（后端同样拒绝这些冲突操作，返回 409）。
- 成功后显示文件名、可复制完整路径、文件类型、模型、完成时间、页数或文本块数、解析单元数、模型调用数、TXT 编码与最终状态，并自动打开规则草稿工作区。
- 失败后显示失败阶段、失败页/文本块、可理解原因与“重试”按钮；“停止准备”通过既有 `/api/operation/cancel` 取消。
- 后台任务先释放模型槽再发布最终状态，避免页面看到“成功”时点击锁定却收到“忙碌”。规则保存会改变上下文版本：只有发起任务（或刷新后接入该任务）且当时未过期的页面采用新的上下文令牌，其他标签页仍按既有机制视为过期。

### 3.2 页内“规则解析模型”控件

- 抽屉中新增“规则解析模型”输入框（带已知模型候选列表）、“使用推荐模型”按钮和“本次将使用：…”提示；默认取上次使用的模型，否则为推荐模型 `claude-haiku-5-5`。
- 空值、含空格或无法识别模型族的 ID 在页内提示，不发送请求；后端同样校验（`rulejob.model_invalid`，HTTP 400），不会启动任务。
- 规则准备、锁定、更换流程不再使用 `prompt()` / `alert()` / `confirm()`；锁定与更换改为页内确认框。左侧栏规则文件选择失败也改为页内提示。

### 3.3 max_tokens 恢复（独立、有界、不保存半截 JSON）

`CodebookParseBudget`（不可变 dataclass，仅用于规则解析）：

| 参数 | 值 | 含义 |
|---|---|---|
| `unit_output_tokens` | 2200 | 每页/每组文本块首次请求 |
| `part_output_tokens` | 2200 | 拆分后每个部分 |
| `max_split_depth` | 2 | 先二分，再四分（仅对失败的部分） |
| `min_split_chars` | 400 | 小于此长度的文本不再拆分 |
| `escalated_output_tokens` | 4400 | 无法继续拆分（含纯图像页）时仅一次的递增重试 |
| `merge_output_tokens` | 3500 → 8000 → 16000 | 合并仅在输出上限时递增，最多 3 次 |
| `repair_output_tokens` | 4096 | JSON 语法修复（最多 1 次） |
| `max_total_calls` | 300 | 单次准备的总调用硬上限 |

- 每单元最多 4 次“尝试层级”（整页、二分、四分、递增）；最坏情况每单元 11 次调用；单次准备调用上限 = min(300, 单元数×11+4)。实现为深度优先、首个不可恢复部分即失败，因此持续失败的页通常只用 4 次调用。
- 提示词改为紧凑规则笔记：类别名保留原文，每条定义/规则/边界一句，表格只保留标题、列名与有分类意义的行，禁止逐字复述整页。
- 识别 Claude `max_tokens`、Gemini `MAX_TOKENS`、OpenAI `length`。截断响应从不解析；每个页/块笔记必须是完整 JSON 对象，否则以“无效 JSON”失败；最终草稿仍经既有解析/修复/规则 ID 校验。
- 最终失败示例（中文）：“第 3 页内容过长，已尝试 4 次仍无法完成。请重试，或改用输出能力更强的模型。”；卡片：“准备失败：第 3 页输出长度不足”。原始 `Error: incomplete Claude response (max_tokens)` 仅出现在诊断详情中。
- 失败的模型调用仍计入会话用量与成本。

### 3.4 TXT 规则文件

- 白名单 `.pdf/.docx/.txt`，后缀大小写不敏感。TXT 本地读取，不进入 PDF 页读取、OCR 或页面图像逻辑。
- 编码顺序：BOM（UTF-8/UTF-32/UTF-16）→ 严格 UTF-8 → 无 BOM 的 UTF-16（按 NUL 分布判断）→ Windows-1252（拒绝控制字符过多的结果）。空文件、二进制文件和无法识别的编码分别给出明确原因，且不调用模型。普通材料中的 TXT/MD 也用同一解码，失败时保留原有的宽松回退。
- TXT 与 DOCX 一样按文本块（与材料分节标签 `文件名 — section i/n` 一致）分组解析，引用写入 `blocks` / `evidence_blocks`，不伪造页码；模型若把块号写进 `pages`，会被移到 `blocks`。随后进入同一草稿、校验、锁定与分类流程（分类时按“无页码规则”要求章节/文本块引用）。
- “查看规则”对 TXT/DOCX 显示“依据文本块”，并显示“OCR：TXT 不适用”。

### 3.5 右侧卡片与错误展示

- 卡片只显示简洁完整状态：未选择规则文件 / 正在准备：第 3 / 12 页 / 已准备草稿，等待确认锁定 / 已锁定并可用于分类 / 准备失败：第 3 页输出长度不足；取消截断，允许换行。
- 新文件准备失败而旧规则已锁定时，卡片显示第二行“当前有效规则：Rules.docx（已锁定并可用于分类）”，面板注明“此次失败未改变现有规则”。规则文件只在全部步骤成功后才写入，旧规则不会被覆盖。
- “处理记录与诊断详情”可展开，含带时间的处理日志、原始技术详情与完整诊断 JSON，并提供“复制诊断信息”（剪贴板不可用时提示手动复制）。

### 3.6 “固定规则分类”伪下拉框

产品确有两种模式，因此改为真实的两段式切换（固定规则分类 / 解释性追问），并在旁边说明当前模式的作用。没有已锁定规则和已确认材料时，不显示切换，改为静态标签“当前模式：普通问答”并说明“锁定分类规则并确认材料后，才可使用固定规则分类”。发送给后端的 `require_classification` 语义不变。

## 4 测试

### 4.1 命令（在 `local_llm_chat_bot/` 下）

```bash
python -m unittest discover -s tests -v
PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python tests/browser_release.py
python -m ruff check --select E9,F63,F7,F82 .
python -m ruff check .
python -m mypy
python -m compileall -q .
git diff --check
```

### 4.2 实际结果

| 检查 | main 基线 `4e26c19` | 本分支 |
|---|---|---|
| unittest discovery | 244 运行，243 通过，1 跳过 | **263 运行，262 通过，1 跳过，0 失败** |
| 浏览器（Chromium） | 20/20 通过 | **25/25 通过**，无 pageerror、无未知翻译键告警 |
| Ruff 致命子集 | 退出 0 | 退出 0 |
| 完整 Ruff | 全部通过 | 全部通过 |
| mypy（11 个应用模块） | 10 个既有错误 | 10 个（未增加） |
| compileall / git diff --check | 退出 0 | 退出 0 |

唯一跳过项仍是 `test_native_windows_case_and_junction`（需要原生 Windows NTFS）。

### 4.3 需求测试对应

| # | 要求 | 测试 |
|---|---|---|
| 1 | PDF 成功准备、查看、锁定、刷新后恢复 | `test_pdf_background_job_reports_stages_then_view_lock_and_restore`；浏览器 `test_rule_preparation_shows_live_progress_without_native_dialogs_and_restores`（运行中刷新、完成后再刷新） |
| 2 | DOCX 成功准备 | `test_docx_prepares_with_text_block_references`、既有 DOCX 流程 |
| 3 | TXT：UTF-8 / BOM / UTF-16 / Windows-1252、空、二进制、未知编码 | `test_txt_rule_files_decode_common_encodings_locally`、`test_txt_empty_binary_and_unknown_encoding_fail_clearly_without_model_calls`、浏览器 `test_txt_rules_prepare_and_show_text_block_references` |
| 4 | 第 3 页 Claude max_tokens：页号、可理解错误、按设计重试、不保存半截规则 | `test_pdf_page_three_max_tokens_recovers_by_splitting_only_that_page`、`test_pdf_page_three_persistent_max_tokens_fails_with_page_and_attempts`、`test_merge_output_limit_escalates_within_its_own_bounded_budget`、`test_total_call_limit_stops_a_run`；浏览器 `test_rule_page_three_max_tokens_is_explained_and_old_rules_stay_in_effect` |
| 5 | 旧锁定规则在新规则失败后仍可用且状态明确 | `test_failed_new_rules_keep_old_locked_rules_in_effect`；上述浏览器测试（含分类仍可用） |
| 6 | 无网络、超时、无效 JSON、用户取消均收尾 | `test_network_failure_closes_job`、`test_model_timeout_closes_job`、`test_invalid_json_from_page_and_from_merge_is_rejected`、`test_user_cancel_of_background_job_is_recorded_and_saves_nothing`、`test_interrupted_running_record_is_closed_after_restart`；浏览器 `test_rule_preparation_stop_closes_job_and_reenables_controls` |
| 7 | 卡片不截断，详情可看完整诊断 | 浏览器 max_tokens 测试（卡片全文、无裁剪、诊断 JSON、复制） |
| 8 | 不再调用原生 prompt() | `test_frontend_has_no_native_model_prompt_or_dead_mode_dropdown`；浏览器测试记录对话框事件为 0 |
| 9 | “固定规则分类”不再是伪下拉框 | 浏览器 `test_rule_model_validation_and_answer_mode_are_in_page_controls`、`test_explicit_explanation_mode_and_nonpaged_rule_references` |
| 10 | 中/英/德完整 | `test_every_failure_message_is_complete_in_three_languages`、目录校验、浏览器中三语切换断言与既有“英/德无中文界面”全流程测试 |

## 5 测试环境说明（如实记录）

本沙箱无法访问 PyPI 与 crates.io，依赖按以下方式就地准备，不属于仓库内容：

- FastAPI 0.162.0 与 annotated-doc 取自 GitHub 源码；OpenAI SDK 1.82.0 取自 GitHub 源码；httpx 0.28.1、ruff 0.16.9、mypy 2.3.1 取自本机缓存（与 requirements-dev 固定的 ruff 0.17.2 / mypy 1.15.0 不同，基线与分支用同一版本对比）。
- PyMuPDF 1.26.5 + MuPDF 1.26.10 从源码编译（SWIG 4.3.1、libclang 18）。
- OpenAI SDK 依赖的 Rust 扩展 `jiter` 无法编译，测试虚拟环境内用标准库 `json` 写了一个仅供测试的替身（仅支持完整 JSON）。该替身装入后，基线 OpenAI 流式测试全部通过。
- Linux、Python 3.13、Chromium（Playwright 浏览器目录 `/opt/pw-browsers`），非目标 Windows/Bosch 环境。

## 6 仍存在的限制与风险

- 未使用真实 Bosch Farm 和 `Codebook_Baugruppenklassifikation_v2_3.pdf` 验证；第 3 页能否在 2200 token 的二分/四分内完成取决于该页真实文本量与模型。纯图片/扫描表格页无法按文本拆分，只能进行一次 4400 token 递增重试；若仍失败会明确报错，可改用输出能力更强的模型。
- 拆分后的部分仍附带整页图像（作布局参考），输入 token 成本随拆分增加；输出 token 与总调用次数有硬上限。
- 合并步骤在输出上限时可递增到 16000 token（低于连接器 32000 上限），针对很大的 Codebook 仍可能失败。
- 规则文件以外的原生对话框保持不变：规则草稿编辑的放弃/保存确认、会话重命名/删除、应用修改计划确认、非规则文件选择错误。
- 刷新后“只读接入运行中任务”仅针对规则准备；聊天流式请求进行中刷新仍沿用既有“忙碌”提示。
- DOCX/TXT 新准备的规则改为 `blocks` 引用（此前 DOCX 分段号被写入 `pages`）。已锁定的旧 DOCX 规则不受影响；无页码规则分类本就不使用页码。
- `GET /api/codebook/task` 返回任务前后的上下文令牌，仅用于发起页面恢复绑定；本程序只监听 127.0.0.1，风险低，但这是对上下文令牌可见性的放宽。
- 预算为代码常量（可测试、可修改），尚未提供环境变量覆盖。
- 无 BOM 且含 Windows-1252 未定义字节（0x81、0x8D、0x8F、0x90、0x9D）的 Latin-1 文本会被判为“编码无法识别”，需另存为 UTF-8。

## 7 补充：三语界面复核（第二个提交）

按“进行中 / 成功（TXT）/ 失败（第 3 页 max_tokens，旧规则已锁定）/ 已取消”四种状态，在中、英、德三种界面语言下分别截图并检查抽屉面板、右侧卡片与回答模式区域：均无未翻译的键、无残留占位符，英/德界面中除文件路径外无中文。复核中发现并修复两处问题：

- 规则准备（或回答生成）运行期间切换界面语言时，页面立即切换，但保存语言设置的 `/api/language` 会等待任务持有的全局锁，直到任务结束才返回。现改为模型任务运行期间不等待该锁（此时会话切换本就被拒绝，任务使用自己的会话副本），浏览器测试断言运行中三次切换各在 3 秒内完成且面板随之更新。
- 英/德日志文案“1 classes / 1 Klassen”“1 text blocks”在单数时语法不对，改为“（classes: 1, model calls: 4）”式写法。

复测：unittest 263 运行（1 跳过）全部通过；浏览器 25/25；ruff 通过；mypy 10（未增加）；compileall、git diff --check 通过。

## 8 现场反馈后的修复：分段合并与已完成页面复用（2026-10-26）

真实 6 页 Codebook 上第 3 页已顺利解析，但合并阶段一次输出整份规则：3500、8000 token 均触发输出上限，16000 token 的单次生成约 90 秒后被公司网络代理切断（`Error after 3 attempts: ProxyError`），界面却提示“无法连接 Bosch Farm，请检查网络或 VPN”，具有误导性。

- 合并先尝试一次 3500 token；若触发输出上限，不再递增到 8000/16000，而改为**分段合并**：类别目录 → 每个类别一次 → 通用规则 → 表格规则，每段最多 3500 token，失败时以“更简洁”要求重试一次（7000 token），在本地拼装后照常校验。整份笔记放在系统提示中，Claude 可使用提示缓存降低重复输入成本。单次请求变短，不再触及代理超时。
- **已完成页面复用**：成功解析的页/文本块笔记按“文件内容 + 模型 + 解析提示版本”保存在 `AI_Bot_State/codebook_note_cache/`。重试时直接复用，不再重复付费，日志显示“第 X 页已在上次成功解析，直接复用”。更换模型或文件内容变化时不会复用。
- `ProxyError` 归类为“被网络代理中断”，提示说明长请求后的代理超时并告知重试会复用已完成页面。
- 预算：`merge_output_tokens=(3500,)`，`section_output_tokens=(3500, 7000)`，`max_merge_classes=40`；总调用上限仍为 300。

新增测试：分段合并（复现现场情形）、分段输出上限失败、重试复用页面、代理中断分类。复测：unittest 266（1 跳过）全部通过；浏览器 25/25；ruff 通过；mypy 10（未增加）。

## 9 材料预读：逐组缓存与限定输出形式（2026-10-26）

目标是减少材料预读的截断和重复 token 消耗。已选定的“截断时对失败组拆分一次”（第 3 步）和“额外重试总上限”（第 4 步）留待后续实现。

- **逐组缓存（第 1 步）**：以前，一个文件只要有一组失败，整份摘要就不缓存，重新扫描会把所有组重读一遍。现在每个成功组的笔记按“组文本 + 模型 + 提示版本”保存在 `AI_Bot_State/material_cache/<文件哈希>/groups/`，重新扫描只为失败的组和最后的合并付费。扫描结果新增 `text_groups_reused` 字段。“重建此文件缓存”和“清除摘要缓存”会一并删除这些组笔记；换模型时不复用。
- **限定输出形式（第 2 步）**：组提示要求最多 10 条要点，每条一句、约 50 个汉字以内，标注来源标签，表格只摘关键行；合并提示要求最多 15 条要点，同时保留冲突、不确定处和证据标签。token 上限不变（900 / 1400）。提示改动只会使组笔记缓存失效；已完成的文件摘要缓存仍然有效，不会重新付费。

新增 `tests/test_material_preread_cache.py`（3 个测试）。复测：unittest 269（1 跳过）全部通过；浏览器 25/25；ruff 通过；mypy 10（未增加）。

### 9.1 第 3、4 步：截断组拆分一次与每次扫描的重试上限

- **第 3 步**：只有因输出上限被截断的组才会拆分，并且只拆一次。拆分点优先选在带标签的片段之间并靠近中间；如果整组只有一个长片段，就在文本中间拆开，第二半重复原标签，保证每半都能追溯来源。两半沿用 900 token 上限，不加大预算，也不再继续拆分。两半都成功时，合并后的笔记按整组缓存；某一半仍被截断时，记为“组 X 第 2/2 部分：…”，该文件标为未完整覆盖，已有内容照常使用。重新扫描时，已缓存的那一半和整组都不会再次付费，只重试失败的那一半。
- **第 4 步**：每次扫描的额外重试调用数不超过 max(2, 组数 × 20% 向上取整)，且最多 10 次，每次拆分消耗 2 次。超出上限的截断组不再重试，标为“本次扫描的拆分重试已达上限（N 次）”。“扫描状态”显示“拆分重试 X 次（本次上限 N 次）”，扫描结果中记录 `retry_calls` 和 `retry_limit`。
- 非截断类失败（如安全拦截、网络错误）不拆分，处理方式与以前相同。

新增 3 个测试：截断组拆分后在同一次扫描内完成；仍被截断的一半如实标出，且下次只重试这一半；重试上限限制额外调用数。复测：unittest 272（1 跳过）全部通过；浏览器 25/25；ruff 通过；mypy 10（未增加）。

## 10 现场反馈：代理隧道超时被误报为“模型 300 秒未返回”（2026-10-26）

现场日志中，第一次 3500 token 合并触发输出上限，随后改为分段合并；类别目录合并成功，“类别 KLASSE 1 Lineareinheit”在 12:23:41 发出，12:23:46 失败。界面提示“模型未在规定时间内返回完整结果”，技术详情为 `no complete response within 300 s (ReadTimeout)`。

**根因**：失败只用了 5 秒，恰好等于连接超时（原默认 5 秒），而不是 300 秒的响应超时。经 HTTP(S) 代理访问时，代理建立隧道（CONNECT）过慢，`requests` 会在**连接**超时后抛出 `ReadTimeout`，异常信息为 “read timeout=<连接超时值>”。这已在本地用一个故意变慢的代理复现。此时请求从未发送到 Bosch Farm，不会产生费用，但原逻辑把它当作“模型可能仍在生成”，既不重试，提示文字也写错了。

**修复**：
- 只有同时满足两个条件才判定为“连接建立阶段超时”，并像连接错误一样自动重试（最多 3 次）：异常中报告的超时值等于连接超时，且失败时间早于连接超时 + 1.5 秒。其他 ReadTimeout 仍不重试，避免重复付费生成。最终提示说明“请求未发出、不产生费用”，并给出 `WORKBENCH_CONNECT_TIMEOUT_SECONDS` 的调整建议。真正的读超时提示改为报告实际使用的超时值。
- 连接超时默认值由 5 秒改为 15 秒（README 已更新），适应较慢的公司代理；仍可在 `.env` 中设置 `WORKBENCH_CONNECT_TIMEOUT_SECONDS`（0.05–60）。
- 分段合并中成功的部分（类别目录、各类别、通用规则、表格规则）按“笔记 + 请求 + 模型”缓存。重试时只补未完成的部分，页面解析结果也照常复用。
- 进度显示修正：类别目录单独显示为“正在分段合并：类别目录”，后续按“第 X / 共 Y 部分”计数，不再出现“第 1 / 共 1 部分”后跳到“第 2 / 共 10 部分”。
- 适用范围：上述连接超时判定只作用于 Gemini/Claude 使用的 HTTP 请求路径；OpenAI 兼容模型使用 SDK 自带的超时处理，未改动。

新增测试：慢代理隧道复现（重试 3 次并给出准确原因）、真正的读超时不重试、判定条件单元测试、合并分段复用、连接超时原因的三语提示。复测：unittest 277（1 跳过）全部通过；浏览器 25/25；ruff 通过；mypy 10（未增加）。

## 11 现场反馈：第 6 页笔记 JSON 格式错误导致整次失败（2026-10-26）

现场日志中，6 页全部完成解析，但第 6 页的回复虽然完整（停止原因正常，不是截断），却不是严格有效的 JSON。技术详情显示这是一段内容完整的规则笔记，旧逻辑因此判定整次准备失败。

- **宽松解析页/文本块笔记**：允许 Markdown 代码块、对象后的多余文字、第二个对象和尾随逗号。合并分段的结果同样适用。
- **仍无法解析时按原文传递**：回复已确认完整，就以 `unparsed_note` 文本形式交给合并，不重新请求该页，也不调用修复，因此不增加 token。日志显示警告。规则草稿记录 `unparsed_units`，规则工作区顶部提示“请重点核对：第 X 页的模型笔记不是标准 JSON…”（三语）。重试时复用该笔记，提示仍然保留。
- **数据完整性不变**：截断（max_tokens 等）仍会走拆分/失败流程；空回复仍会失败；最终合并出的规则仍经严格解析和校验，并需人工核对后锁定。
- **诊断信息**：任务记录保存解析出错的位置及前后文字，便于查看具体是哪里格式有误。
- **缓存可见性**：解析开始时记录“页面解析缓存：可复用 X / Y 个单元（文件名）”。现场这次 6 页全部重新解析、没有复用 12:22 那次的结果，最可能的原因是新版本解压到了另一个文件夹（缓存保存在程序文件夹的 `AI_Bot_State` 中），有待用户确认。

新增测试：第 6 页笔记格式错误时按原文合并并标出（且不重复调用）、重试时复用并保留标记、常见包装的宽松解析、合并结果为无效 JSON 时仍失败、浏览器中规则工作区显示核对提示。复测：unittest 279（1 跳过）全部通过；浏览器 26/26；ruff 通过；mypy 10（未增加）。
