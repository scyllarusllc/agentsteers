"""Restart only the dedicated AgentSteers website service."""
from pathlib import Path
import os
import shutil
import subprocess
import sys

UNIT = 'agentsteers-web.service'


def restart_website_service(bench):
    if not Path('/etc/systemd/system/' + UNIT).is_file():
        raise RuntimeError('Dedicated agentsteers-web.service is not installed. '
                           'Install the reviewed deploy/agentsteers-web.service before publishing; '
                           'bench restart may be a no-op on an unconfigured Bench.')
    # Refuse to restart a unit installed for a different checkout/Bench.
    result = subprocess.run(['systemctl', 'show', UNIT, '--property=WorkingDirectory', '--value'],
                            text=True, capture_output=True, check=True)
    if result.stdout.strip() != str(Path(bench).resolve() / 'sites'):
        raise RuntimeError('Website unit points to another Bench; refusing restart.')
    if os.geteuid() == 0:
        command = ['systemctl', 'restart', UNIT]
    else:
        if not sys.stdin.isatty() or not shutil.which('su'):
            raise RuntimeError('Interactive Linux root authentication required to restart ' + UNIT)
        print('Restarting only agentsteers-web.service. su may request the Linux root password.', flush=True)
        command = ['su', '-c', 'systemctl restart agentsteers-web.service']
    subprocess.run(command, check=True)
    subprocess.run(['systemctl', 'is-active', '--quiet', UNIT], check=True)
