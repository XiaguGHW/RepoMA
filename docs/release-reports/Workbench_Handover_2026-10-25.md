# Workbench 修复交接说明（2026-10-25）

本文件供下一位接手 `XiaguGHW/RepoMA` 中 `local_llm_chat_bot/` 后续修复的代码专家使用。
它取代此前口头/附件形式的交接说明。若与旧说明冲突，以本文件和当前 `main` 的代码为准。

## 1. 当前基线

- **唯一基线：** `main` = `3db6e7f`
  `refactor(workbench): remove dead code and runtime-overridden UI functions [skip ci]`
- **工作区状态：** 干净；所有修复都已合并进 `main`。
- **ZIP 状态：** 仓库里的 `local_llm_chat_bot.zip` 是在 `76c6618` 从 `96ac952` 打的包，**已落后于当前 `main`**。其后的 `dbf90b8`、`de7fabc`、`bfb1433`、`3a599ec`、`3db6e7f` 都改了程序代码。
  用户的决定是：**全部任务做完后最后再打包，现在不打包。**
- **打包工作流：** `.github/workflows/package_local_llm_chat_bot.yml` 仍会在推送改动 `local_llm_chat_bot/**` 时自动重建 ZIP（除非提交信息含 `[skip ci]`），且没有测试门禁。第 8 步处理。

## 2. 必读材料（路径已核对）

| 文件 | 内容 |
|---|---|
| `docs/release-reports/Baugruppe_Classification_Workbench_PreRelease_Repair_Report_2026-10-24.md` | 原始缺陷 R01–R16 与修复要求 |
| `docs/release-reports/Workbench_Repair_Step_01…09_*.md` 与 `Workbench_Repair_Step_09_Evidence_2026-10-25.json` | 第一轮九步修复的历史记录 |
| `docs/release-reports/Workbench_Independent_Review_2026-10-25.md` | 独立复审报告（问题编号 F-01～F-13、S-1～S-4 的来源） |
| `tools/release_audit/README.md` | 审查基线与诊断脚本的局限 |
| `tools/release_audit/independent_review_*.py` | 复审时的复现脚本与浏览器探针。它们断言的是**修复前**的缺陷行为，修复后大部分会按预期失败；只作诊断参考，不是验收门禁 |
| `local_llm_chat_bot/TESTING.md` | 测试命令与每步修复的测试入口 |
| `local_llm_chat_bot/README.md`、`CODE_CHAT_AGENT_README.md`、`I18N_MIGRATION.md` | 用户文档（第 6 步要修正其中的冲突） |

旧交接说明中提到的 `Workbench_Release_Repair_Report.md` **在仓库中不存在**，请改读上表第一行。

## 3. 已完成的工作

### 3.1 复审后第一批修复（影响基本使用的问题，均已合并）

| 提交 | 问题 | 内容 | 测试入口 |
|---|---|---|---|
| `4374f02` | F-02 请求时限 | 完整响应等待默认 300 秒（`WORKBENCH_RESPONSE_TIMEOUT_SECONDS`），流式间隔 60 秒，整个操作 3600 秒；读超时不再自动重发；Codebook 准备、预读、对比、档案重建可停止（`POST /api/operation/cancel`） | `tests/test_release_request_bounds.py` |
| `7840154` | F-04 多标签页串上下文 | 页面发送 `X-Workbench-Context`（会话目录 + 上下文版本）；旧页面的模型操作和上下文修改返回 409 `context.stale_page`，且不调用模型；规则编辑沿用 `profile_version` 检查 | `tests/test_release_page_context.py`，浏览器方法 `test_stale_tab_cannot_classify_another_tabs_session_or_bg` |
| `d47c547` | F-03 重复规则 ID | 自动编号不冲突；编辑/锁定时拒绝重复（400 `rules.duplicate_ids`）；模型合并结果中的重复自动改名为 `<类别>:<id>`；旧的重复档案在调用模型前返回 409 | `tests/test_release_rule_ids.py` |
| `2c593fe` | F-01 密钥文件 | 实际使用的 env 文件和所有 `*.env`、`.env*` 文件不在模型可读写范围内；当前密钥在提示、预览、回答、计划、证据和历史中替换为 `[redacted]` | `tests/test_release_secret_boundary.py` |
| `20742ab` | F-09 / F-05 | 普通模式下空的 `classification` 字段被忽略并提示（真正的分类对象仍被拒绝）；删除规则后可直接以普通模式重新确认材料 | `tests/test_release_plain_mode_recovery.py` |
| `96ac952` | F-07 / F-11（部分） | 非分页文本标为 `section i/n`，CSV 标出行范围，子目录文件带相对路径；`.gitignore` 增加状态目录、`*.env`、`*_ai_updated*` 等 | `tests/test_release_traceable_labels.py` |
| `76c6618` | 分发 | 从 `96ac952` 重建 ZIP（只取已提交文件），解压冷启动验证通过 | — |
| `d7c509f` | 文档 | 独立复审报告和复现脚本合并进 `main` | — |

