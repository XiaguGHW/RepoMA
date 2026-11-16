"""F-01: the Farm key and configured env files never reach a model, history or plan."""

import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import chat_workbench as w
from fixture_support import FixtureEnvironment

SECRET = "REVIEW_SYNTHETIC_FARM_KEY_6f1e"


class SecretBoundary(unittest.TestCase):
    def setUp(self):
        self.f = FixtureEnvironment().__enter__()
        self.addCleanup(self.f.__exit__, None, None, None)
        environment = patch.dict(os.environ, {"BOSCH_FARM_SUBSCRIPTION_KEY": SECRET})
        environment.start()
        self.addCleanup(environment.stop)
        self.client = TestClient(w.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)

    def setup_with(self, relative):
        env_file = self.f.workspace / relative
        env_file.parent.mkdir(parents=True, exist_ok=True)
        env_file.write_text("BOSCH_FARM_SUBSCRIPTION_KEY=" + SECRET + "\n", encoding="utf-8")
        response = self.client.post("/api/setup", json={"workspace": str(self.f.workspace), "model": "gemini-2.5-pro",
                                                        "language": "en", "env_file": str(env_file)})
        self.assertEqual(response.status_code, 200, response.text)
        return env_file

    def assert_secret_nowhere(self, prompts=()):
        state = w.ACTIVE["state"]
        stored = [state.path.read_text(encoding="utf-8")]
        if state.transcript_path.exists():
            stored.append(state.transcript_path.read_text(encoding="utf-8"))
        for text in list(prompts) + stored + [json.dumps(self.f.calls, ensure_ascii=False)]:
            self.assertNotIn(SECRET, text)

    def test_configured_env_file_cannot_be_requested_by_the_model(self):
        for relative in ["farm.env", "Farm ü.env", "sub/x.env", "FARM.ENV", "config/farm-settings.txt"]:
            with self.subTest(relative=relative):
                env_file = self.setup_with(relative)
                prompts = []

                def ask(_files, prompt, *args, **kwargs):
                    prompts.append(prompt)
                    return json.dumps({"answer": "need config", "read_files": [env_file.relative_to(self.f.workspace).as_posix()],
                                       "changes": []})
                with patch.object(w.ACTIVE["llm"], "ask_about_files", side_effect=ask):
                    response = self.client.post("/api/chat", json={"question": "Which settings are used?"})
                self.assertEqual(response.status_code, 400, response.text)
                self.assertEqual(len(prompts), 1)  # refused before any second model call
                self.assert_secret_nowhere(prompts)
                self.assertNotIn(SECRET, response.text)

    def test_diff_apply_and_index_exclude_the_configured_file(self):
        env_file = self.setup_with("farm_settings.json")  # .json would otherwise be indexed as code
        state = w.ACTIVE["state"]
        self.assertNotIn("farm_settings.json", state.data["files"])
        with self.assertRaises(ValueError):
            w.build_diff(state, [{"path": "farm_settings.json", "content": "overwritten"}])
        with self.assertRaises(ValueError):
            state.resolve_relative("farm_settings.json")
        prompts = []

        def ask(_files, prompt, *args, **kwargs):
            prompts.append(prompt)
            return json.dumps({"answer": "ok", "read_files": [], "changes": []})
        with patch.object(w.ACTIVE["llm"], "ask_about_files", side_effect=ask):
            self.assertEqual(self.client.post("/api/chat", json={"question": "farm settings BOSCH_FARM_SUBSCRIPTION_KEY"}).status_code, 200)
        self.assert_secret_nowhere(prompts)
        self.assertIn("BOSCH_FARM_SUBSCRIPTION_KEY=" + SECRET, env_file.read_text(encoding="utf-8"))

    def test_ordinary_workspace_files_remain_readable(self):
        self.setup_with("farm.env")
        (self.f.workspace / "notes.txt").write_text("ORDINARY_MARKER", encoding="utf-8")
        prompts = []

        def ask(_files, prompt, *args, **kwargs):
            prompts.append(prompt)
            return json.dumps({"answer": "x", "read_files": ["notes.txt"] if len(prompts) == 1 else [], "changes": []})
        with patch.object(w.ACTIVE["llm"], "ask_about_files", side_effect=ask):
            self.assertEqual(self.client.post("/api/chat", json={"question": "notes"}).status_code, 200)
        self.assertIn("ORDINARY_MARKER", prompts[1])

    def test_key_inside_material_is_redacted_from_prompts_answers_and_previews(self):
        self.setup_with("outside/../farm.env")
        (self.f.workspace / "leaky.txt").write_text("Copied config: " + SECRET, encoding="utf-8")
        (self.f.bg_a / "facts.txt").write_text("FIXTURE_BG_A rotates. Pasted key " + SECRET, encoding="utf-8")
        self.client.post("/api/target", json={"target": str(self.f.bg_a), "selected_paths": ["facts.txt"]})
        prompts = []

        def ask(_files, prompt, *args, **kwargs):
            prompts.append(prompt)
            handler = kwargs.get("event_handler")
            raw = json.dumps({"answer": "The key is " + SECRET, "read_files": ["leaky.txt"] if len(prompts) == 1 else [],
                              "changes": [{"path": "echo.txt", "content": "KEY=" + SECRET}]})
            if handler:
                handler("reasoning", "thinking about " + SECRET)
                handler("content", raw)
            return raw
        with patch.object(w.ACTIVE["llm"], "ask_about_files", side_effect=ask):
            response = self.client.post("/api/chat/stream", json={"question": "Explain leaky config"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertGreaterEqual(len(prompts), 2)
        self.assertNotIn(SECRET, response.text)  # previews, reasoning and final result
        self.assertIn("[redacted]", response.text)
        self.assert_secret_nowhere(prompts)
        self.assertTrue(all("[redacted]" in prompt for prompt in prompts[1:]))
        for item in w.ACTIVE.get("pending", []):
            self.assertNotIn(SECRET, item["content"])


class TerminalBoundary(unittest.TestCase):
    def test_terminal_project_state_protects_its_env_file(self):
        from code_chat_agent import ProjectState
        with FixtureEnvironment() as f:
            env_file = f.workspace / "terminal settings.txt"
            env_file.write_text("BOSCH_FARM_SUBSCRIPTION_KEY=" + SECRET, encoding="utf-8")
            state = ProjectState(f.root / "state", f.workspace, "terminal")
            state.protect(str(env_file))
            with self.assertRaises(ValueError):
                state.resolve_relative("terminal settings.txt")


if __name__ == "__main__":
    unittest.main(verbosity=2)
