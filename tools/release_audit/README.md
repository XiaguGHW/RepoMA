# 2026-10-24 审查基线同步说明

此目录与本次同步的 `local_llm_chat_bot/` 改动共同恢复发布前报告的完整审查基线。它不是 R01–R16 的修复完成版本。报告位于 `docs/release-reports/Baugruppe_Classification_Workbench_PreRelease_Repair_Report_2026-10-24.md`。

此前工作区的 7 个已修改文件、`release_safety.py` 和 5 个新增测试/fixture 文件已一并同步。业务代码按审查时原样保存；诊断脚本仅将原机器的目录、Chromium 路径和输出目录改为可移植配置，没有改变诊断断言。原报告中的 `audit/...` 诊断脚本现在位于本目录。

## 安装与运行

从仓库根目录执行，使用独立 Python 环境。需要 Node.js 才能运行现有 JS 回归测试。

```bash
python -m pip install -r local_llm_chat_bot/requirements.txt
python -m pip install httpx ruff mypy playwright==1.51.0
python -m playwright install chromium

cd local_llm_chat_bot
python -m unittest discover -s tests -v
python -m ruff check --select E9,F63,F7,F82 .
cd ..

python tools/release_audit/test_audit_gaps.py
python tools/release_audit/browser_original.py
python tools/release_audit/browser_adapted.py
python tools/release_audit/browser_gaps.py
python tools/release_audit/startup_state_probe.py
```

- `test_audit_gaps.py`：11 个期望安全行为的断言。审查基线中这 11 个断言失败，代表报告发现的缺陷仍存在，不是测试环境缺少文件。不要把它们设为 skip/expectedFailure 来制造全绿结果。
- `browser_original.py`：审查时原浏览器测试的可移植运行副本；预期在旧的 `#contextworkspace` 选择器超时。应用目录中的 `tests/browser_release.py` 也保留原样，供 R01 修复。
- `browser_adapted.py`：审查时修正测试选择器、等待条件和卡片定位后的副本；原环境的 6 个阶段检查通过，但窄窗检查仍有报告 R15 指出的缺口，不是可靠性验收完成证明。
- `browser_gaps.py`：输出规则草稿丢失、属性注入、旧语言卡片、抽屉边界等诊断观察值；脚本退出 0 仅表示采集完成，**不表示观察值全部安全**。R01 应把这些观察转换成严格回归断言。
- `startup_state_probe.py`：恢复审查时通过一次性命令执行的启动参数和嵌套状态探针，输出观察值，不作通过声明。

浏览器默认使用 Playwright 安装的 Chromium。已有浏览器可通过 `WORKBENCH_CHROMIUM_EXECUTABLE` 指定绝对可执行路径。浏览器输出默认写到系统临时目录，也可设置 `WORKBENCH_TEST_OUTPUT`；不要将输出或截图提交到仓库。

全部材料由现有 `tests/fixture_support.py` 临时生成，模型服务使用回环 HTTP mock；不需要 Bosch 凭据。全部 Bosch 服务部分仍为“未在真实 Endpoint 验证”。

## 下一步

新对话从最新 main 开始，先核对本次文件均存在，再按报告第 6 节第一步执行 R01。原报告是历史审查结果，未更改其事实描述；其中“未提交/仓库外”的位置描述由本同步说明更新。

本次只同步审查基线，不打包 ZIP。提交消息使用 `[skip ci]`，避免现有 push 工作流自动创建 ZIP。后续对应用目录的提交同样需要遵守用户的“不生成 ZIP”限制。
