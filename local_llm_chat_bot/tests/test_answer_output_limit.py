"""A classification answer cut at its output limit is asked for once more,
explicitly shortened; a second cut fails clearly and saves nothing (synthetic)."""

import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient  # noqa: E402
import chat_workbench as w  # noqa: E402
from code_chat_agent import SYSTEM  # noqa: E402
from fixture_support import FixtureEnvironment  # noqa: E402

ANSWER_SYSTEM = "careful local workspace"


class AnswerOutputLimit(unittest.TestCase):
    def setUp(self):
        self.f = FixtureEnvironment().__enter__()
        self.addCleanup(self.f.__exit__, None, None, None)
        self.client = TestClient(w.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)
        self.post("/api/setup", {"workspace": str(self.f.workspace), "model": "claude-haiku-5-5", "language": "zh"})
        self.post("/api/codebook/prepare", {"path": str(self.f.rules)})
        self.post("/api/codebook/lock", {})
        self.post("/api/target", {"target": str(self.f.bg_a), "selected_paths": ["facts.txt"]})
        self.post("/api/coverage", {})

    def post(self, path, body):
        response = self.client.post(path, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def answer_calls(self, start=0):
        return [call["body"] for call in self.f.calls[start:] if ANSWER_SYSTEM in json.dumps(call["body"])]

    def cut_answers(self, count):
        state = {"left": count}

        def transform(response, prompt, system):
            if ANSWER_SYSTEM in system and state["left"] > 0:
                state["left"] -= 1
                response["candidates"][0]["finishReason"] = "MAX_TOKENS"
            return response
        self.f.response_transform = transform

    def test_cut_classification_answer_is_retried_once_shorter(self):
        self.cut_answers(1)
        before = len(self.f.calls)
        result = self.post("/api/chat", {"question": "根据分类规则判断当前Baugruppe类别"})
        self.assertEqual(result["classification"]["label"], "Rotationseinheit")
        calls = self.answer_calls(before)
        self.assertEqual([call["max_tokens"] for call in calls], [4096, w.ANSWER_RETRY_OUTPUT_TOKENS])
        self.assertNotIn("exceeded the output limit", json.dumps(calls[0]))
        self.assertIn("exceeded the output limit and was discarded", json.dumps(calls[1]))
        self.assertIn("notice.answer_shortened", [item["message_key"] for item in result["notice_messages"]])
        self.assertEqual(len(w.ACTIVE["state"].data["history"]), 2)

    def test_second_cut_fails_clearly_and_saves_nothing(self):
        self.cut_answers(2)
        before = len(self.f.calls)
        response = self.client.post("/api/chat", json={"question": "根据分类规则判断当前Baugruppe类别"})
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual((response.json()["message_key"], response.json()["params"]), ("model.answer_too_long", {"tokens": 8192}))
        self.assertNotIn("max_tokens", response.json()["detail"])  # a readable reason, not the raw connector text
        self.assertEqual(len(self.answer_calls(before)), 2)  # never a third attempt
        self.assertEqual(w.ACTIVE["state"].data["history"], [])
        self.assertFalse(w.MODEL_WORK_IN_PROGRESS.is_set())

    def test_classification_answer_length_is_bounded_in_the_prompt(self):
        self.assertNotIn("may exceed the normal length limit", SYSTEM)
        self.assertIn("at most about 1500 Chinese characters", SYSTEM)
        self.assertIn("The classification object must always be complete", SYSTEM)


if __name__ == "__main__":
    unittest.main(verbosity=2)
