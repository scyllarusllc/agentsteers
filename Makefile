# AgentSteers development and explicit website deployment helpers. Never runs Codex.
SHELL := /bin/sh
PYTHON ?= python3.11
VENV := .venv
VENV_PYTHON := $(VENV)/bin/python

.PHONY: help setup install frappe-install frappe-dev-auto dev dev-setup dev-fast dev-sync mcp-dev mcp-mock-install mcp-mock-test mcp-mock-start mcp-mock-proxy-preview mcp-mock-proxy-apply list start stop restart check-google-login fix-google-login publish publish-hot test pull git-pull-force

help:
	@printf '%s\n' 'make setup            Initialise the managed Frappe Bench and dedicated site interactively' 'make install          Create local Python environment and install dependencies' 'make dev              Auto-setup missing isolated dev Bench, then serve locally' 'make dev-setup        Create isolated development Bench and site (interactive)' 'make dev-fast         Start development site without database sync' 'make dev-sync         Disabled: production database copies are prohibited' 'make mcp-dev          Start the previous local mock MCP service' 'make mcp-mock-install Install Gunicorn for isolated HTTP mock testing' 'make mcp-mock-test   Run Mock HTTP MCP and authentication boundary tests' 'make mcp-mock-start  Start token-protected Mock HTTP MCP on localhost:8766 (foreground)' 'make mcp-mock-proxy-preview Preview dedicated Caddy MCP site change' 'make mcp-mock-proxy-apply  Test and enable dedicated HTTPS MCP proxy (confirmation)' 'make list             Show production website service status' 'make start            Start production website service' 'make stop             Stop production website (confirmation required)' 'make restart          Restart production website service' 'make check-google-login  Check Frappe public URL for Google OAuth' 'make fix-google-login    Confirm, back up and correct Frappe public URL' 'make frappe-install   Require local Bench; install/update dedicated dev app' 'make publish          Check, confirm, back up and deploy the Frappe website' 'make publish-hot  Refresh live website assets/caches and gracefully reload workers' 'make test             Run Python unit tests locally' 'make pull             Fast-forward the current branch from its upstream' 'make git-pull-force   Confirm, back up, and reset local main to origin/main'

setup:
	@$(PYTHON) scripts/setup_managed_bench.py

install:
	@command -v $(PYTHON) >/dev/null 2>&1 || { echo 'Python 3.11 not found. On CentOS Stream 9 run: sudo dnf install python3.11 python3.11-pip' >&2; exit 1; }
	@$(PYTHON) scripts/bootstrap_dev.py
	$(VENV_PYTHON) -m pip install -e . 'mcp>=1.28,<2' 'uvicorn>=0.30,<1' 'PyJWT[crypto]>=2.9,<3'

frappe-install:
	@$(PYTHON) scripts/install_frappe_dev.py --required

frappe-dev-auto:
	@$(PYTHON) scripts/install_frappe_dev.py

dev:
	@BENCH_DISABLE_UV=1 $(PYTHON) scripts/dev_environment.py ensure
	@$(PYTHON) scripts/run_frappe_dev.py

dev-setup:
	@BENCH_DISABLE_UV=1 $(PYTHON) scripts/dev_environment.py setup

dev-fast:
	@$(PYTHON) scripts/run_frappe_dev.py

dev-sync:
	@$(PYTHON) scripts/dev_environment.py sync

mcp-dev: install frappe-dev-auto
	@set -eu; \
	token="$${AGENTSTEERS_DEV_TOKEN:-}"; \
	if [ -z "$$token" ]; then \
		token="$$( $(VENV_PYTHON) -c 'import secrets; print(secrets.token_urlsafe(48))' )"; \
		printf '%s\\n' 'Generated an ephemeral local development token (not printed).'; \
	fi; \
	export AGENTSTEERS_DEV_TOKEN="$$token"; \
	$(VENV_PYTHON) scripts/restart_dev_port.py; \
	printf '%s\\n' 'AgentSteers mock MCP: http://127.0.0.1:8765/mcp' 'Loopback development only; no Codex execution or public exposure.'; \
	exec $(VENV_PYTHON) -m agentsteers.http_server


# Separate MCP test service; does NOT deploy a Caddy route or execute Codex.
# Set secrets only in the server's private service environment.
mcp-mock-install:
	@$(VENV_PYTHON) -m pip install 'gunicorn>=21,<24'

mcp-mock-test:
	@PYTHONPATH=src $(VENV_PYTHON) -m unittest discover -s tests -p 'test_mock_http_mcp.py' -v
	@PYTHONPATH=src $(VENV_PYTHON) -m unittest discover -s tests -p 'test_remote_mcp_guard.py' -v
	@PYTHONPATH=src $(VENV_PYTHON) -m unittest discover -s tests -p 'test_mcp_mock_caddy.py' -v

