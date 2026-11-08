# MCP Streamable HTTP: loopback development gateway

This milestone adds a **single-tenant local HTTP gateway** with a bearer-token check.
It is **not** an Internet-facing MCP deployment, an OAuth provider, a cloud worker,
or a live ChatGPT Voice integration.

## Run on a developer machine only

Install the MCP SDK and ASGI server (Python 3.10+):

```bash
python -m pip install -e . 'mcp>=1.28,<2' 'uvicorn>=0.30,<1'
export AGENTSTEERS_DEV_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export AGENTSTEERS_MOCK_REPOS=demo/example
python -m agentsteers.http_server
```

The service listens **only on 127.0.0.1:8765**. A test MCP client can use
`http://127.0.0.1:8765/mcp`, setting `Authorization: Bearer <AGENTSTEERS_DEV_TOKEN>`.
Never share this token in chat, GitHub, logs, or screenshots.

The HTTP guard rejects missing or incorrect bearer tokens, untrusted host headers,
and untrusted browser origins. The underlying four tools still return mock results:
**no Codex, no remote command, no production access.**

## Required before any remote deployment

- Proper OAuth/OIDC identity verification, scoped tokens, caller-bound tool permissions.
- Replace the caller-supplied `approved` boolean: it is NOT authorization evidence.
- Task ownership and tenant isolation, immutable audit events and durable job storage.
- Rate limiting, request-size limits, secure MCP transport/origin validation and TLS.
- Separate authenticated worker with no direct network access from ChatGPT into shell.
- Test the ChatGPT plugin's real MCP binding and Voice Mode support.

Do not change the bind host to 0.0.0.0 or put this development server behind a
public reverse proxy. A public/ChatGPT-accessible service is a **later milestone**
and needs a security review.
