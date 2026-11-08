"""In-memory mock task lifecycle; no Codex, shell, network or remote execution."""
from __future__ import annotations
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4
import re

_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_MAX_TEXT = 2000

class MockTaskService:
    def __init__(self, allowed_repositories: set[str]):
        self.allowed_repositories = frozenset(allowed_repositories)
        self._tasks: dict[str, dict] = {}
        self._lock = RLock()

    def submit_task(self, repository: str, instruction: str, approved: bool = False) -> dict:
        if not approved:
            return {"ok": False, "error": "explicit_approval_required"}
        if not isinstance(repository, str) or not _REPO.fullmatch(repository) or repository not in self.allowed_repositories:
            return {"ok": False, "error": "repository_not_allowed"}
        if not isinstance(instruction, str) or not instruction.strip() or len(instruction) > _MAX_TEXT:
            return {"ok": False, "error": "invalid_instruction"}
        task_id = uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        task = {"task_id": task_id, "repository": repository, "status": "queued_mock", "created_at": now,
                "result": {"message": "Mock task accepted. No Codex or server command was executed."}}
        with self._lock:
            self._tasks[task_id] = task
        return {"ok": True, "task_id": task_id, "status": task["status"]}

    def get_task_status(self, task_id: str) -> dict:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return {"ok": False, "error": "task_not_found"}
            return {"ok": True, "task_id": task_id, "status": task["status"], "created_at": task["created_at"]}

    def get_task_result(self, task_id: str) -> dict:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return {"ok": False, "error": "task_not_found"}
            return {"ok": True, "task_id": task_id, "status": task["status"], "result": dict(task["result"])}

    def cancel_task(self, task_id: str) -> dict:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return {"ok": False, "error": "task_not_found"}
            if task["status"] == "cancelled":
                return {"ok": True, "task_id": task_id, "status": "cancelled", "already_cancelled": True}
            if task["status"] != "queued_mock":
                return {"ok": False, "error": "task_not_cancellable"}
            task["status"] = "cancelled"
            task["result"] = {"message": "Mock task cancelled."}
            return {"ok": True, "task_id": task_id, "status": "cancelled"}
