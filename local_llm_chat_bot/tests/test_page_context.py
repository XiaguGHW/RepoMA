"""F-04: a stale page must not act in another tab's session/context (synthetic only)."""

import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import chat_workbench as w
from fixture_support import FixtureEnvironment

HEADER = "X-Workbench-Context"


class PageContext(unittest.TestCase):
    def setUp(self):
        self.f = FixtureEnvironment().__enter__()
        self.addCleanup(self.f.__exit__, None, None, None)
        self.client = TestClient(w.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)
        response = self.client.post("/api/setup", json={"workspace": str(self.f.workspace),
                                                        "model": "gemini-2.5-pro", "language": "en"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.headers.get(HEADER))
        self.post("/api/codebook/prepare", {"path": str(self.f.rules)})
        self.post("/api/codebook/lock", {})
        self.page_a = self.post("/api/target", {"target": str(self.f.bg_a), "selected_paths": ["facts.txt"]},
                                token=True)

    def post(self, path, body, token=False, headers=None):
        response = self.client.post(path, json=body, headers=headers or {})
        self.assertEqual(response.status_code, 200, response.text)
        return response.headers[HEADER] if token else response.json()

    def snapshot(self):
        state = w.ACTIVE["state"]
        return copy.deepcopy(state.data), state.transcript_path.read_bytes() if state.transcript_path.exists() else b""

    def make_page_a_stale_by_other_tab(self):
        """Tab B opens a new session and confirms BG_B; tab A still holds its old token."""
        self.post("/api/session/new", {})
        self.page_b = self.post("/api/target", {"target": str(self.f.bg_b), "selected_paths": ["facts.txt"]},
                                token=True)
        self.assertNotEqual(self.page_a, self.page_b)

    def stale(self, method, path, body=None):
        before_calls = len(self.f.calls)
        before = self.snapshot()
        response = self.client.request(method, path, json=body, headers={HEADER: self.page_a})
        self.assertEqual(response.status_code, 409, (path, response.text))
        self.assertEqual(response.json().get("message_key"), "context.stale_page")
        self.assertEqual(response.headers.get("X-Workbench-Stale"), "1")
        self.assertEqual(len(self.f.calls), before_calls, path)
        self.assertEqual(self.snapshot(), before, path)
        self.assertFalse(w.MODEL_WORK_IN_PROGRESS.is_set())

    def test_stale_page_cannot_run_model_work_in_another_session(self):
        self.make_page_a_stale_by_other_tab()
        for path, body in [("/api/chat", {"question": "Classify this Baugruppe"}),
                           ("/api/chat/stream", {"question": "Classify this Baugruppe"}),
                           ("/api/compare", {"question": "classify", "models": ["gemini-2.5-pro", "gemini-2.5-flash"]}),
                           ("/api/coverage", {}),
                           ("/api/cache/dossier/rebuild", {"confirmed": True}),
                           ("/api/codebook/prepare", {"path": str(self.f.rules)})]:
            with self.subTest(path=path):
                self.stale("POST", path, body)

    def test_stale_page_cannot_change_the_other_context(self):
        self.make_page_a_stale_by_other_tab()
        for method, path, body in [("POST", "/api/target", {"target": str(self.f.bg_a), "selected_paths": ["facts.txt"]}),
                                   ("POST", "/api/model", {"model": "gemini-2.5-flash"}),
                                   ("DELETE", "/api/bg", None),
                                   ("POST", "/api/codebook/lock", {}),
                                   ("DELETE", "/api/codebook", None),
                                   ("POST", "/api/session/delete", {"confirmed": True}),
                                   ("POST", "/api/session/rename", {"name": "renamed"}),
                                   ("POST", "/api/apply", {"confirmed": True, "plan_id": "x"}),
                                   ("DELETE", "/api/pending", None),
                                   ("POST", "/api/cache/clear", {"confirmed": True}),
                                   ("POST", "/api/export/session", {})]:
            with self.subTest(path=path, method=method):
                self.stale(method, path, body)

    def test_current_page_and_rebinding_navigation_still_work(self):
        self.make_page_a_stale_by_other_tab()
        # Tab B (current token) works and classifies BG_B.
        response = self.client.post("/api/chat", json={"question": "Classify this Baugruppe"},
                                    headers={HEADER: self.page_b})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("FIXTURE_BG_B", str(self.f.calls[-1]))
        # A stale page may still stop work and re-bind by opening a session.
        self.assertNotEqual(self.client.post("/api/language", json={"language": "de"}, headers={HEADER: self.page_a}).status_code, 409)
        opened = self.client.post("/api/session/open", json={"name": "default"}, headers={HEADER: self.page_a})
        self.assertEqual(opened.status_code, 200, opened.text)
        rebound = opened.headers[HEADER]
        response = self.client.post("/api/chat", json={"question": "Classify this Baugruppe"}, headers={HEADER: rebound})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("FIXTURE_BG_A", str(self.f.calls[-1]))

    def test_same_page_sequence_learns_each_new_token(self):
        """A page that changes context itself continues with the token from that response."""
        token = self.post("/api/model", {"model": "gemini-2.5-flash"}, token=True, headers={HEADER: self.page_a})
        self.assertNotEqual(token, self.page_a)  # model switch reset the context
        token = self.post("/api/target", {"target": str(self.f.bg_a), "selected_paths": ["facts.txt"]},
                          token=True, headers={HEADER: token})
        response = self.client.post("/api/chat", json={"question": "Classify this Baugruppe"}, headers={HEADER: token})
        self.assertEqual(response.status_code, 200, response.text)

    def test_requests_without_a_page_token_keep_api_compatibility(self):
        self.make_page_a_stale_by_other_tab()
        response = self.client.post("/api/chat", json={"question": "Classify this Baugruppe"})
        self.assertEqual(response.status_code, 200, response.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
