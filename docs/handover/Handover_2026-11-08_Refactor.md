# 交接文档：Bosch Assembly Assistant 架构审查与重构计划（2026-11-08）

新对话请先完整阅读本文件，再开始工作。全程用中文回复用户。

## 1 一句话现状

程序可用，但最近的 bug 集中出在“调用大模型”这一层（截断、JSON 格式、代理超时）。决定**不从零重写**，而是按方案 C 原地渐进重构，目标结构是方案 B（保留底层、重建上层）。下一步：**第 0 步**。

## 2 仓库与分支状态（截至 2026-11-08 16:00）

- 仓库：`XiaguGHW/RepoMA`，程序目录 `local_llm_chat_bot/`。
- **实际发布、同事在用的版本在 `feat/classify-button` 上**（最新提交 2026-10-30，“Update downloadable Bosch Assembly Assistant package”）。
  - 程序已改名为 **Bosch Assembly Assistant**，打包文件是仓库根目录的 `Bosch_Assembly_Assistant.zip`，启动器是 `Bosch_Assembly_Assistant.bat`。
  - 该分支比两者的合并基点 `753f60c`（2026-10-26）**多 53 个提交，尚未合并到 main**。
- **main**：程序代码自 `753f60c` 起没有改动，之后只有论文相关提交（评估指标、混淆矩阵示意图等）。main 上的 `local_llm_chat_bot.zip` 是 10 月 26 日的旧版。
- 两个分支上的打包工作流 `.github/workflows/package_local_llm_chat_bot.yml` **不一样**：
  - 分支版本打包为 `Bosch_Assembly_Assistant.zip`，并删除 `local_llm_chat_bot.zip`；
  - main 版本打包为 `local_llm_chat_bot.zip`。
  - 两者都只能手动触发（`workflow_dispatch`），打包前只跑后端测试。
- **CI**：没有在 push 或 PR 时自动运行的测试。`feat/classify-button` 上“Temporary CI”被加上又删掉过 8 次。浏览器测试从未在 CI 中运行。

### `feat/classify-button` 上的检查结果（2026-11-08，本地沙盒）

- unittest：运行 333 个，**3 个失败**，1 个跳过。跳过的是只能在原生 Windows 上运行的 `test_native_windows_case_and_junction`。失败的 3 个都在 `tests/test_release_step_five.py` 的 `UsageLedger` 中：
  - `test_failed_codebook_main_and_dossier_do_not_erase_consumed_usage`（location='dossier'，`1 != 2`）
  - `test_missing_then_known_usage_survives_reload_and_export`：期望导出中出现“未知”，实际导出已是德语“Unbekannt”。看起来是程序改了、测试没跟上，需要确认。
  - `test_preread_dossier_main_followup_and_cache_reuse`
- mypy：15 个错误（main 为 10 个）。新增的错误里，`code_chat_agent.py: "type[PricingCatalog]" has no attribute "partial_estimate"` **可能是真 bug**，要优先查。其余分布在 `bosch_chat.py`（9 个）、`chat_workbench.py`（4 个）、`local_document_library.py`（1 个）。
- ruff：1 个问题，`tests/test_token_savings.py:12` 中未使用的导入 `PROMPT_CACHE_BREAK`。
- 浏览器测试：本次没有在该分支上运行。

## 3 用户的约束与工作方式（必须遵守）

1. **全程中文**。
2. 每项改动：独立分支 → 跑完测试 → 开 PR → **等用户明确确认后再合并** → 手动触发打包工作流 → 核对 zip 内容与源码逐个文件一致 → 向用户报告。PR 描述末尾附生成说明；提交信息末尾附 Co-Authored-By。
3. **程序数据保存在程序文件夹本身**（`AI_Bot_State`，不放 AppData），同事也在用。更新方式是把 zip 覆盖解压到原文件夹的上一级目录。
4. **公司数据不能离开公司电脑**，不能上传到对话。需要在公司电脑上运行的脚本，推到 RepoMA 合适的位置，由用户下载后在本地执行。
5. **论文约束**：用户正在写关于基于 LLM 的 Baugruppe 分类的论文，评估是 5 种模型/输入配置 × 每种 10 次运行，主指标是 Allowed-Label-Set Accuracy。**评估数据收齐之前，不改分类逻辑、分类提示词或规则解析提示词**，否则前后结果不可比。动这些之前必须先问用户评估是否已完成。
6. 产品定位：只用于 Baugruppe 分类，不再回答代码问题。聊天默认是解释性追问；按规则分类只能通过输入框旁的“开始分类”按钮触发。
7. 用户在 2026-10-30 提过、尚未完成的 UI 小改动（见用户记忆，做 UI 相关工作时一并处理）：
   - 处理中的提示框改为圆角；
   - 统一回答框的布局；
   - 去掉回答上方的 “Klassifikation” 标签；
   - 把范围标签（如 “Bereich: alle 13 Dateien”）移到 “Klassifikation nach Regeln” 标签旁边。
   这些需要先和用户确认是否已在 `feat/classify-button` 中完成。

