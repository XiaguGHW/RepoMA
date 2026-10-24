# Baugruppe Classification Workbench 发布前修复交接报告

审查日期：2026-10-24。结论：**暂不具备发布条件**。现有 67 项自动化测试通过，但本次补充诊断复现了路径隔离、写入确认、固定规则校验、状态一致性、成本统计及界面问题。未发现已发生的真实数据损坏，也未发现已发生的真实凭据泄露；下列复现全部使用可删除的合成数据。

本报告供 6.1 Sol/Terra 或其他开发模型直接实施。审查阶段没有修改业务代码、仓库测试文件、README 或发布配置，没有重构、提交、推送或生成 ZIP。诊断脚本位于仓库外 `audit/`，复用现有 `tests/fixture_support.py`。实施模型应先保留当前未提交修改，再逐条修复；不要退回远端旧版本、删除已有修复或扩大为全仓库重构。

## 1. 实际审查基线与当前完成情况

- 仓库：`RepoMA`；应用目录：`local_llm_chat_bot/`。下文文件路径均相对此应用目录，另行注明的工作流除外。
- 本地 HEAD：`d89b19b`，快照说明对应远端基线 `c98901e4c5b6208bae4652d9f75130be82ab9ad4`。**本报告针对该 HEAD 加当前全部工作区改动，不是只审查 HEAD。** 本次未重新拉取远端。
- 已有 tracked diff：7 个文件，449 行新增、158 行删除。另有未跟踪的 `release_safety.py`、`tests/fixture_support.py`、`tests/browser_release.py` 及 3 个 release 测试文件。将来交付时必须包含它们，尤其不能漏掉已被业务模块导入的 `release_safety.py`。
- 审查前后文件哈希比较：仓库业务代码、测试及文档未改变；只有测试工具缓存变化。`git diff --check` 通过。
- 当前架构：FastAPI + 内嵌 HTML/JavaScript；`chat_workbench.py` 管理 API、全局活动会话、材料范围、规则与 UI；`code_chat_agent.py` 管理会话、提示与价格；`local_document_library.py` 解析文件；`llm_connector_with_prompt_caching.py` 封装三个供应商接口；`excel_agent.py` 负责受控 Excel 副本写入。无独立前端构建项目。
- 状态默认保存在**应用目录** `AI_Bot_State/`，包括全局设置、Codebook profile、材料选择，以及 `projects/<workspace hash>/<session>/` 的会话、历史、备份和导出。它不是 BG 源目录。测试通过替换 `app_state_home()` 将全部状态隔离到临时目录。
- 此前已有修复保留：同路径确认材料不再清空勾选；主分类要求精确类别；切换材料/模型清理历史；主聊天检查源文件哈希；单任务互斥；坏状态的部分降级；供应商空响应/截断处理；Token 缺失归一化；代码写入备份与回滚；Excel 临时保存和验证后发布；规则编辑确认；部分动态翻译及路径过滤。

### 本次检查结果

| 检查 | 命令/范围 | 实际结果 |
|---|---|---|
| 全部现有 unittest | 应用目录运行 `python -m unittest discover -s tests -v` | **67/67 通过**，无跳过；日志中 HTTP/网络 ERROR 是故障 mock 的预期输出 |
| JavaScript 语法/翻译/材料确认 | 包含于 `test_workbench_i18n.py`，Node 运行实际提取的 JS | 通过；不是完整界面覆盖 |
| 致命错误 lint | `python -m ruff check --select E9,F63,F7,F82 .` | 通过 |
| 完整 lint | `python -m ruff check . --output-format concise` | **105 项报错**；包括未使用导入、类型/风格规则、宽泛异常等；没有执行 `--fix` |
| 探索性类型检查 | `python -m mypy --ignore-missing-imports --follow-imports=skip`，后接全部 9 个应用 `.py` 文件 | **38 项错误，涉及 6 个文件**；仓库没有既定 mypy 配置，不能把它称为原有 CI 门禁失败 |
| Python 编译 | `python -m compileall -q .` | 通过；不等于运行正确 |
| 原浏览器测试 | 保持原测试逻辑，只指定本机 Chromium 可执行文件 | **失败**：`#contextworkspace` 不存在，30 秒超时 |
| 浏览器测试副本 | 仅纠正测试选择器、等待条件、重复卡片定位；业务代码不变 | 6 个阶段检查通过，pageerror/翻译 key 警告均为 0；使用 Chromium 133 + Playwright 1.51 |
| 新增后端诊断 | `audit/test_audit_gaps.py`，10 项 + 后加的 1 项单独运行 | **11 项安全/正确性断言均失败**，分别支撑下文问题；并非把失败伪装成通过 |
| 浏览器边界诊断 | `audit/browser_gaps.py` | 实测草稿丢失、旧语言卡片、属性注入、390px 抽屉越界 |
| 启动/状态定点探针 | mock 启动器、真实 TestClient、临时坏状态 | 复现自定义 env 路径被忽略、坏嵌套状态进入运行期错误 |
| 独立构建/打包 | 无前端编译配置；现有工作流仅调用 ZIP | 本轮依用户要求**不运行打包，不生成 ZIP** |

