# `_LLM_IGNORE` 文件夹使用说明

## 1. 目的

`run_classification.py` 会递归扫描每个 BG 文件夹，并把其中支持的 PDF 和图片发送给模型。  
如果某些旧版本、重复文件或不重要资料不需要参与分类，可以在对应 BG 文件夹内建立：

```text
_LLM_IGNORE
```

脚本修改完成后，该文件夹及其所有子文件夹中的文件仍保留在电脑上，但不会加入模型请求。

这有两个主要作用：

- 减少无关资料对分类结果的干扰；
- 减小请求体积，降低 GPT 路线出现 `413 Request Entity Too Large` 的概率。

---

## 2. 推荐的文件结构

```text
BG_DATA_ROOT/
└── 0804DT6452/
    ├── BOM.pdf
    ├── Drawing.pdf
    ├── CAD_screenshot.png
    └── _LLM_IGNORE/
        ├── old_BOM.pdf
        ├── duplicate_drawing.pdf
        └── archive/
            └── outdated_catalogue.pdf
```

上例中，模型只会收到：

- `BOM.pdf`
- `Drawing.pdf`
- `CAD_screenshot.png`

`_LLM_IGNORE` 下的三个文件都会被忽略。

---

## 3. 修改 `run_classification.py`

### 3.1 添加忽略目录配置

在 `SUPPORTED_EXTENSIONS` 附近添加：

```python
IGNORED_FOLDER_NAMES = {"_llm_ignore"}
```

这里统一使用小写名称，是因为后面的判断会调用 `casefold()`。因此以下目录名都可以被识别：

```text
_LLM_IGNORE
_llm_ignore
_Llm_Ignore
```

为了保持项目结构统一，仍建议始终使用 `_LLM_IGNORE`。

### 3.2 修改文件收集逻辑

在 `collect_all_supported_files()` 中找到原来的代码：

```python
files = sorted(
    path for path in assembly_folder.rglob("*")
    if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
)
```

替换为：

```python
supported_candidates = [
    path
    for path in assembly_folder.rglob("*")
    if path.is_file()
    and path.suffix.lower() in SUPPORTED_EXTENSIONS
]

files = sorted(
    path
    for path in supported_candidates
    if not any(
        folder_name.casefold() in IGNORED_FOLDER_NAMES
        for folder_name in path.relative_to(assembly_folder).parts[:-1]
    )
)

ignored_count = len(supported_candidates) - len(files)
```

说明：

- `rglob("*")` 仍会递归查找 BG 下的文件；
- `parts[:-1]` 只检查文件所属的目录，不检查文件名；
- 只要文件路径中的任意一层目录叫 `_LLM_IGNORE`，该文件就不会进入 `files`；
- `ignored_count` 用于记录本次忽略了多少个受支持文件。

### 3.3 修改日志输出

将原来的文件数量日志替换或补充为：

```python
logging.info(
    "%d supported files selected for BG %s; "
    "%d file(s) ignored under _LLM_IGNORE.",
    len(files),
    assembly_id,
    ignored_count,
)
```

运行时应该看到类似输出：

```text
12 supported files selected for BG 0804DT6452; 4 file(s) ignored under _LLM_IGNORE.
```

这里的 `12` 才是最终会发送给模型的文件数。

---

## 4. 使用方法

1. 在需要筛选资料的 BG 文件夹中建立 `_LLM_IGNORE`。
2. 将不希望模型读取的 PDF、PNG、JPG 或 JPEG 移入该目录。
3. 不需要在每个 BG 中都建立它；只有需要人工筛选的 BG 才需要。
4. 正常运行分类命令，例如：

```powershell
python run_classification.py --model "claude-sonnet-5" --max-rows 1
```

5. 检查终端日志中的 `selected` 和 `ignored` 数量。

---

## 5. 验证是否真的被忽略

建议第一次只选择一个 BG 进行测试：

1. 记录移动文件前日志中的文件数量。
2. 将一个受支持文件移入 `_LLM_IGNORE`。
3. 使用 `--max-rows 1` 再次运行。
4. 确认：
   - `selected` 数量减少 1；
   - `ignored` 数量增加 1；
   - 输出 Excel 的 `Files_Used` 中没有该文件路径。

如果 `Files_Used` 仍包含该文件，应检查：

- 目录名是否确实位于对应 BG 文件夹内部；
- 本地运行的是否是已经完成上述修改的 `run_classification.py`；
- 是否误将文件复制而不是移动，导致原位置仍保留另一份文件。

---

## 6. 注意事项

- 该规则只影响发送给 LLM 的文件列表，不会删除或修改任何资料。
- Excel 中 BG 的行仍然会被处理。
- 如果所有支持文件都被移入 `_LLM_IGNORE`，该 BG 会被记为“没有找到可发送的支持文件”并跳过模型调用。
- 对 GPT 模型而言，该功能能减小请求体积，但不能保证一定消除 413；PDF 转成 JPEG 后仍可能过大。
- 建议优先保留 BOM、主要技术图纸和最能反映总成结构的资料。
