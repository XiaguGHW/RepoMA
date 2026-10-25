"""R16: real dotenv files, isolated subprocess startup and recovery; no Bosch calls."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
from dotenv import load_dotenv  # noqa: E402 - locate sibling application modules
from fastapi.testclient import TestClient  # noqa: E402
import httpx  # noqa: E402
import chat_workbench as w  # noqa: E402
from fixture_support import FixtureEnvironment  # noqa: E402
from workbench_startup import FarmEnvironment, StartupConfig, StartupError, check_state_directory, check_dependencies  # noqa: E402


SECRET = 'synthetic-step8-key-never-log'


class Configuration(unittest.TestCase):
    def setUp(self):
        self.f = FixtureEnvironment().__enter__()
        self.addCleanup(self.f.__exit__, None, None, None)
        self.client = TestClient(w.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)
        self.endpoint = os.environ['BOSCH_FARM_BASE_URL']
        self.env = self.f.root / 'Konfiguration 中文 ü.env'
        self.write_env(self.env)
        for context in [patch.object(w, 'FARM_ENVIRONMENT', FarmEnvironment()),
                        patch.object(w, 'load_dotenv', load_dotenv), patch.dict(os.environ, {}, clear=True),
                        patch.object(w, 'STARTUP_CONFIG', StartupConfig(env_file=self.f.root / '.env'))]:
            context.start()
            self.addCleanup(context.stop)

    def write_env(self, path, *, secret=SECRET, alternate=False, endpoint=None):
        name = 'BOSCH_FARM_API_KEY' if alternate else 'BOSCH_FARM_SUBSCRIPTION_KEY'
        path.write_text(f'{name}={secret}\nBOSCH_FARM_BASE_URL={endpoint or self.endpoint}\n', encoding='utf-8-sig')

    def setup_request(self, env=None, **extra):
        body = {'workspace': str(self.f.workspace), 'model': 'gemini-2.5-pro', 'language': 'en', **extra}
        if env is not None:
            body['env_file'] = str(env)
        return self.client.post('/api/setup', json=body, headers={'X-Workbench-Language': 'en'})

    def configured(self, env=None, **extra):
        result = self.setup_request(self.env if env is None else env, **extra)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertNotIn(SECRET, result.text)
        return result

    def test_actual_custom_env_is_shared_by_setup_probe_and_diagnostics(self):
        self.configured()
        self.assertEqual(w.ACTIVE['llm'].api_key, SECRET)
        probe = self.client.post('/api/model-test', json={'model': 'gemini-2.5-pro'})
        self.assertEqual(probe.status_code, 200, probe.text)
        self.assertTrue(probe.json()['ok'], probe.text)
        self.assertTrue(self.f.calls)
        diagnostic = self.client.get('/api/diagnostics')
        env_check = next(item for item in diagnostic.json()['checks'] if item['id'] == 'env_file')
        self.assertEqual(env_check['path'], str(self.env))
        self.assertTrue(env_check['ok'])
        for response in [probe, diagnostic, self.client.get('/api/settings')]:
            self.assertNotIn(SECRET, response.text)
        self.assertEqual(self.setup_request().status_code, 200)  # GUI omits the env field.
        self.assertEqual(w.ACTIVE['env_file'], str(self.env))
        self.assertFalse((self.f.bg_a / 'AI_Bot_State').exists())

    def test_file_switch_drops_old_loaded_values_but_external_values_win(self):
        self.configured()
        second = self.f.root / 'zweite.env'
        self.write_env(second, secret='second-synthetic-key', alternate=True)
        self.configured(second)
        self.assertNotIn('BOSCH_FARM_SUBSCRIPTION_KEY', os.environ)
        self.assertEqual(w.ACTIVE['llm'].api_key, 'second-synthetic-key')
        os.environ['BOSCH_FARM_SUBSCRIPTION_KEY'] = 'external-process-key'
        self.configured()
        self.assertEqual(w.ACTIVE['llm'].api_key, 'external-process-key')

    def test_failed_config_switch_preserves_active_environment_and_pending_plan(self):
        self.configured()
        active = dict(w.ACTIVE)
        w.ACTIVE['pending'].append({'path': 'reviewed-fixture.txt'})
        snapshot = dict(os.environ)
        invalid = self.f.root / 'invalid.env'
        invalid.write_bytes(b'\xff\xfesecret data not UTF-8')
        for path, key in [(self.f.root / 'missing.env', 'startup.env_missing'),
                          (invalid, 'startup.env_unreadable')]:
            response = self.setup_request(path)
            self.assertEqual(response.status_code, 400, response.text)
            self.assertEqual(response.json()['message_key'], key)
            self.assertIs(w.ACTIVE['state'], active['state'])
            self.assertEqual(w.ACTIVE['pending'], [{'path': 'reviewed-fixture.txt'}])
            self.assertEqual(dict(os.environ), snapshot)
            self.assertNotIn(SECRET, response.text)
        second = self.f.root / 'valid-new.env'
        self.write_env(second, secret='new-key-should-roll-back')
        self.assertEqual(self.setup_request(second, model='unknown').status_code, 400)
        self.assertEqual(dict(os.environ), snapshot)
        self.assertIs(w.ACTIVE['llm'], active['llm'])

    def test_missing_default_configuration_can_be_fixed_without_restart(self):
        response = self.setup_request()
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(response.json()['message_key'], 'startup.key_missing')
        self.write_env(w.STARTUP_CONFIG.env_file)
        self.assertEqual(self.setup_request().status_code, 200)
        self.assertEqual(self.setup_request().status_code, 200)
        self.assertEqual(w.ACTIVE['llm'].api_key, SECRET)

    def test_state_failure_is_actionable_transactional_and_recoverable(self):
        self.configured()
        active = w.ACTIVE['state']
        blocked = self.f.root / 'blocked-state'
        blocked.write_text('A file cannot be a state directory', encoding='utf-8')
        with patch.object(w, 'app_state_home', return_value=blocked):
            response = self.setup_request(self.env)
            self.assertEqual(response.status_code, 503, response.text)
            self.assertEqual(response.json()['message_key'], 'startup.state_unwritable')
            self.assertIn('permissions', response.json()['detail'])
            self.assertIs(w.ACTIVE['state'], active)
            blocked.unlink()
            self.assertEqual(self.setup_request(self.env).status_code, 200)
        with patch.object(w, 'save_workbench_settings', side_effect=PermissionError('locked')):
            active = w.ACTIVE['state']
            self.assertEqual(self.setup_request(self.env).status_code, 503)
            self.assertIs(w.ACTIVE['state'], active)

    def test_state_override_is_rejected_and_permission_errors_have_no_raw_trace(self):
        result = self.setup_request(self.env, state_dir=str(self.f.bg_a))
        self.assertEqual(result.json()['message_key'], 'startup.state_fixed')
        self.assertFalse((self.f.bg_a / 'projects').exists())
        with patch('workbench_startup.os.replace', side_effect=PermissionError('synthetic lock')):
            with self.assertRaises(StartupError) as caught:
                check_state_directory(self.f.root / 'state-probe')
        self.assertEqual(caught.exception.code, 'startup.state_unwritable')
        self.assertEqual(list((self.f.root / 'state-probe').iterdir()), [])

    def test_bad_endpoint_is_redacted_and_failed_probe_cannot_change_active_config(self):
        self.configured()
        snapshot = dict(os.environ)
        self.write_env(self.env, endpoint=f'https://user:{SECRET}@invalid.example/api')
        result = self.client.post('/api/model-test', json={'model': 'gemini-2.5-pro'})
        self.assertEqual(result.status_code, 400)
        self.assertEqual(result.json()['message_key'], 'startup.endpoint_invalid')
        self.assertNotIn(SECRET, result.text)
        self.assertEqual(dict(os.environ), snapshot)
        self.write_env(self.env, secret='changed-config-key')
        self.assertTrue(self.client.post('/api/model-test', json={'model': 'gemini-2.5-pro'}).json()['ok'])
        self.assertEqual(dict(os.environ), snapshot)
        self.assertEqual(w.ACTIVE['llm'].api_key, SECRET)
        self.configured()
        self.assertEqual(w.ACTIVE['llm'].api_key, 'changed-config-key')

    def test_uvicorn_bind_failure_after_preflight_has_recovery_and_no_secret(self):
        output = io.StringIO()
        with (patch.object(w, 'STARTUP_CONFIG', StartupConfig(env_file=self.env, env_explicit=True, port=8877)),
              patch.object(w, 'check_port'), patch.object(w.uvicorn, 'run', side_effect=SystemExit(1)),
              redirect_stderr(output), redirect_stdout(output)):
            with self.assertRaises(SystemExit) as caught:
                w.main()
        self.assertEqual(caught.exception.code, 1)
        self.assertIn('--port', output.getvalue())
        self.assertNotIn(SECRET, output.getvalue())


class StartupSubprocess(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='Workbench Start 中文 Prüfung ')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.app = self.root / 'Programm ü'
        self.app.mkdir()
        for pattern in ['*.py', '*.json', 'requirements.txt']:
            for source in APP.glob(pattern):
                shutil.copy2(source, self.app / source.name)
        self.cwd = self.root / 'BG 原始资料'
        self.cwd.mkdir()
        self.source = self.cwd / 'facts.txt'
        self.source.write_bytes(b'immutable source fixture')
        self.environment = {key: value for key, value in os.environ.items()
                            if not key.startswith(('BOSCH_FARM_', 'WORKBENCH_'))}
        self.environment['NO_PROXY'] = '127.0.0.1,localhost'

    def tearDown(self):
        self.assertEqual(self.source.read_bytes(), b'immutable source fixture')
        self.assertEqual(sorted(p.name for p in self.cwd.iterdir()), ['facts.txt'])

    def run_cli(self, *args, no_site=False):
        command = [sys.executable, *(['-S'] if no_site else []), str(self.app / 'chat_workbench.py'), *args]
        result = subprocess.run(command, cwd=self.cwd, env=self.environment, capture_output=True, text=True, timeout=15)
        self.assertNotIn(SECRET, result.stdout + result.stderr)
        return result

    def default_env(self):
        (self.app / '.env').write_text('BOSCH_FARM_SUBSCRIPTION_KEY=' + SECRET + '\n', encoding='utf-8')

    def test_help_unknown_options_and_port_validation_work_without_dependencies(self):
        help_result = self.run_cli('--help', no_site=True)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn('--env-file', help_result.stdout)
        for args in [('--wrong-option',), ('--port', '0'), ('--port', '65536'), ('--port', 'abc'), ('--host', '0.0.0.0'), ('--env-file', '')]:
            with self.subTest(args=args):
                result = self.run_cli(*args, no_site=True)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertNotIn('Traceback', result.stderr)

    def test_missing_dependencies_show_exact_install_command(self):
        result = self.run_cli(no_site=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Missing Python packages:', result.stderr)
        self.assertIn('uvicorn', result.stderr)
        self.assertIn('pip install -r', result.stderr)
        self.assertIn(str(self.app / 'requirements.txt'), result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        with patch('workbench_startup.importlib.import_module', side_effect=ImportError(SECRET)):
            with self.assertRaises(RuntimeError) as caught:
                check_dependencies()
        self.assertIn('Cannot load Python packages', str(caught.exception))
        self.assertNotIn(SECRET, str(caught.exception))

    def test_explicit_missing_or_bad_encoding_file_fails_cleanly(self):
        result = self.run_cli('--env-file', str(self.root / 'not-found.env'))
        self.assertEqual(result.returncode, 1)
        self.assertIn('--env-file', result.stderr)
        bad = self.root / 'bad.env'
        bad.write_bytes(b'\xff\xfe' + SECRET.encode())
        result = self.run_cli('--env-file', str(bad))
        self.assertEqual(result.returncode, 1)
        self.assertIn('UTF-8', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_missing_key_and_blocked_state_show_recovery(self):
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertIn('BOSCH_FARM_SUBSCRIPTION_KEY', result.stderr)
        self.default_env()
        (self.app / 'AI_Bot_State').write_text('blocked by fixture file', encoding='utf-8')
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertIn('writable location', result.stderr)
        self.assertIn('file locks', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_occupied_port_reports_reuse_or_alternate_port(self):
        self.default_env()
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            port = listener.getsockname()[1]
            result = self.run_cli('--port', str(port))
        self.assertEqual(result.returncode, 1)
        self.assertIn(f'http://127.0.0.1:{port}', result.stderr)
        self.assertIn('--port 8877', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_real_server_different_cwd_custom_env_shutdown_and_restart(self):
        custom = self.root / 'eigene 中文 ü.env'
        custom.write_text('BOSCH_FARM_SUBSCRIPTION_KEY=' + SECRET + '\n', encoding='utf-8-sig')
        with socket.socket() as selector:
            selector.bind(('127.0.0.1', 0))
            port = selector.getsockname()[1]
        # Relative --env-file uses the launch cwd; default state still uses the app directory.
        relative = os.path.relpath(custom, self.cwd)
        command = [sys.executable, str(self.app / 'chat_workbench.py'), '--env-file', relative, '--port', str(port)]
        for iteration in range(2):
            process = subprocess.Popen(command, cwd=self.cwd, env=self.environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            def stop():
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=6)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)
            self.addCleanup(stop)
            try:
                with httpx.Client(base_url=f'http://127.0.0.1:{port}', trust_env=False, timeout=1) as client:
                    deadline = time.monotonic() + 10
                    while time.monotonic() < deadline and process.poll() is None:
                        try:
                            if client.get('/api/settings').status_code == 200:
                                break
                        except httpx.HTTPError:
                            pass
                        time.sleep(0.05)
                    else:
                        self.fail('Fixture subprocess did not become ready')
                    if iteration:
                        self.assertEqual(client.get('/api/settings').json()['workspace'], str(self.cwd))
                    result = client.post('/api/setup', json={'workspace': str(self.cwd), 'model': 'gemini-2.5-pro'})
                    self.assertEqual(result.status_code, 200, result.text)
                    self.assertNotIn(SECRET, result.text)
                    self.assertTrue((self.app / 'AI_Bot_State' / 'workbench_settings.json').exists())
            finally:
                stop()
                stdout, stderr = process.communicate(timeout=3)
                self.assertNotIn(SECRET, stdout + stderr)
                self.assertNotIn('Traceback', stderr)
        for path in (self.app / 'AI_Bot_State').rglob('*.json'):
            self.assertNotIn(SECRET, path.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