测试依赖装入仓库外目录。真实 Python 库执行文件解析、持久化、API、浏览器与 Excel 操作；模型服务使用回环 HTTP mock 或现有 SDK mock。**所有 Bosch 模型相关结论均为“未在真实 Endpoint 验证”。**

## 2. 实施约束及统一复现准备

排序依据：先让测试能可靠复现，再修复输入和写入边界、状态绑定、分类与账务，最后处理展示和启动。P1 为发布阻断项；P2 为应在正式交付前修复的重要可靠性问题。本次没有证据足以标为 P0。

常用 API 复现均可使用如下准备，不需要 Bosch 凭据或真实文件：

```python
# 从 local_llm_chat_bot 目录执行；需 requirements.txt、httpx。
import sys, json, copy
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path('tests').resolve()))
from fastapi.testclient import TestClient
import chat_workbench as w
from fixture_support import FixtureEnvironment, PROFILE

with FixtureEnvironment() as f, TestClient(w.app, raise_server_exceptions=False) as c:
    def post(path, body):
        r = c.post(path, json=body)
        assert r.status_code == 200, (path, r.status_code, r.text)
        return r.json()
    post('/api/setup', {'workspace': str(f.workspace),
                       'model': 'gemini-2.5-pro', 'language': 'en'})
    # 需要固定规则 BG 的问题继续执行：
    post('/api/codebook/prepare', {'path': str(f.rules)})
    post('/api/codebook/lock', {})
    post('/api/target', {'target': str(f.bg_a), 'selected_paths': ['facts.txt']})
    # 在同一 with 内执行各问题中的后续操作。
```

UI 复现应以现有 `FixtureEnvironment` + uvicorn + Playwright 为基础。不要将路径替换为真实 Bosch 材料。以下行号是当前快照的定位线索，实施时以函数名为准。

## 3. 按依赖顺序排列的问题与修复操作

### R01 — P2：浏览器测试无法原样运行，且窄窗断言会产生假通过

**是否复现：是。** 原测试在工作区输入处超时；修正后还暴露异步等待和卡片定位问题。其窄窗检查确实放过了 R15。

**精确复现：** 安装 Playwright/Chromium，运行 `python tests/browser_release.py`；在 `#contextworkspace` 填入路径时超时。实际 UI ID 是 `#contextworkspacepath`。仅改这个 ID 后，测试可能在 `#custommodel` 不可见处超时：它只等待 `lastStatusSnapshot`，而 `setup()` 的 `restoreSessionContext()` 尚未结束，后续会恢复模型并隐藏输入框。原“Lock Codebook”按钮名称也不匹配当前英文文案；分类结果和覆盖报告共用 `.classification-card`，`inner_text()` 会命中多个元素。

**根因/位置：** `tests/browser_release.py:35–101`；对应 `chat_workbench.py` 的 `setup():2569`、`showCodebookWorkspace():2549`。仅用 `scrollWidth <= innerWidth` 无法发现被裁掉或负坐标的元素。

**明确修复：** 只修改测试：纠正 ID、使用当前 `rulews.lock_action` 对应按钮；等待工作区恢复真正完成；给分类卡片和覆盖卡片分别设可靠定位条件。检查抽屉及关键按钮的 bounding box、可见性和实际点击结果。把测试依赖写入开发测试说明，测试失败必须返回非零退出码。设置仓库自己的 lint/type 配置，记录原有基线，不要靠禁用全模块检查掩盖问题。不要改 UI 文案来迁就旧测试，不要继续以 `page.evaluate()` 代替所有关键用户点击。

**验收：** 原测试脚本可直接运行；6 阶段流程通过；R15 修复前，新窄窗断言必须失败；运行失败时结果文件明确包含失败阶段，不能仅留下空 checks 让人误判。

**回归：** 全部现有 unittest；浏览器全流程；1440/800/390px 下打开材料抽屉并实际点击“确认所选材料”；同步完成工作区恢复后立即输入自定义模型。类型检查需覆盖 9 个模块；当前典型错误包括 `LocalDocumentLibrary.list` 遮蔽类型名、允许 None 的费用类型和 `split_qualified()` 返回 list/tuple 不一致。

### R02 — P1：工作区内的符号链接可绕过私有状态读取隔离

**是否复现：是，模型提示内容级复现。** 使用纯测试标记，未读取真实私有文件。

**精确复现：** 仅完成 setup。创建 `f.workspace/AI_Bot_State/fixture-private.txt`，内容 `SYNTHETIC_PRIVATE_MARKER`；在工作区创建指向它的 `alias.txt`。mock 当前连接器：第一次返回 `{"answer":"fixture","read_files":["alias.txt"],"changes":[]}`，第二次记录收到的 prompt 并返回普通回答。POST `/api/chat`。当前第二次模型 prompt 含私有标记，API 返回 200。

**根因/位置：** `code_chat_agent.py:304`，`ProjectState.resolve_relative()` 只检查原始 `Path(value).parts` 是否包含忽略目录，没有检查解析后的路径是否落入私有目录；`scan()` 跳过 symlink 并不能保护 `call_model():1450` 的按模型要求直接读取。

**明确修复：** 在统一解析函数中同时验证原始路径和 resolve 后相对工作区的路径；拒绝任何路径组件中的符号链接/Windows junction 或 reparse 跳转，至少保证无法进入实际状态目录、配置、密钥和忽略目录。返回规范化路径；对读、diff 构建和 apply 共用同一判定。Windows 大小写按路径语义处理。不要通过扩大扫描范围解决，不要阻止正常工作区内文件。

