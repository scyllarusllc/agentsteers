"""Root-side temporary mock MCP route for the existing Docker JSON installation.

Only exact mcp.agentsteers.com routes can change. No certificates, firewall,
website routes, backend code or authentication secrets are modified here.
"""
from __future__ import annotations
import argparse
import copy
import datetime
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time

HOST = 'mcp.agentsteers.com'
CONFIG = Path('/tpdata/caddy/config.json')
CONTAINER = 'trojan-panel-caddy'
BACKEND = '127.0.0.1:8766'


def mock_candidate(config):
    result = copy.deepcopy(config)
    servers = result.get('apps', {}).get('http', {}).get('servers', {})
    found = []
    for name, server in servers.items():
        for index, route in enumerate(server.get('routes', [])):
            for match in route.get('match', []):
                if HOST in match.get('host', []):
                    if match.get('host') != [HOST] or len(route.get('match', [])) != 1:
                        raise RuntimeError('MCP route is shared or ambiguous; refusing modification.')
                    found.append((name, index, route))
    if not found or len({name for name, _, _ in found}) != 1:
        raise RuntimeError('Expected dedicated MCP routes in exactly one JSON HTTP server.')
    # Never take ownership of an unknown live service.
    for _, _, route in found:
        for handler in route.get('handle', []):
            if handler.get('handler') == 'reverse_proxy':
                upstreams = handler.get('upstreams', [])
                if upstreams != [{'dial': '127.0.0.1:8765'}]:
                    raise RuntimeError('Existing MCP proxy is unknown or already owned by another session.')
            elif handler.get('handler') != 'static_response' or handler.get('status_code') != 503:
                raise RuntimeError('Existing MCP route is not the known proxy or maintenance response.')
    name = found[0][0]
    routes = servers[name]['routes']
    first = min(index for _, index, _ in found)
    remove = {index for _, index, _ in found}
    routes[:] = [r for index, r in enumerate(routes) if index not in remove]
    routes[first:first] = [
        {'@id': 'agentsteers_mock_session', 'match': [{'host': [HOST], 'path': ['/mcp']}],
         'terminal': True, 'handle': [{'handler': 'reverse_proxy', 'upstreams': [{'dial': BACKEND}],
         'headers': {'request': {'set': {'Host': [HOST], 'X-Forwarded-Proto': ['https']}},
                     'response': {'set': {'Cache-Control': ['no-store']}}}}]},
        {'@id': 'agentsteers_mock_session_deny', 'match': [{'host': [HOST]}], 'terminal': True,
         'handle': [{'handler': 'static_response', 'status_code': 404}]}
    ]
    return result


def docker(*args):
    return subprocess.run(['docker', *args], check=True, text=True, capture_output=True)


def validate(text):
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json') as stream:
        stream.write(text); stream.flush()
        docker('cp', stream.name, CONTAINER + ':/tmp/agentsteers-mcp-session.json')
    docker('exec', CONTAINER, 'caddy', 'validate', '--config', '/tmp/agentsteers-mcp-session.json')


def apply(expected, replacement):
    if CONFIG.read_text() != expected:
        raise RuntimeError('Caddy JSON changed concurrently; refusing overwrite.')
    # Keep the inode: Docker bind-mounts this individual file.
    with CONFIG.open('r+') as stream:
        stream.write(replacement); stream.truncate(); stream.flush(); os.fsync(stream.fileno())
    docker('restart', CONTAINER)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--uid', type=int, required=True)
    args = parser.parse_args(argv)
    if os.geteuid() != 0 or args.uid == 0:
        raise RuntimeError('JSON Caddy session requires root supervision of a non-root mock backend.')
    process = Path('/proc') / str(args.pid)
    if process.stat().st_uid != args.uid:
        raise RuntimeError('Mock backend owner mismatch.')
    command = (process / 'cmdline').read_bytes()
    if b'agentsteers.mock_http_mcp:application' not in command or BACKEND.encode() not in command:
        raise RuntimeError('Unexpected mock backend process.')
    # An active original backend must not be displaced by a test session.
    try:
        with socket.create_connection(('127.0.0.1', 8765), timeout=.3):
            raise RuntimeError('Original MCP backend on 8765 is running; refusing to replace its route.')
    except ConnectionRefusedError:
        pass
    original = CONFIG.read_text()
    candidate = json.dumps(mock_candidate(json.loads(original)), indent=2) + '\n'
    validate(candidate)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup = CONFIG.with_name(CONFIG.name + '.mcp-session-' + stamp)
    fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(original)
    stop = False
    def on_signal(signum, frame):
        nonlocal stop
        stop = True
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, on_signal)
    applied = False
    try:
        # Mark before restart so a failed restart still restores the file.
        applied = True
        apply(original, candidate)
        print(f'Temporary mock MCP route active. Caddy backup: {backup}', flush=True)
        print('Caddy alone was restarted. Ctrl+C restores its original JSON routes.', flush=True)
        while not stop:
            try:
                os.kill(args.pid, 0)
                if (process / 'stat').read_text().split(') ', 1)[1].startswith('Z'):
                    break
            except (ProcessLookupError, FileNotFoundError):
                break
            time.sleep(.25)
    finally:
        if applied:
            current = CONFIG.read_text()
            if current == candidate:
                apply(candidate, original)
                print('Original Caddy JSON routes restored.', flush=True)
            elif current != original:
                raise RuntimeError(f'Caddy changed during the session; refusing overwrite. Restore manually from {backup}.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        # Do not dump subprocess output or private configuration.
        print(f'JSON Caddy MCP session stopped: {exc}', file=sys.stderr)
        raise SystemExit(1)
