"""The page asks with its own dialogs; browser confirm/alert/prompt boxes do not fit its design."""

from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import chat_workbench as w  # noqa: E402


class NoNativeDialogs(unittest.TestCase):
    def test_page_script_never_calls_browser_dialogs(self):
        script = re.search(r"<script>(.*?)</script>", w.HTML, re.S).group(1)
        code = re.sub(r"(?m)^\s*//.*$", "", script)  # comments may name them
        calls = re.findall(r"(?<![A-Za-z0-9_.$])(confirm|alert|prompt)\s*\(", code)
        self.assertEqual(calls, [])
        for helper in ("function appConfirm(", "function appNotice(", "function appPrompt("):
            self.assertIn(helper, script)


if __name__ == "__main__":
    unittest.main(verbosity=2)
