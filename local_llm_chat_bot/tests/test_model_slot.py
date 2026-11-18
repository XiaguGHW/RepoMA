"""The model slot: one model task at a time, no global lock during model calls,
and only requests that cannot affect the running task are let through
(other saved sessions, diagnostics, model test, reading, UI language)."""

from pathlib import Path
import sys

APP = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(APP), str(APP / "tests")]

import threading  # noqa: E402
import unittest  # noqa: E402
from unittest.mock import patch  # noqa: E402

import chat_workbench as w  # noqa: E402
from api_cases import EnglishApiCase  # noqa: E402
from request_runtime import RequestControl  # noqa: E402
from workbench_tasks import ModelSlot  # noqa: E402


OPERATION_ID = "0123456789abcdef0123456789abcdef"


def lock_is_free_from_another_thread() -> bool:
    result = []

    def probe():
        acquired = w.LOCK.acquire(blocking=False)
        result.append(acquired)
        if acquired:
            w.LOCK.release()

    thread = threading.Thread(target=probe)
    thread.start()
    thread.join(5)
    return result == [True]


class ModelSlotUnit(unittest.TestCase):
    def test_reserve_is_exclusive_until_released(self):
        slot = ModelSlot()
        self.assertTrue(slot.reserve())
        self.assertTrue(slot.busy.is_set())
        self.assertFalse(slot.reserve())
        slot.release()
        self.assertFalse(slot.busy.is_set())
        self.assertTrue(slot.reserve())

    def test_operations_are_found_by_id_until_forgotten(self):
        slot, control = ModelSlot(), RequestControl()
        slot.register("op-1", control)
        slot.register("", RequestControl())  # no ID: not stoppable from the page
        self.assertIs(slot.control("op-1"), control)
        self.assertIsNone(slot.control(""))
        slot.forget("op-1")
        self.assertIsNone(slot.control("op-1"))

    def test_the_old_name_is_the_same_busy_event(self):
        self.assertIs(w.MODEL_WORK_IN_PROGRESS, w.MODEL_SLOT.busy)


class NoGlobalLockDuringModelCalls(EnglishApiCase):
    """Each model task runs with the slot taken and the global lock free."""

    def setUp(self):
        super().setUp()
        self.seen = []

    def record(self, value):
        self.seen.append((w.MODEL_WORK_IN_PROGRESS.is_set(), lock_is_free_from_another_thread()))
        return value

    def test_answer(self):
        self.bg()
        with patch.object(w, "call_model", lambda *a, **k: self.record({"answer": "ok"})):
            self.post("/api/chat", {"question": "classify"})
        self.assertEqual(self.seen, [(True, True)])
        self.assertFalse(w.MODEL_WORK_IN_PROGRESS.is_set())

    def test_comparison(self):
        self.bg()
        with patch.object(w, "call_comparison", lambda *a, **k: self.record({"results": []})):
            self.post("/api/compare", {"question": "classify", "models": ["gemini-2.5-pro", "claude-haiku-5-5"]})
        self.assertEqual(self.seen, [(True, True)])

    def test_coverage(self):
        self.bg()
        with patch.object(w, "prepare_coverage", lambda *a, **k: self.record({"complete": True})):
            self.post("/api/coverage", {})
        self.assertEqual(self.seen, [(True, True)])

    def test_dossier_rebuild(self):
        self.bg()
        self.post("/api/coverage", {})
        with patch.object(w, "prepare_bg_dossier", lambda *a, **k: self.record(({}, None, False))), \
                patch.object(w, "cache_audit", lambda data: {}):
            self.post("/api/cache/dossier/rebuild", {"confirmed": True})
        self.assertEqual(self.seen, [(True, True)])

    def test_rule_preparation(self):
        original = w.prepare_codebook_profile

        def prepare(*args, **kwargs):
            self.record(None)
            return original(*args, **kwargs)
        with patch.object(w, "prepare_codebook_profile", prepare):
            self.post("/api/codebook/prepare", {"path": str(self.f.rules)})
        self.assertEqual(self.seen, [(True, True)])
        self.assertFalse(w.MODEL_WORK_IN_PROGRESS.is_set())


