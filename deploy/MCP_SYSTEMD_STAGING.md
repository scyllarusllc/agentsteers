# Persistent Mock MCP — staging-only systemd foundation

This unit is **not** a production ChatGPT connector. It serves only the
existing fake-job MCP implementation; there is **no Codex or shell execution**.
It does not install itself, expose a public route, manage Caddy, or change Frappe.

## Safety preflight

- Review all paths in `deploy/agentsteers-mcp-mock.service`. The current website
  unit suggests `/home/frappe/github/agentsteers`, but verify with `pwd`.
- First end the temporary `make mcp` session and confirm its privileged
  Caddy supervisor has restored the original route. Do **not** run the two
  backends concurrently: they both bind `127.0.0.1:8766`.
- Keep `mcp.agentsteers.com` on its 503 prelaunch route. **Do not** point
  Caddy to this service. Shared bearer authorization is not ChatGPT OAuth.
- Check `systemctl cat agentsteers-mcp-mock.service` before installing to
  avoid overwriting an existing unit. Have an authorized VPS operator review
  production-impacting steps; these commands are examples, not executed actions.
- Do not execute `make git-pull-force` or `git reset --hard` to fetch this branch.

## Manual, reviewed staging installation (not performed by this repository)

As the dedicated `frappe` owner, create the isolated Python environment as
documented for the project and ensure `gunicorn` is installed. Test offline:

```sh
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_mock_http_mcp.py' -v
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_remote_mcp_guard.py' -v
```

Prepare a private root-owned environment file at
`/etc/agentsteers/mock-mcp.env` (directory `0750`, file `0600`) with:

```ini
AGENTSTEERS_MCP_MOCK_ENABLED=1
AGENTSTEERS_MCP_MOCK_TOKEN=<new random 48+ character token, do not commit>
AGENTSTEERS_MCP_MOCK_HOST=mcp.agentsteers.com
AGENTSTEERS_MCP_MOCK_REPOS=scyllarusllc/agentsteers
```

Use a different staging token from the interactive `make mcp` token.
Do not print or paste tokens into issues or chats. The system manager reads
`EnvironmentFile` before dropping privileges to `frappe`.

After verifying Caddy is back in prelaunch mode and port 8766 is free, an
operator may copy the reviewed unit to
`/etc/systemd/system/agentsteers-mcp-mock.service`, then run:

```sh
sudo systemctl daemon-reload
sudo systemctl start agentsteers-mcp-mock.service
sudo systemctl --no-pager status agentsteers-mcp-mock.service
sudo journalctl -u agentsteers-mcp-mock.service -n 50 --no-pager
```

The template intentionally has no `[Install]` section and is not boot-enabled.
To stop/rollback:

```sh
sudo systemctl stop agentsteers-mcp-mock.service
```

Check `ss -ltn` for `127.0.0.1:8766` only; it must not bind
`0.0.0.0` or `::`. The service should not require any changes to the
existing website unit, database, Caddy container, or firewall.

## Production gates not yet implemented

Before exposing MCP to ChatGPT, implement and test OAuth/OIDC resource server
discovery/challenges, per-user authorization, durable jobs, audit controls,
limits and isolated Codex execution. This staging service is not a shortcut
around those gates. Jobs currently exist only in memory and disappear on restart.
