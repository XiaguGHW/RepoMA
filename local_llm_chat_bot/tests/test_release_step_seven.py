"""R13/R14: synthetic draft isolation and explicit localized message records."""

import copy
import json
import re
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import chat_workbench as w
from fixture_support import FixtureEnvironment
from workbench_i18n import UIMessage, localize_message


class LocalizedMessages(unittest.TestCase):
    def test_only_explicit_ui_messages_translate(self):
        opaque = '原文 Baugruppe <tag> {pages} 中文规则'
        nested = UIMessage('model.context_group', 'zh', name=opaque, group=2)
        value = UIMessage('model.request_failed', 'zh', context=nested, detail=opaque)
        for language in ['zh', 'en', 'de']:
            result = localize_message(value, language)
            self.assertIn(opaque, result)
            self.assertEqual(result.params['detail'], opaque)
            self.assertIs(localize_message(opaque, language), opaque)
            payload = json.loads(json.dumps(result.payload()))
            self.assertEqual(payload['params']['context']['params']['name'], opaque)
            self.assertEqual(payload['message_key'], 'model.request_failed')


class DraftAndProgress(unittest.TestCase):
    def setUp(self):
        self.f = FixtureEnvironment().__enter__()
        self.addCleanup(self.f.__exit__, None, None, None)
        self.client = TestClient(w.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)
        self.post('/api/setup', {'workspace': str(self.f.workspace), 'model': 'gemini-2.5-pro', 'language': 'en'})

    def post(self, path, body):
        response = self.client.post(path, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_save_changes_only_app_draft_and_rejects_stale_version(self):
        source = self.f.rules.read_bytes()
        profile = self.post('/api/codebook/prepare', {'path': str(self.f.rules)})
        draft = copy.deepcopy(profile['draft'])
        draft['classes'][0]['definition'] = 'User text 中文 {count} bleibt unverändert'
        saved = self.post('/api/codebook/edit', {'draft': draft, 'confirmed': True, 'profile_version': profile['version']})
        self.assertEqual(saved['draft'], draft)
        self.assertNotEqual(saved['version'], profile['version'])
        self.assertEqual(self.f.rules.read_bytes(), source)
        stale = self.client.post('/api/codebook/edit', json={'draft': profile['draft'], 'confirmed': True, 'profile_version': profile['version']}, headers={'X-Workbench-Language': 'de'})
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertEqual(stale.json()['message_key'], 'rules.version_changed')
        self.assertNotRegex(stale.json()['detail'], r'[\u4e00-\u9fff]')
        self.assertEqual(self.client.get('/api/codebook').json()['draft'], draft)

    def test_unconfirmed_and_invalid_edits_leave_profile_unchanged(self):
        profile = self.post('/api/codebook/prepare', {'path': str(self.f.rules)})
        for draft, confirmed in [(profile['draft'], False), ({'classes': []}, True)]:
            response = self.client.post('/api/codebook/edit', json={'draft': draft, 'confirmed': confirmed,
                                                                     'profile_version': profile['version']})
            self.assertEqual(response.status_code, 400, response.text)
            self.assertTrue(response.json()['message_key'])
            self.assertEqual(self.client.get('/api/codebook').json(), profile)

    def test_error_header_selects_language_and_preserves_path(self):
        missing = str(self.f.root / 'Missing 中文 {count}.pdf')
        for language in ['zh', 'en', 'de']:
            response = self.client.post('/api/codebook/prepare', json={'path': missing}, headers={'X-Workbench-Language': language})
            self.assertEqual(response.status_code, 400, response.text)
            body = response.json()
            self.assertEqual(body['message_key'], 'error.file_missing')
            self.assertEqual(body['params']['path'], missing)
            self.assertIn(missing, body['detail'])

    def test_progress_notices_reuse_and_scope_carry_keys(self):
        self.post('/api/codebook/prepare', {'path': str(self.f.rules)})
        self.post('/api/codebook/lock', {})
        self.post('/api/target', {'target': str(self.f.bg_a), 'selected_paths': ['facts.txt']})
        for language in ['en', 'de']:
            self.post('/api/language', {'language': language})
            response = self.client.post('/api/chat/stream', json={'question': 'Classify this Baugruppe'})
            self.assertEqual(response.status_code, 200, response.text)
            events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
            progress = [e for e in events if e['type'] == 'progress']
            self.assertTrue(progress)
            self.assertTrue(all(e.get('message_key') for e in progress), progress)
            self.assertTrue(all(not re.search(r'[\u4e00-\u9fff]', e['text']) for e in progress), progress)
            result = next(e['data'] for e in events if e['type'] == 'result')
            self.assertTrue(result['notice_messages'])
            self.assertTrue(all(n.get('message_key') for n in result['notice_messages']))
            if language == 'de':
                self.assertIn('notice.dossier_reused', [n['message_key'] for n in result['notice_messages']])
            for item in result['coverage_summary']['files']:
                self.assertEqual(item['scope_message']['message_key'], 'material.scope_full')

    def test_structured_errors_keep_existing_secret_redaction(self):
        error = w.UIRequestError(UIMessage('model.request_failed', 'zh',
            context=UIMessage('model.context_main'), detail='offline-fixture-only'))
        result = w.error_copy(error, {'language': 'de'})
        self.assertNotIn('offline-fixture-only', str(result))
        self.assertNotIn('offline-fixture-only', json.dumps(result.payload()))
        self.assertEqual(result.payload()['params']['context']['message_key'], 'model.context_main')

    def test_cad_image_groups_expose_localizable_counts_without_changing_names(self):
        from PIL import Image
        folder = self.f.root / 'Bilder 中文 {count}'
        folder.mkdir()
        paths = []
        for index in range(5):
            path = folder / f'view-{index}.png'
            Image.new('RGB', (80, 60), color=(index * 30, 100, 120)).save(path)
            paths.append(path)
        for count, key in [(2, 'notice.image_group_full'), (5, 'notice.image_group_overview')]:
            w.ACTIVE['documents'].visual_paths([], self.f.root / 'visual-cache', bilder_images=paths[:count])
            report = w.ACTIVE['documents'].last_visual_report
            self.assertEqual(report['image_group_details'][0]['count'], count)
            for language in ['en', 'de']:
                notice = w.image_group_notices({'language': language}, report)[0]
                self.assertEqual(notice.message_key, key)
                self.assertEqual(notice.params['name'], folder.name)
                self.assertNotRegex(str(notice).replace(folder.name, ''), r'[\u4e00-\u9fff]')


if __name__ == '__main__':
    unittest.main()
