# Workbench 独立发布前复审报告

审查日期：2026-10-25（Europe/Berlin）。审查对象：`XiaguGHW/RepoMA` 的 `local_llm_chat_bot/`。
审查方式：通读文档与核心实现、独立运行现有检查、补充最小合成复现。没有修改业务代码，没有生成/更新 ZIP，
没有触发打包工作流，没有调用真实 Bosch Endpoint，没有使用真实密钥或真实 BG/Codebook/Excel。没有提交或推送。

**结论：不适合进入打包/发布阶段。** 九步修复覆盖了原 R01–R16 的大部分复现，现有回归在本环境可复跑通过。
但本轮新发现 3 项 P1：
- 配置的 env 密钥文件可被模型读取；
- 默认请求时限在真实耗时下大概率使 Codebook 准备和首轮装配体分析失败；
- 陈旧标签页可以把另一会话、另一装配体的“已校验”分类显示在当前页面。

另有 3 项 P2，以及若干 P3 和推测项。R02、R10、R12、R14 应改判为“部分闭环”。

证据类别标记（全文统一）：

- 【实测】本轮在当前环境实际运行并观察到结果；
- 【推断】仅根据代码阅读得出，未运行；
- 【历史】仅来自既有报告/JSON，本轮未复核；
- 【无法验证】当前环境无法验证（Windows、真实 Bosch、真实 PyMuPDF 等）。

---

## 1. 对项目目标与当前状态的理解

### 1.1 用户操作流程

1. 在 Bosch Windows 电脑上从程序目录启动：`python chat_workbench.py [--env-file PATH] [--port N]`。
   启动阶段先检查依赖、配置、状态目录和端口；只监听 127.0.0.1。
2. 浏览器打开本地页面，选择工作区。`/api/setup` 建立 `ACTIVE` 会话：`ProjectState`、`LocalDocumentLibrary`、
   `LLMConnector` 和价格目录。全局设置写入程序目录下的 `AI_Bot_State/`。
3. 准备分类规则：`/api/codebook/prepare` 逐页（PDF）或逐段（DOCX）调用模型转写，再合并为结构化草稿。
   用户可编辑（`/api/codebook/edit`，需确认），然后锁定（`/api/codebook/lock`）。规则档案只有一份，
   全局保存在 `AI_Bot_State/codebook_profile.json`。
4. 选择装配体材料：`/api/target-tree` 只读浏览目录，`/api/target` 在暂存索引副本上解析所选文件。
   全部校验通过后，再一次性提交 `active_source_ids`、`selected_target`、`bg_context`（含锁定规则快照、版本和哈希）
   以及 `source_binding`，同时归档旧对话。
5. 提问：`/api/chat/stream`。首个装配体问题会自动预读：先做逐文件摘要（`prepare_coverage`），
   再生成装配体证据档案（`prepare_bg_dossier`），然后执行主回答，必要时进行一次修复轮和一次补读轮。
   流式预览只显示已解码的 `answer` 文本；最终结果先通过分类与引用校验，才会写入历史和待确认计划。
6. 可选功能：多模型对比（`/api/compare`，只读）、缓存审计与重建、导出、会话管理、三语切换。
7. 写入：模型给出的代码修改只生成 diff 和 `plan_id`。只有 `/api/apply` 携带当前 `plan_id` 并确认，
   且上下文摘要与源文件哈希都一致时，才通过备份、临时文件、原子替换和回滚写入工作区文本文件。
   Excel 修改只在终端工具 `excel_chat_agent.py`/`excel_agent.py` 中进行：用户输入“确认执行”后，
   生成新的 `*_ai_updated_*.xlsx` 副本并逐格校验，源文件不变。

### 1.2 模块职责与数据流

| 模块 | 职责 |
|---|---|
| `workbench_startup.py` | CLI（`--env-file`/`--port`）、依赖/状态/端口检查、`FarmEnvironment`（只追踪 dotenv 引入的变量并可回滚） |
| `chat_workbench.py` | FastAPI 路由、全局 `ACTIVE`/`LOCK`/`MODEL_WORK_IN_PROGRESS`、规则准备与校验、材料提交事务、模型调用编排、分类校验、记账、SSE、计划绑定与写入；内嵌约 630 行单文件 HTML/JS |
| `code_chat_agent.py` | `ProjectState`（会话状态、加载期校验与隔离、转录、记账）、`resolve_relative` 路径边界、提示词与引用清单 |
| `local_document_library.py` | 文件解析/分块/OCR/视觉附件、文档索引（按工作区共享）、检索 |
| `llm_connector_with_prompt_caching.py` | Gemini/Claude（完整响应 HTTP）、OpenAI 兼容（SDK，可流式）三类调用；逐次派发记账；请求控制 |
| `request_runtime.py` | `RequestControl`（取消、整体截止时间、I/O 超时、重试退避、大小上限）、`AnswerPreview` |
| `release_safety.py` | 用量归一化/汇总、错误脱敏、规则档案与持久化上下文 schema 校验 |
| `workbench_i18n.*` | 三语目录与 `UIMessage`（key + 参数） |

模型调用路径：路由函数 → `begin_model_work()`（占用全局模型槽，创建一个 `RequestControl`）→ `call_model`/
`call_comparison`/`prepare_codebook_profile`/`prepare_coverage` → `accounted_model_call()`（派发前检查、
派发后逐次记账）→ `LLMConnector.ask_about_files()` → 对应供应商的 `_http_post`/OpenAI SDK。

状态保存：程序目录 `AI_Bot_State/`，包括 `workbench_settings.json`、`codebook_profile.json`、`material_selections.json`、
`material_cache/`、`bg_dossier_cache/`、`codebook_visual_cache/`，以及 `projects/<工作区哈希>/documents.json`
（同一工作区的所有会话共享），每个会话目录下有 `state.json`、`transcript.jsonl`、`analysis_coverage.json`、
`archives/`、`backups/`、`exports/`、`quarantine/` 和 `visual_cache/`。BG 源目录只读。

写入边界：
- 代码：经 `plan_id` 确认写入工作区内允许后缀的文本文件；
- 规则：只写应用内草稿，不改源 Codebook；
- Excel：只经终端工具写新副本；
- 不写 BG 源目录；
- 密钥只存在于进程环境，正常路径不会写入状态文件（但见 F-01）。

### 1.3 当前状态

- 远端最新 main 即已知最终修复提交 `bf4ce5ac43544ef883aa3ccebb2e4cd8b22fe161`，之后没有新提交。
  本地工作区开始时干净。【实测】
- 第九步证据 JSON 中 34 个被测文件的 SHA-256 与当前 HEAD 逐一相同，即第九步的被测源码就是当前 main。【实测】
- 九步修复已执行；完整静态门禁仍未通过；Windows/Bosch 目标环境与新分发包未验证。这与第九步报告一致。

