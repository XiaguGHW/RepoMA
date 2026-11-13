"""The page in static/ is assembled into one self-contained document."""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
import workbench_frontend as frontend  # noqa: E402
sys.path.insert(0, str(APP / "tests"))
import test_package_manifest as manifest  # noqa: E402


class FrontendAssembly(unittest.TestCase):
    def test_page_is_one_document_with_inline_styles_and_script(self):
        page = frontend.load_frontend_html()
        self.assertTrue(page.startswith("<!doctype html>"))
        self.assertTrue(page.endswith("</script></body></html>"))
        for marker in frontend.INCLUDES:
            self.assertNotIn(marker, page)
        self.assertEqual(page.count("<style>"), 1)
        self.assertEqual(page.count("<script>"), 1)
        self.assertIn(frontend.read_static("workbench.css"), page)
        self.assertIn(frontend.read_static("workbench.js"), page)
        # No external resources: everything the page needs is inline.
        self.assertNotIn("<script src", page)
        self.assertNotIn('<link rel="stylesheet"', page)
        self.assertEqual(page.count("__WORKBENCH_I18N_JSON__"), 1)

    def test_crlf_checkout_gives_the_same_page(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in (frontend.SHELL_FILE, *frontend.INCLUDES.values()):
                text = frontend.read_static(name)
                (Path(folder) / name).write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
            expected = frontend.load_frontend_html()
            with patch.object(frontend, "STATIC_DIR", Path(folder)):
                self.assertEqual(frontend.load_frontend_html(), expected)

    def test_missing_or_duplicated_include_marker_fails_loudly(self):
        shell = frontend.read_static(frontend.SHELL_FILE)
        marker = next(iter(frontend.INCLUDES))
        for broken in (shell.replace(marker, ""), shell.replace(marker, marker * 2)):
            with self.subTest(count=broken.count(marker)):
                with patch.object(frontend, "read_static",
                                  side_effect=lambda name: broken if name == frontend.SHELL_FILE
                                  else "x"):
                    with self.assertRaises(RuntimeError):
                        frontend.load_frontend_html()

    def test_every_static_file_is_shipped(self):
        shipped = set(manifest.package_files())
        for name in (frontend.SHELL_FILE, *frontend.INCLUDES.values()):
            self.assertIn(f"static/{name}", shipped)
        self.assertEqual({p for p in shipped if p.startswith("static/")},
                         {f"static/{p.name}" for p in (APP / "static").iterdir() if p.is_file()})


if __name__ == "__main__":
    unittest.main(verbosity=2)
