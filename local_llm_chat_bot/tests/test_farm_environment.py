"""FarmEnvironment.peek(): the settings use() would see, without touching os.environ."""

from pathlib import Path
import sys

APP = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(APP), str(APP / "tests")]

import os  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from unittest.mock import patch  # noqa: E402

from dotenv import dotenv_values, load_dotenv  # noqa: E402

from llm_connector_with_prompt_caching import LLMConnector, farm_base_url  # noqa: E402
from workbench_startup import FarmEnvironment, StartupError  # noqa: E402

KEY, URL, OTHER = "BOSCH_FARM_SUBSCRIPTION_KEY", "BOSCH_FARM_BASE_URL", "FARM_TEST_EXTRA"
NAMES = (KEY, "BOSCH_FARM_API_KEY", URL, OTHER)


class Peek(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name)
        self.env = self.dir / ".env"
        clean = {name: value for name, value in os.environ.items() if name not in NAMES}
        patcher = patch.dict(os.environ, clean, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.farm = FarmEnvironment()

    def write(self, **values):
        self.env.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")

    def seen_by_use(self, explicit=False):
        """What the old, environment-rewriting use(commit=False) exposes."""
        with self.farm.use(self.env, load_dotenv, explicit=explicit, commit=False) as key:
            return key, {name: os.environ[name] for name in NAMES if name in os.environ}

    def seen_by_peek(self, explicit=False):
        before = dict(os.environ)
        settings = self.farm.peek(self.env, dotenv_values, explicit=explicit)
        self.assertEqual(dict(os.environ), before, "peek() changed the process environment")
        return settings.key, {name: settings.values[name] for name in NAMES if name in settings.values}

    def assert_same_as_use(self, explicit=False):
        self.assertEqual(self.seen_by_peek(explicit), self.seen_by_use(explicit))

    def test_reads_the_env_file(self):
        self.write(**{KEY: "file-key", URL: "https://farm.example/api", OTHER: "x"})
        key, values = self.seen_by_peek()
        self.assertEqual(key, "file-key")
        self.assertEqual(farm_base_url(values), "https://farm.example/api")
        self.assert_same_as_use()

    def test_process_variables_win_over_the_file(self):
        self.write(**{KEY: "file-key", URL: "https://file.example/api"})
        os.environ[KEY] = "process-key"
        self.assert_same_as_use()
        self.assertEqual(self.seen_by_peek()[0], "process-key")

    def test_an_edited_env_replaces_what_an_earlier_setup_loaded(self):
        self.write(**{KEY: "old-key", URL: "https://old.example/api", OTHER: "gone"})
        with self.farm.use(self.env, load_dotenv):  # setup adopts the .env
            pass
        self.assertEqual(os.environ[URL], "https://old.example/api")
        self.write(**{KEY: "new-key", URL: "https://new.example/api"})
        key, values = self.seen_by_peek()
        self.assertEqual((key, values.get(URL), values.get(OTHER)), ("new-key", "https://new.example/api", None))
        self.assert_same_as_use()
        self.assertEqual(os.environ[URL], "https://old.example/api")  # the running session keeps its setup

    def test_api_key_name_is_accepted(self):
        self.write(**{"BOSCH_FARM_API_KEY": "api-key"})
        self.assert_same_as_use()

    def test_errors_match_use(self):
        cases = [
            ("missing explicit .env", lambda: None, True, "startup.env_missing"),
            ("no key", lambda: self.write(**{URL: "https://farm.example/api"}), False, "startup.key_missing"),
            ("blank key", lambda: self.write(**{KEY: "  "}), False, "startup.key_missing"),
            ("folder instead of file", lambda: self.env.mkdir(), False, "startup.env_unreadable"),
        ]
        for name, prepare, explicit, message_key in cases:
            with self.subTest(name):
                if self.env.is_dir():
                    self.env.rmdir()
                elif self.env.exists():
                    self.env.unlink()
                prepare()
                before = dict(os.environ)
                for read in (self.seen_by_peek, self.seen_by_use):
                    with self.assertRaises(StartupError) as caught:
                        read(explicit)
                    self.assertEqual(caught.exception.code, message_key)
                self.assertEqual(dict(os.environ), before)

    def test_connector_uses_a_fixed_endpoint_when_given(self):
        os.environ[URL] = "https://process.example/api"
        fixed = LLMConnector("gemini-2.5-pro", "k", base_url="https://fixed.example/api")
        self.assertEqual(fixed._farm_base(), "https://fixed.example/api")
        self.assertEqual(LLMConnector("gemini-2.5-pro", "k")._farm_base(), "https://process.example/api")


if __name__ == "__main__":
    unittest.main(verbosity=2)
