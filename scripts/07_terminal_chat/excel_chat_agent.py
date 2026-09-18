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
import threading
import time
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
TOOL_LABELS = {
    "discover_workbooks": "搜索目录", "open_workbook": "打开选中的文件",
    "overview": "读取工作簿概况", "sheet_preview": "读取工作表预览",
    "read_range": "读取指定单元格", "search": "搜索单元格内容",
    "trace": "检查公式引用", "plan_participants": "生成参与者修改计划",
}
QUOTED_RE = re.compile(r'["“]([^"”\n]+)["”]')
WINDOWS_PATH_RE = re.compile(r'([A-Za-z]:\\[^"“”\r\n]+)')
NAME_HINT_RE = re.compile(r'(?:名字叫|名为|叫)\s*["“]?([^"“”\s]+?)(?:的)?(?:excel|xlsx|xlsm|工作簿|表格|文件)', re.IGNORECASE)


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


class TerminalProgress:
    """Show actual stages and elapsed time, independently of model output."""

    def __init__(self, interval: float = 10.0):
        self.interval = interval
        self.output = sys.stdout
        self._lock = threading.Lock()
        self._stream_kind = None
        self._last_activity = time.monotonic()

    def _end_stream(self) -> None:
        if self._stream_kind is not None:
            print(file=self.output, flush=True)
            self._stream_kind = None

    def note(self, message: str) -> None:
        with self._lock:
            self._end_stream()
            print(f"[进度] {message}", file=self.output, flush=True)
            self._last_activity = time.monotonic()

    def chunk(self, kind: str, text: str) -> None:
        if not text:
            return
        with self._lock:
            if self._stream_kind != kind:
                self._end_stream()
                print("接口思考> " if kind == "reasoning" else "assistant> ", end="", file=self.output, flush=True)
                self._stream_kind = kind
            print(text, end="", file=self.output, flush=True)
            self._last_activity = time.monotonic()

    @contextlib.contextmanager
    def phase(self, label: str):
        self.note(label)
        started = time.monotonic()
        stopped = threading.Event()

        def heartbeat():
            while not stopped.wait(self.interval):
                with self._lock:
                    if time.monotonic() - self._last_activity < self.interval:
                        continue
                    self._end_stream()
                    elapsed = time.monotonic() - started
                    print(f"[进度] {label}，已用 {elapsed:.0f} 秒，仍在等待完成…", file=self.output, flush=True)
                    self._last_activity = time.monotonic()

        worker = threading.Thread(target=heartbeat, daemon=True)
        worker.start()
        state = "完成"
        try:
            yield
        except BaseException:
            state = "中止"
            raise
        finally:
            stopped.set()
            worker.join(timeout=0.5)
            self.note(f"{label}：{state}，{time.monotonic() - started:.1f} 秒")


def ask_with_progress(llm, prompt: str, label: str, tokens: int, args, progress: TerminalProgress,
                      *, show_answer: bool = False) -> tuple[str, bool]:
    rendered_answer = False

    def on_event(kind, text):
        nonlocal rendered_answer
        if kind == "notice":
            progress.note(text)
        elif kind == "reasoning" and args.show_reasoning:
            progress.chunk(kind, text)
        elif kind == "content" and show_answer:
            progress.chunk(kind, text)
            rendered_answer = True

    with progress.phase(label):
        answer = llm.ask_about_files(
            [], prompt, SYSTEM, {"maxOutputTokens": tokens},
            stream=args.stream or (args.show_reasoning and not args.no_stream),
            event_handler=on_event, thinking=args.thinking,
        )
        if answer.startswith(("Error:", "HTTP error", "Error after")):
            raise RuntimeError(answer)
    if args.show_reasoning and not llm.last_reasoning:
        progress.note("本次接口没有返回 reasoning_content；无法显示本次思考文本。")
    return answer, rendered_answer


