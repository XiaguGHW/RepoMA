# Bosch Farm Workbench and Terminal Chat

The downloadable `local_llm_chat_bot.zip` contains only the graphical
Workbench (files listed in `PACKAGE_MANIFEST.txt`; see `WORKBENCH_README.md`).
The terminal and Excel tools described below are available in this repository
folder.

Download the complete `local_llm_chat_bot` folder anywhere on your Bosch computer.
Use Python 3.10 or newer and keep the complete folder together, including all
Python/JSON files and requirements.txt. The graphical workbench also needs
chat_workbench.py, workbench_startup.py, workbench_i18n.py/workbench_i18n.json,
request_runtime.py, release_safety.py, code_chat_agent.py and
local_document_library.py. The terminal/Excel entry points include:

- `llm_connector_with_prompt_caching.py`
- `bosch_chat.py`
- `excel_agent.py` — precise Excel inspection and safe writing tool
- `excel_chat_agent.py` — recommended Chinese conversational Excel agent

## Recommended Bosch-computer setup and later updates

This downloads only this folder, while preserving the normal `git pull` update
workflow. In VS Code's PowerShell terminal, run these commands once:

```powershell
cd $env:USERPROFILE\Documents
git clone --filter=blob:none --no-checkout https://github.com/XiaguGHW/RepoMA.git BoschTools
cd .\BoschTools
git sparse-checkout init --cone
git sparse-checkout set local_llm_chat_bot
git checkout main
```

The resulting structure is deliberately short:

```text
Documents
└── BoschTools
    └── local_llm_chat_bot
```

For every later update, run only:

```powershell
cd $env:USERPROFILE\Documents\BoschTools
git pull
```

Then start the graphical workbench:

```powershell
cd .\local_llm_chat_bot
python -m pip install -r requirements.txt
python .\chat_workbench.py
```

### One-click start (no VS Code needed)

After the packages are installed once, double-click `start_workbench.bat` in
the `local_llm_chat_bot` folder. It starts the Workbench, opens
`http://127.0.0.1:8765` in the default browser and reopens the last workspace,
model and language. Keep the black window open; closing it stops the
Workbench. Double-clicking again while it runs only opens the browser page.

For a desktop icon: right-click `start_workbench.bat` → *Send to* → *Desktop
(create shortcut)*. To always open a specific folder, edit the shortcut's
target and append `--workspace "C:\path\to\folder"`. Other flags: `--port`,
`--env-file`, `--no-browser`.

The launcher finds a Python that has the Workbench packages by itself, in this
order: `WORKBENCH_PYTHON` (a full path to `python.exe`), the Python used last
time, a `.venv` next to or above the folder, `python` on PATH, every conda
environment registered in `%USERPROFILE%\.conda\environments.txt`, the usual
Anaconda/Miniconda/Miniforge folders, then `py -3`. A conda environment is used
directly — no `conda activate` needed. The choice is remembered in
`AI_Bot_State\python_path.txt`. If nothing suitable exists, the window offers to
create a private `.venv` in the folder and install `requirements.txt` once.

Put your existing Farm `.env` file in this downloaded tool folder (or provide
its location with `--env-file`). Do not put its secret into any Python file:

```dotenv
BOSCH_FARM_SUBSCRIPTION_KEY=...
# Optional if your Farm base URL differs from the connector default:
BOSCH_FARM_BASE_URL=https://aoai-farm.bosch-temp.com/api
```

### GUI startup, configuration and recovery

The GUI listens only on `127.0.0.1`, on port `8765` by default. Its default `.env`
and `AI_Bot_State` are resolved beside the program, independently of the current
terminal directory or selected workspace/BG. It never creates a default `.env`
or state directory in a selected BG source folder.

For example, from another directory in PowerShell, using the
`Documents\Python_Projects\BoschTools` layout:

```powershell
python "$env:USERPROFILE\Documents\Python_Projects\BoschTools\local_llm_chat_bot\chat_workbench.py" `
  --env-file "C:\path with spaces\Farm ü.env" `
  --port 8877
# Open http://127.0.0.1:8877
```

`--env-file` selects an existing UTF-8 file (a UTF-8 BOM is supported). Relative
paths use the launch directory; the default always uses the program directory.
An explicitly selected missing/unreadable file fails with recovery instructions,
even if an environment key exists. Existing process environment variables take
precedence over dotenv values. On a successful config-file change, values loaded
from the previous file are replaced; failed changes restore the previous runtime
environment and active session. No key is printed, returned by the GUI or saved
in session/settings files. Keep keys in the config file or process environment,
never in command arguments.

