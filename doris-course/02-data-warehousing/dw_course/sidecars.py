"""Explicit lifecycle for local teaching services, attached only to course Doris."""

import json
import subprocess

from .docker_runtime import compose_command
from .runtime import COURSE_ROOT


def service_command(service, *arguments):
    return ['docker', 'compose', '--project-name', 'doris-warehousing-' + service,
            '--file', str(COURSE_ROOT / 'environments' / service / 'compose.yml'), *arguments]


def start_service(lab, service, *, start=False):
    """Require explicit opt-in; retain service metadata and attach only our container."""
    if not start:
        raise RuntimeError('Pass start=True to start the local ' + service + ' teaching service')
    subprocess.run(service_command(service, 'up', '-d', '--wait',
                                   '--wait-timeout', '300'), check=True, timeout=1800)
    container = subprocess.check_output(compose_command('ps', '-q', 'doris'), text=True).strip()
    sidecar = subprocess.check_output(service_command(service, 'ps', '-q'), text=True).strip()
    networks = json.loads(subprocess.check_output(
        ['docker', 'inspect', '--format', '{{json .NetworkSettings.Networks}}', sidecar], text=True))
    network = next(name for name in networks if name.endswith('_default'))
    attached = json.loads(subprocess.check_output(
        ['docker', 'inspect', '--format', '{{json .NetworkSettings.Networks}}', container], text=True))
    if network not in attached:
        subprocess.run(['docker', 'network', 'connect', '--alias', 'course-doris', network, container], check=True)
        # Adding a container interface can invalidate an existing TCP connection.
        lab.restore_session()
    return network
