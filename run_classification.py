"""
主入口：用一个指定的 LLM 模型，对一批 Baugruppe 进行 Funktionsklasse 分类。

对每个 Baugruppe，脚本会递归扫描其资料文件夹，并将所有支持的文件一起
发送给模型；不再使用 Priorität 1 / Priorität 2 或 file inventory。

运行示例（先用 20 个 BG 做测试）：
    python run_classification.py \
        --input-excel input/all_HBG_random_no_label.xlsx \
        --classes-excel input/Functional_classes.xlsx \
        --data-root "processed HBG" \
        --max-rows 20

它依赖同一文件夹内 Anja 的 llm_connector.py；该 connector 负责实际调用
Gemini / Claude / GPT。本文件只负责：读取实验数据、扫描 BG 文件夹、构建分类 Prompt、
保存结果。
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
    # 没有 tqdm 时仍可运行，只是不显示进度条。
    def tqdm(iterable, **_kwargs):
        return iterable

try:
    # python-dotenv 只用于读取本地 .env；没有安装时仍可使用已设置好的系统环境变量。
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv() -> bool:
        logging.warning("python-dotenv is not installed; .env will not be loaded.")
        return False


# 这些是 Anja 的 connector 能直接接收的文件类型。
SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}

# 文件盘点表的真实列名可能略有不同。因此可用 CLI 参数指定，也会先在这些常见名字中自动找。
ID_COLUMN_CANDIDATES = ("Baugruppennummer", "Baugruppen-ID", "Baugruppen_ID", "HBG")
NAME_COLUMN_CANDIDATES = ("Benennung", "Baugruppenname", "Baugruppenbezeichnung")
CLASS_COLUMN_CANDIDATES = ("Funktionsklasse", "Functional class", "Functional_class")

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify Baugruppen with an LLM and save one timestamped Excel result."
    )
    parser.add_argument("--input-excel", required=True, type=Path)
    parser.add_argument("--classes-excel", required=True, type=Path)
    parser.add_argument("--model", default="gemini-2.5-pro")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument(
        "--data-root", required=True, type=Path,
        help="包含各 Baugruppe 文件夹的根目录，例如 processed HBG。",
    )
    parser.add_argument("--max-rows", type=int, default=None,
                        help="只处理输入 Excel 的前 N 行，适合 20 BG pilot。")

    # 默认列名可通过命令行覆盖，不需要修改源码。
    parser.add_argument("--id-column", default=None)
    parser.add_argument("--name-column", default=None)
    parser.add_argument("--class-column", default=None)
    return parser.parse_args()


def find_column(df: pd.DataFrame, requested: str | None, candidates: tuple[str, ...], label: str) -> str:
    """找到用户指定列，或自动匹配常见列名；找不到时明确列出实际表头。"""
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


def read_classes(classes_path: Path, requested_column: str | None) -> list[str]:
    df = pd.read_excel(classes_path)
    class_column = find_column(df, requested_column, CLASS_COLUMN_CANDIDATES, "class_column")
    classes = [str(value).strip() for value in df[class_column].dropna() if str(value).strip()]
    classes = list(dict.fromkeys(classes))  # 保留 Excel 中的顺序，同时去除重复项。
    if not classes:
        raise ValueError(f"No allowed classes found in '{classes_path}'.")
    return classes


def assembly_id_variants(value: object) -> list[str]:
    """生成可能的文件夹名，兼容 Excel 将 123 读成 123.0 的情况。"""
    raw = str(value).strip()
    variants = [raw]
    try:
        number = float(raw)
        if number.is_integer():
            variants.append(str(int(number)))
    except ValueError:
        pass
    return list(dict.fromkeys(variants))


def collect_all_supported_files(assembly_id: object, data_root: Path) -> list[str]:
    """递归收集一个 BG 文件夹下所有可由 connector 输入的 PDF/图片文件。"""
    for folder_name in assembly_id_variants(assembly_id):
        assembly_folder = data_root / folder_name
        if assembly_folder.is_dir():
            files = sorted(
                path for path in assembly_folder.rglob("*")
                if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
            )
            logging.info(
                "%d supported files found for BG %s in %s",
                len(files), assembly_id, assembly_folder,
            )
            return [str(path) for path in files]

    logging.warning("Folder for BG %s was not found below %s", assembly_id, data_root)
    return []


def build_question(assembly_name: object, allowed_classes: list[str]) -> str:
    class_list = "\n".join(f"- {name}" for name in allowed_classes)
    return f"""Baugruppenbenennung: {assembly_name}

