# Workbench release tests

Run from an isolated Python environment. Node.js is required for the JavaScript
tests; browser tests need Chromium. No Bosch credentials are required: fixtures
generate disposable documents and use a loopback HTTP mock.

From the repository root:

```bash
python -m venv .venv-workbench
# Activate the environment using your shell's usual activation command.
python -m pip install -r local_llm_chat_bot/requirements-dev.txt
python -m playwright install chromium
cd local_llm_chat_bot
python -m unittest discover -s tests -v
python tests/browser_release.py
python -m ruff check --select E9,F63,F7,F82 .
python -m ruff check .
python -m mypy
python -m compileall -q .
git diff --check
```

Run each command even if an earlier command fails when collecting the baseline;
do not treat the last command's exit code as the result of all checks.
Python requirements retain the application's existing lower bounds; they are not
a complete lockfile. The testing tools are pinned in requirements-dev.txt.
The repository's mypy configuration explicitly checks all eleven application
modules, including function bodies. Third-party missing stubs and followed
imports are excluded, not the application's source files. Mypy 1.15.0 is used
because 2.4.0 crashed in this container's process discovery before checking code.

## Result interpretation

- Existing tests and new audit assertions are discovered together. At the
  step-one baseline there are 82 tests: 67 pass and 15 fail. The failures are
  executable release blockers, not skipped tests or expectedFailure markers.
- The original 11 backend diagnostics were promoted into
  tests/test_release_audit_gaps.py. Four additional assertions cover nested
  context corruption, custom env loading, CLI port selection and unknown CLI
  arguments. The historical tools/release_audit scripts remain unchanged.
- Run a single regression with, for example:
  `python -m unittest discover -s tests -p test_release_audit_gaps.py -v`.
- Browser tests run separately. They exercise the workspace, custom model,
  six language changes, rules prepare/lock/edit, BG changes, classification,
  follow-up, refresh, tree expansion/selection, and real material confirmation.
  Cards are located by their specific heading, separating classification from
  coverage despite their shared CSS class.
- Browser defects are asserted independently: draft preservation, existing-card
  retranslation, attribute input escaping, and drawer/button geometry at
  1440/800/390px. The main user flow is independently reported, so a narrow-screen
  defect does not prevent checking refresh or the other defect cases.
- On any browser assertion/timeout, the command exits nonzero and
  browser-results.json records success=false, the failed test/stage and traceback.
  Multiple language or viewport failures can belong to a single regression.
  A failed result is not a release pass even if some stages passed.
- Output defaults to a unique system temporary directory, printed on completion.
  Set WORKBENCH_TEST_OUTPUT to choose a separate output directory.
  WORKBENCH_CHROMIUM_EXECUTABLE optionally selects an installed Chromium executable.
  Keep browser screenshots, generated state, environments and logs out of commits.

## Current gates and environment

The current code baseline is `main` at `3db6e7f` (post-review steps 1–5). Run
the commands above from an isolated environment with the versions pinned in
`requirements-dev.txt`; browser checks require Playwright Chromium. The
repository test fixture sets `WORKBENCH_ALLOW_TEST_HOST=1` because `testserver`
is intentionally rejected in production. Do not set it for a production run.

At this baseline, complete backend discovery has 242 tests. In this environment,
eight cannot complete with the real dependency set because PyMuPDF is unavailable:
two import `fitz` directly and six subprocess checks correctly stop when the
dependency check fails. The six subprocess checks pass when rerun with a
minimal substitute that satisfies that import check. One native Windows test is
skipped on non-Windows. These limitations do not replace the required real
PyMuPDF and Python 3.10 verification on the target computer.

The browser suite has 20 passing methods. Fatal Ruff
(`--select E9,F63,F7,F82`), compileall and `git diff --check` pass. Full Ruff
and mypy 1.15.0 (targeting Python 3.10) both exit 0. The former baseline of
165 E702, 84 E701, 6 F401, 1 E402 and 44 mypy errors was removed without
weakening either check's scope.

The checked-in `local_llm_chat_bot.zip` was built at `76c6618` and is older than
the current application code. Do not rebuild or replace it during normal test
work. Packaging happens only after the packaging gate is complete and the user
explicitly authorizes a final ZIP.

## Post-review regression entry points

The following focused suites accompany the completed post-review repairs. They
are additional diagnostics, not substitutes for complete backend and browser
runs.

- F-02 request bounds and cancellation:
  `python -m unittest discover -s tests -p test_release_request_bounds.py -v`
- F-04 stale-page context protection:
  `python -m unittest discover -s tests -p test_release_page_context.py -v`
- F-03 unique rule IDs:
  `python -m unittest discover -s tests -p test_release_rule_ids.py -v`
