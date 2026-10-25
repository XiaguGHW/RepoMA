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

## Step 3a: static interface binding

The former page-wide text `MutationObserver` is removed. At startup,
`bindInitialStaticI18n()` records only known, server-rendered UI copy and
`applyLanguage()` updates that fixed collection plus explicitly registered
elements. Runtime content is never observed or inferred as a translation key.

Dynamic renderers still need to use semantic keys and rerender from their data
when the language changes. Do not reintroduce a whole-page text observer as a
shortcut for those renderers.

## Completed migration work and remaining manual checks

The migrated interface now uses catalog keys and named parameters for server
progress and error messages. Dynamic panels redraw from their data when the
language changes, and state messages use `setUIMessage` (or `uiMessageNode`)
instead of retaining a previously rendered literal. English and German browser
tests scan the visible full workflow, including diagnostics, rules, materials,
classification, drawers and scan reports, for Chinese UI residue.

New status messages must use `setUIMessage` or `uiMessageNode`; do not build a
one-shot status message with `innerHTML` and `t()`. The source checks in
`tests/test_release_frontend_cleanup.py` enforce this rule.

Catalog and browser tests cannot establish operating-system rendering. The
remaining manual checks are Windows-provided fonts, the actual system file
picker's title and text, and browser zoom/layout at the target display sizes.
