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

### Website runtime on the current server

The dedicated system unit `agentsteers-web.service` runs Gunicorn as `frappe` on
`127.0.0.1:8010`, using `deploy/website_wsgi.py` for Frappe and public asset serving.
The reviewed unit template is `deploy/agentsteers-web.service`; its absolute paths
must match the deployment checkout. `make publish` restarts this exact service,
checks it is active, then verifies the public HTTPS page markers. It refuses to
restart a unit for a different Bench. Non-root publishing requests Linux root
authentication via `su` for that service restart; no general sudo rights are added.

Caddy must route `agentsteers.com` to this loopback listener with
`X-Frappe-Site-Name: agentsteers.com` and `X-Forwarded-Proto: https`. The current
website route accepts GET/HEAD only for `/`, `/privacy`, `/terms` and
`/assets/agentsteers_frappe/*`; other paths return 404. This does not publish the
Frappe API, login, private files or MCP. Caddy configuration remains managed
separately from `make publish`. The web service is enabled at boot, but its Redis
dependencies still need persistent service management for full reboot recovery.

Publishing builds both `frappe` and `agentsteers_frappe` frontend assets. The core
Frappe bundles are required by login and other framework pages; building only the
custom app leaves unresolved `/website.bundle.css` and JavaScript URLs.

### Resuming development setup

`make dev` resumes a structurally valid `frappe-dev-bench/` when its development
site has not been created yet. It never replaces an existing site or reinitializes
the Bench. The site uses a fresh generated MariaDB database and local account,
with Linux root socket provisioning via interactive `su`; the Frappe Administrator
password is entered separately during bootstrap. Production data and credentials
are never copied. Incomplete provisioning keeps a private recovery record and
stops for inspection rather than creating further database objects.

Development Redis runs on its own configured loopback ports (13001/11001 on this
server). The web launcher uses the development Bench Python directly and binds
only `127.0.0.1:8001` (`AGENTSTEERS_DEV_PORT` can override the port), with no workers,
remote debugger, public proxy changes or production restart. The shared project
Bench CLI is used for management commands; `env/bin/bench` is not required.

Development app setup registers the app in the development `sites/apps.txt`
before calling `install-app`. `make dev` also resumes this registration and app
installation when a previous setup created the dev site but stopped before the
app was installed. An already installed app with complete core asset mappings is
not reinstalled or rebuilt on each launch. These repairs are restricted to the
validated development Bench; production app registration is unchanged.

### Fast live website updates

Run `make publish-hot` as `frappe` to refresh `https://agentsteers.com/`
from the source checkout already linked into the production Bench. It validates
production isolation, installed app, Python syntax, core asset manifest and Redis;
requests `HOTUPDATE agentsteers.com`; builds custom frontend bundles only if
present; clears Frappe caches; sends HUP to the dedicated Gunicorn master for a
graceful worker replacement; and checks the public website. It does not restart
the master or Caddy, install packages, migrate, back up the database, or perform
Git commits/pushes. `su` may prompt for Linux root authentication for the signal.

Use full `make publish` for dependency, DocType/schema, hooks or patch changes.
This fast command assumes the database already matches the application: it does
not determine whether pending schema changes require a migration. Because the
production app uses an editable source link, source edits may already affect
live templates/assets before invoking either command; this is not an isolated
staging or rollback mechanism. Use `make dev` for private experimentation.
Cloudflare/browser caches may retain assets at unchanged URLs; version CSS/JS
URLs when editing those files. No development server or MCP endpoint is enabled.


### Embedded MCP preflight in the existing Frappe WSGI process (not launched)

The existing `agentsteers-web.service` Gunicorn process now has a **disabled-by-default**
`/mcp` WSGI route. There is no additional service, port, systemd unit, or standalone
MCP process. This initial compatibility slice implements JSON-mode MCP
`initialize`, `ping` and `tools/list` (returns an empty tool list). It
intentionally rejects `tools/call`; no real task submission, authorization,
Codex or user-data access is available. SSE/session handling and authenticated
user-scoped task actions are **not** implemented. This is NOT a production-ready
ChatGPT connector.

The route is disabled unless the Gunicorn process explicitly receives both
`AGENTSTEERS_MCP_EMBEDDED=1` and a private, randomly generated
`AGENTSTEERS_MCP_EMBEDDED_TOKEN` of at least 32 characters. Neither the
`make publish` command nor the checked-in systemd unit supplies these values.
Do **not** enable this flag in production: the development bearer token is not
OAuth or per-user authorization.

The current public Caddy website allowlist must continue to return 404 on
`/mcp`; `deploy/Caddyfile.prelaunch` must continue returning 503 for
`mcp.agentsteers.com`. Do NOT add a public proxy route to the preflight.
Integration tests can instantiate the WSGI app directly offline. Before a
public release, add authenticated identity and repository-scoped authorization,
MCP protected resource metadata, request limits, complete transport compatibility
tests, logging redaction and explicit operator review; only then separately
approve proxy/HTTPS routing and publish.

Offline regression tests:
```sh
PYTHONPATH=src python3.11 -m unittest discover -s tests -p 'test_embedded_mcp_wsgi.py' -v
```

### `make mcp` on this server's Docker Caddy installation

`CADDY_CONFIG` is auto-detected as `/tpdata/caddy/config.json` here, rather than
assuming `/etc/caddy/Caddyfile`. `make mcp` runs the mock-only backend as the
non-root application owner on `127.0.0.1:8766`. After `ENABLE MOCK MCP`, Linux
root authentication through `su --pty` starts a privileged route supervisor.
This handles the root-owned JSON without relaxing file permissions or Docker
access for `frappe`. No token is printed or passed to the privileged helper.

The supervisor accepts only the known dedicated MCP routes, refuses to displace
an active old backend on port 8765, preserves all other JSON settings, validates
with the running Caddy image, backs up the original config, and changes only the
MCP host to the guarded mock. It preserves the bind-mounted config inode and
sets Host and forwarded HTTPS correctly. Since this Caddy instance has its admin
API disabled, activation and restoration restart only `trojan-panel-caddy`;
other websites can see a brief interruption at those two points. No certificates,
firewall settings, Frappe service, production databases or Codex execution change.

Ctrl+C, ordinary termination, or backend exit restores the exact original config
without another root password prompt. Concurrent config edits cause a refusal to
overwrite and a manual recovery message. Forced termination (SIGKILL), host loss,
or a failed Docker restart requires inspecting the root-owned `.mcp-session-*`
backup; this is a temporary test session, not a persistent deployment. The token
remains in `~/.config/agentsteers/mock-mcp.token` with private permissions. The
Caddyfile-based workflow remains available for other installations. For this
JSON installation use `make mcp` for activation/restoration, rather than the
persistent `mcp-mock-proxy-apply` target.
