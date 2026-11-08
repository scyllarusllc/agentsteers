# AgentSteers local development helpers. Never deploys or runs Codex.
SHELL := /bin/sh
PYTHON ?= python3.11
VENV := .venv
VENV_PYTHON := $(VENV)/bin/python

.PHONY: help install dev test pull git-pull-force

help:
	@printf '%s\n' 'make install          Create local Python environment and install dependencies' 'make dev              Start loopback-only mock MCP development server' 'make test             Run Python unit tests locally' 'make pull             Fast-forward the current branch from its upstream' 'make git-pull-force   Confirm, back up, and reset local main to origin/main'

install:
	@command -v $(PYTHON) >/dev/null 2>&1 || { echo 'Python 3.11 not found. On CentOS Stream 9 run: sudo dnf install python3.11 python3.11-pip' >&2; exit 1; }
	@$(PYTHON) scripts/bootstrap_dev.py
	$(VENV_PYTHON) -m pip install -e . 'mcp>=1.28,<2' 'uvicorn>=0.30,<1' 'PyJWT[crypto]>=2.9,<3'

dev: install
	@set -eu; \
	token="$${AGENTSTEERS_DEV_TOKEN:-}"; \
	if [ -z "$$token" ]; then \
		token="$$( $(VENV_PYTHON) -c 'import secrets; print(secrets.token_urlsafe(48))' )"; \
		printf '%s\n' 'Generated an ephemeral local development token (not printed).'; \
	fi; \
	export AGENTSTEERS_DEV_TOKEN="$token"; \
	$(VENV_PYTHON) scripts/restart_dev_port.py; \
	printf '%s\n' 'AgentSteers mock MCP: http://127.0.0.1:8765/mcp' 'Loopback development only; no Codex execution or public exposure.'; \
	exec $(VENV_PYTHON) -m agentsteers.http_server

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
