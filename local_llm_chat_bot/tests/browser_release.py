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
        self.handle_dialog = lambda dialog: (
                dialog.accept("gemini-2.5-pro")
                if dialog.type == "prompt"
                else dialog.accept()
            )
        self.page.on('dialog', self.handle_dialog)
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
        elif self.page.viewport_size['width'] < 1180 and kind in {'materials', 'rules'}:
            self.page.locator('#contextshortcut-' + kind).click()
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
        self.assertEqual(self.page.locator('.classification-card').filter(
            has=self.page.get_by_role('heading', name=self.page.evaluate("t('classification.title')"), exact=True)
        ).count(), 1)
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
        self.assertEqual(self.page.locator('.classification-card').filter(
            has=self.page.get_by_role('heading', name=self.page.evaluate("t('classification.title')"), exact=True)
        ).count(), 1)
        self.assertNotIn(
            "classification",
            self.page.locator("#chat .message.error").all_text_contents(),
        )
        self.select_bg(self.f.bg_b)
        self.assertEqual(self.page.input_value("#answermode"), "classification")

    def test_answer_preview_stop_keeps_busy_until_worker_exits_then_retry(self):
        self.language('en')
        self.page.select_option('#model', 'gemini-2.5-pro')
        self.page.wait_for_function("lastStatusSnapshot.model==='gemini-2.5-pro'")
        release = threading.Event()
        self.addCleanup(release.set)
        preview = 'VISIBLE_PREVIEW\n```python\nprint("ü 😀")\n```\n| Part | Function |\n|---|---|\n| Motor | Rotation |\n<img onerror="window.previewInjection=1">'
        raw = json.dumps({'changes': [{'path': 'SECRET_PATH', 'content': 'SECRET_CONTENT'}],
                          'classification': {'label': 'SECRET_CLASS'}, 'answer': preview})
        original_history = list(w.ACTIVE['state'].data['history'])
        def answer(*_args, **kwargs):
            for index in range(0, len(raw), 13):
                kwargs['event_handler']('content', raw[index:index+13])
            release.wait(5)
            return json.dumps({'answer': 'late final', 'read_files': ['extra.txt'], 'changes': []})
        with patch.object(w.ACTIVE['llm'], 'ask_about_files', side_effect=answer) as model:
            self.page.locator('#question').fill('Show a draft answer')
            self.button('chat()', '#composer').click()
            self.page.wait_for_function("document.querySelector('.preview-text')?.textContent.includes('<img')")
            self.assertEqual(self.page.locator('.preview-text').inner_text(), preview)
            self.assertNotIn('SECRET_', self.page.locator('.answer-preview').inner_text())
            self.assertEqual(self.page.locator('.answer-preview img').count(), 0)
            self.assertEqual(self.page.locator('.change-plan').count(), 0)
            self.assertEqual(self.page.locator('.classification-card').count(), 0)
            self.assertTrue(self.page.evaluate('busy'))
            self.page.locator('#cancelchat').click()
            self.page.wait_for_function("document.querySelector('[data-process-text]')?.textContent.includes('Stopping')")
            self.assertTrue(w.MODEL_WORK_IN_PROGRESS.is_set())
            self.assertTrue(self.page.evaluate('busy'))
            self.assertEqual(self.page.locator('.answer-preview').count(), 0)
            release.set()
            self.page.wait_for_function('!busy')
            self.assertEqual(model.call_count, 1)
        self.assertEqual(w.ACTIVE['state'].data['history'], original_history)
        self.assertIn('Stopped', self.page.locator('[data-process-text]').inner_text())
        self.assertFalse(w.MODEL_WORK_IN_PROGRESS.is_set())
        self.assertEqual(w.ACTIVE['pending'], [])
        self.ask('Retry after stop')
        self.completed('safe preview, explicit stop and retry')

    def test_navigation_disconnect_and_truncated_preview_never_create_results(self):
        self.language('en')
        self.page.select_option('#model', 'gemini-2.5-pro')
        self.page.wait_for_function("lastStatusSnapshot.model==='gemini-2.5-pro'")
        release = threading.Event()
        self.addCleanup(release.set)
        def answer(*_args, **kwargs):
            kwargs['event_handler']('content', '{"answer":"VISIBLE_PREVIEW","changes":[')
            release.wait(5)
            return '{"answer":"VISIBLE_PREVIEW","changes":['
        old_history = list(w.ACTIVE['state'].data['history'])
        with patch.object(w.LLMConnector, 'ask_about_files', side_effect=answer):
            self.page.locator('#question').fill('Navigation disconnect')
            self.button('chat()', '#composer').click()
            self.page.locator('.answer-preview').wait_for()
            control = w.CHAT_TASK['control']
            self.page.reload()
            self.assertTrue(control.cancel_event.wait(1))
            self.assertTrue(w.MODEL_WORK_IN_PROGRESS.is_set())
            release.set()
            self.page.wait_for_function("typeof busy!=='undefined'")
            deadline = time.monotonic() + 3
            while w.MODEL_WORK_IN_PROGRESS.is_set() and time.monotonic() < deadline:
                self.page.wait_for_timeout(20)
            self.assertFalse(w.MODEL_WORK_IN_PROGRESS.is_set())
            self.open_workspace()
            self.page.locator('#question').fill('Truncated response')
            with self.page.expect_response(lambda response: response.url.endswith('/api/chat/stream')):
                self.button('chat()', '#composer').click()
            self.page.wait_for_function('!busy')
        self.assertEqual(w.ACTIVE['state'].data['history'], old_history)
        self.assertEqual(self.page.locator('.answer-preview').count(), 0)
        self.assertEqual(self.page.locator('.change-plan').count(), 0)
        self.assertEqual(w.ACTIVE['pending'], [])
        self.assertGreater(self.page.locator('#chat .message.error').count(), 0)
        self.completed('navigation disconnect and truncated preview cleanup')

    def test_unknown_usage_is_visible_in_chat_status_rules_and_comparison(self):
        self.language('en')
        self.page.select_option('#model', 'gemini-2.5-pro')
        self.page.wait_for_function("lastStatusSnapshot.model==='gemini-2.5-pro'")
        self.f.response_transform = lambda response, *_: {
            key: value for key, value in response.items() if key != 'usageMetadata'
        }
        self.ask('Explain the fixture')
        self.assertIn('Unknown', self.page.locator('#usagedetail').inner_text())
        self.assertIn('Known subtotal', self.page.locator('#status').inner_text())
        self.assertIn('Unknown', self.page.locator('#status').inner_text())
        self.assertNotIn('null', self.page.locator('#usagedetail').inner_text())
        self.f.response_transform = None
        self.ask('Explain again')
        self.assertIn('Unknown', self.page.locator('#status').inner_text())
        self.assertIn('20 / 10', self.page.locator('#status').inner_text())
        self.f.response_transform = lambda response, *_: {
            key: value for key, value in response.items() if key != 'usageMetadata'
        }
        self.prepare_rules()
        self.lock_rules()
        self.assertIn('Unknown', self.page.locator('.codebook-workspace').inner_text())
        self.button('leaveCodebookWorkspace()').click()
        self.select_bg(self.f.bg_a)
        self.page.locator('#question').fill('classify')
        self.button('openCompareDrawer()').click()
        self.page.select_option('#cmpsel0', 'gemini-2.5-pro')
        self.button('addCompareModel()').click()
        self.page.select_option('#cmpsel1', 'gemini-2.5-flash')
        self.button('compareModels()').click()
        self.page.locator('.comparison-grid .answer').first.wait_for()
        self.assertIn('Unknown', self.page.locator('.comparison-grid').inner_text())
        self.assertFalse(self.errors, self.errors)
        self.completed('unknown usage display')

    def test_material_drawer_geometry_and_real_actions(self):
        self.language("en")
        self.prepare_rules()
        self.lock_rules()
        self.button("leaveCodebookWorkspace()").click()
        for width in [1440, 800, 390]:
            with self.subTest(width=width):
                self.stage = f"materials drawer geometry and clicks at {width}px"
                self.page.set_viewport_size({"width": width, "height": 900})
                # Use the permanent visible shortcut when the context sidebar is hidden.
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
            self.page.wait_for_function("document.getElementById('setupmsg').textContent===t('workspace.opened') && activeContextDrawer===null")

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

    def test_long_invalid_draft_keeps_selection_scroll_errors_and_cancel_guard(self):
        self.prepare_rules()
        original = self.f.rules.read_bytes()
        self.button('editCodebookDraft()').click()
        raw = '{\n' + '\n'.join(f'  "line{i}": "原文 Regel {i}",' for i in range(180))
        self.page.locator('#ruleeditor').fill(raw)
        self.page.eval_on_selector('#ruleeditor', '(node)=>{node.setSelectionRange(1200,1234,"backward");node.scrollTop=800;node.dispatchEvent(new Event("select"));node.dispatchEvent(new Event("scroll"))}')
        state = self.page.eval_on_selector('#ruleeditor', '(n)=>[n.selectionStart,n.selectionEnd,n.selectionDirection,n.scrollTop]')
        self.button('saveCodebookDraft()').click()
        self.assertTrue(self.page.locator('#ruleediterror').inner_text())
        for language in ['zh', 'en', 'de', 'zh', 'en', 'de']:
            self.language(language)
            self.assertEqual(self.page.input_value('#ruleeditor'), raw)
            self.assertEqual(self.page.eval_on_selector('#ruleeditor', '(n)=>[n.selectionStart,n.selectionEnd,n.selectionDirection,n.scrollTop]'), state)
            self.assertIn(self.page.evaluate("t('rules.invalid_json',{detail:''})").strip(), self.page.locator('#ruleediterror').inner_text())
            self.assertEqual(self.page.locator('#ruledirty').inner_text(), self.page.evaluate("t('rules.unsaved')"))
        # A rejected discard leaves the same editing context intact.
        self.page.remove_listener('dialog', self.handle_dialog)
        session = self.page.evaluate('lastStatusSnapshot.session_name')
        self.page.once('dialog', lambda dialog: dialog.dismiss())
        self.page.locator('#newsessionbutton').click()
        self.assertEqual(self.page.evaluate('lastStatusSnapshot.session_name'), session)
        self.assertEqual(self.page.input_value('#ruleeditor'), raw)
        self.open_drawer('workspace')
        self.page.locator('#contextworkspacepath').fill(str(self.f.root))
        self.page.once('dialog', lambda dialog: dialog.dismiss())
        self.button('contextOpenWorkspace()').click()
        self.assertEqual(self.page.evaluate('lastStatusSnapshot.workspace'), str(self.f.workspace))
        self.assertEqual(self.page.input_value('#ruleeditor'), raw)
        self.close_drawer()
        self.open_drawer('rules')
        self.page.once('dialog', lambda dialog: dialog.dismiss())
        self.button('contextSyncRule();prepareCodebook()').click()
        self.close_drawer()
        self.assertEqual(self.page.input_value('#ruleeditor'), raw)
        self.page.once('dialog', lambda dialog: dialog.dismiss())
        self.button('cancelRuleDraft()').click()
        self.assertEqual(self.page.input_value('#ruleeditor'), raw)
        self.page.once('dialog', lambda dialog: dialog.accept())
        self.button('cancelRuleDraft()').click()
        self.assertEqual(self.page.locator('#ruleeditor').count(), 0)
        self.assertEqual(self.f.rules.read_bytes(), original)

    def test_draft_save_confirmation_and_stale_context_preserve_raw_input(self):
        self.prepare_rules()
        source = self.f.rules.read_bytes()
        self.button('editCodebookDraft()').click()
        draft = json.loads(self.page.input_value('#ruleeditor'))
        draft['classes'][0]['definition'] = 'USER 中文 Definition {count}'
        raw = json.dumps(draft, ensure_ascii=False, indent=3)
        self.page.locator('#ruleeditor').fill(raw)
        self.page.remove_listener('dialog', self.handle_dialog)
        self.page.once('dialog', lambda dialog: dialog.dismiss())
        self.button('saveCodebookDraft()').click()
        self.assertEqual(self.page.input_value('#ruleeditor'), raw)
        self.page.once('dialog', lambda dialog: dialog.accept())
        self.button('saveCodebookDraft()').click()
        self.page.wait_for_function('ruleEditState===null')
        self.assertEqual(self.page.evaluate('lastCodebookWorkspaceProfile.draft.classes[0].definition'), draft['classes'][0]['definition'])
        self.assertEqual(self.f.rules.read_bytes(), source)
        # A second tab changes the app draft after this editor opened.
        self.button('editCodebookDraft()').click()
        raw += '  '
        self.page.locator('#ruleeditor').fill(raw)
        response = self.page.request.post(self.page.url + 'api/codebook/edit', data={
            'draft': draft, 'confirmed': True,
            'profile_version': self.page.evaluate('lastCodebookWorkspaceProfile.version'),
        })
        self.assertEqual(response.status, 200)
        self.page.once('dialog', lambda dialog: dialog.accept())
        self.button('saveCodebookDraft()').click()
        self.page.wait_for_function('ruleEditState?.error?.message_key === "rules.version_changed"')
        self.language('de')
        self.assertEqual(self.page.input_value('#ruleeditor'), raw)
        self.assertEqual(self.page.locator('#ruleediterror').inner_text(), self.page.evaluate("t('rules.version_changed')"))
        self.assertEqual(self.f.rules.read_bytes(), source)

    def test_structured_dynamic_messages_redraw_without_translating_content(self):
        self.page.evaluate("""() => {
            let raw='MODEL 原文 <b>Regel</b> {count}';
            $('chat').innerHTML='';message(raw);showChatResult({answer:raw,reasoning:raw,notices:[raw],
                notice_messages:[{message_key:'notice.dossier_failed',params:{detail:raw}}],
                sources:[{label:raw,visual:true}],dfc_evidence:[{name:raw,ocr_status:'not_requested',segments_used:[1],segments_total:2}],
                coverage_summary:{complete:true,files:[{name:raw,complete:true,scope_message:{message_key:'material.scope_full'},read:1,total:1}]},changes:[],usage:lastStatusSnapshot});
            window.fixtureProcessing=processingCard();updateProcessing(fixtureProcessing,{message_key:'reading.file',params:{index:1,total:2,name:raw},percent:20});
        }""")
        self.page.locator('.reason summary').click()
        for language in ['zh', 'en', 'de', 'zh', 'en', 'de']:
            self.language(language)
            raw = 'MODEL 原文 <b>Regel</b> {count}'
            self.assertEqual(self.page.locator('#chat > .message').first.inner_text(), raw)
            self.assertEqual(self.page.locator('.reason pre').inner_text(), raw)
            self.assertEqual(self.page.locator('.reason summary').inner_text(), self.page.evaluate("t('model.reasoning')"))
            self.assertEqual(self.page.locator('[data-process-text]').inner_text(), self.page.evaluate("t('reading.file',{index:1,total:2,name:'MODEL 原文 <b>Regel</b> {count}'})"))
            self.assertIn(self.page.evaluate("t('evidence.visual')"), self.page.locator('#sources').inner_text())
            self.assertIn(self.page.evaluate("t('state.not_requested')"), self.page.locator('#sources').inner_text())
            self.assertEqual(self.page.locator('[data-ui-component="notices"]').inner_text(), self.page.evaluate("t('notice.dossier_failed',{detail:'MODEL 原文 <b>Regel</b> {count}'})"))

    def test_german_mobile_drawer_long_error_folder_selection_and_close(self):
        self.language('de')
        self.prepare_rules()
        self.button('leaveCodebookWorkspace()').click()
        nested = self.f.bg_a / ('Unterlagen_' + 'lang_' * 18)
        nested.mkdir()
        (nested / ('Zeichnung_' + 'x' * 110 + '.txt')).write_text('Fixture material', encoding='utf-8')
        for width in [390, 800, 1440]:
            self.page.set_viewport_size({'width': width, 'height': 900})
            self.open_drawer('materials')
            self.page.route('**/api/pick/file', lambda route: route.fulfill(json={'path': str(self.f.bg_a / 'facts.txt')}))
            self.button("contextPickTarget('file')").click()
            self.page.wait_for_function('(path)=>document.getElementById("contexttargetpath").value===path', arg=str(self.f.bg_a / 'facts.txt'))
            self.page.unroute('**/api/pick/file')
            self.page.route('**/api/pick/folder', lambda route: route.fulfill(json={'path': str(self.f.bg_a)}))
            self.button("contextPickTarget('folder')").click()
            self.page.wait_for_function('(path)=>lastTargetTreePayload?.tree?.path===path', arg=str(self.f.bg_a))
            self.page.unroute('**/api/pick/folder')
            self.page.route('**/api/pick/folder', lambda route: route.fulfill(json={'path': ''}))
            with self.page.expect_response(lambda response: response.url.endswith('/api/pick/folder')):
                self.button("contextPickTarget('folder')").click()
            self.assertEqual(self.page.input_value('#contexttargetpath'), str(self.f.bg_a))
            self.page.unroute('**/api/pick/folder')
            detail = str(nested / 'missing') + ': ' + ('Technische Fehlerbeschreibung ' * 30)
            self.page.route('**/api/target-tree?*', lambda route: route.fulfill(status=400, content_type='application/json', body=json.dumps({
                'detail': detail, 'message_key': 'error.operation_failed', 'params': {'detail': detail}})))
            self.page.locator('#contexttargetpath').fill(str(nested / 'missing'))
            self.button('contextSyncTarget();loadTargetTree()').click()
            self.page.locator('#treestatus .error').wait_for()
            self.assertIn(detail, self.page.locator('#treestatus').text_content())
            self.page.screenshot(path=str(OUTPUT / f'de-long-error-{width}.png'))
            box = self.page.locator('.context-drawer').bounding_box()
            self.assertGreaterEqual(box['x'], -1)
            self.assertLessEqual(box['x'] + box['width'], width + 1)
            self.page.unroute('**/api/target-tree?*')
            self.page.locator('#contexttargetpath').fill(str(self.f.bg_a))
            self.button('contextSyncTarget();loadTargetTree()').click()
            self.page.locator('input.tree-folder').first.wait_for()
            folder = self.page.locator('input.tree-folder').first
            folder.uncheck()
            self.assertEqual(self.page.locator('input.tree-file:checked').count(), 0)
            folder.check()
            self.assertEqual(self.page.locator('input.tree-file:checked').count(), 2)
            self.close_drawer()
            self.assertEqual(self.page.locator('input.tree-file:checked').count(), 2)
            self.open_drawer('materials')
            self.page.keyboard.press('Escape')
            self.page.wait_for_function('activeContextDrawer===null')

    def test_startup_configuration_errors_are_visible_localized_and_recoverable(self):
        self.language('en')
        for code in ['startup.key_missing', 'startup.state_unwritable']:
            if code == 'startup.state_unwritable':
                self.page.set_viewport_size({'width': 390, 'height': 900})
            self.open_drawer('workspace')
            state = w.ACTIVE['state']
            failure = w.StartupError(code, path=self.f.root / 'Konfiguration 中文 ü')
            with patch.object(w, 'check_state_directory', side_effect=failure):
                self.button('contextOpenWorkspace()').click()
                self.page.locator('#contextworkspacemsg .error').wait_for()
                self.assertIs(w.ACTIVE['state'], state)
                self.assertEqual(self.page.evaluate('activeContextDrawer'), 'workspace')
                self.assertTrue(self.page.locator('#startupnotice').is_visible())
                for language in ['de', 'zh', 'en']:
                    self.language(language)
                    expected = self.page.evaluate('(v)=>t(v.code,{path:v.path})', {'code': code, 'path': str(self.f.root / 'Konfiguration 中文 ü')})
                    self.assertEqual(self.page.locator('#startupnotice').inner_text(), expected)
                    self.assertEqual(self.page.locator('#contextworkspacemsg').inner_text(), expected)
                    self.assertTrue(self.page.locator('#contextworkspacemsg').is_visible())
                    if code == 'startup.state_unwritable' and language == 'de':
                        self.page.screenshot(path=str(OUTPUT / 'startup-recovery-de-390.png'))
                    self.assertEqual(self.page.input_value('#contextworkspacepath'), str(self.f.workspace))
            self.button('contextOpenWorkspace()').click()
            self.page.wait_for_function('activeContextDrawer===null && !document.getElementById("startupnotice")')

    def test_workspace_attribute_input_cannot_create_event_handler(self):
        payload = 'fixture" onpointerover="window.__auditXss=1'
        self.open_drawer("workspace")
        self.page.locator("#contextworkspacepath").fill(payload)
        self.button("contextOpenWorkspace()").click()
        self.page.locator('#contextworkspacemsg .error').wait_for()
        self.assertEqual(self.page.evaluate('lastStatusSnapshot.workspace'), str(self.f.workspace))
        self.close_drawer()
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

    def test_stale_tab_cannot_classify_another_tabs_session_or_bg(self):
        self.language("en")
        self.page.select_option("#model", "gemini-2.5-pro")
        self.page.wait_for_function('lastStatusSnapshot.model === "gemini-2.5-pro"')
        self.prepare_rules()
        self.lock_rules()
        self.button("leaveCodebookWorkspace()").click()
        self.select_bg(self.f.bg_a)
        session_a = self.page.evaluate("lastStatusSnapshot.session_name")
        other = self.browser.new_page(viewport={"width": 1440, "height": 1000})
        self.addCleanup(other.close)
        other.on("dialog", self.handle_dialog)
        other.on("pageerror", lambda error: self.errors.append(str(error)))
        other.goto(self.page.url)
        other.wait_for_function(
            "lastStatusSnapshot?.workspace && document.getElementById('setupmsg').textContent === t('workspace.opened')"
        )
        first_page = self.page
        self.page = other
        try:
            other.evaluate("newSession()")
            other.wait_for_function("(s)=>lastStatusSnapshot?.session_name && lastStatusSnapshot.session_name!==s",
                                    arg=session_a)
            self.select_bg(self.f.bg_b)
        finally:
            self.page = first_page
        session_b = w.ACTIVE["state"].root.name
        calls = len(self.f.calls)
        self.page.locator("#question").fill("Classify this Baugruppe")
        self.button("chat()", "#composer").click()
        self.page.wait_for_function("!busy")
        # The stale tab gets a visible, localized refusal and no result card.
        self.assertEqual(self.page.locator(".classification-card").count(), 0)
        error = self.page.locator("#chat .message.error").inner_text()
        self.assertIn(self.page.evaluate("t('context.stale_page')"), error)
        self.assertEqual(len(self.f.calls), calls)
        self.assertEqual(w.ACTIVE["state"].root.name, session_b)
        self.assertEqual(w.ACTIVE["state"].data["history"], [])
        # The current tab still classifies its own BG_B.
        self.page = other
        try:
            self.ask("Classify this Baugruppe")
        finally:
            self.page = first_page
        self.assertIn("FIXTURE_BG_B", json.dumps(self.f.calls[-1]))
        self.assertNotIn("FIXTURE_BG_A", json.dumps(self.f.calls[-1]))
        # Reloading re-binds the stale tab to the current session instead of the old view.
        self.page.reload()
        self.page.wait_for_function("(s)=>lastStatusSnapshot?.session_name===s", arg=session_b)


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
