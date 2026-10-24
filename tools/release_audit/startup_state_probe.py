"""Portable restoration of the audit's original one-off startup/state probe.

This prints observations, not a pass verdict. All state is synthetic.
"""
import os
import runpy
import sys
from pathlib import Path
from unittest.mock import patch

APP = Path(__file__).resolve().parents[2] / 'local_llm_chat_bot'
sys.path[:0] = [str(APP), str(APP / 'tests')]
import chat_workbench as w
from fixture_support import FixtureEnvironment
from fastapi.testclient import TestClient


def main():
    with patch('uvicorn.run') as serve, patch.object(
        sys, 'argv', [str(APP / 'chat_workbench.py'), '--env-file',
                      '/synthetic/custom.env', '--port', '8877']
    ):
        runpy.run_path(str(APP / 'chat_workbench.py'), run_name='__main__')
        print('CLI_requested_port_8877_actual_server_kwargs', serve.call_args.kwargs)
    with FixtureEnvironment() as f, TestClient(w.app, raise_server_exceptions=False) as client:
        body = {'workspace': str(f.workspace), 'model': 'gemini-2.5-pro',
                'env_file': str(f.root / 'custom.env')}
        with patch.dict(os.environ, {}, clear=True), patch.object(w, 'load_dotenv') as load:
            result = client.post('/api/setup', json=body)
            print('custom_env_setup', result.status_code, 'requested', body['env_file'],
                  'actually_loaded', str(load.call_args.args[0]))
        client.post('/api/setup', json=body)
        w.ACTIVE['state'].data['bg_context'] = ['legacy-invalid']
        w.ACTIVE['state'].save()
        result = client.post('/api/setup', json=body)
        print('corrupt_nested_state_setup', result.status_code)
        result = client.post('/api/chat', json={'question': 'fixture'})
        print('corrupt_nested_state_chat', result.status_code, result.text)


if __name__ == '__main__':
    main()
