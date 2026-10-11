# Local-first Code Chat

`code_chat_agent.py` is a terminal assistant for an existing local codebase.
It sends the model only selected code excerpts and, when a file needs changing,
the current full content of that one target file. It does not put indexes,
sessions, or caches in the source repository.

Place it beside the existing `llm_connector_with_prompt_caching.py` from
RepoMA's `scripts/07_terminal_chat` folder. The connector and the existing
`requirements.txt` are reused.

## Start on the company computer

```powershell
python -m pip install -r requirements.txt
python code_chat_agent.py --workspace "D:\Projects\my_bot" --state-dir "D:\AI_Bot_State" --model gpt-5.5 --env-file "C:\path\to\.env"
```

`--state-dir` is required and may be any directory you choose. State is stored
under `projects/<hash>/<session>` there; the code project remains clean.

## Usage

Tell the assistant the requested change naturally in Chinese. It locally
searches its code index, supplies a few relevant excerpts to the model, and
shows a unified diff for any proposed creation or modification. Type exactly
`确认执行` to write the displayed changes. `/cancel` discards them.

Useful commands:

- `/model MODEL_ID` — switch among models available through Farm.
- `/scan` — rebuild the local file and symbol index after substantial manual changes.
- `/status` — show the number of indexed files and token usage returned by Farm.
- `/cancel` — discard the proposed changes.
- `/quit` — exit.

Before applying a change, the script checks that the target file has not changed
since the diff was displayed. If it has, it refuses the write so your manual
edits are not overwritten.

## Cost behaviour

The initial scan stays on the computer and does not call the model. Every new
request uses local filename/symbol matching first. A full file is sent only
when the model requests that file as the concrete target of a modification;
the rest of the repository is not retransmitted. Token totals are shown when
the company gateway returns usage data.
