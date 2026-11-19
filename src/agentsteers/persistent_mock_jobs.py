"""Optional persistent, mock-only task state for the AgentSteers MCP adapter.

No worker, shell, Codex or executable actions. Records task metadata/results
only. SQLite connections are short-lived so separate WSGI workers can see the
same store. Caller identity must come from trusted MCP authentication.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
import os
from pathlib import Path
import re
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from agentsteers.actor_jobs import Principal

REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
TASK_ID = re.compile(r"^[a-f0-9]{32}$")


class PersistentMockJobs:
    def __init__(self, path: str, *, max_jobs: int = 1000):
        target = Path(path)
        if not target.is_absolute() or target.is_symlink() or max_jobs < 1:
            raise ValueError("Private absolute SQLite path required")
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if target.parent.stat().st_mode & 0o022:
            raise ValueError("Mock job directory must not be group/world writable")
        self.path = target
        self.max_jobs = max_jobs
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS mock_jobs (
                id TEXT PRIMARY KEY,
                owner TEXT NOT NULL,
                repository TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('queued_mock','cancelled')),
                result TEXT NOT NULL,
                created_at TEXT NOT NULL
            )""")

    @contextmanager
    def _db(self):
        # This is not a mailbox or user file store. Keep mock task data private.
        # Existing files must be owned/protected by the deployment operator.
        if self.path.exists() and (self.path.is_symlink() or self.path.stat().st_mode & 0o077):
            raise ValueError("Mock job file permissions are too broad")
        # Create the file with private permissions before opening SQLite.
        # Do not change permissions on an existing file that might be unsafe.
        if not self.path.exists():
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            try:
                fd = os.open(self.path, flags, 0o600)
                os.close(fd)
            except FileExistsError:
                pass  # A parallel worker may have created the same file.
        if self.path.is_symlink() or (self.path.stat().st_mode & 0o077):
            raise ValueError("Mock job file permissions are too broad")
        connection = sqlite3.connect(str(self.path), timeout=5, isolation_level=None)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA busy_timeout=5000")
            yield connection
        finally:
            connection.close()

    @staticmethod
    def _owned(db, principal: Principal, job_id: str):
        if not isinstance(job_id, str) or not TASK_ID.fullmatch(job_id):
            return None
        row = db.execute("SELECT * FROM mock_jobs WHERE id=? AND owner=?",
                         (job_id, principal.subject)).fetchone()
        if row is None or row["repository"] not in principal.repositories:
            return None
        return row

    def submit(self, principal: Principal, repository: str, instruction: str):
        if not principal.can_submit:
            return {"ok": False, "error": "forbidden"}
        if not isinstance(repository, str) or not REPO.fullmatch(repository) or repository not in principal.repositories:
            return {"ok": False, "error": "repository_not_allowed"}
        if not isinstance(instruction, str) or not instruction.strip() or len(instruction) > 2000:
            return {"ok": False, "error": "invalid_instruction"}
        job_id = uuid4().hex
        with self._db() as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                count = db.execute("SELECT COUNT(*) FROM mock_jobs").fetchone()[0]
                if count >= self.max_jobs:
                    db.execute("ROLLBACK")
                    return {"ok": False, "error": "queue_full"}
                db.execute("""INSERT INTO mock_jobs(id,owner,repository,state,result,created_at)
                    VALUES (?,?,?,?,?,?)""",
                    (job_id, principal.subject, repository, "queued_mock",
                     json.dumps({"message": "Simulation only. No server or Codex invocation."}),
                     datetime.now(timezone.utc).isoformat()))
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise
        return {"ok": True, "task_id": job_id, "status": "queued_mock"}

    def status(self, principal: Principal, job_id: str):
        with self._db() as db:
            row = self._owned(db, principal, job_id)
        if row is None:
            return {"ok": False, "error": "task_not_found"}
        return {"ok": True, "task_id": job_id, "status": row["state"]}

    def result(self, principal: Principal, job_id: str):
        with self._db() as db:
            row = self._owned(db, principal, job_id)
        if row is None:
            return {"ok": False, "error": "task_not_found"}
        return {"ok": True, "task_id": job_id, "status": row["state"],
                "result": json.loads(row["result"])}

    def cancel(self, principal: Principal, job_id: str):
        if not principal.can_cancel:
            return {"ok": False, "error": "forbidden"}
        with self._db() as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                row = self._owned(db, principal, job_id)
                if row is None:
                    db.execute("ROLLBACK")
                    return {"ok": False, "error": "task_not_found"}
                if row["state"] == "cancelled":
                    db.execute("ROLLBACK")
                    return {"ok": True, "task_id": job_id, "status": "cancelled", "already_cancelled": True}
                db.execute("UPDATE mock_jobs SET state='cancelled',result=? WHERE id=?",
                           (json.dumps({"message": "Mock task cancelled."}), job_id))
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise
        return {"ok": True, "task_id": job_id, "status": "cancelled"}
