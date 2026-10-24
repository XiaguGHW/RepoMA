# Workbench UI language migration

## Step 2: shared catalog

`workbench_i18n.json` is the only source of migrated UI translations.
`messages` contains matching zh/en/de semantic keys; `legacy_keys` maps old
visible strings to keys during migration. Do not add new legacy aliases.
`t(key, parameters)` is the common formatter. `tr` and `rt` are compatibility
adapters, not independent translation dictionaries.

The catalog is embedded by `chat_workbench.py` at startup. It is packaged next
to the Python files, independent of the chosen workspace and AI_Bot_State.
No new API endpoint or external translation service is used.

## Rules for new UI copy

- Add the same semantic key and named placeholders in all three languages.
- Use complete sentences, not translated fragments joined around dynamic data.
- Chinese UI calls a Baugruppe 装配体; German engineering copy uses Baugruppe,
  Klassifikationsregeln, Materialumfang and Evidenz as appropriate.
- Never translate filenames, paths, model IDs, class names, source passages,
  user input or model answers. Pass dynamic values as parameters unchanged.
- Escape rendered HTML at the rendering boundary; the translator returns text,
  not trusted HTML. Prefer textContent for UI copy.
- Run `python -m unittest discover -s local_llm_chat_bot/tests -p test_workbench_i18n.py`
  from the repository root. Install Node.js to include embedded JS checks.

## Deliberately not completed in step 2

The legacy DOM translation observer remains until static markup and dynamic
renderers are migrated. Existing hardcoded strings not yet wired to keys,
server progress/errors, language persistence races and open-panel rerendering
still need subsequent steps. Catalog tests do NOT prove browser switching is
fixed. Full browser tests must check ZH → EN → DE → ZH → EN → DE, asynchronous
updates and unchanged source content/selections. The translator loop test is
only a unit test, not a substitute for those browser checks.