---

## 2. 审查基线、范围与实际运行的检查

### 2.1 基线与范围

- 审查提交：`bf4ce5ac43544ef883aa3ccebb2e4cd8b22fe161`（浅克隆，`git fetch origin main` 后确认无后续变更）。
- 范围：`local_llm_chat_bot/` 全部 11 个应用模块、内嵌 UI、测试与文档；`tools/release_audit/`；
  打包工作流和 `.gitignore`（只读）。
- 已阅读：README、CODE_CHAT_AGENT_README、I18N_MIGRATION、TESTING、原修复报告、
  `tools/release_audit/README.md`（审查基线与脚本局限）、第六步和第九步报告、第九步证据 JSON；
  其他各步报告按需查阅。

### 2.2 本轮环境（与第九步不同，影响结论边界）

沙箱无法访问 PyPI（代理对 `pypi.org` 返回 403）。因此本轮使用容器中已有的 venv（Python 3.13.17，含系统包），
并从官方 GitHub 发布物补齐了固定版本的静态工具：

| 组件 | 本轮 | 第九步记录【历史】 |
|---|---|---|
| Python | 3.13.17 | 3.12.14 |
| FastAPI / Starlette | 0.115.12 / 0.46.2 | 0.162.0 / 1.10.0 |
| OpenAI SDK / httpx | 1.82.0（源码安装；`jiter` 为调用即抛错的导入桩）/ 0.28.1 | 3.37.0 / 0.28.1 + httpx2 |
| PyMuPDF | **缺失**（PyPI 被阻断） | 1.26.6 |
| Playwright / 浏览器 | 1.63.0 / Chrome for Testing 153.0.8010.12 | 1.51.0 / Chromium 134 |
| Node | 22.23.4 | 24.22.1 |
| Ruff | 0.17.2（官方 GitHub 发布二进制，与固定版本一致） | 0.17.2 |
| mypy | 1.15.0（官方 v1.15.0 源码，以 Python 3.12 运行，目标 3.10） | 1.15.0 |

Python 3.10 不可用：只做了 `ast.parse(feature_version=(3,10))` 语法检查，不能代替 3.10 运行时验证。【无法验证】

### 2.3 实际运行的检查及结果

| 检查 | 结果 | 类别 |
|---|---|---|
| 完整 `unittest discover -s tests -v` | 184 个方法：175 通过、1 跳过（原生 Windows junction）、8 未通过。8 项全部由缺 PyMuPDF 引起：2 项测试内部 `import fitz` 报错；6 项启动/CLI 子进程测试被 `check_dependencies()` 按设计拦截 | 实测 |
| 上述 6 项改用 PyMuPDF **导入桩**（只满足 `find_spec`，调用即抛错）复跑 `test_release_step_eight.py`、`test_release_audit_gaps.py` | 29/29 通过 | 实测（启动路径不使用 PDF 功能） |
| 两项真实 PDF 测试（`test_all_declared_file_formats_and_source_immutability`、`test_real_pdf_rule_pages_use_the_actual_page_inventory`） | 本轮无法运行 | 无法验证；通过结果仅有【历史】记录 |
| 浏览器 `python tests/browser_release.py` | 17/17 通过，退出 0（版本与固定版本不同，见上表） | 实测 |
| 致命 Ruff 子集 `E9,F63,F7,F82` | 通过 | 实测 |
| 完整 Ruff 0.17.2 | 退出 1：257 项（E702=166，E701=84，F401=6，E402=1），与第九步一致 | 实测 |
| mypy 1.15.0（`pyproject.toml` 配置，11 个模块） | 退出 1：45 项。其中 44 项与证据 JSON 的文件/行/代码逐项一致；多出 1 项是 `requests` 缺 stub 的 `import-untyped`（本环境未装 `types-requests`，属环境差异） | 实测 |
| `compileall` / `git diff --check` / 3.10 语法解析 | 通过 | 实测 |
| 证据 JSON 源码摘要比对 | 34/34 一致 | 实测 |
| 新增独立复现 `tools/release_audit/independent_review_2026-10-25.py` | 10 项全部复现问题（断言的是**当前缺陷行为**） | 实测 |
| 浏览器探针：英文界面残留中文扫描、两个标签页上下文串扰 | 均复现（截图在临时目录，不入库） | 实测 |

结论：除需要真实 PyMuPDF 的 2 项外，第九步“183 通过、1 跳过、浏览器 17 通过、Ruff 257、mypy 44”的数字在本环境可复现。
但这些测试没有覆盖下文问题。

---

## 3. 问题清单（按严重程度排序）

P1 = 发布阻断；P2 = 正式交付前应修复；P3 = 应排期修复的缺陷、体验问题或维护问题。复现脚本均使用合成数据和回环 mock。

### F-01 — P1：配置的 env 密钥文件可被模型通过 `read_files` 读取并发送给模型　【实测】

- **位置：**
  - `code_chat_agent.py:353–383` `ProjectState.resolve_relative()`：只拒绝名称以 `.env` 开头的路径组件、`.pem/.key` 后缀、`IGNORED_DIRS` 和应用状态目录；
  - `chat_workbench.py:1693–1700` `call_model()` 按模型要求读取全文；
  - `chat_workbench.py:886–899` `build_diff()` 与 `2861` `apply()` 共用同一判定；
  - 有效配置文件来自 `chat_workbench.py:1942–1949` / `workbench_startup.py:56–67`。
- **触发条件：** 通过 `--env-file` 或 `/api/setup env_file` 指定的配置文件位于所选工作区内，且文件名不以 `.env` 开头。
  README 第 72–74 行的示例正是 `"Farm ü.env"`，也可能是 `farm.env`、`bosch.env` 等。随后模型在 `read_files` 中请求该文件。
  这可能是模型自发行为，也可能来自 BG 文档中的提示注入。
- **实际影响：** Farm 订阅密钥进入第二轮提示，被发送给模型服务。如果模型回答中复述了密钥，会写入 `transcript.jsonl`/
  `state.json`、显示在界面上并可被导出。这违反“密钥不得进入日志、界面、会话文件”。同一路径还能出现在修改计划中，
  但写入仍需确认。
- **证据：** `SecretBoundary.test_configured_env_file_inside_workspace_reaches_model_prompt`：
  `/api/chat` 返回 200，第二次模型 prompt 含合成密钥 `REVIEW_SYNTHETIC_FARM_KEY_6f1e`。
