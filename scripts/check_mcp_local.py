#!/usr/bin/env python3
"""Read-only MCP protocol smoke check for the local mock server.

Does not submit tasks, use Codex, or access production. The caller must
provide the same AGENTSTEERS_DEV_TOKEN used by 'make mcp-server'.
"""
from __future__ import annotations

import asyncio
import os
import sys

EXPECTED_TOOLS = frozenset({
    "submit_task", "get_task_status", "get_task_result", "cancel_task",
})


def verify_tool_names(names: set[str]) -> None:
    missing = EXPECTED_TOOLS - names
    if missing:
        raise RuntimeError("MCP tool discovery incomplete: " + ", ".join(sorted(missing)))


async def check_server(token: str) -> None:
    # Import inside the check so the diagnostic stays clear if dependencies
    # have not been installed. Never permit an external MCP server URL here.
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(
        "http://127.0.0.1:8765/mcp",
        headers={"Authorization": "Bearer " + token},
    ) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            response = await session.list_tools()
            names = {tool.name for tool in response.tools}
            verify_tool_names(names)
            print("Local MCP handshake: OK")
            print("Discovered tools: " + ", ".join(sorted(EXPECTED_TOOLS)))
            print("Read-only check: no tasks submitted, no Codex executed.")


def main() -> int:
    token = os.environ.get("AGENTSTEERS_DEV_TOKEN", "")
    if len(token) < 32 or any(ch in token for ch in "\r\n"):
        print(
            "Set AGENTSTEERS_DEV_TOKEN (32+ characters) to the same value "
            "used to start 'make mcp-server'.",
            file=sys.stderr,
        )
        return 2
    try:
        asyncio.run(check_server(token))
    except Exception:
        # Library exceptions can contain request headers or other secrets.
        print(
            "Local MCP handshake failed. Confirm 'make mcp-server' is running "
            "on 127.0.0.1:8765 with the same token and MCP dependencies installed.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
