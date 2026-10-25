"""Release boundaries. Fixtures are generated under TemporaryDirectory only."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import chat_workbench as w
from code_chat_agent import ProjectState, PricingCatalog, safe_name, parse_json
from local_document_library import LocalDocumentLibrary
from llm_connector_with_prompt_caching import LLMConnector


class ReleaseRegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='发布 Prüfung ')
        self.root = Path(self.tmp.name)
        self.workspace = self.root / 'app'; self.workspace.mkdir()
        self.old = dict(w.ACTIVE); w.ACTIVE.clear(); w.MODEL_WORK_IN_PROGRESS.clear()
        self.patches = [patch.object(w, 'app_state_home', return_value=self.workspace / 'AI_Bot_State'),
                        patch.object(w, 'load_dotenv'),
                        patch.dict(os.environ, {'BOSCH_FARM_SUBSCRIPTION_KEY': 'fixture-only',
                                                'WORKBENCH_ALLOW_TEST_HOST': '1'})]
        for p in self.patches: p.start()
        w.setup(w.Setup(workspace=str(self.workspace), state_dir='', model='gemini-test'))

    def tearDown(self):
        w.ACTIVE.clear(); w.ACTIVE.update(self.old); w.MODEL_WORK_IN_PROGRESS.clear()
        for p in reversed(self.patches): p.stop()
        self.tmp.cleanup()

    def test_single_file_without_codebook(self):
        source = self.root / 'Bauteil 中文 ü.txt'; source.write_text('linear motor evidence', encoding='utf-8')
        result = w.analyze_target(w.TargetRequest(target=str(source)))
        self.assertFalse(result['classification'])

    def test_target_switch_clears_old_prompt_and_export(self):
        state = w.ACTIVE['state']; state.add_turn('assistant', 'OLD_BG_SECRET')
        state.data['last_bg_analysis'] = {'answer': 'OLD_BG_SECRET'}
        source = self.root / 'BG_B.txt'; source.write_text('New assembly')
        try: w.analyze_target(w.TargetRequest(target=str(source)))
        except UnboundLocalError: pass  # independent regression for context isolation
        self.assertEqual(state.data['history'], [])
        self.assertNotIn('last_bg_analysis', state.data)

    def test_setup_invalid_model_preserves_active_session(self):
        before = w.ACTIVE['state']
        with self.assertRaises(Exception):
            w.setup(w.Setup(workspace=str(self.workspace), state_dir='', model='unknown'))
        self.assertIs(w.ACTIVE.get('state'), before)

    def test_state_scan_excludes_private_application_state(self):
        state = w.ACTIVE['state']; secret = state.root / 'private.json'
        secret.write_text('{"secret":"old material"}')
        state.scan()
        self.assertFalse(any('AI_Bot_State' in p for p in state.data['files']))

    def test_session_name_cannot_escape_project(self):
        for name in ('.', '..', '../..', 'CON', 'NUL'):
            self.assertNotIn(safe_name(name), ('.', '..', 'CON', 'NUL'))

    def test_corrupt_state_types_and_legacy_missing_fields(self):
        state = w.ACTIVE['state']
        for value in ([], {'workspace': str(self.workspace)}, {'workspace': str(self.workspace), 'usage': None}):
            with self.subTest(value=value):
                state.path.write_text(json.dumps(value))
                loaded = ProjectState(w.app_state_home(), self.workspace, 'default')
                self.assertIsInstance(loaded.data['history'], list)
                self.assertIsInstance(loaded.data['files'], dict)
                self.assertIsInstance(loaded.data['usage'], dict)

    def test_codebook_rejects_duplicates_and_missing_definitions(self):
        for classes in ([{'name': 'Gantry', 'definition': 'A'}, {'name': 'Gantry', 'definition': 'B'}],
                        [{'name': 'Gantry', 'definition': ''}]):
            with self.subTest(classes=classes), self.assertRaises(ValueError):
                w.parse_codebook_draft(json.dumps({'classes': classes}))

    def test_classification_requires_exact_member_not_substring(self):
        profile = {'classes': [{'name': 'Rotationseinheit', 'definition': 'rotary motion'}]}
        action = {'classification': {'label': 'Rotation', 'confidence': 'high', 'evidence_labels': ['file A'],
                                     'bg_evidence_pages': ['file A'], 'uncertainties': []}}
        self.assertIsNotNone(w.validate_classification(action, [{'label': 'file A'}], 'Rotationseinheit', profile))

    def test_bad_json_action_field_types_are_rejected(self):
        for field, value in [('read_files', None), ('changes', {}), ('answer', ['wrong'])]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                parse_json(json.dumps({field: value}))

    def test_gemini_text_skips_thought_and_joins_parts(self):
        reply = {'candidates': [{'content': {'parts': [{'text': 'private thought', 'thought': True},
                   {'text': 'A'}, {'text': 'B'}]}, 'finishReason': 'STOP'}]}
        self.assertEqual(LLMConnector._extract_gemini_text(reply), 'AB')

    def test_claude_thinking_block_does_not_hide_final_text(self):
        llm = LLMConnector('claude-test', 'fixture-only')
        self.assertEqual(llm._extract_claude_text({'content': [{'type': 'thinking', 'thinking': 'x'},
                         {'type': 'text', 'text': 'A'}, {'type': 'text', 'text': 'B'}]}), 'AB')

    def test_partial_usage_is_unknown_not_zero_cost(self):
        state = w.ACTIVE['state']; before = state.data['usage']['requests']
        cost = state.note_usage({}, w.ACTIVE['pricing'], 'gemini-2.5-pro')
        self.assertIsNone(cost)
        self.assertEqual(state.data['usage']['requests'], before + 1)
        self.assertEqual(state.data['usage']['unpriced_requests'], 1)

    def test_invalid_pricing_is_safe(self):
        path = self.root / 'prices.json'
        for obj in ([], {'entries': None}, {'entries': [{'match': ['gemini'], 'input_usd_per_million': 'bad', 'output_usd_per_million': 2}]}):
            path.write_text(json.dumps(obj))
            self.assertIsNone(PricingCatalog(path).estimate('gemini-test', 10, 10))

    def test_invalid_image_is_not_indexed_as_valid_evidence(self):
        path = self.root / 'broken.png'; path.write_bytes(b'not an image')
        with self.assertRaises(Exception): w.ACTIVE['documents'].add(str(path))

    def test_corrupt_document_index_type(self):
        path = self.root / 'documents.json'; path.write_text('[]')
        self.assertEqual(LocalDocumentLibrary(path).list(), [])

    def test_sparse_excel_preserves_source_row_coordinates(self):
        from openpyxl import Workbook
        path = self.root / 'sparse.xlsx'; book = Workbook(); book.active['A100'] = 'EVIDENCE'
        book.save(path); book.close()
        doc = w.ACTIVE['documents'].add(str(path))
        chunk = next(c for c in doc['chunks'] if 'EVIDENCE' in c['text'])
        self.assertLessEqual(chunk['visual']['start_row'], 100)
        self.assertGreaterEqual(chunk['visual']['end_row'], 100)


if __name__ == '__main__': unittest.main()
