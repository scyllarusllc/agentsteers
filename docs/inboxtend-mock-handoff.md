# Inbox Tend → AgentSteers mock-only task handoff

**Status:** code contract documented, **not deployed or end-to-end verified**. No Codex, shell, production deployment, or email operation is enabled by this handoff.

Inbox Tend is a separate self-hosted email/task application. It can submit a **reviewed task title and description** to AgentSteers' existing authenticated **mock MCP** endpoint. It must never treat an email or attachment as authorization to execute code.

## Wire contract

The existing `src/agentsteers/mock_http_mcp.py` implements JSON-RPC at `POST /mcp` with required HTTPS, configured Host, a long bearer token, and a repository allowlist. Nothing is exposed unless the mock service is explicitly enabled.

| Action | JSON-RPC method | Required arguments | Response |
|---|---|---|---|
| Authenticated connectivity check | `ping` | none | `{"result":{}}` |
| Submit reviewed mock task | `tools/call` → `submit_task` | `repository`, `instruction` | content JSON with `ok`, `task_id`, `status:queued_mock` |
| Read mock status | `tools/call` → `get_task_status` | `task_id` | `queued_mock` or `cancelled` (when applicable) |
| Read simulated result | `tools/call` → `get_task_result` | `task_id` | explanatory mock result, not a real execution artifact |

By default this is a **bounded in-memory simulation**; a restarted service or a separate worker process does not retain/see existing job IDs unless the separately configured private SQLite mock store is in use. `queued_mock` is not `done` or `succeeded`. Do not invent a completion transition.

## Deployment boundary

A server operator would separately need to enable the AgentSteers mock WSGI endpoint and configure these **private** environment variables (placeholders, never actual credentials in Git):

- `AGENTSTEERS_MCP_MOCK_ENABLED=1`
- `AGENTSTEERS_MCP_MOCK_HOST=<exact-trusted-https-host>`
- `AGENTSTEERS_MCP_MOCK_TOKEN=<private-random-token-at-least-32-chars>`
- `AGENTSTEERS_MCP_MOCK_REPOS=scyllarusllc/agentsteers`

The Inbox Tend operator must independently configure the matching bearer token, HTTPS `/mcp` URL, and allowlisted repository via `INBOX_TEND_AGENTSTEERS_*` as described in its [integration guide](https://github.com/scyllarusllc/inboxtend/blob/main/docs/agentsteers-handoff.md).

**Do not expose a private listener or promote this to a live executable task runner merely to make the demonstration work.** Real deployment, OAuth authorization, separate actor identity, persistence, and remote worker isolation require independent verification and approval. The mock bearer-token identity is a **single simulated actor**, not user-specific OAuth.

## Optional persistent mock task storage (source implemented, not deployed)

AgentSteers now provides `src/agentsteers/persistent_mock_jobs.py`, an opt-in SQLite store for mock task IDs, statuses, owners, repository scopes and simulated results. The mock WSGI adapter uses it **only when** `AGENTSTEERS_MCP_MOCK_DB` is set to a private **absolute path** (for example, `/srv/agentsteers-private/mock-jobs.sqlite3`). The parent directory must not be group/world writable, and the database file must have private permissions. Provision storage and encrypted backups outside Git, on a separately authorized host; do not configure or publish a database credential or user correspondence.

- With this setting **unset**, the legacy in-memory mock backend remains in use and restart loses its jobs.
- With this setting **configured**, the adapter fails closed if SQLite storage is invalid or unavailable; it does not silently fall back to memory.
- Jobs can be queried after a process restart as long as the same database file and mock actor identity are used. Jobs remain `queued_mock` unless explicitly cancelled. Persistence **does not run a worker, complete tasks, or guarantee production recovery**.
- The current bearer-token mock MCP identity is shared and **not suitable for multi-user production workloads**; implement identity-bound OAuth authorization and stronger isolation before any real worker deployment.
- Inbox Tend retains its own task ID and remote job ID in its SQLite task record. If the remote job cannot be found after a restart or storage migration, Inbox Tend should display a **recovery-needed** state rather than interpreting it as completion or retrying dispatch.

## What the UI does

Inbox Tend offers mock dispatch from the task list **and** the expanded task details. Both require a signed-in user, CSRF protection, an explicit confirmation, and a reviewed task. The UI can request an authenticated read-only `ping` without creating a task. After a successful check it can refresh **one queued mock task per minute while the browser page is visible**, stopping after a connection failure. These are application UI behavior claims based on the source, **not a claim that the remote service has been reached**.

A fictional university student-registration-page email and local task are provided by Inbox Tend's demo seed. There is no actual Gmail fetch, code edit, or deployment from this mock workflow.

## Further engineering gates

1. Provision private host configuration and an isolated HTTPS **mock-only** endpoint, if explicitly authorized.
2. Confirm one authenticated ping, one manually approved mock submission, and status ownership isolation; never send secrets into logs.
3. Add a persistent task store and authenticated per-user scoping before scaling beyond the isolated prototype.
4. Treat real Codex execution as a **separate** later feature with scoped access, independent approval, isolation, and auditability.

This documentation does not request or imply an automated deployment or test-suite run.
