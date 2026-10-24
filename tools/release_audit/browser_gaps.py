"""Minimal browser probes; reuses the existing fake-data environment."""
import json
import os
import tempfile
import socket
import sys
import threading
import time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / 'local_llm_chat_bot'
sys.path[:0] = [str(APP), str(APP / 'tests')]
import uvicorn
import chat_workbench as w
from fixture_support import FixtureEnvironment
from playwright.sync_api import sync_playwright

out = Path(os.environ['WORKBENCH_TEST_OUTPUT']) if os.getenv('WORKBENCH_TEST_OUTPUT') else Path(tempfile.mkdtemp(prefix='workbench-browser-gaps-'));out.mkdir(parents=True, exist_ok=True)
with FixtureEnvironment() as f:
    sock = socket.socket();sock.bind(('127.0.0.1', 0));port=sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(w.app, log_level='error'))
    thread=threading.Thread(target=server.run, kwargs={'sockets':[sock]}, daemon=True);thread.start()
    for _ in range(100):
        if server.started:break
        time.sleep(.05)
    findings={}
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True, **({'executable_path': os.environ['WORKBENCH_CHROMIUM_EXECUTABLE']} if os.getenv('WORKBENCH_CHROMIUM_EXECUTABLE') else {}), args=['--no-sandbox','--disable-dev-shm-usage','--disable-gpu'])
            page=browser.new_page(viewport={'width':1440,'height':1000})
            page.goto(f'http://127.0.0.1:{port}')
            page.evaluate("async path=>{$('workspace').value=path;setSelectedModel('gemini-2.5-pro');await setup()}",str(f.workspace))
            profile=page.evaluate("async path=>await api('/api/codebook/prepare',{method:'POST',body:JSON.stringify({path})})",str(f.rules))
            page.evaluate('p=>showCodebookWorkspace(p)',profile)
            page.evaluate('editCodebookDraft()')
            page.locator('#ruleeditor').fill('UNSAVED_FIXTURE_DRAFT')
            page.select_option('#language','en');page.evaluate('languageSave')
            findings['unsaved_editor_after_language_change']={'count':page.locator('#ruleeditor').count(), 'marker_present': 'UNSAVED_FIXTURE_DRAFT' in page.locator('#chat').inner_text()}
            page.evaluate('leaveCodebookWorkspace()')
            page.select_option('#language','zh');page.evaluate('languageSave')
            page.evaluate("$('chat').append(classificationCard({label:'Rotationseinheit',confidence:'high',evidence_labels:['fixture'],codebook_rule_ids:['rotation-1'],codebook_rule_pages:[1],bg_evidence_pages:['fixture'],uncertainties:[]}))")
            before=page.locator('.classification-card h3').inner_text()
            page.select_option('#language','en');page.evaluate('languageSave')
            findings['existing_classification_card_language']={'before':before,'after':page.locator('.classification-card h3').inner_text(),'expected':page.evaluate("t('classification.title')")}
            page.evaluate('''$('workspace').value='fixture" onpointerover="window.__auditXss=1';openContextDrawer('workspace');$('contextworkspacepath').dispatchEvent(new Event('pointerover'))''')
            findings['attribute_injection']={'handler':page.locator('#contextworkspacepath').get_attribute('onpointerover'),'executed':page.evaluate('window.__auditXss===1')}
            page.evaluate('closeContextDrawer()')
            for width in [800,390]:
                page.set_viewport_size({'width':width,'height':900})
                page.evaluate("openContextDrawer('materials')")
                page.wait_for_timeout(300)
                findings[f'layout_{width}']=page.evaluate("""()=>{let r=document.querySelector('.context-drawer').getBoundingClientRect();return {viewport:innerWidth,scrollWidth:document.documentElement.scrollWidth,drawer:{left:r.left,right:r.right,width:r.width},buttons:[...document.querySelectorAll('#contextdrawerbody button')].map(e=>{let b=e.getBoundingClientRect();return {text:e.textContent,left:b.left,right:b.right}})}}""")
                page.screenshot(path=str(out/f'viewport-{width}.png'),full_page=False)
                page.evaluate('closeContextDrawer()')
            browser.close()
    finally:
        server.should_exit=True;thread.join(timeout=10);sock.close()
        (out/'findings.json').write_text(json.dumps(findings,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(findings,ensure_ascii=False))

