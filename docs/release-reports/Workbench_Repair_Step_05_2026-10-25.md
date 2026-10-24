# Release repair — step 5

Scope: repair report section 6, step 5, R11 only.
Starting main: 21e5b4018bd5ed7924c64b5313b0b910f65e7293.
Initial working tree was clean; remote main matched the local commit.
No ZIP generation or packaging workflow was requested or run.

## Unified request accounting

All session model work in chat_workbench.py now uses accounted_model_call:
Codebook page/section reading, merge and syntax repair; material prereading and
summary merges; BG dossier creation/rebuild; main answers, classification repairs
and supplemental file reads; each comparison model and its repair.

The connector records each dispatched HTTP/OpenAI request separately. A streamed
response updates the same entry as metadata arrives; chunks are not new requests.
Explicit stream fallback and HTTP retry attempts are separate entries. OpenAI
SDK-hidden retries are disabled (max_retries=0), so no unobservable SDK retry can
bypass this ledger. This also applies to connector consumers outside the GUI;
they no longer receive the SDK's implicit retries. Timeout/cancellation policy
remains for step 6.

Accounting runs in a finally block before output validation. Truncated responses,
invalid classifications, failed repair/merge calls and exceptions retain returned
usage. Error response bodies are inspected for usage too, including the response
body retained by the OpenAI SDK. A dispatched request without usable usage is
counted with unknown tokens/cost. These are request dispatch counts, not proof
that a provider billed or completed generation on a failed transport attempt.
The actual returned model ID determines each call's configured price when present.

Successful cached summaries and dossiers are reused without a request or charge.
Automatic prereading and dossier calls belong to the initiating chat turn as well
as the cumulative ledger. Removed the previous caller-side dossier/main/coverage
accounting to prevent duplicates. Comparison results retain consumed usage even
on failure and refresh cumulative UI status when comparison ends.

## Unknown counts and configured pricing

normalize_usage and summarize_usage preserve null for unknown/invalid required
token totals, retain known subtotals and expose usage_complete. Mixed known and
unknown calls cannot become a fully known total. Real zero counts remain zero.
State save/reload preserves nullable totals and known_input/known_output.

Pricing requires complete quantities and the required configured rates. Unknown
models and missing/invalid rates produce an unknown estimate; true zero rates
remain valid. Per-call calculation and cumulative addition use Decimal before
persisting numeric values; they do not round individual small charges to six
decimal places. The UI formats values only for display.

Canonical input tokens include cache reads/writes. Claude's separate uncached,
cache-read and cache-creation counts are combined once. OpenAI prompt cached_tokens
and Gemini cachedContentTokenCount are already part of prompt totals, so cached
counts are subtracted before charging uncached input. Repeated normalization is
idempotent. Cache charges use only cache_read_usd_per_million and
cache_write_usd_per_million from the matching pricing entry. Absent required cache
prices or invalid cache quantities leave the call's total cost unknown. Existing
public-price entries were not changed or supplemented with assumed cache rates.

Per-turn/comparison/Codebook totals expose cost_usd, cost_complete and
known_cost_usd. Cumulative estimated_cost_usd is explicitly a subtotal of fully
priced calls, with unpriced_requests/cost_complete. Status, usage cards, Codebook
cards, comparisons and session export show unknown totals and label known cost
subtotals. They do not display missing usage as free. Known subtotals do not
estimate partially priced components inside an incomplete call.

Historical calls omitted before this repair cannot be recovered from the old
counters. Existing history and known usage are preserved; legacy unpriced counters
are migrated conservatively rather than reconstructing unavailable quantities.

## Validation

All model traffic uses synthetic files and a loopback HTTP mock, or the real
OpenAI SDK with a local mock transport. No Bosch Endpoint or user materials used.

- 20 new accounting tests pass. The acceptance fixture dispatches 2 Codebook
  calls plus 2 comparison calls: requests=4, input=80, output=40,
  configured estimated cost=$0.000406.
- Coverage includes syntax/classification repairs, supplemental reads, preread/
  dossier/main failure, consumed comparison usage, transport retries, OpenAI
  stream fallback and final usage metadata, actual-model pricing, cache reuse,
  missing/mixed usage, persistence/export, zero prices, missing prices, cache
  semantics/prices, invalid quantities and cumulative precision.
- Full unittest discovery: 144 tests, 138 pass, 5 known later-step failures,
  1 native Windows test skipped on Linux, no errors. Both R11 audit regressions
  now pass. The remaining failures are R12 stream content, R14 English processing
  messages, and R16 env-file/CLI-port/unknown-option behavior. Assertions remain
  active; no expectedFailure or new skip was introduced.
- Browser: 10 methods, 7 pass; 3 methods retain 8 known R13/R14/R15 assertions
  (six editor-language cycles, one existing-card translation, one 390px drawer).
  The new unknown-usage test passes using real chat/rule/comparison UI controls
  and loopback responses. The browser command still exits nonzero for known bugs.
- Fatal Ruff subset, full Ruff on the new/modified structured browser/accounting/
  SDK test files, Python compilation, JS syntax/catalog checks and git diff
  whitespace checks pass.
- Complete Ruff: 265 findings; mypy: 44 errors in 6 files (9 checked). These
  existing broad gates remain non-green and are not claimed as release passes.

Final logs: /tmp/workbench-step5-unit-final.log,
/tmp/workbench-step5-browser-final.log, /tmp/workbench-step5-mypy-final.log,
/tmp/workbench-step5-ruff-final.log. Browser artifacts:
/tmp/workbench-step5-browser-final. Logs/artifacts are temporary and not committed.

## Handoff boundary

Step 5 is complete. Step 6 (R12: answer deltas, cancellation and bounded request
lifecycle) has not been implemented. Windows-native behavior and real Bosch
Endpoint behavior remain unverified. Continue from main and read this report
alongside tools/release_audit/README.md before executing the next stage.
