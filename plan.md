# AgentSteers Development Plan

Updated: 2026-11-09 (Saipan time)

## Goal

ChatGPT Voice -> authenticated AgentSteers MCP over HTTPS -> actor-scoped tasks -> isolated Codex CLI worker -> status/results back to ChatGPT.

## Current verified state

- Frappe website and shared navigation are implemented separately from MCP deployment.
- `deploy/embedded_mcp_wsgi.py` provides an opt-in, disabled-by-default preflight `/mcp` WSGI endpoint. It supports initialize/ping/tools-list with an empty tool list. It does **not** run tasks or Codex.
- Local stdio mock task tools and an actor-scoped in-memory mock task store exist. They are not deployed remotely.
- `src/agentsteers/remote_mcp_guard.py` is an opt-in authentication boundary, **not wired to the public route**.
- `deploy/Caddyfile.prelaunch` intentionally returns HTTP 503. No verified public MCP endpoint or ChatGPT Voice integration yet.

## Agreed fast-path: PUBLIC MOCK-ONLY MCP TEST

The owner approved a public HTTPS test endpoint secured with a generated Bearer token. A production OAuth rollout is **not** required for this isolated *mock-only* milestone. Do not conflate this token-only test with production OAuth or with actual server authorization.

1. Build a **separate, opt-in** test MCP HTTP application with `submit_task`, `get_task_status`, `get_task_result`, and `cancel_task`. Back it with mock-only tasks; never call shell, Codex, Git write tools, Frappe production data, or network task execution.
2. Reject absent/incorrect tokens, untrusted hosts/origins, invalid methods, oversized requests and invalid JSON-RPC. Generate a cryptographically random token **on the deployment host**, store it only in a protected environment/secret store, and never commit or log it. Apply request limits and bound task storage.
3. Verify with offline protocol tests, auth-negative tests, task lifecycle, and task ownership/isolation tests. Test independent of production website and preserve its existing login state.
4. Prepare a dedicated HTTPS reverse proxy route for `mcp.agentsteers.com/mcp` forwarding only to a loopback-bound test process; keep the prelaunch 503 configuration until the host, DNS, TLS, secrets, and application have been checked. Do **not** expose backend ports or make existing website routes public.
5. Deploy the mock service only with confirmed authorized server access and owner-approved deployment change. Verify 401 without token, MCP initialize and tools/list with token, submit/status/result/cancel with token, and no real execution. Document how to disable the public route quickly.
6. Separately validate whether the user's ChatGPT Voice/Plugin environment supports invoking this custom MCP endpoint. A curl/MCP smoke test by itself is not proof of Voice support.

## Beyond the public mock milestone

- Replace dev bearer-token authentication with a real OAuth resource server for any write-capable worker: issuer/audience/JWKS, server-side scope/repo policy, actor ownership, revocation strategy, rate limits, audited jobs, durable queue, redacted logs.
- Connect Codex CLI **only after** an isolated non-root worker with restricted repository scope, time/resource limits, no production credentials, and cancellation has been tested.
- Never treat a client-supplied `approved=true` as real authorization.
- Do not auto-deploy, edit production records, or expose a generic shell tool.
- Voice -> MCP -> actual Codex -> result is a separate end-to-end acceptance milestone.

## Workflow

- Ordinary repository development: direct commits to `main` without pull requests, as requested.
- Production deployment remains a separate operation. GitHub changes do not imply server deployment.
- Report only confirmed test results, commits, and live connectivity; never describe mock success as Codex execution.

## Next implementation step

Add the mock-only, token-protected HTTP application and its negative tests while leaving production Caddy and `/mcp` routing disabled. Then prepare opt-in deployment instructions and run the offline test suite.
