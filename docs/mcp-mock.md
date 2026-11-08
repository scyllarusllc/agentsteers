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

## MCP protocol smoke test

GitHub Actions installs the MCP Python v1 SDK and launches the adapter as a subprocess over stdio. The test negotiates the protocol, discovers all four tools, and exercises submit, status, result, and cancel. This is **not** a ChatGPT Voice integration test. If the test is skipped locally, install `mcp>=1.18,<2` and rerun it. The CI job installs the dependency so a skipped local test must not be treated as a protocol pass.

## ChatGPT connectivity gate

Before building a remote endpoint, verify that the intended ChatGPT plan/workspace actually permits **custom MCP tools with write actions**, and separately verify tool invocation from **Voice Mode**. Availability can differ between ChatGPT plans and the OpenAI API. Neither a successful stdio handshake nor a working OpenAI API MCP call proves that a personal ChatGPT Voice session can invoke the custom write-capable plugin. If that pathway is unavailable, a separately hosted voice client using the OpenAI API is an alternative architecture to evaluate.

For a later remote prototype, use authenticated Streamable HTTP behind TLS, with server-verified caller identity and action permissions. A user-provided `approved=True` value is not meaningful proof of authorization and **must be removed/replaced before exposing write access**. The remote endpoint remains disabled in this milestone.

## Security limitations (must resolve before remote access)

**Do not deploy or expose this adapter publicly.** The `approved` parameter is a demonstration flag, **not** proof of caller identity or authorization. Production needs OAuth or another verified authentication mechanism, actor-scoped authorization, tenant isolation, request limits, durable task storage, audited decisions, TLS, network origin/host protections, and a separate restricted cloud worker. The in-memory mock queue is lost on restart and does not execute tasks. Voice Mode calling a deployed plugin requires an actual installed and authorized ChatGPT integration; this repository does not create that connection automatically.

Remote MCP should use Streamable HTTP rather than legacy SSE when the above protections are in place.
