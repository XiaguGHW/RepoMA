"""Rules, BG selection and sessions stay consistent: changes, stale results, corrupt state."""

from __future__ import annotations

from pathlib import Path
import sys

APP = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(APP), str(APP / "tests")]

import copy  # noqa: E402
import json  # noqa: E402
import unittest  # noqa: E402
from unittest.mock import patch  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import chat_workbench as w  # noqa: E402
from fixture_support import FixtureEnvironment, PROFILE  # noqa: E402
from local_document_library import LocalDocumentLibrary  # noqa: E402
import asyncio  # noqa: E402
from code_chat_agent import ProjectState  # noqa: E402
from types import SimpleNamespace  # noqa: E402
import chat_workbench as workbench  # noqa: E402
from api_cases import DirectSessionCase, EnglishApiCase  # noqa: E402


class ContextIntegrity(unittest.TestCase):
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
        self.post("/api/codebook/edit", {"draft": draft, "confirmed": True,
                                         "profile_version": w.load_codebook_profile()["version"]})
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
            "/api/codebook/edit", json={"draft": PROFILE, "confirmed": False,
                                          "profile_version": w.load_codebook_profile()["version"]}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.snapshot(), before)
        self.post("/api/codebook/edit", {"draft": PROFILE, "confirmed": True,
                                         "profile_version": w.load_codebook_profile()["version"]})
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


class StaleResults(unittest.TestCase):
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

    def prepare_bg(self):
        self.post("/api/codebook/prepare", {"path": str(self.f.rules)})
        self.post("/api/codebook/lock", {})
        self.post("/api/target", {"target": str(self.f.bg_a), "selected_paths": ["facts.txt"]})

    def test_comparison_never_uses_a_completed_but_stale_coverage_summary(self):
        self.prepare_bg()
        self.post("/api/coverage", {})
        coverage = w.load_coverage(w.ACTIVE["state"])
        coverage["context_revision"] = "stale-context-revision"
        coverage["files"][0]["summary"] = "STALE_COVERAGE_SENTINEL"
        w.write_json_atomically(w.coverage_path(w.ACTIVE["state"]), coverage)

        before = len(self.f.calls)
        self.post("/api/compare", {"question": "Classify this Baugruppe", "models": ["gemini-2.5-pro", "gemini-2.5-flash"]})
        prompts = str(self.f.calls[before:])
        self.assertNotIn("STALE_COVERAGE_SENTINEL", prompts)

    def test_changed_source_after_model_response_cannot_commit_old_result(self):
        self.prepare_bg()
        state = w.ACTIVE["state"]
        history = copy.deepcopy(state.data["history"])
        original = w.ACTIVE["llm"].ask_about_files

        def mutate_source_then_answer(*args, **kwargs):
            (self.f.bg_a / "facts.txt").write_text("Changed while the model was running.", encoding="utf-8")
            return original(*args, **kwargs)

        with patch.object(w.ACTIVE["llm"], "ask_about_files", side_effect=mutate_source_then_answer):
            response = self.client.post("/api/chat", json={"question": "Classify this Baugruppe"})
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(state.data["history"], history)
        self.assertIsNone(state.data.get("last_bg_analysis"))

    def test_base_exception_in_worker_always_releases_model_slot(self):
        class NeverDisconnect:
            async def is_disconnected(self):
                return False

        class SynchronousThread:
            def __init__(self, *, target=None, daemon=False):
                self.target = target
                self.daemon = daemon
                self._alive = False

            def start(self):
                self._alive = True
                try:
                    self.target()
                except BaseException:
                    pass
                finally:
                    self._alive = False

            def join(self):
                return None

            def is_alive(self):
                return self._alive

        with patch.object(w, "call_model", side_effect=KeyboardInterrupt("fixture")), patch.object(w.threading, "Thread", SynchronousThread):
            asyncio.run(w.chat_stream(w.ChatRequest(question="Explain the workspace"), NeverDisconnect()))
        self.assertTrue(w.CHAT_TASK["done"].is_set())
        self.assertEqual(w.CHAT_TASK["state"], "failed")
        self.assertFalse(w.MODEL_WORK_IN_PROGRESS.is_set())

    def test_rule_edits_require_the_current_profile_version(self):
        profile = self.post("/api/codebook/prepare", {"path": str(self.f.rules)})
        before = w.codebook_profile_path().read_bytes()
        body = {"draft": profile["draft"], "confirmed": True}

        missing = self.client.post("/api/codebook/edit", json=body)
        self.assertEqual(missing.status_code, 400, missing.text)
        self.assertEqual(missing.json()["message_key"], "rules.version_required")
        self.assertEqual(w.codebook_profile_path().read_bytes(), before)

        stale = self.client.post("/api/codebook/edit", json={**body, "profile_version": "old-version"})
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertEqual(stale.json()["message_key"], "rules.version_changed")
        self.assertEqual(w.codebook_profile_path().read_bytes(), before)


