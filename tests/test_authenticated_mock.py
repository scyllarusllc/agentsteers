"""Local auth-boundary regression tests with a stub verifier.

The stub checks service wiring, not cryptographic JWT or HTTP OAuth.
"""
import unittest

from agentsteers.authenticated_mock import AuthenticatedMockTaskService
from agentsteers.oauth_security import AuthorizationError, Principal


class StubVerifier:
    def verify(self, authorization_header):
        identities = {
            "Bearer owner": Principal("owner", frozenset({
                "agentsteers:submit", "agentsteers:read", "agentsteers:cancel"})),
            "Bearer other": Principal("other", frozenset({
                "agentsteers:submit", "agentsteers:read", "agentsteers:cancel"})),
            "Bearer reader": Principal("reader", frozenset({"agentsteers:read"})),
        }
        try:
            return identities[authorization_header]
        except (KeyError, TypeError):
            raise AuthorizationError("Invalid token") from None


class AuthenticatedMockTests(unittest.TestCase):
    def setUp(self):
        self.service = AuthenticatedMockTaskService(
            verifier=StubVerifier(), repositories={"scyllarusllc/ez-workbase"})

    def submit(self):
        return self.service.dispatch(
            "Bearer owner", "submit_task",
            repository="scyllarusllc/ez-workbase", instruction="check mock task")

    def test_local_round_trip_and_repeat_cancel(self):
        task_id = self.submit()["task_id"]
        self.assertEqual(self.service.dispatch(
            "Bearer owner", "get_task_status", task_id=task_id)["status"], "queued_mock")
        self.assertIn("Simulation only", self.service.dispatch(
            "Bearer owner", "get_task_result", task_id=task_id)["result"]["message"])
        self.assertEqual(self.service.dispatch(
            "Bearer owner", "cancel_task", task_id=task_id)["status"], "cancelled")
        self.assertTrue(self.service.dispatch(
            "Bearer owner", "cancel_task", task_id=task_id)["already_cancelled"])

    def test_other_user_cannot_read_or_cancel(self):
        task_id = self.submit()["task_id"]
        for action in ("get_task_status", "get_task_result", "cancel_task"):
            with self.subTest(action=action):
                self.assertEqual(self.service.dispatch(
                    "Bearer other", action, task_id=task_id),
                    {"ok": False, "error": "task_not_found"})

    def test_reject_missing_invalid_tokens(self):
        for token in (None, "", "Bearer bad", "Basic owner"):
            with self.subTest(token=token), self.assertRaises(AuthorizationError):
                self.service.dispatch(
                    token, "submit_task", repository="scyllarusllc/ez-workbase",
                    instruction="x")

    def test_reject_insufficient_permissions_and_unknown_action(self):
        task_id = self.submit()["task_id"]
        for action, args in (
            ("submit_task", {"repository": "scyllarusllc/ez-workbase", "instruction": "x"}),
            ("cancel_task", {"task_id": task_id}),
        ):
            with self.subTest(action=action), self.assertRaises(AuthorizationError):
                self.service.dispatch("Bearer reader", action, **args)
        with self.assertRaises(AuthorizationError):
            self.service.dispatch("Bearer owner", "run_shell", command="id")

    def test_reject_extra_arguments_and_disallowed_repository(self):
        task_id = self.submit()["task_id"]
        with self.assertRaises(AuthorizationError):
            self.service.dispatch("Bearer owner", "get_task_status",
                                  task_id=task_id, owner="other")
        self.assertEqual(self.service.dispatch(
            "Bearer owner", "submit_task", repository="other/unknown",
            instruction="x")["error"], "repository_not_allowed")

    def test_empty_repository_allowlist_fails(self):
        with self.assertRaises(ValueError):
            AuthenticatedMockTaskService(verifier=StubVerifier(), repositories=[])


if __name__ == "__main__":
    unittest.main()
