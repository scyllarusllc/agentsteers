"""Offline security checks for future Codex execution preflight."""
from dataclasses import replace
from pathlib import Path
import os
import tempfile
import unittest

from agentsteers.codex_readiness import (
    ExecutionGrant, LocalWorkerConfig, WorkerNotReady, verify_execution_grant,
)


class CodexReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.checkout = Path(self.temp.name) / "repo"
        self.checkout.mkdir()
        self.config = LocalWorkerConfig(
            checkout=self.checkout, expected_repository="scyllarusllc/agentsteers")
        self.grant = ExecutionGrant(
            task_id="task-1", subject="owner", repository="scyllarusllc/agentsteers",
            approval_id="a" * 32, approved_subject="owner",
            approved_repository="scyllarusllc/agentsteers", approved_task_id="task-1")

    def check(self, config=None, grant=None):
        return verify_execution_grant(
            config or self.config, grant or self.grant, current_subject="owner",
            allowed_repositories=frozenset({"scyllarusllc/agentsteers"}))

    def test_disabled_by_default(self):
        with self.assertRaisesRegex(WorkerNotReady, "disabled"):
            self.check()

    def test_mismatched_subject_rejected(self):
        with self.assertRaises(WorkerNotReady):
            self.check(replace(self.config, enabled=True),
                       replace(self.grant, approved_subject="someone-else"))

    def test_mismatched_task_rejected(self):
        with self.assertRaises(WorkerNotReady):
            self.check(replace(self.config, enabled=True),
                       replace(self.grant, approved_task_id="another-task"))

    def test_unlisted_repository_rejected(self):
        with self.assertRaises(WorkerNotReady):
            self.check(replace(self.config, enabled=True),
                       replace(self.grant, repository="other/repo"))

    def test_weak_approval_rejected(self):
        with self.assertRaises(WorkerNotReady):
            self.check(replace(self.config, enabled=True),
                       replace(self.grant, approval_id="yes"))

    def test_symlink_rejected(self):
        link = Path(self.temp.name) / "link"
        link.symlink_to(self.checkout, target_is_directory=True)
        with self.assertRaises(WorkerNotReady):
            self.check(replace(self.config, enabled=True, checkout=link))

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "non-root test")
    def test_valid_preflight_is_only_a_preflight(self):
        self.assertEqual(self.check(replace(self.config, enabled=True)),
                         self.checkout.resolve())


if __name__ == "__main__":
    unittest.main()
