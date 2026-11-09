"""Free 8766 only for this owner's project mock, including Gunicorn workers."""
import os
from pathlib import Path
import signal
import time
from restart_dev_port import listeners, matching_pids

ROOT = Path(__file__).resolve().parents[1]
PORT = 8766
APP = b'agentsteers.mock_http_mcp:application'


def identity(pid):
    proc = Path('/proc') / str(pid)
    try:
        if proc.stat().st_uid != os.getuid() or (proc / 'cwd').resolve(strict=True) != ROOT.resolve():
            return None
        argv = (proc / 'cmdline').read_bytes().split(b'\0')
        if APP not in argv or b'127.0.0.1:8766' not in argv:
            return None
        stat = (proc / 'stat').read_text().split(') ', 1)[1].split()
        return (stat[19], int(stat[1]))  # start-time and parent PID
    except (OSError, ValueError, IndexError):
        return None


def session_parent(pid):
    proc = Path('/proc') / str(pid)
    try:
        if proc.stat().st_uid != os.getuid() or (proc / 'cwd').resolve(strict=True) != ROOT.resolve():
            return None
        argv = (proc / 'cmdline').read_bytes().split(b'\0')
        if not any(x in argv for x in (b'scripts/run_mcp_mock_session.py',
                                       str(ROOT / 'scripts/run_mcp_mock_session.py').encode())):
            return None
        return (proc / 'stat').read_text().split(') ', 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def signal_verified(pid, original, sig):
    # pidfd prevents a PID reused between verification and signaling being killed.
    fd = None
    try:
        if hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal'):
            fd = os.pidfd_open(pid)
        if identity(pid) != original:
            raise RuntimeError('Mock process identity changed; refusing to signal it.')
        if fd is not None:
            signal.pidfd_send_signal(fd, sig)
        else:
            os.kill(pid, sig)
    except ProcessLookupError:
        return
    finally:
        if fd is not None:
            os.close(fd)


def stop_previous_mock():
    inodes = listeners(PORT)
    if not inodes:
        return
    mapping = matching_pids(inodes)
    pids = set().union(*mapping.values())
    if not pids or any(not mapping[x] for x in inodes):
        raise RuntimeError('Port 8766 has an unidentified owner; refusing to kill it.')
    identities = {pid: identity(pid) for pid in pids}
    if any(value is None for value in identities.values()):
        raise RuntimeError('Port 8766 is not this user\'s AgentSteers mock; stop it manually.')
    masters = [pid for pid, value in identities.items() if value[1] not in pids]
    if len(masters) != 1:
        raise RuntimeError('Multiple mock masters on port 8766; refusing ambiguous cleanup.')
    master = masters[0]
    if any(pid != master and value[1] != master for pid, value in identities.items()):
        raise RuntimeError('Unexpected listener process tree; refusing cleanup.')
    parent = identities[master][1]
    previous_session = session_parent(parent)
    if not inodes.issubset(listeners(PORT)):
        raise RuntimeError('Port 8766 listener changed; rerun make mcp.')
    print(f'Stopping previous AgentSteers mock MCP on port 8766 (master PID {master})...', flush=True)
    signal_verified(master, identities[master], signal.SIGTERM)
    for _ in range(100):
        if not listeners(PORT).intersection(inodes):
            break
        time.sleep(.1)
    else:
        # Escalate only the already identified same-user processes, never fuser -k.
        for pid, original in identities.items():
            if identity(pid) == original:
                signal_verified(pid, original, signal.SIGKILL)
        for _ in range(30):
            if not listeners(PORT).intersection(inodes):
                break
            time.sleep(.1)
        else:
            raise RuntimeError('Previous mock did not release port 8766.')
    # The old session's privileged helper restores Caddy after backend exit.
    # Do not race a new activation against that restoration.
    if previous_session is not None:
        for _ in range(200):
            if session_parent(parent) != previous_session:
                break
            time.sleep(.1)
        else:
            raise RuntimeError('Previous MCP session has not finished restoring Caddy; wait before retrying.')
    if listeners(PORT):
        raise RuntimeError('Another listener claimed port 8766 during cleanup; refusing to kill it.')
    print('Port 8766 is free; previous session cleanup completed.', flush=True)
