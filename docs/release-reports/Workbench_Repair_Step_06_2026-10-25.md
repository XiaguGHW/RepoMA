# Release repair — step 6

Scope: repair report section 6, step 6, R12 only.
Starting main: 27abb0abb27d669cfbc6287fe65dd32dce932c0a.
Local and remote heads matched; the initial working tree was clean.
No ZIP generation or packaging workflow was requested or run.

## Answer-only incremental preview

request_runtime.AnswerPreview scans the root JSON object's string-valued answer
incrementally. It handles keys and Unicode escapes split across chunks, surrogate
pairs, newlines, code blocks and tables. It does not emit raw action JSON,
changes, classification objects or nested answer keys. The scanner uses bounded
key/prefix buffers and a configurable answer limit; it does not repeatedly parse
an ever-growing JSON buffer.

Chat SSE emits start/request_id, progress, answer_reset and answer_delta. Repairs
and supplemental rounds reset their temporary preview. A connected consumer gets
one final result or error and end after worker completion. The browser appends
preview text to a text node, with an explicit temporary/validation label. It
removes the preview on success, stop, disconnect or error. Only the final validated
result can create classification or reviewed change-plan cards.

The GUI now validates one complete action object (or one complete JSON fence),
rather than accepting an inner object from a truncated outer array or fence.
Truncated action-like text cannot become a natural-language fallback. Ordinary
read-only text fallback is retained; it has the same answer-size bound.

OpenAI streaming responses provide incremental content when the Farm deployment
supports it. Explicit stream rejection still falls back once when the attempt
budget allows. Gemini/Claude keep their current complete-response interfaces:
they show processing progress and a decoded completed answer, not purported
native token streaming. No real Bosch streaming capability was inferred or tested.

## Cancellation and final publication

Each operation has a RequestControl with cancellation, a monotonic deadline and
policy bounds. The stream watches actual HTTP disconnects and finalizes its
generator by signalling cancellation. The browser Stop button aborts its fetch
and also sends POST /api/chat/cancel with the request_id. Unknown IDs cannot stop
a different task. GET /api/chat/task/{request_id} reports state, done and
worker_alive; it does not wait for the global model-work lock.

The worker retains the shared task slot throughout response generation, transport
cleanup and cancellation unwinding. A separate joining reaper clears the slot
only after thread.join() returns. Closing the SSE consumer alone never clears
the slot. The browser waits for task completion before allowing its next chat;
the server independently rejects overlapping model/context work with 409.

Cancellation checks occur at dispatch, provider content, preparation progress,
repair/supplemental boundaries and immediately before final publication. Stop
exceptions propagate through dossier/preread fallback handlers. They cannot start
another repair/read after cancellation or save a new conversation, pending plan,
last_bg_analysis or result. Successful source-fact caches and consumed usage from
earlier work are retained and may be reused; they are not accepted answers.

Cancellation and the final history/plan/analysis publication share a guard. If
cancellation wins, publication is rejected. If the final publication already won,
the request remains completed; a later Stop does not undo the saved answer. The
UI explicitly distinguishes this case from a cancelled answer. The existing
confirmation requirement for applying a final reviewed plan remains unchanged.

## Bounded lifecycle

The model event queue holds at most 64 entries and applies cooperative backpressure.
Disconnect/cancellation/deadline checks break a blocked producer. Completion
progress cannot keep a committed worker blocked on an abandoned full queue.

Policy is read per operation and validated within these ranges:

| Environment variable | Default | Allowed range |
|---|---:|---:|
| WORKBENCH_REQUEST_TIMEOUT_SECONDS | 180 | 0.1–1800 |
| WORKBENCH_CONNECT_TIMEOUT_SECONDS | 5 | 0.05–60 |
| WORKBENCH_READ_TIMEOUT_SECONDS | 20 | 0.05–120 |
| WORKBENCH_MAX_ATTEMPTS | 3 | integer 1–3 |
| WORKBENCH_RETRY_BACKOFF_SECONDS | 1 | 0–5 |
| WORKBENCH_MAX_RESPONSE_CHARS | 262144 | integer 1024–2097152 |
| WORKBENCH_MAX_ANSWER_CHARS | 131072 | integer 256–1048576 |