**验收：** 该 fixture 在任何模型请求读取前被拒绝；私有标记不出现在 prompt、返回结果或新索引中；正常相对路径仍能读取，越界路径继续拒绝。

**回归：** `test_private_state_symlink_must_not_enter_model_prompt`；现有 `test_state_scan_excludes_private_application_state`；新增目录链接、文件链接、`..`、Windows 大小写/junction 测试（Windows 专有测试可在对应环境运行，不得以 Linux 通过代替）。

### R03 — P1：文本转义函数被用于 HTML 属性，允许注入事件处理器

**是否复现：是，真实 Chromium 中执行了无害标记赋值。** 这是本地输入渲染漏洞，不声称存在未经用户交互的远程攻击。

**精确复现：** 在测试页面执行 `$('workspace').value='fixture" onpointerover="window.__auditXss=1'`，调用 `openContextDrawer('workspace')`。随后向 `#contextworkspacepath` 派发 `pointerover`。实际 DOM 的 `onpointerover` 为 `window.__auditXss=1`，标记为 true。使用手动输入并重新打开抽屉也能走到相同渲染路径。

**根因/位置：** `chat_workbench.py:2738` 的 `esc()` 使用 `textContent → innerHTML`，只满足文本节点转义，不转义属性中的双引号；`openContextDrawer():2517–2521`、`renderCompareSlotsForLanguage():2600` 等把结果拼入 `value="..."`。

**明确修复：** 动态输入值使用 DOM 元素 `.value`/`.textContent` 赋值；如保留模板字符串，增加专用属性转义，覆盖 `& < > " '`，并逐个修正属性插值点。已有安全的普通文本渲染保留。不要改成允许任意 HTML 的 Markdown 渲染，也不要通过修改原始用户路径掩盖问题。

**验收：** 相同输入按原文显示，DOM 不产生额外属性/节点，不执行事件；引号、尖括号、变音和中文路径仍能显示及编辑。

**回归：** Playwright 对工作区、Codebook/材料路径和手动对比模型输入做上述属性注入测试；确认 `onpointerover` 为 null、标记未置位；现有 JavaScript/i18n 测试继续通过。

### R04 — P1：旧页面的确认按钮可以应用另一份未被该页面审阅的修改计划

**是否复现：是。** 只写入临时 fixture 的新文本文件。

**精确复现：** setup 后，让第一次 `/api/chat` 返回新建 `plan_A.txt` 的 changes，保留其确认页面。第二次请求模拟另一标签页，返回新建 `plan_B.txt` 的 changes。再按旧 A 页面实际行为 POST `/api/apply`，body 为 `{"confirmed":true}`。当前返回 200，实际创建 B。

**根因/位置：** `chat_workbench.py:1480` 覆盖全局 `pending`；`ApplyRequest:2279`、`apply():2285` 和前端 `apply():2738` 没有计划版本标识。`before` 哈希只校验文件自审阅后的变化，不能证明用户确认的是当前计划。

**明确修复：** 生成不可复用的 `plan_id`，绑定会话、上下文版本、模型、规则/材料版本和有序 changes 摘要；返回给页面。apply 必须携带该 ID，持锁后对比当前 pending 并重新检查源文件哈希。取消、切换会话/上下文或新计划均使旧 ID 失效。保留确认弹窗、目标范围限制、备份、原子替换和回滚，不允许缺失 ID 的请求继续写入。

**验收：** A 确认遇到 B 返回 409，A/B 均不因该请求写入；只有确认 B 的当前 ID 才能写入 B；取消和重复提交不写入。

**回归：** `test_stale_confirmation_must_not_apply_a_different_pending_plan`；双页面场景；已有 `test_pending_cancel_confirm_backup_and_rollback`；源文件改变、切换 BG/规则后旧确认全部拒绝。

### R05 — P2：状态恢复只校验顶层默认字段，坏的上下文可恢复成运行期错误

**是否复现：是。**

**精确复现：** setup 后将 fixture 会话 `state.data['bg_context']=['legacy-invalid']` 并 save，重新 `/api/setup`。当前返回 200；接着 `/api/chat` 返回 400，detail 为 `'list' object has no attribute 'get'`，未提供可操作恢复说明。

**根因/位置：** `code_chat_agent.py:215` 的 `_load()` 未校验 `bg_context`、`selected_target`、`active_source_ids` 等可选嵌套字段；`ensure_current_sources():1619` 假定 context 为 dict。`local_document_library.py:159` 的索引恢复也主要检查字段存在，未严格验证 chunks 的形状。

**明确修复：** 为持久化上下文定义小型版本化 schema；加载时校验可选字段类型及内层 ID/path/profile 结构。不合法上下文应隔离/保留原状态供恢复，清除不可用绑定并明确提示重新确认材料/规则；有效历史和用量不要整份删除。防御性检查应位于加载边界，模型调用入口也拒绝未验证上下文。

**验收：** 各种旧版缺字段和类型错误均可打开 UI；不会把损坏上下文当作已准备；错误可操作；不向模型发送错误范围的材料。

