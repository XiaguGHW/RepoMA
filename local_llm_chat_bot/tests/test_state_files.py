"""State files carry a format version; old files are migrated when read."""

from pathlib import Path
import sys

APP = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(APP), str(APP / "tests")]

import json  # noqa: E402
import tempfile  # noqa: E402
from types import SimpleNamespace  # noqa: E402
import unittest  # noqa: E402
from unittest.mock import patch  # noqa: E402

import chat_workbench as w  # noqa: E402
import workbench_state_files as state_files  # noqa: E402
from workbench_state_files import FORMAT_KEY, StateFormatError, decode, encode  # noqa: E402


class FormatCodec(unittest.TestCase):
    def test_every_format_has_a_migration_path_to_its_version(self):
        for fmt in state_files.FORMATS:
            with self.subTest(fmt=fmt.name):
                self.assertEqual(sorted(fmt.migrations), list(range(fmt.version)))

    def test_object_files_round_trip_and_hide_the_version(self):
        payload = {"workspace": "C:/BG", "language": "de"}
        written = encode(state_files.SETTINGS, payload)
        self.assertEqual(written[FORMAT_KEY], state_files.SETTINGS.version)
        self.assertEqual(decode(state_files.SETTINGS, written), payload)
        self.assertNotIn(FORMAT_KEY, payload)  # the caller's dict is not changed

    def test_record_files_use_an_envelope(self):
        records = {"C:/BG A": {"files": []}, "C:/BG B": {"files": []}}
        written = encode(state_files.MATERIAL_SELECTIONS, records)
        self.assertEqual(set(written), {FORMAT_KEY, "records"})
        self.assertEqual(decode(state_files.MATERIAL_SELECTIONS, written), records)

    def test_files_without_a_version_are_version_zero(self):
        self.assertEqual(decode(state_files.SETTINGS, {"language": "en"}), {"language": "en"})
        old_records = {"claude-haiku-5-5": {"status": "ok"}}
        self.assertEqual(decode(state_files.MODEL_TESTS, old_records), old_records)

    def test_newer_invalid_or_wrong_type_is_rejected_as_unreadable(self):
        for fmt, raw in [
            (state_files.SETTINGS, {FORMAT_KEY: state_files.SETTINGS.version + 1}),
            (state_files.SETTINGS, {FORMAT_KEY: "1"}),
            (state_files.SETTINGS, {FORMAT_KEY: True}),
            (state_files.SETTINGS, {FORMAT_KEY: -1}),
            (state_files.SETTINGS, ["not", "an", "object"]),
            (state_files.MODEL_TESTS, {FORMAT_KEY: 99, "records": {}}),
            (state_files.MODEL_TESTS, {FORMAT_KEY: 1, "records": []}),
            (state_files.MODEL_TESTS, []),
        ]:
            with self.subTest(fmt=fmt.name, raw=raw):
                with self.assertRaises(StateFormatError):
                    decode(fmt, raw)
                self.assertTrue(issubclass(StateFormatError, ValueError))

    def test_migrations_run_in_order(self):
        steps = []
        fmt = state_files.StateFormat("demo", 2, migrations={
            0: lambda p: steps.append(0) or {**p, "a": 1},
            1: lambda p: steps.append(1) or {**p, "b": p["a"] + 1}})
        self.assertEqual(decode(fmt, {"x": 0}), {"x": 0, "a": 1, "b": 2})
        self.assertEqual(steps, [0, 1])
        self.assertEqual(decode(fmt, {FORMAT_KEY: 1, "a": 5}), {"a": 5, "b": 6})


class StateFilesOnDisk(unittest.TestCase):
    """The program's own loaders and savers, against a temporary state folder."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.home = Path(folder.name) / "AI_Bot_State"
        self.home.mkdir()
        patcher = patch.object(w, "app_state_home", return_value=self.home)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, path, raw):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(raw), encoding="utf-8")

    def read(self, path):
        return json.loads(path.read_text(encoding="utf-8"))

    def test_old_settings_are_read_and_saved_with_a_version(self):
        self.write(w.workbench_settings_path(), {"workspace": "C:/BG", "session": "s1",
                                                 "model": "claude-haiku-5-5", "language": "en"})
        self.assertEqual(w.load_workbench_settings()["language"], "en")
        self.assertEqual(w.load_workbench_settings()["workspace"], "C:/BG")
        w.save_workbench_settings(Path("C:/BG"), "s1", "claude-haiku-5-5", "de")
        saved = self.read(w.workbench_settings_path())
        self.assertEqual(saved[FORMAT_KEY], state_files.SETTINGS.version)
        self.assertEqual(w.load_workbench_settings()["language"], "de")

    def test_settings_from_a_newer_program_fall_back_to_defaults_and_stay_untouched(self):
        newer = {FORMAT_KEY: state_files.SETTINGS.version + 1, "language": "en", "workspace": "C:/BG"}
        self.write(w.workbench_settings_path(), newer)
        self.assertEqual(w.load_workbench_settings()["workspace"], "")
        self.assertEqual(self.read(w.workbench_settings_path()), newer)

    def test_old_rule_profile_job_and_coverage_are_read(self):
        profile = {"status": "locked", "version": "abc", "rules": []}
        self.write(w.codebook_profile_path(), profile)
        self.assertEqual(w.load_codebook_profile(), profile)
        w.save_codebook_profile(dict(profile))
        saved = self.read(w.codebook_profile_path())
        self.assertEqual(saved[FORMAT_KEY], state_files.CODEBOOK_PROFILE.version)
        self.assertNotIn(FORMAT_KEY, w.load_codebook_profile())

        job = {"state": "succeeded", "stage": "saving", "task_id": "t1"}
        self.write(w.codebook_job_path(), job)
        self.assertEqual(w.load_codebook_job(), job)

        session = SimpleNamespace(root=self.home / "session")
        coverage = {"complete": True, "files": [{"id": "d1"}]}
        self.write(w.coverage_path(session), coverage)
        self.assertEqual(w.load_coverage(session), coverage)

    def test_record_files_migrate_from_bare_dicts(self):
        self.write(w.model_tests_path(), {"claude-haiku-5-5": {"requested_model": "claude-haiku-5-5", "status": "ok"}})
        self.assertEqual(list(w.load_model_tests()), ["claude-haiku-5-5"])
        w.save_model_test({"requested_model": "gemini-2.5-pro", "status": "ok"})
        saved = self.read(w.model_tests_path())
        self.assertEqual(set(saved), {FORMAT_KEY, "records"})
        self.assertEqual(sorted(w.load_model_tests()), ["claude-haiku-5-5", "gemini-2.5-pro"])

        folder = self.home.parent / "BG A"
        folder.mkdir()
        (folder / "facts.txt").write_text("x", encoding="utf-8")
        stat = (folder / "facts.txt").stat()
        self.write(w.material_selections_path(), {str(folder): {"updated_at": "2026-10-01T10:00:00+02:00", "files": [
            {"path": "facts.txt", "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns}]}})
        self.assertEqual(w.load_material_selection(folder), ({"facts.txt"}, 0, 0))
        w.save_material_selection(folder, [folder / "facts.txt"])
        self.assertEqual(set(self.read(w.material_selections_path())), {FORMAT_KEY, "records"})
        self.assertEqual(w.load_material_selection(folder), ({"facts.txt"}, 0, 0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
