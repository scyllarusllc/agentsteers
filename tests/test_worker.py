import unittest

from agentsteers.worker import AuditLog, DryRunWorker, Task, TaskRejected


class DryRunWorkerTests(unittest.TestCase):
    def setUp(self):
        self.audit = AuditLog()
        self.worker = DryRunWorker(allowed_repositories={"demo/example"}, audit=self.audit)

    def task(self, **changes):
        data = dict(task_id="t-001", action="mock.test", repository="demo/example", approved_by="reviewer", payload="fixture")
        data.update(changes)
        return Task(**data)

    def test_approved_allowed_task_is_simulated(self):
        result = self.worker.run(self.task())
        self.assertEqual(result["status"], "simulated")
        self.assertEqual(self.audit.events[-1]["decision"], "accepted")

    def test_no_approval_rejected(self):
        with self.assertRaises(TaskRejected):
            self.worker.run(self.task(approved_by=None))

    def test_arbitrary_command_rejected(self):
        with self.assertRaises(TaskRejected):
            self.worker.run(self.task(action="shell.exec"))

    def test_wrong_repository_rejected(self):
        with self.assertRaises(TaskRejected):
            self.worker.run(self.task(repository="other/repo"))

    def test_duplicate_rejected(self):
        task = self.task()
        self.worker.run(task)
        with self.assertRaises(TaskRejected):
            self.worker.run(task)

    def test_invalid_task_id_rejected(self):
        with self.assertRaises(TaskRejected):
            self.worker.run(self.task(task_id="../../x"))

    def test_large_payload_rejected(self):
        with self.assertRaises(TaskRejected):
            self.worker.run(self.task(payload="x" * 2049))

    def test_audit_does_not_record_payload(self):
        self.worker.run(self.task(payload="secret-sample"))
        self.assertNotIn("secret-sample", str(self.audit.events))

    def test_no_empty_allowlist(self):
        with self.assertRaises(ValueError):
            DryRunWorker(allowed_repositories=set())


if __name__ == "__main__":
    unittest.main()