**回归：** 现有 corrupt state/index 测试；增加 `bg_context` 为 list/string、`active_source_ids` 为 dict、坏 `locked_profile`、坏 chunks、有效部分历史保留的恢复测试。

### R06 — P1：目标切换失败前已清空旧会话，产生部分提交

**是否复现：是。** 历史被归档并从活动会话移除，未证实永久丢失。

**精确复现：** 按公共准备绑定 BG_A，成功 `/api/chat {"question":"classify"}`，记录两条历史。仅修改 fixture Codebook 原文件的字节，使哈希变化；POST `/api/target` 选择 BG_B。当前返回 409，但 `state.data['history']` 已变成 `[]`，旧 transcript 已移入 archives，而旧目标绑定仍可能保留。

**根因/位置：** `chat_workbench.py:1958` 的 `analyze_target()` 先更新文档索引/材料选择，并在约 1983 行 `reset_context(data)`，之后才验证锁定 Codebook 哈希。

**明确修复：** 将目标存在性、文件解析和规则版本检查放入准备阶段；验证全部成功后再在锁内提交 active_source_ids、selected_target、bg_context，并清理旧对话。失败不得改变活动绑定、历史、待确认计划或选择记忆。允许可删除缓存产生，但不能让新缓存记录覆盖活动会话所依赖的旧文档版本；必要时在临时对象中解析后提交。

**验收：** BG_B 切换被拒绝时，BG_A 的目标、历史、结果与 pending 完全保持；源文件只读；成功切换时仍清理旧上下文。

**回归：** `test_failed_target_change_must_preserve_old_conversation`；模拟解析、权限、状态保存失败；现有 target switch 和 source immutability 测试。

### R07 — P1：修改并重新锁定规则后，原 BG 静默退回普通问答

**是否复现：是。**

**精确复现：** 按公共准备绑定 BG_A；复制 PROFILE，将类别名改为 `New fixture class`，POST `/api/codebook/edit`，confirmed=true；POST `/api/codebook/lock`。不重新选择同一个 BG，直接 `/api/chat {"question":"Classify this Baugruppe"}`。当前 200，classification=null；模型 prompt 不再包含 BG 分类上下文，但界面仍存在已选材料和已锁定规则信息。

**根因/位置：** `chat_workbench.py:2060/2076` 的 edit/lock 删除 `bg_context`，却保留 `active_source_ids`、`selected_target`；`call_model():1312` 用是否存在 bg_context 判断模式。前端 `saveCodebookDraft():2743`/lock 后没有可靠地把材料标记为必须重新确认。路径输入 `contextSyncRule():2492` 也没有区分待准备路径与真正生效规则。

**明确修复：** 增加明确的“规则已变更、材料待重新确认”状态。在本次改规则/重新锁定后保留材料草稿供用户确认，同时让 chat/compare 在重新绑定前返回 409，并禁用/提示对应动作；确认成功后绑定新的 profile 版本。展示当前生效规则与尚未准备的路径，避免路径 A 的输入让用户误以为 B 的锁定规则已替换。不要默默退为普通模式，不要自动沿用旧规则，不要丢失材料勾选。

**验收：** 原复现应得到清楚的 409；重新确认现有 BG 后使用新类别/规则 ID，旧 history、prompt、result 不复用。用户明确选择普通单文件问答时仍可使用普通模式。

**回归：** `test_relocked_rules_must_not_silently_disable_bg_classification`；浏览器在不换 BG 的情况下改规则、锁定、追问；取消规则编辑不改变上下文；修改规则路径但不准备时不冒充已生效。

### R08 — P1：多模型对比绕过源文件和规则的新鲜度校验

**是否复现：是。**

**精确复现：** 公共准备完成后，将 `BG_A/facts.txt` 改成 `CHANGED_FIXTURE_BG_A`；记录 mock 调用数。POST `/api/compare`，question=classify，models 为 gemini-2.5-pro、gemini-2.5-flash。当前 `(状态码, 新模型调用数)=(200,2)`；普通 `/api/chat` 对相同变化会拒绝。

**根因/位置：** `chat_workbench.py:1514` 的 `call_comparison()` 未调用 `ensure_current_sources()`，直接使用索引、bg_context 和可用 coverage/dossier。相关预读/重建入口也需要统一入口约束，不能只保护 chat。

**明确修复：** 在任何证据检索/模型调用前，对 comparison 调用统一上下文与源版本检查。检查源文件哈希、当前锁定 profile 版本、材料 ID 集合。coverage/dossier 只在同一版本下可用；失效返回 409 并引导重新确认，不能静默继续。保持每个模型结果独立、只读的对比设计。

**验收：** 原复现 `(409,0)`；删除文件、修改规则、仅修改选择范围也不会发送旧材料；重新确认后恢复正常对比。

**回归：** `test_compare_must_reject_changed_sources_before_call`；将已有单模型 source-change 用例参数化到 compare/coverage/rebuild 等实际依赖证据的入口。

### R09 — P1：非关键词追问的分类修复响应跳过第二次校验

**是否复现：是。** 本轮 classification 卡片被隐藏，但无效内部 action 被当作成功，产生“校验通过”提示并接受回答；不能把隐藏卡片等同于正确拒绝。

