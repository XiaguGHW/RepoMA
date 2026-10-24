"""R11: reconcile real loopback requests, unknown usage and configured prices."""

import json
from decimal import Decimal
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import chat_workbench as w
from code_chat_agent import PricingCatalog, ProjectState
from fixture_support import FixtureEnvironment, PROFILE
from llm_connector_with_prompt_caching import LLMConnector
from release_safety import normalize_usage, summarize_usage
from test_stream_progress import OpenAI, complete, httpx, stream_response


class UsageLedger(unittest.TestCase):
    def setUp(self):
        self.f = FixtureEnvironment().__enter__()
        self.addCleanup(self.f.__exit__, None, None, None)
        self.client = TestClient(w.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)
        self.post('/api/setup', {'workspace': str(self.f.workspace), 'model': 'gemini-2.5-pro'})

    def post(self, path, body):
        response = self.client.post(path, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def bg(self):
        self.post('/api/codebook/prepare', {'path': str(self.f.rules)})
        self.post('/api/codebook/lock', {})
        self.post('/api/target', {'target': str(self.f.bg_a), 'selected_paths': ['facts.txt']})

    def reconcile(self):
        usage = w.ACTIVE['state'].data['usage']
        self.assertEqual(usage['requests'], len(self.f.calls))
        self.assertEqual(usage['input'], len(self.f.calls) * 20)
        self.assertEqual(usage['output'], len(self.f.calls) * 10)
        return usage

    def test_codebook_two_and_comparison_two_are_exactly_four(self):
        self.bg()
        result = self.post('/api/compare', {'question': 'classify', 'models': ['gemini-2.5-pro', 'gemini-2.5-flash']})
        self.assertTrue(all(item['ok'] for item in result['results']))
        usage = self.reconcile()
        self.assertEqual((usage['requests'], usage['input'], usage['output']), (4, 80, 40))
        self.assertAlmostEqual(usage['estimated_cost_usd'], 0.000406)

    def test_preread_dossier_main_followup_and_cache_reuse(self):
        self.bg()
        first = self.post('/api/chat', {'question': 'classify'})
        self.assertEqual(first['turn_usage']['requests'], 3)
        self.assertEqual(first['turn_usage']['input'], 60)
        self.reconcile()
        second = self.post('/api/chat', {'question': 'Explain', 'require_classification': False})
        self.assertEqual(second['turn_usage']['requests'], 1)
        self.reconcile()
        before = len(self.f.calls)
        coverage = w.prepare_coverage(w.ACTIVE)
        w.prepare_bg_dossier(w.ACTIVE, coverage)
        self.assertEqual(len(self.f.calls), before)
        self.post('/api/cache/dossier/rebuild', {'confirmed': True})
        self.assertEqual(len(self.f.calls), before + 1)
        self.reconcile()

    def test_codebook_syntax_repair_is_counted_once(self):
        def transform(response, _prompt, system):
            if 'consolidate page-by-page' in system:
                response['candidates'][0]['content']['parts'][0]['text'] = '{broken'
            elif 'repair JSON syntax' in system:
                response['candidates'][0]['content']['parts'][0]['text'] = json.dumps(PROFILE)
            return response
        self.f.response_transform = transform
        profile = self.post('/api/codebook/prepare', {'path': str(self.f.rules)})
        self.assertEqual(len(self.f.calls), 3)
        self.assertEqual(profile['usage']['requests'], 3)
        self.reconcile()

    def test_classification_repair_and_supplementary_reads_are_counted_once(self):
        self.bg()
        self.post('/api/chat', {'question': 'classify'})
        (self.f.workspace / 'extra.txt').write_text('Full extra evidence', encoding='utf-8')
        counter = 0
        def transform(response, _prompt, system):
            nonlocal counter
            if 'careful local workspace' in system:
                counter += 1
                action = json.loads(response['candidates'][0]['content']['parts'][0]['text'])
                if counter == 1:
                    action['classification']['label'] = 'invalid'
                if counter == 2:
                    action['read_files'] = ['extra.txt']
                response['candidates'][0]['content']['parts'][0]['text'] = json.dumps(action)
            return response
        self.f.response_transform = transform
        result = self.post('/api/chat', {'question': 'classify again'})
        self.assertEqual(counter, 3)
        self.assertEqual(result['turn_usage']['requests'], 3)
        self.reconcile()

    def test_failed_comparison_keeps_consumed_usage(self):
        self.bg()
        self.f.response_transform = lambda response, *_: {**response, 'candidates': [{'finishReason': 'MAX_TOKENS'}]}
        result = self.post('/api/compare', {'question': 'classify', 'models': ['gemini-2.5-pro', 'gemini-2.5-flash']})
        self.assertTrue(all(not item['ok'] for item in result['results']))
        self.assertTrue(all(item['usage']['input'] == 20 for item in result['results']))
        self.reconcile()

    def test_failed_codebook_main_and_dossier_do_not_erase_consumed_usage(self):
        for location in ('codebook', 'main', 'dossier'):
            with self.subTest(location=location):
                if location != 'codebook':
                    self.bg()
                    if location == 'dossier':
                        coverage = w.prepare_coverage(w.ACTIVE)
                        w.bg_dossier_cache_path(coverage, w.ACTIVE['model']).unlink(missing_ok=True)
                before = len(self.f.calls)
                def transform(response, _prompt, system):
                    match = {'codebook': 'transcribe exactly one', 'main': 'careful local workspace',
                             'dossier': 'careful technical evidence consolidator'}[location]
                    if match in system:
                        response['candidates'][0]['finishReason'] = 'MAX_TOKENS'
                    return response
                self.f.response_transform = transform
                if location == 'codebook':
                    response = self.client.post('/api/codebook/prepare', json={'path': str(self.f.rules)})
                    self.assertEqual(response.status_code, 400)
                elif location == 'main':
                    response = self.client.post('/api/chat', json={'question': 'classify'})
                    self.assertEqual(response.status_code, 400)
                else:
                    result = self.post('/api/chat', {'question': 'classify'})
                    self.assertEqual(result['turn_usage']['requests'], 2)
                self.assertGreater(len(self.f.calls), before)
                self.reconcile()
                self.f.response_transform = None

    def test_missing_then_known_usage_survives_reload_and_export(self):
        self.f.response_transform = lambda response, *_: {k: v for k, v in response.items() if k != 'usageMetadata'}
        result = self.post('/api/chat', {'question': 'Explain'})
        self.assertIsNone(result['turn_usage']['input'])
        self.assertIsNone(result['turn_cost'])
        self.f.response_transform = None
        result = self.post('/api/chat', {'question': 'Explain again'})
        status = result['usage']
        self.assertIsNone(status['input_tokens'])
        self.assertEqual(status['known_input_tokens'], 20)
        self.assertIsNone(status['cost'])
        self.assertAlmostEqual(status['known_cost_usd'], 0.000125)
        old = w.ACTIVE['state']
        restored = ProjectState(old.private_state_root, old.workspace, old.root.name)
        self.assertEqual(restored.data['usage'], old.data['usage'])
        exported = w.write_session_export(w.ACTIVE).read_text(encoding='utf-8')
        self.assertIn('未知', exported)
        self.assertIn('小计', exported)

    def test_actual_response_model_controls_price(self):
        self.f.response_transform = lambda response, *_: {**response, 'modelVersion': 'gemini-2.5-flash'}
        result = self.post('/api/chat', {'question': 'Explain'})
        self.assertEqual(result['model_response'], 'gemini-2.5-flash')
        self.assertAlmostEqual(result['turn_cost'], 0.000031)

    def test_transport_retry_counts_each_attempt_and_partial_usage(self):
        for failed_usage in ({'promptTokenCount': 1, 'candidatesTokenCount': 2}, None):
            with self.subTest(failed_usage=failed_usage):
                connector = LLMConnector('gemini-2.5-pro', 'fixture-only')
                responses = [SimpleNamespace(ok=False, status_code=503, json=lambda: {'usageMetadata': failed_usage}),
                             SimpleNamespace(ok=True, json=lambda: {'candidates': [{'content': {'parts': [{'text': 'ok'}]}}],
                                                                    'usageMetadata': {'promptTokenCount': 20, 'candidatesTokenCount': 10}})]
                records = []
                before = w.ACTIVE['state'].data['usage']['requests']
                with patch('requests.post', side_effect=responses) as post, patch('time.sleep'):
                    self.assertEqual(w.accounted_model_call(w.ACTIVE, connector, [], 'question', usage_records=records), 'ok')
                self.assertEqual(post.call_count, 2)
                self.assertEqual(w.ACTIVE['state'].data['usage']['requests'] - before, 2)
                usage = summarize_usage(records)
                self.assertEqual(usage['known_input'], 21 if failed_usage else 20)
                self.assertEqual(usage['usage_complete'], bool(failed_usage))
                self.assertEqual(usage['cost_complete'], bool(failed_usage))

    def test_exception_records_usage_and_never_reuses_previous_call(self):
        connector = w.ACTIVE['llm']
        def failed(*_args, **_kwargs):
            connector.last_usage = {'input_tokens': 5, 'output_tokens': 2}
            raise RuntimeError('response failed after usage')
        with patch.object(connector, 'ask_about_files', side_effect=failed):
            with self.assertRaises(RuntimeError):
                w.accounted_model_call(w.ACTIVE, connector, [], 'question')
        with patch.object(connector, 'ask_about_files', side_effect=RuntimeError('no metadata')):
            with self.assertRaises(RuntimeError):
                w.accounted_model_call(w.ACTIVE, connector, [], 'question')
        usage = w.ACTIVE['state'].data['usage']
        self.assertEqual((usage['requests'], usage['known_input'], usage['known_output']), (2, 5, 2))
        self.assertIsNone(usage['input'])
        self.assertEqual(usage['unpriced_requests'], 1)

    def test_openai_fallback_and_stream_metadata_are_counted_per_dispatch(self):
        replies = [httpx.Response(400, json={'error': {'message': 'stream is not supported'},
                                           'usage': {'prompt_tokens': 1, 'completion_tokens': 0}}),
                   httpx.Response(200, json=complete()),
                   stream_response([{'content': 'ok'}, {'content': ' done'}])]
        requests = []
        def client(**kwargs):
            self.assertEqual(kwargs['max_retries'], 0)
            def handle(request):
                requests.append(request)
                return replies.pop(0)
            return OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handle)))
        with patch('llm_connector_with_prompt_caching.OpenAI', side_effect=client):
            for expected_count in (2, 1):
                records = []
                connector = LLMConnector('gpt-4.1', 'fixture-only')
                w.accounted_model_call(w.ACTIVE, connector, [], 'question', stream=True, usage_records=records)
                self.assertEqual(len(records), expected_count)
                self.assertEqual(summarize_usage(records)['known_input'], 21 if expected_count == 2 else 20)
        self.assertEqual(len(requests), 3)
        self.assertEqual(w.ACTIVE['state'].data['usage']['requests'], 3)

    def test_failed_preread_is_counted_even_when_chat_can_continue(self):
        self.bg()
        def transform(response, _prompt, system):
            if 'careful technical evidence extractor' in system:
                response['candidates'][0]['finishReason'] = 'MAX_TOKENS'
            return response
        self.f.response_transform = transform
        result = self.post('/api/chat', {'question': 'classify'})
        self.assertEqual(result['turn_usage']['requests'], 2)
        self.reconcile()


