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
The repository's mypy configuration explicitly checks all nine application
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

## Current gates

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
