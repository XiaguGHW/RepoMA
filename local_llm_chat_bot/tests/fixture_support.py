"""Generated data and a real loopback HTTP mock Farm. Never contacts Bosch."""
import json
import os
from pathlib import Path
import re
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import chat_workbench as w


PROFILE = {'classes': [{'name':'Rotationseinheit','definition':'Rotates an object.',
    'decision_rules':[{'id':'rotation-1','text':'The primary function is rotation.','pages':[1]}],
    'boundaries':[], 'evidence_pages':[1]}], 'global_rules':[], 'table_rules':[], 'uncertainties':[]}


class FixtureEnvironment:
    def __enter__(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='Workbench 发布 Prüfung ')
        self.root=Path(self.tmp.name)
        self.workspace=self.root/'code workspace'
        self.workspace.mkdir()
        self.bg_a=self.root/'BG_A'
        self.bg_a.mkdir()
        self.bg_b=self.root/'BG_B'
        self.bg_b.mkdir()
        (self.bg_a/'facts.txt').write_text('FIXTURE_BG_A: The motor rotates the object.',encoding='utf-8')
        (self.bg_b/'facts.txt').write_text('FIXTURE_BG_B: An independent rotary unit.',encoding='utf-8')
        from docx import Document
        document=Document()
        document.add_paragraph('Rotationseinheit: rotates an object. Rule rotation-1.')
        self.rules=self.root/'Rules ü.docx'
        document.save(self.rules)
        self.calls=[]
        calls=self.calls
        self.response_transform=None
        fixture=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                calls.append({'path':self.path,'body':body})
                # Claude (Vertex rawPredict) requests get a Claude-shaped reply;
                # transforms are always written against the Gemini shape.
                claude=self.path.endswith(':rawPredict')
                if claude:
                    prompt='\n'.join(b.get('text','') for m in body.get('messages',[]) for b in (m.get('content') if isinstance(m.get('content'),list) else []) if isinstance(b,dict))
                    system='\n'.join(b.get('text','') for b in body.get('system',[]) if isinstance(b,dict))
                else:
                    prompt='\n'.join(p.get('text','') for c in body.get('contents',[]) for p in c.get('parts',[]))
                    system='\n'.join(p.get('text','') for p in body.get('system_instruction',{}).get('parts',[]))
                if 'one section per request' in system:
                    cls=PROFILE['classes'][0]
                    if 'SECTION outline' in prompt:
                        text=json.dumps({'classes':[{'name':cls['name']}]})
                    elif 'SECTION class' in prompt:
                        text=json.dumps(cls)
                    elif 'SECTION general' in prompt:
                        text=json.dumps({'global_rules':[],'uncertainties':[]})
                    else:
                        text=json.dumps({'table_rules':[]})
                elif 'consolidate page-by-page' in system:
                    text=json.dumps(PROFILE)
                elif 'transcribe exactly one' in system:
                    text=json.dumps({'page':1,'definitions':['Rotationseinheit: rotates objects']})
                elif 'careful local workspace' in system:
                    if 'TEST_EMPTY' in prompt:
                        text=''
                    elif 'TEST_BAD_JSON' in prompt:
                        text='{"answer":'
                    else:
                        labels=re.findall(r'--- DOCUMENT \[[^\]]+\] (.*?) ---',prompt)
                        profile_match=re.search(r'primary rule source\): (\{[^\n]+\})',prompt)
                        profile=json.loads(profile_match.group(1)) if profile_match else PROFILE
                        cls=profile['classes'][0]
                        reference_match=re.search(r'Classification reference manifest: (\{[^\n]+\})',prompt)
                        references=json.loads(reference_match.group(1)) if reference_match else {}
                        bg_labels=references.get('bg_labels', labels[:1])
                        rule_labels=references.get('codebook_labels', [])
                        language='de' if 'primarily in German' in prompt else 'zh' if 'primarily in Chinese' in prompt else 'en'
                        answer={'en':'The fixture rotates the object.\n\n| Part | Function |\n|---|---|\n| Motor | Rotation |',
                                'de':'Die Testbaugruppe dreht das Objekt.', 'zh':'测试装配体使对象旋转。'}[language]
                        classification={'label':'Rotation' if 'TEST_UNKNOWN' in prompt else cls['name'], 'confidence':'high',
                            'alternative_label':'','codebook_rule_ids':[cls['decision_rules'][0]['id']],
                            'codebook_rule_pages':[] if references.get('codebook_source_kind')=='nonpaged' else [1],
                            'codebook_rule_refs':rule_labels[:1],
                            'evidence_labels':bg_labels[:1], 'bg_evidence_pages':bg_labels[:1], 'uncertainties':[]}
                        # AUTO and EXPLANATION MODE: like a real model, classify only when the
                        # request explicitly asks for it; CLASSIFICATION REQUIRED always classifies.
                        request_match=re.search(r'User request: (.*)',prompt)
                        asks_class=bool(re.search(r'classif|klassifi|分类|类别|判断',request_match.group(1) if request_match else '',re.I))
                        optional=('- AUTO MODE:' in prompt or '- EXPLANATION MODE:' in prompt)
                        wants=('BG CLASSIFICATION MODE' in prompt and (not optional or asks_class))
                        text=json.dumps({'answer':answer,'classification':classification if wants else None,
                                         'changes':[],'read_files':[]},ensure_ascii=False)
                else:
                    text='Fixture evidence: the object is rotated by a motor; facts.txt.'
                response={'candidates':[{'content':{'parts':[{'text':text}]},'finishReason':'STOP'}],
                          'usageMetadata':{'promptTokenCount':20,'candidatesTokenCount':10,'totalTokenCount':30}}
                if fixture.response_transform:
                    response=fixture.response_transform(response, prompt, system)
                if claude and 'candidates' in response:
                    candidate=response['candidates'][0]
                    reason=candidate.get('finishReason','STOP')
                    response={'content':[{'type':'text','text':''.join(part.get('text','') for part in candidate.get('content',{}).get('parts',[]))}],
                              'stop_reason':{'STOP':'end_turn','MAX_TOKENS':'max_tokens'}.get(reason,str(reason).lower()),
                              'usage':{'input_tokens':20,'output_tokens':10}}
                encoded=json.dumps(response).encode()
                self.send_response(200)
                self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(encoded)))
                self.end_headers()
                try:
                    self.wfile.write(encoded)
                except (BrokenPipeError,ConnectionResetError):
                    pass  # Expected when a timeout/stop closes the fixture socket.
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.old=dict(w.ACTIVE)
        w.ACTIVE.clear()
        w.MODEL_WORK_IN_PROGRESS.clear()
        self.patches=[patch.object(w,'app_state_home',return_value=self.workspace/'AI_Bot_State'),patch.object(w,'load_dotenv'),
                      patch.dict(os.environ,{'BOSCH_FARM_SUBSCRIPTION_KEY':'offline-fixture-only',
                          'WORKBENCH_ALLOW_TEST_HOST':'1',
                          'BOSCH_FARM_BASE_URL':f'http://127.0.0.1:{self.server.server_port}/api'})]
        for p in self.patches:
            p.start()
        return self

    def __exit__(self,*args):
        for p in reversed(self.patches):
            p.stop()
        w.ACTIVE.clear()
        w.ACTIVE.update(self.old)
        w.MODEL_WORK_IN_PROGRESS.clear()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.tmp.cleanup()
