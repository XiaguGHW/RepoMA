"""Bosch Farm connector: HTTP status, timeouts, usage, truncation, provider replies."""

from pathlib import Path
import sys

APP = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(APP), str(APP / "tests")]

from types import SimpleNamespace  # noqa: E402
import unittest  # noqa: E402
from unittest.mock import patch  # noqa: E402
import requests  # noqa: E402
import chat_workbench as w  # noqa: E402
from llm_connector_with_prompt_caching import LLMConnector  # noqa: E402
from release_safety import normalize_usage  # noqa: E402
from api_cases import DirectSessionCase  # noqa: E402


class TransportMatrix(unittest.TestCase):
    def test_http_status_retry_matrix(self):
        for status in [400, 401, 403, 404, 413, 429, 500, 502, 503, 504]:
            with self.subTest(status=status):
                llm = LLMConnector('gemini-test', 'private-fixture-key')
                response = SimpleNamespace(ok=False, status_code=status, text='private-fixture-key')
                with patch('requests.post', return_value=response) as post, patch('request_runtime.RequestControl.pause') as sleep:
                    answer = llm.ask_about_files([], 'fixture')
                self.assertEqual(post.call_count, 3 if status in {429, 500, 502, 503, 504} else 1)
                self.assertEqual(sleep.call_count, post.call_count - 1)
                self.assertIsNotNone(w.connector_failure(answer))
                self.assertNotIn('private-fixture-key', answer)

    def test_timeout_connection_invalid_json_empty_and_recovery(self):
        # The request never reached the provider: bounded retries are safe.
        # A read timeout may still be generating/billing: never re-dispatch it.
        for error, dispatches in ((requests.ConnectionError('connection'), 3),
                                  (requests.exceptions.ConnectTimeout('connect'), 3),
                                  (requests.exceptions.ReadTimeout('read'), 1),
                                  (requests.Timeout('timeout'), 1)):
            llm = LLMConnector('gemini-test', 'fixture')
            with patch('requests.post', side_effect=error) as post, patch('request_runtime.RequestControl.pause'):
                self.assertIsNotNone(w.connector_failure(llm.ask_about_files([], 'fixture')))
                self.assertEqual(post.call_count, dispatches)
        llm = LLMConnector('gemini-test', 'fixture')
        with patch('requests.post', return_value=SimpleNamespace(ok=True, json=lambda: [])) as post:
            self.assertIsNotNone(w.connector_failure(llm.ask_about_files([], 'fixture')))
            self.assertEqual(post.call_count, 1)
        good = {'candidates': [{'content': {'parts': [{'text': 'recovered'}]}, 'finishReason': 'STOP'}]}
        with patch('requests.post', return_value=SimpleNamespace(ok=True, json=lambda: good)):
            self.assertEqual(llm.ask_about_files([], 'fixture'), 'recovered')

    def test_provider_usage_missing_zero_invalid_and_thoughts(self):
        for raw in ({'prompt_tokens': 12, 'completion_tokens': 3}, {'input_tokens': 12, 'output_tokens': 3},
                    {'promptTokenCount': 12, 'candidatesTokenCount': 3}):
            u = normalize_usage(raw)
            self.assertEqual((u['input_tokens'], u['output_tokens'], u['total_tokens']), (12, 3, 15))
        self.assertIsNone(normalize_usage({})['input_tokens'])
        self.assertEqual(normalize_usage({'prompt_tokens': 0, 'completion_tokens': 0})['total_tokens'], 0)
        for value in (-1, 'bad', float('nan'), float('inf')):
            self.assertIsNone(normalize_usage({'input_tokens': value})['input_tokens'])
        self.assertEqual(normalize_usage({'candidatesTokenCount': 3, 'thoughtsTokenCount': 9})['output_tokens'], 12)

    def test_provider_truncation_and_empty_not_valid(self):
        for reason in ('MAX_TOKENS', 'SAFETY'):
            answer = LLMConnector._extract_gemini_text({'candidates': [{'finishReason': reason, 'content': {'parts': [{'text': '{"x":1}'}]}}]})
            self.assertIsNotNone(w.connector_failure(answer))
        llm = LLMConnector('claude-test', 'fixture')
        self.assertIsNotNone(w.connector_failure(llm._extract_claude_text({'stop_reason': 'max_tokens', 'content': [{'text': '{}'}]})))
        self.assertIsNotNone(w.connector_failure(LLMConnector._extract_gemini_text({})))


class ProviderReplies(DirectSessionCase):
    def test_gemini_text_skips_thought_and_joins_parts(self):
        reply = {'candidates': [{'content': {'parts': [{'text': 'private thought', 'thought': True},
                   {'text': 'A'}, {'text': 'B'}]}, 'finishReason': 'STOP'}]}
        self.assertEqual(LLMConnector._extract_gemini_text(reply), 'AB')

    def test_claude_thinking_block_does_not_hide_final_text(self):
        llm = LLMConnector('claude-test', 'fixture-only')
        self.assertEqual(llm._extract_claude_text({'content': [{'type': 'thinking', 'thinking': 'x'},
                         {'type': 'text', 'text': 'A'}, {'type': 'text', 'text': 'B'}]}), 'AB')


if __name__ == "__main__":
    unittest.main(verbosity=2)