The configuration file actually used (default `.env`, or the `--env-file`
path) and any file named `*.env`/`.env*` are never readable, diffable or
writable by the model, even when they lie inside the selected workspace. The
active Farm key is also replaced with `[redacted]` in every prompt, streamed
preview, answer, change plan and saved conversation, if it appears in any file.

The GUI does not need an env-file picker. Setup, model tests and diagnostics use
the selected application config. After editing that file, reopen the workspace
to apply it to the active connector; diagnostics/model probes can inspect the
updated file without changing an existing session. For API callers only, a
nonempty `/api/setup` `env_file` overrides the application file for successful
setup; later empty values retain it until restart. Pass the CLI flag again on
restart when using a custom file. GUI `state_dir` overrides are rejected;
application state remains beside the program.

Run `python .\chat_workbench.py --help` for supported flags. Unknown options,
invalid ports and `--host` are rejected, rather than silently starting a server.
Help/argument validation works even before dependencies are installed.

| Failure | Recovery |
|---|---|
| Python/dependency missing or broken | Select Python 3.10+, then install requirements.txt with that interpreter. The error prints a command using its exact executable (PowerShell syntax on Windows). Keep the complete downloaded folder together. |
| Config missing/unreadable or no Farm key | Create/fix the selected UTF-8 env file with BOSCH_FARM_SUBSCRIPTION_KEY or BOSCH_FARM_API_KEY, then retry/restart with the same `--env-file`. A default missing .env is allowed when a process environment key exists. |
| Invalid Farm URL | Set BOSCH_FARM_BASE_URL to an HTTP(S) URL without embedded username/password. |
| State directory/file locked or not writable | Check permissions, available space and file locks. If necessary, close Workbench and move the complete program folder to a writable location before restarting. Do not put state in a BG source folder. |
| Port already in use | If it is an existing Workbench instance, open its local URL. Otherwise choose another port, for example `--port 8877`. A different service on that port is not a Workbench instance. |

### Request time limits and Stop

Model calls are bounded so a stalled request cannot block the workbench, but the
defaults leave room for real multimodal work. Override any value in the same
`.env` file (or the process environment) and restart:

| Variable | Default | Allowed | Meaning |
|---|---:|---:|---|
| `WORKBENCH_RESPONSE_TIMEOUT_SECONDS` | 300 | 0.05–3600 | Wait for one complete response. Gemini/Claude send nothing until they finish generating. |
| `WORKBENCH_READ_TIMEOUT_SECONDS` | 60 | 0.05–600 | Maximum silence between chunks of a streamed response. |
| `WORKBENCH_REQUEST_TIMEOUT_SECONDS` | 3600 | 0.1–14400 | Whole user operation, e.g. all Codebook pages plus merge, or all material summaries plus the answer. |
| `WORKBENCH_CONNECT_TIMEOUT_SECONDS` | 15 | 0.05–60 | TCP/TLS connection and proxy tunnel setup. A timeout here means the request was never sent, so it is retried. |
| `WORKBENCH_MAX_ATTEMPTS` | 3 | 1–3 | Attempts for connection failures and HTTP 429/5xx. |
| `WORKBENCH_RETRY_BACKOFF_SECONDS` | 1 | 0–5 | First retry delay (doubles per retry). |

A response that exceeds `WORKBENCH_RESPONSE_TIMEOUT_SECONDS` is reported, and is
never sent again automatically, because the provider may still be generating
and billing it. Increase the value if a model regularly needs longer. The Stop
button also stops Codebook preparation, material pre-reading, model comparison
and dossier rebuilding. Stopped work saves no profile, report or answer.
Usage that was already consumed is still counted.

### Evidence labels

Citations name the exact source. A file inside a subfolder of the selected
material folder is cited with its relative path (`sub1/notes.txt`), so
same-named files stay distinguishable. Text, Markdown and Word files longer
than one chunk are cited per section (`notes.txt — section 2/5`), CSV files
by row range, PDFs by page and Excel by sheet and rows. Indexes created by
older versions are re-read locally once to get these labels (no model call).

`AI_Bot_State/`, the terminal chat folders, any `*.env` file and
`*_ai_updated*` Excel copies are listed in `.gitignore`; keep them out of
commits even if you work inside a git checkout.

### Several tabs or windows

