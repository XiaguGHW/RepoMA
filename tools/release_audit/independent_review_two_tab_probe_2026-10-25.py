"""Independent review probe F-04: a stale tab's chat runs in another tab's session/BG.

Run from local_llm_chat_bot/: python ../tools/release_audit/independent_review_two_tab_probe_2026-10-25.py OUTDIR
Synthetic fixture + loopback mock only. Prints JSON evidence and writes two screenshots.
"""
import json
from pathlib import Path
import socket
import sys
import threading
import time

APP = Path(__file__).resolve().parents[2] / "local_llm_chat_bot"
sys.path.insert(0, str(APP)); sys.path.insert(0, str(APP / "tests"))
import uvicorn  # noqa: E402
import chat_workbench as w  # noqa: E402
from fixture_support import FixtureEnvironment  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")


def open_workspace(page, f):
    page.wait_for_function('typeof materialDraftDirty !== "undefined"')
    page.select_option("#language", "en"); page.evaluate("languageSave")
    page.locator("#workspaceshortcut").click()
    page.locator("#contextworkspacepath").fill(str(f.workspace))
    page.locator('button[onclick="contextOpenWorkspace()"]').click()
    page.wait_for_function("document.getElementById('setupmsg').textContent === t('workspace.opened')")
    page.evaluate("closeContextDrawer()")
    page.select_option("#model", "gemini-2.5-pro")
    page.wait_for_function('lastStatusSnapshot.model === "gemini-2.5-pro"')


def select_bg(page, folder):
    page.evaluate("openContextDrawer('materials')")
    page.locator("#contexttargetpath").fill(str(folder))
    page.evaluate("contextSyncTarget();loadTargetTree()")
    page.wait_for_function("(p)=>lastTargetTreePayload?.tree?.path===p", arg=str(folder))
    page.locator('button[onclick="contextSyncTarget();analyzeTarget()"]').click()
    try:
        page.wait_for_function("(p)=>lastStatusSnapshot.bg_context?.folder===p", arg=str(folder), timeout=8000)
    except Exception:
        print("SELECT_BG_FAILED", page.locator("#contextdrawerbody").inner_text()[-800:], page.evaluate("JSON.stringify(lastStatusSnapshot)")[:600])
        raise
    page.evaluate("closeContextDrawer()")


with FixtureEnvironment() as f:
    sock = socket.socket(); sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(w.app, log_level="error"))
    threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        a = browser.new_page(viewport={"width": 1440, "height": 1000})
        a.on("dialog", lambda d: d.accept("gemini-2.5-pro") if d.type == "prompt" else d.accept())
        a.goto(f"http://127.0.0.1:{port}"); open_workspace(a, f)
        a.evaluate("openContextDrawer('rules')")
        a.locator("#contextcodebookpath").fill(str(f.rules))
        a.locator('button[onclick="contextSyncRule();prepareCodebook()"]').click()
        a.wait_for_function('lastCodebookWorkspaceProfile?.status === "draft"')
        a.evaluate("closeContextDrawer()")
        a.get_by_role("button", name=a.evaluate("t('rulews.lock_action')"), exact=True).click()
        a.wait_for_function('lastCodebookWorkspaceProfile?.status === "locked"')
        a.locator('button[onclick="leaveCodebookWorkspace()"]').click()
        select_bg(a, f.bg_a)
        session_a = a.evaluate("lastStatusSnapshot.session_name")
        # Second tab: new chat session bound to BG_B.
        b = browser.new_page(viewport={"width": 1440, "height": 1000})
        b.on("dialog", lambda d: d.accept("gemini-2.5-pro") if d.type == "prompt" else d.accept())
        b.goto(f"http://127.0.0.1:{port}"); open_workspace(b, f)
        b.evaluate("newSession()"); b.wait_for_function("(s)=>lastStatusSnapshot?.session_name && lastStatusSnapshot.session_name!==s", arg=session_a)
        select_bg(b, f.bg_b)
        session_b = b.evaluate("lastStatusSnapshot.session_name")
        time.sleep(2)  # give tab A any chance to poll/refresh its own state
        before = len(f.calls)
        a.locator("#question").fill("Classify this Baugruppe")
        a.locator('#composer button[onclick="chat()"]').click()
        a.wait_for_function("!busy && document.getElementById('question').value === ''", timeout=20000)
        sent = json.dumps(f.calls[before:], ensure_ascii=False)
        evidence = {
            "tab_a_session_shown": a.evaluate("lastStatusSnapshot.session_name"),
            "tab_a_bg_folder_shown_before_reply": str(f.bg_a),
            "tab_b_session": session_b,
            "server_active_session": w.ACTIVE["state"].root.name,
            "prompt_contains_BG_A_marker": "FIXTURE_BG_A" in sent,
            "prompt_contains_BG_B_marker": "FIXTURE_BG_B" in sent,
            "tab_a_shows_classification_card": a.locator(".classification-card").count(),
            "tab_a_errors": a.locator("#chat .message.error").count(),
            "answer_saved_in_session": w.ACTIVE["state"].root.name,
            "tab_a_error_text": a.locator("#chat .message.error").all_inner_texts(),
            "tab_a_chat_text": a.locator("#chat").inner_text()[-600:],
            "session_b_history": [t["content"][:80] for t in w.ACTIVE["state"].data["history"]],
            "session_a_history_len": len(w.ProjectState(w.app_state_home(), f.workspace, session_a).data["history"]),
        }
        a.screenshot(path=str(out / "two_tab_stale_tab_a.png"))
        print(json.dumps(evidence, ensure_ascii=False, indent=1))
        browser.close()
    server.should_exit = True
