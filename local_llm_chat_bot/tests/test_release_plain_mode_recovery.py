"""F-09 plain answers survive a stray classification; F-05 removing rules allows reconfirmation."""

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import chat_workbench as w
from fixture_support import FixtureEnvironment


class Base(unittest.TestCase):
    def setUp(self):
        self.f = FixtureEnvironment().__enter__()
        self.addCleanup(self.f.__exit__, None, None, None)
        self.client = TestClient(w.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)
        self.post("/api/setup", {"workspace": str(self.f.workspace), "model": "gemini-2.5-pro", "language": "en"})

    def post(self, path, body):
        response = self.client.post(path, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()


class PlainMode(Base):
    def test_stray_classification_is_ignored_with_a_localized_notice(self):
        for stray in ({}, "", "text", []):
            with self.subTest(stray=stray):
                action = {"answer": "Plain answer", "classification": stray, "changes": [], "read_files": []}
                with patch.object(w.ACTIVE["llm"], "ask_about_files", return_value=json.dumps(action)):
                    result = self.post("/api/chat", {"question": "Explain the workspace"})
                self.assertEqual(result["answer"], "Plain answer")
                self.assertIsNone(result["classification"])
                self.assertIn("notice.classification_ignored",
                              [item.get("message_key") for item in result["notice_messages"]])
                self.assertEqual(w.ACTIVE["state"].data["history"][-1]["content"], "Plain answer")

    def test_real_classification_object_is_still_rejected_outside_bg_mode(self):
        action = {"answer": "x", "classification": {"label": "Anything"}, "changes": [], "read_files": []}
        with patch.object(w.ACTIVE["llm"], "ask_about_files", return_value=json.dumps(action)):
            response = self.client.post("/api/chat", json={"question": "Explain the workspace"})
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(w.ACTIVE["state"].data["history"], [])

    def test_bg_mode_still_validates_every_returned_classification(self):
        self.post("/api/codebook/prepare", {"path": str(self.f.rules)})
        self.post("/api/codebook/lock", {})
        self.post("/api/target", {"target": str(self.f.bg_a), "selected_paths": ["facts.txt"]})
        action = {"answer": "x", "classification": {}, "changes": [], "read_files": []}
        with patch.object(w.ACTIVE["llm"], "ask_about_files", return_value=json.dumps(action)):
            response = self.client.post("/api/chat", json={"question": "Explain only", "require_classification": False})
        self.assertEqual(response.status_code, 400, response.text)


class RuleRemoval(Base):
    def test_removed_rules_allow_plain_material_reconfirmation(self):
        self.post("/api/codebook/prepare", {"path": str(self.f.rules)})
        self.post("/api/codebook/lock", {})
        self.post("/api/target", {"target": str(self.f.bg_a), "selected_paths": ["facts.txt"]})
        self.assertEqual(self.client.delete("/api/codebook").status_code, 200)
        self.assertEqual(w.ACTIVE["state"].data["context_issue"], "rules_removed")
        self.assertIsNone(w.ACTIVE["state"].data.get("bg_context"))
        # Old scope must still be reconfirmed before any question ...
        response = self.client.post("/api/chat", json={"question": "Explain facts"})
        self.assertEqual(response.status_code, 409, response.text)
        # ... and reconfirmation now works directly, in ordinary mode.
        result = self.post("/api/target", {"target": str(self.f.bg_a), "selected_paths": ["facts.txt"]})
        self.assertFalse(result["classification"])
        self.assertEqual(w.ACTIVE["state"].data["context_issue"], "")
        answer = self.post("/api/chat", {"question": "Explain facts"})
        self.assertIsNone(answer["classification"])

    def test_changed_but_unlocked_rules_still_require_locking(self):
        self.post("/api/codebook/prepare", {"path": str(self.f.rules)})
        self.post("/api/codebook/lock", {})
        self.post("/api/target", {"target": str(self.f.bg_a), "selected_paths": ["facts.txt"]})
        self.post("/api/codebook/prepare", {"path": str(self.f.rules)})  # new draft, not locked
        response = self.client.post("/api/target", json={"target": str(self.f.bg_a), "selected_paths": ["facts.txt"]})
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["message_key"], "error.rules_lock")


if __name__ == "__main__":
    unittest.main(verbosity=2)