The workbench has one active session. Every page sends the session/context it
displays; if another tab has since switched the session, materials, rules or
model, actions from the older page are refused with "This page is out of date"
and nothing is run or changed. Reload that page (F5) to continue with the
current state. Stop still works from any page.

Startup checks are local and never contact Farm. Dependency/configuration/state
or port failures exit nonzero with instructions. The port check is advisory;
a later Uvicorn bind failure also prints recovery instructions. Native Windows
ACL/locking and real Bosch connectivity still require separate local verification.

The automated test environment, pinned test tools, commands and known static
findings are documented in [TESTING.md](TESTING.md). No release ZIP is generated
by running those tests.

Install the listed packages once in the Python environment that already uses
your Bosch proxy, from inside the downloaded tool folder:

```powershell
python -m pip install -r requirements.txt
```

### Codebook OCR（建议安装）

Codebook 的准备会保留 PDF 原生文字、生成整页高清图，并尝试以
Tesseract OCR 读取扫描页。Python 依赖会随 `requirements.txt` 安装；在
Windows 上还需安装本机的 Tesseract 程序及 German (`deu`) language data。
如果它不可用，界面仍会完成原生文字 + 页面图片 + 多模态解析，并在
锁定的 `codebook_profile.json` 中明确记录该页 OCR 不可用，而不会悄悄把
OCR 当作已经成功。

Start a named persistent conversation and point it to the existing `.env`:

```powershell
python bosch_chat.py --env-file "C:\\path\\to\\your_existing\\.env" --model gemini-2.5-pro --session excel_project
```

Then first run `/test`. It must reply exactly `Bosch Farm terminal chat is
connected.` before relying on it.  Add files with `/add "path\\to\\file.pdf"`.
The `.bosch_chat` folder is created locally next to the script and contains
conversation history and the searchable file index; it never stores the Farm
key.

Useful commands: `/help`, `/add PATH`, `/files`, `/search WORDS`,
`/summary TEXT`, `/model MODEL_ID`, `/new`, `/test`, `/quit`.

## Models and Chinese

The same conversation and local file memory can be used with any model ID
available to your Bosch Farm subscription. Start with `--model`, or switch at
runtime without losing the local session:

```text
/model gemini-2.5-pro
/model claude-sonnet-5-5
/model deepseek-r1-0528-maas
```

The connector routes Gemini, Claude and GPT/O1/O3/Llama/GLM/DeepSeek-style
model names to the appropriate Farm API. Ask questions in Chinese and add this
to `/summary` if you always want Chinese output: `始终使用中文回答。`

### Bosch Farm model catalogue (confirmed 2026-10-23)

Use the **Model ID** exactly as listed below. In particular, `Claude Haiku
5.5` is `claude-haiku-5-5`, not `claude-haiku-5.5`; the latter produces a
Farm `HTTP 404` because that model does not exist at the Anthropic Vertex
endpoint.

| Publisher | Model name | Model ID |
|---|---|---|
| Anthropic | Claude Opus 5 | `claude-opus-5` |
| Anthropic | Claude Opus 4.8 | `claude-opus-4-8` |
| Anthropic | Claude Opus 4.7 | `claude-opus-4-7` |
| Anthropic | Claude Opus 4.6 | `claude-opus-4-6` |
| Anthropic | Claude Opus 4.5 | `claude-opus-4-5@20251101` |
| Anthropic | Claude Sonnet 5.5 | `claude-sonnet-5-5` |
| Anthropic | Claude Sonnet 5 | `claude-sonnet-5` |
| Anthropic | Claude Sonnet 4.6 | `claude-sonnet-4-6` |
| Anthropic | Claude Sonnet 4.5 | `claude-sonnet-4-5@20250929` |
| Anthropic | Claude Haiku 5.5 | `claude-haiku-5-5` |
| Anthropic | Claude Haiku 4.5 | `claude-haiku-4-5@20251001` |
| Google | Gemini 3.7 Flash | `gemini-3.7-flash` |
| Google | Gemini 3.6 Flash | `gemini-3.6-flash` |
| Google | Gemini 3.5 Flash | `gemini-3.5-flash` |
| Google | Gemini 3.5 Flash-Lite | `gemini-3.5-flash-lite` |
| Google | Gemini 3.1 Flash-Lite | `gemini-3.1-flash-lite` |
| Google | Gemini 2.5 Pro | `gemini-2.5-pro` |
| Google | Gemini 2.5 Flash | `gemini-2.5-flash` |
| Google | Gemini 2.5 Flash-Lite | `gemini-2.5-flash-lite` |
| Google | Gemini 3.1 Flash Image (Nano Banana 2) | `gemini-3.1-flash-image` |
| Google | Gemini 2.5 Flash Image (Nano Banana) | `gemini-2.5-flash-image` |
| Google | Gemini Embedding 2 | `gemini-embedding-2` |
| Google | Gemini Embedding 1 | `gemini-embedding-001` |
| Mistral AI | Mistral OCR 2 (25.05) | `mistral-ocr-2505` |
| Endpoint #3 | DeepSeek R1 (0528) | `deepseek-r1-0528-maas` |
| Endpoint #3 | Llama 3.3 70B | `llama-3.3-70b-instruct-maas` |
| Endpoint #3 | GLM-5 | `glm-5-maas` |
| Endpoint #3 | GLM-4.7 | `glm-4.7-maas` |

