"""One-click start: open the browser, remember a --workspace folder, reuse a running Workbench."""

from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import socket
import sys
import threading
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn  # noqa: E402
import chat_workbench as w  # noqa: E402
import workbench_startup as startup  # noqa: E402
from fixture_support import FixtureEnvironment  # noqa: E402


def free_socket():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    return sock


class Options(unittest.TestCase):
    def test_command_line_opens_the_browser_unless_told_not_to(self):
        self.assertTrue(startup.parse_options([]).open_browser)
        self.assertFalse(startup.parse_options(["--no-browser"]).open_browser)
        self.assertIsNone(startup.parse_options([]).workspace)
        self.assertEqual(startup.parse_options(["--workspace", '"C:/BG"']).workspace, Path("C:/BG"))

    def test_embedded_config_never_opens_a_browser(self):
        self.assertFalse(startup.StartupConfig().open_browser)


class RunningWorkbench(unittest.TestCase):
    def setUp(self):
        self.f = FixtureEnvironment().__enter__()
        self.addCleanup(self.f.__exit__, None, None, None)

    def serve_workbench(self):
        sock = free_socket()
        self.addCleanup(sock.close)
        server = uvicorn.Server(uvicorn.Config(w.app, log_level="error"))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        self.addCleanup(lambda: (setattr(server, "should_exit", True), thread.join(timeout=10)))
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        return sock.getsockname()[1]

    def test_detects_only_a_workbench(self):
        port = self.serve_workbench()
        self.assertTrue(startup.running_workbench(port))

        class Other(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"hello": 1}')

            def log_message(self, *args):
                pass

        other = HTTPServer(("127.0.0.1", 0), Other)
        threading.Thread(target=other.serve_forever, daemon=True).start()
        self.addCleanup(other.shutdown)
        self.assertFalse(startup.running_workbench(other.server_address[1]))
        sock = free_socket()
        unused = sock.getsockname()[1]
        sock.close()
        self.assertFalse(startup.running_workbench(unused))

    def test_browser_opens_once_the_server_listens(self):
        port = self.serve_workbench()
        opener = Mock()
        startup.open_browser_when_ready(port, timeout=5, opener=opener).join(timeout=6)
        opener.assert_called_once_with(f"http://127.0.0.1:{port}")

    def test_second_start_reuses_the_running_workbench(self):
        port = self.serve_workbench()
        config = startup.StartupConfig(env_file=self.f.root / ".env", port=port, open_browser=True)
        with (patch.object(w, "STARTUP_CONFIG", config), patch.object(w.webbrowser, "open") as browser,
              patch.object(w.uvicorn, "run") as run):
            w.main()
        browser.assert_called_once_with(f"http://127.0.0.1:{port}")
        run.assert_not_called()

    def test_workspace_option_becomes_the_restored_workspace(self):
        folder = self.f.root / "BG folder"
        folder.mkdir()
        w.save_workbench_settings(self.f.workspace, "work", "gemini-2.5-pro", "en")
        self.assertEqual(w.remember_start_workspace(folder), folder.resolve())
        settings = w.load_workbench_settings()
        self.assertEqual(Path(settings["workspace"]), folder.resolve())
        self.assertEqual((settings["session"], settings["model"], settings["language"]),
                         ("default", "gemini-2.5-pro", "en"))
        with self.assertRaises(startup.StartupError) as error:
            w.remember_start_workspace(self.f.root / "missing")
        self.assertEqual(error.exception.code, "startup.workspace_missing")


if __name__ == "__main__":
    unittest.main(verbosity=2)