### 3.2 剩余任务计划的第 1～5 步（均已合并）

| 步骤 | 提交 | 内容 | 测试入口 |
|---|---|---|---|
| 1 健壮性（S-1～S-4） | `dbf90b8` | 对比和问答不再使用过期预读摘要；模型生成期间源文件变化时，提交前返回 409；worker 抛出任何异常都会释放模型槽；规则编辑的 `profile_version` 改为必填 | `tests/test_release_step_ten.py` |
| 2 本地访问（F-06） | `de7fabc` | `Sec-Fetch-Site: cross-site` 的请求一律返回 403；`testserver` 主机只在 `WORKBENCH_ALLOW_TEST_HOST=1` 时允许（测试夹具已设置） | `tests/test_release_local_access.py` |
| 3 三语残留（F-08） | `bfb1433` | 扫描状态、对比上限、aria-label、导出文件、新会话命名（`chat_YYYYMMDD_HHMMSS`） | `tests/test_release_i18n_residual.py`，浏览器方法 `test_english_and_german_page_scan_has_no_chinese_ui_residue` |
| 4 Excel 计划（F-10） | `3a599ec` | `excel_chat_agent.py` 在模型回复之后打印本地确定性计划摘要（含 SHA-256）；确认时核对哈希，按核对过的内容写入；`excel_agent.die()` 的拒绝不再让对话程序退出 | `tests/test_release_excel_plan.py` |
| 5 死代码（F-13） | `3db6e7f` | 删除 `activate_bg()` 中执行不到的代码和无调用方的 `needs_bg_preparation()`；16 个运行时被覆盖的前端函数改为只声明一次并调用 `*ForLanguage` 版本；14 处一次性 `innerHTML+t()` 状态提示改为按 key 显示（例如切换模型后的确认提示，原来切换语言后仍是中文）；新增英文/德文全流程浏览器扫描 | `tests/test_release_frontend_cleanup.py`，浏览器方法 `test_full_workflow_and_diagnostics_have_no_chinese_ui_in_english_or_german` |

每一步的新测试都已确认：改动前的代码上失败、改动后通过。少数测试用来确认原有正常行为没有被破坏，这类测试在新旧代码上都通过，各步提交说明里有注明。

### 3.3 复审问题状态总览

| 编号 | 状态 |
|---|---|
| F-01、F-02、F-03、F-04、F-05、F-06、F-07、F-09、F-10、F-13 | 已修复 |
| F-08 | 已修复（英文/德文全流程扫描通过） |
| F-11 | 部分完成：忽略规则已加；**打包门禁和包含清单未做 → 第 8 步** |
| F-12 | 未做 → **第 6 步** |
| S-1～S-4 | 已修复 |
| 静态检查存量 | 未做 → **第 7 步** |
| 真实环境验证 | 未做 → **第 9 步（由用户执行）** |

## 4. 当前测试与静态基线（`3db6e7f`，在本环境实测）

| 检查 | 结果 |
|---|---|
| 后端 `python -m unittest discover -s tests -p 'test_*.py' -v` | 242 项。本环境缺真实 PyMuPDF（PyPI 被阻断），因此 8 项无法通过：2 项测试内部直接 `import fitz`；6 项启动子进程测试被依赖检查按设计拦截。这 6 项用只满足导入检查的替代模块复跑全部通过。其余全部通过，1 项原生 Windows 测试跳过 |
| 浏览器 `python tests/browser_release.py` | 20 项全部通过 |
| 致命 Ruff `--select E9,F63,F7,F82`、`compileall`、`git diff --check` | 通过 |
| 完整 Ruff（0.17.2） | **256 项**：E702 165、E701 84、F401 6、E402 1 |
| mypy（1.15.0，目标 3.10） | **44 项**，分布在 6 个文件（local_document_library 23、code_chat_agent 11、chat_workbench 5、llm_connector 2、excel_chat_agent 2、excel_agent 1）。如果环境没有安装 `types-requests`，会额外出现 1 项 `import-untyped`，属环境差异，不计入 44 |

本环境的版本与 `requirements-dev.txt` 的固定版本不同：Python 3.13、Playwright 1.63、FastAPI 0.115。在完整依赖环境中复跑时，以退出码和断言为准。测试日志里出现的 HTTP 400/401/429/5xx、连接错误等，多数是传输异常矩阵的预期模拟分支。

## 5. 必须遵守的执行规则（用户已确认）