The workbench's normal model list deliberately contains the common **chat**
models; choose **Other** and paste any other exact ID. The catalogue is a Farm
availability list, not a statement that every item fits the current chat
connector: embedding models cannot answer chat prompts, image models have a
different output use case, and `mistral-ocr-2505` needs a dedicated OCR
connector (it is not currently routed by this chat tool). The pricing file
recognises the exact current IDs for the chat models where a price is already
configured; it does not invent prices for models whose Farm pricing is unknown.

## Complex Excel workbooks

### Recommended: conversational Excel Agent

For workbook questions and safe edits, start the single conversational tool:

```powershell
python excel_chat_agent.py --model deepseek-v4-flash-2026-04-23 --session workshop
```

Progress is now shown by default: model planning, folder search, workbook
loading, tool execution and elapsed seconds. While a stage is waiting, an
update appears every 10 seconds. A single user message can require several
model requests; the final line reports the request count and total time.

To also display the reasoning text **actually returned by Farm** and request
streaming:

```powershell
python excel_chat_agent.py --model deepseek-v4-flash-2026-04-23 --session workshop --show-reasoning
```

`接口思考>` is the API's `reasoning_content`; `[进度]` is a local execution
status. Neither is evidence that a tool has succeeded until it returns.
The official DeepSeek API supports this field, but the Bosch deployment must
forward it. If the field is missing, the program says so. It never invents a
reasoning transcript. Reasoning text is not saved to conversation history.

If Farm explicitly rejects streaming, the connector retries once without it
and keeps that choice for the current connection. A broken stream after output
has begun is reported as an error; partial planner JSON is never executed.
You can also start explicitly without streaming; reasoning, if returned, will
then appear only when the response finishes:

```powershell
python excel_chat_agent.py --model deepseek-v4-flash-2026-04-23 --session workshop --show-reasoning --no-stream
```