**精确复现：** 公共准备后 POST `/api/chat`，question=`TEST_UNKNOWN explain the motor evidence`。现有 mock 连续返回规则外 label=`Rotation`。第一次被发现不合法并重试；第二次仍不合法，却返回 200。相比之下，已有 `TEST_UNKNOWN classify` 用例会正确拒绝，所以原测试未覆盖此分支。

**根因/位置：** `chat_workbench.py:1408–1433` 的 `validated_action()`：首轮条件为 `classification_request or action.get('classification') is not None`；修复轮只有 `if classification_request`。`needs_bg_preparation():1134` 的关键词启发式决定该布尔值，并不覆盖所有中德英表达。成功 action 随后进入历史/导出处理；约 1510 行又按关键词隐藏 classification。

**明确修复：** 使用同一验证入口处理首轮、修复轮以及补充读取后的响应。凡响应包含 classification，必须按当前锁定规则校验；修复分类的那一轮不得再降格为可省略分类。分类意图与“是否需要预读”分开，不依靠多语言关键词作为安全条件。普通解释性追问可以没有 classification；未知标签不能靠近似匹配自动映射。最多一次修复，仍失败就不给 validated 结论、不更新 last_bg_analysis、不接受 changes。

**验收：** 上述追问在连续两次非法标签时清楚失败；不记录“校验通过”；合法追问成功；明确分类请求缺少分类对象失败；不会增加无限重试。

**回归：** `test_followup_repair_must_revalidate_classification`；中/英/德无关键词追问返回未知分类、修复仍错误、修复缺字段、补充 read_files 后错误；保留现有精确类别、JSON 截断及 HTTP 错误恢复测试。

### R10 — P1：“已校验”分类允许伪造 Codebook/BG 页码

**是否复现：是，直接执行生产 validator。**

**精确复现：** 使用 PROFILE；证据仅 `[{'label':'facts.txt block 1'}]`。classification 指定合法 label/confidence、rule_id=`rotation-1`、evidence_labels=`['facts.txt block 1']`，但 `codebook_rule_pages=[999999]`、`bg_evidence_pages=['never-supplied.pdf p999']`。`validate_classification(...)` 当前返回 None，表示通过。

**根因/位置：** `chat_workbench.py:1257–1296`：页码字段只要求非空 list，未与规则和证据对应；规则 ID 集合的类型检查也偏弱。`confidence` 为 list 时会触发不可哈希异常，而不是结构化校验错误。

**明确修复：** 为 classification 建立明确 schema。Codebook 页码必须是正整数、属于实际引用规则/相关规则来源页；BG 引用必须能映射到本轮已发送证据标签及其真实页/表/行范围。DOCX/TXT 无物理页时使用真实 section/chunk 标识，不伪造数字页码。区分 BG 证据与 Codebook 证据；规则 ID 必须是存在的字符串。跨类别边界规则可合法引用，不应简单禁止所有其他类别规则。所有类型不符返回可读验证原因，再按 R09 进行一次修复。

**验收：** 原伪造引用失败；合法页码/表格范围通过；分类卡片只有通过完整结构和引用校验才能标“已校验”。不宣称自动证明技术语义正确。

**回归：** `test_evidence_pages_must_reference_supplied_pages`；缺失页码、负数、字符串页码、列表型 confidence、仅引用规则文件作为 BG 证据、无页码文本、真实规则边界引用。

### R11 — P2：累计成本漏计整类请求，未知 Token 被转成零价

**是否复现：是，两条独立路径。**

**精确复现 A：** 公共准备后运行两模型 `/api/compare`；mock 收到 4 次请求（Codebook 读取/合并 2 次、对比 2 次），而 `state.data['usage']` 的 requests/input/output/cost 全为 0。

**精确复现 B：** `u=summarize_usage([{'input_tokens':None,'output_tokens':None,'usage_complete':False}])`，再以 gemini-2.5-pro 调 `pricing.estimate(model,u['input'],u['output'])`。当前得到 input=0/output=0/cost_usd=0.0，而不是未知。

**根因/位置：** `chat_workbench.py:630–668` 的 Codebook 处理和 `call_comparison():1514–1590` 未记入 `state.note_usage()`；`summarize_usage():671` 把 None/坏值转 0。`release_safety.normalize_usage()` 已保留 unknown，但后续汇总丢失该语义。缓存读/写字段虽显示，价格估计只支持普通输入/输出；费用不完整时不能显示为完整总价。

**明确修复：** 统一每次实际模型调用的记账入口，覆盖 Codebook 页读/合并/修复、预读、dossier、主回答/修复/补读、对比；一次只记一次。保留已知 token 小计和完整性标记，未知数量使用 null，缺任意必要价格/数量则总价为未知或明确“已知部分小计”。真实 0 token、真实 0 单价仍为 0。缓存计费按实际返回字段与价格配置处理；没有缓存价格时明确不完整，不猜价格。重用缓存不得再次计入模型请求。

**验收：** fixture 四次调用累计 requests=4、input=80、output=40；全缺 token 的已知模型不显示免费；混合已知/未知不冒充完整总价；修复重试计入且不重复。

**回归：** `test_codebook_and_comparison_calls_must_be_counted`、`test_unknown_usage_must_not_become_free_price`；现有 provider usage/pricing 测试；新增缓存字段、零价、未知模型、部分缺失、累计精度和失败后已消费 usage 的测试。