Beurteile die Baugruppenbenennung und alle beigefügten technischen Dateien.
Wähle genau eine der folgenden Funktionsklassen:
{class_list}
- Nicht klassifizierbar
"""


def extract_label(raw_response: object, allowed_classes: list[str]) -> str | None:
    """仅接受一个确切标签；容忍模型偶尔输出的空格或 Markdown 代码框。"""
    answer = str(raw_response).strip().strip("`").strip()
    allowed_with_fallback = allowed_classes + ["Nicht klassifizierbar"]
    exact_lookup = {name.casefold(): name for name in allowed_with_fallback}
    if answer.casefold() in exact_lookup:
        return exact_lookup[answer.casefold()]

    # 如果模型无意中多加了一行说明，只在整段文字中恰好出现一个允许标签时才提取，避免猜测。
    matches = [name for name in allowed_with_fallback if name.casefold() in answer.casefold()]
    unique_matches = list(dict.fromkeys(matches))
    return unique_matches[0] if len(unique_matches) == 1 else None


def make_output_path(args: argparse.Namespace) -> Path:
    safe_model = re.sub(r"[^A-Za-z0-9_.-]+", "_", args.model)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    return args.output_dir / f"classification_all_files_{safe_model}_{timestamp}.xlsx"


def create_connector(model_name: str, api_key: str):
    """延迟导入连接器，使 --help 和 Excel 参数检查不依赖公司连接器文件。"""
    try:
        from llm_connector import LLMConnector
    except ImportError as error:
        raise ImportError(
            "llm_connector.py with class LLMConnector was not found. "
            "Place Anja's actual llm_connector.py next to run_classification.py."
        ) from error
    return LLMConnector(model_name, api_key)


def write_checkpoint(df: pd.DataFrame, output_path: Path) -> None:
    """每处理一行都保存一次；中途网络失败时，已完成的结果也不会丢失。"""
    df.to_excel(output_path, index=False, engine="openpyxl")


def run(args: argparse.Namespace) -> Path:
    if not os.getenv("BOSCH_FARM_SUBSCRIPTION_KEY"):
        raise EnvironmentError("BOSCH_FARM_SUBSCRIPTION_KEY is not set in .env or the environment.")
    if args.max_rows is not None and args.max_rows <= 0:
        raise ValueError("--max-rows must be greater than 0.")

    input_df = pd.read_excel(args.input_excel)
    input_id_column = find_column(input_df, args.id_column, ID_COLUMN_CANDIDATES, "id_column")
    name_column = find_column(input_df, args.name_column, NAME_COLUMN_CANDIDATES, "name_column")
    if args.max_rows:
        input_df = input_df.head(args.max_rows).copy()

    if not args.data_root.is_dir():
        raise FileNotFoundError(f"--data-root does not exist or is not a directory: {args.data_root}")

    allowed_classes = read_classes(args.classes_excel, args.class_column)
    output_path = make_output_path(args)

    # 这一步只创建 connector 并识别模型家族；还没有真正请求 LLM。
    llm = create_connector(args.model, os.environ["BOSCH_FARM_SUBSCRIPTION_KEY"])

    result_df = input_df.copy()
    for column in (
        "Predicted_Label", "Raw_Model_Response", "Processing_Status", "Files_Used",
        "File_Count", "Run_Model", "Run_Mode", "Run_Timestamp", "Token_Usage_JSON",
    ):
        result_df[column] = pd.NA

    run_timestamp = datetime.now().isoformat(timespec="seconds")
    for index, row in tqdm(result_df.iterrows(), total=len(result_df), desc="Classifying"):
        assembly_id = row[input_id_column]
        assembly_name = row[name_column]
        if pd.isna(assembly_id) or pd.isna(assembly_name) or not str(assembly_name).strip():
            result_df.loc[index, "Processing_Status"] = "SKIPPED: missing ID or Benennung"
            write_checkpoint(result_df, output_path)
            continue

        try:
            files = collect_all_supported_files(assembly_id, args.data_root)
            if not files:
                result_df.loc[index, "Processing_Status"] = "SKIPPED: no supported documents found"
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


if __name__ == "__main__":
    load_dotenv()
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
