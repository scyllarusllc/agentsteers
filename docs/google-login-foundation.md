# Website sign-in foundation (development branch)

This branch adds an AgentSteers account entry point without changing production deployment or configuring OAuth secrets.

## Flow
- Landing page links to `/account`.
- Guests are offered Frappe's built-in `/login?redirect-to=%2Faccount` route. The Google option appears there **only after** the administrator enables a Google Social Login Key.
- Signed-in users see their Frappe session identity on `/account`. No Codex/MCP privileges are implied.
- Logout uses Frappe's website logout endpoint. Confirm this route with the installed Frappe version before release.

## Administrator configuration (not automated)
1. In Google Cloud, register `https://agentsteers.com/api/method/frappe.integrations.oauth2_logins.login_via_google` as the authorized redirect URI. Verify it against the installed Frappe version before saving.
2. In Frappe Desk, create a Google **Social Login Key**, set Client ID and Client Secret securely, and enable Social Login. Never commit secrets.
3. Keep self-signup enabled if new Google identities should become **Website User** accounts; verify the installed Frappe version's settings. Do not grant **System User** or administrative roles to ordinary accounts.
4. Confirm Google login, session, logout, redirect to `/account`, and that website users cannot access Desk or privileged API methods.
5. Google login does **not** authorize the future MCP/Codex service. That needs a separate token and permission boundary.

## Release gate
Review the branch and test on a staging Frappe site before merging. Production `main` and `make publish` are unchanged.