### R12 — P2：GUI 丢弃正文流增量，断连取消未接入工作线程

**是否复现：正文流丢弃已实测；关闭页面后的工作线程取消仅代码审查，未做真实 Bosch 中断测试。**

**精确复现：** setup 后 mock `ask_about_files()`，通过 event_handler 连续发两个 `content` 片段，包含 `STREAM_FIXTURE_ANSWER`，最终返回完整合法 action。POST `/api/chat/stream`，当前只有 progress/result/end；result 前没有任何正文片段。取消路径可通过浏览器发请求后 AbortController.abort 检查，当前代码没有把断连写入 cancel_event 的入口。

**根因/位置：** `chat_workbench.py:1394` 的 `model_events()` 仅更新一次“生成中”；`events()` 只保存 reasoning/notice；`chat_stream():2224` 的线程、队列与响应生成器无断连绑定；前端 `chat():2735` 也只处理 progress/result/error。`call_model.report()` 虽检查 cancel_event，但没有实际创建与设置流程。连接器每次请求 timeout=300，HTTP 路径最多 3 次，故可能长时间保留任务槽。

**明确修复：** 仅将解析出的 answer 文本作为 SSE delta 发送并显示临时预览；不要将原始 action JSON、changes 或未验证分类直接渲染成确认卡片。保留最终验证后的一次 result。接入请求取消标记、断连检测和配置化有界超时/退避；取消后停止后续调用，不提交 history/pending/结果。线程未实际停止前不得先释放任务槽，避免并发污染。

**验收：** 生成过程中能看到正文；中断显示明确状态并保留/清理临时预览的规则一致；不生成可执行半计划；任务终止后可以重试；不调用下一轮补读/修复。

**回归：** `test_model_content_chunks_must_reach_stream_client`；现有 `test_partial_stream_never_becomes_an_executable_plan`、流式拒绝回退测试；增加浏览器断连/取消与工作线程释放、超长回答、代码块/表格跨 chunk、最终 JSON 截断测试。

### R13 — P1：切换界面语言会无提示丢失未保存的规则编辑

**是否复现：是，真实浏览器。**

**精确复现：** 打开已准备 Codebook，点 Edit rule draft，修改 `#ruleeditor`（测试使用 `UNSAVED_FIXTURE_DRAFT`，故意连未完成 JSON 也覆盖）。切换 ZH→EN。当前编辑器节点数量变成 0，草稿标记从 DOM 消失，回到原 profile 展示；未提示保存或取消。

**根因/位置：** `chat_workbench.py:2427` 的 `rerenderLanguageSensitiveUI()` 无条件在 codebook-workspace 中调用 `showCodebookWorkspace()`；`editCodebookDraft():2742` 没有独立 draft/dirty 状态。

**明确修复：** 将正在编辑的原始文本、dirty 标记、光标/选择区保存为编辑状态；语言切换只更新编辑 UI 文案或用该状态重建编辑器。未完成/非法 JSON 也必须保留，不能在切语言时强制解析。取消才丢弃草稿，保存仍需明确确认。更换 workspace/session/Codebook 时有未保存修改须明确处理，不可默默带入新规则。

**验收：** 连续 ZH→EN→DE→ZH→EN→DE 后编辑文本逐字相同、仍在编辑模式；取消不写入；保存只修改应用中的规则草稿，不覆盖源 Codebook。

**回归：** Playwright 针对合法/未完成 JSON、长规则、选择区和错误提示；保留现有 Codebook confirmed=false 与源文件哈希不变测试。

### R14 — P2：三语切换仍有动态中文残留及旧语言分类卡片

**是否复现：是，API 流事件和真实浏览器均复现。**

**精确复现 A：** 使用 language=en 的公共准备发送 classify。SSE progress/notices 含“正在读取并理解文件 1/1”“已完成 1/1”“已生成并保存 BG 综合证据档案”等 6 条中文 UI 文案。

**精确复现 B：** 中文界面生成分类卡片，再切到英文；h3 仍为“本次分类结论（已校验）”，但当前 `t('classification.title')` 为 `Classification result (validated)`。

**根因/位置：** `chat_workbench.py:1011` 的 `prepare_coverage()`、`call_model():1340–1503` 的 notices 和连接器 notice 硬编码中文；`classificationCard():2535`/coverage card 已渲染节点未由语言切换重建。部分 scope、错误文字、德语的“页”等也在 catalog 之外。

**明确修复：** 内部 UI 消息传 message_key + 参数，前端按当前语言渲染，或后端统一可测试的三语消息目录；历史分类卡片保留结构数据并重绘其标签。不要翻译模型原始回答、用户输入、文件名、类别名或规则内容；只翻译 UI 包装文案。先落实 R13，避免修语言时再次销毁编辑状态。

**验收：** 六次语言切换后，静态与动态 UI 包装文字一致、无裸 key、无旧语言卡片；语料中包含中文文件名/模型回答不应被错误认定为翻译失败。

**回归：** `test_english_progress_and_notices_must_not_contain_chinese_ui`；对英文/德文重放首次预读、缓存复用、模型失败/重试、Codebook 编辑、Token/成本、确认弹窗和 classification/coverage 卡；catalog 测试继续通过。