- F-01 env-file boundary and redaction:
  `python -m unittest discover -s tests -p test_release_secret_boundary.py -v`
- F-09/F-05 plain mode and rule-removal recovery:
  `python -m unittest discover -s tests -p test_release_plain_mode_recovery.py -v`
- F-07/F-11 traceable labels and ignored runtime files:
  `python -m unittest discover -s tests -p test_release_traceable_labels.py -v`
- S-1–S-4 robustness fixes:
  `python -m unittest discover -s tests -p test_release_step_ten.py -v`
- F-06 local-origin access control:
  `python -m unittest discover -s tests -p test_release_local_access.py -v`
- F-08 three-language residual scan:
  `python -m unittest discover -s tests -p test_release_i18n_residual.py -v`
- F-10 deterministic Excel plans:
  `python -m unittest discover -s tests -p test_release_excel_plan.py -v`
- F-13 dead-code and frontend-cleanup checks:
  `python -m unittest discover -s tests -p test_release_frontend_cleanup.py -v`

Post-review fix F-02 (2026-10-25) replaces the step-6 request defaults: one
complete response may take 300 s (`WORKBENCH_RESPONSE_TIMEOUT_SECONDS`), stream
chunk silence is 60 s, a whole operation 3600 s. Read timeouts are no longer
re-dispatched; connection failures and HTTP 429/5xx keep bounded retries.
Codebook preparation, coverage, comparison and dossier rebuild are stoppable
via `POST /api/operation/cancel`. Run its regressions with
`python -m unittest discover -s tests -p test_release_request_bounds.py -v`.

Post-review fix F-04 (2026-10-25): pages send `X-Workbench-Context` (session
directory + context revision); context and model actions from a stale page get
409 `context.stale_page` without a model call or state change. Requests without
the header (API callers, older tests) are not checked. Regressions:
`python -m unittest discover -s tests -p test_release_page_context.py -v` and
the browser method `test_stale_tab_cannot_classify_another_tabs_session_or_bg`.

Post-review fix F-03 (2026-10-25): rule IDs are unique across the whole
profile. Generated IDs never collide; edit/lock reject explicit duplicates with
400 `rules.duplicate_ids`; model-merged duplicates are renamed deterministically
(`<class-key>:<id>`, recorded in `rule_id_renames`); a profile or session locked
earlier with duplicates gets 409 before material binding or any model call.
Regressions: `python -m unittest discover -s tests -p test_release_rule_ids.py -v`.

Post-review fix F-01 (2026-10-25): the configured env file and any `*.env`
file are outside the model path boundary (read, diff, apply, index); the active
key is redacted from prompts, previews/reasoning, answers, plans, evidence
excerpts and history. Regressions:
`python -m unittest discover -s tests -p test_release_secret_boundary.py -v`.

Post-review fixes F-09/F-05 (2026-10-25): outside BG mode an empty or
non-object `classification` is ignored with notice `notice.classification_ignored`
(a real classification object is still rejected); deleting the Codebook marks
the scope `rules_removed`, so materials can be reconfirmed directly for ordinary
questions, while a changed-but-unlocked profile still requires locking.
Regressions: `python -m unittest discover -s tests -p test_release_plain_mode_recovery.py -v`.

Post-review fixes F-07/F-11 (2026-10-25): nonpaged text/DOCX chunks are
labelled `section i/n`, CSV chunks by row range (index `label_version` 2; older
records are re-extracted locally on reuse); evidence and pre-reading summaries
use the path relative to the confirmed material folder. `.gitignore` covers
runtime state, terminal chat folders, `*.env`/`.env.*` (templates excepted) and
`*_ai_updated*` workbooks. Regressions:
`python -m unittest discover -s tests -p test_release_traceable_labels.py -v`.

Post-review step 4 / F-10 (2026-10-25): `excel_chat_agent.py` prints a
deterministic local plan summary (sheet, target column, header, cell count,
first ten edits, plan path, SHA-256) after the model's reply; `确认执行` applies
a private copy of exactly the shown bytes and refuses a changed plan or a plan
without a stored summary hash. excel_agent safety refusals (`die()`) are
reported instead of exiting the agent. Regressions:
`python -m unittest discover -s tests -p test_release_excel_plan.py -v`.

Post-review step 5 / F-13 (2026-10-25): the 16 UI functions that were
redefined at runtime are now declared once and delegate to their
`*ForLanguage` implementation (the material-flow DOM builder is
`createMaterialFlow`); the dead legacy bodies, the unreachable code in
`activate_bg()` and the unused `needs_bg_preparation()` are removed. Fourteen
one-shot status lines built with `innerHTML` + `t()` (e.g. the model-switch
confirmation) now use key-based `setUIMessage`, so a language switch redraws
them. The browser method
`test_full_workflow_and_diagnostics_have_no_chinese_ui_in_english_or_german`
scans the visible EN/DE UI after rules, materials, classification, rules and
materials drawers, diagnostics and the scan/cache report. Source checks:
`python -m unittest discover -s tests -p test_release_frontend_cleanup.py -v`.
Static baseline after this step: Ruff 256, mypy 44 (step 7 clears both).

