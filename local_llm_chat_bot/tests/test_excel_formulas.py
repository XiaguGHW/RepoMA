"""Regression fixtures for special Excel formula objects, entirely offline."""
import contextlib
import hashlib
import io
import json
import sys
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from openpyxl import Workbook
from openpyxl.worksheet.formula import ArrayFormula, DataTableFormula

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import excel_agent as exact
import excel_chat_agent as chat


class FormulaTests(unittest.TestCase):
    def setUp(self):
        self.book = Workbook()
        self.sheet = self.book.active
        self.sheet.title = "Klassifikation_Übersicht_Gesamt"
        self.formula = "=SUM('Daten Quelle'!$B$2:$B$5*$A30)"
        self.sheet["M30"] = ArrayFormula(ref="M30:M32", text=self.formula)
        self.sheet["X30"] = "=M30+SUM('Daten Quelle'!C2:C5)"
        self.sheet["Y30"] = ArrayFormula(ref="Y30:Y32", text="=TRANSPOSE(A1:C1)")
        self.sheet["G2"] = DataTableFormula(ref="G2:H4", r1="C1", r2="D1", dt2D=True)
        self.sheet["A1"] = datetime(2026, 9, 18, 20, 30)
        self.sheet["A2"] = date(2026, 9, 18)
        self.sheet["A3"] = time(20, 30)
        self.sheet["A4"] = timedelta(hours=2)
        self.sheet["C1"] = "完整内容" * 200
        self.book.create_sheet("Daten Quelle")
        self.tools = chat.WorkbookTools(SimpleNamespace(data={}))
        self.tools.book = lambda: self.book

    def test_trace_array_preserves_text_range_and_cross_sheet_references(self):
        with self.assertRaisesRegex(TypeError, "ArrayFormula.*JSON serializable"):
            json.dumps({"value": self.sheet["M30"].value})
        record = self.tools.trace(f"{self.sheet.title}!M30")
        json.dumps(record, ensure_ascii=False)
        self.assertEqual(record["formula"], self.formula)
        self.assertEqual(record["formula_range"], "M30:M32")
        self.assertEqual(record["formula_anchor"], f"{self.sheet.title}!M30")
        self.assertTrue(record["is_formula_anchor"])
        self.assertEqual(record["references"], ["Daten Quelle!B2:B5", f"{self.sheet.title}!A30"])
        prompt = chat.controller_prompt("解释 M30", {}, [{"tool": "trace", "result": record}])
        self.assertIn(self.formula, prompt)
        self.assertNotIn("object at 0x", prompt)

    def test_array_member_points_to_owner_instead_of_being_reported_as_empty(self):
        record = self.tools.trace(f"{self.sheet.title}!M31")
        self.assertEqual(record["formula"], self.formula)
        self.assertFalse(record["is_formula_anchor"])
        self.assertEqual(record["formula_anchor"], f"{self.sheet.title}!M30")
        self.assertEqual(record["formula_range"], "M30:M32")

    def test_read_preview_search_and_prompt_are_json_serializable(self):
        region = self.tools.read_range(self.sheet.title, "M30:Y30")
        self.assertEqual(region["cells"][0]["formula_type"], "array")
        self.assertEqual(region["cells"][-2]["formula_type"], "normal")
        self.assertEqual(region["cells"][-1]["formula_type"], "array")
        results = [region, self.tools.sheet_preview(self.sheet.title, 35, 25),
                   self.tools.search("TRANSPOSE", self.sheet.title),
                   self.tools.read_range(self.sheet.title, "A1:A4")]
        payload = json.dumps(results, ensure_ascii=False)
        self.assertNotIn("object at 0x", payload)
        self.assertIn("2026-09-18T20:30:00", payload)
        self.assertEqual(self.tools.read_range(self.sheet.title, "C1")["cells"][0]["value"], "完整内容" * 200)
        chat.final_prompt("解释 M30 X30 Y30", {}, [{"tool": "read_range", "result": region}])

    def test_data_table_metadata_is_preserved_without_a_fabricated_formula(self):
        record = self.tools.trace(f"{self.sheet.title}!H3")
        self.assertEqual(record["formula_type"], "data_table")
        self.assertEqual(record["formula_definition"]["r1"], "C1")
        self.assertEqual(record["formula_definition"]["r2"], "D1")
        self.assertIsNone(record["formula"])
        self.assertTrue(record["warnings"])
        json.dumps(record)

    def test_formula_fingerprint_detects_special_formula_text_and_range_changes(self):
        before = exact.formula_fingerprint(self.book)
        self.sheet["M30"].value.text = "=SUM(A1:A3)"
        changed_text = exact.formula_fingerprint(self.book)
        self.assertNotEqual(before, changed_text)
        self.sheet["M30"].value.ref = "M30:M33"
        self.assertNotEqual(changed_text, exact.formula_fingerprint(self.book))
        before_table = exact.formula_fingerprint(self.book)
        self.sheet["G2"].value.r1 = "C2"
        self.assertNotEqual(before_table, exact.formula_fingerprint(self.book))

    def test_ordinary_formula_fingerprint_remains_compatible(self):
        self.book.remove(self.sheet)
        sheet = self.book.active
        sheet["B1"] = "=A1+1"
        fingerprint = exact.formula_fingerprint(self.book)
        expected = hashlib.sha256(f"{sheet.title}!B1\0=A1+1\n".encode()).hexdigest()
        self.assertEqual(fingerprint, {"formula_cells": 1, "formula_sha256": expected})

    def test_empty_looking_array_or_table_members_cannot_be_written(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                exact.assert_target_safe(self.sheet, 13, 31, 32, 32)
            with self.assertRaises(SystemExit):
                exact.assert_target_safe(self.sheet, 8, 3, 4, 4)
        exact.assert_target_safe(self.sheet, 16, 30, 31, 32)

    def test_search_and_fingerprint_do_not_expand_formatted_million_row_sheet(self):
        self.sheet["W1048576"].number_format = "0.00"
        count = len(self.sheet._cells)
        self.tools.search("TRANSPOSE", self.sheet.title)
        exact.formula_fingerprint(self.book)
        self.assertEqual(len(self.sheet._cells), count)

    def test_cli_trace_range_and_json_boundary_use_same_converter(self):
        with patch.object(exact, "load_book", return_value=self.book), contextlib.redirect_stdout(io.StringIO()) as output:
            exact.command_trace(SimpleNamespace(workbook="fixture.xlsx", cell=f"{self.sheet.title}!M30"))
        self.assertEqual(json.loads(output.getvalue())["formula"], self.formula)
        with patch.object(exact, "load_book", return_value=self.book), contextlib.redirect_stdout(io.StringIO()) as output:
            exact.command_range(SimpleNamespace(workbook="fixture.xlsx", sheet=self.sheet.title, range="M30"))
        self.assertEqual(json.loads(output.getvalue())["values"][0][0]["formula"], self.formula)
        encoded = json.dumps({"formula": self.sheet["M30"].value}, default=exact.excel_json_value)
        self.assertEqual(json.loads(encoded)["formula"]["ref"], "M30:M32")

    def test_quoted_text_named_and_external_references_are_not_guessed(self):
        refs, warnings = exact.formula_references('=IF(A1="Z99",SUM(\'Daten Quelle\'!A2:B4),NamedRange)', self.sheet.title)
        self.assertNotIn(f"{self.sheet.title}!Z99", refs)
        self.assertIn("Daten Quelle!A2:B4", refs)
        self.assertTrue(any("NamedRange" in item for item in warnings))


if __name__ == "__main__":
    unittest.main()

# From the downloaded standalone folder, without Farm API requests:
# 1) python -m pip install -r requirements.txt
# 2) python -m unittest discover -s tests -p "test_excel_formulas.py" -v
# 3) python -m unittest discover -s tests -v
