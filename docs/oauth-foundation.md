# OAuth security foundation — not a live OAuth login flow

This branch adds `agentsteers.oauth_security`, a fail-closed verifier and
authorization-policy building block. **It does not enable Google login or
protect the existing local HTTP development server by itself.** Do not proxy
that development server publicly.

## Intended identity flow

1. A trusted authorization server provides the OAuth authorization-code
   flow with PKCE, OAuth discovery metadata, refresh/revocation controls,
   and a Google OIDC sign-in option to authenticate the human.
2. That authorization server issues **MCP access tokens** whose audience is
   `https://mcp.agentsteers.com`, signed by its own trusted keys.
3. AgentSteers validates issuer, JWKS signature, token expiry, audience,
   an allowlisted subject, and required scopes before handling requests.
4. Server-side repository allowlists and persisted task owner are checked
   before each task operation. User-supplied `approved=true` is ignored.
5. Only after this works can the Caddy site switch from 503 to the
   authenticated MCP service. Codex execution is a separate milestone.

**Do not pass Google ID tokens directly to the MCP resource server.**
An ID token for a Google OAuth client has a different audience and purpose.
The authorization server must issue resource-bound access tokens.

## Developer verification

Install optional dependency with `pip install -e '.[oauth]'`, then run
`python -m unittest discover -s tests -p 'test_oauth_security.py'`.

## Remaining work (NOT implemented)

- Real OIDC/Google sign-in provider registration and account verification.
- ChatGPT-compatible OAuth authorization-server metadata, dynamic client
  registration if needed, PKCE and protected-resource metadata endpoints.
- Wire the verifier into a remote Streamable HTTP MCP handler **before**
  any task side effect; issue proper 401 Bearer challenges and 403 denials.
- Persist owner/repository ACLs and jobs; rate limit, audit and redact.
- Test tampered, expired and incorrect-audience tokens with signed fixtures;
  test task ownership, refresh/revocation and end-to-end client login.
- Review the Cloudflare/Caddy configuration and do not publicly expose
  the prototype until all security and compatibility tests pass.

Cloudflare/Caddy may already route the hostname, but reachability is
not a substitute for authentication and authorization.
