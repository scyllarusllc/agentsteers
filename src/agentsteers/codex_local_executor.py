"""Opt-in local Codex CLI runner; NEVER expose this directly as an MCP tool.

A trusted caller must acquire/consume a durable, expiring, one-time approval
before calling run(). This module is *not* an authorization service, a job
queue, or a deployment recipe. Keep it disconnected from public HTTP routes.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import subprocess
from typing import Callable

from agentsteers.codex_readiness import (
    ExecutionGrant, LocalWorkerConfig, WorkerNotReady,
    verify_execution_grant,
)

MAX_PROMPT = 2000
MAX_OUTPUT = 16_384


@dataclass(frozen=True)
class CodexRunResult:
    returncode: int
    output: str


class LocalCodexRunner:
    """Run a real Codex CLI task only behind a trusted, isolated local caller.

    The host must separately provide process/container isolation, restricted
    network/filesystem access, resource limits, safe checkout provisioning,
    and durable audit/approval storage. Codex's workspace-write policy is
    defense-in-depth, not a substitute for a host-level sandbox.
    """

    def __init__(self, *, binary: Path, timeout_seconds: int = 300,
                 run_process: Callable = subprocess.run):
        if not binary.is_absolute():
            raise ValueError("Codex binary must have an absolute path")
        if not (1 <= timeout_seconds <= 1800):
            raise ValueError("Invalid timeout")
        self.binary = binary
        self.timeout_seconds = timeout_seconds
        self._run_process = run_process

    def run(self, *, config: LocalWorkerConfig, grant: ExecutionGrant,
            current_subject: str, allowed_repositories: frozenset[str],
            instruction: str, approval_consumed: bool) -> CodexRunResult:
        # approval_consumed MUST be derived from trusted server storage.
        # Never pass a client-supplied Boolean through this boundary.
        if approval_consumed is not True:
            raise WorkerNotReady("trusted one-time approval not consumed")
        if not isinstance(instruction, str) or not instruction.strip() or len(instruction) > MAX_PROMPT:
            raise WorkerNotReady("invalid task instruction")
        checkout = verify_execution_grant(
            config, grant, current_subject=current_subject,
            allowed_repositories=allowed_repositories,
        )
        if not self.binary.is_file() or self.binary.is_symlink():
            raise WorkerNotReady("trusted Codex binary unavailable")

        # No shell, no arbitrary flags, no user-controlled executable/cwd.
        argv = [
            str(self.binary), "exec", "--sandbox", "workspace-write",
            "--ask-for-approval", "never", "--cd", str(checkout),
            "--json", "-",
        ]
        # A dedicated non-root OS account and isolated CODEX_HOME should
        # provision these variables. Do not inherit application secrets.
        env = {k: os.environ[k] for k in ("PATH", "HOME", "CODEX_HOME", "TMPDIR")
               if k in os.environ}
        env["GIT_TERMINAL_PROMPT"] = "0"
        try:
            outcome = self._run_process(
                argv, input=instruction, text=True, cwd=str(checkout),
                env=env, capture_output=True, timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise WorkerNotReady("Codex task timeout") from exc
        except OSError as exc:
            raise WorkerNotReady("Codex launch failed") from exc
        # Never return raw stderr or environment diagnostics.
        output = outcome.stdout or ""
        if len(output) > MAX_OUTPUT:
            output = output[:MAX_OUTPUT] + "\n[output truncated]"
        return CodexRunResult(returncode=outcome.returncode, output=output)
