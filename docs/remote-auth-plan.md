# AgentSteers remote authentication gate

**Status:** code contains only a local mock task store. **No remote MCP service has been deployed.** This file specifies the required boundary before exposing any API or Codex worker.

## Flow

ChatGPT Voice + installed AgentSteers plugin → verified HTTPS Streamable HTTP MCP resource server → server-derived Principal → actor-scoped jobs → *future* authenticated isolated worker → *future* Codex CLI.

## Authentication and authorization requirements

- Use an external OAuth 2.1 / OIDC authorization server and verified MCP access tokens; the MCP service must function as a resource server, not its own login provider.
- Validate JWT signature, expiry, issuer and resource audience (or use authenticated RFC 7662 token introspection); trust only configured issuer and keys.
- Derive the actor's subject, repository allowlist, and permissions from verified server-side claims/policy. **Never** trust `approved=true`, `user_id`, or `repository_permissions` supplied as tool arguments.
- Bind every job's status, result and cancellation to its authenticated owner and current repository permission. Return the same not-found error for missing and unauthorized IDs.
- Reject unexpected commands; do not expose a generic shell tool.
- Use TLS, restrict host and origin, rate-limit requests, cap task sizes, record redacted audit events, enforce queue size and time limits.
- Persist jobs transactionally before launching real workers; the current in-memory prototype is not suitable for production.
- Use isolated non-root per-job execution for future Codex CLI, with no production filesystem or secrets by default, and explicit approval for any deployment.

## Current implementation

`actor_jobs.py` provides a **pure Python mock** for actor-scoped ownership and queue limits. It is intentionally not connected to the earlier unauthenticated HTTP development server. Test with:

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
```

The existing loopback bearer prototype is still for a single local developer. Do not change its bind address or expose it via a reverse proxy.

## External deployment blockers

1. Supply a verified issuer, resource audience, JWKS/introspection endpoint, and permitted client configuration from a real identity provider.
2. Obtain an authorized deployment target with non-root permissions and TLS termination.
3. Implement the actual MCP OAuth resource-server middleware and server-side policy mapping; run negative tests for missing/expired/incorrect-audience tokens.
4. Verify the real AgentSteers ChatGPT plugin's remote MCP tool connection and Voice Mode invocation.
5. Only then enroll a restricted worker and connect Codex CLI.

Official MCP Python SDK authorization documentation: https://py.sdk.modelcontextprotocol.io/run/authorization/
