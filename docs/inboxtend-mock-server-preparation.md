# Inbox Tend ↔ AgentSteers: mock MCP server preparation

**Status: documentation and source only — not installed, connected, authenticated end-to-end, or deployed.**
This runbook describes a manually approved **mock-only** endpoint for Inbox Tend. It does not start Codex, execute user-provided commands, change GitHub repositories, read mailbox data or send email. The server operator must own the host and review each action.

## Existing pieces

- AgentSteers already implements a bearer-authenticated mock JSON-RPC endpoint at `src/agentsteers/mock_http_mcp.py`: `ping`, `submit_task`, `get_task_status`, `get_task_result`, and `cancel_task`.
- `src/agentsteers/persistent_mock_jobs.py` optionally stores mock jobs in private SQLite. Without `AGENTSTEERS_MCP_MOCK_DB`, the legacy in-memory queue is lost across process restarts.
- The repository's `deploy/Caddyfile.mock-mcp` is a **reference only**, not evidence that `mcp.agentsteers.com` actually routes to a running service. Existing Caddy could be under a different management system; never overwrite another application's configuration.
- `deploy/agentsteers-mock-mcp.service.example` is an **uninstalled** example for a dedicated non-root systemd service. Adjust all paths and identities to the authorized host before considering installation.
- Inbox Tend already has an opt-in bridge with manual connectivity check, explicit dispatch confirmation, remote-job-ID storage and a **recovery_needed** state for a missing remote job.

## Planned private configuration

**Never commit actual secrets.** If an operator expressly authorizes a deployment, create a protected file **on the server**, e.g. `/etc/agentsteers/mock-mcp.env`, mode `0600`, visible only to the dedicated service operator as appropriate. Use actual privately provisioned hostnames and tokens, not these placeholders.

```ini
AGENTSTEERS_MCP_MOCK_ENABLED=1
AGENTSTEERS_MCP_MOCK_HOST=YOUR_APPROVED_MCP_HOSTNAME
AGENTSTEERS_MCP_MOCK_REPOS=scyllarusllc/agentsteers
AGENTSTEERS_MCP_MOCK_DB=/var/lib/agentsteers-mock/jobs.sqlite3
AGENTSTEERS_MCP_MOCK_TOKEN=REPLACE_WITH_PRIVATE_RANDOM_TOKEN_AT_LEAST_32_CHARACTERS
```

The corresponding private Inbox Tend configuration uses `INBOX_TEND_AGENTSTEERS_BRIDGE_ENABLED=1`, the **same** token, the exact `https://YOUR_APPROVED_MCP_HOSTNAME/mcp` endpoint, and the same allowlisted repository. Never expose the token to the browser, README, issue, analytics, or access logs. Rotate both sides together; an unauthorized or stale token must fail closed.

## Read-only operator preflight (not run against any server here)

A new source-only utility is available at [`scripts/check_mock_mcp_host.py`](../scripts/check_mock_mcp_host.py). On the **authorized target host**, an operator can run:

```sh
python3 scripts/check_mock_mcp_host.py
```

It prints a **local-only JSON report** for the current Unix account, relevant repository files, optional venv Gunicorn, Caddy binary presence, mock environment variable *syntax* (never their secret values), private SQLite file/directory permissions, and an informational TCP listener lookup for port 8766. It **does not connect to a server**, alter any file, start a process, invoke a worker, run a test suite, or approve deployment.

The script reads environment variables from its **current process only**; systemd EnvironmentFile values are not automatically available to a manual shell. Consequently missing variables in a shell can be informational even if a future service unit is configured. A `ready: true` response would still **not prove** correct TLS, login, network firewall, task ownership or service availability. Review the report manually; never paste or commit private configuration into the repository.

## Server preparation checklist (not performed)

1. **Host and identity:** Confirm ownership, actual server path, dedicated non-root Unix user and group, host firewall, DNS, proxy implementation and Caddy ownership. Do not infer access from the existence of a GitHub repository.
2. **Isolation and storage:** Provision a private state directory not writable by other users. A systemd `StateDirectory=agentsteers-mock` can create `/var/lib/agentsteers-mock` for the service owner. The SQLite store needs a private file and private backups; do not use a public web directory. Keep the working directory readable but application code read-only at runtime.
3. **Private service:** Review the example systemd unit against the actual host and dependency install before copying or enabling it. Gunicorn must listen on **127.0.0.1:8766 only**, with no public firewall exposure. The unit runs **one worker**, and uses the same private persistent DB after restarts.
4. **HTTPS gateway:** Preserve existing Caddy routes. Only after separate approval, adapt the reference `deploy/Caddyfile.mock-mcp` for the approved hostname and correct reverse-proxy trust boundary. The backend checks the exact host, HTTPS request scheme and bearer token. TLS proxy must correctly pass the trusted scheme and Host; never trust arbitrary external `X-Forwarded-Proto` headers.
5. **Manual gates before enabling access:** Inspect the candidate systemd config, private file modes, Caddy syntax, firewall and existing virtual hosts. Independently verify authenticated `ping`, rejection of wrong token/host, repository allowance, task ownership, persistence after restart and inability to perform real execution. Those checks **have not been run** by the assistant.
6. **Inbox Tend:** Only after the mock endpoint is independently approved and enabled, privately configure the bridge and use its **Check AgentSteers connection** action. A successful `ping` confirms only that the mock service responded with the supplied credentials; it does **not** prove remote code execution.
7. **Rollback:** Disable the mock service and restore only the owned route/configuration without disturbing other sites. Preserve the private SQLite file during rollback for later reconciliation. Do not delete a database or auto-resubmit tasks merely because the endpoint is unavailable.

## Explicit limitations

- The bearer token maps to a **single shared mock principal**. This is not multi-user OAuth or production-grade agent authorization.
- Job states are `queued_mock` and `cancelled`; a queued state is **not a completed task**.
- Persistent SQLite supports reading the **same** mock task after process restart when the same database and principal are used. It is not a distributed queue or a high-availability guarantee.
- Inbox Tend's `recovery_needed` status means a remote task ID was not found; the correct response is **manual reconciliation**, not automatic duplicate dispatch.
- Running the legacy temporary `make mcp` script may change proxy routes after explicit interactive approval. It is **not** a persistent deployment method and must not be run as an unattended rollout.
- The user requested **no test-suite execution** during this development stage. Source inspection and GitHub file verification are not claims of working server behavior. A future public launch must still undergo the necessary independent safety checks, with the owner's permission.

**Next gate:** actual host access, its route topology, privately provisioned credentials and separately authorized server changes. No deployment has been initiated here.
