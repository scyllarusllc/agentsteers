"""Offline tests for the opt-in Frappe bridge; no production site needed."""
import json
import unittest
from unittest.mock import patch

from agentsteers.frappe_task_client import FrappeTaskClient


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, *args):
        return json.dumps(self.payload).encode()


class FrappeTaskClientTests(unittest.TestCase):
    def setUp(self):
        self.client = FrappeTaskClient(
            base_url="https://frappe.example.test", api_key="KEY", api_secret="SECRET",
            allowed_repositories={"scyllarusllc/agentsteers"})

    def test_requires_safe_transport(self):
        with self.assertRaises(ValueError):
            FrappeTaskClient(base_url="http://frappe.example.test", api_key="k",
                             api_secret="s", allowed_repositories={"owner/repo"})

    def test_approval_and_allowlist_prevent_requests(self):
        with patch("agentsteers.frappe_task_client.urlopen") as request:
            self.assertEqual("explicit_approval_required",
                             self.client.submit_task("scyllarusllc/agentsteers", "fix", False)["error"])
            self.assertEqual("repository_not_allowed",
                             self.client.submit_task("other/repo", "fix", True)["error"])
            request.assert_not_called()

    def test_persist_and_read_status(self):
        calls = []
        def transport(request, **kwargs):
            calls.append(request)
            return FakeResponse({"message": {
                "ok": True, "task_id": "abc123", "status": "Queued"
            }})
        with patch("agentsteers.frappe_task_client.urlopen", side_effect=transport):
            submitted = self.client.submit_task("scyllarusllc/agentsteers", "update docs", True)
            status = self.client.get_task_status("abc123")
        self.assertEqual("abc123", submitted["task_id"])
        self.assertEqual("Queued", status["status"])
        self.assertEqual(["POST", "GET"], [x.get_method() for x in calls])
        self.assertIn("get_task_status", calls[1].full_url)
        self.assertEqual("token KEY:SECRET", calls[0].get_header("Authorization"))

    def test_cancel_fails_closed(self):
        self.assertEqual("frappe_cancellation_not_implemented",
                         self.client.cancel_task("abc")["error"])


if __name__ == "__main__":
    unittest.main()
