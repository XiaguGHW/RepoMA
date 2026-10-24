# Release repair — step 4

Scope: report section 6, step 4, R09 → R10.
Starting main: 56ea5d06800d8a4d0dff429d7d77f6d0a4c2a03a.
Initial tracked diff and untracked file list were empty.

## R09 — every response round uses the same validator

The main answer, repair and supplementary-file answer all pass through
validated_model_action. Any non-null classification requires full validation,
including in an explanation follow-up. Once an answer contains a classification,
later rounds cannot drop it to escape validation.

Each answer has one shared repair budget across its initial and supplementary
rounds. Each comparison model has its own one-repair budget. A still-invalid
classification/action raises a readable error; it does not become a raw-answer
fallback, an accepted change plan, a new history entry or last_bg_analysis.
A failed comparison model now reports ok=false without an accepted answer or
classification, while the next model can succeed independently.

Classification intent is an explicit request value, not a multilingual keyword
security decision. ChatRequest.require_classification defaults to true for BG
work. The composer has two translated options:

- Fixed-rule classification: a complete classification is required.
- Explanation follow-up: classification may be null, but any returned object is
  validated with exactly the same constraints.

The mode survives a language switch within the same confirmed context and resets
to classification when the confirmed context changes. It is disabled outside BG
mode. Evidence preparation remains based on the confirmed BG scope, independently
of the response mode. Ordinary non-BG text-answer fallback stays read-only; it
cannot accept an unlocked classification object or a write plan.

Validated follow-up classifications are returned rather than hidden based on a
keyword heuristic. Invalid classifications never create a validated result card.

## R10 — typed, source-grounded references

The validator explicitly checks single exact class labels, confidence enums,
alternative labels, uncertainty lists, string rule IDs and reference lists.
List/dict confidence values and other malformed fields return validation reasons
instead of unhashable/type errors. Unknown labels and rule IDs are not mapped by
similarity or string coercion.

Codebook rule pages must be positive JSON integers, belong to the cited rule or
boundary-rule page metadata, and exist in the actual indexed PDF page inventory.
Valid boundary rules from another class can be cited. The validator does not
restrict every rule to the chosen class.

For DOCX/TXT/nonpaged rules, codebook_rule_pages must be empty.
codebook_rule_refs carries actual supplied Codebook section/chunk labels.
The result card displays these references instead of pretending they are
physical pages. PDF pages and nonpaged references have separate prompt guidance.

BG citations must exactly copy supplied BG page/sheet/row/chunk labels and be
included in evidence_labels. Codebook labels cannot serve as BG evidence.
The server derives the reference manifest from trusted document IDs and supplies
it in every BG prompt; model output cannot redefine it.

These checks establish structure and provenance. They do not automatically prove
the engineering semantics of a classification or that a cited rule was interpreted
correctly.

## Fixture and regression updates

The loopback fixture now copies actual BG and Codebook labels from the reference
manifest and uses section refs for its DOCX rules. It no longer cites the first
arbitrary document as BG evidence or assigns a made-up physical DOCX page.
Its explanation-mode detection checks the explicit mode declaration rather than
mentions of the mode name in general protocol instructions.

New backend tests cover:

- Keyword-free Chinese/English/German follow-ups, repeatedly invalid labels,
  missing classifications after repair, explicit classification without
  language-specific keywords, and valid null-classification explanations.
- Invalid/truncated actions, supplementary-file failures, a repair budget shared
  across rounds, no changes/history/analysis update after failure, and isolation
  of one failed comparison model from a successful next model.
- Invalid field types, empty/multiple/unknown labels, fabricated or out-of-range
  pages, uncited BG refs, Codebook-only BG evidence, actual Excel ranges/text
  chunks, real nonpaged refs and valid cross-class boundary rules.
- A generated real PDF Codebook whose accepted page references are checked
  against its actual page inventory.

The browser regression checks real response-mode selection, its request payload,
language-switch preservation, nonpaged reference display, and reset when changing
the BG. All test files and writes use synthetic temporary data.

## Actual verification

Same isolated environment as prior steps: Linux / Python 3.12 / Node 24.22.1,
Playwright 1.51.0 with Chromium 134, Ruff 0.17.2 and mypy 1.15.0.

| Check | Result |
|---|---|
| New step-four tests within full discovery | All 18 methods passed |
| Full unittest discovery | 124 tests: 116 passed, 7 failed, 1 native Windows skip; no errors |
| Existing R09/R10 audit assertions | Both now pass |
| Original regression coverage | Passed, including context, backup/rollback, empty/truncated provider outputs and HTTP errors |
| Full browser suite | 9 methods: 6 passed; 3 fail with 8 known R13/R14/R15 assertions; no errors |
| New response-mode/reference browser test | Passed |
| Full Ruff on new backend and modified browser tests | Passed |
| Application fatal Ruff subset | Passed |
| Full Ruff | 268 findings remain; not green |
| mypy, all nine modules | 47 errors in 6 files remain; not green |
| compileall and git diff --check | Passed |

The seven remaining backend failures belong to R11, R12, R14 and R16.
The eight remaining browser assertions are six unsaved-draft language cases,
one old-language classification card and one 390px layout case. They were not
skipped or marked expected failures.

No real Bosch Endpoint/native Windows validation and no ZIP generation occurred.
The commit uses [skip ci]. Historical reports and prior-step records are retained.
Next report stage: step 5, R11 usage and cost accounting; it was not implemented.
