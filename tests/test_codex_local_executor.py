"""Tests for the opt-in local Codex CLI runner. No Codex is launched."""
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from agentsteers.codex_readiness import (
    ExecutionGrant, LocalWorkerConfig, WorkerNotReady,
)
from agentsteers.codex_local_executor import LocalCodexRunner


class CodexLocalExecutorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.repo = root / "repo"
        self.repo.mkdir()
        self.binary = root / "codex"
        self.binary.write_text("#! /bin/sh\nexit 0\n")
        self.config = LocalWorkerConfig(
            checkout=self.repo, expected_repository="scyllarusllc/agentsteers",
            enabled=True,
        )
        self.grant = ExecutionGrant(
            task_id="t1", subject="owner", repository="scyllarusllc/agentsteers",
            approval_id="a" * 32, approved_subject="owner",
            approved_repository="scyllarusllc/agentsteers",
            approved_task_id="t1",
        )
        self.calls = []

        def fake_run(argv, **kwargs):
            self.calls.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 0, stdout='{"type":"done"}\n', stderr="")
        self.runner = LocalCodexRunner(binary=self.binary, run_process=fake_run)

    def invoke(self, **overrides):
        args = dict(
            config=self.config, grant=self.grant,
            current_subject="owner",
            allowed_repositories=frozenset({"scyllarusllc/agentsteers"}),
            instruction="Refactor the tests",
            approval_consumed=True,
        )
        args.update(overrides)
        with patch("agentsteers.codex_readiness.os.geteuid", return_value=12345), patch(
            "agentsteers.codex_readiness.Path.stat", autospec=True
        ) as stat_mock:
            # Preserve actual file attributes while substituting a non-root UID.
            real_stat = Path.stat
            def safe_stat(path, *a, **k):
                result = real_stat(path, *a, **k)
                values = list(result)
                values[4] = 12345
                return __import__("os").stat_result(values)
            stat_mock.side_effect = safe_stat
            return self.runner.run(**args)

    def test_real_codex_command_is_fixed_and_sandboxed(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 0)
        argv, kwargs = self.calls[0]
        self.assertEqual(argv[:2], [str(self.binary), "exec"])
        self.assertEqual(argv[argv.index("--sandbox") + 1], "workspace-write")
        self.assertEqual(argv[argv.index("--ask-for-approval") + 1], "never")
        self.assertEqual(argv[-1], "-")
        self.assertEqual(kwargs["input"], "Refactor the tests")
        self.assertEqual(kwargs["cwd"], str(self.repo))
        self.assertNotIn("AGENTSTEERS_FRAPPE_CLIENT_SECRET", kwargs["env"])

    def test_missing_approval_fails_before_spawn(self):
        with self.assertRaises(WorkerNotReady):
            self.invoke(approval_consumed=False)
        self.assertFalse(self.calls)

    def test_wrong_actor_fails_before_spawn(self):
        with self.assertRaises(WorkerNotReady):
            self.invoke(current_subject="different")
        self.assertFalse(self.calls)

    def test_prompt_validation_fails_before_spawn(self):
        with self.assertRaises(WorkerNotReady):
            self.invoke(instruction=" ")
        self.assertFalse(self.calls)

    def test_disabled_worker_fails_before_spawn(self):
        with self.assertRaises(WorkerNotReady):
            self.invoke(config=LocalWorkerConfig(
                checkout=self.repo, expected_repository="scyllarusllc/agentsteers",
                enabled=False,
            ))
        self.assertFalse(self.calls)


if __name__ == "__main__":
    unittest.main()
