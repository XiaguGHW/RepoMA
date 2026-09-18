"""Chinese conversational Excel agent with exact, locally controlled workbook tools.

The LLM may inspect data through a small allow-list of tools.  It never receives
permission to write a workbook directly: it can only create a reviewable plan;
the user must type "确认执行" before a new output workbook is produced.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from openpyxl.utils.cell import range_boundaries

from excel_agent import (
    command_apply,
    command_plan_participants,
    formula_references,
    load_book,
    resolve_sheet,
    verify_plan,
    worksheet_overview,
)

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args, **_kwargs):
        return False


APP_DIR = Path(__file__).resolve().parent / ".excel_chat_agent"
SYSTEM = "你是一个谨慎的 Excel 助手。始终用中文回答。只能依据本地精确工具返回的单元格、公式和计划；不得猜测单元格位置或文件内容。写入前必须清楚展示计划并等待用户输入‘确认执行’。"
PATH_RE = re.compile(r'["“]([^"”\n]+?\.(?:xlsx|xlsm))["”]', re.IGNORECASE)


def compact(value: Any, length: int = 220) -> str:
    text = "" if value is None else str(value)
    return text if len(text) <= length else text[: length - 1] + "…"


def parse_json_reply(text: str) -> dict[str, Any] | None:
    cleaned = text.strip().replace("```json", "").replace("```", "")
    decoder = json.JSONDecoder()
    for offset, char in enumerate(cleaned):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(cleaned[offset:])
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            pass
    return None


class Session:
    def __init__(self, name: str):
        self.root = APP_DIR / name
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "session.json"
        self.data = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {"workbook": None, "results": None, "pending_plan": None, "history": []}

    def save(self) -> None:
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def add(self, role: str, text: str) -> None:
        self.data["history"].append({"role": role, "text": text})
        self.data["history"] = self.data["history"][-12:]
        self.save()


class WorkbookTools:
    def __init__(self, session: Session):
        self.session = session

    @property
    def path(self) -> Path:
        raw = self.session.data.get("workbook")
        if not raw:
            raise ValueError("尚未打开工作簿。请先输入：打开 \"C:\\路径\\文件.xlsx\"")
        path = Path(raw)
        if not path.is_file():
            raise ValueError(f"当前工作簿已不存在：{path}")
        return path

    def book(self):
        return load_book(self.path, data_only=False)

    def overview(self) -> dict[str, Any]:
        return worksheet_overview(self.book())

    def sheet_preview(self, selector: str, rows: int = 35, cols: int = 20) -> dict[str, Any]:
        book = self.book()
        sheet = resolve_sheet(book, str(selector))
        cells = []
        for row in sheet.iter_rows(min_row=1, max_row=min(rows, sheet.max_row), max_col=min(cols, sheet.max_column)):
            for cell in row:
                if cell.value is not None:
                    cells.append({"cell": f"{sheet.title}!{cell.coordinate}", "value": compact(cell.value), "formula": cell.value if isinstance(cell.value, str) and cell.value.startswith("=") else None})
        return {"sheet": sheet.title, "dimensions": sheet.calculate_dimension(), "preview": f"A1:{sheet.cell(min(rows, sheet.max_row), min(cols, sheet.max_column)).coordinate}", "cells": cells}

    def read_range(self, selector: str, address: str) -> dict[str, Any]:
        book = self.book()
        sheet = resolve_sheet(book, str(selector))
        try:
            min_col, min_row, max_col, max_row = range_boundaries(address)
        except ValueError as exc:
            raise ValueError(f"无效单元格区域：{exc}") from exc
        if (max_col - min_col + 1) * (max_row - min_row + 1) > 500:
            raise ValueError("一次最多读取 500 个单元格。请缩小区域。")
        cells = []
        for row in sheet.iter_rows(min_row=min_row, max_row=max_row, min_col=min_col, max_col=max_col):
            for cell in row:
                cells.append({"cell": f"{sheet.title}!{cell.coordinate}", "value": compact(cell.value), "formula": cell.value if isinstance(cell.value, str) and cell.value.startswith("=") else None})
        return {"sheet": sheet.title, "range": address, "cells": cells}

    def trace(self, qualified_cell: str) -> dict[str, Any]:
        if "!" not in qualified_cell:
            raise ValueError("公式追踪必须使用 Sheet!A1，例如 Workshop!D37。")
        sheet_name, address = qualified_cell.rsplit("!", 1)
        book = self.book()
        sheet = resolve_sheet(book, sheet_name)
        value = sheet[address].value
        if not isinstance(value, str) or not value.startswith("="):
            return {"cell": qualified_cell, "value": value, "formula": None, "references": []}
        refs, warnings = formula_references(value, sheet.title)
        return {"cell": qualified_cell, "formula": value, "references": refs, "warnings": warnings}

    def search(self, query: str, selector: str | None = None, limit: int = 40) -> dict[str, Any]:
        query = query.strip().lower()
        if len(query) < 2:
            raise ValueError("搜索词至少需要两个字符。")
        book = self.book()
        sheets = [resolve_sheet(book, str(selector))] if selector else book.worksheets
        matches = []
        for sheet in sheets:
            for row in sheet.iter_rows():
                for cell in row:
                    if cell.value is not None and query in str(cell.value).lower():
                        matches.append({"cell": f"{sheet.title}!{cell.coordinate}", "value": compact(cell.value), "formula": cell.value if isinstance(cell.value, str) and cell.value.startswith("=") else None})
                        if len(matches) >= limit:
                            return {"query": query, "matches": matches, "truncated": True}
        return {"query": query, "matches": matches, "truncated": False}

    def plan_participants(self, payload: dict[str, Any]) -> dict[str, Any]:
        results = self.session.data.get("results")
        if not results:
            raise ValueError("还没有参与者结果文件。请先输入：结果文件 \"C:\\路径\\results.xlsx\"")
        required = ["sheet", "header_row", "id_header", "template_header", "target_column", "new_header", "results_id_column", "results_value_column"]
        missing = [key for key in required if not payload.get(key)]
        if missing:
            raise ValueError("模型尚不能安全确定这些字段：" + ", ".join(missing))
        plan_path = self.session.root / f"pending_plan_{uuid.uuid4().hex[:8]}.json"
        args = SimpleNamespace(
            workbook=str(self.path), results=str(results), plan=str(plan_path), force=False,
            sheet=str(payload["sheet"]), header_row=int(payload["header_row"]), id_header=str(payload["id_header"]),
            template_header=str(payload["template_header"]), target_column=str(payload["target_column"]), new_header=str(payload["new_header"]),
            results_id_column=str(payload["results_id_column"]), results_value_column=str(payload["results_value_column"]),
        )
        with contextlib.redirect_stdout(io.StringIO()):
            command_plan_participants(args)
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        self.session.data["pending_plan"] = str(plan_path)
        self.session.save()
        return {"plan_created": True, "plan": str(plan_path), "operation": plan["operation"], "sheet": plan["sheet"], "target_column": plan["target_column"], "new_header": payload["new_header"], "edit_count": len(plan["edits"]), "preflight": plan["preflight"], "confirmation_required": "确认执行"}

    def apply_pending(self) -> dict[str, Any]:
        raw = self.session.data.get("pending_plan")
        if not raw or not Path(raw).is_file():
            raise ValueError("没有待执行计划。请先让助手生成计划。")
        plan_path = Path(raw)
        suffix = self.path.suffix
        output = self.path.with_name(f"{self.path.stem}_ai_updated_{datetime.now().strftime('%Y%m%d_%H%M%S')}{suffix}")
        args = SimpleNamespace(workbook=str(self.path), plan=str(plan_path), output=str(output), force=False)
        with contextlib.redirect_stdout(io.StringIO()):
            command_apply(args)
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        verification = verify_plan(output, plan)
        self.session.data["pending_plan"] = None
        self.session.save()
        return {"output": str(output), "verification": verification, "source_unchanged": True}


def controller_prompt(question: str, context: dict[str, Any], tool_results: list[dict[str, Any]]) -> str:
    tools = """可调用工具：
