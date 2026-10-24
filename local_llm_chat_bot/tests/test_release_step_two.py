"""R02/R04 regressions; synthetic paths and loopback model requests only."""

import copy
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import chat_workbench as w
from fixture_support import FixtureEnvironment


class StepTwo(unittest.TestCase):
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

    def test_old_and_missing_ids_cannot_apply_new_plan(self):
        first = self.propose("A")
        second = self.propose("B")
        self.assertNotEqual(first, second)
        self.rejected(first)
        self.rejected("")
        self.assertFalse((self.f.workspace / "A.txt").exists())
        self.assertFalse((self.f.workspace / "B.txt").exists())
        result = self.post("/api/apply", {"confirmed": True, "plan_id": second})
        self.assertEqual(result["applied"], 1)
        self.assertEqual((self.f.workspace / "B.txt").read_text(), "B")
        self.rejected(second)

    def test_unconfirmed_and_cancelled_plan_never_writes(self):
        plan_id = self.propose("cancelled")
        response = self.client.post(
            "/api/apply", json={"confirmed": False, "plan_id": plan_id}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.delete("/api/pending").status_code, 200)
        self.rejected(plan_id)
        self.assertFalse((self.f.workspace / "cancelled.txt").exists())

    def test_plan_digest_rejects_content_or_order_change(self):
        for mutation in ["content", "order"]:
            with self.subTest(mutation=mutation):
                changes = w.build_diff(
                    w.ACTIVE["state"],
                    [
                        {"path": "one.txt", "content": "one"},
                        {"path": "two.txt", "content": "two"},
                    ],
                )
                plan_id = w.publish_pending(w.ACTIVE, changes)
                if mutation == "content":
                    w.ACTIVE["pending"][0]["content"] = "unreviewed"
                else:
                    w.ACTIVE["pending"].reverse()
                self.rejected(plan_id)
                self.assertFalse((self.f.workspace / "one.txt").exists())
                self.assertFalse((self.f.workspace / "two.txt").exists())

    def test_model_target_session_and_setup_invalidate_old_plan(self):
        transitions = [
            ("/api/model", {"model": "gemini-2.5-flash"}),
            (
                "/api/target",
                {"target": str(self.f.bg_a), "selected_paths": ["facts.txt"]},
            ),
            ("/api/session/new", {}),
            (
                "/api/setup",
                {"workspace": str(self.f.workspace), "model": "gemini-2.5-pro"},
            ),
        ]
        for index, (endpoint, body) in enumerate(transitions):
            with self.subTest(endpoint=endpoint):
                name = "context" + str(index)
                plan_id = self.propose(name)
                self.post(endpoint, body)
                self.rejected(plan_id)
                self.assertFalse((self.f.workspace / (name + ".txt")).exists())

    def test_rules_edit_and_relock_invalidate_confirmation(self):
        self.post("/api/codebook/prepare", {"path": str(self.f.rules)})
        self.post("/api/codebook/lock", {})
        plan_id = self.propose("rule_change")
        profile = w.load_codebook_profile()
        draft = copy.deepcopy(profile["draft"])
        draft["classes"][0]["definition"] += " Additional fixture definition."
        self.post("/api/codebook/edit", {"draft": draft, "confirmed": True})
        self.post("/api/codebook/lock", {})
        self.rejected(plan_id)
        self.assertFalse((self.f.workspace / "rule_change.txt").exists())

    def test_context_fingerprint_rejects_unannounced_binding_change(self):
        plan_id = self.propose("binding")
        w.ACTIVE["state"].data["selected_target"] = {"path": str(self.f.bg_b)}
        self.rejected(plan_id)
        self.assertFalse((self.f.workspace / "binding.txt").exists())

    def test_rule_source_change_after_review_rejects_confirmation(self):
        self.post("/api/codebook/prepare", {"path": str(self.f.rules)})
        self.post("/api/codebook/lock", {})
        plan_id = self.propose("stale_rule")
        with self.f.rules.open("ab") as handle:
            handle.write(b"changed fixture rules")
        self.rejected(plan_id)
        self.assertFalse((self.f.workspace / "stale_rule.txt").exists())

    def test_source_change_after_review_rejects_before_writing(self):
        self.post(
            "/api/target", {"target": str(self.f.bg_a), "selected_paths": ["facts.txt"]}
        )
        plan_id = self.propose("stale_source")
        (self.f.bg_a / "facts.txt").write_text("Changed fixture source")
        self.rejected(plan_id)
        self.assertFalse((self.f.workspace / "stale_source.txt").exists())

    def test_changed_replacement_is_preserved(self):
        target = self.f.workspace / "original.txt"
        target.write_text("before")
        changes = w.build_diff(
            w.ACTIVE["state"], [{"path": "original.txt", "content": "after"}]
        )
        plan_id = w.publish_pending(w.ACTIVE, changes)
        target.write_text("external edit")
        self.rejected(plan_id)
        self.assertEqual(target.read_text(), "external edit")

    def test_regular_unicode_paths_work_and_unsafe_paths_are_rejected(self):
        state = w.ACTIVE["state"]
        good = self.f.workspace / "中文 ü folder" / "normal.txt"
        good.parent.mkdir()
        good.write_text("safe")
        self.assertEqual(state.resolve_relative("中文 ü folder/normal.txt"), good)
        self.assertEqual(state.resolve_relative("中文 ü folder\\normal.txt"), good)
        self.assertEqual(
            state.resolve_relative("new/file.txt"), self.f.workspace / "new/file.txt"
        )
        for value in [
            "../outside.txt",
            "/etc/passwd",
            "C:\\private.txt",
            ".env",
            ".env/data.txt",
            "AI_Bot_State/private.txt",
            "config.pem",
            "config.key",
        ]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                state.resolve_relative(value)

    def test_file_and_directory_links_are_blocked_for_reads_and_diffs(self):
        state = w.ACTIVE["state"]
        private = self.f.workspace / "AI_Bot_State" / "private.txt"
        private.write_text("PRIVATE_MARKER")
        directory = self.f.workspace / "linked_directory"
        file = self.f.workspace / "linked_file.txt"
        directory.symlink_to(private.parent, target_is_directory=True)
        file.symlink_to(private)
        ordinary = self.f.workspace / "normal.txt"
        ordinary.write_text("normal")
        (self.f.workspace / "ordinary_alias.txt").symlink_to(ordinary)
        for name in [
            "linked_directory/private.txt",
            "linked_file.txt",
            "ordinary_alias.txt",
        ]:
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    state.resolve_relative(name)
                with self.assertRaises(ValueError):
                    w.build_diff(state, [{"path": name, "content": "blocked"}])
        state.scan()
        self.assertFalse(
            any("linked_" in name or "alias" in name for name in state.data["files"])
        )
        self.assertEqual(private.read_text(), "PRIVATE_MARKER")

    def test_link_inserted_after_review_cannot_redirect_apply(self):
        plan_id = self.propose("link_after_review")
        private = self.f.workspace / "AI_Bot_State" / "private.txt"
        private.write_text("unchanged")
        (self.f.workspace / "link_after_review.txt").symlink_to(private)
        response = self.client.post(
            "/api/apply", json={"confirmed": True, "plan_id": plan_id}
        )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(private.read_text(), "unchanged")

    def test_custom_state_directory_is_private_and_not_indexed(self):
        from code_chat_agent import ProjectState

        state_home = self.f.workspace / "custom-storage"
        state = ProjectState(state_home, self.f.workspace, "isolated")
        (state_home / "private.md").write_text("PRIVATE_MARKER")
        with self.assertRaises(ValueError):
            state.resolve_relative("custom-storage/private.md")
        state.scan()
        self.assertFalse(any("custom-storage" in name for name in state.data["files"]))

    def test_reparse_metadata_is_rejected_before_access(self):
        linked = self.f.workspace / "reparse"
        linked.mkdir()
        real_lstat = Path.lstat

        def lstat(path, *args, **kwargs):
            if path == linked:
                return SimpleNamespace(
                    st_mode=stat.S_IFDIR,
                    st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT,
                )
            return real_lstat(path, *args, **kwargs)

        with patch.object(Path, "lstat", lstat), self.assertRaises(ValueError):
            w.ACTIVE["state"].resolve_relative("reparse/private.txt")

    @unittest.skipUnless(
        os.name == "nt", "Requires native Windows NTFS junction and case semantics"
    )
    def test_native_windows_case_and_junction(self):
        state = w.ACTIVE["state"]
        with self.assertRaises(ValueError):
            state.resolve_relative("ai_bot_state/private.txt")
        junction = self.f.workspace / "junction"
        subprocess.run(
            [
                "cmd",
                "/c",
                "mklink",
                "/J",
                str(junction),
                str(self.f.workspace / "AI_Bot_State"),
            ],
            check=True,
            capture_output=True,
        )
        try:
            with self.assertRaises(ValueError):
                state.resolve_relative("junction/private.txt")
        finally:
            junction.rmdir()


if __name__ == "__main__":
    unittest.main(verbosity=2)
