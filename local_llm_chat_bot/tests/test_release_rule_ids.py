"""F-03: rule IDs are unique before rules can be saved, locked or used (synthetic only)."""

import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import chat_workbench as w
from fixture_support import FixtureEnvironment, PROFILE


def all_ids(draft):
    return [rule["id"] for _owner, rule in w.profile_rules_in_order(draft)]


class RuleIds(unittest.TestCase):
    def setUp(self):
        self.f = FixtureEnvironment().__enter__()
        self.addCleanup(self.f.__exit__, None, None, None)
        self.client = TestClient(w.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)
        self.post("/api/setup", {"workspace": str(self.f.workspace), "model": "gemini-2.5-pro", "language": "en"})

    def post(self, path, body):
        response = self.client.post(path, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def duplicate_draft(self):
        draft = copy.deepcopy(PROFILE)
        draft["classes"].append({"name": "Gantry", "definition": "Moves along axes.",
                                 "decision_rules": [{"id": "rotation-1", "text": "Different rule.", "pages": [1]}],
                                 "boundaries": [], "evidence_pages": [1]})
        return draft

    def test_generated_ids_never_collide(self):
        draft = w.parse_codebook_draft(json.dumps({"classes": [
            {"name": "Greifer/Endeffektor", "definition": "a", "decision_rules": ["one", "two"]},
            {"name": "Greifer Endeffektor", "definition": "b", "decision_rules": ["three"],
             "boundaries": [{"id": "greifer-endeffektor-boundary-1", "text": "explicit"}, "generated"]}],
            "global_rules": ["g"]}))
        ids = all_ids(draft)
        self.assertEqual(len(ids), len(set(ids)), ids)
        self.assertIn("greifer-endeffektor-boundary-1", ids)  # explicit ID kept verbatim
        self.assertEqual(w.rule_id_conflicts(draft), [])

    def test_edit_with_duplicate_explicit_ids_is_rejected_and_saves_nothing(self):
        self.post("/api/codebook/prepare", {"path": str(self.f.rules)})
        before = w.codebook_profile_path().read_bytes()
        response = self.client.post("/api/codebook/edit", json={"draft": self.duplicate_draft(), "confirmed": True,
                                                                "profile_version": w.load_codebook_profile()["version"]})
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(response.json()["message_key"], "rules.duplicate_ids")
        self.assertIn("rotation-1", response.json()["detail"])
        self.assertEqual(w.codebook_profile_path().read_bytes(), before)

    def test_lock_rejects_a_stored_draft_with_duplicates(self):
        self.post("/api/codebook/prepare", {"path": str(self.f.rules)})
        profile = w.load_codebook_profile()
        profile["draft"] = self.duplicate_draft()
        w.save_codebook_profile(profile)
        response = self.client.post("/api/codebook/lock", json={})
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(response.json()["message_key"], "rules.duplicate_ids")
        self.assertEqual(w.load_codebook_profile()["status"], "draft")

    def test_model_merged_duplicates_are_renamed_then_classification_works(self):
        duplicated = self.duplicate_draft()

        def merge(response, prompt, system):
            if "consolidate page-by-page" in system:
                response["candidates"][0]["content"]["parts"][0]["text"] = json.dumps(duplicated)
            return response
        self.f.response_transform = merge
        profile = self.post("/api/codebook/prepare", {"path": str(self.f.rules)})
        self.f.response_transform = None
        ids = all_ids(profile["draft"])
        self.assertEqual(len(ids), len(set(ids)), ids)
        self.assertIn("rotation-1", ids)  # the first use keeps its ID
        self.assertEqual(profile["rule_id_renames"], [{"from": "rotation-1", "to": "gantry:rotation-1"}])
        self.post("/api/codebook/lock", {})
        self.post("/api/target", {"target": str(self.f.bg_a), "selected_paths": ["facts.txt"]})
        result = self.post("/api/chat", {"question": "Classify this Baugruppe"})
        self.assertEqual(result["classification"]["codebook_rule_ids"], ["rotation-1"])

    def test_previously_locked_duplicates_stop_before_any_model_call(self):
        self.post("/api/codebook/prepare", {"path": str(self.f.rules)})
        self.post("/api/codebook/lock", {})
        self.post("/api/target", {"target": str(self.f.bg_a), "selected_paths": ["facts.txt"]})
        # Simulate a profile and session locked by a version without the uniqueness rule.
        profile = w.load_codebook_profile()
        profile["draft"] = self.duplicate_draft()
        w.write_json_atomically(w.codebook_profile_path(), profile)
        state = w.ACTIVE["state"]
        state.data["bg_context"]["locked_profile"] = copy.deepcopy(profile["draft"])
        state.save()
        calls = len(self.f.calls)
        for path, body in [("/api/chat", {"question": "Classify this Baugruppe"}),
                           ("/api/target", {"target": str(self.f.bg_a), "selected_paths": ["facts.txt"]})]:
            with self.subTest(path=path):
                response = self.client.post(path, json=body)
                self.assertEqual(response.status_code, 409, response.text)
                self.assertEqual(response.json()["message_key"], "rules.duplicate_ids")
        self.assertEqual(len(self.f.calls), calls)


if __name__ == "__main__":
    unittest.main(verbosity=2)
