# AgentSteers OAuth authorization server — testing setup

Updated 2026-11-10. **Preparation only. No authorization service has been deployed or verified.**

## Choice

For the single-user test phase, prefer an existing OAuth/OIDC provider instead of implementing login, credential storage or token issuance in AgentSteers. **Keycloak** is the suggested self-hosted candidate because it documents MCP authorization-server integration and supports Authorization Code + PKCE S256. Its CIMD support can require explicitly enabled experimental features and client policies; do not assume CIMD is active by default.

Authoritative references:
- OpenAI authentication: https://developers.openai.com/plugins/build/auth
- OpenAI custom MCP plugin: https://developers.openai.com/api/docs/guides/custom-mcp-server
- Keycloak MCP guidance: https://www.keycloak.org/securing-apps/mcp-authz-server
- Keycloak server administration: https://www.keycloak.org/documentation

## Planned topology (NOT online)

- ChatGPT web plugin: OAuth client.
- Authorization server: separate, owner-managed issuer at a **to-be-chosen verified HTTPS hostname**. `auth.agentsteers.com` below is merely an illustrative DNS name; do not publish metadata containing it until deployed.
- MCP resource: `https://mcp.agentsteers.com/mcp`; advertise this exact value in protected resource metadata and access-token audience.
- AgentSteers resource server: the opt-in `agentsteers.oauth_mock_wsgi:application` WSGI app; separate from the existing `make mcp` static-token service.
- Tools remain mock-only; no Codex, shell, Git writes, or production data access.

## Keycloak operator sequence

1. Choose a dedicated **test realm**, private admin credentials, database/backup, TLS reverse proxy and a permanent public HTTPS issuer URL. Do not install/modify Keycloak or existing Caddy routes as an undocumented side effect of a GitHub commit.
2. Create a dedicated owner login within the realm; use a separate normal account for authorization, not the Keycloak administrator. The configured `AGENTSTEERS_OAUTH_SUBJECTS` is the allowlist of access-token `sub` values; capture these privately from trusted Keycloak account management, not by pasting access tokens into chat.
3. Use a ChatGPT-supported OAuth client identity strategy:
   - For the **simplest controlled prototype**, register a **public client** with Authorization Code (standard flow), require PKCE `S256`, disable implicit and direct-access password grants, set exact ChatGPT callback URI shown by the plugin connection UI, and configure token-endpoint authentication method `none`.
   - Alternatively use **CIMD** after enabling and testing Keycloak's supported CIMD feature/policies, or use **DCR** only with restricted registration policy. These are alternatives, not simultaneous requirements.
   - For an OpenAI-managed stable callback, confirm issuer-identification support before using `https://chatgpt.com/connector_platform_oauth_redirect`; otherwise copy the callback generated for the actual connection. Never guess callback IDs.
4. Ensure Keycloak metadata advertises `issuer`, HTTPS `authorization_endpoint`, `token_endpoint`, `jwks_uri`, `code_challenge_methods_supported` including `S256`, and `token_endpoint_auth_methods_supported` including the selected method. For CIMD, additionally configure and verify `client_id_metadata_document_supported`.
5. **Audience is a hard gate:** Keycloak must issue access tokens meant for the *full* resource `https://mcp.agentsteers.com/mcp`. Configure and test an appropriate access-token audience mapper/client policy. Do not assume a default Keycloak client audience or an ID token satisfies the MCP resource audience. Preserve the OAuth `resource` parameter throughout authorization and token exchange as required by MCP.
6. Define and grant the smallest scopes needed for the mock tools:
   - `agentsteers:read` for status/result;
   - `agentsteers:submit` for mock task creation;
   - `agentsteers:cancel` for mock cancellation.
   Ensure these appear in the access token's **space-separated `scope` claim**, because AgentSteers currently reads that form. Do not confuse Keycloak roles/groups with OAuth scopes.
7. Only after verifying issuer, audience and token claims, configure the *server-only* environment of the new default-off WSGI app (replace every placeholder with a verified value):

```dotenv
AGENTSTEERS_OAUTH_MOCK_ENABLED=1
AGENTSTEERS_OAUTH_ISSUER=https://YOUR-REAL-KEYCLOAK-ISSUER/realms/agentsteers-test
AGENTSTEERS_OAUTH_AUDIENCE=https://mcp.agentsteers.com/mcp
AGENTSTEERS_OAUTH_JWKS_URL=https://YOUR-REAL-KEYCLOAK-ISSUER/realms/agentsteers-test/protocol/openid-connect/certs
AGENTSTEERS_OAUTH_AUTHORIZATION_SERVER=https://YOUR-REAL-KEYCLOAK-ISSUER/realms/agentsteers-test
AGENTSTEERS_OAUTH_SUBJECTS=YOUR-REAL-OWNER-SUB
AGENTSTEERS_OAUTH_REPOS=scyllarusllc/agentsteers
```

These are **templates, not credentials or runnable deployment instructions**. Do not commit the populated environment file. The current WSGI entry point does not create an authorization server and does not automatically expose itself through HTTPS.

## Acceptance checks

- Fetch the actual authorization server metadata and ensure `issuer` is exact; confirm `S256`, authorization/token endpoints, client registration settings, and token endpoint authentication methods.
- Fetch `https://mcp.agentsteers.com/.well-known/oauth-protected-resource` **after intentionally mounting the new OAuth app**. Confirm the `authorization_servers` entry matches the issuer and the `resource` is exactly the MCP URL.
- Confirm unauthenticated MCP requests return `401` and `WWW-Authenticate` with `resource_metadata`.
- Complete Authorization Code + PKCE login from ChatGPT web, then verify access-token signature, issuer, audience, expiry, owner-subject allowlist, and scopes.
- Verify `initialize`, `tools/list`, all four mock calls, an invalid token, insufficient scope, and cross-owner task denial. No Codex operations should occur.
- Current repository OAuth mock tools do **not yet** advertise per-tool `securitySchemes` or attach the corresponding MCP `mcp/www_authenticate` error metadata for auth-required tools. Finish those before claiming that ChatGPT's tool-level linking prompt works.
- Keep the old `make mcp` static-token mock separate; do not treat it as an OAuth connection test.

**Status:** No Keycloak deployment, issuer metadata, OAuth login or ChatGPT tool call is confirmed by this document.
