"""Read-only release audit: expected-safe assertions, existing synthetic fixtures only."""

import copy
import json
import runpy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

APP = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(APP), str(APP / "tests")]
from fastapi.testclient import TestClient  # noqa: E402 - portable direct runner path
import chat_workbench as w  # noqa: E402 - import after locating the application
from fixture_support import FixtureEnvironment, PROFILE  # noqa: E402


class AuditGaps(unittest.TestCase):
    def test_gui_cli_must_honor_explicit_port(self):
        with (
            patch("uvicorn.run") as serve,
            patch("workbench_startup.check_state_directory"),
            patch("workbench_startup.check_port"),
            patch.object(
                sys, "argv", [str(APP / "chat_workbench.py"), "--port", "8877"]
            ),
        ):
            runpy.run_path(str(APP / "chat_workbench.py"), run_name="__main__")
        self.assertEqual(serve.call_args.kwargs.get("port"), 8877)

    def test_gui_cli_must_reject_unknown_option(self):
        with (
            patch("uvicorn.run") as serve,
            patch.object(
                sys,
                "argv",
                [str(APP / "chat_workbench.py"), "--fixture-invalid-option"],
            ),
        ):
            with self.assertRaises(SystemExit) as error:
                runpy.run_path(str(APP / "chat_workbench.py"), run_name="__main__")
        self.assertEqual(error.exception.code, 2)
        serve.assert_not_called()

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

    def test_private_state_symlink_must_not_enter_model_prompt(self):
        secret = self.f.workspace / "AI_Bot_State" / "fixture-private.txt"
        secret.write_text("SYNTHETIC_PRIVATE_MARKER", encoding="utf-8")
        (self.f.workspace / "alias.txt").symlink_to(secret)
        prompts = []

        def answer(_files, prompt, *args, **kwargs):
            prompts.append(prompt)
            return json.dumps(
                {
                    "answer": "fixture",
                    "read_files": ["alias.txt"] if len(prompts) == 1 else [],
                    "changes": [],
                }
            )

        with patch.object(w.ACTIVE["llm"], "ask_about_files", side_effect=answer):
            response = self.client.post(
                "/api/chat", json={"question": "Explain fixture file"}
            )
        self.assertFalse(
            any("SYNTHETIC_PRIVATE_MARKER" in p for p in prompts),
            f"private marker reached second model prompt; response={response.status_code}",
        )

    def test_followup_repair_must_revalidate_classification(self):
        self.bg()
        result = self.client.post(
            "/api/chat", json={"question": "TEST_UNKNOWN explain the motor evidence"}
        )
        self.assertNotEqual(
            result.status_code,
            200,
            f"accepted unknown class: {result.json().get('classification')}",
        )

    def test_evidence_pages_must_reference_supplied_pages(self):
        action = {
            "classification": {
                "label": "Rotationseinheit",
                "confidence": "high",
                "evidence_labels": ["facts.txt block 1"],
                "codebook_rule_ids": ["rotation-1"],
                "codebook_rule_pages": [999999],
                "bg_evidence_pages": ["never-supplied.pdf p999"],
                "alternative_label": "",
                "uncertainties": [],
            }
        }
        self.assertIsNotNone(
            w.validate_classification(
                action, [{"label": "facts.txt block 1"}], "", PROFILE
            ),
            "fabricated Codebook and BG page references accepted",
        )

    def test_compare_must_reject_changed_sources_before_call(self):
        self.bg()
        (self.f.bg_a / "facts.txt").write_text("CHANGED_FIXTURE_BG_A", encoding="utf-8")
        count = len(self.f.calls)
        response = self.client.post(
            "/api/compare",
            json={
                "question": "classify",
                "models": ["gemini-2.5-pro", "gemini-2.5-flash"],
            },
        )
        self.assertEqual(
            (response.status_code, len(self.f.calls) - count),
            (409, 0),
            "comparison used stale indexed source and contacted mock models",
        )

    def test_relocked_rules_must_not_silently_disable_bg_classification(self):
        self.bg()
        draft = copy.deepcopy(PROFILE)
        draft["classes"][0]["name"] = "New fixture class"
        self.post("/api/codebook/edit", {"draft": draft, "confirmed": True})
        self.post("/api/codebook/lock", {})
        response = self.client.post(
            "/api/chat", json={"question": "Classify this Baugruppe"}
        )
        body = response.json()
        self.assertTrue(
            response.status_code == 409
            or (body.get("classification") or {}).get("label") == "New fixture class",
            f"locked rules + selected BG returned {response.status_code}, classification={body.get('classification')}",
        )

    def test_failed_target_change_must_preserve_old_conversation(self):
        self.bg()
        self.post("/api/chat", {"question": "classify"})
        old = copy.deepcopy(w.ACTIVE["state"].data["history"])
        with self.f.rules.open("ab") as handle:
            handle.write(b"fixture changed")
        response = self.client.post(
            "/api/target",
            json={"target": str(self.f.bg_b), "selected_paths": ["facts.txt"]},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            w.ACTIVE["state"].data["history"],
            old,
            "rejected target switch already erased history",
        )

    def test_codebook_and_comparison_calls_must_be_counted(self):
        self.bg()
        self.post(
            "/api/compare",
            {"question": "classify", "models": ["gemini-2.5-pro", "gemini-2.5-flash"]},
        )
        usage = w.ACTIVE["state"].data["usage"]
        self.assertEqual(
            usage["requests"],
            len(self.f.calls),
            f"mock calls={len(self.f.calls)} but accumulated usage={usage}",
        )

    def test_unknown_usage_must_not_become_free_price(self):
        usage = w.summarize_usage(
            [{"input_tokens": None, "output_tokens": None, "usage_complete": False}]
        )
        estimate = w.ACTIVE["pricing"].estimate(
            "gemini-2.5-pro", usage["input"], usage["output"]
        )
        self.assertIsNone(estimate, f"unknown usage priced as {estimate}")

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

    def test_model_content_chunks_must_reach_stream_client(self):
        def answer(_files, _prompt, *args, **kwargs):
            handler = kwargs.get("event_handler")
            if handler:
                handler("content", '{"answer":"STREAM_FIXTURE_')
                handler("content", 'ANSWER","changes":[],"read_files":[]}')
            return json.dumps(
                {"answer": "STREAM_FIXTURE_ANSWER", "changes": [], "read_files": []}
            )

        with patch.object(w.ACTIVE["llm"], "ask_about_files", side_effect=answer):
            text = self.client.post(
                "/api/chat/stream", json={"question": "Explain fixture"}
            ).text
        events = [
            json.loads(line[6:])
            for line in text.splitlines()
            if line.startswith("data: ")
        ]
        intermediate = [e for e in events if e["type"] not in {"result", "end"}]
        self.assertTrue(
            any("STREAM_FIXTURE_" in json.dumps(e) for e in intermediate),
            f"content deltas were dropped; event types={[e['type'] for e in events]}",
        )

    def test_stale_confirmation_must_not_apply_a_different_pending_plan(self):
        def plan(name):
            return json.dumps(
                {
                    "answer": name,
                    "changes": [
                        {"path": name + ".txt", "content": name, "reason": "fixture"}
                    ],
                    "read_files": [],
                }
            )

        with patch.object(
            w.ACTIVE["llm"],
            "ask_about_files",
            side_effect=[plan("plan_A"), plan("plan_B")],
        ):
            first = self.post("/api/chat", {"question": "Prepare fixture A"})
            self.assertEqual(first["changes"][0]["path"], "plan_A.txt")
            self.post("/api/chat", {"question": "Prepare fixture B from second tab"})
        # This is exactly the request the still-open A confirmation button sends.
        response = self.client.post("/api/apply", json={"confirmed": True})
        self.assertEqual(
            response.status_code,
            409,
            f"A confirmation applied B: status={response.status_code}, B exists={(self.f.workspace / 'plan_B.txt').exists()}",
        )

    def test_corrupt_nested_context_must_require_reconfirmation(self):
        state = w.ACTIVE["state"]
        state.data["bg_context"] = ["legacy-invalid"]
        state.save()
        self.post(
            "/api/setup",
            {
                "workspace": str(self.f.workspace),
                "model": "gemini-2.5-pro",
                "language": "en",
            },
        )
        count = len(self.f.calls)
        response = self.client.post("/api/chat", json={"question": "fixture"})
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(len(self.f.calls), count)

    def test_explicit_env_file_must_be_loaded(self):
        env = self.f.root / "custom ü.env"
        env.write_text(
            "BOSCH_FARM_SUBSCRIPTION_KEY=offline-fixture-only\\n", encoding="utf-8"
        )
        with patch.object(w, "load_dotenv") as load:
            self.post(
                "/api/setup",
                {
                    "workspace": str(self.f.workspace),
                    "model": "gemini-2.5-pro",
                    "env_file": str(env),
                },
            )
        self.assertEqual(Path(load.call_args.args[0]).resolve(), env.resolve())


if __name__ == "__main__":
    unittest.main(verbosity=2)
