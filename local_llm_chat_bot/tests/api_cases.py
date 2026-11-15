"""Shared test bases for tests regrouped by feature.

Each base keeps the exact setUp/tearDown and helpers of the class its tests
came from, so the tests run under the same conditions as before."""

from pathlib import Path
import sys

APP = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(APP), str(APP / "tests")]

import json  # noqa: E402
import unittest  # noqa: E402
from unittest.mock import patch  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import chat_workbench as w  # noqa: E402
from fixture_support import FixtureEnvironment  # noqa: E402
import os  # noqa: E402
import tempfile  # noqa: E402


class ApiCase(unittest.TestCase):
    """HTTP fixture: mock Bosch Farm, TestClient, /api/setup with the default UI language."""

    def setUp(self):
        self.f = FixtureEnvironment().__enter__()
        self.addCleanup(self.f.__exit__, None, None, None)
        self.client = TestClient(w.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)
        self.post(
            "/api/setup",
            {"workspace": str(self.f.workspace), "model": "gemini-2.5-pro"},
        )

    def post(self, path, body):
        response = self.client.post(path, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()


class EnglishApiCase(unittest.TestCase):
    """HTTP fixture: mock Bosch Farm, TestClient, /api/setup in English; bg() prepares
    and locks the fixture rules and selects facts.txt of BG A."""

    def setUp(self):
        self.f = FixtureEnvironment().__enter__()
        self.client = TestClient(w.app, raise_server_exceptions=False)
        self.post(
            "/api/setup",
            {
                "workspace": str(self.f.workspace),
                "model": "gemini-2.5-pro",
                "language": "en",
            },
        )

    def tearDown(self):
        self.client.close()
        self.f.__exit__(None, None, None)

    def post(self, path, body):
        response = self.client.post(path, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def bg(self):
        self.post("/api/codebook/prepare", {"path": str(self.f.rules)})
        self.post("/api/codebook/lock", {})
        self.post(
            "/api/target", {"target": str(self.f.bg_a), "selected_paths": ["facts.txt"]}
        )


class DirectSessionCase(unittest.TestCase):
    """No HTTP: a temporary folder (non-ASCII name), patched state home and .env,
    and w.setup() called directly with a test model."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='发布 Prüfung ')
        self.root = Path(self.tmp.name)
        self.workspace = self.root / 'app'
        self.workspace.mkdir()
        self.old = dict(w.ACTIVE)
        w.ACTIVE.clear()
        w.MODEL_WORK_IN_PROGRESS.clear()
        self.patches = [patch.object(w, 'app_state_home', return_value=self.workspace / 'AI_Bot_State'),
                        patch.object(w, 'load_dotenv'),
                        patch.dict(os.environ, {'BOSCH_FARM_SUBSCRIPTION_KEY': 'fixture-only',
                                                'WORKBENCH_ALLOW_TEST_HOST': '1'})]
        for p in self.patches:
            p.start()
        w.setup(w.Setup(workspace=str(self.workspace), state_dir='', model='gemini-test'))

    def tearDown(self):
        w.ACTIVE.clear()
        w.ACTIVE.update(self.old)
        w.MODEL_WORK_IN_PROGRESS.clear()
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()


class LegacyApplyPlanHelpers:
    """Legacy code-change plan helpers (/api/chat proposal, rejected /api/apply).
    Removed together with /api/apply in refactor step 2."""

    def propose(self, name):
        action = {
            "answer": name,
            "changes": [{"path": name + ".txt", "content": name}],
            "read_files": [],
        }
        with patch.object(
            w.ACTIVE["llm"], "ask_about_files", return_value=json.dumps(action)
        ):
            result = self.post("/api/chat", {"question": "Prepare " + name})
        self.assertTrue(result["plan_id"])
        self.assertNotIn("content", result["changes"][0])
        return result["plan_id"]

    def rejected(self, plan_id):
        response = self.client.post(
            "/api/apply", json={"confirmed": True, "plan_id": plan_id}
        )
        self.assertEqual(response.status_code, 409, response.text)
