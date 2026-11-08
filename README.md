# AgentSteers

**AgentSteers turns ChatGPT Voice Mode on an iPad into a voice control interface for Codex CLI on the owner's cloud server.** The user speaks to ChatGPT, the authorized AgentSteers Plugin relays the task to AgentSteers running on the cloud server, and AgentSteers controls Codex CLI installed **on that same server**. Task progress and results flow back through the Plugin to ChatGPT Voice. AgentSteers is the secure bridge, not another chat assistant.

> **Status (2026-11-08):** The end-to-end Voice Mode → integration → server Codex loop is **not yet implemented or verified**. Local mock-worker experiments do not provide live remote execution.

## Why AgentSteers? (Planned product value)

**Speak to your coding agent, from anywhere — on your own infrastructure.**

AgentSteers is designed for developers who want to issue development requests from **ChatGPT Voice Mode on an iPad** and have a **Codex CLI instance on their own cloud server** carry them out, with progress and results returned to the conversation.

- **Voice-first, not another remote desktop:** ask for a coding task in natural conversation instead of navigating a separate terminal or control dashboard.
- **Self-hosted execution:** keep the development workspace and Codex CLI on a server you control, with AgentSteers as the narrow connection layer.
- **One server, simple path:** the intended `mcp.agentsteers.com` HTTPS/MCP entry point routes directly to AgentSteers and Codex CLI on the same host — no separate relay machine required.
- **Task feedback in conversation:** submit tasks, check progress, retrieve sanitized results, and cancel work without leaving the voice workflow.
- **Controlled automation:** approved repositories and operations, authenticated identity, least-privileged execution, redacted audit trails, and separate approval for dangerous changes.
- **Open-source and extensible by design:** start with Codex CLI; other coding agents may be considered later, but are not supported today.

### How it differs from mobile coding interfaces

Mobile interfaces and remote development tools can already help people manage coding work away from their desks. AgentSteers is **not intended to replace those interfaces**. Its proposed differentiator is the combination of **ordinary ChatGPT voice conversation + private-plugin bridge + self-hosted Codex CLI**, with an auditable permission boundary. This distinction is a **product hypothesis**, not a proven competitive advantage or evidence of demand.

### Why build this instead of only using official Codex tools?

**Official capabilities we acknowledge:** OpenAI's Codex Remote lets people start, steer, review, and approve tasks on connected development machines from the ChatGPT mobile app. Its secure relay can keep those machines reachable without exposing them directly to the public Internet. OpenAI also supports voice-driven coordination with Codex in supported desktop experiences. AgentSteers does **not** claim to have invented remote Codex access, approvals, secure relay, or mobile task monitoring.

**Our narrower hypothesis:** Some developers want an **ordinary ChatGPT Voice conversation on an iPad** to be their primary interface to a **self-hosted Codex CLI** on a server they control, rather than navigating a dedicated Codex Remote UI. AgentSteers aims to provide an open-source, narrowly scoped, auditable bridge for that experience, with a stable `mcp.agentsteers.com` entry point, explicit repository permissions, and conversational task-status feedback. We are not claiming the official product cannot evolve to offer this experience.

| Question | Official Codex experiences | AgentSteers target |
| --- | --- | --- |
| Remote Codex tasks from a mobile device? | Yes, through supported Codex Remote experiences. | Intended, but not yet working. |
| Primary interaction | Official Codex mobile/desktop experiences and supported voice features. | Ordinary ChatGPT Voice conversation on iPad using an authorized plugin. |
| Execution environment | Connected development machines and supported remote environments. | Owner-managed cloud host running AgentSteers and Codex CLI together. |
| Integration model | Official OpenAI Codex ecosystem. | Open-source self-hosted MCP bridge with repo-scoped authorizations. |
| Confirmed iPad Voice → plugin → own server → CLI round-trip? | Not claimed as a universal official workflow. | **Not yet verified**; this is the central prototype milestone. |

**Why invest in it?** To test whether the voice-first, self-hosted workflow saves time and reduces friction for developers away from their keyboards. It is an experiment, not yet a validated user need. Success requires a real iPad end-to-end demo, security validation, and feedback from early users. If official tools already meet a person's needs, they may not need AgentSteers at all.

