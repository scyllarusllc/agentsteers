# AgentSteers website

Static product landing page intended for `https://agentsteers.com`. Source:
`website/index.html`, `website/styles.css`, `website/privacy.html`,
and `website/terms.html`. No build process, JavaScript, application
backend or secret is needed.

## Architecture

- `agentsteers.com` / optionally `www.agentsteers.com` serves static pages.
- `mcp.agentsteers.com` routes to a **separate authenticated MCP service**.
- Both can use the existing CentOS/Caddy host but must not share the
  Codex worker's OS identity, data paths or private configuration.

## Suggested deployment on the owner's Caddy host

1. Review and approve the site copy, the operator's identity and the privacy
   and legal terms before claiming public Google OAuth readiness.
2. On the server, pull the vetted repo commit. Copy **only** the `website/`
   static files to a dedicated path such as `/srv/agentsteers-website`.
   Give the Caddy process read access. Do not expose `.git`, env files,
   credentials, or the server-side AgentSteers source tree as the web root.
3. Back up the existing Caddy configuration and add an *additional* site
   block to the existing Caddyfile, preserving other sites:

   ```caddyfile
   agentsteers.com {
       root * /srv/agentsteers-website
       file_server
   }
   ```

   If using `www.agentsteers.com`, separately configure DNS and the
   corresponding redirect or domain site after it resolves. Do not modify the
   `mcp.agentsteers.com` site block as part of the website release.
4. Check ownership, filesystem/SELinux permissions and the site's network
   policy on CentOS. Validate with `sudo caddy validate --config
   /etc/caddy/Caddyfile` (adjust if the host uses a different active
   config) and then gracefully reload Caddy.
5. Verify the landing page, CSS, privacy and terms URLs through Cloudflare
   and make sure unrelated sites and the MCP route remain unchanged.

## Important limitations

- The landing page is not a Google login system and performs no authentication.
- Privacy and Terms are explicitly **drafts**; both use `noindex` until
  reviewed and made accurate for real processing.
- Google OAuth consent-screen policies, authorized-domain verification and
  an actual working OAuth callback remain separate implementation steps.
- The future MCP service must verify resource-bound OAuth tokens and enforce
  repo-scoped permissions. A website login is not Codex execution approval.
