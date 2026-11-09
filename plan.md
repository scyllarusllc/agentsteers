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
- `src/agentsteers/mock_http_mcp.py` implements a separate opt-in bearer-token protected WSGI Mock MCP app with four tools and no Codex execution; `tests/test_mock_http_mcp.py` contains offline test cases. Source presence is **not** proof that tests passed or the service is running.

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

Run the offline tests and verify this standalone Mock MCP deployment with authorized server access. The website deployment does not start this WSGI app, and an HTTP handshake does not verify ChatGPT Voice compatibility.

## Website MCP navigation (2026-11-09)

- The shared Frappe site header now links to `/mcp-connection` on every page.
- The page is informational: it displays **Not verified**, never claims an active MCP session, and does not accept or expose credentials.
- Website authentication is separate from MCP authorization. The mock HTTP server and public reverse-proxy activation remain independent follow-up work.
- Deploy the website update separately, then verify the new route and responsive shared header. No automatic deployment is performed by GitHub commits.

## Mock MCP launch checklist (operator-run; not deployed by this commit)

**Prerequisites:** an authorized Linux host, DNS and a valid TLS certificate for `mcp.agentsteers.com`, a dedicated non-root service account, an up-to-date repository checkout and isolated Python environment with `gunicorn` installed. Keep the current website service unchanged. Do not put secrets in the repo, shell history, GitHub Actions logs or the MCP Connection webpage.

1. Update the server checkout to the reviewed `main` commit. As the non-root service user, run offline tests before enabling anything:

   ```sh
   PYTHONPATH=src python -m unittest discover -s tests -p 'test_mock_http_mcp.py' -v
   PYTHONPATH=src python -m unittest discover -s tests -p 'test_remote_mcp_guard.py' -v
   ```

   Record results; do not infer a pass from the presence of test files.

2. Generate a fresh random Bearer Token on the server (`python -c 'import secrets; print(secrets.token_urlsafe(48))'`) and place it in a private service environment/secret file readable only by the service owner. Never paste the actual token in a public page or a support conversation. Configure the service environment:

   ```text
   AGENTSTEERS_MCP_MOCK_ENABLED=1
   AGENTSTEERS_MCP_MOCK_TOKEN=<server-generated-secret>
   AGENTSTEERS_MCP_MOCK_HOST=mcp.agentsteers.com
   AGENTSTEERS_MCP_MOCK_REPOS=scyllarusllc/agentsteers
   ```

   The placeholders must be replaced in the private configuration; they are not a ready-to-run shell command.

3. Start the **separate** app as the dedicated non-root account, using that service environment and the correct repository checkout:

   ```sh
   PYTHONPATH=src gunicorn --bind 127.0.0.1:8766 --workers 1 \
     --access-logfile - agentsteers.mock_http_mcp:application
   ```

   Use exactly one worker for this in-memory proof of concept: multiple workers do **not** share task state, and process restarts lose all mock tasks. Keep the backend port bound to loopback only. Use a supervised service for reboot recovery; this foreground example is a smoke test, not a permanent production unit.

4. **Only after the tests pass and the local process is healthy**, replace the **separate MCP domain's** prelaunch 503 block with a reviewed Caddy configuration equivalent to:

   ```caddyfile
   mcp.agentsteers.com {
       encode zstd gzip
       handle /mcp {
           reverse_proxy 127.0.0.1:8766
       }
       respond 404
   }
   ```

   Preserve the original Host header and trusted HTTPS forwarding; ensure Gunicorn only trusts forwarded scheme headers from loopback. Validate the Caddy configuration before reload. Do not add a proxy rule to the main website domain or expose port 8766 publicly. Do not switch the route until the service configuration and tests are checked.

5. From an authorized test client, check that `POST https://mcp.agentsteers.com/mcp` returns **401 without a token**. With the Bearer token and `Accept: application/json, text/event-stream`, send an MCP JSON-RPC `initialize` request, then `tools/list`; expect four named tools: `submit_task`, `get_task_status`, `get_task_result`, `cancel_task`. Exercise one complete mock task lifecycle, including cancellation, and verify no Codex/shell/Git operation occurred. Avoid writing token-bearing commands to shell history.

6. Report the page status as **Not verified** until live endpoint and client compatibility have actually been tested. This static page does not measure connectivity or accept a token. Test ChatGPT plugin and Voice separately; bearer-token support in the intended ChatGPT client is not assumed. For real worker execution, replace the shared mock token with actor-scoped OAuth and authorization.

**Rollback:** restore `deploy/Caddyfile.prelaunch` (503) for the MCP hostname, validate and reload Caddy, then stop the dedicated Mock MCP process. This does not require taking the AgentSteers website offline.

**Important:** This checklist is deployment guidance, not an assertion of live service, completed testing, or permission to execute Codex.
