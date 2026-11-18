"""Paths: Unicode, links and junctions, private state folder, session names."""

from pathlib import Path
import sys

APP = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(APP), str(APP / "tests")]

import json  # noqa: E402
import os  # noqa: E402
import stat  # noqa: E402
import subprocess  # noqa: E402
from types import SimpleNamespace  # noqa: E402
import unittest  # noqa: E402
from unittest.mock import patch  # noqa: E402
import chat_workbench as w  # noqa: E402
from code_chat_agent import safe_name  # noqa: E402
from api_cases import ApiCase, DirectSessionCase, EnglishApiCase  # noqa: E402


class PathSafety(ApiCase):
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

    def test_file_and_directory_links_are_blocked_for_reads(self):
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
        state.scan()
        self.assertFalse(
            any("linked_" in name or "alias" in name for name in state.data["files"])
        )
        self.assertEqual(private.read_text(), "PRIVATE_MARKER")

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


class PrivateStateInPrompts(EnglishApiCase):
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


class SessionAndScanPaths(DirectSessionCase):
    def test_state_scan_excludes_private_application_state(self):
        state = w.ACTIVE['state']
        secret = state.root / 'private.json'
        secret.write_text('{"secret":"old material"}')
        state.scan()
        self.assertFalse(any('AI_Bot_State' in p for p in state.data['files']))

    def test_session_name_cannot_escape_project(self):
        for name in ('.', '..', '../..', 'CON', 'NUL'):
            self.assertNotIn(safe_name(name), ('.', '..', 'CON', 'NUL'))


if __name__ == "__main__":
    unittest.main(verbosity=2)