- **根因：** 路径边界按“文件名规则”判断，而不是按“应用实际使用的敏感文件”判断；也没有在出站提示和落盘内容上做纵深脱敏。
- **修复：**
  1. 在 `resolve_relative` 的统一边界中加入受保护绝对路径集合：当前有效 env 文件、`STARTUP_CONFIG.env_file`、程序目录 `.env`，
     比较时用解析后的路径和 `os.path.normcase`；同时拒绝任何 `*.env` 后缀的文件。
     由 `chat_workbench` 在创建/切换 `ProjectState` 时注入，读取、diff、apply、scan 共用这一判定。
  2. 在 `accounted_model_call()` 派发前，对 prompt 中出现的当前密钥做替换或拒绝。在 `add_turn`、导出和 SSE 之前，
     用 `safe_error` 同源逻辑脱敏 answer。
- **验收：**
  - 新增回归覆盖 `farm.env`、`Farm ü.env`、`sub/x.env`、大小写变体：都在第二次模型调用前返回 4xx；
  - mock 收到的所有 prompt、返回体、`state.json`、`transcript.jsonl` 中都不含合成密钥；
  - `build_diff`/`apply` 对这些路径也拒绝；
  - 正常 `.txt/.py` 读取不受影响；`test_release_step_two.py` 继续全部通过。

### F-02 — P1：默认请求时限会让真实耗时的完整响应和多步骤操作失败，并造成重复计费　【实测（缩放复现）＋推断（真实延迟）】

- **位置：**
  - `request_runtime.py:28–36`：默认 `timeout=180`、`read_timeout=20`、`attempts=3`；`:56–59` 一个 `RequestControl` 只有一个截止时间；
  - `chat_workbench.py:454–465`：每个用户操作只创建一个控制对象。下列操作都在同一个 180 秒预算内完成：
    - `/api/codebook/prepare` 的全部页面转写、合并和修复（`2423–2441`，`781–815`）；
    - 首问自动预读的全部逐文件摘要、证据档案、主回答、修复和补读（`1539–1648`）；
    - 对比的全部模型（`2778–2791`）。
  - `llm_connector_with_prompt_caching.py:459–501`：Gemini/Claude 是**完整响应**接口，`requests` 读超时就是等待整段生成的时间上限，
    超时后最多重试 3 次；
  - `:89`：终端工具（`bosch_chat.py`、`excel_chat_agent.py`、`code_chat_agent.py`）在没有传入控制对象时，
    同样使用默认 `RequestControl()`。原报告记录修复前为 `timeout=300`。
- **触发条件：** 任何一次 Gemini/Claude 生成耗时超过 20 秒（大附件、多模态页面、4096 输出 token 或长思考），
  或一个操作的累计耗时超过 180 秒。典型情况包括多页 PDF Codebook，以及包含多份材料的首次装配体分类。
- **实际影响：** 服务正常但响应较慢时，请求被判失败。每次读超时后都会重新派发，供应商可能为 3 次完整生成计费，
  但账本只能记录 3 次未知用量。Codebook 准备超时后，已付费的逐页转写全部丢弃，规则无法准备。
  这类失败对用户表现为偶发失败，难以定位。环境变量最大只能设到 1800/120 秒，而且 README 没有说明这些变量（只有 TESTING.md 提到）。
- **证据：** `RequestBounds` 共 4 项。
  - 默认值确认（含终端连接器）。
  - 读超时缩放到 0.5 秒、服务延迟 1 秒：`/api/chat` 返回 400 `ReadTimeout`；mock 实际收到 3 次生成；
    账本为 3 次请求、`input=None`。把读超时提高到 5 秒后，同一服务成功。
  - 整体时限缩放到 1.5 秒、4 个文件各延迟 0.4 秒：首次分类超时，历史为空；时限设为 60 秒后，分类成功。
  - DOCX Codebook 12 段、每段延迟 0.4 秒、时限 1.2 秒：准备失败且不保存档案；时限设为 60 秒后，准备成功。
  - 真实 Farm 的生成延迟本轮无法测量；“真实环境大概率超时”是根据 20 秒/180 秒默认值，与多模态长输出的常见耗时对比得出的推断。
- **根因：** R12 把“防止任务无限占用槽位”实现为对整个用户操作的单一硬截止时间，并把流式“字节间隔”超时
  原样套用到非流式的完整响应上；读超时又被当作可重试的瞬时错误。
- **修复：**
  1. 区分“单次调用等待完整响应的时限”（例如默认 300 秒，可配置）与“流式字节间隔时限”（可保留 20 秒）。
     Gemini/Claude 的 `_http_post` 使用前者。
  2. 整体截止时间改为按调用计算，或按工作量给出可配置上限，并为 Codebook 准备、预读和对比提供可见的 Stop
     （通用任务注册表，复用 `/api/chat/cancel` 的语义）。
  3. 对非幂等的生成请求，`ReadTimeout` 默认不自动重试（至多 1 次，并且计入账本）。
  4. 在 README 记录全部 `WORKBENCH_*` 变量及默认值，以及如何放在 `.env` 中。
  5. 先在 Bosch 电脑上记录各模型的 Codebook 页转写、预读和主回答的 p50/p95 耗时，再据此确定默认值。
- **验收：**
  - 回环 mock 延迟大于流式字节间隔、但小于完整响应时限时，Gemini/Claude 调用成功，且只派发 1 次；
  - 24 段 DOCX Codebook 在每段延迟 0.4 秒、默认配置下准备成功；
  - 读超时只派发 1 次（或配置的次数），账本与派发次数一致；
  - Codebook 准备、预读和对比可以停止：停止后不提交结果，模型槽在线程退出后才释放；
  - 现有 `test_release_step_six.py` 中的截止、取消、背压用例继续通过（必要时按新语义调整参数，不能删除断言）。

### F-04 — P1：请求不绑定页面所见的会话/上下文，陈旧标签页会得到另一装配体的“已校验”分类　【实测】

- **位置：**
  - `chat_workbench.py:370–373` `ChatRequest` 只有问题与模式；`CompareRequest`（`376–379`）、`/api/coverage`、`/api/target` 等同样不带会话或上下文版本；
  - `454–465` `begin_model_work()` 一律使用全局 `ACTIVE`；
  - `2023–2034`：会话切换只替换 `ACTIVE`；
  - 前端 `chat()`（`chat_workbench.py:3410` 起）只发送 question、request_id 和模式，没有发送 `lastStatusSnapshot.context_revision`/`session_name`。
- **触发条件：** 同一服务开着两个标签页或窗口，或者旧页面没有刷新。标签页 B 新建会话并确认 BG_B，
  然后用户回到仍显示 BG_A 和会话 `default` 的标签页 A 提问。
