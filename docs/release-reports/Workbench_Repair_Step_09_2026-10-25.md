# Workbench 修复第九步：综合验收与最终交接

日期：2026-10-25（Europe/Berlin）。范围：原修复报告第 6 节第九步。

**九步修复与本轮综合检查已执行完毕。合成数据功能回归通过，完整发布验收尚未全绿。**
完整 Ruff 仍有 257 项告警，mypy 仍有 44 项错误；目标 Windows/Bosch 环境及新分发包尚未验证。
本报告不将这些未通过、未验证项目算作通过。

## 验证对象与本步变更

开始时本地与远端 main 均为 `238f6b881a3a4974356a0f9559fe3f3bfbb2f437`，工作区干净。
已阅读原修复报告、tools/release_audit/README.md 和第八步交接报告。

本步复核发现一个 R14 遗漏：`/api/pick/{kind}` 的原生选择器窗口标题仍写死为中文。
原浏览器流程模拟了原生选择器的返回值，因此此前没有验证传入系统窗口的标题。
本步完成了以下补修，再运行完整检查：

- 文件/文件夹窗口标题进入共享三语目录，优先使用请求的 X-Workbench-Language，回退到当前会话语言。
- 新增一个回归方法，检查中/英/德 × 文件/文件夹六种标题组合、语言头优先级、路径原文、取消及非法 kind。
- 该测试在 Tk 边界模拟对话框，不会打开真实系统窗口。Windows 系统窗口实际呈现仍待实机验证。
- 整理同一选择器函数的紧凑语句，消除 3 项既有 Ruff 告警。未修改分类、记账、写入或取消协议。

最终测试对象为上述基础提交加本步选择器补丁。
[机器可读证据](Workbench_Repair_Step_09_Evidence_2026-10-25.json) 保存全部被测应用/测试文件的 SHA-256、
184 个方法的实际结果、R01–R16 对应关系、依赖版本、命令退出码及当前每一条静态检查诊断。
后续仅修改交接文档，不改变已测运行代码。

## 本轮完整检查结果

| 检查 | 实际结果 | 判定 |
|---|---|---|
| 完整 unittest discovery | 184 方法：183 通过、1 跳过、0 失败、0 错误；111 个成功子测试 | 功能回归通过，跳过项另列 |
| 原审查提升的 15 个后端断言 | 全部通过 | 通过 |
| 完整 Chromium 浏览器流程 | 17 方法全部通过；无 pageerror/裸翻译 key 告警 | 通过 |
| 浏览器失败路径负对照 | 故意注入 1 个失败，原入口退出 1；结果 success=false 并记录失败阶段 | 失败传播机制通过 |
| 致命 Ruff 子集 E9/F63/F7/F82 | 退出 0 | 通过 |
| 完整 Ruff（应用及测试） | 退出 1：257 项，E702=166、E701=84、F401=6、E402=1 | 未通过 |
| mypy，显式检查 11 个应用模块 | 退出 1：44 个错误，涉及 6 文件；目标 Python 3.10 | 未通过 |
| compileall | 退出 0 | 通过 |
| git diff --check | 退出 0 | 通过 |
| 补充字体/布局检查 | 中/英/德 × 390/800/1440px 九种组合，抽屉边界及内部宽度检查通过 | 当前环境通过 |

唯一跳过项为
`test_release_step_two.StepTwo.test_native_windows_case_and_junction`，
原因是需要原生 Windows NTFS junction 与大小写语义。Linux 上的模拟 reparse 测试不能替代它。
没有添加 skip/expectedFailure，也没有降低现有断言。
负对照的故意失败单独记账，不属于生产回归套件中的失败。

完整静态诊断的最新位置以本步 JSON 为准。
[第八步逐项说明](Workbench_Repair_Step_08_Static_Findings_2026-10-25.md) 保留为历史基线和处理建议。
本轮只消除了选择器中的 3 条紧凑语句告警；其余 257 项仍是既有类型的诊断。
44 项 mypy 错误未增加。未添加全局忽略、缩小模块范围或通过改配置掩盖失败。

## R01–R16 证据汇总

下表给出主要测试文件；JSON 中列出每项的完整方法名和实际状态。
“通过”均限定为当前合成数据和测试环境，不表示真实 Bosch 服务或工程分类语义已经验证。

