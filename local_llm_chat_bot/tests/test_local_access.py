"""F-06: the loopback workbench rejects cross-site and test-only hosts."""

import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import chat_workbench as w


class LocalAccess(unittest.TestCase):
    def test_cross_site_requests_are_rejected_while_local_calls_still_work(self):
        with patch.dict(os.environ, {"WORKBENCH_ALLOW_TEST_HOST": "1"}):
            with TestClient(w.app) as client:
                self.assertEqual(client.get("/", headers={"Sec-Fetch-Site": "same-origin"}).status_code, 200)
                self.assertEqual(client.get("/").status_code, 200)
                self.assertEqual(client.get("/", headers={"Sec-Fetch-Site": "cross-site"}).status_code, 403)

    def test_testserver_host_is_rejected_without_the_explicit_test_switch(self):
        with patch.dict(os.environ, {}, clear=True):
            with TestClient(w.app) as client:
                response = client.get("/", headers={"Host": "testserver"})
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main(verbosity=2)