- **实际影响：** 回环 mock 收到的提示只含 `FIXTURE_BG_B`、不含 `FIXTURE_BG_A`，但标签页 A 显示一张“Classification result (validated)”卡片，
  右侧仍写着 BG_A。问答被写入会话 B 的历史，会话 A 的历史为 0。两个 BG 都有 `facts.txt`，卡片上的引用无法区分来源（见 F-07）。
  这会把错误的装配体结论标成“已校验”，直接违反“基于当前已确认的规则、装配体和材料范围，提供可追溯证据”。
  R04 只对 `/api/apply` 做了 `plan_id` 绑定，问答本身没有对应的绑定。
- **证据：** `tools/release_audit/independent_review_two_tab_probe_2026-10-25.py` 输出：
  `prompt_contains_BG_A_marker=false`、`prompt_contains_BG_B_marker=true`、`tab_a_shows_classification_card=2`、
  `session_b_history=["Classify this Baugruppe", …]`、`session_a_history_len=0`；截图显示 A 页材料仍为 BG_A。
- **根因：** 服务端只有一个可变的全局活动上下文，而客户端请求没有声明“我基于哪个会话、哪个上下文版本”。
- **修复：**
  1. 所有依赖上下文的请求（chat/stream、compare、coverage、cache 重建、target、codebook prepare/edit/lock/clear、
     session 操作、apply）都携带 `session_name` 与 `context_revision`（来自 `/api/status`）。
  2. 服务端在 `begin_model_work()`/`context_mutation` 持锁时比较；不一致时返回 409 和本地化 key（如 `context.stale_page`），
     并且不派发模型请求。
  3. 前端收到该错误后刷新状态、会话列表和历史，并提示用户重新确认。可选：用 `BroadcastChannel` 通知其他标签页。
- **验收：**
  - API 回归：携带旧 revision 或其他会话名的 chat/compare/coverage/target 返回 409，mock 新增调用数为 0，两个会话的 state/transcript 都不变；
  - 浏览器回归：把上述两标签页探针改为断言 A 页得到可见的本地化 409，不出现分类卡片，会话 B 历史不变；
  - 单标签页主流程和第九步全部用例继续通过。

### F-03 — P2：规则档案允许重复的规则 ID，锁定后所有分类必然失败　【实测】

- **位置：**
  - `chat_workbench.py:649–697` `parse_codebook_draft()` 直接采用模型或用户给出的 `id`（`670`、`692`），不检查唯一性；
  - `release_safety.py:87–120` `valid_rule_profile()` 也不检查；
  - `2458–2497` edit/lock 接受这样的档案；
  - 到 `validate_classification()`（`1443–1453`）才报 “ambiguous rule ID”。
- **触发条件：** 合并模型给不同类别生成了同名规则 ID（例如每类都从 `rule-1` 开始），或者用户编辑时复制规则。
- **实际影响：** 规则可以锁定，但之后每次分类都会先完成预读、证据档案、主回答和一次修复（本例共 4 次付费调用），
  最后才失败。错误信息指向模型输出，而不是规则档案，用户难以自行恢复。
- **证据：** `RuleProfileIntegrity.test_duplicate_rule_ids_lock_successfully_then_block_every_classification`：
  lock 返回 locked，随后 `/api/chat` 返回 400 并包含 `ambiguous rule ID`，新增模型调用 4 次。
- **根因：** 唯一性约束只放在使用阶段，没有放在档案的加载和锁定边界。
- **修复：** 在 `parse_codebook_draft` 和 `valid_rule_profile` 中强制全档案范围内规则 ID 非空且唯一。
  `/api/codebook/edit` 和 `/api/codebook/lock` 在冲突时返回 400，并列出重复 ID（三语 key）。
  对模型合并结果，可以做确定性的命名空间化（如 `<class-key>:<id>`）并在规则工作区提示，或者走一次 JSON 修复。
  已锁定的旧档案在加载时如有重复，应把 `context_issue` 标为 `rules_changed`，要求重新编辑。
- **验收：** 重复 ID 的 edit/lock 返回 400，并且不改变已保存的档案；合并结果中的重复 ID 会被提示或修复；
  对重复 ID 的已锁定档案进行分类时返回 409，模型调用数为 0；现有规则相关测试继续通过。

### F-07 — P2：DOCX/TXT/CSV 证据只有文件级标签，不同子目录的同名文件无法区分（R10 部分闭环）　【实测】

- **位置：**
  - `local_document_library.py:130–147` `_chunks()`：同一文件的所有分块共用一个标签；
  - `:863`（TXT/MD）、`:892`（DOCX）、`:933`（CSV）以 `path.name` 作为标签；
  - `code_chat_agent.py:600–618` 清单用 `dict.fromkeys` 去重标签；
  - `chat_workbench.py:1437–1441` 只按标签字符串校验。
- **触发条件：** BG 材料包含长文本或 DOCX（会产生多个分块），或者不同子目录中有同名文件（如各子装配体都有 `Stückliste.xlsx`、`notes.txt`）。
  非分页 Codebook 也一样：本轮浏览器卡片显示的引用是 “Section/chunk references Rules ü.docx”。
- **实际影响：** “已校验”卡片上的 BG 证据和非分页规则引用只能定位到文件名，定位不到段落/节，也定位不到是哪一个同名文件。
  原报告 R10 的要求“DOCX/TXT 无物理页时使用真实 section/chunk 标识”没有达成。
- **证据：** `ReferenceTraceability.test_nonpaged_and_same_named_sources_share_one_file_level_label`：
  两份 `sub1/notes.txt`、`sub2/notes.txt` 产生多个分块，标签集合只有 `{"notes.txt"}`；分类引用为 `["notes.txt"]`，验证通过。
  另外，`tests/test_release_step_four.py:282、357–373` 使用的 `facts.txt block 1`、`rules.docx section 1` 等标签，
  真实解析器并不会生成，测试因此没有覆盖到这个缺口。
- **根因：** 标签格式由解析器决定，而修复只增强了校验器。
- **修复：** 标签改为“BG 相对路径 + 分块/节序号”，例如 `sub1/notes.txt — section 2/5`；DOCX 可按标题或段落范围标注。
  Excel 已有行范围，PDF 已有页码，应补上相对路径。提高索引版本：旧索引在加载时重建标签，或者标记需要重新确认材料。
  清单中保证标签唯一。
- **验收：** 同名文件和多分块文件的标签全局唯一，并能反查到具体文件和分块；用真实解析器产出的标签替换测试中的虚构标签；
  浏览器卡片显示可区分的引用；现有 R10 用例继续通过。

### F-11 — P2：推荐的 git 工作副本中，运行状态和自定义密钥文件不在忽略列表内；打包仍无门禁　【实测＋推断】