## 4 架构审查结论（摘要）

### 4.1 bug 集中的根因：模型调用层

- 有 11 处直接调用模型（`accounted_model_call`），每处自己设置 token 上限、处理截断、解析 JSON、重试和缓存。同一类问题因此修了 4 次。
- 连接器把错误当作字符串返回（`"Error: ..."`），`connector_failure()` / `classify_model_failure()` 靠关键词识别错误类型（如 `"max_tokens"`、`"proxyerror"`、`"connecttimeout"`）。
- 没有使用模型原生的结构化输出（Claude 工具调用、Gemini `responseSchema`），JSON 只靠提示词要求。
- Claude（`:rawPredict`）和 Gemini（`:generateContent`）都不是流式调用，长请求在公司代理处容易超时。
- **结构化输出和流式接口在 Bosch Farm 上是否可用，尚未验证**，需要先给用户一个在公司电脑上运行的小测试脚本。

### 4.2 结构问题

- `chat_workbench.py` 有 5,742 行：47 个 API、206 个函数。另有约 17.7 万字符的 HTML/JS/CSS 写在 Python 字符串 `HTML` 里，包括 255 个 JS 函数、56 处 `innerHTML=`、64 个内联 `onclick`，最长一行 10,766 个字符。
- 全局会话字典 `ACTIVE` 被引用 121 次，约 27 个键，没有类型定义。一把全局锁 `LOCK`（RLock）在整个模型调用期间一直被占用。
- 旧功能仍在：`code_chat_agent.SYSTEM`（约 3,700 字符）里还讲改代码、读文件、记忆操作；仍有 `/api/apply` 接口；`excel_agent.py`、`excel_chat_agent.py`、`bosch_chat.py` 仍打进安装包。
- 重复实现：`write_json_atomically`（`chat_workbench.py`、`code_chat_agent.py` 各一份）、`sha256`、`plan_digest`。
- 超长函数：`call_model`（284 行）、`prepare_coverage`（204 行）、`chat_stream`（125 行）、`prepare_codebook_profile`（121 行）。
- 测试按修复轮次命名（`test_release_step_two` … `step_ten`），不是按功能模块。部分测试在 Python 源码里搜索前端字符串。
- 约 15 种状态 JSON 文件没有格式版本号，也没有迁移机制。

### 4.3 应保留的优点

原子写文件；截断输出一律不保存；取消与超时策略；成本记账；三语文案目录及其测试；密钥边界（`release_safety`）；本地模拟 Bosch Farm 的测试服务（`tests/fixture_support.py`）。

## 5 可复用模块

| 模块 | 处理方式 |
|---|---|
| `local_document_library.py` | 直接复用（只依赖 `release_safety`） |
| `llm_connector_with_prompt_caching.py` | 复用并改造：错误改为异常或明确的结果类型；加流式输出和结构化输出 |
| `request_runtime.py`、`release_safety.py`、`workbench_startup.py`、`price_page.py`、`model_pricing.json` | 直接复用 |
| `workbench_i18n.py` + `workbench_i18n.json` | 直接复用 |
| `tests/fixture_support.py` | 直接复用（可模拟截断、超时、JSON 错误，Claude 格式与 Gemini 格式均支持） |
| `chat_workbench.py` 中的规则准备、规则与分类校验、材料预读、各类提示词 | 逻辑保留，拆分到独立模块 |
| 前端 JS/CSS、API 路由、全局会话状态 | 重组或重写 |

## 6 重构计划（方案 C，每一步单独 PR）

- **第 0 步：稳住流程（下一步要做的）**
  1. 把 `feat/classify-button` 合并到 main。注意两边的打包工作流和 zip 名称不同，应保留分支版本，即 `Bosch_Assembly_Assistant.zip`，并清理 main 上旧的 `local_llm_chat_bot.zip`。合并前先和用户确认。
  2. 修好上述 3 个失败测试：判断是测试过时还是程序回归。
  3. 处理 mypy 新增的错误，重点是 `partial_estimate`；修掉 ruff 问题。
  4. 新增 CI 工作流：push 和 PR 时自动跑 unittest、浏览器测试、ruff、mypy（mypy 以当前基线为准，不允许增加）。
- **第 1 步：统一模型调用层**
  - 一个统一入口（例如 `structured_call(task, schema, budget, retry_policy, cache_key)`），返回明确类型的结果或错误。
  - 统一处理截断时的拆分或重试、JSON 校验、调用次数上限、缓存。
  - 在 Bosch Farm 上验证通过后，再接入结构化输出和流式接口。
  - **会改变分类行为，需等论文评估完成。**
- **第 2 步：清理旧功能**
  - 删除改代码、`/api/apply`、Excel 和 `bosch_chat` 相关部分。
  - 给分类单独写一份更短的系统提示（会改变提示词，同样受论文约束）。
