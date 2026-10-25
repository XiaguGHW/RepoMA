"""Independent pre-release review repros (2026-10-25). Synthetic data, loopback mock only.

Run from local_llm_chat_bot/:
    python -m unittest discover -s ../tools/release_audit -p independent_review_2026-10-25.py -v

Every test asserts the CURRENT (defective) behaviour, so a passing test here means the
problem was reproduced.  After a fix, invert the marked assertions into regression tests
under tests/ (see the review report); do not keep these as permanent "green" checks.
No real Bosch endpoint, key, BG, Codebook or Excel is touched.
"""
import copy
import json
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

APP = Path(__file__).resolve().parents[2] / "local_llm_chat_bot"
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "tests"))
from fastapi.testclient import TestClient  # noqa: E402
import chat_workbench as w  # noqa: E402
from fixture_support import FixtureEnvironment  # noqa: E402
from llm_connector_with_prompt_caching import LLMConnector  # noqa: E402


class ReviewBase(unittest.TestCase):
    def setUp(self):
        self.f = FixtureEnvironment().__enter__()
        self.addCleanup(self.f.__exit__, None, None, None)
        self.client = TestClient(w.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)

    def post(self, path, body, status=200):
        response = self.client.post(path, json=body)
        self.assertEqual(response.status_code, status, response.text)
        return response.json()

    def setup_workspace(self, **extra):
        body = {"workspace": str(self.f.workspace), "model": "gemini-2.5-pro", "language": "en"}
        body.update(extra)
        return self.post("/api/setup", body)

    def bg(self, folder=None, paths=("facts.txt",)):
        self.post("/api/codebook/prepare", {"path": str(self.f.rules)})
        self.post("/api/codebook/lock", {})
        self.post("/api/target", {"target": str(folder or self.f.bg_a), "selected_paths": list(paths)})

    def delay_model(self, seconds):
        def transform(response, prompt, system):
            time.sleep(seconds)
            return response
        self.f.response_transform = transform


class SecretBoundary(ReviewBase):
    def test_configured_env_file_inside_workspace_reaches_model_prompt(self):
        """F-01: a configured *.env not named '.env…' inside the workspace is model-readable."""
        secret = "REVIEW_SYNTHETIC_FARM_KEY_6f1e"
        env_file = self.f.workspace / "farm.env"
        env_file.write_text("BOSCH_FARM_SUBSCRIPTION_KEY=" + secret + "\n", encoding="utf-8")
        with patch.dict(os.environ, {"BOSCH_FARM_SUBSCRIPTION_KEY": secret}):
            self.setup_workspace(env_file=str(env_file))
            prompts = []

            def ask(_files, prompt, *args, **kwargs):
                prompts.append(prompt)
                if len(prompts) == 1:
                    return json.dumps({"answer": "need config", "read_files": ["farm.env"], "changes": []})
                return json.dumps({"answer": "done", "read_files": [], "changes": []})

            with patch.object(w.ACTIVE["llm"], "ask_about_files", side_effect=ask):
                result = self.client.post("/api/chat", json={"question": "Which settings are used?"})
        # CURRENT behaviour (defect): request succeeds and the secret is sent to the model.
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(len(prompts), 2)
        self.assertIn(secret, prompts[1])
        # The same resolver also accepts the path for a change plan (diff/apply share it).
        self.assertEqual(w.ACTIVE["state"].resolve_relative("farm.env"), env_file.resolve())


