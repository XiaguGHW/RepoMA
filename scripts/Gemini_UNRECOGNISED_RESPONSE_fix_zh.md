# Gemini 2.5 Pro 与 GPT-5 大量 UNRECOGNISED_RESPONSE：原因与完整修改说明

日期：2026-08-20

相关文件：

```text
scripts/run_classification.py
llm_connector.py
```

注意：`run_classification.py` 在 RepoMA 的 `scripts/` 中；实际运行所用的 `llm_connector.py` 需要与它放在同一目录。本说明只记录应修改的内容，不代表源码已经自动修改。

## 1. 实验现象

使用同一套分类脚本运行 60 个 BG：

- Claude Opus 基本没有出现输出无法识别的问题；
- Gemini 2.5 Pro 出现较多 `UNRECOGNISED_RESPONSE`；
- GPT-5 也出现较多 `UNRECOGNISED_RESPONSE`。

Gemini 2.5 Pro 的 `Raw_Model_Response` 中出现过：

```text
Multi-Achs
Kombin
(no text content, finishReason=...)
```

GPT-5 的失败行中，`Raw_Model_Response` 经常直接为空；成功行则可以正常返回：

```text
Multi-Achs-Systeme (Gantry)
Lineareinheiten
Roboter
```

对应的 `Processing_Status` 是：

```text
CHECK: response is not one valid label
```

这说明存在两种不同问题：

1. Gemini 有时返回简称、截断内容或没有最终文本；
2. GPT-5 有时没有返回可读取的最终文本。

`extract_label()` 只能验证已经取得的模型文本。当回答为空、被截断或不是允许类别的完整名称时，脚本会写入 `UNRECOGNISED_RESPONSE`。

## 2. 主要原因

当前 `run_classification.py` 使用：

```python
"maxOutputTokens": 100,
```

Gemini 2.5 Pro 和 GPT-5 都可能在产生最终答案前使用推理 token。任务还包含多份 PDF 和图片，因此 `100` 的输出预算可能先被推理过程消耗，最后造成：

- 最终类别名称没有生成；
- 类别名称只输出一部分；
- GPT-5 的 `message.content` 为空；
- Gemini 返回 `no text content`。

Claude 连接器当前没有显式开启单独的 thinking 配置，因此它更容易在较小预算下直接生成类别名称。这不能证明 Claude 的分类能力一定更强，只能说明当前参数对不同模型并不同样合适。

另外，GPT 连接器目前只读取 `message.content`，没有完整记录 `finish_reason`、`refusal` 和 token usage，因此 Excel 中只看到空白，不能直接判断是 token 用尽、内容过滤还是其他返回状态。

## 3. 修改一：将 maxOutputTokens 从 100 提高到 4096

文件：

```text
scripts/run_classification.py
```

找到：

```python
GENERATION_CONFIG = {
    "temperature": 0.0,
    "topP": 0.95,
    "candidateCount": 1,
    "maxOutputTokens": 100,
}
```

改为：

```python
GENERATION_CONFIG = {
    "temperature": 0.0,
    "topP": 0.95,
    "candidateCount": 1,
    "maxOutputTokens": 4096,
}
```

本次关键修改是：

```python
"maxOutputTokens": 100,
```

改为：

```python
"maxOutputTokens": 4096,
```

`4096` 是允许使用的最大值，不代表每个 BG 一定消耗 4096 token。模型正常输出一个短类别时，实际使用量通常会低于上限。

当前 `GENERATION_CONFIG` 是全局配置，因此 Gemini、GPT 和 Claude 都会收到对应的最大输出预算。

## 4. 修改二：加强 SYSTEM_PROMPT

文件：

```text
scripts/run_classification.py
```

找到原来的：

```python
SYSTEM_PROMPT = """Du bist ein technischer Experte für Baugruppen im Maschinen- und Anlagenbau.
Ordne jede Baugruppe genau einer vorgegebenen Funktionsklasse zu.
Nutze nur die bereitgestellte Benennung und – falls beigefügt – die technischen Dateien.
Gib ausschließlich den exakten Namen einer erlaubten Funktionsklasse aus.
Wenn die Informationen für eine belastbare Zuordnung nicht reichen, gib ausschließlich
'Nicht klassifizierbar' aus. Keine Begründung, kein Satzzeichen und kein zusätzlicher Text."""
```

替换为：