`--stream` alone streams answer text without displaying reasoning. `--thinking
enabled` or `--thinking disabled` explicitly sends DeepSeek's thinking option;
only use it if your Farm deployment accepts that option. The default `auto`
preserves the deployment's existing setting, and `--show-reasoning` by itself
does not change that setting. Gemini and Claude currently use full responses
with progress updates. Showing output sooner does not shorten model compute.
See the [DeepSeek thinking API guide](https://api-docs.deepseek.com/guides/thinking_mode/).

It opens with `you>`. Every normal Chinese message is first sent to the chosen
LLM as a tool-planning request: the LLM decides whether to search the folder,
choose one returned candidate, open the workbook, inspect cells or prepare a
safe edit plan. It does **not** rely on a fixed Chinese command format.

The local program remains the safety boundary: it only lets the model search a
directory explicitly named in the current message, only lets it open a file
that search returned, and never writes until you type `确认执行`. Commands are
only needed for `/model`, `/status`, `/cancel`, `/quit` and that confirmation.
The first message only needs to describe where the source file is. It accepts
either an exact file path or a folder plus a natural-language filename hint,
for example:

```text
打开 "C:\\work\\workshop.xlsx"
打开 "C:\\work\\资料目录\\这个路径里面名字叫129BG的excel文件"
第六个 Sheet 的表头和公式关系是什么？请引用准确单元格坐标。
请在 "C:\\work" 中找到 berk_results.xlsx，把它作为参与者结果文件。
在 Workshop 表中按 BG-ID 添加 Berk 的判断，先给出修改计划，不要写入。
```

The model can call only the controlled local tools for exact ranges, cell
searches and direct formula references. It replies in Chinese and must cite
`Sheet!A1` for workbook facts. It can create a JSON plan but cannot write the
workbook until you type exactly `确认执行`. After a plan is created the program
itself prints a local summary read from the plan file (sheet, target column,
new header, number of written cells, the first ten "cell → value" edits, plan
path and SHA-256); this summary, not the model's wording, is what you confirm.
If the plan file changes after that summary was shown, `确认执行` is refused
and a new plan must be created. Safety refusals are reported as "未执行写入"
without ending the conversation. It then creates a separately named
`*_ai_updated.xlsx` and verifies each planned cell plus all original formula
text. The original file remains unchanged.

Array formulas are supported by the exact reader and formula tracer. Results
include the original formula text, its anchor cell and the covered range;
array result cells point back to that anchor. Excel data-table formulas expose
their stored definition instead of an invented formula string. Dates, times
and durations are converted to JSON-compatible values. This fixes
`Object of type ArrayFormula is not JSON serializable` during analysis.

For example, ask naturally:

```text
请读取 Klassifikation_Übersicht_Gesamt 的 M30、X30、Y30，分别列出公式原文、数组范围和直接引用，再用中文解释。
```

The reader does not calculate Excel formulas. Direct references retain their
Sheet and range; dynamic references, named ranges and external links that
cannot be resolved are explicitly reported. New edit plans also check array
formula definitions and refuse to write into array/data-table result ranges.
Recreate an older edit plan if its formula verification predates this fix.

### General document chat

Add the `.xlsx` file first:

```text
/add "C:\\work\\result.xlsx"
```

The chat program reads every worksheet, cell value and formula (formulas are
kept as formulas), then retrieves relevant sections when you ask a question.
For a complex workbook, first ask it to list sheets and describe the analysis
plan, then ask one question at a time, naming the sheet, columns and expected
output. For example: `请只分析 Sheet "Results" 的 A:Q 列，先解释公式关系，再检查异常值。`

Cell text and formulas are read well. Charts, colours, merged-cell layout,
embedded images and the visual meaning of a multi-page printed worksheet are
not fully represented by `.xlsx` extraction. Export the relevant sheets/ranges
to PDF or screenshots and add those too; then the vision model can inspect the
actual layout:

```text
/add "C:\\work\\result.xlsx"
/add "C:\\work\\Results_sheets.pdf"
```

For exact spreadsheet work, do not ask the RAG chat to guess a cell address.
Use `excel_agent.py`: it prints exact `Sheet!A1` coordinates and formula text,
creates a JSON plan containing every intended write, and only applies that
reviewed plan to a *new* workbook. It refuses to overwrite the source file,
to write into a non-empty target column, to proceed when a BG ID is missing,
or to apply a plan after the source workbook changed. It also verifies each
written cell and checks that every original formula is unchanged.

Typical workshop-participant workflow:

```powershell
# Inspect Sheet names and exact layout.
python excel_agent.py inspect "C:\\work\\workshop.xlsx"
python excel_agent.py range "C:\\work\\workshop.xlsx" --sheet "Workshop" --range "A1:Z40"

# Create an editable but non-executing plan. BG-ID and Judgement are columns
# in berk_results.xlsx (or CSV). M must be a reserved, fully empty column.
python excel_agent.py plan-participants "C:\\work\\workshop.xlsx" --sheet "Workshop" --header-row 1 --id-header "BG-ID" --template-header "Jonas" --target-column "M" --new-header "Berk" --results "C:\\work\\berk_results.xlsx" --results-id-column "BG-ID" --results-value-column "Judgement" --plan "C:\\work\\berk_plan.json"

# Open and review berk_plan.json. Then apply to a copy and verify it.
python excel_agent.py apply "C:\\work\\workshop.xlsx" --plan "C:\\work\\berk_plan.json" --output "C:\\work\\workshop_with_berk.xlsx"
python excel_agent.py verify "C:\\work\\workshop_with_berk.xlsx" --plan "C:\\work\\berk_plan.json"
```

The safe first version fills a **pre-existing empty participant column** and
copies the chosen template column's formatting. It deliberately does not
insert columns or automatically rewrite unrelated formulas, tables, charts or
external links; those changes need a workbook-specific reviewed plan. Open the
result in Excel once to recalculate formulas, because openpyxl preserves but
does not calculate Excel formulas.

For PDFs and images retrieved as relevant evidence, the source file is sent
again to the selected Farm model. For text-based files, only the relevant local
excerpts are included. This is why file memory remains usable after reopening
the terminal without continually re-uploading every document.
