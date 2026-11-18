"""Offline regressions: real SDK decoding against a local mock HTTP transport."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from openai import OpenAI
# Use the transport bundled with the installed SDK (httpx or httpx2).
from openai import _base_client

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import llm_connector_with_prompt_caching as connector

httpx = getattr(_base_client, "httpx2", None) or _base_client.httpx


def complete(content="已读取工作表。", reasoning="先检查工作簿结构。"):
    message = {"role": "assistant", "content": content}
    if reasoning is not None:
        message["reasoning_content"] = reasoning
    return {"id": "test", "object": "chat.completion", "created": 1,
            "model": "test-deepseek-deployment", "choices": [
                {"index": 0, "message": message, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}}


def stream_response(pieces, finished=True):
    events = []
    for delta in pieces:
        events.append({"id": "test", "object": "chat.completion.chunk", "created": 1,
                       "model": "test-deepseek-deployment", "choices": [
                           {"index": 0, "delta": delta, "finish_reason": None}]})
    if finished:
        events.append({"id": "test", "object": "chat.completion.chunk", "created": 1,
                       "model": "test-deepseek-deployment", "choices": [
                           {"index": 0, "delta": {}, "finish_reason": "stop"}]})
        events.append({"id": "test", "object": "chat.completion.chunk", "created": 1,
                       "model": "test-deepseek-deployment", "choices": [],
                       "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}})
    body = "".join("data: " + json.dumps(item, ensure_ascii=False) + "\n\n" for item in events)
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body + "data: [DONE]\n\n")


class StreamingTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.responses = []
        self.patch = patch.object(connector, "OpenAI", self.make_client)
        self.patch.start()
        self.logs = patch.object(connector.logging, "exception")
        self.logs.start()
        self.llm = connector.LLMConnector("deepseek-v4-flash-2026-04-23", "offline-test-only")

    def tearDown(self):
        self.patch.stop()
        self.logs.stop()

    def make_client(self, **kwargs):
        def handle(request):
            self.requests.append(json.loads(request.content))
            return self.responses.pop(0)
        kwargs.setdefault('max_retries', 0)
        return OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handle)))

    def test_default_request_keeps_nonstream_contract(self):
        self.responses = [httpx.Response(200, json=complete())]
        self.assertEqual(self.llm.ask_about_files([], "检查文件"), "已读取工作表。")
        self.assertNotIn("stream", self.requests[0])
        self.assertNotIn("thinking", self.requests[0])
        self.assertEqual(self.llm.last_reasoning, "先检查工作簿结构。")
        self.assertEqual(self.llm.last_response_model, "test-deepseek-deployment")

    def test_stream_keeps_reasoning_out_of_planner_json(self):
        planner = '{"tool_calls":[],"reply":"完成"}'
        self.responses = [stream_response([
            {"role": "assistant"}, {"reasoning_content": "先读取"},
            {"reasoning_content": "再判断。"}, {"content": planner[:10]}, {"content": planner[10:]},
        ])]
        events = []
        text = self.llm.ask_about_files([], "检查文件", stream=True, event_handler=lambda k, t: events.append((k, t)))
        self.assertEqual(text, planner)
        self.assertEqual(self.llm.last_reasoning, "先读取再判断。")
        self.assertEqual("".join(t for k, t in events if k == "content"), planner)
        self.assertEqual(self.llm.last_usage["total_tokens"], 30)

    def test_stream_rejection_falls_back_once_and_is_remembered(self):
        self.responses = [httpx.Response(400, json={"error": {"message": "stream is not supported"}}),
                          httpx.Response(200, json=complete()), httpx.Response(200, json=complete())]
        self.llm.ask_about_files([], "检查文件", stream=True)
        self.llm.ask_about_files([], "再检查", stream=True)
        self.assertEqual(len(self.requests), 3)
        self.assertTrue(self.requests[0]["stream"])
        self.assertNotIn("stream", self.requests[1])
        self.assertNotIn("stream", self.requests[2])

    def test_unrelated_error_does_not_retry_or_disable_thinking(self):
        self.responses = [httpx.Response(400, json={"error": {"message": "thinking is unsupported"}})]
        text = self.llm.ask_about_files([], "检查文件", stream=True, thinking="enabled")
        self.assertTrue(text.startswith("Error:"))
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0]["thinking"], {"type": "enabled"})
        self.assertFalse(self.llm._stream_rejected)

    def test_gemini_does_not_receive_openai_streaming_options(self):
        llm = connector.LLMConnector("gemini-2.5-pro", "offline-test-only")
        with patch.object(llm, "_http_post", return_value="中文回答") as post:
            self.assertEqual(llm.ask_about_files([], "问题", generation_config={"maxOutputTokens": 100}, stream=True, thinking="enabled"), "中文回答")
        payload = post.call_args.args[2]
        self.assertEqual(payload["generationConfig"], {"maxOutputTokens": 100})
        self.assertNotIn("stream", payload)
        self.assertNotIn("thinking", payload)


if __name__ == "__main__":
    unittest.main()

# Offline verification, from the downloaded standalone folder:
# 1) python -m pip install -r requirements.txt
# 2) python -m unittest discover -s tests -p "test_stream_progress.py" -v
# Tests use mock HTTP responses only; no .env, Farm credentials or real API calls.
