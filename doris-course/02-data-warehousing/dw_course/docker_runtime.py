"""Explicit opt-in lifecycle for course 02's own single-node Compose project."""

import os
import shlex
import subprocess

import pymysql

from .runtime import COURSE_ROOT, WarehouseLab
from .ui import WorkflowProgress

COMPOSE_FILE = COURSE_ROOT / "environments/single-node/compose.yml"
PROJECT = "doris-warehousing-course"
CONNECTION = {
    "DW_HOST": "127.0.0.1",
    "DW_PORT": "52030",
    "DW_BE_HTTP_URL": "http://127.0.0.1:51040",
    "DW_USER": "root",
    "DW_PASSWORD": "",
}
STARTUP_STEPS = {
    1: "Check Docker and Compose",
    2: "Validate the single-container course configuration",
    3: "Prepare the Doris image",
    4: "Start or reuse the container and volumes, then wait for health",
    5: "Verify the FE connection and BE execution",
    6: "Inspect the running course container",
}


def compose_command(*arguments, streaming=False):
    override = (["--file", str(COURSE_ROOT / "environments/streaming/doris-resources.yml")]
                if streaming else [])
    return [
        "docker", "compose", "--project-name", PROJECT,
        "--file", str(COMPOSE_FILE), *override, *arguments,
    ]


def _run(command, progress, *, timeout=30):
    progress.log("$ " + shlex.join(command))
    result = subprocess.run(
        command, check=True, timeout=timeout, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    progress.log(result.stdout)


def _verify_sql():
    connection = pymysql.connect(
        host=CONNECTION["DW_HOST"], port=int(CONNECTION["DW_PORT"]),
        user=CONNECTION["DW_USER"], password=CONNECTION["DW_PASSWORD"],
        connect_timeout=5, read_timeout=10, autocommit=True,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            if cursor.fetchone() != (1,):
                raise RuntimeError("Sandbox SQL readiness check failed")
            cursor.execute('SELECT SUM(number) FROM numbers("number"="10")')
            if cursor.fetchone() != (45,):
                raise RuntimeError("Sandbox BE execution check failed")
    finally:
        connection.close()


def prepare_environment(*, start=False, streaming=False):
    """Start on explicit opt-in and report each completed or failed step."""
    if not start and os.environ.get("DW_START_SANDBOX") != "yes":
        raise RuntimeError("Set DW_START_SANDBOX=yes only to start course 02's Docker sandbox")
    if streaming:
        from .streaming import check_resources
        check_resources()

    def command(*arguments):
        return compose_command(*arguments, streaming=True) if streaming else compose_command(*arguments)

    progress = WorkflowProgress("Prepare the Doris lab environment", STARTUP_STEPS)
    try:
        progress.advance(1)
        _run(["docker", "info", "--format", "{{.ServerVersion}}"], progress)
        _run(["docker", "compose", "version"], progress)
        progress.advance(2)
        _run(command("config", "--quiet"), progress)
        progress.advance(3)
        _run(command("pull", "--policy", "missing"), progress, timeout=1800)
        progress.advance(4)
        # The pinned image supplies the container healthcheck.
        _run(command("up", "-d", "--wait", "--wait-timeout", "300"),
             progress, timeout=1800)
        progress.advance(5)
        _verify_sql()
        progress.log("SELECT 1 = 1; BE SUM(number) = 45")
        progress.advance(6)
        _run(command("ps"), progress)
    except Exception as error:
        detail = str(error)
        if isinstance(error, (subprocess.CalledProcessError, subprocess.TimeoutExpired)):
            output = error.output
            if isinstance(output, bytes):
                output = output.decode("utf-8", errors="replace")
            if output:
                detail += "\n" + output
        progress.fail(detail)
        raise
    os.environ.update(CONNECTION)
    progress.finish()
    return dict(CONNECTION)


def connect_sandbox():
    """Connect this notebook to the course container without starting Docker."""
    os.environ.update(CONNECTION)
    return WarehouseLab(allow_writes=True)
