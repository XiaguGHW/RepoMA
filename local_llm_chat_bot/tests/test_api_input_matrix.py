"""API inputs and files: invalid paths, model switch, origin checks, formats, selections."""

from pathlib import Path
import sys

APP = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(APP), str(APP / "tests")]

import os  # noqa: E402
import unittest  # noqa: E402
from unittest.mock import patch  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from openpyxl import Workbook  # noqa: E402
import chat_workbench as w  # noqa: E402
from api_cases import DirectSessionCase  # noqa: E402


class ApiAndFileMatrix(DirectSessionCase):
    def test_invalid_paths_blank_question_long_question_and_missing_key(self):
        with TestClient(w.app, raise_server_exceptions=False) as client:
            for payload in ({'target': ''}, {'target': str(self.root/'missing')}):
                self.assertEqual(client.post('/api/target', json=payload).status_code, 400)
            self.assertEqual(client.post('/api/chat', json={'question': ' '}).status_code, 400)
            self.assertEqual(client.post('/api/chat', json={'question': 'x'*50001}).status_code, 422)
            with patch.dict(os.environ, {'WORKBENCH_ALLOW_TEST_HOST': '1'}, clear=True):
                result = client.post('/api/setup', json={'workspace': str(self.workspace), 'model': 'gemini-test'})
                self.assertEqual(result.status_code, 400)
                self.assertIn('BOSCH_FARM_SUBSCRIPTION_KEY', result.json()['detail'])

    def test_model_switch_canonicalization_and_request(self):
        with TestClient(w.app) as client:
            for model in [' GEMINI-TEST ', 'claude-fixture', 'gpt-fixture']:
                result = client.post('/api/model', json={'model': model})
                self.assertEqual(result.status_code, 200)
                self.assertEqual(w.ACTIVE['llm'].model_name, model.strip().lower())
            for model in ['', 'gpt with spaces', 'unknown']:
                self.assertEqual(client.post('/api/model', json={'model': model}).status_code, 400)

    def test_model_slot_rejects_context_mutation_and_recovers(self):
        with TestClient(w.app) as client:
            w.MODEL_WORK_IN_PROGRESS.set()
            for route, payload in [('/api/model', {'model':'gemini-test'}), ('/api/target', {'target':str(self.root)}), ('/api/session/new', {}), ('/api/chat', {'question':'x'})]:
                self.assertEqual(client.post(route, json=payload).status_code, 409)
            w.MODEL_WORK_IN_PROGRESS.clear()
            with patch.object(w, 'call_model', side_effect=RuntimeError('fixture failure')):
                self.assertEqual(client.post('/api/chat', json={'question':'x'}).status_code, 400)
                self.assertFalse(w.MODEL_WORK_IN_PROGRESS.is_set())

    def test_cross_origin_and_host_rejected(self):
        with TestClient(w.app) as client:
            self.assertEqual(client.post('/api/model', json={'model':'gemini-test'}, headers={'Origin':'https://untrusted.example'}).status_code, 403)
            self.assertEqual(client.get('/api/settings', headers={'Host':'untrusted.example'}).status_code, 403)

    def test_all_declared_file_formats_and_source_immutability(self):
        import fitz
        from docx import Document
        from PIL import Image
        source = self.root/'材料 ü'
        source.mkdir()
        pdf = fitz.open()
        pdf.new_page().insert_text((30,30), 'Linear motor')
        pdf.save(source/'fixture.pdf')
        pdf.close()
        doc = Document()
        doc.add_paragraph('Linear motor')
        doc.save(source/'fixture.docx')
        book = Workbook()
        book.active['A1']='part'
        book.active['B2']='=1+1'
        book.active.merge_cells('C1:D1')
        book.save(source/'fixture.xlsx')
        book.close()
        for ext in ['png','jpg','jpeg','webp']:
            Image.new('RGB', (64,64), 'white').save(source/f'fixture.{ext}')
        for ext in ['csv','txt','md']:
            (source/f'fixture.{ext}').write_text('motor,linear\n1,2', encoding='utf-8')
        before = {p.name:p.read_bytes() for p in source.iterdir()}
        w.analyze_target(w.TargetRequest(target=str(source), selected_paths=['.']))
        self.assertEqual(len(w.ACTIVE['state'].data['active_source_ids']), len(before))
        self.assertEqual(before, {p.name:p.read_bytes() for p in source.iterdir()})

    def test_empty_corrupt_oversize_nested_duplicate_selection(self):
        folder=self.root/'BG'
        (folder/'nested').mkdir(parents=True)
        (folder/'nested'/'good.txt').write_text('technical motor')
        (folder/'bad.pdf').write_bytes(b'broken PDF')
        (folder/'empty.txt').write_text('')
        book=Workbook()
        book.save(folder/'blank.xlsx')
        book.close()
        x=w.analyze_target(w.TargetRequest(target=str(folder),selected_paths=['.','nested/good.txt']))
        self.assertEqual(x['sources'],1)
        self.assertEqual(x['skipped_count'],3)
        self.assertTrue(any('bad.pdf' in e for e in x['skipped']))
        with self.assertRaises(w.HTTPException):
            w.analyze_target(w.TargetRequest(target=str(folder),selected_paths=[]))
        from local_document_library import MAX_DOCUMENT_BYTES
        large=folder/'large.txt'
        with large.open('wb') as handle:
            handle.truncate(MAX_DOCUMENT_BYTES+1)
        with self.assertRaisesRegex(ValueError,'larger'):
            w.ACTIVE['documents'].add(str(large))

    def test_no_source_scope_means_no_old_documents(self):
        source=self.root/'old.txt'
        source.write_text('SECRET_OLD motor')
        w.ACTIVE['documents'].add(str(source))
        self.assertEqual(w.ACTIVE['documents'].search('motor', allowed_ids=[]), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