class Session:
    def __init__(self, name: str):
        self.root = APP_DIR / name
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "session.json"
        self.data = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {"workbook": None, "results": None, "pending_plan": None, "discovered_files": [], "history": []}

    def save(self) -> None:
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def add(self, role: str, text: str) -> None:
        self.data["history"].append({"role": role, "text": text})
        self.data["history"] = self.data["history"][-12:]
        self.save()


class WorkbookTools:
    def __init__(self, session: Session):
        self.session = session
        self.allowed_roots: list[Path] = []

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

    def discover_workbooks(self, root: str, name_hint: str = "", purpose: str = "workbook") -> dict[str, Any]:
        folder = Path(root).expanduser().resolve()
        if not folder.is_dir():
            raise ValueError(f"该目录不存在：{folder}")
        if not self.allowed_roots:
            raise ValueError("请先在当前消息中提供需要搜索的目录路径。")
        try:
            permitted = any(os.path.commonpath([str(folder), str(allowed)]) == str(allowed) for allowed in self.allowed_roots)
        except ValueError:
            permitted = False
        if not permitted:
            raise ValueError("只能搜索你在当前消息中明确提供的目录或其子目录。")
        include_csv = purpose == "results"
        candidates = workbook_candidates(folder, name_hint, include_csv=include_csv)
        self.session.data["discovered_files"] = [str(item.resolve()) for item in candidates]
        self.session.save()
        return {"root": str(folder), "name_hint": name_hint, "purpose": purpose, "candidates": [{"path": str(item.resolve()), "name": item.name} for item in candidates[:30]], "candidate_count": len(candidates)}

    def open_workbook(self, path: str, role: str = "workbook") -> dict[str, Any]:
        candidate = Path(path).expanduser().resolve()
        known = {Path(item).resolve() for item in self.session.data.get("discovered_files", [])}
        if candidate not in known:
            raise ValueError("只能打开本轮目录搜索返回的候选文件。")
        if role == "results":
            if candidate.suffix.lower() not in {".xlsx", ".xlsm", ".csv"}:
                raise ValueError("结果文件必须是 .xlsx、.xlsm 或 .csv。")
            self.session.data["results"] = str(candidate)
            self.session.save()
            return {"opened_results_file": candidate.name, "path": str(candidate)}
        if candidate.suffix.lower() not in {".xlsx", ".xlsm"}:
            raise ValueError("工作簿必须是 .xlsx 或 .xlsm 文件。")
        book = load_book(candidate, data_only=False)
        self.session.data["workbook"] = str(candidate)
        self.session.data["pending_plan"] = None
        self.session.save()
        return {"opened_workbook": candidate.name, "path": str(candidate), "overview": worksheet_overview(book)}

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
- discover_workbooks {root: '用户本轮提供的目录', name_hint: '用户提到的文件名或关键词', purpose: 'workbook 或 results'}
- open_workbook {path: 'discover_workbooks 返回的候选完整路径', role: 'workbook 或 results'}
- overview {}
- sheet_preview {sheet: 'Sheet名称或序号', rows: 35, cols: 20}
- read_range {sheet: '名称或序号', range: 'A1:Z40'}
- search {query: '关键词', sheet: '可选'}
- trace {cell: 'Sheet!D37'}
- plan_participants {sheet, header_row, id_header, template_header, target_column, new_header, results_id_column, results_value_column}

规则：
1. 只返回一个 JSON 对象，不要 Markdown。
2. JSON 格式为 {"tool_calls":[{"name":"...","arguments":{...}}],"reply":"给用户的简短中文说明"}。
3. 每一轮普通聊天都先规划工具调用。如果用户提到要打开、读取、使用某个本地 Excel，先 discover_workbooks，随后只能 open_workbook 一个返回的候选文件；不要要求用户使用固定句式。
4. 如果尚未有精确工具证据，先调用读取工具；不要臆测单元格。
5. 绝不调用写入工具。plan_participants 只可生成待确认计划，且必须先检查相关表头、目标列和结果文件字段。
6. 每轮最多两个工具调用，优先小范围读取。
7. 工具证据足够时，返回空 tool_calls 和完整中文 reply，无需重复查询。工作簿事实应引用准确坐标；创建计划后必须提示确认执行。
8. max_row/max_column 是工作表记录范围的边界，可能因格式延伸到空白区域；不能称为实际有数据的行数或列数。"""
    return f"""你是 Excel Agent 的工具规划器。{tools}