Reproduce the final additional regression with:
`python -m unittest discover -s tests -p test_release_step_nine.py -v`.
All current static findings and exact tested source hashes are in the JSON;
the step-8 static snapshot remains a historical explanation of the prior baseline.

## Historical gate snapshots

After step 8 (R16), discovery runs 183 methods: 182 pass, no failures/errors and
the existing native Windows test is skipped on Linux. Fourteen new startup/config
methods and all 15 promoted audit methods pass. The browser suite has 17 passing
methods, including visible localized startup recovery and retry at 390px.

```bash
python -m unittest discover -s tests -p test_release_step_eight.py -v
python -m unittest discover -s tests -p test_release_audit_gaps.py -v
python tests/browser_release.py
```

Subprocess startup tests copy the application into disposable paths with spaces,
Chinese and umlauts, clear Farm key variables, use actual synthetic env files,
test missing dependencies with Python -S, occupy a loopback port, simulate blocked
state and a post-probe bind failure, then start/stop/restart a real local server
from another cwd. API model probes use the loopback fixture only. Windows ACLs
and file locks still require Windows; no real Bosch connectivity is inferred.

Mypy explicitly targets Python 3.10 and checks all 11 application modules, including
workbench_startup.py. Runtime tests here use Python 3.12.14. Full Ruff remains
non-green with 260 findings; full mypy remains non-green with 44 errors in 6 files.
The new startup module and startup/browser tests pass full Ruff, and the startup
module has no mypy findings. Every remaining static finding is documented in
docs/release-reports/Workbench_Repair_Step_08_Static_Findings_2026-10-25.md at
repository root. No exclusions or blanket ignores were added. Step 9's final
R01–R16 evidence consolidation has not been performed.
See docs/release-reports/Workbench_Repair_Step_08_2026-10-25.md at repository root.

After step 7 (R13–R15), discovery runs 169 tests: 165 pass, 3 fail and the native
Windows test remains skipped on Linux. Seven new draft/message/image-group
methods pass, as does the promoted English progress/notices audit assertion.
Run the new methods with:
`python -m unittest discover -s tests -p test_release_step_seven.py -v`.
The browser suite has 16 methods, all passing. Four new methods cover editor
text/dirty/caret/scroll/error preservation across six language changes, rejected
context discards, cancel/save/stale-version behavior, structured dynamic message
redraw, unchanged source/model text, and German long paths/errors with actual
file/folder/cancel/selection/close clicks at 390/800/1440px. Native path-picker
results and long server errors are synthetic; UI controls are clicked normally.

The remaining failures are R16's explicit env-file loading, GUI CLI port selection
and rejection of unknown CLI options. Full Ruff still reports 264 findings;
mypy still reports 44 errors in 6 files across 10 checked modules. These checks
remain active and nonzero. Step 8 has not been started.
See docs/release-reports/Workbench_Repair_Step_07_2026-10-25.md at repository root.

After step 6 (R12), discovery runs 162 tests: 157 pass, 4 fail and the native
Windows test remains skipped on Linux. The 18 new runtime/lifecycle tests and
the R12 dropped-content audit regression pass. Run the new tests with:
`python -m unittest discover -s tests -p test_release_step_six.py -v`.
The browser suite has 12 methods: 9 pass; 3 retain 8 known R13/R14/R15 failures.
The two new methods exercise visible answer previews, Stop, worker completion,
retry, navigation disconnect and truncated-response cleanup using real controls.

Chat SSE now sends start (request_id), answer_reset, answer_delta, progress and
exactly one final result or error, followed by end for a connected consumer.
Only decoded root answer text is previewed. Repair/supplemental rounds reset it.
Preview is text-only and is removed on success, stop, disconnect or failure;
classification/change cards are created from the final validated result only.
POST /api/chat/cancel accepts request_id; GET /api/chat/task/{request_id} reports
state, done and worker_alive. A joining reaper releases the shared slot only
after the worker has exited. Cancellation is ordered against final publication;
a request already committed before Stop remains completed in the session.

