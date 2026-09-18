# Script map — chronological workflow

The existing scripts intentionally remain at their current paths. Several of
them import neighbouring modules or have documented commands that rely on
`scripts/` as the working directory. This map gives the directory a stable
chronological structure without breaking those entry points.

## 00 — Earlier reference and prototype scripts

- `Experimente_Anja_1_annotiert.py`
- `Gemini_HBG_classification_P1_20.py`
- `Gemini_HBG_classification_P1_P2_20.py`
- `Gemini_HBG_classification_test.py`
- `Google_native_connector_multiplefiles_1_original_annotated_redacted.py`
- `baugruppen_classification_with_files.py`
- `baugruppen_metadatenextraktion_annotiert.py`
- `inventory_generator.py`
- `pdf_image_converter.py`
- `zero_shot_classification.py`

These are retained as historical references or earlier experiment variants.

## 01 — Dataset collection and preparation

Run these before current classification experiments when preparing or checking
the BG corpus.

- `collect_HBG.py`
- `check_129bg_folder_coverage.py`
- `check_neu_bg_duplicates.py`
- `generate_HBG_file_inventory.py`
- `build_experiment_dataset.py`
- `create_visual_context_pdfs.py`

## 02 — Prompt development and PDF/file classification experiments

- `run_prompt_development.py`
- `run_classification.py` — current standard classification entry point
- `label_configuration_experiment.py`
- `check_llm_upload_size.py`
- `test_excel_upload.py`

## 03 — Text-only pipeline

Run in this order. The first step excludes the 14 BGs marked
`prompt_engineering = yes`; later steps use its inventory.

1. `classify_bg_files_text_only.py`
2. `extract_bg_facts_text_only.py`
3. `render_text_dossiers_text_only.py`
4. `run_text_dossier_classification.py`

## 04 — Evaluation and workshop analysis

- `evaluate_classification.py`
- `batch_evaluate_experiments.py` — offline recalculation only; does not call models
- `workshop_annotation_auswertung.py`

## 05 — Current shared connectors and reference material

- `llm_connector_with_prompt_caching.py` — current shared Farm connector
- `llm_connector_annotiert.py`
- `KI_API_guide_zh.md`
- `LLM_IGNORE_folder_guide_zh.md`
- `run_classification_中文完整标注.md`
- `task3_prompt_development.md`
- `task3_llm_experiment_status.md`

## 07 — Persistent terminal chat tool

`07_terminal_chat/` is deliberately standalone. It contains a reconstructed
connector copy, terminal chat with local file memory, its dependency list and
usage guide. It does not replace the current shared connector used by the
research scripts.
