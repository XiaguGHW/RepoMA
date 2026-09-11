# 修改需求：PDF 跨模型 Prompt 配置测试自动化

请先阅读当前仓库中最新的分类脚本、Prompt 定义/模板、模型 connector 和现有的 P1–P5 实验输出；不要根据旧版本脚本猜测参数名或文件路径。请在尽量不破坏现有实验脚本的前提下完成下面的修改。

## 1. Prompt 命名调整

我此前把完整 Codebook 配置从 P3 继续迭代到了 P5。现在请统一改为下面四个正式实验配置：

1. `p1`：只提供类别名称（原 P1）
2. `p2`：类别名称 + 功能描述（原 P2）
3. `p3_original`：原始的完整 Codebook 配置（原 P3，不包含后续优化）
4. `p3_optimized`：优化后的完整 Codebook 配置（原 P5）

请保留 `p3_original`，不要把它覆盖掉。原来代码或输出中叫 `p5` 的优化版本，请改为/映射为 `p3_optimized`；最终运行日志、Excel 文件名、输出目录和结果表都应明确显示这一名称，避免以后混淆。

## 2. 本轮要运行的 PDF 实验

**这份需求只针对 PDF 输入实验。**每个 BG 的上下文必须以现有的 PDF 打包/输入方式提供给模型；不要把本轮实验改成图片输入或纯文本输入。

Prompt Engineering 阶段使用的 14 个 BG（7 类 × 每类 2 个）仅是开发/调参集，不能混入正式准确率比较。本轮所有正式的配置比较都必须使用其余的 **115 个 PDF BG（129 − 14）**，并使用这 115 个 BG 对应的 Ground Truth。

此前 Gemini 2.5 Pro 的 P1 和 P2 只在那 14 个 Prompt Engineering BG 上做过，**尚未完整运行剩余 115 个 BG**。因此，本轮需要额外补跑 Gemini 2.5 Pro 的 `p1` 和 `p2`，且两次都只分类这 115 个 PDF BG。

请为以下其余 3 个模型自动运行相同的 4 个 prompt 配置：

- Gemini Flash（请使用项目 connector 当前实际支持、稳定的 Gemini Flash model ID）
- Claude Opus
- Claude Haiku

三个其余模型均在这 115 个 PDF BG 上运行四个配置。因此，本轮总共应执行：

- Gemini 2.5 Pro：`p1`、`p2` = 2 次；
- Gemini Flash、Claude Opus、Claude Haiku：各 `p1`、`p2`、`p3_original`、`p3_optimized` = 12 次；
- 合计 **14 次完整 PDF 实验运行**。

每一次运行都使用：

- 同一份 **115 个 BG 的 PDF 输入数据集**；
- 同一批 115 个待分类 BG（不包含 Prompt Engineering 的 14 个 BG）；
- 相同 Ground Truth / classes 文件；
- 相同输出 JSON schema 和相同评估逻辑；
- 固定 Temperature = 0（若 connector/API 的实际参数名不同，请正确设置并在日志中记录）；
- 除 prompt 配置及模型外，不改变任何实验条件。

这里的“一次完整实验运行”指：一个模型 + 一个 prompt 配置，对上述 **115 个 PDF BG** 完整分类一次；不是只运行一个 BG，也不是只运行用于 Prompt Engineering 的 14 个 BG。

## 3. 新建批处理启动脚本

请新建一个清晰命名的 Python 脚本（放在仓库现有 `scripts/` 或项目当前用于运行脚本的位置；不要替换原有单次运行脚本），用于按顺序自动执行这 14 次 PDF 实验。

脚本要求：

1. 固定运行顺序如下：
   - Gemini 2.5 Pro：`p1` → `p2`（两次均为剩余 115 个 PDF BG；这是补跑）
   - Gemini Flash：`p1` → `p2` → `p3_original` → `p3_optimized`
   - Claude Opus：`p1` → `p2` → `p3_original` → `p3_optimized`
   - Claude Haiku：`p1` → `p2` → `p3_original` → `p3_optimized`
2. 全部 14 次都使用同一份 115-BG PDF 清单。脚本启动前请检查并明确指定/生成该清单；不要依靠“排除前 14 行”这种不可靠的行号假设，应根据 BG ID 从 129-BG 总清单中排除 Prompt Engineering 的 14 个 BG ID。
3. 每次完整实验结束后，等待 **10 秒**，再开始下一次；最后一次无需等待。
4. 复用现有单次分类脚本/现有评估逻辑，例如通过 `subprocess` 调用。不要复制一套分类业务逻辑到批处理脚本里。
5. 每次运行必须写入独立、不会覆盖旧结果的输出目录；目录名至少含模型名、配置名和日期时间或 run ID。例如：`outputs/pdf_cross_model/<model>/<config>/<timestamp>/`。
6. 在控制台和一个总览日志/CSV 中记录：开始时间、结束时间、模型、prompt 配置、实际命令、输入 BG 数（应为 115）、返回码、输出目录、是否成功、异常信息（若有）。
7. 某一运行失败时，记录失败并继续执行后续运行；最终在控制台输出成功/失败汇总。
8. 提供一个简短、可直接复制的运行命令，并说明运行前必须具备的环境变量/认证条件。不要在代码或日志中输出 API key、Token 或其他凭据。

如果现有脚本没有能从命令行选择 `p1`、`p2`、`p3_original`、`p3_optimized` 的参数，请以尽量小的改动加入一个明确的 `--prompt-config` 参数，并保证默认行为不影响已有用法。

## 4. Claude Prompt Caching：先检查并明确回答

请先检查当前 Claude connector/API 实现以及实际使用的 Anthropic SDK/API 版本，然后在回复中明确回答：

1. Claude 是否已经有可用的 prompt caching 实现？
2. 如果没有，为了让这次 14 次 PDF 实验中的 Claude Opus / Haiku 请求命中缓存，是否需要提前修改代码？
3. 如果需要，请实现正确的缓存写入/命中逻辑，或明确说明当前 connector 抽象无法安全实现、需要我提供什么信息。

缓存只应针对每次完全相同的固定长前缀（例如 system prompt、完整 Codebook、固定分类规则和 JSON schema）。每个 BG 不同的 PDF/上下文数据必须作为非缓存的可变部分发送。请保持固定前缀的字节内容与结构在同一配置的连续请求中完全一致，以提高命中概率。

请不要把模型回答缓存，也不要为了缓存而改变模型实际看到的内容、分类顺序、PDF 输入或评估结果。日志中如 API 返回 token usage/cache read/cache write 信息，请记录它，便于之后核实是否命中缓存；没有该信息时也不要伪造“已命中”的结论。

## 5. 完成后请反馈

请告诉我：

- 修改/新增了哪些文件；
- 14 次 PDF 运行的准确启动命令；
- 每个模型实际使用的 model ID；
- `p3_optimized` 是从原 P5 的哪份 prompt/模板映射而来；
- Claude caching 是否已经实现、如何验证命中；
- 是否只做了脚本/单个 smoke test，还是已经真的跑完 14 次完整实验。