# Task 3 – Change Request: Regime-Aware Ground-Truth Evaluation

## Purpose

Please modify the evaluation/reporting code in 'run_prompt_development_with_prompt_caching.py' so that the results respect the three ground-truth regimes:

- 'E1': unambiguous and annotators agree
- 'E2': one intended class exists, but some human annotators made errors
- 'M': genuinely ambiguous; the primary ground truth and one or more explicitly recorded alternative valid labels may all be acceptable

The current implementation evaluates every row against only 'Ground Truth'. This must remain available as a **strict primary-label metric**, but it is insufficient for M cases.

The model must **not** receive 'Register', 'Weitere zulässige Ground Truth', or any accepted-label information in its prompt. This change is evaluation-only. Do not change prompts, model calls, caching, input preparation, existing raw outputs, or the source columns.

## Current relevant input columns

The dataframe/checkpoint already contains at least:

- 'Ground Truth'
- 'Register' (values include 'E1', 'E2', 'M')
- 'Weitere zulässige Ground Truth'
- 'Predicted_Label'
- 'Possible_Classes_If_Ambiguous'
- 'Confidence_Percent'
- 'SAP-Nummer', 'Teamcenter'
- 'Processing_Status', 'JSON_Parse_Status'

The project already has:

- 'clean_cell_text(...)'
- 'canonical_class_label(...)'
- 'LABEL_ALIASES'
- 'CANONICAL_CLASS_ORDER'

Continue using this canonicalization. In particular, 'Umsetzeinheit' and 'Kombinierte Einheit' must map to the same canonical class if that is already defined in 'LABEL_ALIASES'.

## Required evaluation semantics

### 1. Strict primary-label evaluation (keep)

For every evaluable row:

~~~
strict_primary_correct = canonical_prediction == canonical_primary_ground_truth
~~~

This is the existing logic. Keep it and clearly label it as **strict primary-label** evaluation.

- E1 and E2: this is the normal official correctness decision.
- M: report it too, but only as the stricter/descriptive view.

### 2. Accepted-label-set evaluation (new; M only)

For an M row, define:

~~~
accepted_labels = {primary Ground Truth} ∪ {all valid labels explicitly listed in Weitere zulässige Ground Truth}
accepted_set_correct = canonical_prediction in accepted_labels
~~~

For E1 and E2, do **not** broaden labels:

~~~
accepted_labels = {primary Ground Truth}
accepted_set_correct == strict_primary_correct
~~~

Important:

- Do **not** globally treat 'Roboter' and 'Kombinierte Einheit' as equivalent.
- An alternative label is accepted only for the specific M row where it is explicitly recorded in 'Weitere zulässige Ground Truth'.
- Do not overwrite or modify the original 'Ground Truth' column.

### 3. Alternative-label reporting by the model (new; M only)

For M rows, separately evaluate whether the model explicitly reported another accepted class in 'Possible_Classes_If_Ambiguous'.

Recommended definition:

~~~
allowed_alternatives = accepted_labels - {canonical_prediction}
m_alternative_reported = bool(
    parsed_possible_classes.intersection(allowed_alternatives)
)
~~~

Only calculate this for M rows where at least one explicit alternative label exists. It is an **ambiguity-recognition metric**, not a replacement for classification correctness.

'Possible_Classes_If_Ambiguous' may be a JSON list, a Python-like list, or text. Parse it robustly; canonicalize every parsed label with 'canonical_class_label'; safely return an empty set for empty/malformed values. Do not make the whole run fail because one row is malformed.

## Required code changes

### A. Add small helper functions

Add helpers close to 'canonical_class_label', for example:

1. 'canonicalize_label_collection(value) -> set[str]'
   - accepts a cell value with one or more labels;
   - handles null/empty values;
   - supports JSON lists and common separators such as newline, semicolon, comma, and pipe;
   - does not accidentally split the alias 'Umsetzeinheit/Kombinierte Einheit' into two unrelated labels;
   - canonicalizes each extracted label;
   - ignores unknown/empty labels safely.

2. 'parse_possible_classes(value) -> set[str]'
   - safely parses the model output field 'Possible_Classes_If_Ambiguous';
   - handles a real list, a JSON list string, and simple text;
   - returns canonical labels only.

Please use 'ast.literal_eval' and/or 'json.loads' safely if needed; never use 'eval'.

### B. Modify 'write_prompt_evaluation_sheet(...)'

When looping through 'selected.iterrows()', read:

~~~
register = clean_cell_text(row.get("Register")).upper()
primary_raw = clean_cell_text(row.get("Ground Truth"))
alternative_raw = clean_cell_text(row.get("Weitere zulässige Ground Truth"))
possible_classes_raw = row.get("Possible_Classes_If_Ambiguous")
~~~

Compute and retain at least these fields in each 'cases.append({...})' record:

~~~
Register
Ground_Truth_Primary
Weitere_zulaessige_Ground_Truth
Accepted_Labels                 # readable text, e.g. "Roboter | Kombinierte Einheit"
Strict_Primary_Status           # CORRECT / INCORRECT / NOT_EVALUABLE...
Accepted_Set_Status             # CORRECT / INCORRECT / NOT_EVALUABLE...
M_Alternative_Reported          # True / False / blank or N/A
~~~