### R15 — P2：390px 窄窗下材料抽屉位于屏幕外，关键按钮不可操作

**是否复现：是，bounding box 与截图双重确认。**

**精确复现：** 视口 390×900，打开 materials 抽屉。当前 `scrollWidth=390`，但抽屉 `{left:-260,right:130,width:390}`；“Confirm selected materials”按钮范围约 `[-241,-34.56]`，整个按钮位于屏幕外。800px 下此抽屉未出现该越界。

**根因/位置：** `chat_workbench.py:2455` 的 `initLanguageLayout()`：1180px 断点设 `right:260px`；760px 断点只设 width:100%，没有重置 right。主区域网格/最小尺寸也需要用实际几何验证，不能只看有没有横向滚动。

**明确修复：** 在窄窗断点将抽屉横向锚定为视口内，如 left:0、right:0、width:auto，并确保上下滚动可达所有动作；只调整必要的媒体查询。保留桌面布局和原有 UI 设计，不把按钮隐藏来消除溢出。

**验收：** 390/800/1440px 中抽屉左右边界在视口内；选文件、展开树、确认、取消、关闭均能真实点击；长错误和德语文案不遮挡。

**回归：** R01 增强后的几何和点击测试；浏览器截图人工检查；改变语言和长路径后再次检查。

### R16 — P2：README 承诺的自定义 env 文件在 GUI 启动路径中被忽略

**是否复现：是，启动入口 mock 和 API 参数路径均验证。** 真实 Bosch 凭据未使用。

**精确复现：** README 第 49 行说明可 `--env-file` 指定配置。用 runpy 执行 `chat_workbench.py` 并设置 argv 中的该参数，mock uvicorn.run；入口没有任何参数解析。API `/api/setup` 传入 `env_file=<fixture custom.env>`，捕获 load_dotenv 调用，实际仍加载应用目录 `.env`；无环境 key 时返回 400。另探测 `--port 8877` 仍使用 8765，说明未知参数也被静默忽略（README 当前未承诺支持 --port）。

**根因/位置：** `chat_workbench.py:277` 的 Setup 有 env_file/state_dir 字段，但 `setup():1659` 固定 env_file；末尾约 2750 行入口直接启动固定 8765。`README.md:42–50` 与 GUI 行为不一致。

**明确修复：** 为 GUI 明确实现 `--env-file` 启动参数并在 setup 使用解析后的应用配置，保留“默认从程序目录加载 .env”的行为；不在前端或日志返回 key。未知参数由 argparse 明确报错。增加可选 `--port` 或端口冲突的可操作提示，继续仅监听 127.0.0.1。首次依赖缺失、无配置和状态目录不可写应给安装/配置/权限恢复说明。不要把状态或 .env 默认写到 BG 源文件夹。

**验收：** 从不同 cwd 和含空格/中文/变音路径运行，确实读取指定 fixture env；缺失配置明确报错且可恢复；参数拼错不能悄悄启动；端口冲突提示如何重用已有实例或换端口。

**回归：** 启动 CLI 参数测试；清空 key 环境后验证自定义 env 实际生效；现有 missing key 用例；端口占用、缺依赖、不可写状态目录、关闭再启动的子进程 smoke。Windows ACL/锁行为必须在 Windows 另验。

## 4. 已验证通过的流程及其边界

以下均针对当前代码和本地合成数据；不代表 Bosch 服务可用或分类语义正确。

| 流程 | 已通过的证据 | 不能据此推断 |
|---|---|---|
| 工作区与模型 | Unicode/空格路径 setup；合法前缀 ID、去空格/大小写规范化；空/带内部空格/未知家族拒绝；切换实际请求路径 | Bosch 实际模型清单、部署别名、授权和区域路由正确 |
| 持久化 | 常见顶层坏 JSON/缺字段降级；浏览器刷新恢复 BG、workspace、model、language | 所有嵌套坏状态、进程重启/并发实例/Windows ACL 均安全；R05 未修 |
| 输入解析 | PDF、DOCX、XLSX、CSV、TXT、MD、PNG/JPG/JPEG/WEBP；坏 PDF/图片、空文本/空白表、超大文件、嵌套/重复/全取消选择；真实 parser，源字节不变 | `.xlsm` 宏与复杂企业文档保真、扫描图语义理解、极长 Windows 路径均已验证 |
| 固定规则主流程 | 准备→锁定→确认 BG_A→分类→追问→编辑规则→重新确认 BG_B→新分类；最后 prompt 无 BG_A 标记 | R07 不重新确认材料的分支、R09/R10 非法响应分支已安全 |
| 上下文隔离 | 正常切换目标/模型清理旧会话；无 active_source_ids 不搜索旧文档；主聊天拒绝修改后的源文件 | comparison、失败切换、规则切换的全部路径均有相同保护 |
| 错误恢复 | HTTP 400/401/403/404/413 不重试；429/500/502/503/504 最多三次；超时/连接错误有限重试；空/截断供应商结果拒绝；任务槽失败后释放 | 生产 SDK 默认重试、真实限流头、代理/证书/SSO、流断连取消已端到端验证 |
| 流式连接器 | OpenAI SDK mock 中 reasoning/content 分离；不完整流不成为可执行计划；不支持流时有界回退 | GUI 逐字输出已经实现；R12 仍丢正文 delta |
| 用量底层 | 三类 token 字段归一化、缺字段保持 None、零值、非法值和缺价格安全；部分 main-chat 估价 | 总账完整或所有 UI 显示正确；R11 明确失败 |
| 规则源保护 | confirmed=false 不保存编辑；保存应用草稿不改源 DOCX；类别重复/缺定义拒绝 | 规则编辑中的未保存内容始终保留；R13 明确失败 |
| 代码与 Excel 写入 | 单计划明确确认；模拟第二文件替换失败回滚、备份、取消；Excel 副本保存后验证，源哈希、普通/数组/数据表公式、合并单元格保留；模拟保存失败无半成品 | 多页面确认正确；R04 未修；真实 Windows 文件占用、SMB 硬链接支持、复杂 xlsm 保真已验证 |
| UI | 修正测试副本后完整流程 6 阶段通过；六次语言切换保留所选模型；无 pageerror/裸 key 警告 | 动态消息全翻译、编辑状态不丢失、390px 可操作；R13–R15 明确失败 |

