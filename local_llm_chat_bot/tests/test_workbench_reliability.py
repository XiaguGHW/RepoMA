"""Local, no-network regression tests for the workbench reliability fixes."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import chat_workbench as workbench
from local_document_library import LocalDocumentLibrary


class DocumentIndexAtomicWriteTests(unittest.TestCase):
    def test_save_replaces_valid_json_and_cleans_temporary_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "documents.json"
            library = LocalDocumentLibrary(path)
            for number in range(3):
                library.data = {"version": 1, "documents": [{"id": str(number)}]}
                library._save()
                self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["documents"][0]["id"], str(number))
                self.assertFalse(list(path.parent.glob(f".{path.name}.*.tmp")))

            previous = path.read_text(encoding="utf-8")
            library.data = {"version": 1, "documents": [{"id": "new"}]}
            with patch("local_document_library.os.replace", side_effect=OSError("simulated interruption")):
                with self.assertRaises(OSError):
                    library._save()
            # An interrupted replacement leaves the old complete file intact;
            # the sibling temporary file never becomes the final index.
            self.assertEqual(path.read_text(encoding="utf-8"), previous)
            self.assertFalse(list(path.parent.glob(f".{path.name}.*.tmp")))


class DossierModelSlotTests(unittest.TestCase):
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
        state = SimpleNamespace(note_usage=lambda *_args, **_kwargs: None)
        workbench.ACTIVE.update({"state": state, "model": "test-model", "pricing": object()})
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


class CodebookPageSelectionTests(unittest.TestCase):
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
    unittest.main()