| 编号 | 已实现并复核的行为 | 主要本轮证据 | 边界 |
|---|---|---|---|
| R01 | 正确控件、恢复完成等待、卡片定位、真实点击及几何断言；失败可靠退出非零 | browser_release、test_workbench_i18n、原入口负对照 | 完整静态门禁仍未通过 |
| R02 | 读/diff/apply 共用规范路径边界，拒绝链接、越界、私有状态及配置路径 | test_release_step_two、私有标记审查断言 | 原生 Windows 专用测试跳过 |
| R03 | 工作区/规则/材料路径和自定义比较模型不形成额外 HTML 属性或事件 | browser_release 两个属性注入方法 | 真实 Chromium，使用无害标记 |
| R04 | 确认绑定当前 plan_id、上下文和源版本；旧页、缺失/重放 ID 拒绝 | test_release_step_two、双页面浏览器方法、backup/rollback 矩阵 | 写入仅发生在临时 fixture |
| R05 | 加载时验证嵌套上下文/索引；隔离损坏部分，保留有效历史和用量 | test_release_step_three 的 corrupt/legacy/index 方法 | 不承诺任意未知损坏可自动恢复 |
| R06 | 目标先准备后提交；解析/权限/保存失败保留旧绑定、历史和计划 | test_failed_target_prepare_and_commit_preserve_every_active_record 等 | 单进程异常回滚，不是多文件断电原子性 |
| R07 | 规则版本变化后必须重新确认材料；待准备路径与生效规则明确区分 | test_release_step_three、同一 BG 改规则/重锁浏览器流程 | 显式普通问答模式保留 |
| R08 | chat/SSE/compare/coverage/dossier/cache 共享范围及源新鲜度检查 | changed_deleted_missing_and_changed_scope 入口矩阵等 | 拒绝时核对零新增 mock 模型请求 |
| R09 | 首轮、修复、补读共用验证；修复预算有界；非法结果不提交 | test_release_step_four.ResponseRounds、追问审查断言 | 普通解释可无分类；返回的分类仍须验证 |
| R10 | 类别/字段类型、规则页与真实 BG 页/表/块引用验证 | test_release_step_four.ReferenceSchema、真实生成 PDF/表范围 | 结构与来源可追溯不证明工程解释正确 |
| R11 | 每次实际派发统一记账；失败消耗保留；未知与真实零区分；缓存不重复收费 | test_release_step_five 全部 20 方法、两条审查断言、未知用量浏览器流程 | 配置估价不等于实际供应商账单 |
| R12 | 仅预览已解析 answer；最终只发布已验证结果；停止/断连/超时期间持有任务槽 | test_release_step_six、test_stream_progress、两条浏览器生命周期方法 | 协作式取消，受阻 I/O 在传输边界内退出 |
| R13 | 非法/长草稿、dirty、选择区、滚动及错误跨六次切语言保留；取消/保存/版本冲突明确 | test_release_step_seven、三个草稿浏览器方法 | 内存草稿，不承诺崩溃恢复 |
| R14 | 动态消息/卡片按 key+参数重绘；用户/模型/规则/文件名原文保留；本步补齐选择器标题 | test_release_step_seven、test_workbench_i18n、新增 test_release_step_nine、动态消息浏览器方法 | 系统对话框实际呈现仍需目标 OS 验证 |
| R15 | 390/800/1440px 抽屉及动作可达；长德文/错误/路径换行；文件/文件夹/取消/勾选/确认/关闭 | 两条几何/实际操作浏览器方法、补充九种语言/屏宽组合 | 当前 Chromium/Linux 字体环境 |
| R16 | env/port 参数、未知参数拒绝、统一配置、可操作错误及重试；不同 cwd 与重启 | test_release_step_eight 全部 14 方法、启动审查断言、可见恢复浏览器方法 | Python 3.10 与 Windows ACL/锁仍需实机运行 |

完整浏览器主流程还覆盖：工作区与自定义模型、规则准备/锁定、BG_A 分类与追问、规则编辑、
BG_B 重新确认、结果不带 BG_A 旧标记，以及刷新后恢复工作区/模型/语言/材料范围。
旧的历史审查脚本保留为历史记录；其中使用旧选择器或固定主机路径的脚本不充当当前通过证据。

## 环境、字体与可复现命令

本轮重新建立独立虚拟环境，按仓库 requirements-dev.txt 安装依赖；使用了运行环境中已经满足要求的
系统站点包，因此不将它称为完全隔离、完整锁定的系统镜像。版本明细保存在 JSON 中。

关键版本：Python 3.12.14、Node 24.22.1、Playwright 1.51.0、Chromium 134.0.6998.35、
Ruff 0.17.2、mypy 1.15.0；OpenAI SDK 3.37.0、FastAPI 0.162.0、Uvicorn 0.54.0、
httpx 0.28.1 / SDK 使用的 httpx2 2.16.0。
应用依赖仍为下限约束，不能把一次通过推断为所有未来依赖版本都兼容。