Request bounds are configured with WORKBENCH_REQUEST_TIMEOUT_SECONDS (180),
WORKBENCH_CONNECT_TIMEOUT_SECONDS (5), WORKBENCH_READ_TIMEOUT_SECONDS (20),
WORKBENCH_MAX_ATTEMPTS (3), WORKBENCH_RETRY_BACKOFF_SECONDS (1),
WORKBENCH_MAX_RESPONSE_CHARS (262144), WORKBENCH_MAX_ANSWER_CHARS (131072).
The whole-operation deadline covers automatic preparation and subsequent calls.
Backoff is cancellable. Blocking I/O exits at its configured connect/read bound;
the slot stays reserved while it unwinds. Raw OpenAI response chunks are checked
before SSE line decoding, including an unfinished event sent in small pieces.
Gemini/Claude currently use complete responses and retain processing progress;
this repair does not claim native streaming from those Farm endpoints.
See docs/release-reports/Workbench_Repair_Step_06_2026-10-25.md at repository root.

After step 5 (R11), discovery runs 144 tests: 138 pass, 5 fail and the native
Windows test remains skipped on Linux. The 20 new accounting tests and both
R11 audit regressions pass. Run the accounting tests with:
`python -m unittest discover -s tests -p test_release_step_five.py -v`.
The browser suite has 10 methods: 7 pass; 3 retain 8 known R13/R14/R15 failures.
Its new test checks real unknown-usage responses in chat, cumulative status,
Codebook preparation and comparison cards.

All session model paths share accounted_model_call, including repairs and
failed responses. The ledger counts dispatched transport attempts, not stream
chunks; reused local summaries/dossiers add no requests. OpenAI SDK automatic
retries are disabled so they cannot bypass accounting; explicit stream fallback
and HTTP retries each have their own ledger entry. Returned usage is saved before
output validation. Per-turn totals include automatic preparation and dossier work.

Token totals are null when incomplete, alongside known_input/known_output and
usage_complete. cost_usd is null for incomplete costs; known_cost_usd sums fully
priced calls only. Persisted estimated_cost_usd retains that known subtotal;
unpriced_requests and cost_complete identify incomplete cumulative cost. Existing
historical omissions cannot be reconstructed from the old counters.
Cache pricing is optional configuration in model_pricing.json entries:
cache_read_usd_per_million and cache_write_usd_per_million. No rates are guessed.
Canonical input includes cache tokens; Claude's separate counts are added once,
while OpenAI/Gemini cache hits are subtracted from prompt totals before pricing
uncached input. Missing required cache prices leave the cost unknown.
See docs/release-reports/Workbench_Repair_Step_05_2026-10-25.md at repository root.

After step 4, discovery runs 124 tests: 116 pass, 7 fail and the native Windows
test is skipped on Linux. R09/R10 audit regressions now pass.
Run the new response-round/reference tests with:
`python -m unittest discover -s tests -p test_release_step_four.py -v`.
BG chat defaults to required classification. Use require_classification=false
for an explanation-only API request, or select Explanation follow-up in the UI.
Any returned classification is still fully validated. Nonpaged Codebooks use
codebook_rule_refs with supplied section/chunk labels and empty physical pages.
The browser suite now covers this mode and reference display.
See docs/release-reports/Workbench_Repair_Step_04_2026-10-24.md at repository root.

After step 3, discovery runs 106 tests: 96 pass, 9 fail and the native Windows
test remains skipped on Linux. R05/R06/R07/R08 audit regressions now pass.
Run the new scope/recovery/rollback matrix with:
`python -m unittest discover -s tests -p test_release_step_three.py -v`.
Browser coverage now also verifies editing/relocking rules and re-confirming
the same BG without losing the material selection. The pending rule path is
tested separately from the effective prepared path.
See docs/release-reports/Workbench_Repair_Step_03_2026-10-24.md at repository root.

After step 2, discovery runs 97 tests: 83 pass, 13 fail and one native Windows
junction/case test is skipped on Linux. R02/R03/R04 regressions now pass.
Run the targeted backend suite with:
`python -m unittest discover -s tests -p test_release_step_two.py -v`.
Browser coverage includes attribute-safe paths/custom models and real two-page
review/confirmation clicks. The remaining browser failures still track
R13/R14/R15. Detailed results are recorded in
docs/release-reports/Workbench_Repair_Step_02_2026-10-24.md at repository root.

Ruff's complete E4/E7/E9/F rule selection is explicit in pyproject.toml.
Full Ruff and mypy currently report existing application/test debt; they are
not green gates yet. The fatal Ruff subset, new/modified test files' full Ruff
checks, Python compilation and whitespace checks pass at step one.
Do not suppress a module or convert a failing safety assertion to a skip merely
to make a gate green.

Business fixes belong to subsequent report steps. Windows-only behavior and real
Bosch Endpoint behavior still require their stated later validation.
Application commits must use [skip ci] while ZIP generation is prohibited;
the existing packaging workflow must not be triggered as a testing side effect.
