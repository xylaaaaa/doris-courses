"""Extra sessions for Lab 14's Workload Group demonstrations; SQL stays in the notebook.

A queue is only visible when several sessions submit queries at the same time. These
helpers open those sessions, run one statement in the background, and read the
running and waiting counters that SHOW WORKLOAD GROUPS reports.

The sessions turn off SQL Cache, which is on in the course sandbox. Once a table has
been unchanged for about 30 seconds, Doris answers a repeated query from the cache
without queueing it or checking scan rules, so a learner who pauses between cells
would otherwise see no queue at all.
"""

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import pymysql

from .runtime import identifier
from .ui import show_records


@dataclass(frozen=True)
class QueryOutcome:
    label: str
    seconds: float
    error: str | None

    @property
    def result(self):
        """Return OK, or the Doris message without its errCode prefix."""
        if self.error is None:
            return "OK"
        return self.error.split("detailMessage = ", 1)[-1].strip()


SESSION_DEFAULTS = {"enable_sql_cache": False}


def open_session(lab, **session):
    """Open another connection to the lab database and apply session variables."""
    session = {**SESSION_DEFAULTS, **session}
    names = [identifier(name) for name in session]
    connection = pymysql.connect(
        host=lab.connection.host, port=lab.connection.port,
        user=lab.user, password=lab.password, database=lab.database,
        charset="utf8mb4", autocommit=True, connect_timeout=5, read_timeout=120,
    )
    try:
        with connection.cursor() as cursor:
            for name in names:
                cursor.execute(f"SET {name} = %s", (session[name],))
    except BaseException:
        connection.close()
        raise
    return connection


def run_query(lab, label, statement, **session):
    """Run one statement in its own session; a Doris error is part of the outcome."""
    connection = open_session(lab, **session)
    started = time.monotonic()
    error = None
    try:
        with connection.cursor() as cursor:
            cursor.execute(statement)
            cursor.fetchall()
    except pymysql.MySQLError as exc:
        error = str(exc.args[-1])
    finally:
        seconds = round(time.monotonic() - started, 1)
        connection.close()
    return QueryOutcome(label, seconds, error)


class BackgroundQuery:
    """Start run_query on a worker thread; result() waits for its outcome."""

    def __init__(self, lab, label, statement, **session):
        executor = ThreadPoolExecutor(max_workers=1)
        self._future = executor.submit(run_query, lab, label, statement, **session)
        executor.shutdown(wait=False)

    def result(self, timeout=60):
        return self._future.result(timeout=timeout)


def group_load(lab, group):
    """Return the running and waiting query counts of one Workload Group."""
    with lab.connection.cursor() as cursor:
        cursor.execute("SHOW WORKLOAD GROUPS LIKE %s", (group,))
        columns = [column[0] for column in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    rows = [row for row in rows if row["Name"] == group]
    if len(rows) != 1:
        raise RuntimeError(f"Expected one Workload Group named {group}, found {len(rows)}")
    return {"running": int(rows[0]["running_query_num"]), "waiting": int(rows[0]["waiting_query_num"])}


def wait_for_group(lab, group, *, running, waiting, timeout=10):
    """Poll until the group reports the expected counts, so the next step does not race the queue."""
    expected = {"running": running, "waiting": waiting}
    deadline = time.monotonic() + timeout
    while True:
        load = group_load(lab, group)
        if load == expected:
            return load
        if time.monotonic() >= deadline:
            raise TimeoutError(f"{group} did not reach {expected} within {timeout} s; last seen {load}")
        time.sleep(0.1)


def show_outcomes(title, outcomes):
    """Display each labelled statement's elapsed seconds and result."""
    show_records(title, [(o.label, o.seconds, o.result) for o in outcomes],
                 columns=["Query", "Seconds", "Result"])
