# Release repair — step 2

Scope: report section 6, step 2: R02, R03 and R04.
Starting main commit: ddc886f96bcf324f7d3333653c4640c1330dbcd5.
The starting workspace had no tracked or untracked user changes.

## R02 — shared path boundary

ProjectState.resolve_relative now normalizes separators, validates both original
and resolved components, rejects ignored/private/configuration paths, and protects
the actual state directory even when it has a custom name. Every existing path
component is checked with lstat; symbolic links and Windows reparse points are
rejected. Normal files, Unicode/spaced paths and missing tails for new files remain
usable. The scanner uses the same checks to prune directories and filter files.
Read excerpts, requested full reads, diff creation and application already share
this resolver and now receive the strengthened boundary.

Validated: file/directory links, ordinary in-workspace links, a link inserted
after review, traversal/absolute paths, private state/config names, a custom state
directory, synthetic reparse metadata, and the original private-marker prompt
regression. Native Windows junction/case tests are included but not run on Linux.

## R03 — attribute-safe UI rendering

Dynamic workspace/Codebook/material paths and custom comparison model inputs use
an attribute-specific encoder for ampersands, angle brackets and both quotes.
Comparison option values are encoded too. Cache file IDs are passed through an
encoded data attribute instead of being inserted into JavaScript string literals.
Existing safe text-node encoding remains unchanged.

Real Chromium tests confirm that quoted input is preserved without creating or
executing a pointer event handler. Tests cover all three path inputs and both
comparison renderers. Comparison renderer testing is isolated from the separate
drawer lifecycle during language changes.

Additional observation for the later R14 work: switching language while the
comparison drawer is open can remove its custom input. This existing lifecycle
branch is outside step 2; it has not been claimed fixed.

## R04 — exact-plan confirmation

Every nonempty proposal receives a new server-held plan ID. Its binding includes
session/workspace, model, context revision, selected target, BG context, source
IDs/indexed versions, rule profile and actual rule-source hash, plus a digest of
the ordered changes and their contents. The browser sends the ID on the specific
displayed button. Apply checks that binding under the existing mutation lock,
rechecks current material hashes and target-file hashes, and preserves the
backup/staging/replacement/rollback path.

New questions/proposals, cancellation, successful application and context/session
changes invalidate old IDs. Missing, stale and replayed confirmations return 409.
Rejecting A's stale ID does not invalidate B's valid current proposal.

Browser testing exposed that the pre-existing changes container is CSS-hidden.
For an actual review-and-confirm flow, showChatResult now also displays the full
diff and its bound confirmation button as a normal assistant card. Confirmation
feedback updates that specific card. The existing confirmation dialog remains.
No page-wide layout or unrelated controls were redesigned.

Validated: two real browser pages proposing A and B; A's actual button sends A's ID
and gets 409 without creating either file; B's actual button writes only B.
Backend coverage also checks cancellation, missing/reused IDs, changed content or
order, changed model/target/session/setup/rules, changed material/rule-source bytes,
changed replacement targets and link substitution. The existing rollback test now
obtains a real bound plan before injecting a second-file replacement failure.

## Actual validation

Same isolated environment as step 1: Python 3.12, Node 24.22.1,
Playwright 1.51.0 / Chromium 134, Ruff 0.17.2, mypy 1.15.0.

| Check | Result |
|---|---|
| Step-two backend tests | 15 tests: 14 passed, 1 native Windows test skipped |
| Full unittest discovery | 97 tests: 83 passed, 13 failed, 1 skipped; no errors |
| Original 67 tests | All passed, including source immutability and rollback |
| Original R02/R04 audit assertions | Both now pass |
| Browser safety and two-page confirmation | Passed |
| Browser main user flow | Passed |
| Browser complete suite | 7 methods; 8 assertions still fail in R13/R14/R15; no errors |
| New/modified browser and step-two test files, full Ruff | Passed |
| Application fatal Ruff subset | Passed |
| Full Ruff | 274 findings remain; not passed |
| mypy, all nine modules | 50 errors in 6 files, unchanged count; not passed |
| compileall / git diff --check | Passed |

The 13 remaining backend failures belong to R05–R12/R14/R16. The eight browser
assertions are six draft-preservation language cases, one existing-card language
case and one 390px drawer geometry case. They were not skipped or converted to
expected failures. Step-two fixes do not imply release readiness.

Windows ACLs/reparse behavior and the real Bosch Endpoint remain unverified in
their native environments. Reparse metadata tests on Linux do not replace Windows
validation. All test materials, changes and writes were synthetic temporary data.
No ZIP was generated; the commit uses [skip ci].

Next report stage: step 3, R05 → R06 → R07 → R08. It was not implemented here.
The plan binding can be extended to the explicit persisted context schema/version
introduced in that stage.