Keep the existing 'Evaluation_Status' only for backward compatibility if necessary, but its meaning must be unambiguous. Preferred mapping:

~~~
Evaluation_Status = Strict_Primary_Status
~~~

The existing summary, per-class metrics, and ordinary confusion matrix must use the strict primary-label view unless they are explicitly named as regime-aware.

### C. Extend the 'Prompt_Evaluation' sheet

Keep the existing strict overall result, but rename/label it clearly:

- 'Strict primary-label accuracy'
- 'Strict correct predictions'

Add a second section titled e.g. **Regime-aware result** with:

- 'E1: n, strict accuracy'
- 'E2: n, strict accuracy'
- 'M: n'
- 'M strict primary-label accuracy'
- 'M accepted-label-set accuracy'
- 'M cases with explicit alternative label'
- 'M alternative reported rate' (numerator/denominator and/or percentage)
- 'All cases accepted-label-set accuracy' (optional but useful; for E1/E2 it equals strict)

Use only evaluable records in denominators. Show 'N/A' / blank rather than divide by zero.

Update the case-by-case table to include at least:

~~~
SAP-Nummer
Teamcenter
Register
Ground Truth (primary)
Weitere zulässige Ground Truth
Accepted Labels
Predicted_Label
Strict_Primary_Status
Accepted_Set_Status
M_Alternative_Reported
Possible_Classes_If_Ambiguous
Processing_Status
JSON_Parse_Status
Confidence_Percent
~~~

Use separate fill colors or clear text so that strict and accepted-set results cannot be confused.

### D. Confusion matrix

Do not put multi-label acceptance directly into a normal single-label confusion matrix.

Create/keep:

1. **Strict primary-label confusion matrix**
   - rows = primary 'Ground Truth'
   - columns = 'Predicted_Label'
   - can include all E1/E2/M rows, but title must say “strict primary-label”.

2. **E1+E2 strict confusion matrix** (recommended)
   - rows = primary ground truth
   - columns = prediction
   - excludes M, because E1/E2 are unambiguous intended-label cases.

3. **M acceptance summary table** (new; not a matrix)
   - total evaluable M cases
   - strict-primary correct
   - accepted primary label
   - accepted alternative label
   - not in accepted-label set
   - accepted-label-set accuracy
   - alternative-reporting rate, where applicable

A model prediction of an explicitly allowed M alternative should not be displayed as a red “wrong” result in the M acceptance summary. It remains an 'INCORRECT' strict-primary prediction.

### E. Confidence analysis

The current 'write_confidence_analysis_sheet(...)' separates data via the old 'Evaluation_Status' only. Preserve a strict view, then add regime-aware views.

At minimum provide:

1. **Strict primary-label confidence distribution**
   - correct vs incorrect based on 'Strict_Primary_Status'.

2. **M accepted-label-set confidence distribution**
   - correct vs incorrect based on 'Accepted_Set_Status', M rows only.

3. **High-confidence error tables**
   - strict high-confidence errors: 'Strict_Primary_Status == "INCORRECT"';
   - M accepted-set high-confidence errors: 'Register == "M"' and 'Accepted_Set_Status == "INCORRECT"'.

Do not label a prediction as an accepted-set error when it is an explicitly allowed alternative on that M row.

Keep the current 85% threshold only as a descriptive display threshold. It must not be presented as a validated automatic-acceptance threshold, especially because the current experiments contain incorrect predictions with very high confidence.

### F. Preserve compatibility and robustness

- Do not alter 'Ground Truth', 'Register', or 'Weitere zulässige Ground Truth' in the input Excel.
- Do not change the 14-BG prompt-development selection rule ('prompt_engineering == "yes"').
- Existing P1–P4 output workbooks should still be readable and evaluable.
- Empty alternative-label cells are normal.
- Unknown labels and malformed possible-class strings should result in a row-level NOT_EVALUABLE/empty secondary field when necessary, not a crash.
- Keep all Excel formatting behaviour (title, headers, widths, filters, freeze panes) as far as practical.
- Update the function call chain only as needed. For example, 'write_prompt_evaluation_sheet' can continue returning 'case_frame', and the confusion/confidence functions can consume the added columns.

## Expected interpretation example

Input:

~~~
Register: M
Ground Truth: Roboter
Weitere zulässige Ground Truth: Kombinierte Einheit
Predicted_Label: Kombinierte Einheit
~~~

Expected outcome:

~~~
Strict_Primary_Status: INCORRECT
Accepted_Set_Status: CORRECT
~~~

This does **not** mean that Roboter and Kombinierte Einheit are generally interchangeable. It is accepted only for this specific M row because the alternative was explicitly recorded.

## Deliverable

Please provide the modified code (preferably complete replacement versions of the changed functions plus any new helpers), explain briefly where each change belongs, and identify any assumptions about the exact storage format of 'Possible_Classes_If_Ambiguous'. Do not silently change historical results: the output must explicitly show both strict and regime-aware metrics.
