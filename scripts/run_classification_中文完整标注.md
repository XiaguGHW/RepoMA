# run_classification.py — 中文完整结构标注

对应原文件：run_classification.py（425 行）。本说明按脚本真实执行顺序分成 11 部分；每部分保留对应的完整原代码，并解释其作用。

## 总体作用

它从 Excel 读取每个 Baugruppe 的 ID、Benennung 和可选 Teamcenter ID，在数据根目录定位相应文件夹，递归收集 PDF/PNG/JPG/JPEG，调用选定 LLM 分类为允许的 Funktionsklasse，并把结果与可复查信息写入新的 Excel。

```text
启动 → 读取 .env → 解析参数 → 校验输入 → 读取 Excel/类别 → 创建 Connector
→ 对每个 BG：匹配文件夹 → 收集文件 → 构造问题 → 请求模型 → 校验回复
→ 每行 checkpoint 保存 → 输出最终 Excel 与日志
```

## ① 文件说明、模块导入与兼容性回退

导入标准库与第三方库。tqdm 和 python-dotenv 都有回退逻辑：未安装 tqdm 时仅没有进度条；未安装 python-dotenv 时仍可读取 Windows 系统环境变量，但不会读取项目 .env。此处没有导入 llm_connector，延迟导入设计见第⑧部分。

```python
"""Classify Baugruppen into functional classes with one selected LLM.

For every Baugruppe, the script recursively scans the matched document folder and
sends all supported files to the model. It does not use Priority 1 / Priority 2 or
a file inventory.

The standard files below are resolved relative to this script, so the command can
stay short. The only machine-specific setting is ``BG_DATA_ROOT`` in ``.env``.

This script requires Anja's ``llm_connector.py`` in the same folder. The connector
performs the Gemini / Claude / GPT request; this file reads experiment data, finds
BG folders, builds the classification prompt, and saves results.
"""

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
try:
    from tqdm import tqdm
except ImportError:
    # The script still works without tqdm, but no progress bar is shown.
    def tqdm(iterable, **_kwargs):
        return iterable

try:
    # python-dotenv only loads a local .env; system environment variables still work without it.
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args, **_kwargs) -> bool:
        logging.warning("python-dotenv is not installed; .env will not be loaded.")
        return False

```

## ② 默认路径、可发送格式、Excel 列名候选

PROJECT_DIR 是当前脚本所在目录，所以默认 input、outputs 不依赖终端当前文件夹。SUPPORTED_EXTENSIONS 指定仅 PDF/PNG/JPG/JPEG 会送给模型。四组 CANDIDATES 用于自动识别不同 Excel 中的常见列名；若识别失败，可通过命令行手动指定。

```python
# Default project paths. They are independent of the terminal's current folder.
PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT_EXCEL = PROJECT_DIR / "input" / "60_BG_random_no_label.xlsx"
DEFAULT_CLASSES_EXCEL = PROJECT_DIR / "input" / "Functional_classes.xlsx"
DEFAULT_OUTPUT_DIR = PROJECT_DIR / "outputs"

# File types that Anja's connector can send directly to the LLM.
SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}

# The actual spreadsheet column names can vary. They can be passed via CLI; otherwise
# the script attempts to detect one of these common names.
ID_COLUMN_CANDIDATES = (
    "Baugruppennummer", "Baugruppen-ID", "Baugruppen_ID", "BG", "ID",
    "SAP-Nummer", "SAP Nummer",
)
TEAMCENTER_COLUMN_CANDIDATES = (
    "Teamcenter ID", "Teamcenter-ID", "Teamcenter Nummer", "Teamcenter-Nummer",
    "TC ID", "TC-ID",
)
NAME_COLUMN_CANDIDATES = (
    "Benennung", "Benennung (EN)", "Baugruppenname", "Baugruppenbezeichnung",
)
CLASS_COLUMN_CANDIDATES = ("Funktionsklasse", "Functional class", "Functional_class")
```

## ③ 模型生成设置与 System Prompt

