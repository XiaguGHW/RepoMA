# Local-first Code Chat

`code_chat_agent.py` is a terminal assistant for an existing local codebase.
It sends the model only selected code excerpts and, when a file needs changing,
the current full content of that one target file. It does not put indexes,
sessions, or caches in the source repository.

Place it beside the existing `llm_connector_with_prompt_caching.py` **and**
`model_pricing.json` from RepoMA's root-level `local_llm_chat_bot` folder. The
connector and the existing `requirements.txt` are reused.

## Start on the company computer

```powershell
python -m pip install -r requirements.txt
python code_chat_agent.py --workspace "C:\Users\XXXXX\Documents\Python_Projects\bosch_chat\bot_workspace" --state-dir "C:\Users\XXXXX\Documents\Python_Projects\bosch_chat\AI_Bot_State" --model gpt-6-luna-2026-09-22 --env-file "C:\Users\XXXXX\Documents\Python_Projects\bosch_chat\.env"
```

`--state-dir` is required and may be any directory you choose. State is stored
under `projects/<hash>/<session>` there; the code project remains clean.

## Local browser workbench

If you prefer a graphical Codex-style workspace, start the local-only browser
UI instead:

```powershell
python -m pip install -r requirements.txt
python chat_workbench.py
```

Open `http://127.0.0.1:8765` in the browser that opens on the same computer.
It never listens on the network. Select or paste the code workspace in the
interface, then choose a local document or activate Baugruppe mode with a
Codebook and BG folder. Workbench state is always kept beside the program in
`AI_Bot_State/`; it cannot be redirected to the selected workspace or BG folder.
The centre is the chat; the right panel shows token/cost totals, source evidence
and proposed diffs. Only the **Apply changes** button writes a proposed code
edit.

The workbench shows an expandable **模型推理（接口返回）** panel only when
the Bosch Farm deployment supplies `reasoning_content`. Some models/Farm
deployments return no reasoning; the UI leaves this panel absent rather than
inventing a chain of thought.

## Usage

Tell the assistant the requested change naturally in Chinese. It locally
searches its code index, supplies a few relevant excerpts to the model, and
shows a unified diff for any proposed creation or modification. Type exactly
`确认执行` to write the displayed changes. `/cancel` discards them.

Useful commands:

- `/file PATH` — locally extract and index a PDF, Word document, Excel workbook, CSV, TXT, Markdown file, or PNG/JPEG/WebP image. Quote paths containing spaces.
- `/files` — list locally indexed documents. Use `/file remove ID` or `/file clear` to remove indexes; original files are never changed.
- `/bg "CODEBOOK_PATH" | "BAUGRUPPE_FOLDER"` — activate Codebook-guided Baugruppe analysis. The Codebook and every supported document below the selected BG folder are indexed locally and pinned for later questions.
- `/bg clear` — leave Baugruppe analysis mode while keeping the local indexes for ordinary document questions.
- `/model MODEL_ID` — switch among models available through Farm.
- `/scan` — rebuild the local file and symbol index after substantial manual changes.
- `/status` — show the number of indexed files, cumulative session tokens, and estimated cost.
- `/context` — show exactly what the next request can carry into the model context.
- `/remember TEXT` — immediately save a user-confirmed long-term memory locally for this workspace. Natural requests such as `请记住……` or `删除关于……的记忆` are first shown as a proposal; type `确认记忆` to apply.
- `/memory` — list saved memories. Use `/memory search TEXT`, `/memory edit ID new text`, or `/memory delete ID` to manage them.
- `/cancel` — discard the proposed changes.
- `/quit` — exit.

Before applying a change, the script checks that the target file has not changed
since the diff was displayed. If it has, it refuses the write so your manual
edits are not overwritten.

## Cost behaviour

The initial scan stays on the computer and does not call the model. Every new
request uses local filename/symbol matching first. A full file is sent only
when the model requests that file as the concrete target of a modification;
the rest of the repository is not retransmitted. For OpenAI-compatible Farm models that allow streaming, the Chinese answer appears progressively in the terminal. The internal JSON action remains hidden. When the company gateway returns usage data, every completed turn shows input/output tokens and an estimated cost; `/status` shows the running total for this session. Prices come from local `model_pricing.json`; edit that file to update prices, or start with `--pricing-file "C:\\path\\to\\prices.json"`. If a model has no matching price entry, the script still works but reports the request as unpriced.


## Long-term memory

Long-term memory is stored only in `--state-dir/projects/<workspace-hash>/memory.json`, so it is shared by sessions for the same local workspace but is never placed in the source project. It is written only when you use `/remember` or begin a message with `记住：`. On each request the script locally selects up to five relevant confirmed items; it does not resend the entire memory file.


Natural-language memory changes are never applied automatically. The model can only propose one local add, edit, or delete action; the terminal displays it and requires the exact confirmation `确认记忆`.


## Local document questions

Use `/file "C:\\path\\to\\file.pdf"` to index a local PDF, Word (`.docx`), Excel (`.xlsx`/`.xlsm`), CSV, TXT, Markdown, or PNG/JPEG/WebP file. Extraction and lexical search occur locally; the source file is not uploaded merely because it was indexed. The default local file limit is 80 MB and PDF text is indexed page by page (up to 900 extracted chunks), so a 100–200-page drawing package is no longer silently cut after the first 160 chunks.

For an answer, the script sends only the matching extracted excerpts. It can also attach up to five visual evidence items to the selected Farm model: an original image, a rendered cited PDF page, or a rendered Excel range. A scanned PDF page is kept as visual evidence even when it has no embedded text. The terminal `code_chat_agent.py` does not run local OCR, so its model must inspect that attached page. The graphical Workbench can perform local OCR for scanned pages when Tesseract is available; see the `Codebook OCR` section in `README.md`. Excel cell values/formulas are extracted; charts, colours, merged cells and embedded images are preserved only when a relevant range is rendered as a visual table.

## Baugruppe / Codebook mode

Start a dedicated session with, for example:

```powershell
/bg "C:\\Users\\XXXXX\\Downloads\\Codebook.pdf" | "C:\\Users\\XXXXX\\Downloads\\70BG\\Rotationseinheit\\4711"
```

Then ask naturally, for example: `请根据 Codebook 完整判断这个 Baugruppe 的类别。说明每一步依据，并解释为什么不是 Gantry、Greifer 或 kombinierte Einheit。`

The answer is instructed to use: **Empfehlung**, **Entscheidungsweg nach Codebook**, **Belege**, **Abgrenzung zu Alternativen**, and **Unsicherheit**. Sources are labelled with PDF page or Excel sheet/range. Later questions such as `为什么不是 Gantry？` stay in the same BG mode and use the pinned Codebook/BG sources again. The result is an evidence-led assistant analysis, not an automatic ground truth: missing or conflicting source material should remain explicit as uncertainty.
