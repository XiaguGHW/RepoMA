"""One-click start: open the browser, reuse a running instance, find the right Python."""

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


class Launcher(unittest.TestCase):
    """The Windows launcher cannot run here; check what it must contain."""

    def setUp(self):
        self.raw = (Path(w.__file__).parent / "Baugruppen_Classifier.bat").read_bytes()
        self.text = self.raw.decode("ascii")

    def test_plain_ascii_with_windows_line_endings(self):
        self.assertNotIn(b"\n", self.raw.replace(b"\r\n", b""))
        self.assertNotIn("EnableDelayedExpansion", self.text)  # "!" in paths would break

    def test_finds_conda_environments_without_activation(self):
        for needle in ("WORKBENCH_PYTHON", "python_path.txt", ".venv\\Scripts\\python.exe", "where python",
                       ".conda\\environments.txt", "conda-meta", "Library\\bin", "py -3",
                       "import fastapi, uvicorn, fitz", "chat_workbench.py\" %*"):
            self.assertIn(needle, self.text)

    def test_offers_a_private_environment_when_nothing_is_found(self):
        self.assertIn("-m venv", self.text)
        self.assertIn("-m pip install -r", self.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