class RequestsWhileModelWorkRuns(EnglishApiCase):
    """With the slot taken: other saved sessions may change, the task's context may not."""

    def setUp(self):
        super().setUp()
        state = w.ACTIVE["state"]
        self.active = state.root.name
        for name in ("other_a", "other_b"):
            w.ProjectState(w.app_state_home(), state.workspace, name).save()
        self.work = w.begin_model_work(OPERATION_ID)
        self.addCleanup(lambda: w.MODEL_WORK_IN_PROGRESS.is_set() and w.end_model_work(self.work))

    def status(self, method, path, body=None):
        return self.client.request(method, path, json=body).status_code

    def test_other_sessions_can_be_pinned_renamed_and_deleted(self):
        root = w.ACTIVE["state"].root.parent
        self.assertEqual(self.status("POST", "/api/session/pin", {"name": "other_a", "pinned": True}), 200)
        self.assertEqual(self.status("POST", "/api/session/rename", {"source": "other_a", "name": "renamed_a"}), 200)
        self.assertTrue((root / "renamed_a").is_dir())
        self.assertEqual(self.status("POST", "/api/session/delete", {"name": "other_b", "confirmed": True}), 200)
        self.assertFalse((root / "other_b").exists())
        self.assertTrue(w.MODEL_WORK_IN_PROGRESS.is_set())
        self.assertEqual(w.ACTIVE["state"].root.name, self.active)

    def test_the_active_session_stays_untouched(self):
        for body_path, body in [
            ("/api/session/pin", {"name": self.active, "pinned": True}),
            ("/api/session/rename", {"name": "renamed_active"}),
            ("/api/session/rename", {"source": self.active, "name": "renamed_active"}),
            ("/api/session/delete", {"confirmed": True}),
            ("/api/session/delete", {"name": self.active, "confirmed": True}),
        ]:
            with self.subTest(path=body_path, body=body):
                self.assertEqual(self.status("POST", body_path, body), 409)
        self.assertTrue(w.ACTIVE["state"].root.is_dir())
        self.assertEqual(w.ACTIVE["state"].root.name, self.active)

    def test_context_changes_are_refused(self):
        refused = [
            ("POST", "/api/setup", {"workspace": str(self.f.workspace), "model": "gemini-2.5-pro"}),
            ("POST", "/api/session/open", {"name": "other_a"}),
            ("POST", "/api/session/new", None),
            ("POST", "/api/model", {"model": "claude-haiku-5-5"}),
            ("POST", "/api/target", {"target": str(self.f.bg_a), "selected_paths": ["facts.txt"]}),
            ("POST", "/api/codebook/lock", {}),
            ("DELETE", "/api/codebook", None),
            ("POST", "/api/cache/clear", {"confirmed": True}),
            # A second model task.
            ("POST", "/api/coverage", {}),
        ]
        for method, path, body in refused:
            with self.subTest(path=path):
                self.assertEqual(self.status(method, path, body), 409)

    def test_diagnostics_and_model_test_run_without_touching_the_environment(self):
        environ = dict(w.os.environ)
        seen = []
        original = w.run_model_test

        def run(request, key, base_url):
            seen.append((dict(w.os.environ) == environ, base_url))
            return original(request, key, base_url)
        with patch.object(w, "run_model_test", run):
            response = self.client.post("/api/model-test", json={"model": "claude-haiku-5-5"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["ok"], response.text)
        self.assertEqual(seen, [(True, w.farm_base_url())])
        self.assertEqual(self.status("GET", "/api/diagnostics"), 200)
        self.assertEqual(dict(w.os.environ), environ)
        self.assertTrue(w.MODEL_WORK_IN_PROGRESS.is_set())

    def test_reading_and_language_keep_working(self):
        for path in ("/api/status", "/api/sessions", "/api/codebook", "/api/settings"):
            with self.subTest(path=path):
                self.assertEqual(self.status("GET", path), 200)
        self.assertEqual(self.status("POST", "/api/language", {"language": "de"}), 200)
        self.assertEqual(w.ACTIVE["language"], "de")

    def test_the_running_task_can_be_stopped_by_its_id(self):
        response = self.client.post("/api/operation/cancel", json={"request_id": OPERATION_ID})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["cancelled"])
        self.assertTrue(self.work["cancel_event"].is_set())
        w.end_model_work(self.work)
        self.assertEqual(self.client.post("/api/operation/cancel", json={"request_id": OPERATION_ID}).status_code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
