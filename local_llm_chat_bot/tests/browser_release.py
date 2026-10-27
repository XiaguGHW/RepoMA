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

    def accept_confirm_if_shown(self):
        """Re-confirming materials with an existing conversation asks first."""
        try:
            self.page.locator("#appconfirmok").click(timeout=1500)
        except Exception:
            pass

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

    def prepare_rules(self, path=None, model="gemini-2.5-pro"):
        self.open_drawer("rules")
        self.page.locator("#contextcodebookpath").fill(str(path or self.f.rules))
        # The rule-parsing model is an in-page field (no native prompt()).
        self.page.locator("#rulemodel").fill(model)
        self.button("contextSyncRule();prepareCodebook()").click()
        self.page.wait_for_function('lastCodebookWorkspaceProfile?.status === "draft"')
        self.close_drawer()

    def lock_rules(self):
        label = self.page.evaluate("t('rulews.lock_action')")
        self.page.get_by_role("button", name=label, exact=True).click()
        # Locking asks for confirmation in the page itself, not a browser dialog.
        self.page.locator("#appconfirmok").click()
        self.page.wait_for_function('lastCodebookWorkspaceProfile?.status === "locked"')

    def select_bg(self, folder):
        self.open_drawer("materials")
        self.page.locator("#contexttargetpath").fill(str(folder))
        # The folder tree loads by itself once the path is entered.
        self.page.locator("#contexttargetpath").press("Enter")
        self.page.wait_for_function(
            "(path)=>lastTargetTreePayload?.tree?.path===path", arg=str(folder)
        )
        self.page.locator("input.tree-file").first.wait_for(state="attached")
        self.page.locator("#confirmmaterials").click()
        self.accept_confirm_if_shown()
        self.page.wait_for_function(
            "(path)=>lastStatusSnapshot.bg_context?.folder===path", arg=str(folder)
        )
        # Confirming opens the scan report above the drawer; close it first.
        self.page.wait_for_function("$('scanbackdrop').classList.contains('open')")
        self.page.evaluate("closeScanReport()")
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
        # Locked rules: path, file picker and parser model are read-only until
        # "Replace"; preparing again only reports that the rules are ready.
        for control in ["#contextcodebookpath", "#rulefilepick", "#rulemodel", "#rulemodelrecommended"]:
            self.assertTrue(self.page.locator(control).is_disabled(), control)
        self.assertEqual(self.page.input_value("#contextcodebookpath"), str(self.f.rules))
        self.assertIn(
            str(self.f.rules), self.page.locator("#codebookstatus").inner_text()
        )
        calls = len(self.f.calls)
        self.page.locator("#ruleprepare").click()
        self.assertIn(self.f.rules.name, self.page.locator("#contextrulemsg").inner_text())
        self.assertEqual(len(self.f.calls), calls)
        self.assertTrue(self.page.locator("#rulereplace").is_enabled())
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
            self.page.locator("#confirmmaterials").click()
            self.accept_confirm_if_shown()
        self.assertEqual(response.value.status, 200)
        self.page.wait_for_function("!document.getElementById('question').disabled")
        self.page.wait_for_function("$('scanbackdrop').classList.contains('open')")
        self.page.evaluate("closeScanReport()")
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

    def test_auto_mode_and_nonpaged_rule_references(self):
        self.language("en")
        self.page.select_option("#model", "gemini-2.5-pro")
        self.page.wait_for_function('lastStatusSnapshot.model === "gemini-2.5-pro"')
        self.prepare_rules()
        self.lock_rules()
        self.button("leaveCodebookWorkspace()").click()
        self.select_bg(self.f.bg_a)
        # There is no answer-mode switch; the server decides per question.
        self.assertEqual(self.page.locator("#answermodegroup").count(), 0)
        self.ask("Classify this Baugruppe")
        card = self.page.locator(".classification-card").filter(
            has=self.page.get_by_role(
                "heading", name="Classification result (validated)", exact=True
            )
        )
        self.assertIn("Section/chunk references", card.inner_text())
        self.assertIn(self.f.rules.name, card.inner_text())
        self.language("de")
        with self.page.expect_response(
            lambda response: response.url.endswith("/api/chat/stream")
        ) as response:
            self.ask("Erläutere die Motorfunktion")
        payload = response.value.request.post_data_json
        self.assertNotIn("require_classification", payload)
        self.assertEqual(payload["focus_source_id"], "")
        # A follow-up explanation adds no second classification card.
        self.assertEqual(self.page.locator('.classification-card').filter(
            has=self.page.get_by_role('heading', name=self.page.evaluate("t('classification.title')"), exact=True)
        ).count(), 1)
        self.assertIn(self.page.evaluate("t('scope.kind_answer')"),
                      self.page.locator(".scope-tag").last.inner_text())
        self.assertNotIn(
            "classification",
            self.page.locator("#chat .message.error").all_text_contents(),
        )
        self.select_bg(self.f.bg_b)
        self.assertEqual(self.page.evaluate("scopeFocusId"), "")

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
                self.page.locator("#contexttargetpath").press("Enter")
                self.page.locator("input.tree-file").first.wait_for(state="attached")
                # Expand/collapse the actual tree and change a checkbox, then restore it.
                toggle = self.page.locator("#targettree summary").first
                if toggle.count():
                    toggle.click()
                    toggle.click()
                checkbox = self.page.locator("input.tree-file").first
                checkbox.uncheck()
                checkbox.check()
                confirm = self.page.locator("#confirmmaterials")
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
                self.page.wait_for_function("$('scanbackdrop').classList.contains('open')")
                self.page.evaluate("closeScanReport()")
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

    def visible_han_text(self):
        """Visible UI text with Han characters, excluding user data such as fixture paths."""
        return self.page.evaluate("""(root) => {
            const han=/[\\u3400-\\u9fff]/, found=[];
            const visible=el=>el.checkVisibility({opacityProperty:true, visibilityProperty:true});
            const walker=document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            for(let node;node=walker.nextNode();){
              const text=node.nodeValue.trim(), parent=node.parentElement;
              if(!text||!han.test(text)||!parent||!visible(parent)) continue;
              if(parent.closest('script,style,option,input,textarea,select')) continue;
              if(text.includes(root)||text.includes('Workbench 发布')) continue;  // synthetic path data
              found.push((parent.id||parent.className||parent.tagName)+': '+text.slice(0,120));
            }
            for(const el of document.querySelectorAll('[title],[placeholder],[aria-label]'))
              for(const name of ['title','placeholder','aria-label']){
                const value=el.getAttribute(name);
                if(value&&han.test(value)&&!value.includes(root)&&visible(el)) found.push(name+'@'+(el.id||el.className)+': '+value);
              }
            return found;
        }""", str(self.f.root))

    def test_full_workflow_and_diagnostics_have_no_chinese_ui_in_english_or_german(self):
        """F-08 follow-up: scan after rules, materials, classification, scan report and diagnostics."""
        self.page.select_option("#model", "gemini-2.5-pro")
        self.page.wait_for_function('lastStatusSnapshot.model === "gemini-2.5-pro"')
        for index, language in enumerate(["en", "de"]):
            with self.subTest(language=language):
                self.language(language)
                if index == 0:
                    self.prepare_rules()
                    self.lock_rules()
                    self.button("leaveCodebookWorkspace()").click()
                    self.select_bg(self.f.bg_a)
                self.ask("Classify this Baugruppe")
                self.assertEqual(self.visible_han_text(), [], "after classification")
                self.open_drawer("rules")
                self.assertEqual(self.visible_han_text(), [], "rules drawer")
                self.close_drawer()
                self.open_drawer("materials")
                self.page.locator("input.tree-file").first.wait_for(state="attached")
                self.assertEqual(self.visible_han_text(), [], "materials drawer")
                self.close_drawer()
                self.page.evaluate("openContextDrawer('audit')")
                self.page.wait_for_function(
                    "document.getElementById('diagnosticsresult')?.textContent !== t('audit.diagnostics_loading')")
                self.page.locator("#diagnosticsresult .card").first.wait_for()
                self.assertEqual(self.visible_han_text(), [], "diagnostics drawer")
                self.close_drawer()
                self.page.evaluate("openAuditDetail()")
                self.page.wait_for_timeout(400)
                self.assertEqual(self.visible_han_text(), [], "scan report and cache audit")
                self.page.evaluate("closeScanReport()")

    def test_english_and_german_page_scan_has_no_chinese_ui_residue(self):
        """F-08: dynamic workflow, scan report, diagnostics and new chat rerender."""
        for language in ["en", "de"]:
            with self.subTest(language=language):
                self.language(language)
                self.page.evaluate("""() => {
                    ensureMaterialFlow();
                    renderScanReport({sources: 0, files: [], skipped_count: 0, skipped: []});
                    openScanReport();
                    while(compareSlots.length < 4) addCompareModel();
                    addCompareModel();
                    openContextDrawer('workspace');
                }""")
                self.assertEqual(
                    self.page.locator('#coveragestatus').inner_text(),
                    self.page.evaluate("t('coverage.auto_hint')"),
                )
                self.assertEqual(
                    self.page.locator('#comparestatus').inner_text(),
                    self.page.evaluate("t('compare.maximum')"),
                )
                self.assertEqual(
                    self.page.locator('#leftsplitter').get_attribute('aria-label'),
                    self.page.evaluate("t('layout.left_panel_width')"),
                )
                self.assertEqual(
                    self.page.locator('.context-drawer').get_attribute('aria-label'),
                    self.page.evaluate("t('context.detail')"),
                )
                self.assertEqual(
                    self.page.locator('.scan-drawer').get_attribute('aria-label'),
                    self.page.evaluate("t('scan.report.title')"),
                )
                self.close_drawer()
                self.page.evaluate('closeScanReport()')
                self.page.locator('#newsessionbutton').click()
                self.page.wait_for_function(
                    "[...document.querySelectorAll('.session-title')].some(node => node.textContent === t('session.new_title'))"
                )
                foreign = self.page.evaluate("""() => {
                    const forbidden=/[\\u4e00-\\u9fff]/;
                    const walker=document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                    const found=[];
                    for(let node;node=walker.nextNode();){
                      const text=node.nodeValue.trim(), parent=node.parentElement;
                      if(text && forbidden.test(text) && !parent.closest('script,style,option,input,textarea,select,#workspaceshortcut')) found.push(text);
                    }
                    return found;
                }""")
                self.assertEqual(foreign, [], foreign)
                self.close_drawer() if self.page.locator('#contextbackdrop').evaluate("n => n.classList.contains('open')") else None

    def test_long_invalid_draft_keeps_selection_scroll_errors_and_cancel_guard(self):
        self.prepare_rules()
        original = self.f.rules.read_bytes()
        self.button('editCodebookDraft()').click()
        raw = '{\n' + '\n'.join(f'  "line{i}": "原文 Regel {i}",' for i in range(180))
        # This deliberately large synthetic draft exercises preservation of
        # editing state, rather than an eight-second text-entry performance SLA.
        self.page.locator('#ruleeditor').fill(raw, timeout=20_000)
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
            self.page.locator('#contexttargetpath').press('Enter')
            self.page.locator('#treestatus .error').wait_for()
            self.assertIn(detail, self.page.locator('#treestatus').text_content())
            self.page.screenshot(path=str(OUTPUT / f'de-long-error-{width}.png'))
            box = self.page.locator('.context-drawer').bounding_box()
            self.assertGreaterEqual(box['x'], -1)
            self.assertLessEqual(box['x'] + box['width'], width + 1)
            self.page.unroute('**/api/target-tree?*')
            self.page.locator('#contexttargetpath').fill(str(self.f.bg_a))
            self.page.locator('#contexttargetpath').press('Enter')
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


    # ---- Classification-rule (Codebook) preparation ---------------------
    def make_pdf(self, name, pages):
        import fitz
        path = self.f.root / name
        with fitz.open() as pdf:
            for text in pages:
                pdf.new_page().insert_textbox(fitz.Rect(40, 40, 560, 800), text, fontsize=7)
            pdf.save(path)
        return path

    def record_dialogs(self):
        dialogs = []
        self.page.on("dialog", lambda dialog: dialogs.append(dialog.type))
        return dialogs

    def start_rules(self, path, model):
        self.open_drawer("rules")
        self.page.locator("#contextcodebookpath").fill(str(path))
        self.page.locator("#rulemodel").fill(model)
        self.button("contextSyncRule();prepareCodebook()").click()

    def card(self):
        return self.page.locator("#context-rule-summary").inner_text()

    def test_rule_preparation_shows_live_progress_without_native_dialogs_and_restores(self):
        self.language("en")
        dialogs = self.record_dialogs()
        path = self.make_pdf("Codebook 3 pages.pdf", ["Rotationseinheit: rotation-1.", "Gantry.", "Greifer."])
        gate = threading.Event()
        self.addCleanup(gate.set)

        def slow(response, prompt, system):
            if "transcribe exactly one" in system:
                gate.wait(.7)
            return response
        self.f.response_transform = slow
        self.open_drawer("rules")
        self.page.locator("#contextcodebookpath").fill(str(path))
        self.page.locator("#rulemodel").fill("gemini-2.5-pro")
        self.assertEqual(self.page.locator("#rulemodelhint").inner_text(), "This run will use: gemini-2.5-pro")
        self.button("contextSyncRule();prepareCodebook()").click()
        self.page.wait_for_function("document.getElementById('rulejobpanel')?.innerText.includes('Parsing page')")
        panel = self.page.locator("#rulejobpanel").inner_text()
        for text in ["Preparing", "gemini-2.5-pro", "Codebook 3 pages.pdf", "PDF", " of 3"]:
            self.assertIn(text, panel)
        self.assertNotIn("%", panel)  # no invented percentage
        # Switching the GUI language during the job is immediate (the language
        # save must not wait for the job's lock) and redraws the live panel.
        for language, fragment in [("de", "Seite"), ("zh", "页"), ("en", "Parsing page")]:
            started = time.monotonic()
            self.language(language)
            self.assertLess(time.monotonic() - started, 3, language)
            self.page.wait_for_function("(f)=>document.getElementById('rulejobpanel').innerText.includes(f)", arg=fragment)
            self.assertEqual(self.page.evaluate("lastCodebookTask.state"), "running")
        for selector in ["#ruleprepare", "#rulefilepick", "#contextcodebookpath", "#rulemodel", "#ruleview", "#rulereplace"]:
            self.assertTrue(self.page.locator(selector).is_disabled(), selector)
        self.close_drawer()
        self.page.wait_for_function("/^Preparing: page [123] of 3$/.test(document.getElementById('context-rule-summary').innerText)")
        # A reload while the job runs resumes the same server-side status.
        self.page.reload()
        self.page.wait_for_function("lastCodebookTask && ['running','succeeded'].includes(lastCodebookTask.state)")
        self.assertNotIn(self.page.evaluate("t('error.busy')"), self.page.locator("body").inner_text())
        gate.set()
        self.page.wait_for_function("lastCodebookTask?.state === 'succeeded'", timeout=20000)
        self.page.wait_for_function("lastCodebookProfile?.status === 'draft'")
        self.assertEqual(self.card(), "Draft prepared, awaiting confirmation and lock · Codebook 3 pages.pdf")
        self.open_drawer("rules")
        panel = self.page.locator("#rulejobpanel").inner_text()
        for text in ["Prepared successfully", str(path), "PDF", "gemini-2.5-pro",
                     "Draft prepared, awaiting confirmation and lock"]:
            self.assertIn(text, panel)
        self.assertEqual(self.page.locator("#rulejobpanel dt:text-is('Pages') + dd").inner_text(), "3")
        self.assertFalse(self.page.locator("#ruleprepare").is_disabled())
        self.page.locator("#rulejobview").click()
        self.page.wait_for_function('lastCodebookWorkspaceProfile?.status === "draft"')
        self.close_drawer()
        self.lock_rules()
        self.assertEqual(self.card(), "Locked and in use for classification · Codebook 3 pages.pdf")
        # A second reload shows the last final state.
        self.page.reload()
        self.page.wait_for_function("lastCodebookTask?.state === 'succeeded' && lastCodebookProfile?.status === 'locked'")
        self.assertEqual(dialogs, [])

    def test_rule_page_three_max_tokens_is_explained_and_old_rules_stay_in_effect(self):
        self.language("en")
        self.page.context.grant_permissions(["clipboard-read", "clipboard-write"])
        self.prepare_rules()
        self.lock_rules()
        self.button("leaveCodebookWorkspace()").click()
        dialogs = self.record_dialogs()
        long_text = "Page three table: " + " ".join(f"Rule{index} Rotationseinheit Drehung" for index in range(260))
        path = self.make_pdf("Codebook_Baugruppenklassifikation_v2_3.pdf", ["Rotationseinheit.", "Gantry.", long_text])

        def page_three(response, prompt, system):
            if "Codebook page 3 of 3" in prompt:
                response["candidates"][0]["finishReason"] = "MAX_TOKENS"
            return response
        self.f.response_transform = page_three
        self.start_rules(path, "claude-haiku-5-5")
        self.page.wait_for_function("lastCodebookTask?.state === 'failed'", timeout=20000)
        panel = self.page.locator("#rulejobpanel").inner_text()
        for text in ["Preparation failed", "Page 3 is too long", "after 2 attempts", "Parsing the rules",
                     "This failure did not change the existing rules.", "claude-haiku-5-5"]:
            self.assertIn(text, panel)
        self.assertTrue(self.page.locator("#rulejobretry").is_enabled())
        self.assertTrue(self.page.locator("#ruleprepare").is_enabled())
        self.assertNotIn("incomplete Claude response", panel.split(self.page.evaluate("t('rulejob.details.title')"))[0])
        self.page.locator("#rulejobdetails summary").click()
        self.assertIn("incomplete Claude response (max_tokens)", self.page.locator("#rulejobdiagnostics").inner_text())
        self.assertIn("retrying in smaller parts", self.page.locator(".rulejob-log").inner_text())
        self.page.locator("button[onclick='copyCodebookDiagnostics()']").click()
        self.page.wait_for_function("document.getElementById('rulejobcopymsg').innerText.length > 0")
        self.assertEqual(self.page.locator("#rulejobcopymsg").inner_text(), "Copied")
        self.assertIn("max_tokens", self.page.evaluate("navigator.clipboard.readText()"))
        self.close_drawer()
        expected = ("Preparation failed: Page 3: output limit reached\n"
                    f"Rules in effect: {self.f.rules.name} (Locked and in use for classification)")
        self.assertEqual(self.card(), expected)
        clipped = self.page.eval_on_selector("#context-rule-summary", "n=>n.scrollHeight>n.clientHeight+1||getComputedStyle(n).webkitLineClamp!=='none'")
        self.assertFalse(clipped, "rule card text is clipped")
        for language, fragment in [("zh", "第 3 页输出长度不足"), ("de", "Seite 3: Ausgabelimit erreicht")]:
            self.language(language)
            self.assertIn(fragment, self.card())
            if language == "de":
                self.assertNotRegex(self.card(), r"[一-鿿]")
        self.open_drawer("rules")
        self.assertIn("Seite 3 ist zu lang", self.page.locator("#rulejobpanel").inner_text())
        self.language("zh")
        self.assertIn("第 3 页内容过长，已尝试 4 次仍无法完成", self.page.locator("#rulejobpanel").inner_text())
        self.language("en")
        self.close_drawer()
        # The previously locked rules still classify.
        self.f.response_transform = None
        self.select_bg(self.f.bg_a)
        self.ask("Classify this Baugruppe")
        self.assertIn("Rotationseinheit", self.page.locator(".classification-card").first.inner_text())
        # Retry from the failure panel.
        self.open_drawer("rules")
        self.page.locator("#rulejobretry").click()
        self.page.wait_for_function("lastCodebookTask?.state === 'succeeded'", timeout=20000)
        self.assertEqual(dialogs, [])

    def test_rule_model_validation_and_scope_bar_are_in_page_controls(self):
        self.language("en")
        dialogs = self.record_dialogs()
        self.assertEqual(self.page.locator("#answermodegroup").count(), 0)
        # Without confirmed materials the scope bar stays hidden.
        self.assertFalse(self.page.locator("#scopebar").is_visible())
        calls = len(self.f.calls)
        self.open_drawer("rules")
        self.page.locator("#contextcodebookpath").fill(str(self.f.rules))
        self.page.locator("#rulemodel").fill("not a model")
        self.assertIn("is invalid", self.page.locator("#rulemodelhint").inner_text())
        self.button("contextSyncRule();prepareCodebook()").click()
        self.assertIn("is invalid", self.page.locator("#contextrulemsg").inner_text())
        self.page.locator("#rulemodel").fill("")
        self.button("contextSyncRule();prepareCodebook()").click()
        self.assertEqual(self.page.locator("#contextrulemsg").inner_text(), "Enter a rule-parsing model ID.")
        self.assertIsNone(self.page.evaluate("lastCodebookTask"))
        self.assertEqual(len(self.f.calls), calls)
        self.page.locator("#rulemodelrecommended").click()
        self.assertEqual(self.page.input_value("#rulemodel"), "claude-haiku-5-5")
        # A refused start (another model task is active) is explained in the page
        # and leaves no running state or disabled controls behind.
        w.MODEL_WORK_IN_PROGRESS.set()
        try:
            self.button("contextSyncRule();prepareCodebook()").click()
            self.page.wait_for_function("document.getElementById('contextrulemsg').innerText.includes(t('error.busy'))")
        finally:
            w.MODEL_WORK_IN_PROGRESS.clear()
        self.assertIsNone(self.page.evaluate("lastCodebookTask"))
        self.assertTrue(self.page.locator("#ruleprepare").is_enabled())
        self.assertTrue(self.page.locator("#cancelchat").is_disabled())
        self.close_drawer()
        self.prepare_rules()
        self.lock_rules()
        self.button("leaveCodebookWorkspace()").click()
        self.select_bg(self.f.bg_a)
        # One confirmed file: nothing to choose, so the bar stays hidden.
        self.assertFalse(self.page.locator("#scopebar").is_visible())
        self.assertEqual(dialogs, [])

    def test_txt_rules_prepare_and_show_text_block_references(self):
        self.language("de")
        path = self.f.root / "Regeln ü.txt"
        path.write_text("Rotationseinheit: Die Hauptfunktion ist die Drehung. Regel rotation-1.\n\nGrenzfall: Größe ist kein Kriterium.",
                        encoding="utf-16")
        self.prepare_rules(path=path)
        workspace = self.page.locator(".codebook-workspace").inner_text()
        self.assertIn(self.page.evaluate("t('rulews.evidence_blocks')"), workspace)
        self.assertNotIn(self.page.evaluate("t('rulews.evidence_pages')"), workspace)
        self.assertIn("OCR: für TXT nicht anwendbar", workspace)
        self.open_drawer("rules")
        self.assertIn("PDF / DOCX / TXT", self.page.locator("#contextdrawerbody").inner_text())
        panel = self.page.locator("#rulejobpanel").inner_text()
        for text in ["Erfolgreich vorbereitet", "TXT", "utf-16", self.page.evaluate("t('rulejob.panel.blocks')")]:
            self.assertIn(text, panel)
        self.assertNotRegex(panel.replace(str(path.parent), ""), r"[一-鿿]")  # the temp folder name is CJK

    def test_rule_preparation_stop_closes_job_and_reenables_controls(self):
        self.language("en")
        from docx import Document
        document = Document()
        for index in range(9):
            document.add_paragraph(f"Rule section {index}: " + "detail " * 520)
        path = self.f.root / "Long rules.docx"
        document.save(path)
        gate = threading.Event()
        self.addCleanup(gate.set)
        self.f.response_transform = lambda response, prompt, system: (gate.wait(.5), response)[1]
        self.start_rules(path, "gemini-2.5-pro")
        self.page.wait_for_function("document.getElementById('rulejobpanel')?.innerText.includes('Parsing text blocks')")
        self.assertRegex(self.page.locator("#rulejobpanel").inner_text(), r"group \d of \d")
        self.page.locator("#rulejobstop").click()
        self.page.wait_for_function("lastCodebookTask?.state === 'cancelled'", timeout=15000)
        panel = self.page.locator("#rulejobpanel").inner_text()
        self.assertIn("Rule preparation was cancelled; no rules were saved.", panel)
        self.assertTrue(self.page.locator("#ruleprepare").is_enabled())
        self.assertTrue(self.page.locator("#cancelchat").is_disabled())
        self.close_drawer()
        self.assertEqual(self.card(), "Rule preparation cancelled\nNo locked rules are available for classification")
        self.assertEqual(w.load_codebook_profile(), {})
        self.assertFalse(w.MODEL_WORK_IN_PROGRESS.is_set())

    def test_malformed_page_note_is_flagged_in_the_rules_workspace(self):
        self.language("en")
        path = self.make_pdf("Codebook flagged.pdf", ["Rotationseinheit: rotation-1.", "Gantry."])

        def page_two_malformed(response, prompt, system):
            if "transcribe exactly one" in system and "Codebook page 2 of 2" in prompt:
                response["candidates"][0]["content"]["parts"][0]["text"] = '{"source":"page 2","definitions":["a "b""]}'
            return response
        self.f.response_transform = page_two_malformed
        self.prepare_rules(path=path)
        expected = self.page.evaluate("t('rulews.unparsed_units',{units:t('rulejob.unit.page',{number:2})})")
        self.assertIn(expected, self.page.locator(".codebook-workspace").inner_text())
        self.language("de")
        self.assertIn("Seite 2", self.page.locator(".codebook-workspace .card.error").inner_text())

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
