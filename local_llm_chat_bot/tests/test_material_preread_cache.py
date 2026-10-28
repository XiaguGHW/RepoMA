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

    def fail_group(self, number, reason="SAFETY", parts=()):
        """Fail group ``number``; MAX_TOKENS is an output-limit stop.

        The whole group fails; with ``parts`` the listed split halves fail too.
        """
        marker = f"这是第 {number}/"

        def transform(response, prompt, system):
            if GROUP_SYSTEM in system and marker in prompt:
                part = next((index for index in (1, 2) if f"第 {index}/2 部分" in prompt), None)
                if part is None or part in parts:
                    response["candidates"][0]["finishReason"] = reason
            return response
        self.f.response_transform = transform

    def groups(self):
        return len(w.summary_groups(self.document, self.document["chunks"], folder=self.f.bg_a))

    def part_calls(self, start=0):
        return [call for call in self.group_calls(start) if "部分。" in json.dumps(call["body"], ensure_ascii=False)]

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
        self.fail_group(1)  # a non-output-limit failure is not split
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

    def test_cut_group_is_split_once_and_completes_in_the_same_scan(self):
        groups = self.groups()
        self.fail_group(2, "MAX_TOKENS")
        report = self.post("/api/coverage", {})
        record = self.file_record(report)
        self.assertTrue(record["complete"], record.get("failures"))
        self.assertEqual((record["retry_calls"], report["retry_calls"], report["retry_limit"]), (2, 2, w.material_retry_limit(groups)))
        self.assertEqual(len(self.group_calls()), groups + 2)  # one wasted call, then two halves
        halves = self.part_calls()
        self.assertEqual(len(halves), 2)
        self.assertTrue(all(call["body"]["generationConfig"]["maxOutputTokens"] == w.MATERIAL_GROUP_TOKENS for call in halves))  # no budget increase
        # Each half keeps an evidence label.
        for call in halves:
            self.assertRegex(json.dumps(call["body"], ensure_ascii=False), r"--- manual\.txt — section \d+/\d+ ---")
        # The joined note is cached under the whole group: a rebuild of the
        # per-file summary costs only the merge.
        for path in (w.app_state_home() / "material_cache" / self.document["sha256"]).glob("*.json"):
            path.unlink()  # per-file summaries only; group notes stay
        w.coverage_path(w.ACTIVE["state"]).unlink()
        self.f.response_transform = None
        before = len(self.f.calls)
        self.post("/api/coverage", {})
        self.assertEqual((len(self.group_calls(before)), len(self.merge_calls(before))), (0, 1))

    def test_a_half_that_is_still_cut_stays_a_reported_gap_and_is_retried_alone(self):
        self.fail_group(1, "MAX_TOKENS", parts=(2,))
        record = self.file_record(self.post("/api/coverage", {}))
        self.assertFalse(record["complete"])
        self.assertEqual([item["message_key"] for item in record["failure_messages"]], ["reading.part_failed"])
        self.assertEqual(record["failure_messages"][0]["params"]["part"], 2)
        # Never split twice: exactly the whole group and its two halves.
        self.assertEqual(len([c for c in self.group_calls() if "这是第 1/" in json.dumps(c["body"], ensure_ascii=False)]), 3)
        self.f.response_transform = None
        before = len(self.f.calls)
        record = self.file_record(self.post("/api/coverage", {}))
        self.assertTrue(record["complete"])
        calls = self.group_calls(before)
        self.assertEqual(len(calls), 1)  # the whole group and the good half are not paid for again
        self.assertIn("第 2/2 部分", json.dumps(calls[0]["body"], ensure_ascii=False))

    def test_retry_allowance_bounds_extra_calls_per_scan(self):
        groups = self.groups()
        limit = w.material_retry_limit(groups)
        self.assertEqual(limit, 2)
        marker = "完整文本片段组"

        def every_whole_group_cut(response, prompt, system):
            if GROUP_SYSTEM in system and marker in prompt and "部分。" not in prompt:
                response["candidates"][0]["finishReason"] = "MAX_TOKENS"
            return response
        self.f.response_transform = every_whole_group_cut
        report = self.post("/api/coverage", {})
        record = self.file_record(report)
        self.assertEqual(report["retry_calls"], limit)
        self.assertEqual(len(self.group_calls()), groups + limit)
        limited = [item for item in record["failure_messages"] if item["message_key"] == "reading.retry_limit"]
        self.assertEqual(len(limited), groups - 1)
        self.assertEqual(limited[0]["params"]["limit"], limit)
        self.assertFalse(record["complete"])
        self.assertEqual([w.material_retry_limit(n) for n in (1, 10, 11, 30, 50, 200)], [2, 2, 3, 6, 10, 10])

    def test_group_and_merge_outputs_are_bounded_by_form(self):
        self.post("/api/coverage", {})
        group = json.dumps(self.group_calls()[0]["body"], ensure_ascii=False)
        self.assertIn("最多 10 条要点", group)
        self.assertEqual(self.group_calls()[0]["body"]["generationConfig"]["maxOutputTokens"], w.MATERIAL_GROUP_TOKENS)
        merge = self.merge_calls()[0]["body"]
        self.assertIn("最多 15 条要点", json.dumps(merge, ensure_ascii=False))
        self.assertEqual(merge["generationConfig"]["maxOutputTokens"], w.MATERIAL_MERGE_TOKENS)
        # A stored note from another prompt version is ignored, not reused.
        path = w.material_group_note_path(self.document, "gemini-2.5-pro", "group text")
        w.write_json_atomically(path, {"version": "older-prompt", "model": "gemini-2.5-pro", "note": "old"})
        self.assertIsNone(w.load_material_group_note(self.document, "gemini-2.5-pro", "group text"))
        w.save_material_group_note(self.document, "gemini-2.5-pro", "group text", "new")
        self.assertEqual(w.load_material_group_note(self.document, "gemini-2.5-pro", "group text"), "new")


if __name__ == "__main__":
    unittest.main(verbosity=2)
