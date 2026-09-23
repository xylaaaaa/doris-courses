"""Opt-in local streaming fixtures. Teaching SQL remains in the notebooks."""

import json
import re
import subprocess
import time
from html import escape
from uuid import uuid4
from xml.etree import ElementTree

import requests
import pandas as pd
from IPython import get_ipython
from IPython.display import HTML, display

from .runtime import COURSE_ROOT, identifier, normalized
from .ui import in_notebook, show_frame

COMPOSE = COURSE_ROOT / "environments/streaming/compose.yml"
REST = "http://127.0.0.1:51881"


def compose(*arguments, input=None, timeout=120):
    result = subprocess.run(
        ["docker", "compose", "--file", str(COMPOSE), *arguments],
        input=input, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        timeout=timeout, check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stdout)
    return result.stdout


def configure_streaming_port():
    """Discover Docker's dynamically assigned Flink host port."""
    output = compose("port", "jobmanager", "8081")
    match = re.search(r":(\d+)\s*$", output.strip())
    if match is None:
        raise RuntimeError(f"Could not determine Flink Web UI port: {output!r}")
    port = int(match.group(1))
    global REST
    REST = f"http://127.0.0.1:{port}"
    return port


def _render_wait_progress(description, elapsed, timeout, attempt, handle=None, state="waiting"):
    if get_ipython() is None:
        return handle
    colors = {"waiting": ("#2563eb", "⏳"), "success": ("#16a34a", "✅"), "failure": ("#dc2626", "❌")}
    color, icon = colors[state]
    if state == "success":
        percentage = 100
    else:
        percentage = min(100, int(elapsed / timeout * 100)) if timeout else 100
    detail = {
        "waiting": f"Still working · {elapsed}s elapsed · check {attempt} · timeout {timeout}s",
        "success": f"Ready after {elapsed}s · {attempt} checks",
        "failure": f"Stopped after {elapsed}s · {attempt}",
    }[state]
    description = escape(str(description))
    detail = escape(detail)
    content = f"""
    <div style="border:1px solid #d1d5db;border-radius:8px;padding:10px 12px;margin:8px 0;
                max-width:680px;font-family:system-ui,sans-serif">
      <div style="font-size:14px"><span style="font-size:18px">{icon}</span> <b>{description}</b></div>
      <div style="height:7px;background:#e5e7eb;border-radius:4px;margin:8px 0;overflow:hidden">
        <div style="height:100%;width:{percentage}%;background:{color};border-radius:4px"></div>
      </div>
      <div style="color:#6b7280;font-size:12px">{detail}</div>
    </div>
    """
    if handle is None:
        return display(HTML(content), display_id=True)
    handle.update(HTML(content))
    return handle


def wait_for(read, accepts, *, description, timeout=180, check_health=None):
    deadline = time.monotonic() + timeout
    started = time.perf_counter()
    last = None
    attempt = 0
    handle = None
    try:
        while time.monotonic() < deadline:
            attempt += 1
            elapsed = int(time.perf_counter() - started)
            handle = _render_wait_progress(description, elapsed, timeout, attempt, handle)
            if check_health is not None:
                check_health()
            last = read()
            if accepts(last):
                _render_wait_progress(
                    description, int(time.perf_counter() - started), timeout,
                    attempt, handle, "success"
                )
                return last
            time.sleep(2)
    except Exception as error:
        _render_wait_progress(
            description, int(time.perf_counter() - started), timeout,
            f"last observation: {last!r}; error: {error}", handle, "failure"
        )
        raise
    _render_wait_progress(description, int(time.perf_counter() - started), timeout, repr(last), handle, "failure")
    raise TimeoutError(f"{description}: last observation = {last!r}")


RESOURCE_REQUIREMENTS = {
    "kafka": {
        "memory_gib": 10,
        "cpus": 2,
        "description": "8 GiB Doris cap plus a small Kafka dependency budget",
    },
    "cdc": {
        "memory_gib": 18,
        "cpus": 4,
        "description": "12 GiB Doris cap plus MySQL/Flink dependency budget",
    },
}