class RequestBounds(ReviewBase):
    def test_default_policy_is_20s_read_and_180s_for_whole_operation(self):
        """F-02 context: the shipped defaults, also used by terminal entry points."""
        policy = w.RequestControl().policy
        self.assertEqual((policy.read_timeout, policy.timeout, policy.attempts), (20, 180, 3))
        connector = LLMConnector("gemini-2.5-pro", "offline-fixture-only")
        self.assertIsNone(connector.request_control)
        connector.ask_about_files([], "Reply OK", "You are a connection test.")
        # bosch_chat/excel_chat_agent/code_chat_agent get the same per-call default control.
        self.assertEqual(connector._control.policy.read_timeout, 20)

    def test_healthy_but_slow_nonstreaming_response_fails_and_is_dispatched_three_times(self):
        """F-02a: complete-response Gemini/Claude calls must finish within READ_TIMEOUT (scaled 0.5s)."""
        self.setup_workspace()
        self.delay_model(1.0)
        before = len(self.f.calls)
        with patch.dict(os.environ, {"WORKBENCH_READ_TIMEOUT_SECONDS": "0.5",
                                     "WORKBENCH_RETRY_BACKOFF_SECONDS": "0"}):
            result = self.client.post("/api/chat", json={"question": "Explain the workspace"})
        self.assertEqual(result.status_code, 400, result.text)
        self.assertIn("ReadTimeout", result.text)
        # The mock generated (and a real provider would bill) all three attempts.
        time.sleep(1.2)
        self.assertEqual(len(self.f.calls) - before, 3)
        usage = w.ACTIVE["state"].data["usage"]
        self.assertEqual(usage["requests"], 3)
        self.assertIsNone(usage["input"])  # three unknown-usage dispatches, cost incomplete
        # Control: the same slow-but-healthy server succeeds when the read bound exceeds latency.
        with patch.dict(os.environ, {"WORKBENCH_READ_TIMEOUT_SECONDS": "5"}):
            self.post("/api/chat", {"question": "Explain the workspace"})

    def test_whole_operation_deadline_covers_every_preparation_call(self):
        """F-02b: one 180s budget (scaled 1.5s) covers all per-file summaries, dossier and answer."""
        self.setup_workspace()
        for index in range(4):
            (self.f.bg_a / f"part_{index}.txt").write_text(f"FIXTURE part {index} rotates.", encoding="utf-8")
        self.bg(paths=["."])
        self.delay_model(0.4)
        before = len(self.f.calls)
        with patch.dict(os.environ, {"WORKBENCH_REQUEST_TIMEOUT_SECONDS": "1.5"}):
            result = self.client.post("/api/chat", json={"question": "Classify this Baugruppe"})
        self.assertEqual(result.status_code, 400, result.text)
        self.assertIn("timed out", result.text.lower())
        self.assertGreaterEqual(len(self.f.calls) - before, 3)
        self.assertEqual(w.ACTIVE["state"].data["history"], [])
        with patch.dict(os.environ, {"WORKBENCH_REQUEST_TIMEOUT_SECONDS": "60"}):
            ok = self.post("/api/chat", {"question": "Classify this Baugruppe"})
        self.assertEqual(ok["classification"]["label"], "Rotationseinheit")


    def test_codebook_preparation_shares_one_deadline_across_all_pages(self):
        """F-02c: every page/section call plus merge must fit one REQUEST_TIMEOUT (scaled 1.2s)."""
        from docx import Document
        self.setup_workspace()
        rules = self.f.root / "Long rules.docx"
        document = Document()
        for index in range(12):
            document.add_paragraph(f"Rule section {index}: Rotationseinheit rotates. " + "detail " * 450)
        document.save(rules)
        self.delay_model(0.4)
        before = len(self.f.calls)
        with patch.dict(os.environ, {"WORKBENCH_REQUEST_TIMEOUT_SECONDS": "1.2"}):
            failed = self.client.post("/api/codebook/prepare", json={"path": str(rules)})
        self.assertEqual(failed.status_code, 400, failed.text)
        self.assertIn("timed out", failed.text.lower())
        self.assertGreaterEqual(len(self.f.calls) - before, 3)  # paid page calls are discarded
        self.assertEqual(w.load_codebook_profile(), {})
        with patch.dict(os.environ, {"WORKBENCH_REQUEST_TIMEOUT_SECONDS": "60"}):
            self.assertEqual(self.post("/api/codebook/prepare", {"path": str(rules)})["status"], "draft")


class RuleProfileIntegrity(ReviewBase):
    def test_duplicate_rule_ids_lock_successfully_then_block_every_classification(self):
        """F-03: lock accepts ambiguous rule IDs; validator then rejects all classifications."""
        self.setup_workspace()
        self.post("/api/codebook/prepare", {"path": str(self.f.rules)})
        profile = w.load_codebook_profile()
        draft = copy.deepcopy(profile["draft"])
        draft["classes"].append({"name": "Gantry", "definition": "Moves along axes.",
                                 "decision_rules": [{"id": "rotation-1", "text": "Different rule text.", "pages": [1]}],
                                 "boundaries": [], "evidence_pages": [1]})
        self.post("/api/codebook/edit", {"draft": draft, "confirmed": True, "profile_version": profile["version"]})
        locked = self.post("/api/codebook/lock", {})
        self.assertEqual(locked["status"], "locked")  # defect: no uniqueness check at lock time
        self.post("/api/target", {"target": str(self.f.bg_a), "selected_paths": ["facts.txt"]})
        before = len(self.f.calls)
        result = self.client.post("/api/chat", json={"question": "Classify this Baugruppe"})
        self.assertEqual(result.status_code, 400, result.text)
        self.assertIn("ambiguous rule ID", result.text)
        # File summary + dossier + answer + one repair are all spent before the inevitable failure.
        self.assertEqual(len(self.f.calls) - before, 4)


