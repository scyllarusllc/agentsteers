"""Fail-closed preflight for the future local Codex worker.

This module performs validation only. It MUST NOT be connected to a public MCP
tool until authenticated job ownership and a reviewed isolated executor exist.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import stat

_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_APPROVAL = re.compile(r"^[a-f0-9]{32,128}$")


class WorkerNotReady(RuntimeError):
    """Refuse execution until deployment and authorization gates are satisfied."""


@dataclass(frozen=True)
class ExecutionGrant:
    task_id: str
    subject: str
    repository: str
    approval_id: str
    approved_subject: str
    approved_repository: str
    approved_task_id: str


@dataclass(frozen=True)
class LocalWorkerConfig:
    checkout: Path
    expected_repository: str
    enabled: bool = False


def verify_execution_grant(config: LocalWorkerConfig, grant: ExecutionGrant,
                           *, current_subject: str, allowed_repositories: frozenset[str]) -> Path:
    """Validate an independently persisted server-side grant, not client approval flags.

    The caller MUST obtain grant from trusted server storage and validate expiry,
    one-time consumption and approver identity before invoking this preflight.
    A successful result is NOT authorization to execute by itself.
    """
    if not config.enabled:
        raise WorkerNotReady("real Codex worker disabled")
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        raise WorkerNotReady("root execution prohibited")
    if (not _REPO.fullmatch(grant.repository) or
            not _REPO.fullmatch(config.expected_repository) or
            grant.repository != config.expected_repository or
            grant.repository not in allowed_repositories):
        raise WorkerNotReady("repository not permitted")
    if (not grant.task_id or not grant.subject or
            grant.subject != current_subject or
            grant.approved_subject != grant.subject or
            grant.approved_repository != grant.repository or
            grant.approved_task_id != grant.task_id or
            not _APPROVAL.fullmatch(grant.approval_id)):
        raise WorkerNotReady("missing or mismatched server-side approval")
    checkout = config.checkout
    if not checkout.is_absolute() or checkout.is_symlink():
        raise WorkerNotReady("checkout path must be absolute and not a symlink")
    try:
        info = checkout.stat()
        real_path = checkout.resolve(strict=True)
    except OSError as exc:
        raise WorkerNotReady("checkout unavailable") from exc
    if (not stat.S_ISDIR(info.st_mode) or
            (hasattr(os, "geteuid") and info.st_uid != os.geteuid()) or
            bool(info.st_mode & stat.S_IWOTH)):
        raise WorkerNotReady("unsafe checkout owner or permissions")
    # No command is run and no network access occurs.
    return real_path
