import unittest
from agentsteers.task_service import MockTaskService

class TaskServiceTests(unittest.TestCase):
    def setUp(self):
        self.s = MockTaskService({"demo/example"})

    def submit(self, **kwargs):
        data = {"repository": "demo/example", "instruction": "Simulate test", "approved": True}
        data.update(kwargs)
        return self.s.submit_task(**data)

    def test_submit(self):
        self.assertEqual(self.submit()["status"], "queued_mock")

    def test_approval_required(self):
        self.assertEqual(self.submit(approved=False)["error"], "explicit_approval_required")

    def test_allowlist(self):
        self.assertEqual(self.submit(repository="other/repo")["error"], "repository_not_allowed")

    def test_blank_instruction(self):
        self.assertEqual(self.submit(instruction="")["error"], "invalid_instruction")

    def test_large_instruction(self):
        self.assertEqual(self.submit(instruction="x"*2001)["error"], "invalid_instruction")

    def test_status(self):
        task = self.submit()
        self.assertTrue(self.s.get_task_status(task["task_id"])["ok"])

    def test_mock_result(self):
        task = self.submit()
        self.assertIn("No Codex", self.s.get_task_result(task["task_id"])["result"]["message"])

    def test_cancel(self):
        task = self.submit()
        self.assertEqual(self.s.cancel_task(task["task_id"])["status"], "cancelled")

    def test_cancel_idempotent(self):
        task = self.submit()
        self.s.cancel_task(task["task_id"])
        self.assertTrue(self.s.cancel_task(task["task_id"])["already_cancelled"])

    def test_not_found(self):
        for result in (self.s.get_task_status("missing"), self.s.get_task_result("missing"), self.s.cancel_task("missing")):
            self.assertEqual(result["error"], "task_not_found")

    def test_no_instruction_in_result(self):
        task = self.submit(instruction="private-data")
        self.assertNotIn("private-data", str(self.s.get_task_status(task["task_id"])))
        self.assertNotIn("private-data", str(self.s.get_task_result(task["task_id"])))

if __name__ == "__main__":
    unittest.main()
