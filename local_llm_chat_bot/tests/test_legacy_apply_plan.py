"""Legacy code-change plans (/api/apply). Removed in refactor step 2 with the feature."""

from pathlib import Path
import sys

APP = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(APP), str(APP / "tests")]

import copy  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
from types import SimpleNamespace  # noqa: E402
import unittest  # noqa: E402
from unittest.mock import patch  # noqa: E402
import chat_workbench as w  # noqa: E402
import contextlib  # noqa: E402
import io  # noqa: E402
from openpyxl import Workbook  # noqa: E402
import excel_agent as excel  # noqa: E402
from api_cases import ApiCase, DirectSessionCase, EnglishApiCase, LegacyApplyPlanHelpers  # noqa: E402


class ApplyPlan(LegacyApplyPlanHelpers, ApiCase):
    def test_old_and_missing_ids_cannot_apply_new_plan(self):
        first = self.propose("A")
        second = self.propose("B")
        self.assertNotEqual(first, second)
        self.rejected(first)
        self.rejected("")
        self.assertFalse((self.f.workspace / "A.txt").exists())
        self.assertFalse((self.f.workspace / "B.txt").exists())
        result = self.post("/api/apply", {"confirmed": True, "plan_id": second})
        self.assertEqual(result["applied"], 1)
        self.assertEqual((self.f.workspace / "B.txt").read_text(), "B")
        self.rejected(second)

    def test_unconfirmed_and_cancelled_plan_never_writes(self):
        plan_id = self.propose("cancelled")
        response = self.client.post(
            "/api/apply", json={"confirmed": False, "plan_id": plan_id}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.delete("/api/pending").status_code, 200)
        self.rejected(plan_id)
        self.assertFalse((self.f.workspace / "cancelled.txt").exists())

    def test_plan_digest_rejects_content_or_order_change(self):
        for mutation in ["content", "order"]:
            with self.subTest(mutation=mutation):
                changes = w.build_diff(
                    w.ACTIVE["state"],
                    [
                        {"path": "one.txt", "content": "one"},
                        {"path": "two.txt", "content": "two"},
                    ],
                )
                plan_id = w.publish_pending(w.ACTIVE, changes)
                if mutation == "content":
                    w.ACTIVE["pending"][0]["content"] = "unreviewed"
                else:
                    w.ACTIVE["pending"].reverse()
                self.rejected(plan_id)
                self.assertFalse((self.f.workspace / "one.txt").exists())
                self.assertFalse((self.f.workspace / "two.txt").exists())

    def test_model_target_session_and_setup_invalidate_old_plan(self):
        transitions = [
            ("/api/model", {"model": "gemini-2.5-flash"}),
            (
                "/api/target",
                {"target": str(self.f.bg_a), "selected_paths": ["facts.txt"]},
            ),
            ("/api/session/new", {}),
            (
                "/api/setup",
                {"workspace": str(self.f.workspace), "model": "gemini-2.5-pro"},
            ),
        ]
        for index, (endpoint, body) in enumerate(transitions):
            with self.subTest(endpoint=endpoint):
                name = "context" + str(index)
                plan_id = self.propose(name)
                self.post(endpoint, body)
                self.rejected(plan_id)
                self.assertFalse((self.f.workspace / (name + ".txt")).exists())

    def test_rules_edit_and_relock_invalidate_confirmation(self):
        self.post("/api/codebook/prepare", {"path": str(self.f.rules)})
        self.post("/api/codebook/lock", {})
        plan_id = self.propose("rule_change")
        profile = w.load_codebook_profile()
        draft = copy.deepcopy(profile["draft"])
        draft["classes"][0]["definition"] += " Additional fixture definition."
        self.post("/api/codebook/edit", {"draft": draft, "confirmed": True,
                                         "profile_version": profile["version"]})
        self.post("/api/codebook/lock", {})
        self.rejected(plan_id)
        self.assertFalse((self.f.workspace / "rule_change.txt").exists())

    def test_context_fingerprint_rejects_unannounced_binding_change(self):
        plan_id = self.propose("binding")
        w.ACTIVE["state"].data["selected_target"] = {"path": str(self.f.bg_b)}
        self.rejected(plan_id)
        self.assertFalse((self.f.workspace / "binding.txt").exists())

    def test_rule_source_change_after_review_rejects_confirmation(self):
        self.post("/api/codebook/prepare", {"path": str(self.f.rules)})
        self.post("/api/codebook/lock", {})
        plan_id = self.propose("stale_rule")
        with self.f.rules.open("ab") as handle:
            handle.write(b"changed fixture rules")
        self.rejected(plan_id)
        self.assertFalse((self.f.workspace / "stale_rule.txt").exists())

    def test_source_change_after_review_rejects_before_writing(self):
        self.post(
            "/api/target", {"target": str(self.f.bg_a), "selected_paths": ["facts.txt"]}
        )
        plan_id = self.propose("stale_source")
        (self.f.bg_a / "facts.txt").write_text("Changed fixture source")
        self.rejected(plan_id)
        self.assertFalse((self.f.workspace / "stale_source.txt").exists())

    def test_changed_replacement_is_preserved(self):
        target = self.f.workspace / "original.txt"
        target.write_text("before")
        changes = w.build_diff(
            w.ACTIVE["state"], [{"path": "original.txt", "content": "after"}]
        )
        plan_id = w.publish_pending(w.ACTIVE, changes)
        target.write_text("external edit")
        self.rejected(plan_id)
        self.assertEqual(target.read_text(), "external edit")

    def test_link_inserted_after_review_cannot_redirect_apply(self):
        plan_id = self.propose("link_after_review")
        private = self.f.workspace / "AI_Bot_State" / "private.txt"
        private.write_text("unchanged")
        (self.f.workspace / "link_after_review.txt").symlink_to(private)
        response = self.client.post(
            "/api/apply", json={"confirmed": True, "plan_id": plan_id}
        )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(private.read_text(), "unchanged")


