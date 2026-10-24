"""R12: answer-only previews, real disconnects and worker-owned cancellation."""

import copy
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
import uvicorn
import chat_workbench as w
from fixture_support import FixtureEnvironment
from llm_connector_with_prompt_caching import LLMConnector
from request_runtime import (AnswerPreview, RequestControl, RequestPolicy,
                             RequestCancelled, RequestTimedOut, ResponseLimitExceeded)
from test_stream_progress import OpenAI, httpx as sdk_httpx


def action(answer='Final answer', **extra):
    return json.dumps({'answer': answer, 'changes': [], 'read_files': [], **extra})


class AnswerDecoder(unittest.TestCase):
    def test_every_boundary_preserves_escapes_unicode_code_and_tables(self):
        answer = '中 ü 😀\n```python\nprint("hi\\there")\n```\n| A | B |\n|---|---|\n| 1 | 2 |'
        raw = action(answer, classification={'answer': 'NESTED_SECRET'}, changes=[{'content': 'CHANGE_SECRET'}])
        for boundary in range(len(raw) + 1):
            preview = AnswerPreview()
            self.assertEqual(preview.feed(raw[:boundary]) + preview.feed(raw[boundary:]), answer)
        preview = AnswerPreview()
        self.assertEqual(''.join(preview.feed(char) for char in raw), answer)

    def test_nested_keys_changes_and_classification_never_leak(self):
        raw = json.dumps({'changes': [{'answer': 'SECRET', 'content': 'SECRET'}],
                          'classification': {'answer': 'SECRET'}, 'answer': 'safe'})
        preview = AnswerPreview()
        self.assertEqual(''.join(preview.feed(char) for char in raw), 'safe')
        for raw in ('plain text {"answer":"SECRET"}', '[{"answer":"SECRET"}]'):
            self.assertEqual(AnswerPreview().feed(raw), '')

    def test_json_fences_and_split_encoded_answer_key(self):
        for prefix in ('', '```json\n', '```\n'):
            raw = prefix + '{"answ\\u0065r":"safe"}'
            preview = AnswerPreview()
            self.assertEqual(''.join(preview.feed(char) for char in raw), 'safe')

    def test_invalid_escape_surrogate_and_nonstring_answer_fail_closed(self):
        for raw in ('{"answer":null,"changes":["SECRET"]}', '{"answer":{"answer":"SECRET"}}',
                    '{"answer":"\\uDC00SECRET"}', '{"answer":"\\xSECRET"}'):
            self.assertEqual(AnswerPreview().feed(raw), '')

    def test_long_answer_is_linear_and_has_a_real_size_limit(self):
        answer = 'long ü text\n' * 8000
        raw = action(answer)
        preview = AnswerPreview(len(answer))
        self.assertEqual(''.join(preview.feed(raw[i:i+127]) for i in range(0, len(raw), 127)), answer)
        with self.assertRaises(ResponseLimitExceeded):
            AnswerPreview(100).feed(action(answer))