- **位置：**
  - 根 `.gitignore` 只忽略 `.env`。`git check-ignore` 对以下路径均返回“未忽略”：
    `local_llm_chat_bot/AI_Bot_State/…`、`.bosch_chat/`、`.excel_chat_agent/` 目录、`Farm ü.env`；
  - `.github/workflows/package_local_llm_chat_bot.yml:21–24`：只排除 `__pycache__`、`tests`、`.env`、`visual_cache`，
    没有测试门禁，也没有包含清单。
- **触发条件：** README 推荐用户在 sparse checkout 的仓库目录里直接运行程序（`README.md:15–50`），状态目录会生成在工作副本内。
  用户或维护者执行一次 `git add -A`、提交并推送（不带 `[skip ci]`），就会把会话、BG 提取文本、模型摘要以及非 `.env`
  命名的密钥文件推到 GitHub，打包工作流还会把它们装进 ZIP。
- **实际影响：** 私有工程资料和密钥可能进入提交与分发包。本轮没有发现已经发生。
- **修复：** 在 `.gitignore` 中加入 `local_llm_chat_bot/AI_Bot_State/`、`.bosch_chat/`、`.excel_chat_agent/`、`*.env`
  （示例文件按需例外）、`*_ai_updated_*.xlsx`。打包改为显式包含清单，并在打包前运行测试。
  修改工作流文件本身就会触发该工作流，提交时必须带 `[skip ci]`，并取得发布授权后再运行。
- **验收：** `git check-ignore` 对上述路径全部命中；用只读脚本列出打包清单（不生成 ZIP），确认不含状态、缓存、测试和任何 `*.env`。

### F-05 — P3：删除规则后，界面提示的重新确认材料路径被 409 “请先锁定规则”拦住　【实测】

- **位置：** `chat_workbench.py:2500–2513` `codebook_clear()` → `rules_changed()`（`2450–2455`）把 `context_issue` 设为
  `rules_changed`；`analyze_target()`（`2304–2312`）在没有锁定档案且 `context_issue == "rules_changed"` 时返回 `error.rules_lock`。
- **触发条件：** 已确认 BG 后删除 Codebook，然后按 `context.reconfirm` 的提示重新确认材料，准备做普通问答。
- **影响：** 用户只能先找到“退出分类模式”（`DELETE /api/bg`），否则一直被要求“准备并锁定规则”，而此时已经没有规则可以锁定。
  证据：`ScopeRecovery.test_clearing_rules_blocks_plain_material_reconfirmation_until_bg_is_cleared`。
- **修复：** 规则被删除时，把 `context_issue` 设为单独的值（如 `rules_removed`）：允许以普通模式重新确认，或在 409 中提供明确的三语操作指引。
- **验收：** 删除规则后可以直接以普通模式确认材料，或得到含“退出分类模式”指引的本地化 409；锁定规则后的分类流程不受影响。

### F-08 — P3：三语切换仍有残留中文（R14 部分闭环）　【实测】

- **位置/证据：** 浏览器探针（英文界面）：
  - 右栏 “Scan status” 卡片初始显示 “首次分类提问会自动读取并理解所选材料；无需预先操作。”
    来源是 `chat_workbench.py:2919` `#coveragestatus` 的静态默认文案，没有绑定到目录 key；
  - 对比面板超过 4 个模型时显示 “最多只能同时对比 4 个模型。”（`3376` `addCompareModel()`）；截图已确认；
  - 可访问性标签 `aria-label` “调整左侧栏宽度”（`2920`）、“上下文详情”（`3112`）、“扫描报告”（`3232`）在三种语言下都是中文；
  - 后端导出（`818–883`）固定为中文，token 未知时输出 `None`；新会话目录名由 `"新聊天_%Y…"`（`2125`）经 `safe_name` 变成 `__YYYYMMDD_HHMMSS`。
- **根因：** 浏览器测试只检查指定的动态消息，没有对整页做残留扫描；若干旧函数和静态 HTML 没有接入目录。
- **修复：** 把上述文案改成 key；导出使用当前语言和目录；会话名使用语言无关前缀（如 `chat_…`），显示标题走 key。
  在浏览器套件中加入英文和德文整页 Han 字符扫描，白名单只放用户数据、路径和语言选项。
- **验收：** EN/DE 在主流程、对比上限、扫描报告、诊断、新会话各步骤中扫描结果为空（白名单除外）；ZH 不变；导出与当前语言一致。

### F-06 — P3：GET 接口接受跨站无 Origin 请求；生产环境也接受 `Host: testserver`　【实测】

- **位置：** `chat_workbench.py:1927–1934`：只有在带 Origin 时才校验同源，主机白名单里包含测试用的 `testserver`；
  `2223–2239`：`GET /api/pick/{kind}` 会弹出本机文件对话框。
- **影响：** 任意网页可以用 `<img src="http://127.0.0.1:8765/api/pick/file">` 反复弹出本机对话框，造成干扰或诱导点击；
  响应内容不可跨源读取，所以不构成数据泄露。`testserver` 白名单在 Windows 内网 LLMNR/NBNS 被投毒时可能被滥用（推断）。
  证据：`LocalOrigin.test_cross_site_get_without_origin_and_testserver_host_are_accepted`。
- **修复：** 对 `Sec-Fetch-Site: cross-site` 的请求一律拒绝；有副作用的 GET（pick、diagnostics）改为 POST 或要求自定义请求头；
  `testserver` 只在测试中通过配置加入。
- **验收：** 带 `Sec-Fetch-Site: cross-site` 的 GET 返回 403；不带 Origin 的同源页面功能不受影响；生产配置下 `Host: testserver` 返回 403。

### F-09 — P3：普通（非 BG）问答中，模型返回 `"classification": {}` 会让整个回答失败　【实测】

- **位置：** `chat_workbench.py:1508–1526` 只要 classification 非 null，就按 BG 规则校验；`1665–1672` 抛出 ClassificationValidationError，没有回退。
- **影响：** 普通文档问答因模型多给了一个空对象而返回 400，不保存历史，错误信息还提到 Codebook。
  证据：`PlainModeRobustness.test_empty_classification_object_fails_plain_document_question`。
- **修复：** 没有 bg_context 时，把空的或非对象的 classification 当作 null 处理并给出提示；非空对象拒绝时给出普通模式专用文案；BG 模式保持严格。
- **验收：** 普通模式下 `{}` 正常回答并带提示；BG 模式的修复和拒绝用例不变。

### F-10 — P3：Excel 对话代理的“计划展示”由模型生成摘要，确认前没有本地确定性的清单　【推断（代码）】

- **位置：** `excel_chat_agent.py:294–314` 只把计划摘要（写入数量等）交给模型，由模型组织回答；
  `473–479` 用户输入“确认执行”后直接应用该计划文件。
