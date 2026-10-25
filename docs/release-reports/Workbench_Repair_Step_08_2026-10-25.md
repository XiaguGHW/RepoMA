# Release repair — step 8

Scope: original repair report section 6, step 8, R16 only, including its
regressions and itemized static-check handoff. Step 9 remains a separate stage.
Starting main: 101d471e78763589485d7409e917fdd7e285f680.
Local/remote heads matched and the initial working tree was clean. Read
tools/release_audit/README.md, the original report and the step-7 handoff first.
No ZIP or packaging workflow was requested or run; no real Bosch Endpoint or
user BG/Codebook/Excel was accessed.

## Reproduced baseline

The 15 promoted audit methods reproduced exactly the three remaining R16
failures: setup ignored env_file, --port stayed at 8765, and unknown CLI options
started the server instead of raising an argparse error. Existing later fixes
were preserved. The previous full gate was 169 methods, 165 passes, 3 failures
and one native Windows skip; the 16 browser methods passed.

## Startup and actionable failures

workbench_startup.py is a standard-library bootstrap. It parses --env-file and
--port before third-party imports, so --help, unknown-option rejection and port
validation work even without installed application dependencies. Python 3.10+
is required. Missing packages and broken package imports print an installation
command for the actual Python executable (PowerShell syntax on Windows).
The main entry also explains recovery from a subsequent runtime import failure.

Default .env and AI_Bot_State resolve beside the program, independent of cwd and
the selected workspace. Explicit env paths resolve once from the launch cwd;
empty CLI paths, missing explicit files, unreadable/invalid UTF-8 files and missing
keys fail with recovery instructions and nonzero exit status. UTF-8 BOM is
supported. A missing default .env is allowed when an inherited process key exists.

Ports must be integers in 1–65535. No --host option exists; Uvicorn still receives
host=127.0.0.1. An occupied port explains how to open an existing Workbench URL
or choose --port 8877. The probe is advisory, not a reservation: a subsequent
Uvicorn bind/start failure also gives recovery instructions. The program does
not terminate another process or assume that any service on that port is
Workbench.

State checks exercise directory creation, temporary writing, replacement and
cleanup. Failure reports permissions, space and file-lock recovery or moving
the complete program folder. It does not relocate state to a BG folder. The
legacy GUI state_dir field remains accepted when empty; a nonempty override is
now explicitly rejected. This replaces silent ignoring with an actionable error.

## One configuration and transactional setup

CLI configuration, /api/setup, model tests and diagnostics select the same env
file. An API env_file can explicitly select a different file; subsequent empty
values retain the successful selection for this process. Custom file selection
must be passed again on restart. The GUI still has no env-file picker.

Inherited process variables take precedence over dotenv values. FarmEnvironment
tracks only values dotenv added, preventing an earlier file's key/endpoint from
silently overriding a later file. Failed setup restores the previous environment;
ACTIVE is replaced only after configuration, connector, state and settings
preparation succeed. Existing active state and pending plan remain on failure.

Model probes and diagnostics use temporary env contexts when a session is active.
They can inspect an edited config without changing that session's connector or
endpoint. Reopen the workspace to apply edited config to the active connector.
Shared locking prevents a config inspection/change from racing an active model
call. Keys are neither returned by APIs nor saved in settings/session files;
configuration failures expose recovery copy and paths, not credential contents.

## Visible GUI recovery

Workspace setup returns explicit success/failure. Its drawer stays open on
failure, shows localized recovery instructions and retains the entered path for
retry. A visible application notice also covers automatic restoration failures.
Error records and pending input survive language changes. Model-test status now
appears beside the model selector, rather than only in hidden legacy controls.
The existing attribute-injection regression still closes/reopens the input and
asserts that the supplied text cannot create an event handler; it now explicitly
closes the intentionally retained failure drawer.

## Validation

Runtime: Python 3.12.14, Ruff 0.17.2, mypy 1.15.0 and Playwright 1.51.0/Chromium
on Linux. All data and credentials are synthetic. API model calls use the existing
loopback Farm fixture. Subprocess tests copy program sources into disposable
directories and never use real credentials or contact Farm.

- 14 new startup/configuration methods pass. They cover actual UTF-8/BOM env
  loading after clearing key variables; shared setup/probe/diagnostic selection;
  file changes and environment precedence; failed config/model/state rollback;
  missing-config repair; invalid endpoint redaction; locked replacement cleanup;
  CLI help/unknown/empty-env/port/host arguments; missing/broken dependencies;
  missing/bad-encoding files; missing keys and blocked state; occupied ports;
  a simulated post-probe Uvicorn failure; and real subprocess start, shutdown and
  restart from another cwd with spaces, Chinese and umlauts. Source bytes remain
  unchanged and state stays beside the copied program.
- Full discovery: 183 methods, 182 pass, one native Windows test skipped on
  Linux, zero failures/errors. All 15 promoted audit methods pass. No failures
  were suppressed, skipped or changed to expectedFailure.
- Browser: 17 methods pass. The new method covers visible config/state errors,
  retained active state and workspace input, ZH/EN/DE error redraw and retry after
  removing the fault. Its 390px German screenshot was visually inspected.
  Existing draft, scope, preview/cancel, language, attribute and real drawer
  interactions remain active and pass.
- Fatal Ruff subset, full Ruff on workbench_startup.py/new startup tests/browser
  tests, catalog/JavaScript checks, compileall and git diff whitespace pass.
- Explicit mypy configuration now includes all 11 application modules and sets
  Python 3.10 as the target. The new startup module has no mypy findings. Full
  Ruff remains nonzero with 260 findings (previously 264); full mypy remains
  nonzero with 44 errors in 6 files (unchanged). No blanket ignores or reduced
  check scope were added. Every residual finding, location and follow-up
  disposition is listed in
  [the static findings snapshot](Workbench_Repair_Step_08_Static_Findings_2026-10-25.md).

The existing mocked CLI-port audit additionally mocks the writable-directory
and socket preflights, keeping it side-effect-free. New subprocess tests exercise
those real preflights. The expected port/unknown-option/env-file assertions were
not weakened. README documents dependencies, CLI/API precedence, default paths,
recovery steps and exact test commands via TESTING.md.

Logs: /tmp/workbench-step8-baseline.log, /tmp/workbench-step8-unit-final.log,
/tmp/workbench-step8-browser-final.log, /tmp/workbench-step8-startup-ui-final.log,
/tmp/workbench-step8-catalog-final.log, /tmp/workbench-step8-ruff-final.json and
/tmp/workbench-step8-mypy-final.log. Browser artifacts:
/tmp/workbench-step8-browser-final. Temporary artifacts are not committed.

## Handoff boundary

Step 8 / R16 is complete. The report's step 9 remains: consolidate R01–R16 test
evidence and final release limitations, retain the full checks and review any
unresolved release gates. Passing runtime tests does not mean full lint/type
checks are green. Native Windows ACL/locking/junction behavior, Python 3.10 runtime
execution, real enterprise formats/OCR data and real Bosch endpoint behavior
remain unverified here. No fresh ZIP or unpacked ZIP cold-start is claimed.
Continue from current main with the original report and this handoff; do not
generate a ZIP or access real materials/endpoints without separate authorization.
