"""Explicit opt-in lifecycle for course 02's own single-node Compose project."""

import os
import shlex
import subprocess

import pymysql

from .runtime import COURSE_ROOT, WarehouseLab
from .ui import WorkflowProgress
from .onboarding import SetupRequired

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
    try:
        result = subprocess.run(
            command, check=True, timeout=timeout, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
    except (OSError, subprocess.SubprocessError) as error:
        if command[:2] == ["docker", "info"]:
            message = (
                "Docker was not found. Install Docker Desktop (macOS/Windows) or Docker Engine "
                "with Compose (Linux) on the machine running Jupyter. Open a new terminal, "
                "check `docker info`, then restart Jupyter and rerun this cell."
                if isinstance(error, FileNotFoundError) else
                "Docker is not ready. Start Docker Desktop or Docker Engine on the machine "
                "running Jupyter, finish first-time setup, and wait for `docker info` to succeed. "
                "Then rerun this cell."
            )
        elif command == ["docker", "compose", "version"]:
            message = "Docker Compose is unavailable. Install the Compose plugin or repair Docker Desktop, then check `docker compose version` and rerun this cell."
        else:
            raise
        raise SetupRequired(message, detail=str(error) + "\n" + str(getattr(error, "output", "") or "")) from None
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


def prepare_environment(*, start=False, streaming=False, streaming_profile=None):
    """Start on explicit opt-in and report each completed or failed step."""
    if not start and os.environ.get("DW_START_SANDBOX") != "yes":
        raise RuntimeError("Set DW_START_SANDBOX=yes only to start course 02's Docker sandbox")
    if streaming:
        from .streaming import check_resources
        check_resources(streaming_profile or "cdc")

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
        progress.fail(detail, opened=not isinstance(error, SetupRequired))
        raise
    os.environ.update(CONNECTION)
    progress.finish()
    return dict(CONNECTION)


def connect_sandbox(*, module=None):
    """Connect this notebook to the course container without starting Docker."""
    os.environ.update(CONNECTION)
    try:
        lab = WarehouseLab(allow_writes=True)
    except pymysql.err.OperationalError as error:
        if error.args[0] not in (2002, 2003):
            raise
        # Diagnose only on connection failure; a healthy sandbox needs no Docker CLI call.
        try:
            _run(["docker", "info", "--format", "{{.ServerVersion}}"],
                 WorkflowProgress("Check Docker", {1: "Check Docker"}), timeout=10)
        except SetupRequired:
            raise
        raise SetupRequired(
            "Doris is not reachable at 127.0.0.1:52030. Open Lab 1, run Initialize the Lab Tools, "
            "then Start and Connect. Wait for connection_ok = 1, return here, and rerun this cell. "
            "Opening Jupyter alone does not start the database.",
            labs=(1,), detail=str(error),
        ) from None
    try:
        _check_prerequisites(lab, module)
    except Exception:
        lab.close()
        raise
    return lab


def _check_prerequisites(lab, module):
    requirements = {
        6: {"wwi_customers": (663, 5)},
        7: {"wwi_products": (227, 5), "customers": (663, 6), "orders_clean": (10, 6)},
    }.get(module, {})
    if not requirements:
        return
    existing = {row[0] for row in lab.query("SHOW TABLES")}
    missing = []
    upstream = set()
    for table, (count, source) in requirements.items():
        if table not in existing or lab.query(f"SELECT COUNT(*) FROM {table}")[0][0] != count:
            missing.append(table)
            upstream.add(source)
    if missing:
        raise SetupRequired(
            f"Lab {module} needs data in {lab.database}: {', '.join(missing)} is missing or incomplete. "
            "Complete Lab 5 (historical import), then Lab 6 (quality checks) if needed, "
            "in this same database. Return here and rerun this cell. No lab tables have been reset.",
            labs=tuple(sorted(upstream)),
        )
