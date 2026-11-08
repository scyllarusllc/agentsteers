# AgentSteers deployment plan — single cloud server

**Target:** ChatGPT Voice on iPad → private AgentSteers plugin → https://mcp.agentsteers.com/mcp → AgentSteers → restricted *local* Codex CLI on the SAME cloud server → results back to the plugin.

**Current state:** preparation only. No claim that the domain, server, OAuth, Plugin binding, or Codex is deployed or operational. The existing loopback development server must NEVER be put behind the public hostname.

## DNS and HTTPS preparation

1. Confirm ownership/control of `agentsteers.com` at the DNS provider. Do not assume ownership from the project name.
2. Select an explicitly authorized Linux host and verify that DNS can resolve `mcp.agentsteers.com` to its public IP: create an **A** record (and **AAAA** only if working IPv6 is configured). Do not invent an IP address.
3. Configure a firewall permitting inbound TCP 443 (and TCP 80 for certificate issuance where required), limiting SSH to authorized administration. Never expose the MCP backend's port to the Internet.
4. Install and validate Caddy. Start with `deploy/Caddyfile.prelaunch`: HTTPS front door responds **503** intentionally. It does not proxy any MCP traffic. Confirm `curl -i https://mcp.agentsteers.com/mcp` returns 503 (after DNS + HTTPS are configured).
5. Only switch from maintenance mode after completing the security gates below and running integration tests. A 503 is the expected prelaunch behavior, not proof of MCP functionality.

## Authenticated MCP release gates

- Configure a recognized OAuth/OIDC authorization provider and a **distinct** MCP resource audience. Google Sign-In can identify the owner, but does not alone authorize MCP task execution. Validate issuer, signature/JWKS, expiry, audience, scopes, and token revocation/expiry; never accept a client-supplied `approved=true` as authorization.
- Implement the MCP authorization flow needed by ChatGPT, including protected-resource metadata and token challenge/discovery as required by the chosen provider. Verify the Plugin's client compatibility rather than assuming it.
- Bind every task to the authenticated actor and current repo-scoped permissions; protect status/result/cancellation against cross-user access.
- Persist jobs, add throttling/size limits and redacted audit records, and reject unauthenticated requests before any task side effect.
- Ensure HTTPS, allowlisted Host/Origin, non-root isolated worker, secret handling and cancellation are working and tested.
- Bind the private AgentSteers Plugin to the **verified** `https://mcp.agentsteers.com/mcp` endpoint only once the secure server is live; version and update the existing Plugin rather than creating a duplicate.
- Separately verify whether the iPad's ChatGPT Voice Mode can invoke this private Plugin's tools.
- Connect Codex CLI locally on the host only after security review, with allowlisted repositories and safe dry-run testing first. Never enable arbitrary command execution, payroll, or production deployment by default.

## Deployment boundary

The source repository and a passing CI build do **not** grant server access or perform DNS changes. Deployment requires the owner's server access, actual DNS administration, a configured identity provider, and approval for any production-impacting change.

Current private plugin: https://chatgpt.com/plugins/plugins_6af01e64bc7c8191845e71ac1c947ca6

Do not commit credentials, OAuth client secrets, IP-sensitive details, or token contents into the repository.

## Publishing the Frappe website

Run as the dedicated Bench owner from the reviewed checkout:

```sh
make publish
```

`make publish` runs every deployment step in order: check the clean upstream
`main` release, dedicated single-site Bench, app manifest, database reachability
and site database login; request release confirmation; take a full site backup;
install dependencies/app; migrate; build assets; clear the website cache; restart
the dedicated Bench; and verify HTTPS. No separate preflight command is needed.
Preflight failure stops before deployment changes, and backup failure stops
before installation or migration. When local changes exist, publishing lists them and offers to stage and commit
them with an explicit confirmation and commit message. It separately confirms
pushing local commits. Review all listed files first: untracked non-ignored files
are included. A behind-only branch can be fast-forwarded with confirmation;
review incoming changes and rerun so the updated script is loaded. Diverged
branches stop for manual resolution. No force push, reset, or stash is used.

For an incomplete fresh installation in the managed Bench, `make publish` can
initialize the site after a failed database login. It first verifies through Linux
root socket access that both the database and account are absent. It then asks
for `INITIALIZE FRESH SITE`, creates only that database and local account, archives
the partial site files, and bootstraps Frappe as the non-root Bench owner. Linux
`su` may prompt for the Linux root password; MariaDB root authentication is never
changed or passed to Frappe. The Frappe Administrator password is prompted by
Frappe itself. Existing databases/accounts always block this initialization.
Failures preserve database objects and files for inspection and stop rather than
reinitializing repeatedly. Once initialized, publishing validates login, takes a
full backup, and follows the normal deployment steps. A completely absent Bench
still requires `make setup`; this recovery handles the existing partial site.

This publishes `agentsteers.com`; it does not publish MCP, edit Caddy, or run Codex.

Before installing/migrating the app, publish verifies the dedicated Bench's Redis
cache and queue dependencies. After deployment confirmation and backup, missing
managed instances are started as the Bench owner on loopback ports configured in
this Bench (currently 13000 and 11000). Existing processes must report this exact
Bench configuration and match the Bench owner; conflicting services are never
stopped or replaced. Logs are in `frappe-bench/logs/redis_cache.log` and
`redis_queue.log`. These daemonized processes do not install boot-time services;
a production process manager is still required for reboot recovery and the web,
worker, scheduler and Socket.IO processes. Redis for other applications is untouched.