当前会话：{json.dumps(context, ensure_ascii=False)}
此前工具结果：{json.dumps(tool_results, ensure_ascii=False)[:18000]}
用户的问题：{question}"""


def final_prompt(question: str, context: dict[str, Any], tool_results: list[dict[str, Any]]) -> str:
    return f"""请用中文直接回答用户。只能使用下方精确工具结果；涉及工作簿事实时必须引用 Sheet!A1 格式的坐标。若证据不足，说明下一步需要读取的区域。若已创建计划，要列出 Sheet、目标列、写入单元格数量，并明确提示用户输入“确认执行”才会生成新文件。max_row/max_column 仅是记录范围边界，不能当作实际有数据的行列数。

用户问题：{question}
当前会话：{json.dumps(context, ensure_ascii=False)}
精确工具结果：{json.dumps(tool_results, ensure_ascii=False)[:22000]}"""


def normalise_name(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", value.lower())


def workbook_candidates(folder: Path, hint: str = "", include_csv: bool = False) -> list[Path]:
    if not folder.is_dir():
        return []
    # Search descendants too: project folders often keep the workbook in input/
    # or another named subfolder. Limit the result list, never scan a drive root.
    choices: list[Path] = []
    patterns = ("*.xlsx", "*.xlsm", "*.csv") if include_csv else ("*.xlsx", "*.xlsm")
    for pattern in patterns:
        for item in folder.rglob(pattern):
            choices.append(item)
            if len(choices) >= 200:
                break
        if len(choices) >= 200:
            break
    choices.sort()
    key = normalise_name(hint.replace("文件", "").replace("表格", ""))
    return [item for item in choices if not key or key in normalise_name(item.stem)]


def natural_folder_and_hint(line: str) -> tuple[Path | None, str]:
    """Extract a real directory from free Chinese, not a pre-defined sentence."""
    hint_match = NAME_HINT_RE.search(line)
    hint = hint_match.group(1) if hint_match else ""
    sources = QUOTED_RE.findall(line) + WINDOWS_PATH_RE.findall(line)
    markers = ("这个路径", "该路径", "此路径", "路径里面", "里面", "文件夹中", "文件夹里", "目录中", "目录里")
    for source in sources:
        cutoff = min((source.find(marker) for marker in markers if source.find(marker) >= 0), default=len(source))
        raw_folder = source[:cutoff].rstrip("\\/ ")
        folder = Path(raw_folder).expanduser()
        if folder.is_dir():
            return folder, hint
    return None, hint


def declared_roots_from_text(line: str) -> list[Path]:
    roots: list[Path] = []
    folder, _ = natural_folder_and_hint(line)
    if folder:
        roots.append(folder.resolve())
    for raw in QUOTED_RE.findall(line) + WINDOWS_PATH_RE.findall(line):
        candidate = Path(raw).expanduser()
        if candidate.is_dir():
            roots.append(candidate.resolve())
        elif candidate.suffix.lower() in {".xlsx", ".xlsm", ".csv"} and candidate.parent.is_dir():
            # A directly named file also explicitly authorises a search of its
            # parent directory; the LLM still has to discover then select it.
            roots.append(candidate.parent.resolve())
    return list(dict.fromkeys(roots))


def main() -> None:
    parser = argparse.ArgumentParser(description="Chinese conversational Excel agent with a confirmation gate")
    parser.add_argument("--model", default=os.getenv("BOSCH_CHAT_MODEL", "gpt-5.5"))
    parser.add_argument("--session", default="excel_project")
    parser.add_argument("--env-file")
    parser.add_argument("--show-reasoning", action="store_true", help="显示接口实际返回的 reasoning_content，并默认请求流式输出")
    streaming = parser.add_mutually_exclusive_group()
    streaming.add_argument("--stream", action="store_true", help="请求流式回答（目前用于 OpenAI 格式连接器）")
    streaming.add_argument("--no-stream", action="store_true", help="使用完整响应；若带 --show-reasoning，收到后显示思考文本")
    parser.add_argument("--thinking", choices=("auto", "enabled", "disabled"), default="auto", help="DeepSeek 思考参数；auto 保留 Farm 默认设置")
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
    progress = TerminalProgress()
    print(f"Excel Chat Agent — model={args.model}, session={args.session}. 每条普通中文消息先由 LLM 规划受控工具；输入 /help 查看安全控制。")
    print(f"步骤进度已开启；显示接口思考={'开启' if args.show_reasoning else '关闭'}。", flush=True)
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
            print("assistant> 直接中文提问即可；每条普通消息都会先由 LLM 规划。首次请在消息中给出目录路径，例如：请打开这个目录里名为129BG的 Excel。可用 /model 模型ID、/status、/cancel、确认执行、/quit。")
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
                with progress.phase("执行已确认计划并校验新文件"):
                    result = tools.apply_pending()
                print(f"assistant> 已生成新文件：{result['output']}。逐格校验结果：{result['verification']['checked_cells']} 个单元格通过；原文件未修改。请用 Excel 打开新文件一次以重算公式。")
            except Exception as exc:
                print(f"assistant> 未执行写入：{exc}")
            continue
        turn_started = time.monotonic()
        llm_calls = 0
        rendered_answer = False
        answer = None
        tool_results: list[dict[str, Any]] = []
        try:
            with progress.phase("准备本地会话与工作簿概况"):
                tools.allowed_roots = declared_roots_from_text(line)
                workbook_overview = tools.overview() if session.data.get("workbook") else None
                context = {"workbook": session.data.get("workbook"), "results_file": session.data.get("results"), "pending_plan": bool(session.data.get("pending_plan")), "declared_search_roots": [str(item) for item in tools.allowed_roots], "workbook_overview": workbook_overview}
            for round_number in range(1, 4):
                llm_calls += 1
                raw, _ = ask_with_progress(llm, controller_prompt(line, context, tool_results), f"等待模型规划（第 {round_number} 轮）", 1800, args, progress)
                decision = parse_json_reply(raw)
                if not decision:
                    retry = "上一轮没有返回可执行的 JSON。请严格按要求重新规划；若涉及本地文件，必须先调用 discover_workbooks。"
                    llm_calls += 1
                    raw, _ = ask_with_progress(llm, retry + "\n\n" + controller_prompt(line, context, tool_results), "等待模型修正规划格式", 1800, args, progress)
                    decision = parse_json_reply(raw)
                if not decision:
                    tool_results.append({"tool": "planner", "result": {"error": "模型没有返回可执行的工具规划。请重试，或切换到更强模型。"}})
                    break
                calls = decision.get("tool_calls") or []
                if not isinstance(calls, list):
                    raise ValueError("模型的 tool_calls 必须是列表，本轮没有执行该规划。")
                if not calls:
                    if isinstance(decision.get("reply"), str) and decision["reply"].strip():
                        answer = decision["reply"].strip()
                    break
                for call in calls[:2]:
                    if not isinstance(call, dict) or not isinstance(call.get("arguments", {}), dict):
                        raise ValueError("模型的工具参数格式无效，本轮没有执行该调用。")
                    name, arguments = call.get("name"), call.get("arguments") or {}
                    try:
                        with progress.phase(TOOL_LABELS.get(name, "未知工具") + " " + compact(json.dumps(arguments, ensure_ascii=False), 160)):
                            if name == "discover_workbooks": result = tools.discover_workbooks(str(arguments.get("root", "")), str(arguments.get("name_hint", "")), str(arguments.get("purpose", "workbook")))
                            elif name == "open_workbook": result = tools.open_workbook(str(arguments.get("path", "")), str(arguments.get("role", "workbook")))
                            elif name == "overview": result = tools.overview()
                            elif name == "sheet_preview": result = tools.sheet_preview(str(arguments.get("sheet")), int(arguments.get("rows", 35)), int(arguments.get("cols", 20)))
                            elif name == "read_range": result = tools.read_range(str(arguments.get("sheet")), str(arguments.get("range")))
                            elif name == "search": result = tools.search(str(arguments.get("query", "")), arguments.get("sheet"))
                            elif name == "trace": result = tools.trace(str(arguments.get("cell", "")))
                            elif name == "plan_participants": result = tools.plan_participants(arguments)
                            else: result = {"error": f"不允许的工具：{name}"}
                    except Exception as exc:
                        result = {"error": str(exc)}
                    if "error" in result:
                        progress.note(f"工具返回错误：{result['error']}")
                    tool_results.append({"tool": name, "result": result})
                    if name == "open_workbook" and "opened_workbook" in result:
                        context["workbook"] = result["path"]
                        context["workbook_overview"] = result["overview"]
                    elif name == "open_workbook" and "opened_results_file" in result:
                        context["results_file"] = result["path"]
                if any(item["tool"] == "plan_participants" for item in tool_results):
                    break
            if answer is None:
                llm_calls += 1
                answer, rendered_answer = ask_with_progress(llm, final_prompt(line, context, tool_results), "等待模型整理中文回答", 2200, args, progress, show_answer=True)
        except KeyboardInterrupt:
            answer = "已中断本轮分析。"
        except Exception as exc:
            answer = f"无法完成本轮分析：{exc}"
        if not rendered_answer:
            print("assistant> " + answer, flush=True)
        progress.note(f"本轮共用 {time.monotonic() - turn_started:.1f} 秒；模型请求 {llm_calls} 次；工具结果 {len(tool_results)} 个")
        session.add("user", line); session.add("assistant", answer)


if __name__ == "__main__":
    main()

# Recommended conversational workflow (run in this standalone folder):
# 1) Install dependencies once:
#    python -m pip install -r requirements.txt
# 2) Start with your Bosch Farm model and the .env in this folder:
#    python excel_chat_agent.py --model deepseek-v4-flash-2026-04-23 --session workshop
#    python excel_chat_agent.py --model gemini-2.5-pro --session workshop
# 3) In the terminal, every normal Chinese message is first planned by the LLM.
#    The only direct commands are /help, /model, /status, /cancel, 确认执行, /quit:
#    打开 "C:\\path\\to\\workshop.xlsx"
#    打开 "C:\\path\\to\\资料目录\\这个路径里面名字叫129BG的excel文件"
#    第六个 Sheet 的表头是什么？请列出准确单元格坐标和公式关系。
#    结果文件 "C:\\path\\to\\berk_results.xlsx"
#    在 Workshop 表中按 BG-ID 添加 Berk 的判断，先给出修改计划，不要写入。
# 4) Only after reviewing the Chinese plan, type exactly:
#    确认执行
# 5) The source workbook is kept unchanged; the agent creates and verifies a new *_ai_updated.xlsx file.
# 6) Optional model switch without losing the local Excel session:
#    /model gemini-2.5-pro
# 7) 显示实际步骤与耗时：上面的普通启动命令默认已开启。
#    显示 Farm 实际返回的思考文本，同时请求流式输出：
#    python excel_chat_agent.py --model deepseek-v4-flash-2026-04-23 --session workshop --show-reasoning
#    只流式显示最终回答，不显示接口思考：
#    python excel_chat_agent.py --model deepseek-v4-flash-2026-04-23 --session workshop --stream
#    若 Farm 不支持流式，用完整响应（返回后再显示思考文本）：
#    python excel_chat_agent.py --model deepseek-v4-flash-2026-04-23 --session workshop --show-reasoning --no-stream
#    如 Farm 支持 DeepSeek 的 thinking 参数，可以明确请求启用思考：
#    python excel_chat_agent.py --model deepseek-v4-flash-2026-04-23 --session workshop --show-reasoning --thinking enabled
#    --show-reasoning 只显示接口实际返回的 reasoning_content；不会生成假的思考过程。
