"""Contract tests; no Codex CLI or external services are invoked."""
import unittest

from agentsteers.task_contract import TaskEntryPoint, TaskState, TaskStore


class TaskContractTests(unittest.TestCase):
    def setUp(self):
        self.store = TaskStore()
        self.store.enroll_device("alice", "centos-1")
        self.web = TaskEntryPoint(self.store, "alice")
        self.mcp = TaskEntryPoint(self.store, "alice")

    def test_both_entry_points_share_state(self):
        task = self.web.create("centos-1", "repo-a", "Run tests")
        self.assertEqual(self.mcp.status(task.id).state, TaskState.QUEUED)
        self.store.claim("alice", "centos-1", task.id)
        self.store.finish("alice", "centos-1", task.id, success=True, result="Passed")
        self.assertEqual(self.web.result(task.id), "Passed")
        self.assertEqual(self.mcp.status(task.id).state, TaskState.SUCCEEDED)

    def test_cross_owner_access_denied(self):
        task = self.web.create("centos-1", "repo-a", "Review code")
        stranger = TaskEntryPoint(self.store, "bob")
        with self.assertRaises(KeyError):
            stranger.status(task.id)
        with self.assertRaises(KeyError):
            stranger.cancel(task.id)
        with self.assertRaises(PermissionError):
            stranger.create("centos-1", "repo-a", "Review code")

    def test_cancel_prevents_claim_and_completion(self):
        task = self.mcp.create("centos-1", "repo-a", "Review code")
        self.assertEqual(self.web.cancel(task.id).state, TaskState.CANCELLED)
        with self.assertRaises(ValueError):
            self.store.claim("alice", "centos-1", task.id)

    def test_device_owner_cannot_be_reassigned(self):
        with self.assertRaises(PermissionError):
            self.store.enroll_device("bob", "centos-1")

    def test_wrong_device_cannot_complete(self):
        task = self.web.create("centos-1", "repo-a", "Review code")
        self.store.enroll_device("alice", "centos-2")
        with self.assertRaises(PermissionError):
            self.store.claim("alice", "centos-2", task.id)


if __name__ == "__main__":
    unittest.main()
