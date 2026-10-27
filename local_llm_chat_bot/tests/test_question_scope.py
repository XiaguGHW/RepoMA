"""Question scope (all files / one file) and the automatic classification decision."""

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import chat_workbench as w
from fixture_support import FixtureEnvironment


class QuestionScope(unittest.TestCase):
    def setUp(self):
        self.f = FixtureEnvironment().__enter__()
        self.addCleanup(self.f.__exit__, None, None, None)
        (self.f.bg_a / "drawing.txt").write_text(
            "FIXTURE_DRAWING: bracket, two bolts, gear housing.", encoding="utf-8"
        )
        self.client = TestClient(w.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)
        self.post("/api/setup", {"workspace": str(self.f.workspace), "model": "gemini-2.5-pro"})
        self.post("/api/codebook/prepare", {"path": str(self.f.rules)})
        self.post("/api/codebook/lock", {})
        self.post("/api/target", {"target": str(self.f.bg_a),
                                  "selected_paths": ["facts.txt", "drawing.txt"]})
        docs = {item["name"]: item["id"] for item in self.client.get("/api/documents").json()}
        self.facts_id, self.drawing_id = docs["facts.txt"], docs["drawing.txt"]

    def post(self, path, body):
        result = self.client.post(path, json=body)
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def ask_capturing(self, body, answer=None):
        """Ask once with a stubbed model and return (result, prompts sent)."""
        reply = json.dumps(answer or {"answer": "Stub", "read_files": [], "changes": [],
                                      "classification": None})
        with patch.object(w.ACTIVE["llm"], "ask_about_files", return_value=reply) as model:
            result = self.client.post("/api/chat", json=body)
        return result, [call.args[1] for call in model.call_args_list]

    def test_first_whole_material_question_requires_classification(self):
        result = self.post("/api/chat", {"question": "Classify this Baugruppe"})
        self.assertIsNotNone(result["classification"])
        self.assertEqual(result["scope"], {"kind": "all", "count": 2})

    def test_followup_without_mode_lets_the_model_decide(self):
        first = self.post("/api/chat", {"question": "Classify this Baugruppe"})
        analysis = w.ACTIVE["state"].data["last_bg_analysis"]
        result, prompts = self.ask_capturing({"question": "Explain the motor"})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertIsNone(result.json()["classification"])
        self.assertIn("- AUTO MODE:", prompts[-1])
        self.assertNotIn("- CLASSIFICATION REQUIRED:", prompts[-1])
        # An explanation turn keeps the exportable classification of the first turn.
        self.assertEqual(w.ACTIVE["state"].data["last_bg_analysis"], analysis)
        self.assertIsNotNone(first["classification"])

    def test_focus_uses_only_that_file_and_skips_whole_range_preparation(self):
        self.post("/api/chat", {"question": "Classify this Baugruppe"})
        result, prompts = self.ask_capturing(
            {"question": "What parts are on the drawing?", "focus_source_id": self.drawing_id})
        self.assertEqual(result.status_code, 200, result.text)
        payload = result.json()
        self.assertEqual(payload["scope"], {"kind": "file", "id": self.drawing_id, "name": "drawing.txt"})
        # One model call: no pre-read, no dossier, just the answer.
        self.assertEqual(len(prompts), 1)
        prompt = prompts[0]
        self.assertIn("FOCUS FILE", prompt)
        self.assertIn("drawing.txt", prompt)
        self.assertNotIn("FIXTURE_BG_A", prompt.split("Relevant locally extracted document excerpts:")[1]
                         .split("BG comprehensive evidence dossier")[0])
        self.assertTrue(all("facts.txt" not in item["name"] for item in payload["sources"]
                            if item.get("name") != self.f.rules.name))

    def test_focus_on_first_question_is_not_forced_to_classify(self):
        result, prompts = self.ask_capturing(
            {"question": "What parts are on the drawing?", "focus_source_id": self.drawing_id})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertIn("- AUTO MODE:", prompts[-1])

    def test_unknown_focus_is_rejected_without_a_model_call(self):
        result, prompts = self.ask_capturing({"question": "Explain", "focus_source_id": "not-a-material"})
        self.assertEqual(result.status_code, 409, result.text)
        self.assertEqual(prompts, [])
        self.assertEqual(w.ACTIVE["state"].data["history"], [])

    def test_explicit_mode_flags_still_work_for_api_clients(self):
        self.post("/api/chat", {"question": "Classify this Baugruppe"})
        _, prompts = self.ask_capturing({"question": "Explain", "require_classification": False})
        self.assertIn("- EXPLANATION MODE:", prompts[-1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
