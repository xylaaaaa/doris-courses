"""Offline checks for the extra sessions that Lab 14 uses to show Workload Group queues."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, call, patch

import pymysql

ROOT = Path(__file__).resolve().parents[3] / "doris-course/02-data-warehousing"
sys.path.insert(0, str(ROOT))
from dw_course import workload


def fake_lab(cursor=None):
    connection = SimpleNamespace(host="127.0.0.1", port=52030, cursor=lambda: cursor)
    return SimpleNamespace(connection=connection, user="root", password="secret",
                           database="dw_course_l1_demo")


def fake_connection():
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    return connection, cursor


class OpenSessionTest(unittest.TestCase):
    def test_session_variables_are_validated_names_with_bound_values(self):
        connection, cursor = fake_connection()
        with patch.object(workload.pymysql, "connect", return_value=connection) as connect:
            session = workload.open_session(fake_lab(), workload_group="course_adhoc_l3", query_timeout=2)
        self.assertIs(session, connection)
        self.assertEqual(connect.call_args.kwargs["database"], "dw_course_l1_demo")
        self.assertTrue(connect.call_args.kwargs["autocommit"])
        self.assertEqual(cursor.execute.call_args_list, [
            call("SET enable_sql_cache = %s", (False,)),
            call("SET workload_group = %s", ("course_adhoc_l3",)),
            call("SET query_timeout = %s", (2,)),
        ])
        connection.close.assert_not_called()

    def test_a_caller_can_turn_sql_cache_back_on(self):
        # Cache hits skip the queue and scan rules, so the default keeps every lab query real.
        connection, cursor = fake_connection()
        with patch.object(workload.pymysql, "connect", return_value=connection):
            workload.open_session(fake_lab(), enable_sql_cache=True)
        self.assertEqual(cursor.execute.call_args_list, [call("SET enable_sql_cache = %s", (True,))])

    def test_unsafe_variable_names_are_rejected_before_connecting(self):
        with patch.object(workload.pymysql, "connect") as connect:
            with self.assertRaises(ValueError):
                workload.open_session(fake_lab(), **{"query_timeout = 1; DROP TABLE x": 1})
        connect.assert_not_called()

    def test_connection_is_closed_when_a_session_variable_fails(self):
        connection, cursor = fake_connection()
        cursor.execute.side_effect = pymysql.err.OperationalError(1105, "unknown variable")
        with patch.object(workload.pymysql, "connect", return_value=connection):
            with self.assertRaises(pymysql.err.OperationalError):
                workload.open_session(fake_lab(), workload_group="course_adhoc_l3")
        connection.close.assert_called_once_with()


class RunQueryTest(unittest.TestCase):
    def run_with(self, connection, *, raises=None):
        with patch.object(workload, "open_session", return_value=connection) as opened, \
                patch.object(workload.time, "monotonic", side_effect=[10.0, 12.34]):
            if raises is None:
                return workload.run_query(fake_lab(), "A", "SELECT 1", workload_group="g"), opened
            with self.assertRaises(raises):
                workload.run_query(fake_lab(), "A", "SELECT 1", workload_group="g")
            return None, opened

    def test_success_records_elapsed_seconds_and_closes_the_session(self):
        connection, cursor = fake_connection()
        outcome, opened = self.run_with(connection)
        self.assertEqual(outcome, workload.QueryOutcome("A", 2.3, None))
        self.assertEqual(outcome.result, "OK")
        self.assertEqual(opened.call_args.kwargs, {"workload_group": "g"})
        cursor.execute.assert_called_once_with("SELECT 1")
        cursor.fetchall.assert_called_once_with()
        connection.close.assert_called_once_with()

    def test_doris_errors_become_part_of_the_outcome(self):
        connection, cursor = fake_connection()
        message = ("errCode = 2, detailMessage = query waiting queue is full, "
                   "queue capacity=1, waiting num=1")
        cursor.execute.side_effect = pymysql.err.OperationalError(1105, message)
        outcome, _ = self.run_with(connection)
        self.assertEqual(outcome.error, message)
        self.assertEqual(outcome.result, "query waiting queue is full, queue capacity=1, waiting num=1")
        connection.close.assert_called_once_with()

    def test_other_failures_propagate_after_closing_the_session(self):
        connection, cursor = fake_connection()
        cursor.fetchall.side_effect = RuntimeError("driver bug")
        self.run_with(connection, raises=RuntimeError)
        connection.close.assert_called_once_with()

    def test_messages_without_a_prefix_are_kept(self):
        outcome = workload.QueryOutcome("B", 0.0, "Access denied; you need the USAGE privilege")
        self.assertEqual(outcome.result, "Access denied; you need the USAGE privilege")


class BackgroundQueryTest(unittest.TestCase):
    def test_result_waits_for_the_worker_outcome(self):
        expected = workload.QueryOutcome("A", 6.0, None)
        with patch.object(workload, "run_query", return_value=expected) as run:
            query = workload.BackgroundQuery(fake_lab(), "A", "SELECT 1", workload_group="g")
            self.assertIs(query.result(timeout=5), expected)
        self.assertEqual(run.call_args.args[1:], ("A", "SELECT 1"))
        self.assertEqual(run.call_args.kwargs, {"workload_group": "g"})


class GroupLoadTest(unittest.TestCase):
    def lab_with_rows(self, rows):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.description = [("Id",), ("Name",), ("running_query_num",), ("waiting_query_num",)]
        cursor.fetchall.return_value = rows
        return fake_lab(cursor), cursor

    def test_counts_come_from_the_exactly_named_group(self):
        lab, cursor = self.lab_with_rows([
            ("1", "course_adhoc_l3", "1", "1"),
            ("2", "course_adhocxl3", "5", "5"),
        ])
        self.assertEqual(workload.group_load(lab, "course_adhoc_l3"), {"running": 1, "waiting": 1})
        cursor.execute.assert_called_once_with("SHOW WORKLOAD GROUPS LIKE %s", ("course_adhoc_l3",))

    def test_a_missing_group_is_an_error(self):
        lab, _ = self.lab_with_rows([("2", "course_adhocxl3", "0", "0")])
        with self.assertRaisesRegex(RuntimeError, "found 0"):
            workload.group_load(lab, "course_adhoc_l3")

    def test_wait_for_group_polls_until_the_expected_counts(self):
        loads = [{"running": 0, "waiting": 0}, {"running": 1, "waiting": 0}]
        with patch.object(workload, "group_load", side_effect=loads), \
                patch.object(workload.time, "sleep") as sleep:
            load = workload.wait_for_group(fake_lab(), "g", running=1, waiting=0)
        self.assertEqual(load, {"running": 1, "waiting": 0})
        sleep.assert_called_once_with(0.1)

    def test_wait_for_group_reports_the_last_counts_on_timeout(self):
        with patch.object(workload, "group_load", return_value={"running": 1, "waiting": 0}), \
                patch.object(workload.time, "monotonic", side_effect=[0.0, 5.0, 11.0]), \
                patch.object(workload.time, "sleep"):
            with self.assertRaisesRegex(TimeoutError, r"last seen \{'running': 1, 'waiting': 0\}"):
                workload.wait_for_group(fake_lab(), "g", running=1, waiting=1, timeout=10)


class ShowOutcomesTest(unittest.TestCase):
    def test_rows_show_label_seconds_and_result(self):
        outcomes = [workload.QueryOutcome("A", 6.0, None),
                    workload.QueryOutcome("C", 0.0, "errCode = 2, detailMessage = queue is full")]
        with patch.object(workload, "show_records") as show:
            workload.show_outcomes("Queue", outcomes)
        show.assert_called_once_with("Queue", [("A", 6.0, "OK"), ("C", 0.0, "queue is full")],
                                     columns=["Query", "Seconds", "Result"])
