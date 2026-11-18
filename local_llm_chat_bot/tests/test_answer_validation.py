"""Model answers: JSON action rounds, reference schema, classification validation."""

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
import workbench_classification  # noqa: E402
from fixture_support import FixtureEnvironment  # noqa: E402
from fixture_support import PROFILE  # noqa: E402
from code_chat_agent import parse_json  # noqa: E402
from api_cases import DirectSessionCase, EnglishApiCase  # noqa: E402


class ResponseRounds(unittest.TestCase):
    def setUp(self):
        self.f = FixtureEnvironment().__enter__()
        self.addCleanup(self.f.__exit__, None, None, None)
        self.client = TestClient(w.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)
        self.post(
            "/api/setup",
            {"workspace": str(self.f.workspace), "model": "gemini-2.5-pro"},
        )
        self.post("/api/codebook/prepare", {"path": str(self.f.rules)})
        self.post("/api/codebook/lock", {})
        self.post(
            "/api/target", {"target": str(self.f.bg_a), "selected_paths": ["facts.txt"]}
        )
        self.post("/api/chat", {"question": "Initial classification"})
        data = w.ACTIVE
        context = data["state"].data["bg_context"]
        source = next(
            item
            for item in data["documents"].list()
            if item["id"] in context["source_ids"]
        )
        rules = next(
            item
            for item in data["documents"].list()
            if item["id"] == context["codebook_id"]
        )
        self.good = {
            "answer": "Valid explanation",
            "read_files": [],
            "changes": [],
            "classification": {
                "label": "Rotationseinheit",
                "confidence": "high",
                "alternative_label": "",
                "codebook_rule_ids": ["rotation-1"],
                "codebook_rule_pages": [],
                "codebook_rule_refs": [rules["chunks"][0]["label"]],
                "evidence_labels": [source["chunks"][0]["label"]],
                "bg_evidence_pages": [source["chunks"][0]["label"]],
                "uncertainties": [],
            },
        }

    def post(self, path, body):
        result = self.client.post(path, json=body)
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def invalid(self):
        action = copy.deepcopy(self.good)
        action["classification"]["label"] = "Unknown fixture label"
        action["changes"] = [{"path": "must-not-write.txt", "content": "unvalidated"}]
        return action

    def failed(
        self, actions, *, required=False, question="Explain the motor", calls=None
    ):
        old_analysis = copy.deepcopy(w.ACTIVE["state"].data.get("last_bg_analysis"))
        history = copy.deepcopy(w.ACTIVE["state"].data["history"])
        with patch.object(
            w.ACTIVE["llm"],
            "ask_about_files",
            side_effect=[
                item if isinstance(item, str) else json.dumps(item) for item in actions
            ],
        ) as model:
            response = self.client.post(
                "/api/chat",
                json={"question": question, "require_classification": required},
            )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(model.call_count, calls or len(actions))
        self.assertEqual(w.ACTIVE["state"].data.get("last_bg_analysis"), old_analysis)
        self.assertEqual(w.ACTIVE["state"].data["history"], history)
        self.assertFalse((self.f.workspace / "must-not-write.txt").exists())
        self.assertNotIn("通过校验", response.text)
        self.assertFalse(w.MODEL_WORK_IN_PROGRESS.is_set())

    def test_keyword_free_followups_revalidate_repair_in_all_languages(self):
        for language, question in [
            ("zh", "请进一步说明电机的作用"),
            ("en", "Explain the motor evidence"),
            ("de", "Erläutere bitte die Motorfunktion"),
        ]:
            with self.subTest(language=language):
                self.post("/api/language", {"language": language})
                self.failed([self.invalid(), self.invalid()], question=question)

    def test_repair_cannot_drop_classification_in_explanation_mode(self):
        missing = copy.deepcopy(self.good)
        missing["classification"] = None
        self.failed([self.invalid(), missing])

    def test_explicit_classification_requires_object_without_keyword_detection(self):
        missing = copy.deepcopy(self.good)
        missing["classification"] = None
        self.failed([missing, missing], required=True, question="请给出你的最终判断")

    def test_explanation_can_have_no_classification_and_uses_explicit_prompt(self):
        action = copy.deepcopy(self.good)
        action["classification"] = None
        with patch.object(
            w.ACTIVE["llm"], "ask_about_files", return_value=json.dumps(action)
        ) as model:
            result = self.post(
                "/api/chat", {"question": "Explain", "require_classification": False}
            )
        self.assertIsNone(result["classification"])
        self.assertIn("EXPLANATION MODE", model.call_args.args[1])
        self.assertEqual(model.call_count, 1)

    def test_valid_repair_is_accepted_once_and_followup_card_is_not_hidden(self):
        with patch.object(
            w.ACTIVE["llm"],
            "ask_about_files",
            side_effect=[json.dumps(self.invalid()), json.dumps(self.good)],
        ) as model:
            result = self.post(
                "/api/chat", {"question": "Explain", "require_classification": False}
            )
        self.assertEqual(model.call_count, 2)
        self.assertEqual(result["classification"]["label"], "Rotationseinheit")

    def test_supplementary_round_cannot_fallback_to_invalid_raw_answer(self):
        (self.f.workspace / "notes.txt").write_text("Read-only supplemental fixture")
        first = copy.deepcopy(self.good)
        first["classification"] = None
        first["read_files"] = ["notes.txt"]
        self.failed([first, self.invalid(), self.invalid()])

    def test_one_repair_budget_is_shared_with_supplementary_round(self):
        (self.f.workspace / "notes.txt").write_text("Read-only supplemental fixture")
        repaired = copy.deepcopy(self.good)
        repaired["read_files"] = ["notes.txt"]
        self.failed([self.invalid(), repaired, self.invalid()])

    def test_supplementary_round_cannot_omit_previously_required_classification(self):
        (self.f.workspace / "notes.txt").write_text("Supplement")
        first = copy.deepcopy(self.good)
        first["read_files"] = ["notes.txt"]
        missing = copy.deepcopy(self.good)
        missing["classification"] = None
        self.failed([first, missing, missing])

    def test_truncated_and_malformed_actions_cannot_commit(self):
        self.failed(['{"answer":', '{"answer":'], required=True)
        broken = copy.deepcopy(self.good)
        broken["classification"]["confidence"] = []
        self.failed([broken, broken])

    def test_comparison_validation_failure_isolated_from_next_model(self):
        history = copy.deepcopy(w.ACTIVE["state"].data["history"])
        with patch.object(
            w.LLMConnector,
            "ask_about_files",
            side_effect=[
                json.dumps(self.invalid()),
                json.dumps(self.invalid()),
                json.dumps(self.good),
            ],
        ) as model:
            result = self.post(
                "/api/compare",
                {
                    "question": "Assess",
                    "models": ["gemini-2.5-pro", "gemini-2.5-flash"],
                },
            )
        self.assertEqual(model.call_count, 3)
        self.assertFalse(result["results"][0]["ok"])
        self.assertEqual(result["results"][0]["answer"], "")
        self.assertIsNone(result["results"][0].get("classification"))
        self.assertTrue(result["results"][1]["ok"])
        self.assertEqual(
            result["results"][1]["classification"]["label"], "Rotationseinheit"
        )
        self.assertEqual(w.ACTIVE["state"].data["history"], history)

    def test_normal_mode_cannot_accept_an_unlocked_classification(self):
        self.assertEqual(self.client.delete("/api/bg").status_code, 200)
        with patch.object(
            w.ACTIVE["llm"], "ask_about_files", return_value=json.dumps(self.good)
        ) as model:
            response = self.client.post("/api/chat", json={"question": "Explain"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(model.call_count, 1)

    def test_real_pdf_rule_pages_use_the_actual_page_inventory(self):
        import fitz

        path = self.f.root / "Physical rules.pdf"
        with fitz.open() as pdf:
            page = pdf.new_page()
            page.insert_text(
                (72, 72),
                "Rotationseinheit: The primary function is rotation of the handled object. Rule rotation-1.",
            )
            pdf.save(path)
        self.post("/api/codebook/prepare", {"path": str(path)})
        self.post("/api/codebook/lock", {})
        self.post(
            "/api/target", {"target": str(self.f.bg_a), "selected_paths": ["facts.txt"]}
        )
        result = self.post("/api/chat", {"question": "Assess the fixture"})
        self.assertEqual(result["classification"]["codebook_rule_pages"], [1])
        scope = w.classification_scope(
            w.ACTIVE["documents"], w.ACTIVE["state"].data["bg_context"]
        )
        self.assertEqual(scope["_codebook_pages"], [1])


class ReferenceSchema(unittest.TestCase):
    def setUp(self):
        self.profile = {
            "classes": [
                {
                    "name": "A",
                    "definition": "A fixture",
                    "decision_rules": [{"id": "a", "text": "Rule A", "pages": [1]}],
                    "boundaries": [],
                },
                {
                    "name": "B",
                    "definition": "B fixture",
                    "decision_rules": [],
                    "boundaries": [
                        {
                            "id": "boundary-b",
                            "text": "Cross-class boundary",
                            "pages": [2],
                        }
                    ],
                },
            ],
            "global_rules": [],
            "table_rules": [],
        }
        self.scope = {
            "codebook_id": "rules",
            "codebook_path": "/fixture/rules.pdf",
            "source_ids": ["bg", "sheet", "text"],
            "_codebook_pages": [1, 2],
        }
        self.evidence = [
            {
                "id": "rules",
                "label": "rules.pdf page 1",
                "visual": {"kind": "pdf_page", "path": "/fixture/rules.pdf", "page": 1},
            },
            {
                "id": "bg",
                "label": "BG.pdf page 2",
                "visual": {"kind": "pdf_page", "path": "/fixture/BG.pdf", "page": 2},
            },
            {
                "id": "sheet",
                "label": "parts.xlsx Sheet1 rows 2–5",
                "visual": {"kind": "excel_range", "path": "/fixture/parts.xlsx"},
            },
            {
                "id": "text",
                "label": "facts.txt block 1",
                "text": "actual supplied text",
            },
        ]
        self.action = {
            "classification": {
                "label": "A",
                "confidence": "high",
                "alternative_label": "",
                "codebook_rule_ids": ["a"],
                "codebook_rule_pages": [1],
                "evidence_labels": ["BG.pdf page 2"],
                "bg_evidence_pages": ["BG.pdf page 2"],
                "uncertainties": [],
            }
        }

    def check(self, action=None):
        return workbench_classification.validate_classification(
            action or self.action, self.evidence, "", self.profile, self.scope
        )

    def test_actual_pages_and_cross_class_boundaries_are_valid(self):
        self.assertIsNone(self.check())
        self.action["classification"]["codebook_rule_ids"].append("boundary-b")
        self.action["classification"]["codebook_rule_pages"].append(2)
        self.assertIsNone(self.check())

    def test_invalid_types_return_readable_reasons_not_runtime_errors(self):
        mutations = [
            ("label", []),
            ("label", ["A", "B"]),
            ("label", ""),
            ("label", " A"),
            ("confidence", []),
            ("confidence", {}),
            ("confidence", None),
            ("codebook_rule_ids", [1]),
            ("codebook_rule_ids", [{}]),
            ("codebook_rule_ids", ["unknown"]),
            ("codebook_rule_pages", ["1"]),
            ("codebook_rule_pages", [True]),
            ("codebook_rule_pages", [0]),
            ("codebook_rule_pages", [-1]),
            ("codebook_rule_pages", [999999]),
            ("codebook_rule_pages", []),
            ("bg_evidence_pages", [2]),
            ("bg_evidence_pages", ["BG.pdf page 999"]),
            ("alternative_label", []),
            ("uncertainties", [3]),
            ("codebook_rule_refs", [1]),
        ]
        for field, value in mutations:
            with self.subTest(field=field, value=value):
                action = copy.deepcopy(self.action)
                action["classification"][field] = value
                self.assertIsInstance(self.check(action), str)
        del self.action["classification"]["codebook_rule_pages"]
        self.assertIsInstance(self.check(), str)

    def test_page_must_belong_to_cited_rule_and_actual_document(self):
        self.action["classification"]["codebook_rule_pages"] = [2]
        self.assertIsNotNone(self.check())
        self.profile["classes"][0]["decision_rules"][0]["pages"] = [999]
        self.action["classification"]["codebook_rule_pages"] = [999]
        self.assertIsNotNone(self.check())

    def test_codebook_only_or_uncited_bg_references_fail(self):
        self.action["classification"]["evidence_labels"] = ["rules.pdf page 1"]
        self.action["classification"]["bg_evidence_pages"] = ["rules.pdf page 1"]
        self.assertIsNotNone(self.check())
        self.action["classification"]["bg_evidence_pages"] = ["BG.pdf page 2"]
        self.assertIsNotNone(self.check())

    def test_real_sheet_ranges_and_nonpaged_bg_chunks_are_valid(self):
        for label in ["parts.xlsx Sheet1 rows 2–5", "facts.txt block 1"]:
            self.action["classification"]["evidence_labels"] = [label]
            self.action["classification"]["bg_evidence_pages"] = [label]
            self.assertIsNone(self.check())

    def test_nonpaged_rules_need_real_source_refs_instead_of_physical_pages(self):
        self.scope["codebook_path"] = "/fixture/rules.docx"
        self.evidence[0] = {"id": "rules", "label": "rules.docx section 1"}
        cls = self.action["classification"]
        cls["codebook_rule_pages"] = []
        cls["codebook_rule_refs"] = ["rules.docx section 1"]
        self.assertIsNone(self.check())
        cls["codebook_rule_pages"] = [1]
        self.assertIsNotNone(self.check())
        cls["codebook_rule_pages"] = []
        for refs in [[], ["rules.docx section 999"], ["facts.txt block 1"]]:
            cls["codebook_rule_refs"] = refs
            self.assertIsNotNone(self.check())


class ClassificationRevalidation(EnglishApiCase):
    def test_followup_repair_must_revalidate_classification(self):
        self.bg()
        result = self.client.post(
            "/api/chat", json={"question": "TEST_UNKNOWN explain the motor evidence"}
        )
        self.assertNotEqual(
            result.status_code,
            200,
            f"accepted unknown class: {result.json().get('classification')}",
        )

    def test_evidence_pages_must_reference_supplied_pages(self):
        action = {
            "classification": {
                "label": "Rotationseinheit",
                "confidence": "high",
                "evidence_labels": ["facts.txt block 1"],
                "codebook_rule_ids": ["rotation-1"],
                "codebook_rule_pages": [999999],
                "bg_evidence_pages": ["never-supplied.pdf p999"],
                "alternative_label": "",
                "uncertainties": [],
            }
        }
        self.assertIsNotNone(
            workbench_classification.validate_classification(
                action, [{"label": "facts.txt block 1"}], "", PROFILE
            ),
            "fabricated Codebook and BG page references accepted",
        )


class ActionValidation(DirectSessionCase):
    def test_classification_requires_exact_member_not_substring(self):
        profile = {'classes': [{'name': 'Rotationseinheit', 'definition': 'rotary motion'}]}
        action = {'classification': {'label': 'Rotation', 'confidence': 'high', 'evidence_labels': ['file A'],
                                     'bg_evidence_pages': ['file A'], 'uncertainties': []}}
        self.assertIsNotNone(workbench_classification.validate_classification(action, [{'label': 'file A'}], 'Rotationseinheit', profile))

    def test_bad_json_action_field_types_are_rejected(self):
        for field, value in [('read_files', None), ('changes', {}), ('answer', ['wrong'])]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                parse_json(json.dumps({field: value}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
