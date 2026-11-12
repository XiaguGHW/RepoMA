"""No workspace to choose: an automatic session folder, adopted sessions, no code in prompts."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient  # noqa: E402
import chat_workbench as w  # noqa: E402
from fixture_support import FixtureEnvironment  # noqa: E402


class AutomaticSessionFolder(unittest.TestCase):
    def setUp(self):
        self.f = FixtureEnvironment().__enter__()
        self.addCleanup(self.f.__exit__, None, None, None)
        self.client = TestClient(w.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)

    def post(self, path, body):
        response = self.client.post(path, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_opens_without_a_workspace_and_sends_no_code(self):
        (w.app_state_home() / "workspace").mkdir(parents=True, exist_ok=True)
        status = self.post("/api/setup", {"model": "gemini-2.5-pro", "language": "de"})
        self.assertEqual(Path(status["workspace"]), (w.app_state_home() / "workspace").resolve())
        self.assertEqual(status["code_files"], 0)
        self.assertEqual(status["data_folder"], str(w.app_state_home()))
        self.post("/api/codebook/prepare", {"path": str(self.f.rules)})
        self.post("/api/codebook/lock", {})
        self.post("/api/target", {"target": str(self.f.bg_a), "selected_paths": ["facts.txt"]})
        before = len(self.f.calls)
        self.post("/api/chat", {"question": "Classify this Baugruppe"})
        prompts = json.dumps([call["body"] for call in self.f.calls[before:]])
        for marker in ("Indexed files and symbols", "Relevant code excerpts", "Complete current files", "Workspace:"):
            self.assertNotIn(marker, prompts)

    def test_sessions_of_an_earlier_workspace_are_adopted_once(self):
        self.post("/api/setup", {"workspace": str(self.f.workspace), "model": "gemini-2.5-pro", "language": "de"})
        self.post("/api/codebook/prepare", {"path": str(self.f.rules)})
        self.post("/api/codebook/lock", {})
        self.post("/api/target", {"target": str(self.f.bg_a), "selected_paths": ["facts.txt"]})
        self.post("/api/chat", {"question": "Classify this Baugruppe"})
        history = w.ACTIVE["state"].data["history"]
        self.assertTrue(history)
        status = self.post("/api/setup", {"model": "gemini-2.5-pro", "language": "de"})  # new page version
        self.assertEqual(status["code_files"], 0)
        self.assertFalse(status["context_issue"])
        self.assertEqual(w.ACTIVE["state"].data["history"], history)
        self.assertTrue(w.ACTIVE["state"].data.get("bg_context"))
        self.assertEqual(len(self.client.get("/api/documents").json()), 1)
        # Reopening keeps using the automatic folder, not the old one.
        self.assertEqual(Path(w.load_workbench_settings()["workspace"]), (w.app_state_home() / "workspace").resolve())


class StateHome(unittest.TestCase):
    def test_data_stays_next_to_the_program_unless_overridden(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(w.resolve_state_home({"WORKBENCH_STATE_DIR": root}), Path(root).resolve())
        self.assertEqual(w.resolve_state_home({"LOCALAPPDATA": "C:/Users/x/AppData/Local"}), w.LEGACY_STATE_HOME)
        self.assertEqual(w.LEGACY_STATE_HOME, Path(w.__file__).resolve().parent / "AI_Bot_State")


if __name__ == "__main__":
    unittest.main(verbosity=2)