class RequestBounds(unittest.TestCase):
    def test_cancel_and_deadline_interrupt_waits_and_prevent_commit(self):
        control = RequestControl(RequestPolicy(timeout=.05))
        started = time.monotonic()
        with self.assertRaises(RequestTimedOut):
            control.pause(10)
        self.assertLess(time.monotonic() - started, .5)
        with self.assertRaises(RequestTimedOut), control.commit():
            self.fail('Timed-out work committed')
        control = RequestControl()
        control.cancel()
        with self.assertRaises(RequestCancelled), control.commit():
            self.fail('Cancelled work committed')

    def test_completed_commit_wins_a_later_cancel(self):
        control = RequestControl()
        with control.commit():
            pass
        self.assertFalse(control.cancel())
        control.check()

    def test_environment_policy_is_bounded_and_timeouts_use_remaining_budget(self):
        with patch.dict(os.environ, {'WORKBENCH_REQUEST_TIMEOUT_SECONDS': '.2',
                                     'WORKBENCH_MAX_ATTEMPTS': '1',
                                     'WORKBENCH_READ_TIMEOUT_SECONDS': '.1'}):
            control = RequestControl()
        self.assertEqual(control.policy.attempts, 1)
        connect, read = control.timeouts()
        self.assertLessEqual(connect, .2)
        self.assertLessEqual(read, .1)
        for field, value in [('MAX_ATTEMPTS', '4'), ('READ_TIMEOUT_SECONDS', 'inf'),
                             ('MAX_RESPONSE_CHARS', '0')]:
            with patch.dict(os.environ, {'WORKBENCH_' + field: value}):
                with self.assertRaises(ValueError):
                    RequestPolicy.from_env()

    def test_cancelled_backoff_cannot_dispatch_a_retry(self):
        connector = LLMConnector('gemini-2.5-pro', 'fixture-only')
        control = RequestControl()
        connector.request_control = control
        def fail(*_args, **_kwargs):
            control.cancel()
            return SimpleNamespace(ok=False, status_code=503, json=lambda: {})
        with patch('requests.post', side_effect=fail) as post:
            with self.assertRaises(RequestCancelled):
                connector.ask_about_files([], 'test')
        self.assertEqual(post.call_count, 1)

    def test_unfinished_openai_sse_event_cannot_bypass_deadline_or_byte_limit(self):
        for mode in ('timeout', 'limit'):
            with self.subTest(mode=mode):
                closed = threading.Event()
                pieces = []
                class Drip(sdk_httpx.SyncByteStream):
                    def __iter__(self):
                        yield b'data: {"never_finishes":"'
                        for _ in range(80):
                            threading.Event().wait(.01)
                            pieces.append(1)
                            yield b'x' * 1024
                    def close(self):
                        closed.set()
                def client(**kwargs):
                    return OpenAI(**kwargs, http_client=sdk_httpx.Client(
                        transport=sdk_httpx.MockTransport(lambda _: sdk_httpx.Response(
                            200, headers={'content-type': 'text/event-stream'}, stream=Drip())), trust_env=False))
                connector = LLMConnector('gpt-4.1', 'fixture-only')
                connector.request_control = RequestControl(RequestPolicy(
                    timeout=.1 if mode == 'timeout' else 2,
                    max_response_chars=262144 if mode == 'timeout' else 1024))
                started = time.monotonic()
                with patch('llm_connector_with_prompt_caching.OpenAI', side_effect=client):
                    with self.assertRaises(RequestTimedOut if mode == 'timeout' else ResponseLimitExceeded):
                        connector.ask_about_files([], 'test', stream=True)
                self.assertLess(time.monotonic() - started, .5)
                self.assertLess(len(pieces), 80)
                self.assertTrue(closed.is_set())

    def test_single_attempt_policy_disables_openai_stream_replay(self):
        requests = []
        def client(**kwargs):
            def handle(request):
                requests.append(request)
                return sdk_httpx.Response(400, json={'error': {'message': 'stream is not supported'}})
            return OpenAI(**kwargs, http_client=sdk_httpx.Client(
                transport=sdk_httpx.MockTransport(handle), trust_env=False))
        connector = LLMConnector('gpt-4.1', 'fixture-only')
        connector.request_control = RequestControl(RequestPolicy(attempts=1))
        with patch('llm_connector_with_prompt_caching.OpenAI', side_effect=client):
            self.assertTrue(connector.ask_about_files([], 'test', stream=True).startswith('Error:'))
        self.assertEqual(len(requests), 1)


