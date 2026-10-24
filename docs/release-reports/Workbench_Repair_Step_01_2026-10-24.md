# Release repair — step 1

Scope: report section 6, step 1 / R01 only.

## Preserved starting state

- Repository: XiaguGHW/RepoMA, main.
- Starting commit: c8ea9734c357db10b0107b65307b5bc16a59b394.
- Initial tracked diff: empty. Initial untracked file list: empty.
- All synchronized audit fixtures, release_safety.py and release tests existed.
- Read tools/release_audit/README.md before implementation.
- The starting Git commit preserves every original file; there was no
  uncommitted user work requiring a separate patch backup.

## Changes

- Corrected the existing browser entry point's workspace selector, setup
  completion wait, current lock button label and classification/coverage card
  locators. Main workflow operations use user controls and real clicks.
- Added strict geometry and actual material-selection/confirmation checks.
  A drawer being transparent does not make Playwright is_visible() false;
  close verification checks the application's open state instead.
- Converted the four browser gap observations into independent assertions.
  Only the card retranslation test inserts synthetic structured card data to
  isolate rendering; the full user-flow test obtains actual mock model results.
- Promoted all 11 backend audit assertions to normal unittest discovery;
  added four startup/state assertions from the supplied one-off probes.
- Added development test dependencies, explicit Ruff/mypy configuration and
  TESTING.md. No global skips, expectedFailure markers or module-wide type
  exclusions were introduced.

## Actual validation

Environment: Linux, Python 3.12, Node 24.22.1, Playwright 1.51.0,
Chromium 134.0.6998.35, Ruff 0.17.2, mypy 1.15.0.
Application dependencies were installed from the unchanged requirements.txt.

| Check | Result |
|---|---|
| unittest discovery | 82 executed, 67 passed, 15 failed, no errors/skips |
| Original tests within discovery | All 67 passed |
| Promoted backend diagnostics | All 11 failed as reported |
| Additional startup/state assertions | All 4 failed, reproducing R05/R16 |
| Browser main user workflow | Passed all five core stages, including refresh |
| Sixth phase: geometry and material actions | 1440/800px passed; 390px failed on negative drawer x |
| Browser safety cases | Draft loss, old-language card and injected event attribute reproduced |
| Browser total | 5 test methods, 9 assertion failures, 0 errors; exit 1 |
| Full Ruff on modified/new Python tests | Passed |
| Fatal Ruff subset across application | Passed |
| Full Ruff across application and tests | 277 existing findings; not passed |
| mypy, explicit 9 application modules | 50 errors in 6 files; not passed |
| compileall | Passed |
| git diff --check | Passed |

The browser's nine failures comprise six language subtests for one lost draft,
one card-language assertion, one 390px geometry assertion and one attribute
escaping assertion. They are not nine new independent product defects.
The 390px drawer was measured at x=-226 with width=390 in this environment.
No CSS correction was applied in step one.

Historical counts of 105 Ruff and 38 mypy findings came from the earlier audit's
tool environment. Current counts use explicit configuration and the versions
above; they must not be presented as a new business regression or a green gate.

No business Python/HTML/JavaScript/catalog file, historical audit script, release
report or packaging workflow was changed. No ZIP was created. No real Endpoint
was called. All writes during tests were confined to synthetic temporary data.

## Handoff

Step 1 is complete as a test-foundation change. The suite deliberately remains
red until subsequent report steps fix the demonstrated defects.
The next report stage is step 2: R02, R03 and R04; it was not executed here.
Use TESTING.md to rerun individual cases and preserve this failing baseline.
