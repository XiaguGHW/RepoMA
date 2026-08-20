# Gemini 2.5 Pro 出现大量 UNRECOGNISED_RESPONSE：原因与修改说明

日期：2026-08-20

相关脚本：

```text
scripts/run_classification.py
```

## 1. 现象

使用相同的 `run_classification.py`：

- Claude Opus 对 60 个 BG 进行分类时，基本没有出现输出无法识别的问题。
- Gemini 2.5 Pro 出现了较多 `UNRECOGNISED_RESPONSE`。
- Excel 中的 `Raw_Model_Response` 包含类似以下内容：

```text
Multi-Achs
Kombin
(no text content, finishReason ...)
```

对应的 `Processing_Status` 是：

```text
CHECK: response is not one valid label
```

这通常不是 BG 文件没有被模型读取，而是 Gemini 返回的文字没有严格匹配 `Functional_classes.xlsx` 中的完整类别名称，例如：

- 返回了类别简称；
- 返回内容被截断；
- 没有产生最终文本；
- 返回了不在允许列表中的改写形式。

`extract_label()` 会检查模型回答是否对应一个允许类别。检查失败时，脚本会将结果保存为 `UNRECOGNISED_RESPONSE`。

## 2. 修改位置一：提高 maxOutputTokens

在 `run_classification.py` 靠前位置找到：

```python
GENERATION_CONFIG = {
    "temperature": 0.0,
    "topP": 0.95,
    "candidateCount": 1,
    "maxOutputTokens": 100,
}
```

修改为：

```python
GENERATION_CONFIG = {
    "temperature": 0.0,
    "topP": 0.95,
    "candidateCount": 1,
    "maxOutputTokens": 1024,
}
```

本次只修改：

```python
"maxOutputTokens": 100,
```

为：

```python
"maxOutputTokens": 1024,
```

暂时不修改 `temperature`、`topP` 和 `candidateCount`。

原因：`100` 对 Gemini 2.5 Pro 可能过低。模型可能在产生最终答案前已经消耗了较多输出预算，从而导致回答被截断或出现 `no text content`。

注意：当前 `GENERATION_CONFIG` 是全局配置，因此修改后通过该脚本调用的其他模型也会收到相同的 `maxOutputTokens` 设置。

## 3. 修改位置二：加强 SYSTEM_PROMPT

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

新增要求的目的：

- 禁止使用 `Multi-Achs`、`Kombin` 等简称；
- 禁止改写或翻译类别名称；
- 要求逐字复制允许列表中的完整类别名称；
- 禁止解释、Markdown 和额外文字。

## 4. 修改位置三：加强 build_question()

找到原来的函数：

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

最重要的格式要求放在类别列表之后，使模型在生成最终答案前再次看到输出限制。

## 5. 暂时不要修改 extract_label()

暂时不要在 `extract_label()` 中加入以下类型的人工映射：

```python
"Multi-Achs" -> 某个完整类别
"Kombin" -> 某个完整类别
```

原因：这些回答不一定能够唯一对应一个正确类别。强行转换可能会把本来无效或不明确的输出计算为有效分类，从而影响不同模型实验结果的公平性。

`extract_label()` 当前的主要作用是：

1. 接受完整且合法的类别名称；
2. 忽略大小写和少量格式字符；
3. 当回答不能唯一对应一个允许类别时返回 `None`；
4. 最终在 Excel 中记录为 `UNRECOGNISED_RESPONSE`，便于检查。

## 6. 建议测试顺序

修改完成后，先只测试前 5 个 BG：

```powershell
python .\run_classification.py --model "gemini-2.5-pro" --max-rows 5
```

重点检查输出 Excel 中的三列：

```text
Predicted_Label
Raw_Model_Response
Processing_Status
```

如果 5 个 BG 不再大量出现 `UNRECOGNISED_RESPONSE`，再运行完整的 60 个 BG。

## 7. 预期效果

这些修改主要解决两类问题：

1. `maxOutputTokens` 太低导致的截断或无最终文本；
2. Gemini 没有逐字复制完整类别名称，而是返回简称或改写形式。

修改不会改变 BG 文件的收集方式、PDF/图片上传方式、类别读取方式或 Excel 输出结构。