首次截图证实该 Linux 环境没有中文字体，汉字显示为方框。
补充仅用于测试的 Noto Sans CJK SC 后，重新运行完整浏览器套件，
并复核了等待抽屉动画结束后的九种语言/屏宽组合。
中文字形可见，标题与目录一致，抽屉在视口内，内部没有横向溢出；已人工查看截图。
字体来源及摘要写入 JSON，字体未加入仓库/分发包。
Windows 自带字体、浏览器缩放和系统选择器布局仍需目标机器确认。

从 local_llm_chat_bot 运行：

```bash
python -m unittest discover -s tests -v
python tests/browser_release.py
python -m ruff check --select E9,F63,F7,F82 .
python -m ruff check --output-format json .
python -m mypy
python -m compileall -q .
git diff --check
```

本轮 unittest 使用默认 discover 加临时 TextTestResult 记录器，逐项记录真实结果并按
wasSuccessful() 返回退出码；测试内容和发现范围不变。临时负对照仅替换浏览器入口加载的
测试套件为一个故意失败的方法，用来验证原入口的失败记录和退出码。
常规重跑可直接使用上述标准命令。
首次准备环境、固定开发工具版本及输出目录配置见 [TESTING.md](../../local_llm_chat_bot/TESTING.md)。

## 发布物检查与剩余限制

1. **完整静态门禁仍失败。** 当前 257 项 Ruff 与 44 项 mypy 诊断均保留、逐项记录。
   九步执行完毕不等于完整发布检查全绿；静态清理需按已记录建议安排，不做无关大规模重构。
2. **旧 ZIP 不能代表当前 main。** 本步只读比较了仓库 local_llm_chat_bot.zip 的 12 个应用文件摘要：
   10 项与当前代码不同或缺失；release_safety.py、request_runtime.py、workbench_startup.py 未包含在旧包中。
   该 ZIP 最后更新提交为 `c98901e4c5b6208bae4652d9f75130be82ab9ad4`。
   本轮未重建、解压运行或修改 ZIP，不能把下载旧包称作本次修复后的冷启动验证。
3. **打包流程尚无测试门禁和明确包含清单。** 当前 workflow 直接 zip，排除项只涉及部分目录及 .env；
   未明确排除 AI_Bot_State、日志和虚拟环境。本轮未运行该 workflow，也没有据此声称已发生数据泄露。
   获准生成分发包前，应先完善门禁/包含清单，再验证包内容与解压冷启动。
4. **Windows/企业环境待验。** NTFS 大小写/junction/ACL、Excel 文件占用、杀毒策略、长路径、
   OneDrive/SMB、系统对话框与真实目标字体未在 Windows 实机验证。Linux 模拟错误不替代这些结果。
5. **真实 Bosch 服务待验。** 未调用真实 Endpoint；代理、TLS/SSO、部署授权/ID、实际 usage/cache 字段、
   流协议、限流头、账单和工程分类质量不能由 loopback/SDK mock 推断。
   取消不证明服务端停止生成或停止计费。
6. **格式与 OCR 覆盖有限。** 真实 parser fixture 覆盖 PDF、DOCX、XLSX、CSV、TXT、MD、PNG、JPG、JPEG、WEBP。
   没有真实宏 .xlsm 保真 fixture；扫描 Codebook、德语 Tesseract 数据、复杂 DFC/企业图纸及极大真实材料仍待验。
   `.xlsm` 的声明支持和名为 all_declared_file_formats 的方法不能作为宏保真证明。
7. **部署与并发边界。** Python 3.10 未实际执行；本轮运行 Python 3.12。一个服务进程内的串行化/事务恢复
   已测，多实例共享状态、断电中断和全部网络文件系统故障模式未被证明安全。

将来获准在 Bosch 电脑执行的最小验证应包括：从非项目 cwd 指定 env 启动；确认实际响应模型 ID；
用非敏感小装配体和锁定规则完成分类/追问；改规则、换模型、换材料后重新确认；核对 token/费用完整性；
用无效模型检查失败后的恢复；仅在 Excel 副本验证写入；记录目标字体、文件权限与锁定行为。
本报告未执行这些真实环境步骤，也不要求现在提供密钥或真实材料。

## 交接结果

原报告的九步执行序列到此完成。R01–R16 均有当前回归证据或明确的原生环境待验边界。
本次保留的开放项目为静态门禁、目标环境验证与分发包发布验证，不把它们描述为已通过。
本轮未生成 ZIP、未触发打包、未访问真实 Bosch Endpoint、未修改真实 BG/Codebook/Excel。
提交继续使用 `[skip ci]`。

原始日志与截图位于临时 /tmp/workbench-step9；完整结果摘要、方法名、诊断和源摘要已保存在仓库 JSON 中。
临时日志/截图/环境/字体不随仓库提交，不能保证其跨会话保留。