class ContextChanges(EnglishApiCase):
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
        self.post("/api/codebook/edit", {"draft": draft, "confirmed": True,
                                         "profile_version": w.load_codebook_profile()["version"]})
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


class SessionState(DirectSessionCase):
    def test_single_file_without_codebook(self):
        source = self.root / 'Bauteil 中文 ü.txt'
        source.write_text('linear motor evidence', encoding='utf-8')
        result = w.analyze_target(w.TargetRequest(target=str(source)))
        self.assertFalse(result['classification'])

    def test_target_switch_clears_old_prompt_and_export(self):
        state = w.ACTIVE['state']
        state.add_turn('assistant', 'OLD_BG_SECRET')
        state.data['last_bg_analysis'] = {'answer': 'OLD_BG_SECRET'}
        source = self.root / 'BG_B.txt'
        source.write_text('New assembly')
        try:
            w.analyze_target(w.TargetRequest(target=str(source)))
        except UnboundLocalError:
            pass  # independent regression for context isolation
        self.assertEqual(state.data['history'], [])
        self.assertNotIn('last_bg_analysis', state.data)

    def test_setup_invalid_model_preserves_active_session(self):
        before = w.ACTIVE['state']
        with self.assertRaises(Exception):
            w.setup(w.Setup(workspace=str(self.workspace), state_dir='', model='unknown'))
        self.assertIs(w.ACTIVE.get('state'), before)

    def test_corrupt_state_types_and_legacy_missing_fields(self):
        state = w.ACTIVE['state']
        for value in ([], {'workspace': str(self.workspace)}, {'workspace': str(self.workspace), 'usage': None}):
            with self.subTest(value=value):
                state.path.write_text(json.dumps(value))
                loaded = ProjectState(w.app_state_home(), self.workspace, 'default')
                self.assertIsInstance(loaded.data['history'], list)
                self.assertIsInstance(loaded.data['files'], dict)
                self.assertIsInstance(loaded.data['usage'], dict)


class ModelSlot(unittest.TestCase):
    def setUp(self):
        self.old_active = dict(workbench.ACTIVE)
        workbench.ACTIVE.clear()
        workbench.MODEL_WORK_IN_PROGRESS.clear()

    def tearDown(self):
        workbench.ACTIVE.clear()
        workbench.ACTIVE.update(self.old_active)
        workbench.MODEL_WORK_IN_PROGRESS.clear()

    def test_begin_model_work_blocks_a_second_model_task(self):
        workbench.ACTIVE.update({"state": object()})
        workbench.begin_model_work()
        with self.assertRaises(workbench.HTTPException) as blocked:
            workbench.begin_model_work()
        self.assertEqual(blocked.exception.status_code, 409)

    def test_rebuild_releases_slot_after_success_and_exception(self):
        state = SimpleNamespace(data={}, note_usage=lambda *_args, **_kwargs: None)
        workbench.ACTIVE.update({"state": state, "model": "test-model", "pricing": object(),
                                 "documents": SimpleNamespace(list=lambda: [])})
        originals = (workbench.load_coverage, workbench.coverage_matches_current_selection,
                     workbench.prepare_bg_dossier, workbench.cache_audit)
        workbench.load_coverage = lambda _state: {"files": [{"summary": "ready"}]}
        workbench.coverage_matches_current_selection = lambda _data, _coverage: True
        workbench.cache_audit = lambda _data: {"dossier": {"ready": True}}
        try:
            def successful_rebuild(_data, _coverage, *, force=False):
                self.assertTrue(force)
                self.assertTrue(workbench.MODEL_WORK_IN_PROGRESS.is_set())
                with self.assertRaises(workbench.HTTPException):
                    workbench.begin_model_work()
                return {"summary": "fresh"}, None, True

            workbench.prepare_bg_dossier = successful_rebuild
            result = workbench.rebuild_bg_dossier(workbench.CacheConfirmRequest(confirmed=True))
            self.assertEqual(result["dossier"]["summary"], "fresh")
            self.assertFalse(workbench.MODEL_WORK_IN_PROGRESS.is_set())

            def failed_rebuild(_data, _coverage, *, force=False):
                raise RuntimeError("simulated model failure")

            workbench.prepare_bg_dossier = failed_rebuild
            with self.assertRaisesRegex(RuntimeError, "simulated model failure"):
                workbench.rebuild_bg_dossier(workbench.CacheConfirmRequest(confirmed=True))
            self.assertFalse(workbench.MODEL_WORK_IN_PROGRESS.is_set())
        finally:
            (workbench.load_coverage, workbench.coverage_matches_current_selection,
             workbench.prepare_bg_dossier, workbench.cache_audit) = originals


if __name__ == "__main__":
    unittest.main(verbosity=2)
