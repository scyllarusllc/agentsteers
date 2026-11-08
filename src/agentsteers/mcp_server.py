"""Local-only AgentSteers MCP adapter. Do NOT expose to public networks.

Requires mcp>=1.28,<2. This prototype does not authenticate remote callers.
"""
import os
from mcp.server.fastmcp import FastMCP
from agentsteers.task_service import MockTaskService
from agentsteers.frappe_task_client import FrappeTaskClient

repositories = {r.strip() for r in os.environ.get("AGENTSTEERS_MOCK_REPOS", "demo/example").split(",") if r.strip()}
# Explicit opt-in: absent configuration keeps the existing in-memory mock.
frappe_url = os.environ.get("AGENTSTEERS_FRAPPE_URL", "")
frappe_key = os.environ.get("AGENTSTEERS_FRAPPE_API_KEY", "")
frappe_secret = os.environ.get("AGENTSTEERS_FRAPPE_API_SECRET", "")
if any((frappe_url, frappe_key, frappe_secret)):
    if not all((frappe_url, frappe_key, frappe_secret)):
        raise RuntimeError("All three Frappe bridge settings are required")
    service = FrappeTaskClient(base_url=frappe_url, api_key=frappe_key,
                               api_secret=frappe_secret, allowed_repositories=repositories)
else:
    service = MockTaskService(repositories)
mcp = FastMCP("AgentSteers", instructions="Development task tools only. No Codex execution.")

@mcp.tool()
def submit_task(repository: str, instruction: str, approved: bool = False) -> dict:
    """Submit an explicitly approved queued task (mock or Frappe); never execute code."""
    return service.submit_task(repository, instruction, approved)

@mcp.tool()
def get_task_status(task_id: str) -> dict:
    """Read the status of a previously submitted task."""
    return service.get_task_status(task_id)

@mcp.tool()
def get_task_result(task_id: str) -> dict:
    """Read task results (never executes Codex)."""
    return service.get_task_result(task_id)

@mcp.tool()
def cancel_task(task_id: str) -> dict:
    """Cancel a queued mock task; Frappe mode does not yet support cancellation."""
    return service.cancel_task(task_id)

if __name__ == "__main__":
    mcp.run(transport="stdio")
