"""The Session type matches the session dict the program really builds."""

from pathlib import Path
import sys

APP = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(APP), str(APP / "tests")]

import unittest  # noqa: E402

import chat_workbench as w  # noqa: E402
import workbench_session  # noqa: E402
from api_cases import EnglishApiCase  # noqa: E402


class SessionType(EnglishApiCase):
    def test_setup_builds_exactly_the_typed_keys(self):
        self.assertEqual(set(w.ACTIVE), workbench_session.SETUP_KEYS)

    def test_model_call_copy_adds_exactly_its_controls(self):
        data = w.begin_model_work("req-1")
        try:
            self.assertEqual(set(data) - set(w.ACTIVE), workbench_session.MODEL_WORK_KEYS - {"answer_events"})
            self.assertIsNot(data, w.ACTIVE)
        finally:
            w.end_model_work(data)

    def test_every_typed_key_is_documented_in_one_group(self):
        typed = workbench_session.Session.__optional_keys__ | workbench_session.Session.__required_keys__
        self.assertEqual(workbench_session.SETUP_KEYS | workbench_session.MODEL_WORK_KEYS, typed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