- **影响：** 用户确认的是模型对计划的描述，而不是本地打印的“工作表/列/逐格值”清单。实际写入有强约束：只写新副本、
  目标列必须为空、禁止写入公式、源哈希和公式指纹校验、写后逐格校验，所以风险是“生成了不符合预期的新副本”，不会改坏源文件。
  这与需求“明确的计划展示”有差距。
- **修复：** 创建计划后在本地打印确定性摘要（工作表、目标列、表头、前 N 条和总数、计划文件路径与哈希）；
  “确认执行”时核对计划哈希与已展示的一致。
- **验收：** 单元测试捕获 stdout，确认摘要由本地生成，并在模型返回错误摘要时仍然正确；计划文件被篡改后拒绝确认。

### F-12 — P3：文档与代码冲突（以代码为准）　【实测（阅读）】

- `CODE_CHAT_AGENT_README.md:32–37` 说 GUI 左侧可以选择 state directory；代码对 GUI 的 `state_dir` 一律拒绝
  （`chat_workbench.py:1969–1970`），README 第 94–95 行也这样写。
- `CODE_CHAT_AGENT_README.md:90` 说“this version does not run local OCR”；README 第 125–132 行和 `prepare_coverage()`
  会做本地 OCR。
- `I18N_MIGRATION.md:39–46` “Still to be completed” 仍列出服务端进度和错误、面板重绘等，已与第七至九步不符。
  本轮实测仍有残留（F-08），两者都不准确。
- README 没有说明 `WORKBENCH_*` 请求时限变量（只有 TESTING.md 提到），与 F-02 相关。
- TESTING.md 固定 Playwright 1.51.0；本轮用 1.63.0 通过，只能说明兼容，不代表版本固定已经验证。

### F-13 — P3：死代码和被覆盖的旧渲染器增加维护风险　【实测（阅读）】

- `chat_workbench.py:2274–2280`：`activate_bg()` 在 `return` 之后的不可达代码，接口忽略 `codebook` 参数；
  `1277–1281` `needs_bg_preparation()` 已无调用方。
- 旧 JS 函数仍然留在页面中，运行时被重新赋值覆盖：`renderStatus`（`3172`，含未转义的 `s.model` 插值）、
  `renderSessionRows`（`3195`）、`renderCompareSlots`（`3374`），都含中文硬编码。现在没有生效，但以后只要改动初始化顺序，
  就可能重新引入 R03/R14 类问题。Ruff 规则集不检测这些。
- 修复：删除不可达代码和未用函数；去掉被覆盖的旧实现，只保留 `*ForLanguage` 版本。验收：浏览器套件不变通过；在页面源码中检索不到上述中文硬编码。

### 推测项（未复现或只有低概率触发，单独列出）

| 编号 | 位置 | 推测 | 建议验证 |
|---|---|---|---|
| S-1 | `chat_workbench.py:1771–1775` | `call_comparison()` 在没有证据档案时直接使用 `coverage.files`，没有调用 `coverage_matches_current_selection()`。现有 API 路径会在上下文变化时删除 coverage，所以本轮找不到触发路径；属于缺少纵深防御 | 构造 revision 不一致的 coverage 文件，确认对比不会使用它；修复时与对话使用同一判定 |
| S-2 | `chat_workbench.py:1541` 对比 `1722` | 源文件只在请求开始时检查哈希。如果模型调用期间文件被修改，结果仍会以旧内容提交。回答本身与发送的内容一致，但界面显示的“当前材料”已经变了 | 在 `commit_answer` 前再检查一次绑定和哈希；mock 在调用期间修改文件 |
| S-3 | `chat_workbench.py:2720–2729` | 如果 worker 抛出非 `Exception` 的 `BaseException`，`task["error"]` 为 None，reaper 会在 `MODEL_WORK_IN_PROGRESS.clear()` 之前崩溃，导致模型槽永久占用 | 在 reaper 中用 try/finally 保证清理 |
| S-4 | `chat_workbench.py:2464`；前端 `profile_version:lastCodebookWorkspaceProfile?.version` | `profile_version` 缺省时跳过版本检查，API 调用方或未加载档案的页面可能覆盖较新的草稿 | 把 `profile_version` 设为必填 |

---

## 4. 剩余静态诊断的风险分类

### 4.1 Ruff：257 项（全部复核）【实测】

| 类别 | 数量 | 分类 | 说明 |
|---|---|---|---|
| E702 一行多语句（分号） | 166 | 纯格式 | 主要在 `tests/test_release_matrix.py`（50）、`chat_workbench.py`（46）、`bosch_chat.py`（36）、`tests/fixture_support.py`（29） |
| E701 冒号后同行语句 | 84 | 纯格式 | 同上 |
| F401 未使用导入 | 6 | 纯格式/清理 | `bosch_chat.py:12 textwrap`、`code_chat_agent.py:16 sys`、`tests/test_release_matrix.py:8/9/20`、`tests/test_workbench_reliability.py:5`；全部可以安全删除 |
| E402 导入不在顶部 | 1 | 纯格式 | `tests/test_workbench_i18n.py:12`，测试需要先设置路径 |

这些诊断中没有可触发的运行时风险。需要注意的是，Ruff 当前规则集（E4/E7/E9/F）发现不了 F-13 中的不可达代码和被覆盖的 JS。

### 4.2 mypy：44 项（与证据 JSON 一致；另 1 项为本环境缺 `types-requests`）【实测】

| 分组 | 数量 | 分类 | 依据 |
|---|---:|---|---|
| `local_document_library.py` 中 `LocalDocumentLibrary.list` 方法遮蔽了 `list` 类型（valid-type 8 项 + 由此产生的 “not iterable” attr-defined 7 项） | 15 | 类型标注问题 | 模块使用 `from __future__ import annotations`，运行时不会求值。建议把方法改名为 `list_documents()` 并保留兼容别名，一次消除 |
| var-annotated（`local_document_library.py` 7 项，`code_chat_agent.py:152/780` 2 项） | 9 | 类型标注问题 | 空容器缺少注解 |
| `code_chat_agent.py:251、544、562–571`：字典推断为 `dict[str, object]` | 9 | 类型标注问题 | 终端流式状态字典，运行时类型一致；建议改用 TypedDict 或小型 dataclass |
| `chat_workbench.py:672/693/694`：规则字典值类型混合 | 3 | 类型标注问题 | `pages` 为 int 列表，id/text 为 str |
| `chat_workbench.py:1367/1378`：排序元组 int/float | 2 | 类型标注问题 | 排序键混用 int 与 float，比较合法 |
| `excel_agent.py:371` `split_qualified` 返回 list | 1 | 需要进一步验证，低风险 | `rsplit("!",1)` 在已检查含 `!` 后总是 2 个元素，调用方解包安全；建议显式返回 tuple |
| `excel_chat_agent.py:108`（None→str 赋值）、`:515`（`dict.get(None)`） | 2 | 类型标注问题 | 运行时安全 |
| `llm_connector_with_prompt_caching.py:96`（字典分派调用）、`:158`（payload 推断） | 2 | 类型标注问题 | 分派前已排除 openai 分支 |
| `local_document_library.py:707` 局部变量 `key` 先是 str、后被赋为去重元组 | 1 | 类型标注问题 | 两段代码互不依赖；建议改用不同变量名 |