def check_resources(profile="cdc"):
    """Check Docker daemon capacity, not available RAM or a resource reservation."""
    try:
        requirements = RESOURCE_REQUIREMENTS[profile]
    except KeyError as error:
        raise ValueError(f"Unknown streaming profile: {profile}") from error
    result = subprocess.run(
        ["docker", "info", "--format", "{{json .}}"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        timeout=30, check=True,
    )
    info = json.loads(result.stdout)
    memory_gib = info["MemTotal"] / (1024 ** 3)
    cpus = info["NCPU"]
    print(f"Docker capacity: {memory_gib:.1f} GiB RAM, {cpus} CPUs", flush=True)
    if memory_gib < requirements["memory_gib"] or cpus < requirements["cpus"]:
        raise RuntimeError(
            f"The {profile} streaming lab profile requires Docker capacity of at least "
            f"{requirements['memory_gib']} GiB RAM and {requirements['cpus']} CPUs "
            f"({requirements['description']}). "
            "Increase Docker Desktop resources or use a suitable local host. "
            "See environments/streaming/README.md. No containers were started."
        )
    print("Capacity is not free memory: check host/VM load and disk space before continuing.", flush=True)


def prepare_streaming(profile, *, start=False):
    if not start:
        raise ValueError("Read environments/streaming/README.md, then pass start=True")
    if profile not in ("kafka", "cdc"):
        raise ValueError("Choose kafka or cdc")
    print(compose("--profile", profile, "up", "-d", timeout=1800))
    if profile == "cdc":
        print(f"Flink Web UI: {configure_streaming_port()}")
    # Startup failures are retried only here; operational SQL failures are not hidden.
    def ready():
        try:
            if profile == "kafka":
                kafka("kafka-topics.sh", "--list")
            else:
                mysql("SELECT COUNT(*) FROM course_cdc.orders", show=False)
                response = requests.get(REST + "/overview", timeout=5)
                response.raise_for_status()
                return response.json()["slots-total"] >= 1
            return True
        except (RuntimeError, requests.RequestException) as error:
            return str(error)
    wait_for(ready, lambda value: value is True, description=f"{profile} startup", timeout=300)


def kafka(script, *arguments, input=None):
    return compose("exec", "-T", "kafka", "/opt/kafka/bin/" + script,
                   "--bootstrap-server", "course-stream-kafka:9092", *arguments,
                   input=input)


def produce(topic, rows):
    return kafka("kafka-console-producer.sh", "--topic", topic,
                 input="".join(json.dumps(row) + "\n" for row in rows))


def mysql(sql, *, show=True):
    """Render each MySQL result separately; use structured output, not TSV boundary guesses."""
    notebook = show and in_notebook()
    output_format = ["--xml"] if notebook else ["--batch", "--raw"]
    output = compose("exec", "-T", "mysql", "env", "MYSQL_PWD=course_stream_local_only",
                     "mysql", "--protocol=TCP", "-h127.0.0.1", "-uroot", *output_format, "-e", sql)
    if notebook:
        # mysql --xml emits one XML document per result, including empty result sets.
        documents = re.sub(r'<\?xml[^?]*\?>', '', output)
        results = ElementTree.fromstring("<results>" + documents + "</results>")
        for result in results:
            columns = [field.attrib["name"] for field in result.findall("row[1]/field")]
            rows = [
                [None if field.get("{http://www.w3.org/2001/XMLSchema-instance}nil") == "true"
                 else field.text or "" for field in row]
                for row in result.findall("row")
            ]
            show_frame(result.attrib["statement"], pd.DataFrame(rows, columns=columns))
        return ""
    return output


def flink_api(path):
    response = requests.get(REST + path, timeout=10)
    response.raise_for_status()
    return response.json()


def job_state(job):
    state = flink_api(f"/jobs/{job}")["state"]
    if state in {"FAILED", "CANCELED"}:
        raise RuntimeError(f"Flink job {job} is {state}; see {REST}/#/job/{job}/exceptions")
    return state


def check_flink_job(job):
    state = job_state(job)
    if state in {"FINISHED", "SUSPENDED"}:
        raise RuntimeError(f"Flink job {job} unexpectedly {state}; see {REST}/#/job/{job}/exceptions")


def active_flink_jobs():
    terminal = {"FINISHED", "CANCELED", "FAILED"}
    return [job for job in flink_api("/jobs/overview")["jobs"] if job["state"] not in terminal]


def cancel_flink_job(job):
    if re.fullmatch(r"[0-9a-f]{32}", job) is None:
        raise ValueError("Invalid Flink job ID")
    response = requests.patch(REST + f"/jobs/{job}", timeout=10)
    # The job can finish between /jobs/overview and PATCH /jobs/{jid}.
    # Flink then returns 404, which is already the desired cleanup state.
    if response.status_code == 404:
        return
    response.raise_for_status()


def cleanup_cdc_jobs():
    """Cancel only the continuous job owned by the optional CDC lab."""
    jobs = active_flink_jobs()
    unexpected = [job for job in jobs if job.get("name") != "course_mysql_orders"]
    if unexpected:
        names = [job.get("name", "<unnamed>") for job in unexpected]
        raise RuntimeError(f"Found active Flink jobs outside this lab: {names}")
    for job in jobs:
        cancel_flink_job(job["jid"])
    if jobs:
        wait_for(
            active_flink_jobs,
            lambda current: not current,
            description="stopping the previous CDC Flink job",
            timeout=120,
        )
    return jobs


def check_routine_load(lab, job):
    job = identifier(job)
    statement = f"SHOW ALL ROUTINE LOAD FOR {job}"
    with lab.connection.cursor() as cursor:
        cursor.execute(statement)
        names = [column[0] for column in cursor.description]
        rows = [dict(zip(names, row)) for row in cursor.fetchall()]
    if len(rows) != 1:
        raise RuntimeError(f"Expected one Routine Load job {job}; run {statement}: {rows!r}")
    status = rows[0]
    if status["State"] in {"PAUSED", "STOPPED", "CANCELLED"}:
        raise RuntimeError(
            f"Routine Load {job}: {status['State']}; "
            f"ReasonOfStateChanged={status['ReasonOfStateChanged']}; "
            f"ErrorLogUrls={status['ErrorLogUrls']}; run {statement}"
        )


def cleanup_kafka_routine_load(lab):
    """Stop only stale jobs created by this optional Kafka lab."""
    with lab.connection.cursor() as cursor:
        cursor.execute("SHOW ROUTINE LOAD")
        columns = [column[0] for column in cursor.description]
        jobs = [dict(zip(columns, row)) for row in cursor.fetchall()]
    stale = []
    for job in jobs:
        name = job["Name"]
        if (re.fullmatch(r"course_orders_[0-9a-f]{12}", name) is None
                or job["TableName"] != "ext_kafka_orders"):
            raise RuntimeError(
                f"Found an active Routine Load job outside this lab: {name}. "
                "Stop it manually only after confirming it belongs to this lab."
            )
        stale.append(name)
    for name in stale:
        lab.execute(f"STOP ROUTINE LOAD FOR {name}")
    if stale:
        wait_for(
            lambda: _routine_load_jobs(lab),
            lambda current: not current,
            description="stopping the previous Kafka Routine Load job",
            timeout=30,
        )
    return stale


def _routine_load_jobs(lab):
    with lab.connection.cursor() as cursor:
        cursor.execute("SHOW ROUTINE LOAD")
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def submit_sql(sql):
    if any(job.get("name") == "course_mysql_orders" for job in active_flink_jobs()):
        raise RuntimeError(
            "A course_mysql_orders job is already running; do not rerun the submission cell. "
            "Use the existing job or stop it intentionally before submitting a new one."
        )
    # Separate files prevent overwriting the SQL of a previous session.
    path = "/tmp/course-" + uuid4().hex + ".sql"
    output = compose("exec", "-T", "jobmanager", "sh", "-c",
                     f"cat > {path} && /opt/flink/bin/sql-client.sh -f {path}",
                     input=sql, timeout=180)
    print(output)
    jobs = re.findall(r"Job ID:\s*([0-9a-f]{32})", output)
    if len(jobs) != 1 or "[ERROR]" in output:
        raise RuntimeError("Expected one successful INSERT job; inspect SQL client output")
    job = jobs[0]
    wait_for(lambda: job_state(job),
             lambda state: state == "RUNNING", description="Flink RUNNING")
    return job


def wait_checkpoint(job):
    return wait_for(lambda: flink_api(f"/jobs/{job}/checkpoints"),
                    lambda result: result["counts"]["completed"] > 0,
                    description=f"completed checkpoint for {job}",
                    check_health=lambda: check_flink_job(job))


def stop_with_savepoint(job):
    if re.fullmatch(r"[0-9a-f]{32}", job) is None:
        raise ValueError("Invalid Flink job ID")
    output = compose("exec", "-T", "jobmanager", "/opt/flink/bin/flink", "stop",
                     "--savepointPath", "file:///opt/flink/state/savepoints", job,
                     timeout=180)
    print(output)
    match = re.search(r"Savepoint completed\. Path: (\S+)", output)
    if match is None:
        raise RuntimeError("No completed savepoint in CLI output")
    wait_for(lambda: job_state(job),
             lambda state: state == "FINISHED", description="stopped Flink job")
    return match.group(1)


def wait_rows(lab, table, expected, *, check_health, description=None):
    table = identifier(table)
    return wait_for(
        lambda: lab.query(f"SELECT * FROM {table} ORDER BY order_id"),
        lambda rows: normalized(rows) == normalized(expected),
        description=description or f"{table} matches expected rows",
        check_health=check_health,
    )
