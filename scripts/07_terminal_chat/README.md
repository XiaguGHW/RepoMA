# Bosch Farm Terminal Chat

Put these two Python files in the same directory in your Bosch project:

- `llm_connector_with_prompt_caching.py`
- `bosch_chat.py`

The project `.env` must contain the existing Farm secret (do not put it into
either Python file):

```dotenv
BOSCH_FARM_SUBSCRIPTION_KEY=...
# Optional if your Farm base URL differs from the connector default:
BOSCH_FARM_BASE_URL=https://aoai-farm.bosch-temp.com/api
```

Install the listed packages once in the Python environment that already uses
your Bosch proxy:

```powershell
python -m pip install -r requirements_bosch_chat.txt
```

Start a named persistent conversation:

```powershell
python bosch_chat.py --model gpt-5.5 --session masterarbeit
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

This version can read, analyse and propose Excel modifications, but it does
not write into a workbook yet. That separation is intentional: a future edit
command should first show the requested cell/range changes and require your
confirmation before saving a copy of the `.xlsx` file.

For PDFs and images retrieved as relevant evidence, the source file is sent
again to the selected Farm model. For text-based files, only the relevant local
excerpts are included. This is why file memory remains usable after reopening
the terminal without continually re-uploading every document.