GENERATION_CONFIG 会随每次请求传给 Connector。temperature=0.0 适合只选一个类别、希望结果尽量稳定的任务。SYSTEM_PROMPT 是每一行 BG 共用的规则；当前 Benennung 和类别清单由 build_question() 另外加入。

```python
GENERATION_CONFIG = {
    "temperature": 0.0,
    "topP": 0.95,
    "candidateCount": 1,
    "maxOutputTokens": 100,
}

SYSTEM_PROMPT = """Du bist ein technischer Experte für Baugruppen im Maschinen- und Anlagenbau.
Ordne jede Baugruppe genau einer vorgegebenen Funktionsklasse zu.
Nutze nur die bereitgestellte Benennung und – falls beigefügt – die technischen Dateien.
Gib ausschließlich den exakten Namen einer erlaubten Funktionsklasse aus.
Wenn die Informationen für eine belastbare Zuordnung nicht reichen, gib ausschließlich
'Nicht klassifizierbar' aus. Keine Begründung, kein Satzzeichen und kein zusätzlicher Text."""
```

## ④ parse_args()：读取命令行参数

函数把运行命令转为 args 对象。data-root 默认值来自已读取的 BG_DATA_ROOT；传入 --data-root 时可覆盖。--max-rows 适合只测试前 N 行。四个列名参数用于自动检测无法匹配的 Excel。

```python
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify Baugruppen with an LLM and save one timestamped Excel result."
    )
    data_root_from_env = os.getenv("BG_DATA_ROOT")
    parser.add_argument("--input-excel", type=Path, default=DEFAULT_INPUT_EXCEL)
    parser.add_argument("--classes-excel", type=Path, default=DEFAULT_CLASSES_EXCEL)
    parser.add_argument("--model", default="gemini-2.5-pro")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--data-root", type=Path,
        default=Path(data_root_from_env).expanduser() if data_root_from_env else None,
        help=(
            "Absolute root folder containing all Baugruppe folders. Defaults to "
            "BG_DATA_ROOT from .env."
        ),
    )
    parser.add_argument("--max-rows", type=int, default=None,
                        help="Process only the first N input rows; useful for a pilot run.")

    # Default column detection can be overridden through CLI without editing the script.
    parser.add_argument("--id-column", default=None)
    parser.add_argument(
        "--teamcenter-column", default=None,
        help="Teamcenter ID column. Detected automatically by default; optional.",
    )
    parser.add_argument("--name-column", default=None)
    parser.add_argument("--class-column", default=None)
    return parser.parse_args()
```

## ⑤ 自动识别 Excel 列、读取允许类别

find_column() 用于必须存在的 ID、Benennung、类别列。find_optional_column() 只服务 Teamcenter ID，找不到时返回 None 而不是报错。read_classes() 读取类别表、丢弃空值、去空格、去重，同时保留 Excel 中原本的类别顺序。

```python
def find_column(df: pd.DataFrame, requested: str | None, candidates: tuple[str, ...], label: str) -> str:
    """Use an explicitly requested column or detect a common name."""
    if requested:
        if requested in df.columns:
            return requested
        raise ValueError(f"{label} column '{requested}' was not found. Available: {list(df.columns)}")

    for candidate in candidates:
        if candidate in df.columns:
            return candidate
    raise ValueError(
        f"Could not detect the {label} column. Available: {list(df.columns)}. "
        f"Pass it explicitly, for example --{label.replace('_', '-')} COLUMN_NAME."
    )


def find_optional_column(
    df: pd.DataFrame, requested: str | None, candidates: tuple[str, ...], label: str,
) -> str | None:
    """Like find_column, except a Teamcenter ID is optional."""
    if requested:
        return find_column(df, requested, candidates, label)
    return next((candidate for candidate in candidates if candidate in df.columns), None)


def read_classes(classes_path: Path, requested_column: str | None) -> list[str]:
    df = pd.read_excel(classes_path)
    class_column = find_column(df, requested_column, CLASS_COLUMN_CANDIDATES, "class_column")
    classes = [str(value).strip() for value in df[class_column].dropna() if str(value).strip()]
    classes = list(dict.fromkeys(classes))  # Preserve Excel order while removing duplicates.
    if not classes:
        raise ValueError(f"No allowed classes found in '{classes_path}'.")
    return classes
```

