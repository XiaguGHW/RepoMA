# Baugruppen Classifier

Local web app for classifying a Baugruppe with a locked Codebook and Bosch Farm
models. It runs only on this computer (`http://127.0.0.1:8765`); source files
never leave it except the excerpts sent to the selected Farm model.

## 1. One-time setup

1. Python 3.10 or newer (a conda environment is fine).
2. Install the packages into that Python, from this folder:

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Put your Farm key into a file named `.env` in this folder:

   ```dotenv
   BOSCH_FARM_SUBSCRIPTION_KEY=...
   # Only if your Farm address differs from the default:
   # BOSCH_FARM_BASE_URL=https://aoai-farm.bosch-temp.com/api
   ```

4. Recommended for scanned Codebook pages: install Tesseract OCR for Windows
   with the German (`deu`) language data. Without it the program still works
   and records that OCR was unavailable.

## 2. Start

Double-click `Baugruppen_Classifier.bat`. It finds a Python with the packages
(`.venv`, `python` on PATH, any conda environment — no `conda activate`
needed), starts the program and opens the browser. There is nothing to
choose: rules, materials, chats, model and language of the last session are
restored. Keep the black window open; closing it stops the program.
Double-clicking again while it runs only opens the page.

If no suitable Python is found, the window offers to create a private `.venv`
here and install `requirements.txt` once.

Desktop icon: right-click `Baugruppen_Classifier.bat` → *Send to* → *Desktop
(create shortcut)*. Options for the shortcut target or the command line:

| Option | Meaning |
|---|---|
| `--port 8877` | Use another local port |
| `--env-file "C:\path\x.env"` | Use another configuration file |
| `--no-browser` | Do not open the browser |

To force a specific Python, set the environment variable `WORKBENCH_PYTHON` to
its full `python.exe` path.

## 3. Where your data is kept

Settings, locked rules, material caches and chats are stored in the
`AI_Bot_State` folder inside this program folder, wherever it is unpacked. The
status card (*Material cache & audit → View*) shows the folder in use.

When updating, unpack the new version over the existing folder (or copy
`AI_Bot_State` and `.env` into the new folder) to keep everything. To store
the data elsewhere, set the environment variable `WORKBENCH_STATE_DIR`.

## 4. Keeping model prices current

Costs are estimates. To use the current BMF prices, open the Docupedia page
*Bosch Model Farm → Pricing*, press Ctrl+S and save it as HTML directly into
this folder (next to `chat_workbench.py`; the `_files` folder Chrome creates
is not needed). Restart the program. *Material cache & audit → View* then shows
"Price list: saved Docupedia page … (date, N models)". Models missing on the
page keep the bundled prices from `model_pricing.json`; rows priced in EUR are
ignored. If the page cannot be read, the bundled prices stay in effect and the
status card says so. To return to the bundled prices, delete the saved page.

## 5. Files

| File | Purpose |
|---|---|
| `Baugruppen_Classifier.bat` | One-click start (Windows) |
| `chat_workbench.py` | Web app and server |
| `workbench_startup.py` | Start options and checks |
| `code_chat_agent.py` | Prompts, session state, pricing |
| `local_document_library.py` | Local reading of PDF, Word, Excel, images, OCR |
| `llm_connector_with_prompt_caching.py` | Bosch Farm model connection |
| `request_runtime.py` | Time limits and Stop |
| `release_safety.py` | Usage accounting and safety checks |
| `workbench_i18n.py`, `workbench_i18n.json` | Interface languages (ZH / EN / DE) |
| `model_pricing.json` | Bundled prices for the cost estimate |
| `price_page.py` | Reads a saved Docupedia pricing page |
| `requirements.txt` | Python packages |

Never share or commit `.env`.

## 6. Common problems

| Problem | Fix |
|---|---|
| Missing Python packages | Run `python -m pip install -r requirements.txt` with the Python shown in the black window. |
| No Farm key | Create `.env` as above, then start again. |
| Port in use | The program is probably running already: open `http://127.0.0.1:8765`. Otherwise start with `--port 8877`. |
| Page says it is out of date | Another tab changed the session; press F5. |
| Slow models | Increase `WORKBENCH_RESPONSE_TIMEOUT_SECONDS` (default 300) in `.env` and restart. |