本轮没有发现 mypy 诊断对应的可触发运行时或数据风险。本报告的 P1/P2 问题均不在静态诊断范围内，说明“静态全绿”不能作为发布依据。

---

## 5. R01–R16 复核结论

| 编号 | 结论 | 依据 |
|---|---|---|
| R01 | **已闭环**（测试可运行、失败传播可靠） | 浏览器 17/17 通过【实测】；负对照【历史】。覆盖缺口：无整页残留语言扫描（F-08）、无多标签页（F-04）、无真实延迟（F-02） |
| R02 | **部分闭环** | 符号链接、私有状态、`.env*`、越界路径拒绝均通过【实测】。配置的非 `.env*` 名密钥文件未受保护（F-01）。原生 Windows junction/大小写测试跳过【无法验证】 |
| R03 | **已闭环** | 两项属性注入浏览器用例通过【实测】；当前生效的渲染器都经 `esc`/`escAttr`【实测（阅读）】；残留的被覆盖旧渲染器见 F-13 |
| R04 | **已闭环**（计划写入范围内） | `plan_id`、上下文摘要、源哈希、双页面浏览器用例均通过【实测】。问答本身的上下文绑定是新问题 F-04，不属于 R04 原范围 |
| R05 | **已闭环** | 加载期校验、隔离、保留历史和用量的用例通过【实测】；代码复核加载边界一致【实测（阅读）】 |
| R06 | **已闭环**（单进程） | 暂存后提交、失败恢复用例通过【实测】；多进程或断电原子性不在范围内【无法验证】 |
| R07 | **已闭环** | 改规则或重新锁定后返回 409，重新确认后使用新档案【实测】；删除规则后的恢复路径有体验问题（F-05） |
| R08 | **已闭环** | chat/SSE/compare/coverage/dossier 入口矩阵通过【实测】；对比的 coverage 回退缺纵深防御（S-1，推测） |
| R09 | **已闭环** | 各轮共用校验器，修复预算有界【实测】 |
| R10 | **部分闭环** | 类型、页码和规则 ID 校验通过【实测】。DOCX/TXT/CSV 只有文件级标签，同名文件不可区分（F-07）；单测使用解析器不会产生的标签；锁定时不检查规则 ID 唯一性（F-03）。两项真实 PDF 用例本轮无法运行【无法验证】 |
| R11 | **已闭环**（mock 范围内） | 20 项记账用例和两项审查断言通过【实测】；F-02 复现中失败派发也正确计入未知用量【实测】；真实 Farm usage/cache 字段格式【无法验证】 |
| R12 | **部分闭环** | 预览、停止、断连和槽位释放通过【实测】。默认时限会让真实长操作失败并重复派发（F-02，缩放实测）；Codebook 准备、预读和对比没有停止入口 |
| R13 | **已闭环** | 三项草稿浏览器用例通过【实测】 |
| R14 | **部分闭环** | 目录与动态消息用例、选择器标题用例通过【实测】；英文界面仍有残留（F-08，实测截图）；系统对话框实际呈现【无法验证】 |
| R15 | **已闭环**（Linux Chromium） | 几何和真实点击用例通过【实测】；Windows 字体与缩放【无法验证】 |
| R16 | **已闭环** | 14 项启动用例在 PyMuPDF 导入桩下通过；在缺依赖环境中能按设计报出精确安装命令【实测】；Python 3.10 实机、Windows ACL 与文件锁【无法验证】 |

### 现有测试的有效性问题（避免“错误通过”）

1. 回环 mock 零延迟。`test_release_step_six.py` 只验证“超时后正确停止”，从未验证“慢但健康的响应能成功”，所以 F-02 漏检。
2. R10 单测使用 `facts.txt block 1`、`rules.docx section 1` 等真实解析器不会产生的标签（`tests/test_release_step_four.py:282、357–373`），
   绕开了真实的标签粒度问题（F-07）。
3. mock 模型总是按提示中的清单生成合法分类（`tests/fixture_support.py:46–57`）。成功路径测试在一定程度上是循环论证；
   合法性需要更多“真实模型式”的非理想输出（如跨类规则、重复 ID、同名文件）。
4. 浏览器套件只断言指定的消息，没有做整页残留扫描（F-08）。所有流程都是单标签页，没有覆盖并发会话（F-04）。
5. 两项真实 PDF 用例和启动子进程用例依赖完整依赖集。在缺 PyMuPDF 的环境中它们失败而不是跳过，这是正确行为，
   但说明“全绿”依赖环境，发布验收必须在完整依赖下运行。

---

## 6. 面向下一位实施模型的分步修复计划

通用约束：
- 在 `local_llm_chat_bot/` 下执行；不生成 ZIP，不触发工作流，不调用真实 Endpoint；
- 每步单独提交（只有在用户要求时才提交），提交信息带 `[skip ci]`；
- 本报告的复现脚本断言的是缺陷行为：修复后对应断言应失败，然后改写为 `tests/` 下的正向回归，不要把复现脚本本身留作通过门禁；
- 不删除或弱化现有断言，不添加无依据的 skip 或全局忽略。

