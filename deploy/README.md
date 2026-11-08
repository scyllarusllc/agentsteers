# AgentSteers deployment plan — single cloud server

**Target:** ChatGPT Voice on iPad → private AgentSteers plugin → https://mcp.agentsteers.com/mcp → AgentSteers → restricted *local* Codex CLI on the SAME cloud server → results back to the plugin.

**Current state:** preparation only. No claim that the domain, server, OAuth, Plugin binding, or Codex is deployed or operational. The existing loopback development server must NEVER be put behind the public hostname.

## DNS and HTTPS preparation

1. Confirm ownership/control of `agentsteers.com` at the DNS provider. Do not assume ownership from the project name.
2. Select an explicitly authorized Linux host and verify that DNS can resolve `mcp.agentsteers.com` to its public IP: create an **A** record (and **AAAA** only if working IPv6 is configured). Do not invent an IP address.
3. Configure a firewall permitting inbound TCP 443 (and TCP 80 for certificate issuance where required), limiting SSH to authorized administration. Never expose the MCP backend's port to the Internet.
4. Install and validate Caddy. Start with `deploy/Caddyfile.prelaunch`: HTTPS front door responds **503** intentionally. It does not proxy any MCP traffic. Confirm `curl -i https://mcp.agentsteers.com/mcp` returns 503 (after DNS + HTTPS are configured).
5. Only switch from maintenance mode after completing the security gates below and running integration tests. A 503 is the expected prelaunch behavior, not proof of MCP functionality.

## Authenticated MCP release gates

- Configure a recognized OAuth/OIDC authorization provider and a **distinct** MCP resource audience. Google Sign-In can identify the owner, but does not alone authorize MCP task execution. Validate issuer, signature/JWKS, expiry, audience, scopes, and token revocation/expiry; never accept a client-supplied `approved=true` as authorization.
- Implement the MCP authorization flow needed by ChatGPT, including protected-resource metadata and token challenge/discovery as required by the chosen provider. Verify the Plugin's client compatibility rather than assuming it.
- Bind every task to the authenticated actor and current repo-scoped permissions; protect status/result/cancellation against cross-user access.
- Persist jobs, add throttling/size limits and redacted audit records, and reject unauthenticated requests before any task side effect.
- Ensure HTTPS, allowlisted Host/Origin, non-root isolated worker, secret handling and cancellation are working and tested.
- Bind the private AgentSteers Plugin to the **verified** `https://mcp.agentsteers.com/mcp` endpoint only once the secure server is live; version and update the existing Plugin rather than creating a duplicate.
- Separately verify whether the iPad's ChatGPT Voice Mode can invoke this private Plugin's tools.
- Connect Codex CLI locally on the host only after security review, with allowlisted repositories and safe dry-run testing first. Never enable arbitrary command execution, payroll, or production deployment by default.

## Deployment boundary

The source repository and a passing CI build do **not** grant server access or perform DNS changes. Deployment requires the owner's server access, actual DNS administration, a configured identity provider, and approval for any production-impacting change.

Current private plugin: https://chatgpt.com/plugins/plugins_6af01e64bc7c8191845e71ac1c947ca6

Do not commit credentials, OAuth client secrets, IP-sensitive details, or token contents into the repository.
