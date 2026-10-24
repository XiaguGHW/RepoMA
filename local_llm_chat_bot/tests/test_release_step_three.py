"""R05–R08 scope recovery, transactional selection and shared model guards."""

import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import chat_workbench as w
from fixture_support import FixtureEnvironment, PROFILE
from local_document_library import LocalDocumentLibrary


class StepThree(unittest.TestCase):
    def setUp(self):
        self.f = FixtureEnvironment().__enter__()
        self.addCleanup(self.f.__exit__, None, None, None)
        self.client = TestClient(w.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)
        self.setup_body = {
            "workspace": str(self.f.workspace),
            "model": "gemini-2.5-pro",
            "language": "en",
        }
        self.post("/api/setup", self.setup_body)

    def post(self, path, body):
        result = self.client.post(path, json=body)
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def bg(self):
        self.post("/api/codebook/prepare", {"path": str(self.f.rules)})
        self.post("/api/codebook/lock", {})
        self.post(
            "/api/target", {"target": str(self.f.bg_a), "selected_paths": ["facts.txt"]}
        )

    def model_endpoints(self):
        return [
            ("/api/chat", {"question": "classify"}),
            ("/api/chat/stream", {"question": "classify"}),
            (
                "/api/compare",
                {
                    "question": "classify",
                    "models": ["gemini-2.5-pro", "gemini-2.5-flash"],
                },
            ),
            ("/api/coverage", {}),
            ("/api/cache/dossier/rebuild", {"confirmed": True}),
        ]

    def blocked(self, endpoint, body):
        count = len(self.f.calls)
        result = self.client.post(endpoint, json=body)
        self.assertEqual(result.status_code, 409, result.text)
        self.assertEqual(len(self.f.calls), count)
        self.assertFalse(w.MODEL_WORK_IN_PROGRESS.is_set())

    def snapshot(self):
        state, documents = w.ACTIVE["state"], w.ACTIVE["documents"]
        paths = [
            state.path,
            documents.path,
            state.transcript_path,
            w.coverage_path(state),
            w.material_selections_path(),
        ]
        return {
            "state": copy.deepcopy(state.data),
            "documents": copy.deepcopy(documents.data),
            "pending": copy.deepcopy(w.ACTIVE.get("pending")),
            "plan": copy.deepcopy(w.ACTIVE.get("pending_plan")),
            "files": {
                str(path): path.read_bytes() if path.exists() else None
                for path in paths
            },
            "archives": sorted(
                str(path) for path in (state.root / "archives").glob("*")
            ),
        }

    def test_corrupt_nested_states_preserve_history_usage_and_quarantine(self):
        self.bg()
        self.post("/api/chat", {"question": "classify"})
        clean = copy.deepcopy(w.ACTIVE["state"].data)
        for key, value in [
            ("bg_context", ["legacy-invalid"]),
            ("bg_context", "broken"),
            ("active_source_ids", {}),
            ("selected_target", {"path": "bad", "kind": []}),
            ("context_schema_version", 900),
            (
                "bg_context",
                {**clean["bg_context"], "locked_profile": {"classes": ["invalid"]}},
            ),
        ]:
            with self.subTest(key=key, value=value):
                state = w.ACTIVE["state"]
                state.data = copy.deepcopy(clean)
                state.data[key] = value
                state.save()
                status = self.post("/api/setup", self.setup_body)
                current = w.ACTIVE["state"]
                self.assertEqual(status["context_issue"], "restored_invalid")
                self.assertEqual(current.data["history"], clean["history"])
                self.assertEqual(current.data["usage"], clean["usage"])
                self.assertEqual(current.data["active_source_ids"], [])
                quarantined = list((current.root / "quarantine").glob("state-*.json"))
                self.assertTrue(
                    any(
                        json.loads(path.read_text(encoding="utf-8")).get(key) == value
                        for path in quarantined
                    )
                )
                for endpoint, body in self.model_endpoints():
                    self.blocked(endpoint, body)
        self.post(
            "/api/target", {"target": str(self.f.bg_a), "selected_paths": ["facts.txt"]}
        )
        self.assertEqual(self.client.get("/api/status").json()["context_issue"], "")
        self.post("/api/chat", {"question": "classify"})

    def test_legacy_valid_scope_without_version_is_migrated(self):
        self.bg()
        state = w.ACTIVE["state"]
        for key in ("context_schema_version", "context_revision", "source_binding"):
            state.data.pop(key, None)
        state.save()
        self.post("/api/setup", self.setup_body)
        self.assertEqual(w.ACTIVE["state"].data["context_schema_version"], 1)
        self.assertTrue(w.ACTIVE["state"].data["source_binding"])
        self.post("/api/chat", {"question": "classify"})

    def test_rule_changes_in_another_session_and_cache_revision_are_rejected(self):
        self.bg()
        self.post("/api/chat", {"question": "classify"})
        old_coverage = copy.deepcopy(w.load_coverage(w.ACTIVE["state"]))
        self.post("/api/session/new", {})
        self.post("/api/codebook/prepare", {"path": str(self.f.rules)})
        self.post("/api/codebook/lock", {})
        self.post("/api/session/open", {"name": "default"})
        self.assertEqual(
            self.client.get("/api/status").json()["context_issue"], "rules_changed"
        )
        for endpoint, body in self.model_endpoints():
            self.blocked(endpoint, body)
        self.post(
            "/api/target", {"target": str(self.f.bg_a), "selected_paths": ["facts.txt"]}
        )
        self.assertFalse(w.coverage_matches_current_selection(w.ACTIVE, old_coverage))
        with self.assertRaises(w.HTTPException):
            w.prepare_bg_dossier(w.ACTIVE, old_coverage)
        self.post("/api/chat", {"question": "classify"})
        self.assertTrue(w.coverage_matches_current_selection(w.ACTIVE))

    def test_corrupt_index_chunks_are_quarantined_and_never_sent(self):
        self.bg()
        original = copy.deepcopy(w.ACTIVE["documents"].data)
        for chunks in [
            "invalid",
            [None],
            [{"label": "facts", "text": 4}],
            [{"label": "facts", "text": "", "visual": []}],
        ]:
            with self.subTest(chunks=chunks):
                index = copy.deepcopy(original)
                index["documents"][0]["chunks"] = chunks
                w.ACTIVE["documents"].path.write_text(
                    json.dumps(index), encoding="utf-8"
                )
                status = self.post("/api/setup", self.setup_body)
                self.assertEqual(status["context_issue"], "index_invalid")
                self.assertTrue(
                    list(
                        (w.ACTIVE["documents"].path.parent / "quarantine").glob(
                            "documents-*.json"
                        )
                    )
                )
                for endpoint, body in self.model_endpoints():
                    self.blocked(endpoint, body)
        self.post(
            "/api/target", {"target": str(self.f.bg_a), "selected_paths": ["facts.txt"]}
        )
        self.post("/api/chat", {"question": "classify"})

    def test_failed_target_prepare_and_commit_preserve_every_active_record(self):
        self.bg()
        self.post("/api/chat", {"question": "classify"})
        w.publish_pending(
            w.ACTIVE,
            w.build_diff(
                w.ACTIVE["state"], [{"path": "pending.txt", "content": "reviewed"}]
            ),
        )
        body = {"target": str(self.f.bg_b), "selected_paths": ["facts.txt"]}
        for location in (
            "parse",
            "permission",
            "state_save",
            "index_save",
            "selection_save",
            "archive",
        ):
            with self.subTest(location=location):
                before = self.snapshot()
                if location in ("parse", "permission"):
                    real_add = LocalDocumentLibrary.add

                    def fail_add(library, path):
                        if Path(path).parent == self.f.bg_b:
                            raise (
                                ValueError("bad parser")
                                if location == "parse"
                                else PermissionError("unreadable")
                            )
                        return real_add(library, path)

                    fault = patch.object(LocalDocumentLibrary, "add", fail_add)
                elif location == "state_save":
                    fault = patch.object(
                        w.ACTIVE["state"],
                        "save",
                        side_effect=OSError("cannot save state"),
                    )
                elif location == "index_save":
                    real_save = LocalDocumentLibrary._save

                    def fail_index(library):
                        if not getattr(library, "_defer_save", False):
                            raise OSError("cannot save index")
                        return real_save(library)

                    fault = patch.object(LocalDocumentLibrary, "_save", fail_index)
                elif location == "selection_save":
                    fault = patch.object(
                        w,
                        "save_material_selection",
                        side_effect=OSError("cannot save selection"),
                    )
                else:
                    real_replace = Path.replace

                    def fail_archive(path, target):
                        if path == w.ACTIVE["state"].transcript_path:
                            raise PermissionError("archive locked")
                        return real_replace(path, target)

                    fault = patch.object(Path, "replace", fail_archive)
                with fault:
                    result = self.client.post("/api/target", json=body)
                self.assertNotEqual(result.status_code, 200)
                self.assertEqual(self.snapshot(), before)
        result = self.post("/api/target", body)
        self.assertEqual(result["sources"], 1)
        self.assertEqual(w.ACTIVE["state"].data["history"], [])
        self.assertEqual(w.ACTIVE["pending"], [])

    def test_changed_rule_rejected_before_any_target_mutation(self):
        self.bg()
        self.post("/api/chat", {"question": "classify"})
        before = self.snapshot()
        with self.f.rules.open("ab") as handle:
            handle.write(b"changed fixture")
        result = self.client.post(
            "/api/target",
            json={"target": str(self.f.bg_b), "selected_paths": ["facts.txt"]},
        )
        self.assertEqual(result.status_code, 409)
        self.assertEqual(self.snapshot(), before)

    def test_relocked_rules_require_same_bg_reconfirmation_for_every_model_entry(self):
        self.bg()
        self.post("/api/chat", {"question": "classify"})
        target = copy.deepcopy(w.ACTIVE["state"].data["selected_target"])
        draft = copy.deepcopy(PROFILE)
        draft["classes"][0]["name"] = "Reconfirmed fixture class"
        self.post("/api/codebook/edit", {"draft": draft, "confirmed": True})
        self.post("/api/codebook/lock", {})
        self.assertEqual(w.ACTIVE["state"].data["selected_target"], target)
        self.assertEqual(
            self.client.get("/api/status").json()["context_issue"], "rules_changed"
        )
        for endpoint, body in self.model_endpoints():
            self.blocked(endpoint, body)
        self.post(
            "/api/target",
            {"target": str(self.f.bg_a), "selected_paths": target["selected_paths"]},
        )
        answer = self.post("/api/chat", {"question": "classify"})
        self.assertEqual(answer["classification"]["label"], "Reconfirmed fixture class")
        self.post(
            "/api/compare",
            {"question": "classify", "models": ["gemini-2.5-pro", "gemini-2.5-flash"]},
        )

    def test_cancelled_edit_preserves_scope_and_explicit_normal_mode_is_available(self):
        self.bg()
        before = self.snapshot()
        response = self.client.post(
            "/api/codebook/edit", json={"draft": PROFILE, "confirmed": False}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.snapshot(), before)
        self.post("/api/codebook/edit", {"draft": PROFILE, "confirmed": True})
        self.assertEqual(self.client.delete("/api/bg").status_code, 200)
        self.post("/api/chat", {"question": "Explain the motor"})

    def test_changed_deleted_missing_and_changed_scope_block_every_entry(self):
        self.bg()
        self.post("/api/chat", {"question": "classify"})
        original_state = copy.deepcopy(w.ACTIVE["state"].data)
        fact = self.f.bg_a / "facts.txt"
        raw = fact.read_bytes()
        rule_raw = self.f.rules.read_bytes()
        for cause in ("changed", "deleted", "missing_index", "scope", "rule_bytes"):
            with self.subTest(cause=cause):
                w.ACTIVE["state"].data = copy.deepcopy(original_state)
                index = copy.deepcopy(w.ACTIVE["documents"].data)
                if cause == "changed":
                    fact.write_text("new source")
                elif cause == "deleted":
                    fact.unlink()
                elif cause == "missing_index":
                    w.ACTIVE["documents"].data["documents"] = []
                elif cause == "scope":
                    w.ACTIVE["state"].data["active_source_ids"] = []
                else:
                    with self.f.rules.open("ab") as handle:
                        handle.write(b"changed fixture")
                for endpoint, body in self.model_endpoints():
                    self.blocked(endpoint, body)
                document_id = original_state["active_source_ids"][0]
                self.blocked(
                    "/api/cache/file/rebuild",
                    {"confirmed": True, "document_id": document_id},
                )
                fact.write_bytes(raw)
                self.f.rules.write_bytes(rule_raw)
                w.ACTIVE["documents"].data = index
        w.ACTIVE["state"].data = original_state
        self.post(
            "/api/compare",
            {"question": "classify", "models": ["gemini-2.5-pro", "gemini-2.5-flash"]},
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
