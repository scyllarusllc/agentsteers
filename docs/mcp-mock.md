# AgentSteers MCP mock adapter

This is the **first local-only integration milestone**, not a public ChatGPT plugin and not a cloud Codex connection.

## Tools

- `submit_task(repository, instruction, approved=False)` — explicitly approved, allowlisted mock job.
- `get_task_status(task_id)` — status for this in-memory process.
- `get_task_result(task_id)` — simulated result only.
- `cancel_task(task_id)` — idempotent mock cancellation.

## Local development

Install the project and pinned v1 MCP SDK:

```sh
python -m pip install -e . 'mcp>=1.28,<2'
AGENTSTEERS_MOCK_REPOS=demo/example python -m agentsteers.mcp_server
```

The adapter runs over **stdio** only. An MCP client must launch it as a subprocess. Run tests without the MCP SDK:

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Security limitations (must resolve before remote access)

**Do not deploy or expose this adapter publicly.** The `approved` parameter is a demonstration flag, **not** proof of caller identity or authorization. Production needs OAuth or another verified authentication mechanism, actor-scoped authorization, tenant isolation, request limits, durable task storage, audited decisions, TLS, network origin/host protections, and a separate restricted cloud worker. The in-memory mock queue is lost on restart and does not execute tasks. Voice Mode calling a deployed plugin requires an actual installed and authorized ChatGPT integration; this repository does not create that connection automatically.

Remote MCP should use Streamable HTTP rather than legacy SSE when the above protections are in place.