## ⑥ ID 标准化及 BG 文件夹匹配

normalize_identifier() 处理 Excel 数字 ID 变为 123.0 的情况，并忽略标点和大小写。文件夹匹配依次尝试：精确 SAP、精确 Teamcenter、包含完整 SAP、包含完整 Teamcenter、唯一的 Teamcenter 长片段。多个候选会产生 AMBIGUOUS 状态，绝不随意选择。assembly_id_variants() 当前定义但未调用；其处理 .0 的功能已被 normalize_identifier() 覆盖。

```python
def assembly_id_variants(value: object) -> list[str]:
    """Create possible folder names, including Excel's 123 versus 123.0 variation."""
    raw = str(value).strip()
    variants = [raw]
    try:
        number = float(raw)
        if number.is_integer():
            variants.append(str(int(number)))
    except ValueError:
        pass
    return list(dict.fromkeys(variants))


def normalize_identifier(value: object) -> str:
    """Normalize IDs for comparison by ignoring punctuation and Excel's .0 variation."""
    if pd.isna(value):
        return ""
    raw = str(value).strip()
    try:
        number = float(raw)
        if number.is_integer():
            raw = str(int(number))
    except ValueError:
        pass
    return re.sub(r"[^A-Za-z0-9]+", "", raw).casefold()


def unique_folder_match(
    folders: list[Path], predicate, status: str,
) -> tuple[Path | None, str | None]:
    """Accept only one match; multiple candidates require manual review."""
    matches = [folder for folder in folders if predicate(normalize_identifier(folder.name))]
    if len(matches) == 1:
        return matches[0], status
    if len(matches) > 1:
        return None, f"AMBIGUOUS_{status}"
    return None, None


def teamcenter_fragments(teamcenter_id: object, minimum_length: int = 6) -> list[str]:
    """Create long contiguous Teamcenter ID fragments, e.g. 12345678 -> 12345678, 1234567.

    Some folders retain only part of a Teamcenter ID. To avoid accidental matches,
    fragments shorter than six characters are excluded and matches must remain unique.
    """
    normalized = normalize_identifier(teamcenter_id)
    fragments: list[str] = []
    for length in range(len(normalized), minimum_length - 1, -1):
        for start in range(len(normalized) - length + 1):
            fragments.append(normalized[start:start + length])
    return list(dict.fromkeys(fragments))


def find_assembly_folder(
    assembly_id: object, teamcenter_id: object | None, data_root: Path,
) -> tuple[Path | None, str]:
    """Find the BG folder by reliability order and return the matching method."""
    folders = sorted(path for path in data_root.iterdir() if path.is_dir())
    sap_id = normalize_identifier(assembly_id)
    tc_id = normalize_identifier(teamcenter_id)

    # 1. An exact folder name match is the most reliable option.
    for identifier, label in ((sap_id, "EXACT_ASSEMBLY_ID"), (tc_id, "EXACT_TEAMCENTER_ID")):
        if identifier:
            folder, status = unique_folder_match(folders, lambda name, x=identifier: name == x, label)
            if folder or status:
                return folder, status

    # 2. The full ID appears in a longer folder name, e.g. BG_123456_REV_A.
    for identifier, label in ((sap_id, "CONTAINS_ASSEMBLY_ID"), (tc_id, "CONTAINS_TEAMCENTER_ID")):
        if identifier:
            folder, status = unique_folder_match(folders, lambda name, x=identifier: x in name, label)
            if folder or status:
                return folder, status

    # 3. A long Teamcenter ID fragment appears in the folder name, e.g.
    #    ABCD12345678 in Excel but only 12345678 in the folder. Matches must be unique.
    if tc_id:
        for fragment in teamcenter_fragments(tc_id):
            folder, status = unique_folder_match(
                folders, lambda name, x=fragment: x in name, "TEAMCENTER_FRAGMENT",
            )
            if folder or status:
                return folder, status

    if not sap_id and not tc_id:
        return None, "NO_IDENTIFIER"
    return None, "NOT_FOUND"
```