- overview {}
- sheet_preview {sheet: 'Sheet名称或序号', rows: 35, cols: 20}
- read_range {sheet: '名称或序号', range: 'A1:Z40'}
- search {query: '关键词', sheet: '可选'}
- trace {cell: 'Sheet!D37'}
- plan_participants {sheet, header_row, id_header, template_header, target_column, new_header, results_id_column, results_value_column}

规则：
1. 只返回一个 JSON 对象，不要 Markdown。
2. JSON 格式为 {"tool_calls":[{"name":"...","arguments":{...}}],"reply":"给用户的简短中文说明"}。
3. 如果尚未有精确工具证据，先调用读取工具；不要臆测单元格。
4. 绝不调用写入工具。plan_participants 只可生成待确认计划，且必须先检查相关表头、目标列和结果文件字段。
5. 每轮最多两个工具调用，优先小范围读取。"""
    return f"""你是 Excel Agent 的工具规划器。{tools}

当前会话：{json.dumps(context, ensure_ascii=False)}
此前工具结果：{json.dumps(tool_results, ensure_ascii=False)[:18000]}
用户的问题：{question}"""


def final_prompt(question: str, context: dict[str, Any], tool_results: list[dict[str, Any]]) -> str:
    return f"""请用中文直接回答用户。只能使用下方精确工具结果；涉及工作簿事实时必须引用 Sheet!A1 格式的坐标。若证据不足，说明下一步需要读取的区域。若已创建计划，要列出 Sheet、目标列、写入单元格数量，并明确提示用户输入“确认执行”才会生成新文件。

