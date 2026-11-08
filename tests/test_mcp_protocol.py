"""End-to-end MCP stdio protocol smoke test (SDK v1.x).

Requires: pip install 'mcp>=1.18,<2'. No remote hosts or real Codex.
"""
import asyncio
import json
import os
import sys
import unittest

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:
    ClientSession = StdioServerParameters = stdio_client = None


@unittest.skipIf(ClientSession is None, "MCP SDK not installed")
class MCPProtocolTests(unittest.TestCase):
    def test_four_tools_over_stdio(self):
        asyncio.run(self._exercise_protocol())

    async def _exercise_protocol(self):
        env = dict(os.environ)
        env["AGENTSTEERS_MOCK_REPOS"] = "demo/example"
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "agentsteers.mcp_server"],
            env=env,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                self.assertEqual({"submit_task", "get_task_status", "get_task_result", "cancel_task"},
                                 {tool.name for tool in listed.tools})

                async def invoke(name, arguments):
                    response = await session.call_tool(name, arguments)
                    self.assertFalse(response.isError, f"{name} returned MCP error")
                    blocks = [item.text for item in response.content if item.type == "text"]
                    self.assertTrue(blocks, f"{name} returned no text")
                    return json.loads(blocks[0])

                denied = await invoke("submit_task", {
                    "repository": "demo/example", "instruction": "test", "approved": False})
                self.assertEqual("explicit_approval_required", denied["error"])
                submitted = await invoke("submit_task", {
                    "repository": "demo/example", "instruction": "test", "approved": True})
                self.assertTrue(submitted["ok"])
                task_id = submitted["task_id"]
                status = await invoke("get_task_status", {"task_id": task_id})
                self.assertEqual("queued_mock", status["status"])
                result = await invoke("get_task_result", {"task_id": task_id})
                self.assertIn("No Codex", result["result"]["message"])
                cancelled = await invoke("cancel_task", {"task_id": task_id})
                self.assertEqual("cancelled", cancelled["status"])


if __name__ == "__main__":
    unittest.main()
