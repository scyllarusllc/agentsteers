"""Local-only authenticated mock task dispatcher; no network or shell."""
from __future__ import annotations

from typing import Collection

from agentsteers.actor_jobs import ActorScopedMockJobs, Principal as JobPrincipal
from agentsteers.oauth_security import ACTION_SCOPE, AuthorizationError


class AuthenticatedMockTaskService:
    """Bridge verified identities to isolated mock tasks.

    The repository allowlist is server-owned. This does not enable HTTP OAuth,
    persistent jobs, Codex CLI, or any external execution.
    """

    def __init__(self, *, verifier, repositories: Collection[str], jobs=None):
        self._verifier = verifier
        self._repositories = frozenset(repositories)
        if not self._repositories:
            raise ValueError("Server-side repository allowlist required")
        self._jobs = jobs if jobs is not None else ActorScopedMockJobs()

    def dispatch(self, authorization_header: str | None, action: str, **kwargs) -> dict:
        principal = self._verifier.verify(authorization_header)
        scope = ACTION_SCOPE.get(action)
        if scope is None or scope not in principal.scopes:
            raise AuthorizationError("Action not permitted")
        actor = JobPrincipal(
            subject=principal.subject,
            repositories=self._repositories,
            can_submit="agentsteers:submit" in principal.scopes,
            can_cancel="agentsteers:cancel" in principal.scopes,
        )
        if action == "submit_task":
            if set(kwargs) != {"repository", "instruction"}:
                raise AuthorizationError("Invalid task arguments")
            return self._jobs.submit(actor, kwargs["repository"], kwargs["instruction"])
        if set(kwargs) != {"task_id"} or not isinstance(kwargs["task_id"], str):
            raise AuthorizationError("Invalid task arguments")
        if action == "get_task_status":
            return self._jobs.status(actor, kwargs["task_id"])
        if action == "get_task_result":
            return self._jobs.result(actor, kwargs["task_id"])
        if action == "cancel_task":
            return self._jobs.cancel(actor, kwargs["task_id"])
        raise AuthorizationError("Action not permitted")