The operation deadline includes automatic preparation and all later calls.
Transport connect/read timeouts are capped by the remaining budget. HTTP retries
use cancellable exponential backoff; no retry starts after cancellation/deadline.
OpenAI SDK implicit retries remain disabled, and the explicit streaming fallback
also respects a one-attempt policy. Pricing/accounting still records each actual
dispatch once, including stopped/failed calls and returned usage.

HTTP response reading checks its budget per available raw chunk. OpenAI response
streams are bounded before the SDK's SSE line decoder, preventing an unfinished
event that keeps receiving bytes from bypassing the deadline or byte cap. Provider
body bytes are capped at four times max_response_chars, and decoded model content
and answer text have their own character bounds. The SDK's bundled httpx/httpx2
transport is used for the compatible timeout and byte-stream types.

Cancellation is cooperative: an already-blocked socket read/connect can remain
active until its configured I/O timeout, then unwinds. Local parsing/disk work is
checked at operation boundaries. Threads are not force-killed and the slot is
never released on the assumption that an in-flight worker stopped. This does not
claim that Bosch has cancelled server-side generation or ceased billing.

## Validation

All documents, workspace paths and credentials are synthetic. Tests use loopback
HTTP, a live local Uvicorn server, Chromium and the real OpenAI SDK with a mock
transport. No real Bosch Endpoint or user materials were contacted.

- 18 new decoder/policy/lifecycle methods pass. They cover every split boundary,
  escaped Unicode, code/table chunks, nested/action-field exclusion, long answers,
  configuration bounds, cancellable backoff, a one-attempt policy, unterminated
  SSE events, real TCP disconnect, explicit stop, worker joining, rejection of
  overlapping work, retry, no subsequent repair/read, deadline, consumed usage,
  truncated outer JSON/fences and response/answer size rejection.
- The promoted R12 dropped-content regression now passes. Existing OpenAI partial
  stream, stream rejection/fallback, response-round/reference and usage regressions
  remain active and pass.
- Full discovery: 162 methods, 157 pass, 4 known later-step failures, 1 native
  Windows test skipped on Linux, no test errors. The remaining failures are R14
  English processing/notices and R16 env-file/CLI-port/unknown-option behavior.
- Browser: 12 methods, 9 pass; 3 retain 8 known R13/R14/R15 assertions (six editor
  language cycles, one existing-card translation, one 390px drawer). New tests
  verify visible text-only preview, Stop and busy state while a worker remains
  blocked, cleanup, retry, page-reload disconnect and truncated-response cleanup.
  Commands still exit nonzero for those known failures; no assertions were skipped
  or converted to expectedFailure.
- Fatal Ruff subset, full Ruff on request_runtime.py/new lifecycle tests/browser
  tests, Python compilation, JS syntax/catalog checks and git diff whitespace pass.
- Full Ruff remains non-green: 264 findings. Mypy remains non-green: 44 errors in
  6 files, with 10 application modules explicitly checked (including the new
  runtime). Existing broad lint/type debt is left for its scheduled stage.

The existing HTTP retry test now mocks RequestControl.pause instead of time.sleep,
retaining the same request/backoff count assertions. The local provider fixture
tolerates the expected closed response socket after a timeout or cancellation.

Final logs: /tmp/workbench-step6-unit-final.log,
/tmp/workbench-step6-browser-final.log, /tmp/workbench-step6-mypy-final.log,
/tmp/workbench-step6-ruff-final.log. Browser artifacts:
/tmp/workbench-step6-browser-final. These temporary artifacts are not committed.

## Handoff boundary

Step 6 is complete. Step 7 (R13 rule draft preservation, R14 dynamic localization,
R15 narrow-screen drawer geometry) has not been implemented. Native Windows and
real Bosch Endpoint behavior remain unverified. Continue from main and read this
report together with tools/release_audit/README.md before the next stage.