mcp-mock-start:
	@set -eu; \
	if [ "$${AGENTSTEERS_MCP_MOCK_ENABLED:-}" != "1" ]; then \
		echo 'Set AGENTSTEERS_MCP_MOCK_ENABLED=1 in the private service environment.' >&2; exit 1; \
	fi; \
	if [ -z "$${AGENTSTEERS_MCP_MOCK_TOKEN:-}" ] || [ "$${#AGENTSTEERS_MCP_MOCK_TOKEN}" -lt 32 ]; then \
		echo 'Set a random AGENTSTEERS_MCP_MOCK_TOKEN of at least 32 characters.' >&2; exit 1; \
	fi; \
	if [ "$${AGENTSTEERS_MCP_MOCK_HOST:-}" != "mcp.agentsteers.com" ]; then \
		echo 'Set AGENTSTEERS_MCP_MOCK_HOST=mcp.agentsteers.com.' >&2; exit 1; \
	fi; \
	if [ -z "$${AGENTSTEERS_MCP_MOCK_REPOS:-}" ]; then \
		echo 'Set AGENTSTEERS_MCP_MOCK_REPOS to an allowed owner/repository.' >&2; exit 1; \
	fi; \
	if [ ! -x "$(VENV_PYTHON)" ]; then \
		echo 'Missing local virtual environment. Run make install first.' >&2; exit 1; \
	fi; \
	$(VENV_PYTHON) -m gunicorn --version >/dev/null || { echo 'Run make mcp-mock-install first.' >&2; exit 1; }; \
	printf '%s\n' 'Starting Mock MCP on 127.0.0.1:8766 (one worker; no Codex). Stop with Ctrl+C.'; \
	exec env PYTHONPATH=src $(VENV_PYTHON) -m gunicorn --bind 127.0.0.1:8766 --workers 1 --access-logfile - agentsteers.mock_http_mcp:application


# Caddy is managed independently of the website deploy.
# Set CADDY_CONFIG only if your main Caddyfile lives elsewhere.
CADDY_CONFIG ?= /etc/caddy/Caddyfile

mcp-mock-proxy-preview:
	@$(PYTHON) scripts/mcp_mock_caddy.py --config "$(CADDY_CONFIG)"

mcp-mock-proxy-apply: mcp-mock-test
	@$(PYTHON) scripts/mcp_mock_caddy.py --config "$(CADDY_CONFIG)" --apply

list:
	@$(PYTHON) scripts/manage_website.py list

start:
	@$(PYTHON) scripts/manage_website.py start

stop:
	@$(PYTHON) scripts/manage_website.py stop

restart:
	@$(PYTHON) scripts/manage_website.py restart

check-google-login:
	@$(PYTHON) scripts/manage_google_login.py check

fix-google-login:
	@$(PYTHON) scripts/manage_google_login.py fix

publish:
	@$(PYTHON) $(abspath $(dir $(lastword $(MAKEFILE_LIST))))/scripts/publish_frappe.py

publish-hot:
	@$(PYTHON) $(abspath $(dir $(lastword $(MAKEFILE_LIST))))/scripts/publish_hotupdate.py

test: install
	@PYTHONPATH=src $(VENV_PYTHON) -m unittest discover -s tests -v

pull:
	@git pull --ff-only

git-pull-force:
	@set -eu; \
	branch="$$(git symbolic-ref --quiet --short HEAD || true)"; \
	if [ "$$branch" != "main" ]; then \
		printf '%s\n' 'Refusing: switch to local main before force-sync.' >&2; exit 1; \
	fi; \
	printf '%s\n' 'WARNING: This resets tracked files and local main commits to origin/main.' \
		'Uncommitted changes (including untracked, non-ignored files) will be stashed.' \
		'Ignored files are not removed. Recovery references are kept under refs/backup/.'; \
	printf 'Type YES to continue: '; \
	read answer || exit 1; \
	if [ "$$answer" != "YES" ]; then printf '%s\n' 'Cancelled.'; exit 1; fi; \
	stamp="$$(date -u +%Y%m%dT%H%M%SZ)-$$$$"; \
	git fetch origin main; \
	backup="refs/backup/agentsteers-main-$$stamp"; \
	git update-ref "$$backup" HEAD; \
	printf 'Saved old main to %s\n' "$$backup"; \
	if [ -n "$$(git status --porcelain --untracked-files=normal)" ]; then \
		git stash push --include-untracked -m "agentsteers pre-force $$stamp"; \
		stash_sha="$$(git rev-parse refs/stash)"; \
		git update-ref "refs/backup/agentsteers-worktree-$$stamp" "$$stash_sha"; \
		printf 'Saved worktree to refs/backup/agentsteers-worktree-%s (also in stash list)\n' "$$stamp"; \
	fi; \
	git reset --hard refs/remotes/origin/main; \
	printf '%s\n' 'Local main now matches origin/main. No git clean was run.'
