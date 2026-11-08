"""Local-only, deny-by-default mock task worker.

This module deliberately does not invoke a shell, network, Codex CLI, or GitHub.
It is a demonstrator, not a production authorization boundary.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any

_ALLOWED_ACTIONS = frozenset({"mock.test", "mock.inspect"})
_IDENTIFIER = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")
_MAX_PAYLOAD_LENGTH = 2048


class TaskRejected(ValueError):
    """Task could not be executed safely."""


@dataclass(frozen=True)
class Task:
    task_id: str
    action: str
    repository: str
    approved_by: str | None = None
    payload: str = ""


@dataclass
class AuditLog:
    events: list[dict[str, Any]] = field(default_factory=list)

    def record(self, *, task_id: str, decision: str, detail: str) -> None:
        # Never log payloads, credentials, or arbitrary exception strings.
        self.events.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task_id": task_id if _IDENTIFIER.fullmatch(task_id) else "invalid-id",
            "decision": decision,
            "detail": detail,
        })


class DryRunWorker:
    def __init__(self, *, allowed_repositories: set[str], audit: AuditLog | None = None):
        if not allowed_repositories:
            raise ValueError("Must configure at least one allowed repository")
        self._allowed_repositories = frozenset(allowed_repositories)
        self.audit = audit if audit is not None else AuditLog()
        self._processed: set[str] = set()

    def run(self, task: Task) -> dict[str, str]:
        def reject(reason: str) -> None:
            self.audit.record(task_id=task.task_id, decision="denied", detail=reason)
            raise TaskRejected(reason)

        if not _IDENTIFIER.fullmatch(task.task_id):
            reject("invalid task ID")
        if task.task_id in self._processed:
            reject("duplicate task ID")
        if not task.approved_by or not _IDENTIFIER.fullmatch(task.approved_by):
            reject("approval required")
        if task.action not in _ALLOWED_ACTIONS:
            reject("action not allowlisted")
        if task.repository not in self._allowed_repositories:
            reject("repository not allowlisted")
        if not isinstance(task.payload, str) or len(task.payload) > _MAX_PAYLOAD_LENGTH:
            reject("invalid payload")

        # Deliberately only a simulated, deterministic action; no execution.
        digest = hashlib.sha256(task.payload.encode("utf-8")).hexdigest()
        self._processed.add(task.task_id)
        self.audit.record(task_id=task.task_id, decision="accepted", detail="mock execution only")
        return {"task_id": task.task_id, "status": "simulated", "action": task.action,
                "payload_sha256": digest}


def main() -> None:
    worker = DryRunWorker(allowed_repositories={"demo/example"})
    result = worker.run(Task(task_id="demo-001", action="mock.test", repository="demo/example", approved_by="demo-reviewer"))
    print(json.dumps({"result": result, "audit": worker.audit.events}, indent=2))


if __name__ == "__main__":
    main()