1. 每一步从当前 `main` 新建独立分支。
2. 先写或调整测试，并在改动前的代码上确认会失败；再做最小范围的修复。
3. 运行针对性测试，以及完整后端、浏览器和静态检查。用户已授权后续步骤运行浏览器测试。
4. 提交信息必须含 `[skip ci]`。
5. 只推送审查分支，**不要自行合并 `main`**，等用户明确回复“合并第 N 步”后再合并（快进合并，不产生额外合并提交）。
6. 不提交 `.venv`、状态目录、缓存、真实 `.env`、密钥或用户材料。
7. **不要生成 ZIP**，除非用户明确授权真实打包。用户已决定全部做完后最后再打包。
8. 不得通过删除断言、增加无依据的 skip、缩小检查范围或添加全局忽略来让检查变绿。改动原有断言时，必须在提交说明里写明原因。
9. 不修改原始历史报告；需要更正历史结论时，写进新报告。注意：`e73c346` 改写过 `Workbench_Repair_Step_09_2026-10-25.md`，内容准确，但违反了这条规则，以后不要再这样做。
10. 第 7 步用户已选**方案 B**：彻底清理 E701/E702。

## 6. 剩余任务

### 第 6 步：文档与代码冲突（F-12）

只改文档，但仍要跑一次完整后端和浏览器测试。

1. **`local_llm_chat_bot/CODE_CHAT_AGENT_README.md`**
   - 第 33–34 行：“Select the code workspace and state directory from the left panel”与代码冲突。GUI 对 `state_dir` 一律拒绝（`chat_workbench.py` 中的 `setup()` 抛出 `startup.state_fixed`），README 第 94–95 行也这样写。改为：工作区在界面中选择，状态固定保存在程序目录的 `AI_Bot_State/`。
   - 第 90 行“this version does not run local OCR”：**对终端版 `code_chat_agent.py` 是准确的**（它不调用 OCR），但这一节容易被理解为整个工具都不做 OCR。不要简单删除，应写明范围：终端 `code_chat_agent.py` 的 `/file` 不做本地 OCR；图形界面 Workbench 在找到 Tesseract 时会对扫描页做本地 OCR（见 README 的 “Codebook OCR” 一节）。
2. **`local_llm_chat_bot/I18N_MIGRATION.md`**
   - 第 39–46 行“Still to be completed”已过时。改为说明已完成的部分：服务端进度和错误使用 key + 参数；动态面板按数据重绘；状态提示使用 `setUIMessage`；有英文/德文全流程扫描测试。
   - 只保留仍需人工检查的项目：Windows 自带字体、系统文件选择框的实际显示、浏览器缩放。
   - 规则补充一条：新的状态提示必须用 `setUIMessage` 或 `uiMessageNode`，不要用 `innerHTML` 拼接 `t()`（`tests/test_release_frontend_cleanup.py` 有对应检查）。
3. **`local_llm_chat_bot/TESTING.md`**（目前 306 行）
   - 把 “Current gates” 一节更新为第 4 节的实际基线，并汇总各步修复的测试入口（见第 3 节两张表）。
   - 写明测试环境：PyMuPDF、Chromium/Playwright 版本，以及 `WORKBENCH_ALLOW_TEST_HOST`。
   - 写明 ZIP 状态：落后于 `main`，最后统一打包。
   - 第 7 步完成之前，不得写成 Ruff/mypy 全绿。
   - 历史快照保留，可以移到文末。
- **通过条件：** 文档中没有与代码矛盾的说法；完整后端和浏览器测试通过。

### 第 7 步：静态检查清理（方案 B，分两个提交）

**提交 A：F401、E402、mypy（不改变行为）**
- F401：删除 6 个未使用的导入：`bosch_chat.py:12 textwrap`、`code_chat_agent.py:16 sys`、`tests/test_release_matrix.py:8 tempfile`、`:9 threading`、`:20 PricingCatalog`、`tests/test_workbench_reliability.py:5 os`。
- E402：`tests/test_workbench_i18n.py:12`。导入之前需要先设置 `sys.path`，可以改为在文件顶部完成路径设置后再统一导入，或用 `importlib`。不能改变导入语义，不加全局忽略。
- mypy（目标：`python -m mypy` 退出 0）：
  - `local_document_library.py`：23 项中有 15 项是方法名 `list` 遮蔽了内置类型。在类型标注中改写为 `builtins.list[...]`（需要 `import builtins`），**不改方法名、不改调用方**。其余是空容器缺注解（`var-annotated`），以及第 707 行附近复用的变量 `key`，改为新的变量名。
  - `code_chat_agent.py` 11 项：终端流式状态字典（`streamed_answer_handler`，约第 554–586 行）改用 `TypedDict`；第 152、796 行补注解。
  - `excel_agent.py:371`：`split_qualified` 显式返回 `tuple`，例如 `sheet, cell = address.rsplit("!", 1); return sheet, cell`。
  - `excel_chat_agent.py:156`、`:585`；`chat_workbench.py:768/789/790`（规则字典的值类型）、`:1572/1583`（排序元组中 int 与 float 混用）；`llm_connector_with_prompt_caching.py:96/158`：补注解或显式类型。
