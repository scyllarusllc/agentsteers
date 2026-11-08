"""Start only this managed Bench's loopback Redis dependencies for publishing."""
import json
import os
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import time
from urllib.parse import urlsplit


def redis_info(port):
    """Return Redis server metadata, or None when no listener exists."""
    try:
        connection = socket.create_connection(('127.0.0.1', port), timeout=1)
    except ConnectionRefusedError:
        return None
    with connection:
        connection.settimeout(2)
        connection.sendall(b'*2\r\n$4\r\nINFO\r\n$6\r\nserver\r\n')
        with connection.makefile('rb') as stream:
            header = stream.readline(128)
            if not header.startswith(b'$'):
                raise RuntimeError(f'Port {port} does not provide accessible Redis metadata; refusing to replace it.')
            length = int(header[1:].strip())
            if not 0 < length < 65536:
                raise RuntimeError('Invalid Redis metadata response.')
            data = stream.read(length).decode()
    return dict(line.split(':', 1) for line in data.splitlines() if ':' in line and not line.startswith('#'))


def require_owned(info, config):
    if Path(info.get('config_file', '')).resolve() != config.resolve():
        raise RuntimeError('Redis port is occupied by another instance; no changes made to it.')
    pid = int(info.get('process_id', '0'))
    if pid <= 0 or Path(f'/proc/{pid}').stat().st_uid != os.geteuid():
        raise RuntimeError('Redis listener does not belong to the current Bench owner.')


def ensure_bench_redis(bench, *, start=False):
    bench = Path(bench).resolve()
    settings = json.loads((bench / 'sites/common_site_config.json').read_text())
    binary = shutil.which('redis-server')
    plans = []
    # Validate every dependency before starting any process.
    for name in ('redis_cache', 'redis_queue'):
        url = urlsplit(settings.get(name, ''))
        if (url.scheme != 'redis' or url.hostname != '127.0.0.1' or not url.port
                or url.username or url.password):
            raise RuntimeError('Automatic Redis startup requires the managed loopback configuration.')
        config = bench / 'config' / (name + '.conf')
        if config.is_symlink() or not config.is_file():
            raise RuntimeError(f'{name} configuration missing or symlinked.')
        directives = {}
        for line in config.read_text().splitlines():
            parts = shlex.split(line, comments=True)
            if parts:
                if parts[0] in ('include', 'loadmodule', 'replicaof', 'slaveof'):
                    raise RuntimeError('Custom Redis configuration requires explicit service management.')
                directives[parts[0]] = parts[1:]
        if directives.get('bind') != ['127.0.0.1'] or directives.get('port') != [str(url.port)]:
            raise RuntimeError(f'{name} bind/port differs from the loopback Bench settings.')
        if directives.get('unixsocket'):
            raise RuntimeError('Custom Redis Unix socket requires explicit service management.')
        for key in ('dir', 'pidfile', 'aclfile'):
            value = directives.get(key, [])
            if len(value) != 1 or not Path(value[0]).resolve().is_relative_to(bench):
                raise RuntimeError(f'{name}: {key} must be inside the dedicated Bench.')
        info = redis_info(url.port)
        if info is not None:
            require_owned(info, config)
        elif not start:
            raise RuntimeError(f'{name} is not running on 127.0.0.1:{url.port}. '
                               'make publish will start the dedicated Redis processes after confirmation.')
        plans.append((name, config, url.port, info))
    for name, config, port, info in plans:
        if info is None:
            if not binary:
                raise RuntimeError('redis-server is missing; install it before publishing.')
            logfile = bench / 'logs' / (name + '.log')
            if logfile.is_symlink():
                raise RuntimeError('Refusing a symlinked Redis log file.')
            subprocess.run([binary, str(config), '--daemonize', 'yes', '--protected-mode', 'yes',
                            '--logfile', str(logfile)], cwd=bench, check=True,
                           capture_output=True, text=True)
            for _ in range(30):
                info = redis_info(port)
                if info is not None:
                    require_owned(info, config)
                    break
                time.sleep(.1)
            else:
                raise RuntimeError(f'{name} failed to become ready; inspect {logfile}.')
            print(f'Started dedicated {name} on 127.0.0.1:{port}.', flush=True)
        else:
            print(f'Dedicated {name} ready on 127.0.0.1:{port}.', flush=True)
