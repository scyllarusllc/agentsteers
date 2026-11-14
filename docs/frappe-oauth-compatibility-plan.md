# AgentSteers / Frappe OAuth compatibility implementation plan

Status: **isolated security contract only; NOT a functioning authorization server.**
Do **not** route production OAuth endpoints to this code or enable Codex.

## Observed environment (operator-provided, not independently verified on server)

- Frappe 15.126.0 installed. Isolated/mock testing suggests S256 authorization-code validation works.
- Native Frappe token exchange appeared to accept missing/wrong confidential-client secrets and incorrect resource values.
- Native Frappe introspection payload may omit required claims (`iss`, `aud`, `sub`, `client_id`, `exp`).
- MCP protected-resource metadata is live per operator's 200 test; Frappe's OIDC metadata is live but did not advertise PKCE S256.
- No live end-to-end ChatGPT OAuth exchange has been verified. These are hypotheses from source review and isolated testing, **not confirmed production exploits**.

## What this branch implements

`src/agentsteers/frappe_oauth_compat.py` is an isolated, stdlib-only security boundary:
- `RegisteredClient`: exact server-owned client, confidential secret, redirect and MCP resource.
- `PendingAuthorization`: trusted one-time code record contract, with PKCE challenge, actor, scopes, audience, expiry.
- `verify_exchange()`: rejects incorrect secret/client ID, redirect mismatches, invalid/expired PKCE S256 verifiers, cross-resource exchanges and unexpected scopes.
- `validate_introspection_claims()`: requires live token status, expiry, issuer, subject allowlist, client and explicit **MCP resource audience**; refuses to invent missing claims.
- Tests reject prior weak behaviors; a shorter genuine Frappe Client Secret is accepted, though rotating it to a strong random value is recommended.

This module **does not** issue tokens, authenticate Frappe users, store/consume codes, provide WSGI routes, or advertise OAuth metadata. Its checks must be integrated into a real authorization-code issuing path with transactional one-time code consumption, Frappe session/user identity verification, audited confidential client handling and resource-scoped token issuance.

## Remaining gated implementation work

1. **Design the trust boundary** for an independent AgentSteers authorization server or narrow Frappe adapter. Never forward unvalidated Frappe native token responses as MCP bearer tokens. Decide whether to use its own opaque token store or signed access tokens with explicit `aud=https://mcp.agentsteers.com/mcp`.
2. **Authorization endpoint**: authenticate using supported Frappe login without trusting arbitrary redirect/return URLs; validate client, exact redirect, scope allowlist, `resource`, `state`, and PKCE S256; require consent if appropriate; produce short-lived, single-use codes bound to verified Frappe subject.
3. **Token endpoint**: authenticate confidential client (use a *single configured* `client_secret_post` or `client_secret_basic` method), atomically consume code, validate `verify_exchange`, issue an expiring MCP audience-bound token, and require protections against brute forcing and replay. Never reuse a Frappe refresh/access token as an AgentSteers token without a verified binding.
4. **Introspection or JWT verifier**: expose issuer, audience, client, scope, actor, expiration from server-trusted issuance records. Update the MCP resource-server verifier to use this bridge **only after** actual responses are validated in an integration environment.
5. **Discovery**: publish RFC 8414 OAuth AS metadata (or working OIDC metadata) at standard `/.well-known/` paths, advertising **only actually supported** `S256`, supported client auth methods, authorization/token endpoints and any permitted registration method. The MCP protected-resource endpoint must remain available.
6. **Tests**: unit tests + integration tests with a disposable Frappe 15 Bench, correct/invalid/missing secrets and PKCE, wrong resource, replayed code, expired codes, cross-user tasks, negative token checks, metadata and ChatGPT redirect. Check CSRF, redirect abuse, TLS proxy headers, state validation, log redaction and rate limits.
7. **Deployment**: human review, backup, isolated localhost listener, explicit reversible Caddy routing, monitoring; do not change existing `make mcp-auth` or deployed `8767` until tests pass and the operator authorizes a separate rollout.

## Running isolated contract tests

From repository root with OAuth dependencies installed:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_frappe_oauth_compat.py' -v
```

These tests are not a proof of live OAuth interoperability, and do not touch production, Caddy, database, or Codex.

## Production release criteria

- Verified Frappe login -> ChatGPT callback -> code exchange -> audience-bound access token -> MCP `initialize` / `tools/list` / mock task round trip.
- Missing/wrong client secrets, client binding, PKCE, incorrect resource/audience, expired/replayed codes and unknown actor MUST fail.
- Dedicated client and owner allowlist, no secrets in GitHub or logs, server-side authorization on each tool.
- No Codex worker until independently approved and tested.