## ⑦ 收集附件、构造问题、校验模型回复

collect_all_supported_files() 在找到的 BG 文件夹下递归扫描支持格式。build_question() 将该行 Benennung 与允许类别清单拼成问题。extract_label() 会保留模型原文，但只返回唯一合法类别；若模型回复包含多个类别或无合法类别，则返回 None，供结果表标记 CHECK。

```python
def collect_all_supported_files(
    assembly_id: object, teamcenter_id: object | None, data_root: Path,
) -> tuple[list[str], Path | None, str]:
    """Find the BG folder and recursively collect its supported PDF/image files."""
    assembly_folder, match_status = find_assembly_folder(assembly_id, teamcenter_id, data_root)
    if not assembly_folder:
        logging.warning(
            "Folder for BG %s (Teamcenter: %s) was not found: %s",
            assembly_id, teamcenter_id, match_status,
        )
        return [], None, match_status

    files = sorted(
        path for path in assembly_folder.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    logging.info(
        "%d supported files found for BG %s in %s (%s)",
        len(files), assembly_id, assembly_folder, match_status,
    )
    return [str(path) for path in files], assembly_folder, match_status


def build_question(assembly_name: object, allowed_classes: list[str]) -> str:
    class_list = "\n".join(f"- {name}" for name in allowed_classes)
    return f"""Baugruppenbenennung: {assembly_name}

Beurteile die Baugruppenbenennung und alle beigefügten technischen Dateien.
Wähle genau eine der folgenden Funktionsklassen:
{class_list}
- Nicht klassifizierbar
"""


def extract_label(raw_response: object, allowed_classes: list[str]) -> str | None:
    """Accept one exact label while tolerating extra whitespace or Markdown backticks."""
    answer = str(raw_response).strip().strip("`").strip()
    allowed_with_fallback = allowed_classes + ["Nicht klassifizierbar"]
    exact_lookup = {name.casefold(): name for name in allowed_with_fallback}
    if answer.casefold() in exact_lookup:
        return exact_lookup[answer.casefold()]

    # If the model adds an explanation, extract only when exactly one allowed label occurs.
    matches = [name for name in allowed_with_fallback if name.casefold() in answer.casefold()]
    unique_matches = list(dict.fromkeys(matches))
    return unique_matches[0] if len(unique_matches) == 1 else None
```

## ⑧ 输出路径、延迟导入 Connector、checkpoint

make_output_path() 自动建立输出目录并生成含模型名/时间戳的文件名。create_connector() 到真正要请求模型时才导入 llm_connector.py；因此 .env 已提前加载。这里要求同目录存在名为 llm_connector.py 且定义 LLMConnector 的文件。write_checkpoint() 每行保存一次，稳定性优先于速度。

```python
def make_output_path(args: argparse.Namespace) -> Path:
    safe_model = re.sub(r"[^A-Za-z0-9_.-]+", "_", args.model)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    return args.output_dir / f"classification_all_files_{safe_model}_{timestamp}.xlsx"


def create_connector(model_name: str, api_key: str):
    """Delay the connector import so --help and Excel validation do not need it."""
    try:
        from llm_connector import LLMConnector
    except ImportError as error:
        raise ImportError(
            "llm_connector.py with class LLMConnector was not found. "
            "Place Anja's actual llm_connector.py next to run_classification.py."
        ) from error
    return LLMConnector(model_name, api_key)


def write_checkpoint(df: pd.DataFrame, output_path: Path) -> None:
    """Save after each row so completed results survive a network failure."""
    df.to_excel(output_path, index=False, engine="openpyxl")
