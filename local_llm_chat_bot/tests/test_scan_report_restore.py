"""The local scan report can be reopened after a page reload."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient  # noqa: E402
import chat_workbench as w  # noqa: E402
from fixture_support import FixtureEnvironment  # noqa: E402


class ScanReportRestore(unittest.TestCase):
    def setUp(self):
        self.f = FixtureEnvironment().__enter__()
        self.addCleanup(self.f.__exit__, None, None, None)
        (self.f.bg_a / "drawing.txt").write_text("FIXTURE_DRAWING: bracket.", encoding="utf-8")
        self.client = TestClient(w.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)

    def post(self, path, body):
        response = self.client.post(path, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_report_is_rebuilt_from_confirmed_materials(self):
        self.post("/api/setup", {"workspace": str(self.f.workspace), "model": "gemini-2.5-pro", "language": "de"})
        self.post("/api/codebook/prepare", {"path": str(self.f.rules)})
        self.post("/api/codebook/lock", {})
        scan = self.post("/api/target", {"target": str(self.f.bg_a), "selected_paths": ["facts.txt", "drawing.txt"]})
        restored = self.client.get("/api/scan/report").json()
        self.assertEqual(restored["sources"], 2)
        self.assertEqual(restored["files"], scan["files"])
        self.assertTrue(restored["restored"])

    def test_report_is_empty_without_materials(self):
        self.post("/api/setup", {"workspace": str(self.f.workspace), "model": "gemini-2.5-pro", "language": "de"})
        restored = self.client.get("/api/scan/report").json()
        self.assertEqual(restored["files"], [])

    def test_incomplete_preread_of_current_materials_stays_visible(self):
        self.post("/api/setup", {"workspace": str(self.f.workspace), "model": "gemini-2.5-pro", "language": "de"})
        self.post("/api/codebook/prepare", {"path": str(self.f.rules)})
        self.post("/api/codebook/lock", {})
        self.post("/api/target", {"target": str(self.f.bg_a), "selected_paths": ["facts.txt", "drawing.txt"]})
        self.assertEqual(self.client.get("/api/coverage").json(), {})  # nothing is pre-read before a question
        self.post("/api/chat", {"question": "Classify this Baugruppe"})
        w.invalidate_current_coverage(w.ACTIVE["state"])  # e.g. a file failed to pre-read
        report = self.client.get("/api/coverage").json()
        self.assertFalse(report["complete"])
        self.assertTrue(report["current_selection"])
        self.assertEqual(len(report["files"]), 2)
        self.assertFalse(w.coverage_matches_current_selection(w.session(), report))
        # A different model makes the report stale.
        w.ACTIVE["model"] = "claude-haiku-5-5"
        self.assertFalse(self.client.get("/api/coverage").json()["current_selection"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