class ReferenceTraceability(ReviewBase):
    def test_nonpaged_and_same_named_sources_share_one_file_level_label(self):
        """F-07: DOCX/TXT chunks and same-named files in different subfolders are indistinguishable."""
        self.setup_workspace()
        for folder, text in (("sub1", "FIXTURE motor rotates the table."), ("sub2", "FIXTURE gripper holds the part.")):
            (self.f.bg_a / folder).mkdir()
            (self.f.bg_a / folder / "notes.txt").write_text(text + "\n\n" + ("filler " * 700), encoding="utf-8")
        self.bg(paths=["sub1/notes.txt", "sub2/notes.txt"])
        documents = [item for item in w.ACTIVE["documents"].list()
                     if item["id"] in w.ACTIVE["state"].data["active_source_ids"]]
        labels = [chunk["label"] for item in documents for chunk in item["chunks"]]
        self.assertEqual(len(documents), 2)
        self.assertGreater(len(labels), 2)          # several chunks ...
        self.assertEqual(set(labels), {"notes.txt"})  # ... but one label for all of them
        result = self.post("/api/chat", {"question": "Classify this Baugruppe"})
        # A "validated" card cites only "notes.txt": neither the folder nor the section is traceable.
        self.assertEqual(result["classification"]["bg_evidence_pages"], ["notes.txt"])


class ScopeRecovery(ReviewBase):
    def test_clearing_rules_blocks_plain_material_reconfirmation_until_bg_is_cleared(self):
        """F-05: after DELETE /api/codebook the suggested reconfirmation path returns 409 rules_lock."""
        self.setup_workspace()
        self.bg()
        self.assertEqual(self.client.delete("/api/codebook").status_code, 200)
        self.assertEqual(w.ACTIVE["state"].data.get("context_issue"), "rules_changed")
        result = self.client.post("/api/target", json={"target": str(self.f.bg_a), "selected_paths": ["facts.txt"]})
        self.assertEqual(result.status_code, 409, result.text)
        self.assertEqual(result.json().get("message_key"), "error.rules_lock")
        chat = self.client.post("/api/chat", json={"question": "Explain facts"})
        self.assertEqual(chat.status_code, 409, chat.text)
        # Only the separate "leave BG mode" call unlocks ordinary material confirmation.
        self.assertEqual(self.client.delete("/api/bg").status_code, 200)
        self.post("/api/target", {"target": str(self.f.bg_a), "selected_paths": ["facts.txt"]})


class PlainModeRobustness(ReviewBase):
    def test_empty_classification_object_fails_plain_document_question(self):
        """F-09: outside BG mode a harmless `"classification": {}` aborts the whole answer."""
        self.setup_workspace()
        action = {"answer": "Plain answer", "classification": {}, "changes": [], "read_files": []}
        with patch.object(w.ACTIVE["llm"], "ask_about_files", return_value=json.dumps(action)):
            result = self.client.post("/api/chat", json={"question": "Explain the workspace"})
        self.assertEqual(result.status_code, 400, result.text)
        self.assertIn("No locked Codebook rules", result.text)
        self.assertEqual(w.ACTIVE["state"].data["history"], [])


class LocalOrigin(ReviewBase):
    def test_cross_site_get_without_origin_and_testserver_host_are_accepted(self):
        """F-06: GET endpoints accept cross-site no-Origin requests; production also accepts Host: testserver."""
        self.setup_workspace()
        headers = {"host": "127.0.0.1:8765", "sec-fetch-site": "cross-site", "sec-fetch-mode": "no-cors"}
        response = self.client.get("/api/target-tree", params={"target": str(self.f.bg_a)}, headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        blocked = self.client.get("/api/status", headers={"host": "127.0.0.1:8765", "origin": "https://example.invalid"})
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(self.client.get("/api/status", headers={"host": "testserver"}).status_code, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
