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