class ApplyPlanConfirmation(EnglishApiCase):
    def test_stale_confirmation_must_not_apply_a_different_pending_plan(self):
        def plan(name):
            return json.dumps(
                {
                    "answer": name,
                    "changes": [
                        {"path": name + ".txt", "content": name, "reason": "fixture"}
                    ],
                    "read_files": [],
                }
            )

        with patch.object(
            w.ACTIVE["llm"],
            "ask_about_files",
            side_effect=[plan("plan_A"), plan("plan_B")],
        ):
            first = self.post("/api/chat", {"question": "Prepare fixture A"})
            self.assertEqual(first["changes"][0]["path"], "plan_A.txt")
            self.post("/api/chat", {"question": "Prepare fixture B from second tab"})
        # This is exactly the request the still-open A confirmation button sends.
        response = self.client.post("/api/apply", json={"confirmed": True})
        self.assertEqual(
            response.status_code,
            409,
            f"A confirmation applied B: status={response.status_code}, B exists={(self.f.workspace / 'plan_B.txt').exists()}",
        )


class ApplyAndExcelMatrix(DirectSessionCase):
    def test_pending_cancel_confirm_backup_and_rollback(self):
        a=self.workspace/'a.txt'
        b=self.workspace/'b.txt'
        a.write_text('A')
        b.write_text('B')
        state=w.ACTIVE['state']
        changes=w.build_diff(state,[{'path':'a.txt','content':'new A'},{'path':'b.txt','content':'new B'}])
        plan_id = w.publish_pending(w.ACTIVE, changes)
        with self.assertRaises(w.HTTPException):
            w.apply(w.ApplyRequest(confirmed=False))
        self.assertEqual(a.read_text(),'A')
        real_replace=os.replace
        def fail_second(source,dest):
            if Path(dest)==b:
                raise PermissionError('file locked')
            return real_replace(source,dest)
        with patch.object(w.os,'replace',side_effect=fail_second), self.assertRaises(PermissionError):
            w.apply(w.ApplyRequest(confirmed=True, plan_id=plan_id))
        self.assertEqual(a.read_text(),'A')
        self.assertEqual(b.read_text(),'B')
        self.assertTrue(list((state.root/'backups').rglob('a.txt')))
        w.cancel_pending()
        self.assertEqual(w.ACTIVE['pending'],[])

    def test_atomic_excel_publication_preserves_formulas_and_failure(self):
        source=self.root/'source.xlsx'
        output=self.root/'result.xlsx'
        book=Workbook()
        sheet=book.active
        sheet.title='Data'
        sheet['A1']='ID'
        sheet['A2']='1'
        sheet['B1']='Template'
        sheet['B2']='x'
        sheet['D2']='=A2'
        sheet.merge_cells('E1:F1')
        book.save(source)
        book.close()
        book=excel.load_book(source)
        plan={'source_sha256':excel.sha256(source),'source_formula_fingerprint':excel.formula_fingerprint(book),
              'sheet':'Data','target_column':'C','template_column':'B','header_row':1,
              'edits':[{'cell':'Data!C1','value':'New'},{'cell':'Data!C2','value':'Gantry'}]}
        book.close()
        path=self.root/'plan.json'
        path.write_text(json.dumps(plan))
        args=SimpleNamespace(workbook=str(source),output=str(output),plan=str(path),force=False)
        with contextlib.redirect_stdout(io.StringIO()):
            excel.command_apply(args)
        self.assertEqual(excel.sha256(source),plan['source_sha256'])
        self.assertTrue(excel.verify_plan(output,plan)['ok'])
        output.unlink()
        with patch('openpyxl.workbook.workbook.Workbook.save',side_effect=PermissionError('locked')), self.assertRaises(PermissionError):
            excel.command_apply(args)
        self.assertFalse(output.exists())
        self.assertEqual(excel.sha256(source),plan['source_sha256'])
        self.assertFalse(list(self.root.glob('.result.*')))


if __name__ == "__main__":
    unittest.main(verbosity=2)