## 5. 未完成或无法真实验证的项目

1. **Bosch 内部 Endpoint：未在真实 Endpoint 验证。** 包括真实凭据、网关/代理/TLS、部署 ID、授权、限流响应头、真实 token/cache usage 格式、供应商流协议、视觉能力、分类质量和实际账单。mock 通过不能替代这些结果。
2. 真实 Bosch Windows 机器、企业杀毒/浏览器策略、网络盘/OneDrive/SMB、NTFS ACL、长路径、文件被 Excel 占用以及无权读取的文件夹，尚未真实验证。Linux root 下 chmod 不能代替 Windows 权限测试。
3. Tesseract 德语数据、复杂扫描 Codebook、DFC 大图、真实宏工作簿及企业格式未做真实数据测试；当前 `.xlsm` 声明支持但本次格式矩阵没有宏 fixture。不要将 `test_all_declared_file_formats` 的名称当成覆盖证明。
4. 流断连、取消、任务总时限和多供应商生产默认重试仍需补充针对 GUI 的验证；本次只有现有 transport/SDK mocks 和正文 delta 定点探针。
5. 完整 Ruff 105 项、全模块探索性 mypy 38 项仍在；不存在可宣称“lint/类型全部通过”的依据。避免为了消除风格告警而重构业务。
6. 无 fresh ZIP、无解压冷启动结果，本轮明确不打包。既有打包工作流 `.github/workflows/package_local_llm_chat_bot.yml` 没有先运行测试；排除模式只覆盖部分缓存和 `.env`，没有明确排除 `AI_Bot_State`、日志、虚拟环境等。当前没有实际发现这些数据已泄露或被打包。未来获准发布前应增加测试门禁和明确包含清单，不触发打包作为本轮实施副作用。

Bosch 电脑上将来的最小真实 smoke：从非项目 cwd 启动指定 env；检查模型实际响应 ID；用非敏感小 BG + 锁定规则完成一次分类和追问；切模型/改规则/换 BG 后重新确认并验证上下文；观察 token/费用是否完整；故意用无效模型确认失败后可继续；只在 Excel 副本上验证写入。此清单待本报告修复完成后执行，不要求现在提供凭据。

## 6. 推荐给 6.1 Sol/Terra 的逐步实施顺序

1. 保存当前 diff 和未跟踪文件清单，不清理或覆盖已有工作。按 R01 修复测试脚本，使用现有 FixtureEnvironment；把本文新增诊断转为真正回归测试。先确认失败能复现，不预先改业务逻辑。
2. 实施 R02、R03、R04：路径边界、DOM 属性边界、计划确认绑定。每项仅改相关函数，分别跑针对性测试，再跑 source immutability/rollback。
3. 实施 R05→R06→R07→R08：加载 schema、安全事务式切换、规则版本与材料重新确认、所有模型入口共享检查。明确上下文版本后再完善 plan_id 绑定；不要让规则变化降为普通模式。
4. 实施 R09→R10：统一所有响应轮次的分类验证、证据引用结构。拒绝未知/多个/空分类，不以近似匹配代替固定规则。
5. 实施 R11：统一记账和未知值语义；以 mock 的真实调用计数核对，不以 UI 显示数字反向证明正确。
6. 实施 R12：安全的 answer 流预览、取消与有界任务生命周期；不泄露未验证 action，不提前释放仍运行的任务槽。
7. 实施 R13→R14→R15：先保留编辑状态，再完整动态本地化，最后修断点布局。执行六次语言循环和真实点击，不能只验证翻译目录完整。
8. 实施 R16：启动参数、配置和可操作失败信息；记录明确依赖/测试命令。处理与本次修改有关的 lint/type 错误，建立显式检查配置；剩余旧告警逐项说明，不以大规模重构清零。
9. 运行完整现有 + 新增回归、lint、类型检查、compileall 和完整浏览器流程。报告每个 R 编号的测试证据与剩余限制。此阶段仍**不生成 ZIP、不访问真实 Bosch Endpoint、不修改真实 BG/Codebook/Excel**，除非用户另行授权。

交接完成。审查在此停止，等待实施模型按上述顺序处理。
