"""Independent review probe: CJK UI text left in an English UI (synthetic data only).

Run from local_llm_chat_bot/:  python ../tools/release_audit/independent_review_browser_probe_2026-10-25.py
Prints every visible text node / title / placeholder containing Han characters after
each step, excluding text that contains the synthetic fixture path (its temp directory
name deliberately contains Chinese) and the Chinese language option itself.
This is a diagnostic probe, not an acceptance test.
"""
import json
from pathlib import Path
import socket
import sys
import threading
import time

APP = Path(__file__).resolve().parents[2] / "local_llm_chat_bot"
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "tests"))
import uvicorn  # noqa: E402
import chat_workbench as w  # noqa: E402
from fixture_support import FixtureEnvironment  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

COLLECT = r"""(root) => {
  const han = /[㐀-鿿]/;
  const out = [];
  const visible = el => { const s = getComputedStyle(el); const r = el.getBoundingClientRect();
    return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0
      && r.right > 0 && r.bottom > 0 && r.left < innerWidth && r.top < innerHeight; };
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) { const n = walker.currentNode; const t = n.textContent.trim();
    if (t && han.test(t) && n.parentElement && visible(n.parentElement) && !t.includes(root) && !t.includes('Workbench 发布') && t !== '中文')
      out.push({where: (n.parentElement.id || n.parentElement.className || n.parentElement.tagName), text: t.slice(0, 120)}); }
  for (const el of document.querySelectorAll('[title],[placeholder],[aria-label]'))
    for (const a of ['title', 'placeholder', 'aria-label']) { const v = el.getAttribute(a);
      if (v && han.test(v) && !v.includes(root) && visible(el)) out.push({where: a + '@' + (el.id || el.className || el.tagName), text: v.slice(0, 120)}); }
  return out; }"""


def main():
    with FixtureEnvironment() as f:
        sock = socket.socket(); sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(w.app, log_level="error"))
        threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True).start()
        while not server.started:
            time.sleep(0.05)
        findings = {}
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on("dialog", lambda d: d.accept("gemini-2.5-flash") if d.type == "prompt" else d.accept())
            page.goto(f"http://127.0.0.1:{port}")
            page.wait_for_function('typeof materialDraftDirty !== "undefined"')
            page.select_option("#language", "en"); page.evaluate("languageSave")
            page.wait_for_function("document.documentElement.lang==='en'")

            def snap(step):
                time.sleep(0.4)
                for item in page.evaluate(COLLECT, str(f.root)):
                    findings.setdefault(json.dumps(item, ensure_ascii=False), []).append(step)

            snap("initial EN, no workspace")
            page.locator("#workspaceshortcut").click()
            page.locator("#contextworkspacepath").fill(str(f.workspace))
            page.locator('button[onclick="contextOpenWorkspace()"]').click()
            page.wait_for_function("document.getElementById('setupmsg').textContent === t('workspace.opened')")
            snap("workspace opened (drawer)")
            page.evaluate("closeContextDrawer()")
            page.evaluate("openContextDrawer('rules')")
            page.locator("#contextcodebookpath").fill(str(f.rules))
            page.locator('button[onclick="contextSyncRule();prepareCodebook()"]').click()
            page.wait_for_function('lastCodebookWorkspaceProfile?.status === "draft"')
            snap("rules prepared")
            page.evaluate("closeContextDrawer()")
            page.get_by_role("button", name=page.evaluate("t('rulews.lock_action')"), exact=True).click()
            page.wait_for_function('lastCodebookWorkspaceProfile?.status === "locked"')
            snap("rules locked")
            page.locator('button[onclick="leaveCodebookWorkspace()"]').click()
            page.evaluate("openContextDrawer('materials')")
            page.locator("#contexttargetpath").fill(str(f.bg_a))
            page.evaluate("contextSyncTarget();loadTargetTree()")
            snap("tree loading (immediate)")
            page.wait_for_function("(p)=>lastTargetTreePayload?.tree?.path===p", arg=str(f.bg_a))
            snap("tree loaded")
            page.locator('button[onclick="contextSyncTarget();analyzeTarget()"]').click()
            page.wait_for_function("(p)=>lastStatusSnapshot.bg_context?.folder===p", arg=str(f.bg_a))
            snap("materials confirmed")
            page.evaluate("closeContextDrawer()")
            page.locator("#question").fill("Classify this Baugruppe")
            page.locator('#composer button[onclick="chat()"]').click()
            page.wait_for_function("!busy && document.getElementById('question').value === ''")
            snap("classified")
            page.evaluate("openScanReport();setTimeout(loadCacheAudit,80)")
            time.sleep(1)
            snap("scan report + cache audit")
            page.evaluate("closeScanReport && closeScanReport()")
            page.evaluate("openCompareDrawer()")
            for _ in range(5):
                page.evaluate("addCompareModel()")
            snap("compare drawer, five add clicks")
            page.evaluate("runDiagnostics()")
            time.sleep(1)
            snap("diagnostics")
            for kind in ["workspace", "rules", "materials", "scan", "audit"]:
                page.evaluate("(k)=>openContextDrawer(k)", kind)
                snap("drawer " + kind + " open")
                page.evaluate("closeContextDrawer()")
            page.evaluate("newSession()")
            time.sleep(1)
            snap("new session")
            browser.close()
        server.should_exit = True
    print(json.dumps([{**json.loads(item), "steps": steps} for item, steps in findings.items()],
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
