# Serving AgentSteers website through Frappe

The Frappe application now includes the existing marketing site as native `www/` pages and CSS assets. This does **not** imply the website has been deployed.

- `agentsteers_frappe/www/index.html` — landing page (configured as `home_page = "index"` in hooks).
- `agentsteers_frappe/www/privacy.html` — draft privacy page at `/privacy`.
- `agentsteers_frappe/www/terms.html` — draft terms page at `/terms`.
- `agentsteers_frappe/public/css/styles.css` — packaged Frappe static asset at `/assets/agentsteers_frappe/css/styles.css`.

## Site deployment checklist (dedicated test site first)

1. Install the Frappe app into an **isolated Frappe Bench site**, not EZ Workbase or an existing production ERPNext site. Validate Python/Frappe versions and the app package against the Bench version.
2. In the approved Bench environment, install the app and run migrations with the site's correct `bench --site <site> install-app agentsteers_frappe` and `bench --site <site> migrate` commands. Resolve missing package or site hooks before proceeding.
3. Run `bench build --app agentsteers_frappe`, clear website cache, and verify `/`, `/privacy`, `/terms` and `/assets/agentsteers_frappe/css/styles.css` **locally**.
4. Check that the homepage and links render correctly and that the draft legal pages remain nonindexed. Confirm Frappe site routing and any existing website home-page customizations on the target release.
5. Only after local verification and explicit deployment authorization, point `agentsteers.com` to the dedicated Frappe site using the host's existing reverse proxy and TLS configuration. Preserve all other site blocks, particularly `mcp.agentsteers.com`, which must stay fail-closed.

The old `website/` static files are retained as source/reference for comparison. Do not operate the static Caddy site and Frappe site on the same domain simultaneously. The MCP mock HTTP service and Codex worker are **not** connected to Frappe by this website migration.

### Important security boundary

Frappe `www/` pages are public marketing content only. There is no user sign-in or Codex invocation exposed by this migration. No unauthenticated Frappe endpoint may dispatch an AI coding task. Draft privacy/terms content is not a verified description of production behavior.
