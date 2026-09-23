"""Offline regression checks for optional streaming orchestration and notebooks."""
import ast
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

import nbformat
import yaml

ROOT = Path(__file__).resolve().parents[3] / "doris-course/02-data-warehousing"
sys.path.insert(0, str(ROOT))
from dw_course import streaming, docker_runtime


class StreamingTest(unittest.TestCase):
    def test_explicit_opt_in_and_profiles(self):
        with patch.object(streaming, "compose") as command:
            for args in [("kafka", False), ("other", True)]:
                with self.assertRaises(ValueError):
                    streaming.prepare_streaming(args[0], start=args[1])
            command.assert_not_called()

    def test_streaming_port_is_dynamic_and_rest_client_follows_it(self):
        with patch.object(streaming, "compose", return_value="127.0.0.1:49123\n"):
            self.assertEqual(streaming.configure_streaming_port(), 49123)
        self.assertEqual(streaming.REST, "http://127.0.0.1:49123")

    def test_mysql_renders_result_sets_as_notebook_tables(self):
        output = (
            '<?xml version="1.0"?>\n'
            '<resultset statement="SHOW MASTER STATUS">'
            '<row><field name="File">mysql-bin.000001</field>'
            '<field name="Position">123</field></row></resultset>\n'
            '<?xml version="1.0"?>\n'
            '<resultset statement="SELECT * FROM orders">'
            '<row><field name="order_id">920001</field>'
            '<field name="order_status">CREATED</field></row></resultset>\n'
        )
        with patch.object(streaming, "compose", return_value=output), patch.object(
            streaming, "in_notebook", return_value=True
        ), patch.object(streaming, "show_frame") as show:
            self.assertEqual(streaming.mysql("SHOW MASTER STATUS; SELECT * FROM orders"), "")
        self.assertEqual(show.call_count, 2)
        self.assertEqual(list(show.call_args_list[1].args[1].columns), ["order_id", "order_status"])

    def test_wait_returns_only_matching_observation(self):
        read = Mock(side_effect=[[], [1]])
        with patch.object(streaming.time, "sleep"):
            self.assertEqual(streaming.wait_for(read, lambda x: x == [1], description="test"), [1])
        self.assertEqual(read.call_count, 2)

    def test_wait_renders_live_notebook_progress(self):
        handle = Mock()
        read = Mock(side_effect=[False, True])
        with patch.object(streaming, "get_ipython", return_value=object()), patch.object(
            streaming, "display", return_value=handle
        ) as display, patch.object(streaming.time, "sleep"):
            self.assertTrue(streaming.wait_for(read, bool, description="service startup"))
        self.assertEqual(display.call_count, 1)
        self.assertEqual(handle.update.call_count, 2)

    def test_completed_notebook_progress_is_full_green(self):
        handle = Mock()
        with patch.object(streaming, "get_ipython", return_value=object()), patch.object(
            streaming, "display", return_value=handle
        ) as display:
            streaming._render_wait_progress("finished", 0, 180, 1, state="success")
        content = display.call_args.args[0].data
        self.assertIn("width:100%", content)
        self.assertIn("background:#16a34a", content)

    def test_timeout_reports_last_observation(self):
        with patch.object(streaming.time, "monotonic", side_effect=[0, 0, 2]), patch.object(streaming.time, "sleep"):
            with self.assertRaisesRegex(TimeoutError, "last observation = 'lagging'"):
                streaming.wait_for(lambda: "lagging", bool_false, description="test", timeout=1)

    def test_sql_client_errors_are_not_success(self):
        with patch.object(streaming, "active_flink_jobs", return_value=[]), patch.object(
            streaming, "compose", return_value="[ERROR] connector missing"
        ):
            with self.assertRaisesRegex(RuntimeError, "successful INSERT"):
                streaming.submit_sql("INSERT INTO sink SELECT * FROM src")

    def test_submit_extracts_job_and_waits_for_running(self):
        job = "a" * 32
        def response(path):
            return {"jobs": []} if path == "/jobs/overview" else {"state": "RUNNING"}

        with patch.object(streaming, "compose", return_value="Job ID: " + job), patch.object(
            streaming, "flink_api", side_effect=response
        ):
            self.assertEqual(streaming.submit_sql("SQL"), job)

    def test_submit_rejects_duplicate_course_cdc_job(self):
        with patch.object(
            streaming, "active_flink_jobs", return_value=[{"name": "course_mysql_orders"}]
        ), patch.object(streaming, "compose") as command:
            with self.assertRaisesRegex(RuntimeError, "already running"):
                streaming.submit_sql("SQL")
        command.assert_not_called()

    def test_terminal_failure_is_reported_without_waiting(self):
        with patch.object(streaming, "flink_api", return_value={"state": "FAILED"}):
            with self.assertRaisesRegex(RuntimeError, "FAILED; see"):
                streaming.job_state("a" * 32)

    def test_failed_job_cannot_pass_with_old_checkpoint(self):
        def response(path):
            return {"state": "FAILED"} if path.endswith("/job") else {"counts": {"completed": 1}}
        with patch.object(streaming, "flink_api", side_effect=response), patch.object(streaming.time, "sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError, "FAILED; see"):
                streaming.wait_checkpoint("job")
            sleep.assert_not_called()

    def test_checkpoint_wait_checks_health_on_every_poll(self):
        with patch.object(streaming, "check_flink_job") as health, patch.object(
            streaming, "flink_api", side_effect=[{"counts": {"completed": 0}}, {"counts": {"completed": 1}}]
        ), patch.object(streaming.time, "sleep"):
            self.assertEqual(streaming.wait_checkpoint("job")["counts"]["completed"], 1)
            self.assertEqual(health.call_count, 2)

    def test_data_wait_checks_health_before_accepting_matching_rows(self):
        lab = Mock()
        lab.query.return_value = [[1]]
        health = Mock(side_effect=RuntimeError("job failed"))
        with self.assertRaisesRegex(RuntimeError, "job failed"):
            streaming.wait_rows(lab, "orders", [[1]], check_health=health)
        lab.query.assert_not_called()

    def test_data_wait_healthy_job(self):
        lab = Mock()
        lab.query.return_value = [[1]]
        health = Mock()
        self.assertEqual(streaming.wait_rows(lab, "orders", [[1]], check_health=health), [[1]])
        health.assert_called_once()

    def test_data_wait_accepts_a_specific_description(self):
        lab = Mock()
        lab.query.return_value = [[1]]
        with patch.object(streaming, "wait_for", return_value=[[1]]) as wait:
            streaming.wait_rows(lab, "orders", [[1]], check_health=Mock(), description="after resume")
        self.assertEqual(wait.call_args.kwargs["description"], "after resume")

    def test_unexpected_flink_finish_and_suspension(self):
        for state in ("FINISHED", "SUSPENDED", "CANCELED"):
            with self.subTest(state=state), patch.object(streaming, "flink_api", return_value={"state": state}):
                with self.assertRaisesRegex(RuntimeError, state):
                    streaming.check_flink_job("job")

    def test_routine_load_diagnostics_and_normal_states(self):
        lab = Mock()
        cursor = lab.connection.cursor.return_value.__enter__ = Mock()
        lab.connection.cursor.return_value.__exit__ = Mock(return_value=False)
        cursor.return_value.description = [("State",), ("ReasonOfStateChanged",), ("ErrorLogUrls",)]
        for state in ("PAUSED", "STOPPED", "CANCELLED", "RUNNING", "NEED_SCHEDULE"):
            cursor.return_value.fetchall.return_value = [(state, "bad amount", "http://error")]
            if state in ("RUNNING", "NEED_SCHEDULE"):
                streaming.check_routine_load(lab, "course_orders_abc")
            else:
                with self.assertRaisesRegex(RuntimeError, state + ".*bad amount.*http://error"):
                    streaming.check_routine_load(lab, "course_orders_abc")
        cursor.return_value.fetchall.return_value = []
        with self.assertRaisesRegex(RuntimeError, "Expected one Routine Load"):
            streaming.check_routine_load(lab, "course_orders_abc")

    def test_cleanup_stops_only_stale_course_kafka_jobs(self):
        lab = Mock()
        context = lab.connection.cursor.return_value
        cursor = context.__enter__ = Mock()
        context.__exit__ = Mock(return_value=False)
        cursor.return_value.description = [("Name",), ("TableName",)]
        cursor.return_value.fetchall.side_effect = [
            [("course_orders_" + "a" * 12, "ext_kafka_orders")], []
        ]
        self.assertEqual(streaming.cleanup_kafka_routine_load(lab), ["course_orders_" + "a" * 12])
        lab.execute.assert_called_once_with("STOP ROUTINE LOAD FOR course_orders_aaaaaaaaaaaa")

    def test_cleanup_cancels_only_stale_course_cdc_jobs(self):
        job_id = "b" * 32
        response = Mock()
        with patch.object(streaming, "flink_api", side_effect=[
            {"jobs": [{"jid": job_id, "name": "course_mysql_orders", "state": "RUNNING"}]},
            {"jobs": []},
        ]), patch.object(streaming.requests, "patch", return_value=response) as patch_request:
            self.assertEqual(streaming.cleanup_cdc_jobs()[0]["jid"], job_id)
        patch_request.assert_called_once()
        response.raise_for_status.assert_called_once()

    def test_cleanup_accepts_job_that_finished_before_cancel(self):
        job_id = "c" * 32
        response = Mock(status_code=404)
        with patch.object(streaming, "active_flink_jobs", side_effect=[
            [{"jid": job_id, "name": "course_mysql_orders", "state": "RUNNING"}],
            [],
        ]), patch.object(streaming.requests, "patch", return_value=response):
            self.assertEqual(streaming.cleanup_cdc_jobs()[0]["jid"], job_id)

    def test_cancel_treats_missing_job_as_already_cancelled(self):
        response = Mock(status_code=404)
        with patch.object(streaming.requests, "patch", return_value=response):
            streaming.cancel_flink_job("d" * 32)
        response.raise_for_status.assert_not_called()

    def test_resource_profile_and_base_configuration(self):
        overlay = ROOT / "environments/streaming/doris-resources.yml"
        config = yaml.safe_load(overlay.read_text())
        self.assertEqual(config["services"]["doris"], {"mem_limit": "12g", "memswap_limit": "12g"})
        self.assertNotIn(str(overlay), docker_runtime.compose_command("up"))
        command = docker_runtime.compose_command("up", streaming=True)
        self.assertIn(str(overlay), command)
        self.assertIn("doris-warehousing-course", command)
        self.assertEqual(command[-1], "up")

    def test_kafka_resource_profile_uses_lightweight_overlay(self):
        overlay = ROOT / "environments/streaming/doris-resources-kafka.yml"
        config = yaml.safe_load(overlay.read_text())
        self.assertEqual(config["services"]["doris"], {"mem_limit": "8g", "memswap_limit": "8g"})
        kafka = yaml.safe_load(streaming.COMPOSE.read_text())["services"]["kafka"]
        self.assertEqual(kafka["mem_limit"], "1g")
        self.assertEqual(kafka["memswap_limit"], "1g")
        self.assertEqual(kafka["environment"]["KAFKA_HEAP_OPTS"], "-Xms256m -Xmx512m")
        command = docker_runtime.compose_command("up", streaming=True, streaming_profile="kafka")
        self.assertIn(str(overlay), command)

    def test_resource_preflight_capacity(self):
        for profile, gib, cpus, succeeds, minimum_memory, minimum_cpus in [
            ("kafka", 10, 2, True, 10, 2), ("kafka", 9, 2, False, 10, 2),
            ("kafka", 10, 1, False, 10, 2), ("cdc", 18, 4, True, 18, 4),
            ("cdc", 17, 4, False, 18, 4), ("cdc", 32, 2, False, 18, 4),
        ]:
            with self.subTest(gib=gib, cpus=cpus), patch.object(streaming.subprocess, "run", return_value=Mock(
                stdout=json.dumps({"MemTotal": gib * 1024**3, "NCPU": cpus})
            )):
                if succeeds:
                    streaming.check_resources(profile)
                else:
                    with self.assertRaisesRegex(RuntimeError, f"{minimum_memory} GiB RAM and {minimum_cpus} CPUs"):
                        streaming.check_resources(profile)

    def test_resource_failure_precedes_container_start(self):
        with patch.object(streaming, "check_resources", side_effect=RuntimeError("capacity")), patch.object(docker_runtime, "_run") as run:
            with self.assertRaisesRegex(RuntimeError, "capacity"):
                docker_runtime.prepare_environment(start=True, streaming=True)
            run.assert_not_called()

    def test_streaming_startup_uses_overlay_for_every_compose_command(self):
        with patch.object(streaming, "check_resources") as check, patch.object(docker_runtime, "_run") as run, patch.object(docker_runtime, "_verify_sql"), patch.object(docker_runtime, "WorkflowProgress"):
            docker_runtime.prepare_environment(start=True, streaming=True, streaming_profile="kafka")
            check.assert_called_once()
            check.assert_called_once_with("kafka")
            commands = [call.args[0] for call in run.call_args_list if call.args[0][:2] == ["docker", "compose"] and "--project-name" in call.args[0]]
            self.assertEqual(len(commands), 4)
            for command in commands:
                self.assertIn(str(ROOT / "environments/streaming/doris-resources-kafka.yml"), command)

    def test_optional_notebooks_are_english_and_use_checked_waits(self):
        for path in (ROOT / "level1/module05-ingestion").glob("optional5_*.ipynb"):
            notebook = nbformat.read(path, 4)
            source = "\n".join(cell.source for cell in notebook.cells)
            self.assertNotRegex(source, r"[\u4e00-\u9fff]")
            self.assertRegex(source, r'prepare_environment\(start=True, streaming=True, streaming_profile="(?:kafka|cdc)"\)')
            for cell in notebook.cells:
                if cell.cell_type == "code":
                    for node in ast.walk(ast.parse(cell.source)):
                        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "wait_rows":
                            self.assertIn("check_health", [keyword.arg for keyword in node.keywords])

    def test_mysql_timezone_matches_cdc_notebook(self):
        config = yaml.safe_load(streaming.COMPOSE.read_text())
        self.assertIn("--default-time-zone=+08:00", config["services"]["mysql"]["command"])
        notebook = nbformat.read(ROOT / "level1/module05-ingestion/optional5_flink_mysql_cdc.ipynb", 4)
        self.assertIn("'server-time-zone'='Asia/Shanghai'", "\n".join(c.source for c in notebook.cells))

    def test_savepoint_requires_job_id_and_completed_path(self):
        with self.assertRaises(ValueError):
            streaming.stop_with_savepoint("not-a-job; echo bad")
        with patch.object(streaming, "compose", return_value="savepoint failed"):
            with self.assertRaisesRegex(RuntimeError, "No completed savepoint"):
                streaming.stop_with_savepoint("a" * 32)

    def test_compose_failures_include_output(self):
        with patch.object(streaming.subprocess, "run", return_value=Mock(returncode=1, stdout="fixture failed")):
            with self.assertRaisesRegex(RuntimeError, "fixture failed"):
                streaming.compose("ps")

    def test_local_services_pinned_and_private(self):
        config = yaml.safe_load(streaming.COMPOSE.read_text())
        self.assertEqual(config["name"], "doris-warehousing-streaming")
        self.assertTrue(config["networks"]["doris"]["external"])
        for service in config["services"].values():
            self.assertNotIn(":latest", service["image"])
            for port in service.get("ports", []):
                self.assertTrue(port.startswith("127.0.0.1:"))
        self.assertNotIn("ports", config["services"]["mysql"])
        self.assertNotIn("ports", config["services"]["kafka"])
        self.assertEqual(config["services"]["jobmanager"]["ports"], ["127.0.0.1::8081"])

    def test_notebooks_are_clean_and_teaching_sql_visible(self):
        paths = sorted((ROOT / "level1/module05-ingestion").glob("optional5_*.ipynb"))
        self.assertEqual(len(paths), 2)
        sources = []
        for path in paths:
            notebook = nbformat.read(path, 4)
            nbformat.validate(notebook)
            for cell in notebook.cells:
                if cell.cell_type == "code":
                    ast.parse(cell.source)
                    self.assertEqual(cell.outputs, [])
                    self.assertIsNone(cell.execution_count)
            text = "\n".join(c.source for c in notebook.cells)
            self.assertIn('dw_course_l1_streaming', text)
            self.assertNotIn("DROP DATABASE", text)
            self.assertNotIn("down -v", text)
            self.assertIn("lab.close()", notebook.cells[-1].source)
            sources.append(text)
        self.assertIn("CREATE ROUTINE LOAD", "\n".join(sources))
        self.assertIn("'connector'='mysql-cdc'", "\n".join(sources))
        self.assertIn('restored["external_path"]', "\n".join(sources))


def bool_false(value):
    return False