- 通过条件：mypy 退出 0；完整后端和浏览器测试通过，行为不变。

**提交 B：E701/E702（纯格式）**
- 共 249 项（E702 165、E701 84），分布：`tests/test_release_matrix.py` 50、`chat_workbench.py` 45、`bosch_chat.py` 36、`tests/fixture_support.py` 29、`tests/test_release_regressions.py` 21、`llm_connector_with_prompt_caching.py` 18、`excel_agent.py` 14、`excel_chat_agent.py` 14、`local_document_library.py` 9、`code_chat_agent.py` 7、`tests/test_release_e2e.py` 7、`release_safety.py` 4。
- 只把一行多条语句拆成多行，**不得混入任何行为修改**。不要用 `ruff format` 重排整个文件，`chat_workbench.py` 内嵌的 HTML/JS 原样不动。
- 通过条件：完整 Ruff 退出 0；完整后端和浏览器测试通过。

### 第 8 步：打包门禁和包含清单（F-11 剩余部分）

- 文件：`.github/workflows/package_local_llm_chat_bot.yml`。
1. 只允许 `workflow_dispatch` 手动触发，删除 `push` 触发。
2. 打包前先安装 `requirements-dev.txt`，再运行后端测试；失败就不打包。
3. 改用显式包含清单，只包含：应用 `.py`、必需的 `.json`（`model_pricing.json`、`workbench_i18n.json`、`ui_copy_inventory.json`、`ui_terminology.json`）、`requirements.txt`、README 和必要文档。
4. 清单外的文件一律不打包：测试、缓存、状态、`*.env`、虚拟环境、ZIP 产物本身。
5. 新增一个只读检查（单元测试或脚本），按清单列出将被打包的文件并断言没有违规项。这个检查**不生成 ZIP**。
6. 提交必须带 `[skip ci]`，因为修改工作流文件本身会触发它。
7. 可选：把 `local_origin_only()` 收紧为只接受 `Sec-Fetch-Site` 为 `same-origin` 或 `none`。目前同一台电脑上其他端口的本地网页（`same-site`）仍可访问。需要配套测试。
- 真实生成 ZIP 必须等用户明确授权。

### 最后：打包（用户决定在全部步骤完成后进行）

- 获得授权后，从当时的 `main` 打包：只取已提交的文件（`git show HEAD:<文件>`），按第 8 步的包含清单。
- 解压到路径含空格、中文和变音字符的新文件夹，配一份合成 `.env`，从另一个工作目录启动，验证：
  - `--help` 正常；
  - 页面加载正常（200）；
  - `/api/setup` 成功；
  - 本地自检显示就绪；
  - 状态目录生成在程序旁；
  - 日志和状态文件中都没有密钥。
- ZIP 用 `[skip ci]` 提交。

### 第 9 步：真实 Bosch / Windows 验证（只能由用户执行）

不要假装已经执行。前面各步完成后，向用户提供以下逐项清单：

1. 在装有真实 PyMuPDF 的环境和 Python 3.10 下，各跑一次完整测试。
2. Windows 本机：
   - `test_native_windows_case_and_junction`；
   - 从不同工作目录启动；
   - 路径含空格、中文、变音字符；
   - 文件权限与文件锁；
   - Excel 正打开时的处理；
   - 系统文件选择框的标题和中文字体；
   - Tesseract 自动查找：在自检中看 “OCR (Tesseract)” 一行。
3. 真实 Bosch 服务冒烟测试：
   - 用不敏感的小装配体和锁定的规则，完成一次分类和一次追问；
   - 记录 Codebook 每页转写、预读、主回答的耗时，确认默认 300 秒是否够用；
   - 核对返回的模型 ID、token 用量和缓存字段；
   - 验证停止功能和失败后重试；
   - Excel 只在副本上验证写入。

## 7. 其他待用户决定的事项

- **Tesseract 查找增强（可选，用户尚未决定）：** 目前在 `PATH`、`%LOCALAPPDATA%\Programs\Tesseract-OCR`、`%LOCALAPPDATA%\Tesseract-OCR`、`%ProgramFiles%\Tesseract-OCR`、`%ProgramFiles(x86)%\Tesseract-OCR` 中查找（`local_document_library.py` 的 `ocr_runtime_status()`）。可选的增强：
  - 支持在 `.env` 里用 `TESSERACT_CMD` 指定路径；
  - 读取官方安装程序写入注册表的安装位置；
  - 增加 Scoop、Conda 等常见位置；
  - 在自检中显示找到的完整路径；
  - 查找失败的结果不再缓存。
- **远端旧分支：** `review/independent-review-2026-10-25` 以及已合并的 `fix/*` 分支可以删除，需用户同意。
