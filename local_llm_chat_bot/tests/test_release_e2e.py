"""Real app/file/HTTP flows, only the Farm server is a local synthetic fixture."""
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import chat_workbench as w
from fixture_support import FixtureEnvironment, PROFILE


class EndToEndTests(unittest.TestCase):
    def test_full_user_flow_and_invalid_classification_recovery(self):
        with FixtureEnvironment() as f, TestClient(w.app,raise_server_exceptions=False) as client:
            def post(path,body):
                r=client.post(path,json=body)
                self.assertEqual(r.status_code,200,(path,r.text))
                return r.json()
            post('/api/setup',{'workspace':str(f.workspace),'model':'gemini-2.5-pro','language':'en'})
            for language in ('zh','en','de','zh','en','de'):
                post('/api/language',{'language':language})
                self.assertEqual(client.get('/api/settings').json()['language'],language)
            post('/api/model',{'model':' GEMINI-2.5-FLASH '})
            profile=post('/api/codebook/prepare',{'path':str(f.rules)})
            self.assertEqual(profile['status'],'draft')
            post('/api/codebook/lock',{})
            post('/api/target',{'target':str(f.bg_a),'selected_paths':['facts.txt']})
            result=post('/api/chat',{'question':'Classify this Baugruppe'})
            self.assertEqual(result['classification']['label'],'Rotationseinheit')
            result=post('/api/chat',{'question':'Explain the motor evidence'})
            self.assertTrue(result['answer'])
            result=client.post('/api/chat/stream',json={'question':'TEST_UNKNOWN classify'})
            self.assertIn('"type": "error"',result.text)
            self.assertNotIn('"type": "result"',result.text)
            self.assertFalse(w.MODEL_WORK_IN_PROGRESS.is_set())
            before=f.rules.read_bytes()
            draft=json.loads(json.dumps(PROFILE))
            draft['classes'][0]['name']='Fixture Class B'
            response=client.post('/api/codebook/edit',json={'draft':draft,'confirmed':False,'profile_version':profile['version']})
            self.assertEqual(response.status_code,400)
            self.assertEqual(client.get('/api/codebook').json()['draft']['classes'][0]['name'],'Rotationseinheit')
            post('/api/codebook/edit',{'draft':draft,'confirmed':True,'profile_version':w.load_codebook_profile()['version']})
            post('/api/codebook/lock',{})
            post('/api/target',{'target':str(f.bg_b),'selected_paths':['facts.txt']})
            self.assertEqual(client.get('/api/history').json()['history'],[])
            result=post('/api/chat',{'question':'Classify this Baugruppe again'})
            self.assertEqual(result['classification']['label'],'Fixture Class B')
            self.assertEqual(f.rules.read_bytes(),before)
            last=json.dumps(f.calls[-1],ensure_ascii=False)
            self.assertIn('FIXTURE_BG_B',last)
            self.assertNotIn('FIXTURE_BG_A',last)
            self.assertIn('gemini-2.5-flash',f.calls[-1]['path'])
            self.assertEqual(sorted(p.name for p in f.bg_a.iterdir()),['facts.txt'])
            self.assertEqual(sorted(p.name for p in f.bg_b.iterdir()),['facts.txt'])
            self.assertTrue(client.get('/api/status').json()['requests']>0)
            (f.bg_b/'facts.txt').write_text('changed')
            self.assertEqual(client.post('/api/chat',json={'question':'classify'}).status_code,409)


if __name__=='__main__':
    unittest.main()