```

## ⑨ run() 前半：检查配置、读 Excel、建立结果表

先检查 Bosch Farm key、max-rows、数据路径；再读取输入表、检测 ID/Teamcenter/Benennung 列、处理试运行行数。之后读取类别、生成输出路径、创建 Connector，最后复制输入表并初始化所有结果记录列。

```python
def run(args: argparse.Namespace) -> Path:
    if not os.getenv("BOSCH_FARM_SUBSCRIPTION_KEY"):
        raise EnvironmentError("BOSCH_FARM_SUBSCRIPTION_KEY is not set in .env or the environment.")
    if args.max_rows is not None and args.max_rows <= 0:
        raise ValueError("--max-rows must be greater than 0.")
    if args.data_root is None:
        raise EnvironmentError(
            "BG_DATA_ROOT is not set. Add an absolute path to .env, for example: "
            "BG_DATA_ROOT=C:\\path\\to\\processed_BG"
        )
    if not args.data_root.is_absolute():
        raise ValueError(
            f"--data-root must be an absolute local path, not: {args.data_root}"
        )

    input_df = pd.read_excel(args.input_excel)
    input_id_column = find_column(input_df, args.id_column, ID_COLUMN_CANDIDATES, "id_column")
    teamcenter_column = find_optional_column(
        input_df, args.teamcenter_column, TEAMCENTER_COLUMN_CANDIDATES, "teamcenter_column",
    )
    name_column = find_column(input_df, args.name_column, NAME_COLUMN_CANDIDATES, "name_column")
    if teamcenter_column:
        logging.info("Using Teamcenter ID column: %s", teamcenter_column)
    else:
        logging.warning(
            "No Teamcenter ID column detected. Folder matching will use only '%s'.",
            input_id_column,
        )
    if args.max_rows:
        input_df = input_df.head(args.max_rows).copy()

    if not args.data_root.is_dir():
        raise FileNotFoundError(f"--data-root does not exist or is not a directory: {args.data_root}")

    allowed_classes = read_classes(args.classes_excel, args.class_column)
    output_path = make_output_path(args)

    # This only creates the connector and detects its model family; no LLM request yet.
    llm = create_connector(args.model, os.environ["BOSCH_FARM_SUBSCRIPTION_KEY"])

    result_df = input_df.copy()
    for column in (
        "Predicted_Label", "Raw_Model_Response", "Processing_Status", "Files_Used",
        "File_Count", "Matched_Folder", "Folder_Match_Status", "Run_Model", "Run_Mode",
        "Run_Timestamp", "Token_Usage_JSON",
    ):
        result_df[column] = pd.NA

    run_timestamp = datetime.now().isoformat(timespec="seconds")