```python
SYSTEM_PROMPT = """Du bist ein technischer Experte für Baugruppen im Maschinen- und Anlagenbau.
Ordne jede Baugruppe genau einer vorgegebenen Funktionsklasse zu.
Nutze nur die bereitgestellte Benennung und – falls beigefügt – die technischen Dateien.

Gib ausschließlich einen vollständigen Klassennamen aus der vorgegebenen Liste aus.
Kopiere den Klassennamen exakt Zeichen für Zeichen aus der Liste.
Der Klassenname darf nicht abgekürzt, umformuliert, übersetzt oder ergänzt werden.

Wenn die Informationen für eine belastbare Zuordnung nicht reichen, gib ausschließlich
'Nicht klassifizierbar' aus.

Keine Begründung, kein Satzzeichen, kein Markdown und kein zusätzlicher Text."""
```

目的：

- 禁止 `Multi-Achs`、`Kombin` 等简称；
- 禁止改写、翻译或补充类别名称；
- 要求逐字复制允许列表中的完整类别名称；
- 禁止解释、Markdown 和其他额外文字。

## 5. 修改三：加强 build_question()

文件：

```text
scripts/run_classification.py
```

找到：

```python
def build_question(assembly_name: object, allowed_classes: list[str]) -> str:
    class_list = "\n".join(f"- {name}" for name in allowed_classes)
    return f"""Baugruppenbenennung: {assembly_name}

Beurteile die Baugruppenbenennung und alle beigefügten technischen Dateien.
Wähle genau eine der folgenden Funktionsklassen:
{class_list}
- Nicht klassifizierbar
"""
```

替换为：

```python
def build_question(assembly_name: object, allowed_classes: list[str]) -> str:
    class_list = "\n".join(f"- {name}" for name in allowed_classes)

    return f"""Baugruppenbenennung: {assembly_name}

Beurteile die Baugruppenbenennung und alle beigefügten technischen Dateien.

Erlaubte Funktionsklassen:
{class_list}
- Nicht klassifizierbar

Antworte mit genau einem vollständigen Klassennamen aus dieser Liste.
Kopiere ihn exakt aus der Liste.
Keine Abkürzung, keine Umformulierung und keine Erklärung.
"""
```

最重要的格式要求放在类别列表之后，让模型在生成答案前再次看到输出限制。

## 6. 修改四：GPT-5 使用 max_completion_tokens

文件：

```text
llm_connector.py
```

在 `_call_openai()` 中找到：

```python
kwargs = {
    "model": self.model_name,
    "messages": messages,
    "max_tokens": max_tokens,
    "timeout": 300,
}
if temperature is not None:
    kwargs["temperature"] = temperature
```

替换为：

```python
is_reasoning_model = self.model_name.lower().startswith(("gpt-5", "o1", "o3"))

kwargs = {
    "model": self.model_name,
    "messages": messages,
    "timeout": 300,
}

if is_reasoning_model:
    kwargs["max_completion_tokens"] = max_tokens
else:
    kwargs["max_tokens"] = max_tokens

if temperature is not None and not is_reasoning_model:
    kwargs["temperature"] = temperature
```

作用：

- GPT-5、o1、o3 使用 `max_completion_tokens`；
- GPT-4o 等普通 GPT 模型继续使用 `max_tokens`；
- 不再把通用的 `temperature=0.0` 强行发送给 GPT-5、o1、o3；
- Gemini 的 `temperature=0.0` 不受此处修改影响。

如果公司 Bosch Model Farm 的特定 GPT-5 部署明确只接受 `max_tokens`，应以该内部接口要求为准。但当前连接器应至少记录接口返回的具体错误，不能把错误静默处理为空白。

## 7. 修改五：记录 GPT-5 的空响应原因和 token usage

文件：

```text
llm_connector.py
```

在 `_call_openai()` 中找到：

```python
response = client.chat.completions.create(**kwargs)
return response.choices[0].message.content or "(no text content)"
```

替换为：

```python
response = client.chat.completions.create(**kwargs)

choice = response.choices[0]
message = choice.message
content = message.content or ""

if response.usage:
    self.last_usage = response.usage.model_dump()

logging.info(
    "OpenAI response: finish_reason=%s, refusal=%r, content=%r",
    choice.finish_reason,
    getattr(message, "refusal", None),
    content,
)

if not content.strip():
    return (
        f"(no text content, finish_reason={choice.finish_reason}, "
        f"refusal={getattr(message, 'refusal', None)})"
    )

return content
```

修改以后，GPT-5 再出现空回答时，Excel 的 `Raw_Model_Response` 不会只显示空白，而可能显示：

