"""S-1--S-4: pre-release robustness regressions (synthetic loopback only)."""

import asyncio
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import chat_workbench as w
from fixture_support import FixtureEnvironment


class StepTen(unittest.TestCase):
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

    def prepare_bg(self):
        self.post("/api/codebook/prepare", {"path": str(self.f.rules)})
        self.post("/api/codebook/lock", {})
        self.post("/api/target", {"target": str(self.f.bg_a), "selected_paths": ["facts.txt"]})

    def test_comparison_never_uses_a_completed_but_stale_coverage_summary(self):
        self.prepare_bg()
        self.post("/api/coverage", {})
        coverage = w.load_coverage(w.ACTIVE["state"])
        coverage["context_revision"] = "stale-context-revision"
        coverage["files"][0]["summary"] = "STALE_COVERAGE_SENTINEL"
        w.write_json_atomically(w.coverage_path(w.ACTIVE["state"]), coverage)

        before = len(self.f.calls)
        self.post("/api/compare", {"question": "Classify this Baugruppe", "models": ["gemini-2.5-pro", "gemini-2.5-flash"]})
        prompts = str(self.f.calls[before:])
        self.assertNotIn("STALE_COVERAGE_SENTINEL", prompts)

    def test_changed_source_after_model_response_cannot_commit_old_result(self):
        self.prepare_bg()
        state = w.ACTIVE["state"]
        history = copy.deepcopy(state.data["history"])
        original = w.ACTIVE["llm"].ask_about_files

        def mutate_source_then_answer(*args, **kwargs):
            (self.f.bg_a / "facts.txt").write_text("Changed while the model was running.", encoding="utf-8")
            return original(*args, **kwargs)

        with patch.object(w.ACTIVE["llm"], "ask_about_files", side_effect=mutate_source_then_answer):
            response = self.client.post("/api/chat", json={"question": "Classify this Baugruppe"})
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(state.data["history"], history)
        self.assertEqual(w.ACTIVE["pending"], [])
        self.assertIsNone(state.data.get("last_bg_analysis"))

    def test_base_exception_in_worker_always_releases_model_slot(self):
        class NeverDisconnect:
            async def is_disconnected(self):
                return False

        class SynchronousThread:
            def __init__(self, *, target=None, daemon=False):
                self.target = target
                self.daemon = daemon
                self._alive = False

            def start(self):
                self._alive = True
                try:
                    self.target()
                except BaseException:
                    pass
                finally:
                    self._alive = False

            def join(self):
                return None

            def is_alive(self):
                return self._alive

        with patch.object(w, "call_model", side_effect=KeyboardInterrupt("fixture")), patch.object(w.threading, "Thread", SynchronousThread):
            asyncio.run(w.chat_stream(w.ChatRequest(question="Explain the workspace"), NeverDisconnect()))
        self.assertTrue(w.CHAT_TASK["done"].is_set())
        self.assertEqual(w.CHAT_TASK["state"], "failed")
        self.assertFalse(w.MODEL_WORK_IN_PROGRESS.is_set())

    def test_rule_edits_require_the_current_profile_version(self):
        profile = self.post("/api/codebook/prepare", {"path": str(self.f.rules)})
        before = w.codebook_profile_path().read_bytes()
        body = {"draft": profile["draft"], "confirmed": True}

        missing = self.client.post("/api/codebook/edit", json=body)
        self.assertEqual(missing.status_code, 400, missing.text)
        self.assertEqual(missing.json()["message_key"], "rules.version_required")
        self.assertEqual(w.codebook_profile_path().read_bytes(), before)

        stale = self.client.post("/api/codebook/edit", json={**body, "profile_version": "old-version"})
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertEqual(stale.json()["message_key"], "rules.version_changed")
        self.assertEqual(w.codebook_profile_path().read_bytes(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
