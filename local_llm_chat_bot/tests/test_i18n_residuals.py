"""F-08: exports and new sessions use the active UI language deterministically."""

from pathlib import Path
import json
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import chat_workbench as w
from fixture_support import FixtureEnvironment
from api_cases import EnglishApiCase  # noqa: E402


class I18nResiduals(unittest.TestCase):
    def setUp(self):
        self.fixture = FixtureEnvironment().__enter__()
        self.addCleanup(self.fixture.__exit__, None, None, None)
        self.client = TestClient(w.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)
        response = self.client.post("/api/setup", json={
            "workspace": str(self.fixture.workspace), "model": "gemini-2.5-pro"
        })
        self.assertEqual(response.status_code, 200, response.text)

    def test_exports_follow_the_active_language_and_never_render_none_for_unknown_cost(self):
        state = w.ACTIVE["state"]
        state.data["usage"] = {
            "requests": 1,
            "input": 3,
            "output": 5,
            "known_input": 3,
            "known_output": 5,
            "estimated_cost_usd": 0,
            "unpriced_requests": 1,
        }
        state.data["last_bg_analysis"] = {
            "created_at": "2026-10-25T12:00:00+00:00",
            "session": state.root.name,
            "model": "fixture-model",
            "bg_context": {},
            "token_usage": {"input": 3, "output": 5, "cost_usd": None},
            "question": "Why?",
            "answer": "Because.",
            "sources": [],
        }
        for language, heading, unknown in [
            ("en", "Session transcript", "Unknown"),
            ("de", "Sitzungsprotokoll", "Unbekannt"),
        ]:
            with self.subTest(language=language):
                w.ACTIVE["language"] = language
                session_export = w.write_session_export(w.ACTIVE).read_text(encoding="utf-8")
                analysis_export = w.write_bg_analysis_export(state, language).read_text(encoding="utf-8")
                self.assertIn(heading, session_export)
                self.assertIn(unknown, session_export)
                self.assertIn(unknown, analysis_export)
                self.assertNotIn("None", session_export + analysis_export)
                self.assertNotRegex(session_export + analysis_export, r"[\u4e00-\u9fff]")

    def test_new_session_uses_portable_directory_name_and_localized_sidebar_title(self):
        created = self.client.post("/api/session/new").json()
        self.assertRegex(created["session_name"], r"^chat_\d{8}_\d{6}$")
        rows = self.client.get("/api/sessions").json()["sessions"]
        current = next(item for item in rows if item["name"] == created["session_name"])
        self.assertEqual(current["title_key"], "session.new_title")
        self.assertTrue(w.is_new_session_title("新聊天"))


class EnglishProgressNotices(EnglishApiCase):
    def test_english_progress_and_notices_must_not_contain_chinese_ui(self):
        self.bg()
        text = self.client.post("/api/chat/stream", json={"question": "classify"}).text
        events = [
            json.loads(line[6:])
            for line in text.splitlines()
            if line.startswith("data: ")
        ]
        ui = [e["text"] for e in events if e["type"] == "progress"]
        ui += [n for e in events if e["type"] == "result" for n in e["data"]["notices"]]
        foreign = [s for s in ui if any("\u4e00" <= c <= "\u9fff" for c in s)]
        self.assertEqual(
            foreign, [], f"English UI exposes Chinese processing text: {foreign}"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
