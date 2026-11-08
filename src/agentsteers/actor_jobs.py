"""Actor-scoped, in-memory development task model.

Caller identity MUST be supplied by a verified authentication middleware, not a
tool argument. This class is not exposed as a remote MCP server and has no
connection to shell, network, Codex CLI, or filesystem.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4
import re

_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_MAX_INSTRUCTION = 2000


@dataclass(frozen=True)
class Principal:
    subject: str
    repositories: frozenset[str]
    can_submit: bool = False
    can_cancel: bool = False

    def __post_init__(self):
        if not self.subject or not self.subject.strip():
            raise ValueError("Verified subject required")


class ActorScopedMockJobs:
    """Mock-only bounded task store, never an authenticated network service."""

    def __init__(self, *, max_jobs: int = 1000):
        if max_jobs < 1:
            raise ValueError("max_jobs must be positive")
        self._jobs = {}
        self._lock = RLock()
        self._max_jobs = max_jobs

    def submit(self, principal: Principal, repository: str, instruction: str) -> dict:
        if not principal.can_submit:
            return {"ok": False, "error": "forbidden"}
        if not isinstance(repository, str) or not _REPO.fullmatch(repository) or repository not in principal.repositories:
            return {"ok": False, "error": "repository_not_allowed"}
        if not isinstance(instruction, str) or not instruction.strip() or len(instruction) > _MAX_INSTRUCTION:
            return {"ok": False, "error": "invalid_instruction"}
        with self._lock:
            if len(self._jobs) >= self._max_jobs:
                return {"ok": False, "error": "queue_full"}
            job_id = uuid4().hex
            self._jobs[job_id] = {
                "owner": principal.subject,
                "repository": repository,
                "status": "queued_mock",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "result": {"message": "Simulation only. No server or Codex invocation."},
            }
        return {"ok": True, "task_id": job_id, "status": "queued_mock"}

    def _owned(self, principal: Principal, job_id: str):
        job = self._jobs.get(job_id)
        # Do not reveal whether other users' job IDs exist.
        if job is None or job["owner"] != principal.subject or job["repository"] not in principal.repositories:
            return None
        return job

    def status(self, principal: Principal, job_id: str) -> dict:
        with self._lock:
            job = self._owned(principal, job_id)
            if job is None:
                return {"ok": False, "error": "task_not_found"}
            return {"ok": True, "task_id": job_id, "status": job["status"]}

    def result(self, principal: Principal, job_id: str) -> dict:
        with self._lock:
            job = self._owned(principal, job_id)
            if job is None:
                return {"ok": False, "error": "task_not_found"}
            return {"ok": True, "task_id": job_id, "status": job["status"], "result": dict(job["result"])}

    def cancel(self, principal: Principal, job_id: str) -> dict:
        with self._lock:
            job = self._owned(principal, job_id)
            if job is None:
                return {"ok": False, "error": "task_not_found"}
            if not principal.can_cancel:
                return {"ok": False, "error": "forbidden"}
            if job["status"] == "cancelled":
                return {"ok": True, "task_id": job_id, "status": "cancelled", "already_cancelled": True}
            if job["status"] != "queued_mock":
                return {"ok": False, "error": "not_cancellable"}
            job["status"] = "cancelled"
            job["result"] = {"message": "Mock task cancelled."}
            return {"ok": True, "task_id": job_id, "status": "cancelled"}
