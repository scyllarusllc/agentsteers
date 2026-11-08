import unittest
from agentsteers.actor_jobs import ActorScopedMockJobs, Principal


class ActorScopedMockJobsTests(unittest.TestCase):
    def setUp(self):
        self.jobs = ActorScopedMockJobs(max_jobs=2)
        self.alice = Principal("alice", frozenset({"team/one"}), can_submit=True, can_cancel=True)
        self.bob = Principal("bob", frozenset({"team/one"}), can_submit=True, can_cancel=True)

    def test_submit_and_own_result(self):
        task = self.jobs.submit(self.alice, "team/one", "run mock tests")
        self.assertTrue(task["ok"])
        self.assertEqual(self.jobs.result(self.alice, task["task_id"])["status"], "queued_mock")

    def test_cross_actor_status_hidden(self):
        tid = self.jobs.submit(self.alice, "team/one", "test")["task_id"]
        self.assertEqual(self.jobs.status(self.bob, tid)["error"], "task_not_found")

    def test_cross_actor_result_hidden(self):
        tid = self.jobs.submit(self.alice, "team/one", "test")["task_id"]
        self.assertEqual(self.jobs.result(self.bob, tid)["error"], "task_not_found")

    def test_cross_actor_cancel_denied_without_disclosure(self):
        tid = self.jobs.submit(self.alice, "team/one", "test")["task_id"]
        self.assertEqual(self.jobs.cancel(self.bob, tid)["error"], "task_not_found")

    def test_submit_scope(self):
        self.assertEqual(self.jobs.submit(self.alice, "other/repo", "test")["error"], "repository_not_allowed")

    def test_readonly_cannot_submit(self):
        viewer = Principal("viewer", frozenset({"team/one"}))
        self.assertEqual(self.jobs.submit(viewer, "team/one", "test")["error"], "forbidden")

    def test_submitter_cannot_cancel_without_permission(self):
        tid = self.jobs.submit(self.alice, "team/one", "test")["task_id"]
        limited = Principal("alice", frozenset({"team/one"}), can_submit=True)
        self.assertEqual(self.jobs.cancel(limited, tid)["error"], "forbidden")

    def test_revoked_repository_access(self):
        tid = self.jobs.submit(self.alice, "team/one", "test")["task_id"]
        restricted = Principal("alice", frozenset(), can_submit=True, can_cancel=True)
        self.assertEqual(self.jobs.status(restricted, tid)["error"], "task_not_found")

    def test_cancel_is_idempotent(self):
        tid = self.jobs.submit(self.alice, "team/one", "test")["task_id"]
        self.assertEqual(self.jobs.cancel(self.alice, tid)["status"], "cancelled")
        self.assertTrue(self.jobs.cancel(self.alice, tid)["already_cancelled"])

    def test_queue_limit(self):
        self.jobs.submit(self.alice, "team/one", "a")
        self.jobs.submit(self.bob, "team/one", "b")
        self.assertEqual(self.jobs.submit(self.alice, "team/one", "c")["error"], "queue_full")

    def test_invalid_payload(self):
        self.assertEqual(self.jobs.submit(self.alice, "team/one", "")["error"], "invalid_instruction")

    def test_subject_required(self):
        with self.assertRaises(ValueError):
            Principal("", frozenset())

if __name__ == "__main__":
    unittest.main()