```text
(no text content, finish_reason=length, refusal=None)
```

常见情况的含义：

- `finish_reason=length`：输出预算可能不足；
- `finish_reason=content_filter`：返回可能受到内容过滤；
- `finish_reason=stop` 但内容为空：继续检查 Bosch 接口返回和连接器解析；
- `refusal` 有内容：模型拒绝了请求。

同时，GPT 的 token usage 会进入现有的 `Token_Usage_JSON` 列，便于后续比较成本和输出状态。

## 8. 可选诊断：在 run_classification.py 中记录原始回答

为了让日志中也能看见空字符串、空格和换行，可在以下代码后面：

```python
predicted_label = extract_label(response, allowed_classes)
```

增加：

```python
logging.info(
    "Raw response for BG %s: %r",
    assembly_id,
    response,
)
```

这里使用 `%r` 而不是 `%s`，因此：

- 空字符串会显示为 `''`；
- 只有空格的回答会显示为 `'   '`；
- 换行会显示为 `'\n'`；
- 普通类别名称会完整显示。

这一项主要用于诊断，不会改变分类结果。

## 9. 暂时不要修改 extract_label()

不要在 `extract_label()` 中加入以下类型的人工映射：

```python
"Multi-Achs" -> 某个完整类别
"Kombin" -> 某个完整类别
```

原因：这些回答不一定能够唯一对应一个正确类别。强行映射会把本来无效或不明确的输出计算为有效分类，影响不同模型实验结果的公平比较。

`extract_label()` 当前应继续负责：

1. 接受完整合法的类别名称；
2. 忽略大小写和少量格式字符；
3. 当回答不能唯一对应一个允许类别时返回 `None`；
4. 在 Excel 中记录为 `UNRECOGNISED_RESPONSE`，便于检查。

## 10. 建议实施顺序

建议按以下顺序修改和测试：

1. 将 `maxOutputTokens` 从 `100` 改为 `4096`；
2. 更新 `SYSTEM_PROMPT`；
3. 更新 `build_question()`；
4. 在 `llm_connector.py` 中为 GPT-5 使用 `max_completion_tokens`；
5. 加入 GPT 返回状态与 token usage 记录；
6. 可选加入 `run_classification.py` 的原始回答日志；
7. 先分别测试 5–10 个 BG；
8. 确认没有大量空响应后，再重新运行完整 60 个 BG。

## 11. 测试命令

Gemini 2.5 Pro：

```powershell
python .\scripts\run_classification.py --model "gemini-2.5-pro" --max-rows 5
```

GPT-5：

```powershell
python .\scripts\run_classification.py --model "gpt-5" --max-rows 5
```

如果当前终端已经位于 `scripts` 文件夹，也可以使用：

```powershell
python .\run_classification.py --model "gemini-2.5-pro" --max-rows 5
python .\run_classification.py --model "gpt-5" --max-rows 5
```

实际模型名称必须与 Bosch Model Farm 中使用的 deployment name 完全一致。

## 12. 重点检查的 Excel 列

```text
Predicted_Label
Raw_Model_Response
Processing_Status
File_Count
Token_Usage_JSON
```

判断方法：

- `Raw_Model_Response` 是完整类别且状态为 `SUCCESS`：正常；
- Gemini 返回简称：主要检查 prompt 是否已经更新；
- Gemini 返回 `finishReason=MAX_TOKENS`：继续检查输出预算；
- GPT 返回 `finish_reason=length`：继续检查输出预算；
- GPT 返回 `finish_reason=content_filter`：检查该 BG 的具体文件；
- 失败主要集中在 `File_Count` 很高的 BG：进一步检查图片数量和上下文大小；
- 相同类别有时成功、有时空白：优先检查每个 BG 的文件组合和接口返回状态，不应直接解释为模型不认识该类别。

## 13. 预期效果

这些修改主要解决：

1. GPT-5 和 Gemini 2.5 Pro 的输出预算过低；
2. Gemini 返回简称、截断内容或改写类别名称；
3. GPT-5 空回答无法诊断；
4. GPT token usage 没有被写入结果表；
5. GPT-5 使用不合适的输出参数名称；
6. 不同模型之间的参数差异没有被连接器正确处理。

这些修改不会改变：

- BG 文件夹匹配逻辑；
- PDF/图片文件收集逻辑；
- Functional Classes 的读取方式；
- `extract_label()` 的类别验证标准；
- Excel 的基本输出结构；
- Ground Truth 或后续评价方法。