| 步骤 | 范围 | 依赖 | 主要修改 | 测试命令 | 通过条件 |
|---|---|---|---|---|---|
| 1 | F-01 密钥边界 | 无 | `code_chat_agent.ProjectState` 增加受保护路径集合与 `*.env` 规则（读取、diff、apply、scan 共用）；`chat_workbench` 在 setup/会话切换时注入有效 env 路径；`accounted_model_call` 派发前和 `add_turn`/导出/SSE 前脱敏当前密钥 | `python -m unittest discover -s tests -p test_release_review_followup.py -v`（新建）；`python -m unittest discover -s tests -p test_release_step_two.py -v` | 新测试覆盖 `farm.env`、`Farm ü.env`、子目录、大小写，均在第二次调用前拒绝；所有 prompt 和落盘文件中都没有合成密钥；step_two 全部通过 |
| 2 | F-04 请求与上下文绑定 | 1 | 上下文相关请求携带 `session_name`+`context_revision`；在 `begin_model_work`/`context_mutation` 中比较并返回 409 `context.stale_page`（三语）；前端发送 `lastStatusSnapshot` 的值，收到 409 后刷新 | 新 API 回归；两标签页探针改写进 `tests/browser_release.py` 的新方法；`python tests/browser_release.py` | 旧 revision 请求返回 409 且 mock 调用数为 0；浏览器两标签页用例中 A 页显示 409、无分类卡、会话 B 历史不变；原 17 个方法通过 |
| 3 | F-02 请求时限与停止 | 无（可与 1/2 并行，但最后与 2 合并验证） | 拆分“完整响应时限”（默认≥300 秒）与“流式字节间隔”（20 秒）；整体截止改为按调用或可配置上限；ReadTimeout 默认不自动重试；Codebook 准备、预读和对比接入通用任务注册与 `/api/…/cancel`；README 记录 `WORKBENCH_*` | `python -m unittest discover -s tests -p test_release_step_six.py -v`；新回归（慢但健康的响应成功且只派发 1 次；24 段 DOCX 在默认配置下准备成功；可停止且不提交） | 新回归全部通过；step_six 原有截止、取消、背压断言保持；账本请求数等于实际派发数 |
| 4 | F-03 规则 ID 唯一 | 无 | `parse_codebook_draft`/`valid_rule_profile` 强制唯一；edit/lock 返回 400 并列出冲突 ID；合并结果命名空间化或修复；加载到重复 ID 的已锁定档案时设 `rules_changed` | 新回归；`python -m unittest discover -s tests -p test_release_step_three.py -v`、`…step_four.py` | 重复 ID 的 edit/lock 返回 400，档案文件不变；已锁定的重复档案在分类前返回 409，调用数为 0 |
| 5 | F-07 引用可追溯 | 4 | 证据标签包含 BG 相对路径和分块/节序号；索引版本提升与迁移；清单标签唯一；用真实解析器标签替换测试中的虚构标签 | `…step_four.py`；新回归（同名文件、多分块 DOCX/TXT）；浏览器卡片断言 | 标签唯一且能反查文件和分块；真实标签用例通过；旧索引被重建或要求重新确认 |
| 6 | F-11 仓库与打包卫生 | 无 | `.gitignore` 补充状态目录、`*.env` 和输出副本；工作流改为测试门禁+包含清单（`[skip ci]` 提交，不运行） | `git check-ignore -v <路径列表>`；只读清单脚本（不生成 ZIP） | 全部路径被忽略；清单不含状态、缓存、测试和任何 env 文件 |
| 7 | P3 合集：F-05、F-06、F-08、F-09、F-13，以及推测项 S-1～S-4 的验证与处理 | 2（F-08 的扫描放进浏览器套件） | 按第 3 节各项的“修复”执行；浏览器套件新增 EN/DE 整页 Han 字符扫描（白名单：用户数据、路径、语言选项） | `python -m unittest discover -s tests -v`；`python tests/browser_release.py` | 第 3 节各项“验收”全部满足；扫描结果为空 |
| 8 | F-12 文档与静态清理 | 1–7 | 更新 CODE_CHAT_AGENT_README、I18N_MIGRATION 和 README（时限变量）；删除 6 个 F401；E701/E702 用纯格式提交单独处理（不混入行为修改）；`LocalDocumentLibrary.list` 改名并保留别名，补注解 | `python -m ruff check .`；`python -m mypy`；全部 unittest 与浏览器测试 | Ruff、mypy 退出 0，或剩余项逐条说明并经用户确认；行为测试全部通过 |
| 9 | 综合验收 | 1–8 | 在完整依赖（含真实 PyMuPDF）、Python 3.10 与 3.12 下运行全部检查；记录证据 JSON（源码摘要、方法结果、版本） | 第九步报告中的 7 条标准命令 | 除原生 Windows 跳过项外全部通过；证据 JSON 摘要与提交一致 |

---

## 7. 是否适合进入下一阶段

**不适合进入打包/发布阶段。** 建议先进入“第二轮修复”阶段，完成上表第 1–6 步。

打包前必须完成：

1. 修复 F-01、F-02、F-04（P1），并有正向回归；修复 F-03、F-07、F-11（P2），或由用户书面接受其风险。
2. 在完整依赖环境（含真实 PyMuPDF）中运行完整 unittest 和浏览器套件；在 Python 3.10 下至少运行一次完整 unittest。
3. 在 Bosch Windows 实机上完成以下检查：
   - 原生 junction/大小写用例（`test_native_windows_case_and_junction`）；
   - 启动参数，以及不同工作目录下包含空格、中文和变音字符的路径；
   - NTFS ACL、文件锁、Excel 文件占用；
   - 系统选择器标题和字体。
4. 用真实 Bosch Endpoint、非敏感小装配体和锁定规则做最小冒烟测试：测量 Codebook 页转写、预读和主回答的实际耗时，
   并据此确认 F-02 的默认值；核对实际返回的模型 ID 和 usage/cache 字段；验证停止和失败后的恢复；只在 Excel 副本上验证写入。
5. 确定打包包含清单和测试门禁（F-11）；之后在获得授权时生成新 ZIP，做解压冷启动验证。仓库中现有的 `local_llm_chat_bot.zip` 不代表当前代码。
6. 对静态门禁做出决定：清零，或逐项接受。

---

## 附录 A：本轮新增文件（未提交）

| 文件 | 用途 |
|---|---|
| `tools/release_audit/independent_review_2026-10-25.py` | 10 项后端复现（F-01、F-02a/b/c 与默认值、F-03、F-05、F-06、F-07、F-09），断言当前缺陷行为 |
| `tools/release_audit/independent_review_browser_probe_2026-10-25.py` | 英文界面整页 Han 字符探针（F-08） |
| `tools/release_audit/independent_review_two_tab_probe_2026-10-25.py` | 两标签页上下文串扰探针（F-04），输出 JSON 证据和截图 |
| 本报告 | — |

运行方式（从 `local_llm_chat_bot/` 运行；需要 requirements-dev 依赖与 Chromium）：

```bash
python ../tools/release_audit/independent_review_2026-10-25.py -v
python ../tools/release_audit/independent_review_browser_probe_2026-10-25.py
python ../tools/release_audit/independent_review_two_tab_probe_2026-10-25.py /path/to/output-dir
```

两个探针脚本有少量 E702 风格写法。它们位于应用 Ruff 配置范围之外，只是诊断工具，不是验收测试。
本轮日志与截图保存在会话临时目录，不随仓库保留。

## 附录 B：未修改项确认

- 没有修改业务代码、现有测试、历史报告、README、工作流或 ZIP。
- 没有生成 ZIP，没有触发打包工作流，没有提交，没有推送。
- 没有访问真实 Bosch Endpoint，没有使用真实密钥、BG、Codebook 或 Excel。所有密钥标记均为合成字符串。