class UsagePricing(unittest.TestCase):
    def setUp(self):
        self.pricing = PricingCatalog(None)
        self.pricing.entries = [{'match': ['fixture'], 'input_usd_per_million': 2,
                                 'output_usd_per_million': 10}]

    def cost(self, raw):
        return self.pricing.estimate('fixture', None, None, usage=raw)

    def test_unknown_invalid_partial_and_true_zero(self):
        for raw in ({}, {'input_tokens': 3}, {'output_tokens': 2},
                    {'input_tokens': True, 'output_tokens': 2},
                    {'input_tokens': -1, 'output_tokens': 2}):
            with self.subTest(raw=raw):
                self.assertIsNone(self.cost(raw))
        self.assertEqual(self.cost({'input_tokens': 0, 'output_tokens': 0})['cost_usd'], 0)
        self.assertIsNone(self.pricing.estimate('unknown', 10, 10))

    def test_zero_price_is_real_zero_but_missing_price_is_unknown(self):
        entry = self.pricing.entries[0]
        entry.update(input_usd_per_million=0, output_usd_per_million=0)
        self.assertEqual(self.cost({'input_tokens': 30, 'output_tokens': 15})['cost_usd'], 0)
        for bad in (None, True, -1, float('nan'), float('inf')):
            entry['output_usd_per_million'] = bad
            self.assertIsNone(self.cost({'input_tokens': 30, 'output_tokens': 15}))

    def test_provider_cache_fields_and_normalization_are_idempotent(self):
        for raw in ({'input_tokens': 10, 'output_tokens': 4, 'cache_read_input_tokens': 20, 'cache_creation_input_tokens': 5},
                    {'prompt_tokens': 35, 'completion_tokens': 4, 'prompt_tokens_details': {'cached_tokens': 25}},
                    {'promptTokenCount': 35, 'candidatesTokenCount': 3, 'thoughtsTokenCount': 1, 'cachedContentTokenCount': 25}):
            usage = normalize_usage(raw)
            self.assertEqual(usage['input_tokens'], 35)
            self.assertEqual(usage['output_tokens'], 4)
            self.assertEqual(normalize_usage(usage), usage)
            self.assertEqual(summarize_usage([usage])['input'], 35)
            self.assertIsNone(self.cost(raw))  # No cache prices configured.

    def test_cache_prices_split_uncached_input_without_double_charging(self):
        self.pricing.entries[0].update(cache_read_usd_per_million=0.5, cache_write_usd_per_million=3)
        claude = self.cost({'input_tokens': 10, 'output_tokens': 4,
                            'cache_read_input_tokens': 20, 'cache_creation_input_tokens': 5})
        self.assertAlmostEqual(claude['cost_usd'], 0.000085)
        openai = self.cost({'prompt_tokens': 35, 'completion_tokens': 4, 'prompt_tokens_details': {'cached_tokens': 25}})
        self.assertAlmostEqual(openai['cost_usd'], 0.0000725)
        self.pricing.entries[0]['cache_read_usd_per_million'] = 0
        self.assertAlmostEqual(self.cost({'prompt_tokens': 35, 'completion_tokens': 4,
                                         'prompt_tokens_details': {'cached_tokens': 25}})['cost_usd'], 0.00006)

    def test_invalid_cache_count_and_cache_larger_than_prompt_are_unknown(self):
        for raw in ({'input_tokens': 10, 'output_tokens': 4, 'cache_read_input_tokens': None},
                    {'prompt_tokens': 10, 'completion_tokens': 4, 'prompt_tokens_details': {'cached_tokens': 11}},
                    {'promptTokenCount': 10, 'candidatesTokenCount': 4, 'cachedContentTokenCount': -1}):
            with self.subTest(raw=raw):
                self.assertFalse(normalize_usage(raw)['usage_complete'])
                self.assertIsNone(self.cost(raw))

    def test_summary_preserves_partial_counts_and_prices(self):
        known = normalize_usage({'input_tokens': 20, 'output_tokens': 10})
        known['cost_usd'] = 0.00014
        usage = summarize_usage([known, {'input_tokens': None, 'output_tokens': 3}])
        self.assertIsNone(usage['input'])
        self.assertEqual((usage['known_input'], usage['output']), (20, 13))
        self.assertFalse(usage['usage_complete'])
        self.assertIsNone(usage['cost_usd'])
        self.assertEqual(usage['known_cost_usd'], 0.00014)

    def test_accumulated_cost_does_not_round_each_small_call(self):
        with FixtureEnvironment() as fixture:
            state = ProjectState(fixture.root / 'state', fixture.workspace, 'precision')
            with patch.object(state, 'save'):
                for _ in range(1000):
                    state.note_usage({'input_tokens': 1, 'output_tokens': 1}, self.pricing, 'fixture')
            self.assertEqual(Decimal(str(state.data['usage']['estimated_cost_usd'])), Decimal('0.012'))
            self.assertEqual(state.data['usage']['requests'], 1000)

    def test_input_integer_precision_is_not_lost(self):
        self.assertEqual(normalize_usage({'input_tokens': 2**54 + 1, 'output_tokens': 0})['input_tokens'], 2**54 + 1)


if __name__ == '__main__':
    unittest.main()
