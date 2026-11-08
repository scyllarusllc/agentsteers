"""Local-only shared task contract prototype for website and MCP adapters.

No network listener, OAuth, persistent queue or Codex execution is implemented.
Never expose this in-memory prototype as a production service.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from threading import RLock
from uuid import uuid4


class TaskState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class Task:
    id: str
    owner_id: str
    device_id: str
    project_id: str
    prompt: str
    state: TaskState = TaskState.QUEUED
    result: str | None = None


class TaskStore:
    """In-memory contract test double. NOT a production task queue."""

    def __init__(self):
        self._lock = RLock()
        self._devices: dict[str, str] = {}
        self._tasks: dict[str, Task] = {}

    def enroll_device(self, owner_id: str, device_id: str) -> None:
        if not owner_id or not device_id:
            raise ValueError("owner and device are required")
        with self._lock:
            existing = self._devices.get(device_id)
            if existing is not None and existing != owner_id:
                raise PermissionError("device already belongs to another owner")
            self._devices[device_id] = owner_id

    def create(self, owner_id: str, device_id: str, project_id: str, prompt: str) -> Task:
        if not all((owner_id, device_id, project_id, prompt.strip())):
            raise ValueError("owner, device, project and prompt are required")
        if len(prompt) > 12000:
            raise ValueError("prompt too long")
        with self._lock:
            if self._devices.get(device_id) != owner_id:
                raise PermissionError("device is not enrolled for owner")
            task = Task(str(uuid4()), owner_id, device_id, project_id, prompt)
            self._tasks[task.id] = task
            return task

    def get(self, owner_id: str, task_id: str) -> Task:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None or task.owner_id != owner_id:
                raise KeyError("task not found")
            return task

    def cancel(self, owner_id: str, task_id: str) -> Task:
        with self._lock:
            task = self.get(owner_id, task_id)
            if task.state in (TaskState.SUCCEEDED, TaskState.FAILED, TaskState.CANCELLED):
                return task
            updated = replace(task, state=TaskState.CANCELLED)
            self._tasks[task_id] = updated
            return updated

    def claim(self, owner_id: str, device_id: str, task_id: str) -> Task:
        """Test-only transition; production needs device authentication and claim leases."""
        with self._lock:
            task = self.get(owner_id, task_id)
            if task.device_id != device_id or self._devices.get(device_id) != owner_id:
                raise PermissionError("device mismatch")
            if task.state != TaskState.QUEUED:
                raise ValueError("task is not queued")
            updated = replace(task, state=TaskState.RUNNING)
            self._tasks[task_id] = updated
            return updated

    def finish(self, owner_id: str, device_id: str, task_id: str,
               *, success: bool, result: str) -> Task:
        """Test-only transition; never accept this from unauthenticated callers."""
        with self._lock:
            task = self.get(owner_id, task_id)
            if task.device_id != device_id or self._devices.get(device_id) != owner_id:
                raise PermissionError("device mismatch")
            if task.state != TaskState.RUNNING:
                raise ValueError("task is not running")
            updated = replace(task, state=TaskState.SUCCEEDED if success else TaskState.FAILED,
                              result=result[:16000])
            self._tasks[task_id] = updated
            return updated


class TaskEntryPoint:
    """Shared interface: website and MCP use the same owner-scoped operations.

    owner_id is injected by a future authenticated adapter; never trust it from
    arbitrary HTTP request bodies.
    """

    def __init__(self, store: TaskStore, owner_id: str):
        if not owner_id:
            raise ValueError("authenticated owner required")
        self._store = store
        self._owner = owner_id

    def create(self, device_id: str, project_id: str, prompt: str) -> Task:
        return self._store.create(self._owner, device_id, project_id, prompt)

    def status(self, task_id: str) -> Task:
        return self._store.get(self._owner, task_id)

    def result(self, task_id: str) -> str | None:
        return self.status(task_id).result

    def cancel(self, task_id: str) -> Task:
        return self._store.cancel(self._owner, task_id)
