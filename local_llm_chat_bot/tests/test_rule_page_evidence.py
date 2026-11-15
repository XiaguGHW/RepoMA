"""Which rule pages are sent as evidence for a question."""

from __future__ import annotations

from pathlib import Path
import sys

APP = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(APP), str(APP / "tests")]

import tempfile  # noqa: E402
import unittest  # noqa: E402
import chat_workbench as workbench  # noqa: E402


class RulePageSelection(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.pdf = Path(self.directory.name) / "rules.pdf"
        self.pdf.write_bytes(b"%PDF-1.4\n% local test placeholder\n")
        names = [
            "Linear Einheit", "Gantry", "Roboter", "Greifer/Endeffektor",
            "Handhabungsbaugruppe", "Rotationseinheit", "Kombinierte Einheit",
        ]
        classes = []
        for page, name in enumerate(names, start=1):
            classes.append({"name": name, "definition": f"Definition for {name}",
                            "evidence_pages": [page],
                            "decision_rules": [{"id": f"rule-{page}", "text": f"Core rule for {name}", "pages": [page]}],
                            "boundaries": []})
        self.context = {"codebook_path": str(self.pdf), "locked_profile": {"classes": classes,
                        "global_rules": [], "table_rules": []}}

    def tearDown(self):
        self.directory.cleanup()

    def test_chinese_alias_selects_the_greifer_page(self):
        pages = workbench.relevant_codebook_page_evidence("这个夹爪装配体应如何分类？", self.context)
        self.assertEqual(pages[0]["visual"]["page"], 4)
        self.assertIn("Greifer/Endeffektor", pages[0]["label"])

    def test_german_class_name_selects_rotation_page(self):
        pages = workbench.relevant_codebook_page_evidence("Ist dies eine Rotationseinheit?", self.context)
        self.assertEqual(pages[0]["visual"]["page"], 6)
        self.assertIn("Rotationseinheit", pages[0]["label"])

    def test_unknown_question_uses_stable_definition_page_fallback(self):
        pages = workbench.relevant_codebook_page_evidence("Bitte prüfe die allgemeine technische Beschreibung.", self.context)
        self.assertEqual(pages[0]["visual"]["page"], 1)
        self.assertIn("class Linear Einheit", pages[0]["label"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
