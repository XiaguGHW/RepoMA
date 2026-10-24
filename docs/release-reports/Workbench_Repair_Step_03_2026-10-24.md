# Release repair — step 3

Scope: report section 6, step 3, R05 → R06 → R07 → R08.
Starting main: ae7a710bb6a9564145a1da35bf6b7fbf72aff9ae.
Initial tracked diff and untracked file list were empty.

## R05 — recovery at the loading boundary

Persisted context now has schema version 1, a context revision, validated target
and ID fields, material version bindings and a checked locked-rule structure.
Invalid context is copied to a private quarantine file before clearing unusable
bindings. Valid history, code-file metadata and accumulated usage survive.
Legacy valid context is migrated and its material version binding is established
only after source checks pass.

Document index loading validates records, chunk label/text fields and visual
metadata rather than merely checking field presence. Invalid records are
quarantined and excluded. Missing selected document or Codebook IDs block use of
the scope, including when other index records remain valid.
Runtime entry checks also reject malformed context instead of relying solely on
loading having run. Status/session responses expose a reconfirmation state.

## R06 — prepare first, commit with rollback

Target analysis parses into a deep-copied index with deferred saves. Locked rules
are validated before parsing and rechecked afterwards; prepared source bytes must
match their indexed hashes. Until preparation succeeds, the active index,
history, target, pending plan and remembered selection remain untouched.

The commit saves candidate index/state/selection and archives the old transcript.
Only after those operations succeed are the active in-memory bindings replaced
and the pending plan invalidated. If an operation raises, original private state
file bytes and in-memory data are restored, including transcript, coverage and
selection memory. Parser/OCR caches may remain, as allowed by the report.
This is exception rollback within the serialized process; it is not a claim of
multi-file filesystem crash atomicity.

Existing behavior for mixed readable/corrupt material selections remains: readable
files can be selected while parser failures are explicitly reported as skipped.
A wholly unreadable selection or a permission/commit error leaves the old scope
unchanged. No original BG/Codebook/document is modified.

## R07 — rules changed, materials require confirmation

Preparing/editing/locking/replacing rules creates a new profile version. If
materials were selected, the session retains the target and selection draft but
enters an explicit rules-changed state. Chat and comparison cannot silently
become normal Q&A. Another session's global rule changes are detected too.
Reconfirming the same BG binds the new profile version, source hashes and context
revision; old history/results/plans are not reused.

The UI displays a translated reconfirmation message and disables question/send
and comparison actions until confirmation succeeds. Effective prepared rules are
shown with their full path; an unprepared path input is identified separately.
Material re-confirmation finishes restoring the history before re-enabling chat,
so the history refresh cannot erase a newly generated response.
Explicitly leaving BG classification mode still enables normal document Q&A.

The step-two plan fingerprint now includes the persisted context revision and
schema version, in addition to rule/source/change bindings.

## R08 — common entry validation

Chat, streaming chat (before starting SSE), comparison, coverage preparation,
dossier generation/rebuilding and per-file cache rebuilding validate the context
and current source hashes before evidence/model use. The checks cover actual
locked rule version/hash, complete available document IDs, scope equality and
material version binding. Stale scope returns 409 without contacting a model;
the model work slot is released on refusal.

Coverage reports carry the context revision and can only supply dossiers when
the current revision/model/material set matches. Independent factual per-file
summary caches can still be reused by their content/model/reading-scope identity.
Comparison remains read-only and keeps per-model results separate.

## Tests and results

Environment unchanged: Linux / Python 3.12 / Node 24.22.1,
Playwright 1.51.0 with Chromium 134, Ruff 0.17.2, mypy 1.15.0.

| Check | Result |
|---|---|
| New step-three backend suite | All 9 methods passed, including their failure/entry matrices |
| Full unittest discovery | 106 tests: 96 passed, 9 failed, 1 native Windows skip; no errors |
| Original test coverage | Passed, including source immutability and write backup/rollback |
| Existing R05/R06/R07/R08 audit assertions | All now pass |
| Browser full suite | 8 methods: 5 passed, 3 fail with 8 known R13/R14/R15 assertions; no errors |
| Same-BG rule edit/relock/reconfirm and unprepared-path UI test | Passed with actual UI clicks |
| Step-two paths/attributes/two-page confirmation regressions | Passed |
| Full Ruff on new backend and modified browser tests | Passed |
| Application fatal Ruff subset | Passed |
| Full Ruff | 269 findings remain; not green |
| mypy, nine application modules | 49 errors in 6 files remain; not green |
| compileall and git diff --check | Passed |

The model-slot unit fixture now supplies valid empty state/document objects for
the new entry check; its success/failure slot-release assertions remain intact.
The browser ask helper also rejects processing errors instead of treating a
finished failed response as success. The new real-model-path fixture test
explicitly selects Gemini, the provider supported by its loopback HTTP fixture.

Targeted tests cover:

- List/string contexts, invalid selected targets/IDs/locked profiles/schema
  versions, valid legacy migration, malformed chunks/visuals, quarantine and
  preservation of good history/usage.
- Parser, read permission, index save, state save, selection save and transcript
  archive failures, comparing complete before/after active records and files.
- Rule changes in the active and another session; canceled edits; same-BG
  re-confirmation; explicit normal mode; stale coverage revisions.
- Changed/deleted source bytes, missing index entries, changed material scope
  and changed rule bytes across chat, SSE, compare, coverage, dossier and cache
  rebuild entry points. Every refusal asserts zero new mock model requests.

Remaining backend failures are for R09/R10/R11/R12/R14/R16. The browser's eight
remaining assertions comprise six unsaved-draft language cases, one existing-card
language case and one 390px layout case. None was skipped to create a green run.

No real Bosch Endpoint or native Windows environment was used. All test data and
writes were synthetic and temporary. No ZIP was generated; commit uses [skip ci].
The historical repair report and earlier step records remain unchanged.

Next report stage: step 4, R09 → R10. It was not implemented in this step.
