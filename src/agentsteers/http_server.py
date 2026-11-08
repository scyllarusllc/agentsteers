"""Loopback MCP Streamable HTTP dev server. Never bind to a public interface.

This is NOT a ChatGPT-connectable remote deployment. Authentication is a single
development bearer token, not OAuth or user-specific authorization.
"""
import os

from agentsteers.http_auth import LoopbackBearerGuard
from agentsteers.mcp_server import mcp

def create_app():
    token = os.environ.get("AGENTSTEERS_DEV_TOKEN", "")
    # Fail closed if the required secret is unset or too short.
    return LoopbackBearerGuard(mcp.streamable_http_app(), token)

app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765)
