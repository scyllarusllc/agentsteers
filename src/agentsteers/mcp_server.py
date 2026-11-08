"""Local-only AgentSteers MCP adapter. Do NOT expose to public networks.

Requires mcp>=1.28,<2. This prototype does not authenticate remote callers.
"""
import os
from mcp.server.fastmcp import FastMCP
from agentsteers.task_service import MockTaskService

repositories = {r.strip() for r in os.environ.get("AGENTSTEERS_MOCK_REPOS", "demo/example").split(",") if r.strip()}
service = MockTaskService(repositories)
mcp = FastMCP("AgentSteers Mock", instructions="Mock task tools only. No remote execution.")

@mcp.tool()
def submit_task(repository: str, instruction: str, approved: bool = False) -> dict:
    """Submit an explicitly approved mock task for an allowlisted repository."""
    return service.submit_task(repository, instruction, approved)

@mcp.tool()
def get_task_status(task_id: str) -> dict:
    """Read the status of a previously submitted mock task."""
    return service.get_task_status(task_id)

@mcp.tool()
def get_task_result(task_id: str) -> dict:
    """Read a mock task result (never executes Codex)."""
    return service.get_task_result(task_id)

@mcp.tool()
def cancel_task(task_id: str) -> dict:
    """Cancel a queued mock task."""
    return service.cancel_task(task_id)

if __name__ == "__main__":
    mcp.run(transport="stdio")
