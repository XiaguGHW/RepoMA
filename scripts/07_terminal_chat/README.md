# Bosch Farm Terminal Chat

Download the complete `07_terminal_chat` folder anywhere on your Bosch computer.
The two Python files must remain together inside it:

- `llm_connector_with_prompt_caching.py`
- `bosch_chat.py`
- `excel_agent.py` — precise Excel inspection and safe writing tool

Use your existing Farm `.env` file. Do not put its secret into either Python
file or copy it into this tool folder:

```dotenv
BOSCH_FARM_SUBSCRIPTION_KEY=...
# Optional if your Farm base URL differs from the connector default:
BOSCH_FARM_BASE_URL=https://aoai-farm.bosch-temp.com/api
```

Install the listed packages once in the Python environment that already uses
your Bosch proxy, from inside the downloaded tool folder:

```powershell
python -m pip install -r requirements.txt
```

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
/model claude-opus-4
/model gpt-5.5
```

The connector routes Gemini, Claude and GPT/O1/O3/Llama/GLM/DeepSeek-style
model names to the appropriate Farm API. Ask questions in Chinese and add this
to `/summary` if you always want Chinese output: `始终使用中文回答。`

## Complex Excel workbooks

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