Sources: [OpenAI — Work with Codex from anywhere](https://openai.com/index/work-with-codex-from-anywhere/), [OpenAI Developers — Mastering remote engineering work](https://developers.openai.com/blog/mastering-codex-remote-for-engineering), [ChatGPT Voice help](https://help.openai.com/en/articles/20001274-chatgpt-voice), [ChatGPT Work and Codex help](https://help.openai.com/en/articles/20001275-chatgpt-work-and-codex).

### Example (target experience, not yet implemented)

> On an iPad: “AgentSteers, ask Codex to review the failing tests in EZ Workbase, fix the bug in a safe branch, and tell me what changed.”

AgentSteers would route an approved, scoped task to the server's local Codex CLI and return status, test results, and a reviewable summary to ChatGPT Voice. **This exact voice-to-Codex end-to-end workflow has not been demonstrated yet.** The current private plugin contains guidance only; local MCP mock tools and tests exist, but live plugin binding, remote authentication, cloud deployment, and Codex execution are pending.

## Proposed architecture

> **Target flow, not yet operational:** iPad Voice Mode → AgentSteers Plugin → AgentSteers on the owner's cloud server → Codex CLI on the same server → results back to Voice Mode. The private plugin and local mock MCP components exist, but no live remote plugin/server/Codex link is deployed.

```mermaid
flowchart TD
    V["iPad — ChatGPT Voice Mode"]
    P["Private AgentSteers Plugin"]
    subgraph HOST["Owner's cloud server — one machine"]
        M["mcp.agentsteers.com<br/>HTTPS + verified OAuth access"]
        A["AgentSteers<br/>Scoped task gateway"]
        X["Codex CLI<br/>Restricted local execution"]
        M <--> A
        A -->|"Approved development task"| X
        X -->|"Progress and results"| A
    end
    V -->|"Voice instruction"| P
    P -->|"Authenticated MCP request"| M
    M -->|"Task status and result"| P
    P -->|"Spoken feedback"| V
```

**Scope and safety:** This is the intended architecture, not a working connection. ChatGPT Voice Mode needs a supported, explicitly connected tool/integration to invoke AgentSteers; voice conversation alone does not grant server access. Require scoped authorization, repository/action allowlists, isolated non-root execution, short-lived credentials, cancellation, and redacted audit logs. The worker must return status/errors/results so ChatGPT can explain them. Code changes can be committed/pushed under the owner's authorized workflow, while production deployment, secrets, and financial operations remain separately gated.


## Intended public endpoint

The future MCP endpoint is **`https://mcp.agentsteers.com/mcp`**, pointing to the owner's cloud server where AgentSteers and Codex CLI will run on the same machine. **The domain registration, DNS, HTTPS endpoint, and service deployment are not yet confirmed or verified.** The [deployment guide](deploy/README.md) includes a fail-closed HTTPS prelaunch configuration and security gates. The existing local development HTTP server must never be exposed to the Internet.

## Domain registration and deployment sequence

The intended public address is **`https://mcp.agentsteers.com/mcp`**. The subdomain is an HTTPS entry point **on the same cloud server** as AgentSteers and Codex CLI, **not a separate relay server**. Domain registration was mentioned as in progress by the owner, **not confirmed complete**.

1. **Register and verify domain:** confirm ownership of `agentsteers.com`. **Pending owner confirmation.**
2. **Choose and authorize server:** obtain its public IP or SSH hostname and appropriate access. **Not provided/verified.**
3. **Configure DNS:** point `mcp.agentsteers.com` to the authorized server, after ownership and address are confirmed. **Not performed.**
4. **Provision HTTPS:** configure TLS reverse proxy with the fail-closed prelaunch site (503, no MCP proxy) from [deployment instructions](deploy/README.md). **Not deployed.**
5. **Implement Google sign-in and MCP OAuth:** Google login proves identity; the MCP resource server separately verifies tokens, audience, allowed actions, and job ownership. **Not connected.**
6. **Deploy authenticated AgentSteers MCP service:** enable the four scoped task operations first against mock jobs, with rate limits and audit logs; do not expose the existing unauthenticated loopback prototype. **Not deployed.**
7. **Connect the existing private AgentSteers Plugin:** bind it to the verified HTTPS MCP endpoint, then verify actual ChatGPT Voice Mode tool invocation on iPad. **Not connected or tested.**
8. **Enable same-server Codex CLI under a restricted worker:** only after the preceding security checks and mock end-to-end tests succeed; keep deployment and sensitive actions separately gated. **Not enabled.**

**Existing deliverables:** the private Plugin (instructions only), four local MCP mock tools, protocol tests, HTTP loopback dev gateway, and prelaunch deployment scaffold are in place. **No live voice → plugin → server → Codex flow is claimed.**

## Proposed components

- **ChatGPT Voice Mode + integration:** voice is the user interface; the connected tool translates a permitted conversation request into an authenticated AgentSteers API call.
- **Control service:** authenticate the caller, check scope/approval, queue tasks, and expose job status and results.
- **Same-server Codex:** AgentSteers runs on the owner's cloud server and uses a restricted local worker to invoke Codex CLI installed on that same machine; no separate execution host is required for the initial design.
- **Feedback loop:** return task output, test summaries, errors, and progress to the integration for ChatGPT to report in conversation.
- **GitHub (optional workflow output):** Codex-produced code changes may result in commits/PRs; GitHub is not the primary control path.

## Security principles

1. **Default deny.** A worker must never execute arbitrary commands or tasks from untrusted input.
2. **Explicit approval.** Every potentially destructive, privileged, or external side effect requires appropriate authorization.
3. **Least privilege and isolation.** Use dedicated non-root identities, restricted filesystem/network access, and short-lived credentials.
4. **No secrets in tasks, logs, or commits.** Store secrets in an approved secret manager, never in source control.
5. **Auditable actions.** Record task identity, approver, scope, timestamps, outcomes, and redacted logs.
6. **Human-controlled deployment.** No automatic production deploys, financial transactions, or access to real payroll data.
7. **Safe cancellation and limits.** Enforce timeouts, resource caps, idempotency, and a kill switch.

## Initial milestones

- [x] Document the intended voice-to-Codex architecture and security boundaries.
- [ ] Define the ChatGPT integration interface and supported invocation mechanism.
- [ ] Specify authenticated task submission, status polling, cancellation and result schemas.
- [ ] Validate local dry-run worker behavior and tests.
- [ ] Implement an isolated server worker with a controlled Codex CLI adapter.
- [ ] Demonstrate end-to-end voice request → approved task → Codex → spoken outcome in a test environment.
- [ ] Complete security review before production server access.

## Relationship to EZ Workbase

EZ Workbase is a separate Frappe-based business application. AgentSteers may eventually help implement and test authorized changes to EZ Workbase, but the two projects should remain isolated. Any payroll or ACH integration must use test data until independently approved and validated.

## Development

Do not treat the mock worker as proof of a working cloud bridge. Develop and test the API contract and permission model locally before enrolling a server or allowing real Codex execution.


### Local development commands (Makefile)

Requires Python 3.11+, `make`, Git, and Python virtual environment support. On CentOS Stream 9, install the interpreter and pip if needed with `sudo dnf install python3.11 python3.11-pip`. From the repository root:

```bash
make help
make install
make dev
```

`make dev` checks that `.venv` uses Python 3.11+ and has pip, attempts `ensurepip` repair, and backs up an incompatible virtual environment as `.venv.backup.*` before recreating it. It does not modify the system Python. It then installs the editable package plus MCP, Uvicorn and JWT dependencies into `.venv`, generates an **ephemeral development bearer token** if `AGENTSTEERS_DEV_TOKEN` is unset, and starts the mock MCP HTTP service **only on `127.0.0.1:8765`**. The local endpoint is `http://127.0.0.1:8765/mcp`. Before launching, `make dev` checks Linux `/proc` for an existing listener on port `8765`. It sends SIGTERM **only** if that listener is a same-user `python -m agentsteers.http_server` process running from this repository directory. It waits for the port to be released; if any other process owns the port or ownership is ambiguous, startup stops with an error rather than killing an unrelated service. No `sudo`, generic `fuser -k`, or `kill -9` is used. This feature currently targets Linux (including CentOS Stream 9). The generated token is deliberately not printed. If you still see `ValueError: A random bearer token of at least 32 characters is required`, pull the latest `main` branch: an earlier Makefile incorrectly expanded the shell token during `make dev`. If you explicitly set `AGENTSTEERS_DEV_TOKEN`, it must also be at least 32 characters; if you need to authenticate a separate local client, set a strong token yourself before starting the server:

```bash
export AGENTSTEERS_DEV_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
make dev
```

Keep the token private and do not commit it. Stop the foreground server with Ctrl+C. This development server uses a single bearer-token guard, **not** the production OAuth identity and authorization flow. The underlying tools remain mock-only: `make dev` does not start Codex CLI, access a remote server, run real code-generation tasks, deploy anything, or move funds.

### Automatic local Frappe Bench detection

`make dev` now uses the **current project directory** by default: it checks the working directory, repository root, and `./frappe-bench` for a valid Frappe Bench layout (`apps/frappe`, `sites/`, and `env/bin/python`). You do **not** need to set `AGENTSTEERS_BENCH_DIR` when your Bench is already in one of those locations.

The repository's `frappe_app/` code **is not itself a Bench**. If there is no existing Bench, `make dev` explicitly reports that Frappe installation was skipped and still starts the local mock MCP service. It does not silently install Frappe, create a database/site, or deploy a website.

When a Bench is found, the installer automatically selects a site **only if exactly one** site has a dedicated development name such as `agentsteers-dev.localhost`, with an existing `site_config.json`. It links the local app into Bench, installs the package, then runs `install-app` when needed, `migrate`, `build`, and `clear-website-cache`. An ambiguous or non-development site is refused.

```bash
cd agentsteers
make dev                  # auto-detect Bench and dev site, then start mock MCP
make frappe-install       # require a local Bench + dedicated dev site; fail if absent
```

For a Bench stored elsewhere, explicit overrides are still available:

```bash
export AGENTSTEERS_BENCH_DIR="/actual/path/to/frappe-bench"
export AGENTSTEERS_FRAPPE_SITE="agentsteers-dev.localhost"
export AGENTSTEERS_FRAPPE_DEV_CONFIRM="$AGENTSTEERS_FRAPPE_SITE"
make dev
```

**Safety:** This never modifies an arbitrary ERPNext/EZ Workbase/production site, never starts Frappe's web process, and never redirects `agentsteers.com`. Install and test a separate development Bench/site before switching public traffic. If Frappe is not yet installed, provision the Bench and dedicated development site separately first.

### Publishing the Frappe website to production

`make publish` deploys the **Frappe website application** to an **already provisioned, dedicated single-site Frappe production Bench**. It does not provision Frappe/MariaDB, configure DNS/Caddy/HTTPS, deploy MCP, or run Codex.

The default production Bench path is your **current working directory** (`pwd`). Run the publish command from the dedicated production Frappe Bench directory, while referring to the AgentSteers Makefile by its absolute path:

```bash
cd /actual/production/frappe-bench
make -f /actual/agentsteers/Makefile publish
```

Alternatively, run it from the AgentSteers repository with the explicit override:

```bash
export AGENTSTEERS_PROD_BENCH_DIR="/actual/production/frappe-bench"
make publish
```

The paths above are placeholders; use real server paths. Running plain `make publish` in the AgentSteers Git checkout without the override will refuse to deploy: a Git repository is not a Frappe Bench.

The production site defaults to `agentsteers.com` (you may set `AGENTSTEERS_PROD_SITE` explicitly, but other site names are rejected). The command uses the current directory as its default Bench candidate and requires a non-root Bench owner and interactive release confirmation. It rejects a missing site, an unexpected site name, a shared multi-site Bench, or a conflicting existing app checkout. It first verifies the current Git branch is `main`, the tracked/untracked worktree is clean, and local HEAD exactly matches the current remote `origin/main` (read-only `git ls-remote`, **no automatic pull/reset**). It then requires an **interactive** `PUBLISH agentsteers.com` confirmation; no confirmation environment variable is needed. Only after these checks does it run: **site backup with files → editable app installation → first-time `install-app` if needed → `migrate` → `build` → website cache clear → Bench restart → HTTPS route checks**. The HTTPS checks require the public `agentsteers.com` routes `/`, `/privacy`, `/terms` and the packaged CSS to serve the new Frappe version, not just any old static page. If existing Caddy/DNS still points to the legacy site, the post-deploy check will fail; change routing only in a separate, reviewed operation. The checks do not automatically undo migrations. Backups do not replace a tested restore plan; database migrations can need manual rollback.

`make publish` uses the code currently checked out locally: it **does not run `git pull`**, and it refuses divergent branches or dirty worktrees. Check the intended Git commit before publishing. Do not point the command at an ERPNext/EZ Workbase Bench or other existing production workloads. After the command succeeds, verify `/`, `/privacy`, `/terms` and the CSS URL on the **already routed** production Frappe site; the reverse-proxy/DNS switch must be separately configured and verified. Privacy and Terms are still draft content, so review them before a public launch.

The local MCP mock service on port 8765 is **never** made public by this target. Codex CLI and privileged task execution remain disabled.

Other commands:

| Command | Behavior |
| --- | --- |
| `make help` | Display available targets. |
| `make install` | Verify/rebuild a Python 3.11+ `.venv`, repair missing pip if possible, and install development dependencies. |
| `make frappe-install` | Require a detected local Bench and dedicated AgentSteers dev site; install or update the App, otherwise fail safely. |
| `make publish` | Back up and update a configured, dedicated production Frappe site; never publish MCP/Codex. |
| `make test` | Run the repository's Python unittest suite locally. |
| `make pull` | Run `git pull --ff-only` on the current branch; refuse a divergent history. |
| `make git-pull-force` | **Destructive**: on local `main` only, ask for exact `YES`, fetch `origin/main`, save a recovery ref and stash dirty tracked/untracked non-ignored changes, then `git reset --hard origin/main`. |

For routine updates, prefer:

```bash
make pull
```

Only when you deliberately need to discard local `main` differences and align it with GitHub:

```bash
make git-pull-force
```

**Force-sync warning:** This can overwrite local changes to tracked files and discard local-only commits from the active branch. A pre-reset commit reference is saved under `refs/backup/agentsteers-main-...`; if the working tree was dirty, the command also creates a stash and `refs/backup/agentsteers-worktree-...`. Untracked non-ignored files are stashed; **ignored files are not saved by this command and are not removed**. No `git clean` is performed. Recovery is manual. Review `git status` and back up important work separately before proceeding. Never invoke the force-sync target automatically from `make dev`.

**Verification:** These Makefile commands are committed to GitHub, but their operation on the target CentOS server has not yet been verified.
