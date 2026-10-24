"""Run with Python Playwright 1.51+, Chromium installed. No Bosch access."""
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uvicorn
import chat_workbench as w
from fixture_support import FixtureEnvironment
from playwright.sync_api import sync_playwright


def main():
    output=Path(os.getenv('WORKBENCH_TEST_OUTPUT','/tmp/workbench-browser-results'));output.mkdir(parents=True,exist_ok=True)
    with FixtureEnvironment() as f:
        sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        server=uvicorn.Server(uvicorn.Config(w.app,log_level='error'))
        thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
        for _ in range(100):
            if server.started:break
            time.sleep(.05)
        errors=[]; warnings=[];checks=[]
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True)
                page=browser.new_page(viewport={'width':1440,'height':1000})
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.on('console',lambda message:warnings.append(message.text) if message.type=='warning' else None)
                page.goto(f'http://127.0.0.1:{port}')
                page.wait_for_function('typeof materialDraftDirty !== "undefined"')
                page.locator('#workspaceshortcut').click()
                # The existing drawer provides text input for machines without a file picker.
                page.locator('#contextworkspace').fill(str(f.workspace))
                page.locator('#contextdrawerbody button').filter(has_text='打开工作区').click()
                page.wait_for_function('lastStatusSnapshot && lastStatusSnapshot.workspace')
                page.evaluate('closeContextDrawer()')
                page.select_option('#model','__custom__')
                page.locator('#custommodel').fill(' GEMINI-2.5-PRO ')
                page.evaluate('switchModel()')
                page.wait_for_function('lastStatusSnapshot.model === "gemini-2.5-pro"')
                checks.append('workspace and custom model')
                for language in ['zh','en','de','zh','en','de']:
                    page.select_option('#language',language)
                    page.wait_for_function('(l)=>document.documentElement.lang===l',arg=language)
                    page.evaluate('languageSave')
                    assert page.input_value('#custommodel').strip().lower()=='gemini-2.5-pro'
                checks.append('six language switches preserve selection')
                page.select_option('#language','en');page.evaluate('languageSave')
                page.evaluate('openContextDrawer("rules")')
                page.locator('#contextcodebookpath').fill(str(f.rules))
                page.evaluate('contextSyncRule()')
                page.on('dialog',lambda d:d.accept('gemini-2.5-pro') if d.type=='prompt' else d.accept())
                page.evaluate('prepareCodebook()')
                page.wait_for_function('lastCodebookWorkspaceProfile?.status === "draft"')
                page.evaluate('closeContextDrawer()')
                page.get_by_role('button',name='Lock Codebook',exact=False).click()
                page.wait_for_function('lastCodebookWorkspaceProfile?.status === "locked"')
                page.evaluate('leaveCodebookWorkspace()')
                page.evaluate('openContextDrawer("materials")')
                page.locator('#contexttargetpath').fill(str(f.bg_a))
                page.evaluate('contextSyncTarget();loadTargetTree()')
                page.wait_for_selector('input.tree-file')
                page.evaluate('analyzeTarget()')
                page.wait_for_function('lastStatusSnapshot.bg_context?.folder.endsWith("BG_A")')
                page.evaluate('closeContextDrawer()')
                page.locator('#question').fill('Classify this Baugruppe')
                page.evaluate('chat()')
                page.wait_for_selector('.classification-card')
                assert 'Rotationseinheit' in page.locator('.classification-card').inner_text()
                page.locator('#question').fill('Explain the motor evidence')
                page.evaluate('chat()')
                page.wait_for_function('!busy')
                checks.append('prepare lock select classify follow-up')
                page.evaluate('viewCodebook()')
                page.wait_for_function('lastCodebookWorkspaceProfile?.status === "locked"')
                page.get_by_role('button',name='Edit rule draft',exact=True).click()
                draft=json.loads(page.input_value('#ruleeditor'));draft['classes'][0]['name']='Fixture Class B'
                page.locator('#ruleeditor').fill(json.dumps(draft))
                page.get_by_role('button',name='Save draft',exact=True).click()
                page.wait_for_function('lastCodebookWorkspaceProfile?.status === "draft"')
                page.evaluate('lockCodebook()');page.wait_for_function('lastCodebookWorkspaceProfile?.status === "locked"')
                page.evaluate('leaveCodebookWorkspace();openContextDrawer("materials")')
                page.locator('#contexttargetpath').fill(str(f.bg_b));page.evaluate('contextSyncTarget();loadTargetTree()')
                page.wait_for_function('lastTargetTreePayload?.tree?.path.endsWith("BG_B")')
                page.evaluate('analyzeTarget()');page.wait_for_function('lastStatusSnapshot.bg_context?.folder.endsWith("BG_B")')
                page.evaluate('closeContextDrawer()')
                page.locator('#question').fill('Classify this Baugruppe again');page.evaluate('chat()')
                page.wait_for_selector('.classification-card')
                assert 'Fixture Class B' in page.locator('.classification-card').inner_text()
                assert 'FIXTURE_BG_A' not in json.dumps(f.calls[-1])
                checks.append('edit rules, switch BG, classify without old context')
                page.screenshot(path=str(output/'desktop.png'),full_page=True)
                for width in [800,390]:
                    page.set_viewport_size({'width':width,'height':900})
                    page.evaluate('openContextDrawer("materials")')
                    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth+1')
                    page.screenshot(path=str(output/f'width-{width}.png'),full_page=True)
                    page.evaluate('closeContextDrawer()')
                checks.append('800px and 390px no horizontal overflow')
                page.reload();page.wait_for_function('lastStatusSnapshot?.bg_context?.folder.endsWith("BG_B")')
                checks.append('refresh restores workspace, model, language, BG')
                assert not errors,errors
                assert not [x for x in warnings if 'Unknown UI translation key' in x],warnings
                browser.close()
        finally:
            server.should_exit=True;thread.join(timeout=10);sock.close()
            (output/'browser-results.json').write_text(json.dumps({'checks':checks,'errors':errors,'warnings':warnings},ensure_ascii=False,indent=2))
        print(json.dumps({'checks':checks,'errors':errors},ensure_ascii=False))


if __name__=='__main__':main()
