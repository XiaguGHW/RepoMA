"""A slow proxy tunnel is reported by requests as ReadTimeout after the
*connect* timeout. Such a request never reached Bosch Farm, so it is retried;
a genuine read timeout is still never retried (no second paid generation)."""

import os
from pathlib import Path
import socket
import sys
import threading
import time
import unittest
from unittest.mock import patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from llm_connector_with_prompt_caching import LLMConnector, connection_setup_timeout  # noqa: E402
from request_runtime import RequestControl, RequestPolicy  # noqa: E402


class SlowProxy:
    """Accepts a CONNECT but never answers it within the test's connect timeout."""

    def __enter__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.port = self.sock.getsockname()[1]
        self.tunnels = 0
        self.stop = threading.Event()
        threading.Thread(target=self.serve, daemon=True).start()
        return self

    def serve(self):
        while not self.stop.is_set():
            try:
                client, _address = self.sock.accept()
            except OSError:
                return
            self.tunnels += 1
            threading.Thread(target=self.hold, args=(client,), daemon=True).start()

    def hold(self, client):
        try:
            client.recv(4096)
            self.stop.wait(5)
        finally:
            client.close()

    def __exit__(self, *args):
        self.stop.set()
        self.sock.close()


class ProxyTunnelTimeout(unittest.TestCase):
    def connector(self, connect=0.4):
        connector = LLMConnector("claude-haiku-5-5", "offline-test-key")
        connector.request_control = RequestControl(RequestPolicy(connect_timeout=connect, response_timeout=300,
                                                                 attempts=3, backoff=0))
        return connector

    def test_slow_tunnel_is_retried_and_reported_as_connection_timeout(self):
        with SlowProxy() as proxy, patch.dict(os.environ, {
                "https_proxy": f"http://127.0.0.1:{proxy.port}", "HTTPS_PROXY": f"http://127.0.0.1:{proxy.port}",
                "no_proxy": "", "NO_PROXY": "", "BOSCH_FARM_BASE_URL": "https://farm.example.invalid/api"}):
            started = time.monotonic()
            result = self.connector().ask_about_files([], "question")
            elapsed = time.monotonic() - started
        self.assertTrue(result.startswith("Error after 3 attempts: ConnectTimeout"), result)
        self.assertIn("WORKBENCH_CONNECT_TIMEOUT_SECONDS", result)
        self.assertEqual(proxy.tunnels, 3)
        self.assertLess(elapsed, 5)

    def test_genuine_read_timeout_is_still_not_retried(self):
        error = requests.exceptions.ReadTimeout("HTTPSConnectionPool(host='x', port=443): Read timed out. (read timeout=300)")
        with patch("requests.post", side_effect=error) as post, patch.dict(os.environ, {"BOSCH_FARM_BASE_URL": "https://farm.example.invalid/api"}):
            result = self.connector(connect=15).ask_about_files([], "question")
        self.assertEqual(post.call_count, 1)
        self.assertIn("no complete response within 300 s", result)

    def test_detection_requires_the_connect_value_and_an_early_failure(self):
        tunnel = requests.exceptions.ReadTimeout("Read timed out. (read timeout=15)")
        self.assertTrue(connection_setup_timeout(tunnel, 15.2, 15, 300))
        self.assertFalse(connection_setup_timeout(tunnel, 40, 15, 300))  # too late for setup
        self.assertFalse(connection_setup_timeout(requests.exceptions.ReadTimeout("read"), 0.1, 15, 300))  # unknown
        self.assertFalse(connection_setup_timeout(requests.exceptions.ReadTimeout("Read timed out. (read timeout=300)"), 0.1, 15, 300))
        self.assertFalse(connection_setup_timeout(tunnel, 1, 15, 15.5))  # limits indistinguishable


if __name__ == "__main__":
    unittest.main(verbosity=2)
