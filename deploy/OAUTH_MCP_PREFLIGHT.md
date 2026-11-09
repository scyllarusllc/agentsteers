# OAuth MCP preflight: integration status

The repository now has an opt-in WSGI factory:
`agentsteers.oauth_mcp_preflight.from_environment()`.

It layers OAuth protected-resource discovery (RFC 9728), an existing JWT
access-token verifier, and the MCP handshake endpoint. There are **zero**
task tools: `tools/list` is empty, and `tools/call` is rejected. This does
not provide a login form, OAuth authorization endpoint or token endpoint.

## Run offline tests first

In the project's isolated Python environment with `pip install -e '.[oauth]'`:

```sh
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_oauth_resource_metadata.py' -v
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_oauth_security.py' -v
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_remote_mcp_guard.py' -v
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_oauth_mcp_preflight.py' -v
```

No service or public route is started by these tests.

## Future server-side configuration (not deployed)

A future authorized deployment must use a real OIDC/OAuth authorization
server that signs JWT **access** tokens with the resource audience:

`https://mcp.agentsteers.com/mcp`

The example factory requires:

- `AGENTSTEERS_OAUTH_PREFLIGHT_ENABLED=1`
- `AGENTSTEERS_OAUTH_ISSUER` — trusted HTTPS issuer
- `AGENTSTEERS_OAUTH_JWKS_URL` — issuer's trusted HTTPS signing keys
- `AGENTSTEERS_OAUTH_ALLOWED_SUBJECTS` — comma-separated permitted identities

The issuer must support an authorization-code + PKCE flow usable by the
ChatGPT MCP client, with suitable authorization-server discovery. Register
only exact, provider-approved redirect URIs; configure scopes and audience.
The JWT verifier is **not** an OAuth authorization server and cannot mint
tokens. Google ID tokens are not MCP access tokens.

The existing mock systemd service and public Caddy routes do **not** import
this factory. Do not expose it until token validation, dynamic client
registration or supported client setup, origin/proxy trust, authorized
actions, persistence, rate limits, and real client interoperability
tests are reviewed. No Codex or shell code runs here.

For WSGI integration, construct the app in a separate opt-in entry point
after config validation; do not replace Frappe's existing website_wsgi or
the mock Gunicorn worker. Run offline regression tests before considering
a restricted staging listener. **This repository change does not install,
activate, or publicly publish that endpoint.**