- **第 3 步：拆分文件**
  - 前端移到独立的 `static/` 文件（HTML/JS/CSS）。
  - `chat_workbench.py` 按“API 路由 / 规则准备 / 材料预读 / 分类”拆成多个模块。
  - 测试改为按功能模块组织。
- **第 4 步：状态管理**
  - 用有类型定义的会话对象替换 `ACTIVE`。
  - 后台任务交给专门的任务管理组件，模型调用期间不再占用全局锁。
  - 状态文件加上格式版本号和迁移。

不受论文约束、可以先做的：第 0 步、第 3 步（纯结构拆分，行为不变）、第 4 步，以及第 2 步中只删除旧功能、不改提示词的部分。

## 7 测试环境（沙盒）搭建说明

沙盒**无法访问 PyPI 和 crates.io**，但能访问 GitHub（git clone、gh）。本机有 `/root/.cache/uv/archive-v0` 缓存（含 httpx、httpcore、ruff 0.16.9、mypy 2.3.1 等），系统 Python 3.13 自带部分包。上一个对话的搭法如下（新会话的沙盒可能已重置，需要重做）：

1. `python3 -m venv --system-site-packages /home/claude/venv`
2. 从 GitHub 获取源码，并用 `.pth` 文件加入 venv 的 site-packages：
   - `fastapi/fastapi`（仓库根目录）
   - `fastapi/annotated-doc`（路径加 `src`）
   - `openai/openai-python`，tag `v1.82.0`（路径加 `src`）
3. 从 uv 缓存把 httpx、httpcore 复制进 site-packages。ruff 可执行文件放到 `venv/bin/ruff`；mypy 及其依赖（`mypy_extensions` 等）复制进 site-packages。
4. **jiter 替身（只供测试）**：OpenAI SDK 依赖的 Rust 扩展无法编译。在 site-packages 下建 `jiter/__init__.py`，用标准库 `json` 实现 `from_json(data, **kwargs)`，只支持完整 JSON。
5. **PyMuPDF 从源码编译**：
   - PyMuPDF tag `1.26.5`，MuPDF tag `1.26.10`；子模块逐个 `git submodule update --init --depth 1`，跳过 curl 和 freeglut。
   - SWIG 4.3.1 从源码编译到 `/home/claude/swiginst`。
   - libclang Python 绑定：`llvm-project` tag `llvmorg-18.1.3` 的 sparse checkout，只取 `clang/bindings/python`。
   - 把 `/usr/lib/llvm-18/lib/libclang-18.so.1` 软链接为 `libclang.so`，并加入 `LD_LIBRARY_PATH`。
   - 编译命令所需环境变量：`PYMUPDF_SETUP_SWIG=…/swig`、`PYMUPDF_SETUP_MUPDF_BUILD=…/mupdf`、`PYMUPDF_SETUP_MUPDF_TESSERACT=0`、`PYMUPDF_SETUP_PY_LIMITED_API=0`；然后执行 `pip install --no-build-isolation --no-deps .`（约 20–40 分钟，建议后台运行）。
6. Playwright 浏览器：设置 `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers`。
7. 运行命令（在 `local_llm_chat_bot/` 下）：
   - `python -m unittest discover -s tests`
   - `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python tests/browser_release.py`
   - `ruff check .`
   - `python -m mypy`

说明：GitHub Actions 中使用正式依赖和 Python 3.12，可作为沙盒结果的对照。沙盒里的 ruff/mypy 版本与 `requirements-dev.txt` 中固定的版本不同，比较时应以同一版本下的基线为准。

## 8 常用操作

- 合并 PR：`gh api -X PUT repos/XiaguGHW/RepoMA/pulls/<N>/merge -f merge_method=merge`
- 触发打包：`gh api -X POST repos/XiaguGHW/RepoMA/actions/workflows/package_local_llm_chat_bot.yml/dispatches -f ref=main`，然后轮询 `actions/workflows/.../runs`，直到运行完成。
- 打包后核对：取出 zip，按 `PACKAGE_MANIFEST.txt` 把每个文件与 `git show origin/main:<路径>` 逐字节比较，同时确认没有多余文件。
- `gh pr create` 在本环境中不可用，开 PR 请改用 `gh api repos/XiaguGHW/RepoMA/pulls -X POST`。
- 推送后本地跟踪分支可能不会更新，需要执行 `git fetch origin +refs/heads/<分支>:refs/remotes/origin/<分支>` 并设置 upstream，否则检查脚本会误报“未推送”。

## 9 历史参考

- 10 月 25–26 日的修复记录：`docs/release-reports/Workbench_Codebook_Prepare_Fix_2026-10-25.md`（第 1–12 节，对应 PR #7–#12）。
- 更早的修复报告：`docs/release-reports/Workbench_Repair_Step_02` … `Step_09`。