class StreamLifecycle(unittest.TestCase):
    def setUp(self):
        self.f = FixtureEnvironment().__enter__()
        self.addCleanup(self.f.__exit__, None, None, None)
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))
        self.server = uvicorn.Server(uvicorn.Config(w.app, log_level='error'))
        self.server_thread = threading.Thread(target=self.server.run, kwargs={'sockets': [sock]}, daemon=True)
        self.server_thread.start()
        self.addCleanup(sock.close)
        self.addCleanup(self.stop_server)
        self.wait_until(lambda: self.server.started)
        self.client = httpx.Client(base_url=f'http://127.0.0.1:{sock.getsockname()[1]}', timeout=3, trust_env=False)
        self.addCleanup(self.client.close)
        self.post('/api/setup', {'workspace': str(self.f.workspace), 'model': 'gemini-2.5-pro'})
        self.release = threading.Event()
        self.addCleanup(self.release.set)
        self.old_history = copy.deepcopy(w.ACTIVE['state'].data['history'])

    def stop_server(self):
        self.server.should_exit = True
        self.server_thread.join(timeout=5)

    def wait_until(self, predicate, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.01)
        self.fail('Fixture condition did not complete')

    def post(self, path, body):
        response = self.client.post(path, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def events(self, response):
        self.assertEqual(response.status_code, 200)
        return (json.loads(line[6:]) for line in response.iter_lines() if line.startswith('data: '))

    def blocked(self, *_args, **kwargs):
        kwargs['event_handler']('content', '{"answer":"VISIBLE_')
        kwargs['event_handler']('content', 'PREVIEW","changes":[')
        self.release.wait(3)
        return action('VISIBLE_PREVIEW', read_files=['extra.txt'])

    def assert_uncommitted(self):
        self.assertEqual(w.ACTIVE['state'].data['history'], self.old_history)
        self.assertEqual(w.ACTIVE['pending'], [])
        self.assertFalse((self.f.workspace / 'must-not-write.txt').exists())

    def wait_done(self, request_id):
        self.wait_until(lambda: self.client.get('/api/chat/task/' + request_id).json()['done'])
        status = self.client.get('/api/chat/task/' + request_id).json()
        self.assertFalse(status['worker_alive'])
        self.assertFalse(w.MODEL_WORK_IN_PROGRESS.is_set())
        return status

    def test_delta_is_observable_before_result_and_final_result_is_unique(self):
        with patch.object(w.ACTIVE['llm'], 'ask_about_files', side_effect=self.blocked):
            with self.client.stream('POST', '/api/chat/stream', json={'question': 'explain'}) as response:
                events = self.events(response)
                start = next(events)
                self.assertEqual(start['type'], 'start')
                preview = []
                for event in events:
                    self.assertNotEqual(event['type'], 'result')
                    if event['type'] == 'answer_delta':
                        preview.append(event['text'])
                        if ''.join(preview) == 'VISIBLE_PREVIEW':
                            break
                self.assert_uncommitted()
                self.assertTrue(w.MODEL_WORK_IN_PROGRESS.is_set())
                self.release.set()
                tail = list(events)
        self.assertEqual(sum(item['type'] == 'result' for item in tail), 1)
        self.assertEqual(tail[-1]['type'], 'end')
        self.assertEqual(self.wait_done(start['request_id'])['state'], 'completed')

    def test_stop_holds_slot_until_actual_worker_exit_then_retry_works(self):
        (self.f.workspace / 'extra.txt').write_text('fixture', encoding='utf-8')
        with patch.object(w.ACTIVE['llm'], 'ask_about_files', side_effect=self.blocked) as model:
            with self.client.stream('POST', '/api/chat/stream', json={'question': 'explain'}) as response:
                events = self.events(response)
                request_id = next(events)['request_id']
                next(event for event in events if event['type'] == 'answer_delta')
                status = self.post('/api/chat/cancel', {'request_id': request_id})
                self.assertEqual(status['state'], 'cancelling')
                self.assertFalse(status['done'])
                self.assertTrue(status['worker_alive'])
                self.assertEqual(self.client.post('/api/chat', json={'question': 'overlap'}).status_code, 409)
                self.assertEqual(self.client.post('/api/chat/cancel', json={'request_id': 'wrong'}).status_code, 404)
                self.assert_uncommitted()
                self.release.set()
                tail = list(events)
            self.assertEqual(model.call_count, 1)
        self.assertFalse(any(event['type'] == 'result' for event in tail))
        self.assertEqual(next(event for event in tail if event['type'] == 'error')['code'], 'cancelled')
        self.assertEqual(self.wait_done(request_id)['state'], 'cancelled')
        self.assert_uncommitted()
        self.post('/api/chat', {'question': 'Retry after stop'})

    def test_real_tcp_disconnect_cancels_without_a_cancel_endpoint(self):
        with patch.object(w.ACTIVE['llm'], 'ask_about_files', side_effect=self.blocked) as model:
            with self.client.stream('POST', '/api/chat/stream', json={'question': 'disconnect'}) as response:
                events = self.events(response)
                request_id = next(events)['request_id']
                next(event for event in events if event['type'] == 'answer_delta')
                control = w.CHAT_TASK['control']
            self.assertTrue(control.cancel_event.wait(1), 'Disconnect did not reach the worker control')
            self.assertTrue(w.MODEL_WORK_IN_PROGRESS.is_set())
            self.release.set()
            self.assertEqual(self.wait_done(request_id)['state'], 'cancelled')
            self.assertEqual(model.call_count, 1)
        self.assert_uncommitted()

    def test_timeout_cannot_release_a_still_blocked_worker(self):
        with patch.dict(os.environ, {'WORKBENCH_REQUEST_TIMEOUT_SECONDS': '.15'}):
            with patch.object(w.ACTIVE['llm'], 'ask_about_files', side_effect=self.blocked):
                with self.client.stream('POST', '/api/chat/stream', json={'question': 'timeout'}) as response:
                    events = self.events(response)
                    request_id = next(events)['request_id']
                    next(event for event in events if event['type'] == 'answer_delta')
                    self.assertTrue(w.CHAT_TASK['control'].cancel_event.wait(1))
                    self.assertFalse(self.client.get('/api/chat/task/' + request_id).json()['done'])
                    self.assertTrue(w.MODEL_WORK_IN_PROGRESS.is_set())
                    self.release.set()
                    tail = list(events)
        self.assertEqual(next(event for event in tail if event['type'] == 'error')['code'], 'timeout')
        self.assertEqual(self.wait_done(request_id)['state'], 'timed_out')
        self.assert_uncommitted()

    def test_cancellation_prevents_supplementary_and_classification_repair(self):
        self.post('/api/codebook/prepare', {'path': str(self.f.rules)})
        self.post('/api/codebook/lock', {})
        self.post('/api/target', {'target': str(self.f.bg_a), 'selected_paths': ['facts.txt']})
        self.post('/api/chat', {'question': 'classify'})
        self.old_history = copy.deepcopy(w.ACTIVE['state'].data['history'])
        analysis = copy.deepcopy(w.ACTIVE['state'].data['last_bg_analysis'])
        def cancelled(*_args, **_kwargs):
            w.ACTIVE['llm'].request_control.cancel()
            return action('unvalidated', classification={'label': 'invalid'}, read_files=['extra.txt'],
                          changes=[{'path': 'must-not-write.txt', 'content': 'bad'}])
        with patch.object(w.ACTIVE['llm'], 'ask_about_files', side_effect=cancelled) as model:
            response = self.client.post('/api/chat/stream', json={'question': 'classify again'})
            self.assertEqual(model.call_count, 1)
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
        self.assertFalse(any(event['type'] == 'result' for event in events))
        self.assertEqual(next(event for event in events if event['type'] == 'error')['code'], 'cancelled')
        self.assertEqual(w.ACTIVE['state'].data['last_bg_analysis'], analysis)
        self.assert_uncommitted()

    def test_truncated_json_and_oversized_answer_cannot_be_committed(self):
        for raw, expected in [('{"answer":"partial","changes":[', 'failed'),
                              ('[' + action('truncated outer array'), 'failed'),
                              ('```json\n' + action('missing closing fence'), 'failed'),
                              (action('x' * 3000), 'limit')]:
            with self.subTest(expected=expected):
                def answer(*_args, **kwargs):
                    kwargs['event_handler']('content', raw)
                    return raw
                with patch.dict(os.environ, {'WORKBENCH_MAX_ANSWER_CHARS': '256'}), patch.object(w.ACTIVE['llm'], 'ask_about_files', side_effect=answer):
                    response = self.client.post('/api/chat/stream', json={'question': 'invalid'})
                events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
                self.assertFalse(any(event['type'] == 'result' for event in events))
                self.assertEqual(next(event for event in events if event['type'] == 'error')['code'], expected)
                self.assert_uncommitted()

    def test_real_http_read_is_bounded_and_no_retry_runs_after_deadline(self):
        def delayed(response, *_args):
            self.release.wait(.5)
            return response
        self.f.response_transform = delayed
        started = time.monotonic()
        with patch.dict(os.environ, {'WORKBENCH_REQUEST_TIMEOUT_SECONDS': '.15',
                                     'WORKBENCH_READ_TIMEOUT_SECONDS': '.1', 'WORKBENCH_MAX_ATTEMPTS': '3'}):
            response = self.client.post('/api/chat/stream', json={'question': 'slow provider'})
        self.release.set()
        self.assertLess(time.monotonic() - started, .8)
        self.assertEqual(len(self.f.calls), 1)
        self.assertEqual(w.ACTIVE['state'].data['usage']['requests'], 1)
        self.assertIn('"code": "timeout"', response.text)
        self.assert_uncommitted()


if __name__ == '__main__':
    unittest.main()