用户问题：{question}
当前会话：{json.dumps(context, ensure_ascii=False)}
精确工具结果：{json.dumps(tool_results, ensure_ascii=False)[:22000]}"""


def open_from_text(line: str, session: Session, kind: str) -> bool:
    match = PATH_RE.search(line)
    if not match:
        return False
    path = Path(match.group(1)).expanduser().resolve()
    if not path.is_file():
        print(f"assistant> 找不到文件：{path}")
        return True
    if kind == "results":
        session.data["results"] = str(path)
        session.save()
        print(f"assistant> 已设置参与者结果文件：{path.name}。现在可直接用中文说明要新增哪位参与者的判断。")
    else:
        book = load_book(path, data_only=False)
        session.data["workbook"] = str(path)
        session.data["pending_plan"] = None
        session.save()
        overview = worksheet_overview(book)
        names = "、".join(f"{item['number']}.{item['name']}" for item in overview["sheets"])
        print(f"assistant> 已打开 {path.name}，共 {overview['sheet_count']} 个 Sheet：{names}。现在可以直接中文提问。")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Chinese conversational Excel agent with a confirmation gate")
    parser.add_argument("--model", default=os.getenv("BOSCH_CHAT_MODEL", "gpt-5.5"))
    parser.add_argument("--session", default="excel_project")
    parser.add_argument("--env-file")
    args = parser.parse_args()
    load_dotenv(args.env_file or (Path(__file__).resolve().parent / ".env"))
    from llm_connector_with_prompt_caching import LLMConnector
    key = os.getenv("BOSCH_FARM_SUBSCRIPTION_KEY") or os.getenv("BOSCH_FARM_API_KEY")
    if not key:
        print("Missing BOSCH_FARM_SUBSCRIPTION_KEY in .env or environment.", file=sys.stderr)
        raise SystemExit(2)
    session = Session(args.session)
    tools = WorkbookTools(session)
    farm_session_id = uuid.uuid4().hex
    llm = LLMConnector(args.model, key, session_id=farm_session_id)
    print(f"Excel Chat Agent — model={args.model}, session={args.session}. 用中文说‘打开 \\\"C:\\\\文件.xlsx\\\"’，或输入 /help。")
    while True:
        try:
            line = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print(); break
        if not line:
            continue
        if line in {"/quit", "/exit"}:
            break
        if line == "/help":
            print("assistant> 直接中文提问即可。首次输入：打开 \"C:\\路径\\工作簿.xlsx\"。参与者结果输入：结果文件 \"C:\\路径\\results.xlsx\"。可用 /model 模型ID、/status、/cancel、确认执行、/quit。")
            continue
        if line.startswith("/model "):
            requested_model = line[7:].strip()
            if not requested_model:
                print("assistant> 用法：/model 模型ID")
                continue
            args.model = requested_model
            llm = LLMConnector(args.model, key, session_id=farm_session_id)
            print(f"assistant> 已切换到模型：{args.model}。本地工作簿、结果文件和待确认计划均保留。")
            continue
        if line == "/status":
            print("assistant> " + json.dumps({"workbook": session.data.get("workbook"), "results": session.data.get("results"), "pending_plan": session.data.get("pending_plan")}, ensure_ascii=False))
            continue
        if line == "/cancel":
            session.data["pending_plan"] = None; session.save(); print("assistant> 已取消待执行计划，原 Excel 未被修改。"); continue
        if line in {"确认执行", "/confirm"}:
            try:
                result = tools.apply_pending()
                print(f"assistant> 已生成新文件：{result['output']}。逐格校验结果：{result['verification']['checked_cells']} 个单元格通过；原文件未修改。请用 Excel 打开新文件一次以重算公式。")
            except Exception as exc:
                print(f"assistant> 未执行写入：{exc}")
            continue
        lowered = line.lower()
        if lowered.startswith("打开") or lowered.startswith("open ") or lowered.startswith("/open "):
            if not open_from_text(line, session, "workbook"):
                print("assistant> 请写成：打开 \"C:\\路径\\工作簿.xlsx\"")
            continue
        if "结果文件" in line or lowered.startswith("/results "):
            if not open_from_text(line, session, "results"):
                print("assistant> 请写成：结果文件 \"C:\\路径\\参与者结果.xlsx\"")
            continue
        if not session.data.get("workbook"):
            print("assistant> 请先输入：打开 \"C:\\路径\\工作簿.xlsx\"")
            continue
        context = {"workbook": session.data.get("workbook"), "results_file": session.data.get("results"), "pending_plan": bool(session.data.get("pending_plan")), "workbook_overview": tools.overview()}
        tool_results: list[dict[str, Any]] = []
        try:
            for _ in range(3):
                raw = llm.ask_about_files([], controller_prompt(line, context, tool_results), SYSTEM, {"maxOutputTokens": 1800})
                decision = parse_json_reply(raw)
                if not decision:
                    break
                calls = decision.get("tool_calls") or []
                if not calls:
                    break
                for call in calls[:2]:
                    name, arguments = call.get("name"), call.get("arguments") or {}
                    try:
                        if name == "overview": result = tools.overview()
                        elif name == "sheet_preview": result = tools.sheet_preview(str(arguments.get("sheet")), int(arguments.get("rows", 35)), int(arguments.get("cols", 20)))
                        elif name == "read_range": result = tools.read_range(str(arguments.get("sheet")), str(arguments.get("range")))
                        elif name == "search": result = tools.search(str(arguments.get("query", "")), arguments.get("sheet"))
                        elif name == "trace": result = tools.trace(str(arguments.get("cell", "")))
                        elif name == "plan_participants": result = tools.plan_participants(arguments)
                        else: result = {"error": f"不允许的工具：{name}"}
                    except Exception as exc:
                        result = {"error": str(exc)}
                    tool_results.append({"tool": name, "result": result})
                if any(item["tool"] == "plan_participants" for item in tool_results):
                    break
            answer = llm.ask_about_files([], final_prompt(line, context, tool_results), SYSTEM, {"maxOutputTokens": 2200})
        except Exception as exc:
            answer = f"无法完成本轮分析：{exc}"
        print("assistant> " + answer)
        session.add("user", line); session.add("assistant", answer)


if __name__ == "__main__":
    main()

# Recommended conversational workflow (run in this standalone folder):
# 1) Install dependencies once:
#    python -m pip install -r requirements.txt
# 2) Start with your Bosch Farm model and the .env in this folder:
#    python excel_chat_agent.py --model deepseek-v4-flash-2026-04-23 --session workshop
#    python excel_chat_agent.py --model gemini-2.5-pro --session workshop
# 3) In the terminal, talk naturally in Chinese:
#    打开 "C:\\path\\to\\workshop.xlsx"
#    第六个 Sheet 的表头是什么？请列出准确单元格坐标和公式关系。
#    结果文件 "C:\\path\\to\\berk_results.xlsx"
#    在 Workshop 表中按 BG-ID 添加 Berk 的判断，先给出修改计划，不要写入。
# 4) Only after reviewing the Chinese plan, type exactly:
#    确认执行
# 5) The source workbook is kept unchanged; the agent creates and verifies a new *_ai_updated.xlsx file.
# 6) Optional model switch without losing the local Excel session:
#    /model gemini-2.5-pro
