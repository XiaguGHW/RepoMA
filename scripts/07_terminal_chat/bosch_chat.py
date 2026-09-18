"""Interactive Bosch Farm terminal chat with local conversation and file memory.

Place beside llm_connector_with_prompt_caching.py.  It never stores the Farm key.
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import textwrap
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args, **_kwargs): pass

APP_DIR = Path(__file__).resolve().parent / ".bosch_chat"
TEXT_EXTS = {".txt", ".md", ".py", ".json", ".yaml", ".yml", ".csv", ".log", ".ini", ".toml", ".xml", ".html", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".sql"}
DIRECT_ATTACH_EXTS = {".pdf", ".png", ".jpg", ".jpeg"}
SYSTEM = "You are a careful project assistant. Use the supplied local-memory excerpts and attached files. State when evidence is insufficient. Never claim that you changed a file unless the user explicitly asked for a write operation and it was performed."


def utc_now(): return datetime.now(timezone.utc).isoformat(timespec="seconds")
def tokenise(text): return re.findall(r"[\w\-]{2,}", text.lower(), flags=re.UNICODE)

class Memory:
    def __init__(self, name: str):
        self.root = APP_DIR / name
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "session.json"
        self.db = sqlite3.connect(self.root / "knowledge.sqlite")
        self.db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(path UNINDEXED, label UNINDEXED, content)")
        self.data = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {"session_id": uuid.uuid4().hex, "history": [], "summary": "", "files": {}}

    def save(self): self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
    def add_turn(self, role, text):
        self.data["history"].append({"role": role, "text": text, "time": utc_now()}); self.save()
    def recent(self, n=8): return self.data["history"][-n:]

    def ingest(self, file_path: Path, force=False):
        path = file_path.expanduser().resolve()
        if not path.is_file(): raise FileNotFoundError(path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        key = str(path)
        if not force and self.data["files"].get(key, {}).get("sha256") == digest: return "already indexed (use /reindex PATH after updating the tool)"
        text = extract_text(path)
        self.db.execute("DELETE FROM chunks WHERE path = ?", (key,))
        count = 0
        for i in range(0, len(text), 1800):
            chunk = text[i:i + 2200].strip()
            if chunk:
                self.db.execute("INSERT INTO chunks(path, label, content) VALUES (?, ?, ?)", (key, f"{path.name}#{count + 1}", chunk)); count += 1
        self.db.commit()
        self.data["files"][key] = {"sha256": digest, "indexed_at": utc_now(), "text_chunks": count, "direct_attach": path.suffix.lower() in DIRECT_ATTACH_EXTS}
        self.save(); return f"indexed {count} text chunks"

    def search(self, question, limit=6):
        terms = " OR ".join(tokenise(question)[:12])
        if terms:
            try:
                matches = self.db.execute("SELECT path, label, snippet(chunks, 2, '[', ']', '…', 32) FROM chunks WHERE chunks MATCH ? ORDER BY bm25(chunks) LIMIT ?", (terms, limit)).fetchall()
                if matches:
                    return matches
            except sqlite3.OperationalError:
                pass
        # FTS tokenisation is weak for a natural Chinese question such as
        # "这个 Excel 有几个 sheet".  Never leave a newly added local file out
        # of the prompt merely because no exact cell text was mentioned.
        # The first chunk contains the workbook overview / document heading.
        recent_paths = list(self.data["files"])[-3:]
        fallback = []
        for path in reversed(recent_paths):
            row = self.db.execute("SELECT path, label, content FROM chunks WHERE path = ? ORDER BY rowid LIMIT 1", (path,)).fetchone()
            if row:
                fallback.append((row[0], row[1], row[2][:2200]))
        return fallback

    def attachments(self, results):
        paths = []
        for path, *_ in results:
            if self.data["files"].get(path, {}).get("direct_attach") and Path(path).exists() and path not in paths:
                paths.append(path)
        return paths[:3]


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in TEXT_EXTS:
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".pdf":
        try:
            import fitz
            doc = fitz.open(path); text = "\n".join(page.get_text() for page in doc); doc.close(); return text
        except Exception: return ""
    if suffix == ".docx":
        try:
            import zipfile
            from xml.etree import ElementTree as ET
            with zipfile.ZipFile(path) as z: root = ET.fromstring(z.read("word/document.xml"))
            return "\n".join(t.text or "" for t in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"))
        except Exception: return ""
    if suffix in {".xlsx", ".xlsm"}:
        try:
            import openpyxl
            book = openpyxl.load_workbook(path, read_only=True, data_only=False)
            sheet_names = ", ".join(sheet.title for sheet in book.worksheets)
            body = "\n".join(f"[{sheet.title}]\n" + "\n".join(" | ".join(str(v) for v in row if v is not None) for row in sheet.iter_rows(values_only=True)) for sheet in book.worksheets)
            return f"[Workbook overview: {len(book.worksheets)} sheets: {sheet_names}]\n\n{body}"
        except Exception: return ""
    return ""


def make_prompt(memory, question, results):
    sources = "\n".join(f"- {label}: {snippet}" for _, label, snippet in results) or "(No text excerpt matched; inspect attached source files if present.)"
    history = "\n".join(f"{item['role'].upper()}: {item['text']}" for item in memory.recent())
    return f"""Long-term project memory:\n{memory.data['summary'] or '(none)'}\n\nRecent conversation:\n{history or '(new session)'}\n\nRetrieved local file excerpts:\n{sources}\n\nCurrent user question:\n{question}\n\nAnswer directly. Cite source labels such as [file.py#2] when using the excerpts."""


def print_help():
    print("Commands: /add PATH | /reindex PATH | /files | /search WORDS | /summary TEXT | /model MODEL_ID | /new | /test | /quit\nAny other text is sent as a chat question.")

def main():
    parser = argparse.ArgumentParser(description="Bosch Farm terminal chat with local memory")
    parser.add_argument("--model", default=os.getenv("BOSCH_CHAT_MODEL", "gpt-5.5"))
    parser.add_argument("--session", default="default")
    parser.add_argument("--env-file", help="Path to an existing .env file with Bosch Farm credentials")
    args = parser.parse_args()
    # Load the chosen existing .env before importing the connector: it reads
    # BOSCH_FARM_BASE_URL at import time. No key is copied into this tool.
    load_dotenv(args.env_file or (Path(__file__).resolve().parent / ".env"))
    from llm_connector_with_prompt_caching import LLMConnector
    key = os.getenv("BOSCH_FARM_SUBSCRIPTION_KEY") or os.getenv("BOSCH_FARM_API_KEY")
    if not key:
        print("Missing BOSCH_FARM_SUBSCRIPTION_KEY in .env or environment.", file=sys.stderr); raise SystemExit(2)
    memory = Memory(args.session)
    llm = LLMConnector(args.model, key, session_id=memory.data["session_id"])
    print(f"Bosch Chat — model={args.model}, session={args.session}. Type /help.")
    while True:
        try: line = input("you> ").strip()
        except (EOFError, KeyboardInterrupt): print(); break
        if not line: continue
        if line in {"/quit", "/exit"}: break
        if line == "/help": print_help(); continue
        if line == "/new":
            memory = Memory("session-" + uuid.uuid4().hex[:8]); llm = LLMConnector(args.model, key, session_id=memory.data["session_id"]); print("Started a new session."); continue
        if line.startswith("/model "):
            args.model = line[7:].strip()
            if not args.model:
                print("Usage: /model MODEL_ID"); continue
            try:
                llm = LLMConnector(args.model, key, session_id=memory.data["session_id"])
                print(f"Switched to model={args.model}.")
            except ValueError as exc:
                print(f"Model not accepted: {exc}")
            continue
        if line.startswith("/add "):
            target = Path(line[5:].strip().strip('"'))
            try: print(memory.ingest(target))
            except Exception as exc: print(f"Cannot add file: {exc}")
            continue
        if line.startswith("/reindex "):
            target = Path(line[9:].strip().strip('"'))
            try: print(memory.ingest(target, force=True))
            except Exception as exc: print(f"Cannot reindex file: {exc}")
            continue
        if line == "/files":
            for path, meta in memory.data["files"].items(): print(f"- {path} ({meta['text_chunks']} chunks)")
            continue
        if line.startswith("/search "):
            for _, label, snippet in memory.search(line[8:]): print(f"[{label}] {snippet}")
            continue
        if line.startswith("/summary "):
            memory.data["summary"] = line[9:].strip(); memory.save(); print("Long-term memory saved."); continue
        question = "Reply with exactly: Bosch Farm terminal chat is connected." if line == "/test" else line
        results = memory.search(question)
        prompt = make_prompt(memory, question, results)
        print("assistant> ", end="", flush=True)
        answer = llm.ask_about_files(memory.attachments(results), prompt, SYSTEM, {"maxOutputTokens": 4096})
        print(answer)
        memory.add_turn("user", question); memory.add_turn("assistant", answer)

if __name__ == "__main__": main()

# Independent-folder usage (download this whole 07_terminal_chat folder):
# 1) In this folder, install dependencies once:
#    python -m pip install -r requirements.txt
# 2) Simplest setup: put your existing .env in this same folder, then run:
#    python bosch_chat.py --model gemini-2.5-pro --session excel_project
# 3) Alternatively, keep .env elsewhere and point to it without copying the key:
#    python bosch_chat.py --env-file "C:\\path\\to\\your_existing\\.env" --model gemini-2.5-pro --session excel_project
#    python bosch_chat.py --env-file "C:\\path\\to\\your_existing\\.env" --model claude-sonnet-5 --session excel_project
# 4) Run /test. Then add material, for example:
#    /add "C:\\path\\to\\file.xlsx"
#    /add "C:\\path\\to\\visual_sheets.pdf"
# Rebuild the local Excel index after updating this tool (your current file):
#    /reindex "C:\\Users\\wdu4fel\\Documents\\Python_Projects\\整理129BG资料\\129BG.xlsx"
# 5) Switch model without losing local memory:
#    /model gemini-2.5-flash