```

## ⑩ run() 后半：逐 BG 调模型、容错、保存

每个 ID 和 Benennung 完整且找到附件的 BG 调用一次 ask_about_files()。请求包括文件、具体问题、System Prompt 和生成参数。单个 BG 的错误会记录但不影响之后行；无论成功或失败，当前行都会写入 checkpoint Excel。

```python
    for index, row in tqdm(result_df.iterrows(), total=len(result_df), desc="Classifying"):
        assembly_id = row[input_id_column]
        teamcenter_id = row[teamcenter_column] if teamcenter_column else None
        assembly_name = row[name_column]
        if pd.isna(assembly_id) or pd.isna(assembly_name) or not str(assembly_name).strip():
            result_df.loc[index, "Processing_Status"] = "SKIPPED: missing ID or Benennung"
            write_checkpoint(result_df, output_path)
            continue

        try:
            files, matched_folder, match_status = collect_all_supported_files(
                assembly_id, teamcenter_id, args.data_root,
            )
            result_df.loc[index, "Folder_Match_Status"] = match_status
            result_df.loc[index, "Matched_Folder"] = str(matched_folder) if matched_folder else pd.NA
            if not files:
                result_df.loc[index, "Processing_Status"] = (
                    f"SKIPPED: no supported documents found ({match_status})"
                )
                result_df.loc[index, "File_Count"] = 0
                write_checkpoint(result_df, output_path)
                continue

            response = llm.ask_about_files(
                file_paths=files,
                question=build_question(assembly_name, allowed_classes),
                system_prompt=SYSTEM_PROMPT,
                generation_config=GENERATION_CONFIG,
            )
            predicted_label = extract_label(response, allowed_classes)
            result_df.loc[index, "Raw_Model_Response"] = str(response)
            result_df.loc[index, "Predicted_Label"] = predicted_label or "UNRECOGNISED_RESPONSE"
            result_df.loc[index, "Processing_Status"] = "SUCCESS" if predicted_label else "CHECK: response is not one valid label"
            result_df.loc[index, "Files_Used"] = "\n".join(files)
            result_df.loc[index, "File_Count"] = len(files)
            result_df.loc[index, "Run_Model"] = args.model
            result_df.loc[index, "Run_Mode"] = "all_files"
            result_df.loc[index, "Run_Timestamp"] = run_timestamp
            result_df.loc[index, "Token_Usage_JSON"] = json.dumps(
                llm.get_last_token_usage() or {}, ensure_ascii=False
            )
        except Exception as error:
            logging.exception("Failed to process BG %s", assembly_id)
            result_df.loc[index, "Processing_Status"] = f"ERROR: {error}"

        write_checkpoint(result_df, output_path)

    logging.info("Finished. Result saved to %s", output_path.resolve())
    return output_path
```

## ⑪ 程序入口：先 load_dotenv，再启动

这段只在直接执行脚本时运行。关键顺序是 load_dotenv → parse_args → run → create_connector → import LLMConnector；因此 Connector 导入时可读取 .env 中的 Bosch Farm 配置。日志同时显示在终端并写入 outputs/logs。启动级错误以 exit code 1 退出。

```python
if __name__ == "__main__":
    load_dotenv(PROJECT_DIR / ".env")
    arguments = parse_args()
    log_directory = arguments.output_dir / "logs"
    log_directory.mkdir(parents=True, exist_ok=True)
    log_path = log_directory / f"classification_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler()],
        force=True,
    )
    try:
        result_path = run(arguments)
        print(f"Done: {result_path.resolve()}")
    except Exception as error:
        logging.error("Classification did not start: %s", error)
        sys.exit(1)
```

## 结果 Excel 新增列说明

| 列 | 作用 |
|---|---|
| Predicted_Label | 校验后的最终分类；格式不合规时为 UNRECOGNISED_RESPONSE |
| Raw_Model_Response | 模型原始回复，便于人工复查 |
| Processing_Status | SUCCESS、SKIPPED、CHECK 或 ERROR 的原因 |
| Files_Used / File_Count | 实际发给模型的附件路径和数量 |
| Matched_Folder / Folder_Match_Status | 匹配到的 BG 文件夹和匹配方式 |
| Run_Model / Run_Mode / Run_Timestamp | 模型、实验模式和批次时间 |
| Token_Usage_JSON | Connector 提供时的 token 使用信息 |

## 关键运行关系

```text
load_dotenv(PROJECT_DIR / .env)
→ parse_args()：BG_DATA_ROOT 可作默认 data-root
→ run()：检查输入、读取 Excel
→ create_connector()：此时才 from llm_connector import LLMConnector
→ ask_about_files()：真正向模型发送每个 BG 的文件和问题
```

## 最小目录与配置

```text
项目目录/
├── run_classification.py
├── llm_connector.py          # 必须含 LLMConnector 类
├── .env                      # 不上传 GitHub
├── input/
│   ├── 60_BG_random_no_label.xlsx
│   └── Functional_classes.xlsx
└── outputs/                  # 自动创建
    └── logs/                 # 自动创建
```

.env 至少需要 BOSCH_FARM_SUBSCRIPTION_KEY 和 BG_DATA_ROOT。若 Connector 需要，另加 BOSCH_FARM_BASE_URL。真实 key 和 Bosch 内部地址都不要写入 Python 文件或公开仓库。

