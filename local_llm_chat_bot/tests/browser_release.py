"""Strict synthetic browser regressions. Run directly; failures exit nonzero."""

import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
import chat_workbench as w
from fixture_support import FixtureEnvironment
from playwright.sync_api import sync_playwright


OUTPUT = Path(
    os.getenv("WORKBENCH_TEST_OUTPUT") or tempfile.mkdtemp(prefix="workbench-browser-")
)
CHECKS = []


class BrowserRelease(unittest.TestCase):
    def setUp(self):
        self.stage = self._testMethodName
        self.f = FixtureEnvironment().__enter__()
        self.addCleanup(self.f.__exit__, None, None, None)
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        self.addCleanup(sock.close)
        self.server = uvicorn.Server(uvicorn.Config(w.app, log_level="error"))
        self.thread = threading.Thread(
            target=self.server.run, kwargs={"sockets": [sock]}, daemon=True
        )
        self.thread.start()
        self.addCleanup(self.stop_server)
        deadline = time.monotonic() + 10
        while not self.server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(self.server.started, "fixture server did not start")
        runtime = sync_playwright().start()
        self.addCleanup(runtime.stop)
        options = {"headless": True}
        if os.getenv("WORKBENCH_CHROMIUM_EXECUTABLE"):
            options["executable_path"] = os.environ["WORKBENCH_CHROMIUM_EXECUTABLE"]
        self.browser = runtime.chromium.launch(**options)
        self.addCleanup(self.browser.close)
        self.page = self.browser.new_page(viewport={"width": 1440, "height": 1000})
        self.page.set_default_timeout(8000)
        self.page.set_default_navigation_timeout(10000)
        self.errors, self.warnings = [], []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.on(
            "console",
            lambda msg: (
                self.warnings.append(msg.text) if msg.type == "warning" else None
            ),
        )
        self.page.on(
            "dialog",
            lambda dialog: (
                dialog.accept("gemini-2.5-pro")
                if dialog.type == "prompt"
                else dialog.accept()
            ),
        )
        self.page.goto(f"http://127.0.0.1:{port}")
        self.page.wait_for_function('typeof materialDraftDirty !== "undefined"')
        self.open_workspace()

    def stop_server(self):
        self.server.should_exit = True
        self.thread.join(timeout=10)

    def tearDown(self):
        self.assertEqual(self.errors, [], "browser page errors")
        self.assertEqual(
            [v for v in self.warnings if "Unknown UI translation key" in v], []
        )

    def completed(self, stage):
        CHECKS.append(
            {"test": self._testMethodName, "stage": stage, "status": "passed"}
        )

    def button(self, handler, root=""):
        return self.page.locator(f'{root} button[onclick="{handler}"]')

    def close_drawer(self):
        self.button("closeContextDrawer()", ".context-drawer-head").click()

    def open_drawer(self, kind):
        if kind == "workspace":
            self.page.locator("#workspaceshortcut").click()
        else:
            self.page.locator(
                f".context-card[onclick=\"openContextDrawer('{kind}')\"]"
            ).click()

    def open_workspace(self):
        self.open_drawer("workspace")
        self.page.locator("#contextworkspacepath").fill(str(self.f.workspace))
        self.button("contextOpenWorkspace()").click()
        # renderStatus is earlier than restoreSessionContext; await setup's final signal.
        self.page.wait_for_function(
            "document.getElementById('setupmsg').textContent === t('workspace.opened')"
        )

    def language(self, language):
        self.page.select_option("#language", language)
        self.page.evaluate("languageSave")
        self.page.wait_for_function(
            "(l)=>document.documentElement.lang===l", arg=language
        )

    def prepare_rules(self):
        self.open_drawer("rules")
        self.page.locator("#contextcodebookpath").fill(str(self.f.rules))
        self.button("contextSyncRule();prepareCodebook()").click()
        self.page.wait_for_function('lastCodebookWorkspaceProfile?.status === "draft"')
        self.close_drawer()

    def lock_rules(self):
        label = self.page.evaluate("t('rulews.lock_action')")
        self.page.get_by_role("button", name=label, exact=True).click()
        self.page.wait_for_function('lastCodebookWorkspaceProfile?.status === "locked"')

    def select_bg(self, folder):
        self.open_drawer("materials")
        self.page.locator("#contexttargetpath").fill(str(folder))
        self.button("contextSyncTarget();loadTargetTree()").click()
        self.page.wait_for_function(
            "(path)=>lastTargetTreePayload?.tree?.path===path", arg=str(folder)
        )
        self.page.locator("input.tree-file").first.wait_for(state="attached")
        self.button("contextSyncTarget();analyzeTarget()").click()
        self.page.wait_for_function(
            "(path)=>lastStatusSnapshot.bg_context?.folder===path", arg=str(folder)
        )
        self.close_drawer()

    def ask(self, question):
        self.page.locator("#question").fill(question)
        self.button("chat()", "#composer").click()
        self.page.wait_for_function(
            "!busy && document.getElementById('question').value === ''"
        )
        self.assertEqual(
            self.page.locator("#chat .message.error").count(),
            0,
            self.page.locator("#chat").inner_text(),
        )

    def test_user_flow(self):
        self.stage = "workspace and custom model"
        self.page.select_option("#model", "__custom__")
        self.page.locator("#custommodel").fill(" GEMINI-2.5-PRO ")
        self.button("confirmCustomModel()").click()
        self.page.wait_for_function('lastStatusSnapshot.model === "gemini-2.5-pro"')
        self.completed(self.stage)
        self.stage = "six language switches preserve model"
        for language in ["zh", "en", "de", "zh", "en", "de"]:
            self.language(language)
            self.assertEqual(
                self.page.input_value("#custommodel").strip().lower(), "gemini-2.5-pro"
            )
        self.completed(self.stage)
        self.language("en")
        self.stage = "prepare lock select classify follow-up"
        self.prepare_rules()
        self.lock_rules()
        self.button("leaveCodebookWorkspace()").click()
        self.select_bg(self.f.bg_a)
        self.ask("Classify this Baugruppe")
        # Coverage and classification share a CSS class; identify them by their own heading.
        card = self.page.locator(".classification-card").filter(
            has=self.page.get_by_role(
                "heading",
                name=self.page.evaluate("t('classification.title')"),
                exact=True,
            )
        )
        self.assertEqual(card.count(), 1)
        self.assertIn("Rotationseinheit", card.inner_text())
        coverage = self.page.locator(".classification-card").filter(
            has=self.page.get_by_role(
                "heading", name=self.page.evaluate("t('coverage.title')"), exact=True
            )
        )
        self.assertEqual(coverage.count(), 1)
        self.ask("Explain the motor evidence")
        self.completed(self.stage)
        self.stage = "edit rules and switch BG without old context"
        self.open_drawer("rules")
        self.button("viewCodebook()", "#contextdrawerbody").click()
        self.page.wait_for_function('lastCodebookWorkspaceProfile?.status === "locked"')
        self.close_drawer()
        self.button("editCodebookDraft()").click()
        draft = json.loads(self.page.input_value("#ruleeditor"))
        draft["classes"][0]["name"] = "Fixture Class B"
        self.page.locator("#ruleeditor").fill(json.dumps(draft))
        self.button("saveCodebookDraft()").click()
        self.page.wait_for_function('lastCodebookWorkspaceProfile?.status === "draft"')
        self.lock_rules()
        self.button("leaveCodebookWorkspace()").click()
        self.select_bg(self.f.bg_b)
        self.ask("Classify this Baugruppe again")
        self.assertIn("Fixture Class B", card.inner_text())
        self.assertNotIn("FIXTURE_BG_A", json.dumps(self.f.calls[-1]))
        self.completed(self.stage)
        self.stage = "refresh restores workspace model language and BG"
        self.page.reload()
        self.page.wait_for_function(
            'lastStatusSnapshot?.bg_context?.folder.endsWith("BG_B")'
        )
        self.page.wait_for_function(
            "document.getElementById('targetpath').value.endsWith('BG_B')"
        )
        self.assertEqual(self.page.input_value("#workspace"), str(self.f.workspace))
        self.assertEqual(self.page.evaluate("selectedModel()"), "gemini-2.5-pro")
        self.assertEqual(self.page.input_value("#language"), "en")
        self.completed(self.stage)

    def test_rule_change_reconfirms_same_bg_and_pending_path_is_explicit(self):
        self.language("en")
        self.page.select_option("#model", "gemini-2.5-pro")
        self.page.wait_for_function('lastStatusSnapshot.model === "gemini-2.5-pro"')
        self.prepare_rules()
        self.lock_rules()
        self.button("leaveCodebookWorkspace()").click()
        self.select_bg(self.f.bg_a)
        self.ask("Classify this Baugruppe")
        self.open_drawer("rules")
        alternate = str(self.f.root / "not prepared ü.docx")
        self.page.locator("#contextcodebookpath").fill(alternate)
        self.assertIn(
            str(self.f.rules), self.page.locator("#contextrulemsg").inner_text()
        )
        self.assertIn(
            str(self.f.rules), self.page.locator("#codebookstatus").inner_text()
        )
        self.page.locator("#contextcodebookpath").fill(str(self.f.rules))
        self.assertEqual(self.page.locator("#contextrulemsg").inner_text(), "")
        self.button("viewCodebook()", "#contextdrawerbody").click()
        self.page.wait_for_function('lastCodebookWorkspaceProfile?.status === "locked"')
        self.close_drawer()
        self.button("editCodebookDraft()").click()
        draft = json.loads(self.page.input_value("#ruleeditor"))
        draft["classes"][0]["name"] = "New same-BG fixture class"
        self.page.locator("#ruleeditor").fill(json.dumps(draft))
        self.button("saveCodebookDraft()").click()
        self.page.wait_for_function('lastCodebookWorkspaceProfile?.status === "draft"')
        self.lock_rules()
        self.button("leaveCodebookWorkspace()").click()
        self.page.wait_for_function("document.getElementById('question').disabled")
        self.assertIn("Confirm", self.page.locator("#contextguard").inner_text())
        count = len(self.f.calls)
        for endpoint, body in [
            ("/api/chat", {"question": "classify"}),
            (
                "/api/compare",
                {
                    "question": "classify",
                    "models": ["gemini-2.5-pro", "gemini-2.5-flash"],
                },
            ),
        ]:
            self.assertEqual(
                self.page.request.post(
                    self.page.url.rstrip("/") + endpoint, data=body
                ).status,
                409,
            )
        self.assertEqual(len(self.f.calls), count)
        self.open_drawer("materials")
        self.assertEqual(self.page.input_value("#contexttargetpath"), str(self.f.bg_a))
        self.assertTrue(self.page.locator("input.tree-file").first.is_checked())
        with self.page.expect_response(
            lambda response: response.url.endswith("/api/target")
        ) as response:
            self.button("contextSyncTarget();analyzeTarget()").click()
        self.assertEqual(response.value.status, 200)
        self.page.wait_for_function("!document.getElementById('question').disabled")
        self.close_drawer()
        self.ask("Classify this Baugruppe")
        card = self.page.locator(".classification-card").filter(
            has=self.page.get_by_role(
                "heading",
                name=self.page.evaluate("t('classification.title')"),
                exact=True,
            )
        )
        self.assertIn("New same-BG fixture class", card.inner_text())

    def test_explicit_explanation_mode_and_nonpaged_rule_references(self):
        self.language("en")
        self.page.select_option("#model", "gemini-2.5-pro")
        self.page.wait_for_function('lastStatusSnapshot.model === "gemini-2.5-pro"')
        self.prepare_rules()
        self.lock_rules()
        self.button("leaveCodebookWorkspace()").click()
        self.select_bg(self.f.bg_a)
        self.assertEqual(self.page.input_value("#answermode"), "classification")
        self.ask("Classify this Baugruppe")
        card = self.page.locator(".classification-card").filter(
            has=self.page.get_by_role(
                "heading", name="Classification result (validated)", exact=True
            )
        )
        self.assertIn("Section/chunk references", card.inner_text())
        self.assertIn(self.f.rules.name, card.inner_text())
        self.page.select_option("#answermode", "explanation")
        self.language("de")
        self.assertEqual(self.page.input_value("#answermode"), "explanation")
        with self.page.expect_response(
            lambda response: response.url.endswith("/api/chat/stream")
        ) as response:
            self.ask("Erläutere die Motorfunktion")
        self.assertFalse(
            response.value.request.post_data_json["require_classification"]
        )
        self.assertEqual(card.count(), 1)
        self.assertNotIn(
            "classification",
            self.page.locator("#chat .message.error").all_text_contents(),
        )
        self.select_bg(self.f.bg_b)
        self.assertEqual(self.page.input_value("#answermode"), "classification")

    def test_material_drawer_geometry_and_real_actions(self):
        self.language("en")
        self.prepare_rules()
        self.lock_rules()
        self.button("leaveCodebookWorkspace()").click()
        for width in [1440, 800, 390]:
            with self.subTest(width=width):
                self.stage = f"materials drawer geometry and clicks at {width}px"
                self.page.set_viewport_size({"width": width, "height": 900})
                # Narrow layouts hide the context sidebar: exercise the visible welcome action.
                if width < 1180:
                    self.button("openContextDrawer('materials')", "#chat").click()
                else:
                    self.open_drawer("materials")
                drawer = self.page.locator(".context-drawer")
                box = drawer.bounding_box()
                self.page.screenshot(path=str(OUTPUT / f"width-{width}.png"))
                self.assertIsNotNone(box)
                self.assertGreaterEqual(box["x"], -1, box)
                self.assertLessEqual(box["x"] + box["width"], width + 1, box)
                self.page.locator("#contexttargetpath").fill(str(self.f.bg_a))
                self.button("contextSyncTarget();loadTargetTree()").click()
                self.page.locator("input.tree-file").first.wait_for(state="attached")
                # Expand/collapse the actual tree and change a checkbox, then restore it.
                toggle = self.page.locator("#targettree summary").first
                if toggle.count():
                    toggle.click()
                    toggle.click()
                checkbox = self.page.locator("input.tree-file").first
                checkbox.uncheck()
                checkbox.check()
                confirm = self.button("contextSyncTarget();analyzeTarget()")
                confirm.scroll_into_view_if_needed()
                rect = confirm.bounding_box()
                self.assertGreaterEqual(rect["x"], 0, rect)
                self.assertLessEqual(rect["x"] + rect["width"], width + 1, rect)
                with self.page.expect_response(
                    lambda r: (
                        r.url.endswith("/api/target") and r.request.method == "POST"
                    )
                ) as response:
                    confirm.click()
                self.assertEqual(response.value.status, 200)
                self.close_drawer()
                self.page.wait_for_function(
                    "!document.getElementById('contextbackdrop').classList.contains('open')"
                )
                self.completed(self.stage)
            # Return to a known welcome screen before testing the next viewport.
            self.page.reload()
            self.page.wait_for_function("typeof openContextDrawer === 'function'")

    def test_rule_draft_survives_language_cycle(self):
        self.prepare_rules()
        self.button("editCodebookDraft()").click()
        marker = "UNSAVED_FIXTURE_DRAFT {"
        self.page.locator("#ruleeditor").fill(marker)
        for language in ["zh", "en", "de", "zh", "en", "de"]:
            with self.subTest(language=language):
                self.language(language)
                self.assertEqual(self.page.locator("#ruleeditor").count(), 1)
                self.assertEqual(self.page.input_value("#ruleeditor"), marker)

    def test_existing_classification_card_uses_current_language(self):
        # Isolate card retranslation from backend classification semantics.
        self.language("zh")
        self.page.evaluate("""() => document.getElementById('chat').append(classificationCard({
            label:'Rotationseinheit',confidence:'high',evidence_labels:['facts.txt block 1'],
            codebook_rule_ids:['rotation-1'],codebook_rule_pages:[1],
            bg_evidence_pages:['facts.txt block 1'],uncertainties:[]}))""")
        self.assertIn(
            self.page.evaluate("t('classification.title')"),
            self.page.locator(".classification-card h3").all_text_contents(),
        )
        self.language("en")
        headings = self.page.locator(".classification-card h3").all_text_contents()
        self.assertIn(self.page.evaluate("t('classification.title')"), headings)

    def test_workspace_attribute_input_cannot_create_event_handler(self):
        payload = 'fixture" onpointerover="window.__auditXss=1'
        self.open_drawer("workspace")
        self.page.locator("#contextworkspacepath").fill(payload)
        self.button("contextOpenWorkspace()").click()
        self.page.wait_for_function(
            "!document.getElementById('contextbackdrop')?.classList.contains('open')"
        )
        self.open_drawer("workspace")
        field = self.page.locator("#contextworkspacepath")
        field.dispatch_event("pointerover")
        self.assertIsNone(field.get_attribute("onpointerover"))
        self.assertFalse(self.page.evaluate("window.__auditXss === 1"))
        self.assertEqual(field.input_value(), payload)

    def test_paths_and_custom_comparison_model_escape_attributes(self):
        payload = '中文 ü <tag> & " onpointerover="window.__attributeProbe=1'
        for kind, backing, field in [
            ("workspace", "workspace", "contextworkspacepath"),
            ("rules", "codebook", "contextcodebookpath"),
            ("materials", "targetpath", "contexttargetpath"),
        ]:
            with self.subTest(kind=kind):
                original = self.page.input_value("#" + backing)
                self.page.evaluate(
                    "([id,value])=>document.getElementById(id).value=value",
                    [backing, payload],
                )
                self.open_drawer(kind)
                control = self.page.locator("#" + field)
                self.assertEqual(control.input_value(), payload)
                self.assertIsNone(control.get_attribute("onpointerover"))
                control.dispatch_event("pointerover")
                self.assertFalse(self.page.evaluate("window.__attributeProbe===1"))
                self.close_drawer()
                self.page.evaluate(
                    "([id,value])=>document.getElementById(id).value=value",
                    [backing, original],
                )
        self.button("openCompareDrawer()").click()
        self.page.select_option("#cmpsel0", "__custom__")
        self.page.locator("#cmpcustom0").fill(payload)
        # Isolate both attribute renderers from the separate language-drawer
        # lifecycle issue tracked for the later localization stage.
        self.page.evaluate("renderCompareSlotsForLanguage()")
        control = self.page.locator("#cmpcustom0")
        self.assertEqual(control.input_value(), payload)
        self.assertIsNone(control.get_attribute("onpointerover"))
        control.dispatch_event("pointerover")
        self.assertFalse(self.page.evaluate("window.__attributeProbe===1"))

    def test_two_pages_confirm_only_their_displayed_plan(self):
        other = self.browser.new_page(viewport={"width": 1440, "height": 1000})
        self.addCleanup(other.close)
        other.on("dialog", lambda dialog: dialog.accept())
        other.on("pageerror", lambda error: self.errors.append(str(error)))
        other.goto(self.page.url)
        other.wait_for_function(
            "lastStatusSnapshot?.workspace && document.getElementById('setupmsg').textContent === t('workspace.opened')"
        )

        def action(name):
            return json.dumps(
                {
                    "answer": name,
                    "changes": [{"path": name + ".txt", "content": name}],
                    "read_files": [],
                }
            )

        first_page = self.page
        with patch.object(
            w.ACTIVE["llm"],
            "ask_about_files",
            side_effect=[action("page_A"), action("page_B")],
        ):
            self.ask("Prepare plan A")
            first_id = first_page.locator(
                ".change-plan button[data-plan-id]"
            ).get_attribute("data-plan-id")
            self.page = other
            try:
                self.ask("Prepare plan B")
            finally:
                self.page = first_page
        second_id = other.locator(".change-plan button[data-plan-id]").get_attribute(
            "data-plan-id"
        )
        self.assertNotEqual(first_id, second_id)
        with first_page.expect_response(
            lambda r: r.url.endswith("/api/apply")
        ) as response:
            first_page.locator(".change-plan button[data-plan-id]").click()
        self.assertEqual(response.value.request.post_data_json["plan_id"], first_id)
        self.assertEqual(response.value.status, 409)
        self.assertFalse((self.f.workspace / "page_A.txt").exists())
        self.assertFalse((self.f.workspace / "page_B.txt").exists())
        with other.expect_response(lambda r: r.url.endswith("/api/apply")) as response:
            other.locator(".change-plan button[data-plan-id]").click()
        self.assertEqual(response.value.request.post_data_json["plan_id"], second_id)
        self.assertEqual(response.value.status, 200)
        self.assertEqual((self.f.workspace / "page_B.txt").read_text(), "page_B")


class RecordedResult(unittest.TextTestResult):
    def addFailure(self, test, err):
        super().addFailure(test, err)
        CHECKS.append(
            {
                "test": str(test),
                "stage": getattr(test, "stage", str(test)),
                "status": "failed",
                "detail": self._exc_info_to_string(err, test),
            }
        )

    def addError(self, test, err):
        super().addError(test, err)
        CHECKS.append(
            {
                "test": str(test),
                "stage": getattr(test, "stage", str(test)),
                "status": "error",
                "detail": self._exc_info_to_string(err, test),
            }
        )

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err:
            CHECKS.append(
                {
                    "test": str(subtest),
                    "stage": test.stage,
                    "status": "failed",
                    "detail": self._exc_info_to_string(err, test),
                }
            )


if __name__ == "__main__":
    OUTPUT.mkdir(parents=True, exist_ok=True)
    result = unittest.TextTestRunner(verbosity=2, resultclass=RecordedResult).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(BrowserRelease)
    )
    (OUTPUT / "browser-results.json").write_text(
        json.dumps(
            {
                "success": result.wasSuccessful(),
                "tests_run": result.testsRun,
                "checks": CHECKS,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Browser results: {OUTPUT}")
    sys.exit(0 if result.wasSuccessful() else 1)
