"""Material pre-reading: successful group notes are reused and outputs are
bounded by form, so a re-scan pays only for groups that failed (synthetic)."""

import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient  # noqa: E402
import chat_workbench as w  # noqa: E402
from fixture_support import FixtureEnvironment  # noqa: E402

GROUP_SYSTEM = "careful technical evidence extractor"


class MaterialPrereadCache(unittest.TestCase):
    def setUp(self):
        self.f = FixtureEnvironment().__enter__()
        self.addCleanup(self.f.__exit__, None, None, None)
        self.client = TestClient(w.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)
        self.post("/api/setup", {"workspace": str(self.f.workspace), "model": "gemini-2.5-pro", "language": "en"})
        # Three summary groups (each group holds up to ~24,000 characters).
        text = "\n\n".join(f"Abschnitt {index}: Motor treibt die Drehachse an. " + "Detail " * 400 for index in range(18))
        (self.f.bg_a / "manual.txt").write_text(text, encoding="utf-8")
        self.post("/api/target", {"target": str(self.f.bg_a), "selected_paths": ["manual.txt"]})
        self.document = next(item for item in w.ACTIVE["documents"].list() if item["name"] == "manual.txt")

    def post(self, path, body):
        response = self.client.post(path, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def group_calls(self, start=0):
        return [call for call in self.f.calls[start:]
                if GROUP_SYSTEM in json.dumps(call["body"]) and "完整文本片段组" in json.dumps(call["body"], ensure_ascii=False)]

    def merge_calls(self, start=0):
        return [call for call in self.f.calls[start:] if "片段笔记合成" in json.dumps(call["body"], ensure_ascii=False)]

    def fail_group(self, number):
        marker = f"这是第 {number}/"

        def transform(response, prompt, system):
            if GROUP_SYSTEM in system and marker in prompt:
                response["candidates"][0]["finishReason"] = "MAX_TOKENS"
            return response
        self.f.response_transform = transform

    def file_record(self, report):
        return next(item for item in report["files"] if item["name"] == "manual.txt")

    def test_rescan_after_a_failed_group_pays_only_for_that_group(self):
        groups = len(w.summary_groups(self.document, self.document["chunks"], folder=self.f.bg_a))
        self.assertGreaterEqual(groups, 3)
        self.fail_group(2)
        first = self.file_record(self.post("/api/coverage", {}))
        self.assertFalse(first["complete"])
        self.assertEqual((first["text_groups_processed"], first["text_groups_reused"]), (groups - 1, 0))
        self.assertEqual(len(self.group_calls()), groups)
        self.f.response_transform = None
        before = len(self.f.calls)
        second = self.file_record(self.post("/api/coverage", {}))
        self.assertTrue(second["complete"])
        self.assertEqual((second["text_groups_processed"], second["text_groups_reused"]), (groups, groups - 1))
        retried = self.group_calls(before)
        self.assertEqual(len(retried), 1)  # only the group that failed
        self.assertIn(f"这是第 2/{groups}", json.dumps(retried[0]["body"], ensure_ascii=False))
        self.assertEqual(len(self.merge_calls(before)), 1)
        # A complete file is then served from the existing per-file cache.
        before = len(self.f.calls)
        third = self.file_record(self.post("/api/coverage", {}))
        self.assertEqual((third["cache_status"], len(self.f.calls) - before), ("reused", 0))

    def test_group_notes_are_bound_to_model_and_cleared_with_the_file_cache(self):
        self.fail_group(1)
        self.post("/api/coverage", {})
        self.f.response_transform = None
        notes = list((w.app_state_home() / "material_cache" / self.document["sha256"] / "groups").glob("*.json"))
        self.assertTrue(notes)
        self.assertTrue(all(json.loads(path.read_text(encoding="utf-8"))["model"] == "gemini-2.5-pro" for path in notes))
        # Another model never reuses these notes.
        self.post("/api/model", {"model": "gemini-2.5-flash"})
        self.post("/api/target", {"target": str(self.f.bg_a), "selected_paths": ["manual.txt"]})
        before = len(self.f.calls)
        groups = len(w.summary_groups(self.document, self.document["chunks"], folder=self.f.bg_a))
        self.assertEqual(self.file_record(self.post("/api/coverage", {}))["text_groups_reused"], 0)
        self.assertEqual(len(self.group_calls(before)), groups)
        # Rebuilding the file removes its group notes too.
        self.post("/api/cache/file/rebuild", {"document_id": self.document["id"], "confirmed": True})
        self.assertFalse((w.app_state_home() / "material_cache" / self.document["sha256"]).exists())

    def test_group_and_merge_outputs_are_bounded_by_form(self):
        self.post("/api/coverage", {})
        group = json.dumps(self.group_calls()[0]["body"], ensure_ascii=False)
        self.assertIn("最多 10 条要点", group)
        self.assertEqual(self.group_calls()[0]["body"]["generationConfig"]["maxOutputTokens"], 900)
        merge = self.merge_calls()[0]["body"]
        self.assertIn("最多 15 条要点", json.dumps(merge, ensure_ascii=False))
        self.assertEqual(merge["generationConfig"]["maxOutputTokens"], 1400)
        # A stored note from another prompt version is ignored, not reused.
        path = w.material_group_note_path(self.document, "gemini-2.5-pro", "group text")
        w.write_json_atomically(path, {"version": "older-prompt", "model": "gemini-2.5-pro", "note": "old"})
        self.assertIsNone(w.load_material_group_note(self.document, "gemini-2.5-pro", "group text"))
        w.save_material_group_note(self.document, "gemini-2.5-pro", "group text", "new")
        self.assertEqual(w.load_material_group_note(self.document, "gemini-2.5-pro", "group text"), "new")


if __name__ == "__main__":
    unittest.main(verbosity=2)
