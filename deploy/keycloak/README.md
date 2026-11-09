# Isolated Keycloak OAuth test stack

This directory contains an **operator-run deployment template**, not an active deployment.
It does not change the existing AgentSteers website, Caddy configuration, Mock MCP
`make mcp` route, or start Codex CLI.

## Host prerequisites

- Owner-authorized Linux host with Docker Compose and available resources.
- `auth.agentsteers.com` DNS and a TLS certificate pointed at the **authorized** host.
- A reviewed, dedicated `auth.agentsteers.com` reverse-proxy route; the upstream must be reachable **only on localhost** at `127.0.0.1:8780`.
- Non-root operation with access to Docker; do not confuse Docker group access with low privilege.
- A private persistent PostgreSQL volume and database backup plan.

The pinned example uses Keycloak 26.8.1 and PostgreSQL 17. Review the image security
updates before use. Keycloak's `cimd` and `resource-indicators` features
are experimental, intentionally enabled in the **test** stack only.

## Explicit operator commands (DO NOT run without reviewing existing host)

From the AgentSteers repository root:

```sh
cp deploy/keycloak/env.example deploy/keycloak/.env.auth
chmod 600 deploy/keycloak/.env.auth
# Edit .env.auth locally; replace every placeholder with independent random secrets.
python3 scripts/check_keycloak_env.py deploy/keycloak/.env.auth
docker compose --env-file deploy/keycloak/.env.auth -f deploy/keycloak/compose.yaml config --quiet
docker compose --env-file deploy/keycloak/.env.auth -f deploy/keycloak/compose.yaml up -d
docker compose --env-file deploy/keycloak/.env.auth -f deploy/keycloak/compose.yaml ps
```

`compose.yaml` binds **only** `127.0.0.1:8780:8080`. The database has no
host-published port. This intentionally does not publish a usable OAuth issuer:
the operator must separately review and configure HTTPS.

**Important:** `docker compose config` can print interpolated secrets when used
without `--quiet`. Do not paste a compose config dump or credentials in chat.

The effective issuer must exactly be:
`https://auth.agentsteers.com/realms/agentsteers-test`
**if and only if** that hostname and realm have been configured and verified.
Otherwise substitute the actual issuer consistently in Keycloak, AgentSteers,
and the ChatGPT plugin connection. Keycloak itself is configured with
`--hostname=https://auth.agentsteers.com`.

## Reviewed reverse proxy design (not an apply script)

TLS terminates at a dedicated `auth.agentsteers.com` virtual host.
Forward to `http://127.0.0.1:8780`; preserve the original Host header and
set correct trusted `X-Forwarded-Proto: https`. Verify the proxy's TLS and
forwarded-header trust configuration using your actual Caddy setup first.
**Do not replace the running production Caddy JSON or restart another site's
proxy simply to test this template.** The mock MCP host
`mcp.agentsteers.com` is a separate configuration and should stay unchanged.

## Keycloak admin-console configuration

1. Create realm `agentsteers-test`. Create one non-admin owner user for login.
2. Choose one ChatGPT-supported client registration method:
   - **CIMD** (preferred if configured): Realm Settings → Client Policies:
     create a profile with `client-id-metadata-document` executor, trusted
     client metadata domain `chatgpt.com`, HTTPS only, and the Resource Indicator
     allowlist `https://mcp.agentsteers.com/mcp`. Create a client policy with
     `client-id-uri` condition and link the profile. Validate the exact ChatGPT
     client metadata URL from the plugin UI, not a guessed callback.
   - **Pre-registered client**: create a public OIDC client, standard code flow
     only, PKCE S256 required, no direct grants, and register **exactly**
     the redirect URI shown by ChatGPT. If needed, use DCR with a restricted
     registration policy instead. Do not enable broad anonymous registration.
3. For `agentsteers:read`, `agentsteers:submit` and
   `agentsteers:cancel`, create client scopes and audience mappers that emit
   an access-token `scope` string and `aud` containing the **full MCP URI**.
   Configure resource-indicator policy to accept that URI. Keycloak roles/groups
   do not automatically become these OAuth scopes.
4. Confirm OIDC discovery metadata includes correct issuer, authorization and
   token endpoints, JWKS, PKCE S256 and chosen client registration mode.
5. Only after a **real** login test should the separate OAuth Mock MCP WSGI
   process be mounted behind a reviewed HTTPS MCP route. It is currently
   default-off and independent of the old bearer-token Mock endpoint.

## Non-secret verification

```sh
curl -fsS https://auth.agentsteers.com/realms/agentsteers-test/.well-known/openid-configuration -o /tmp/agentsteers-oidc.json
python3 scripts/check_oauth_metadata.py /tmp/agentsteers-oidc.json --issuer https://auth.agentsteers.com/realms/agentsteers-test --mode cimd
```

The `--mode cimd` check is valid only after Keycloak actually advertises CIMD
in its discovery document. Choose `--mode provided` for a manually registered
client. Passing structural checks is **not** proof that Keycloak returned an
access token with the correct `aud`, `sub`, expiration or scopes.

## Stop / cleanup

Use `docker compose ... stop` to stop the auth services. Never run
`down -v` on a live or valuable PostgreSQL database; this removes the
persistent volume. Keep `.env.auth` and DB backups private.

## Source of requirements

- https://developers.openai.com/plugins/build/auth
- https://www.keycloak.org/securing-apps/mcp-authz-server
- https://www.keycloak.org/server/containers
