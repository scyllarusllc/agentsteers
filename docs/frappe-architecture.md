# AgentSteers Frappe architecture (first scaffold)

Decision: **Frappe is the core business backend** for AgentSteers.
It owns users, task history, settings, connections and the future dashboard.
The MCP protocol adapter stays a **separate, authenticated interface** and
Codex CLI must run through an **isolated worker process**. Neither the
static marketing website nor a browser request may execute Codex directly.

## Intended single-server design

- `agentsteers.com`: static marketing site, then authenticated user dashboard
  (Frappe website/portal route behind Caddy).
- `mcp.agentsteers.com`: authenticated MCP gateway, mapped to Frappe
  business services through server-verified identity; NOT connected yet.
- Frappe: separate dedicated site + `agentsteers_frappe` app; users,
  task history, settings and connection metadata.
- MariaDB: managed by a Frappe Bench site; do not add PostgreSQL just for this.
- Worker: separate low-privilege process that invokes Codex CLI only on
  explicit scoped authorization. **Not implemented.**

The owner may keep the existing local MCP mock interface for tests; never
route its unauthenticated development endpoint to the public Internet.

## Domain models (first scaffold)

- **AgentSteers Task**: owner, repository, instruction, status, result summary;
  supports Dashboard and Task History.
- **AgentSteers Connection**: owner, label, type, status; supports Connections.
- **AgentSteers User Settings**: one record per owner; supports Settings.
- **User**: native Frappe model, not a duplicate custom user database.

Permissions default to **System Manager only** on the underlying DocTypes,
deliberately until per-user permission rules and migrations are reviewed.
The first Frappe API methods are read-only, require a logged-in Frappe session
and apply `owner_user` filtering. Do not pass arbitrary owner IDs from clients.
These methods have NOT been tested against a live Frappe site yet.

## Four modules: MVP scope

1. **Dashboard**: personal task status counts, connection count.
2. **Task History**: chronological list with sanitized result summaries.
3. **Settings**: default repository, voice and notification preferences.
4. **Connections**: server and integration status metadata; never put
   OAuth secrets or Codex tokens in DocType fields.

Dashboard routes/components and all writes are still to be built.
No fake login screens or mock tasks may be presented as production data.

## Deployment and verification

This scaffold lives in `frappe_app/` as a separate Python package.
It is **not installed** on the user's CentOS host. Check the Frappe
version/Bench layout first. In a vetted Bench environment:

```bash
# From a dedicated, working Frappe Bench (NOT the Codex worker account)
./env/bin/pip install -e /path/to/agentsteers/frappe_app
bench --site YOUR_DEDICATED_SITE install-app agentsteers_frappe
bench --site YOUR_DEDICATED_SITE migrate
```

Do not run install-app against an existing ERPNext/EZ Workbase production
site. Verify Frappe application packaging and DocType schema on a test
site before using the commands above. Ensure the installed app has an
appropriate, verified site-compatible release.

### Gates before release

- Frappe unit/integration tests, schema migrations and verified permission rules.
- Google OIDC web login and complete MCP-compatible OAuth authorization server
  binding, with server-side subject mapping and token validation.
- Real task job state machine, durable storage, cancellation and audited worker.
- Responsive authenticated Dashboard/History/Settings/Connections pages.
- Protection against CSRF, cross-user enumeration, secret exposure, and arbitrary
  command execution; separate deployment approval from task submission.
- Explicit live iPad Voice Mode → plugin → MCP → agent → result round-trip test.

Existing static website and Caddy production hosts are unchanged.
