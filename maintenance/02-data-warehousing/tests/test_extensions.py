"""Offline checks for opt-in extension notebooks and their execution lifecycle."""

import ast
import runpy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import nbformat

REPO = Path(__file__).resolve().parents[3]
ROOT = REPO / "doris-course/02-data-warehousing"
RUNNER = REPO / "maintenance/02-data-warehousing/scripts/run_labs.py"


class ExtensionsTest(unittest.TestCase):
    def notebook(self, name):
        return nbformat.read(ROOT / "level1/extensions" / name, as_version=4)

    def test_clean_notebooks_compile_and_match_runner(self):
        runner = runpy.run_path(str(RUNNER))
        self.assertEqual(set(runner["EXTENSIONS"]), {p.name for p in (ROOT / "level1/extensions").glob("*.ipynb")})
        for name in runner["EXTENSIONS"]:
            notebook = self.notebook(name)
            nbformat.validate(notebook)
            for cell in notebook.cells:
                if cell.cell_type == "code":
                    ast.parse(cell.source)
                    self.assertEqual(cell.outputs, [])
                    self.assertIsNone(cell.execution_count)
            self.assertEqual(notebook.cells[-1].source, "lab.close()")

    def test_extension_resets_are_local(self):
        for path in (ROOT / "level1/extensions").glob("*.ipynb"):
            source = "\n".join(c.source for c in nbformat.read(path, 4).cells)
            self.assertNotIn("DROP DATABASE", source)
            self.assertNotIn("TRUNCATE", source)
            self.assertNotIn("DROP TABLE IF EXISTS orders_", source)
            self.assertNotIn("DROP TABLE IF EXISTS wwi_", source)

    def test_runner_closes_connection_and_restores_directory_on_failure(self):
        runner = runpy.run_path(str(RUNNER))
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "failure.ipynb"
            # Capture the per-notebook lab without connecting to a database.
            close = Mock()
            source = "import builtins\nlab = builtins._extension_test_lab\nraise RuntimeError('expected-notebook-failure')"
            nbformat.write(nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell(source)]), path)
            import builtins
            from unittest.mock import patch
            lab = Mock(close=close)
            lab.connection.open = True
            with patch.object(builtins, "_extension_test_lab", lab, create=True):
                with self.assertRaisesRegex(RuntimeError, "expected-notebook-failure"):
                    runner["execute_notebook"](path)
            close.assert_called_once_with()
            self.assertEqual(Path.cwd(), previous)

    def test_broker_cancel_is_failure_not_success(self):
        nb = self.notebook("extension45_files_and_group_commit.ipynb")
        source = next(c.source for c in nb.cells if c.cell_type == "code" and 'LOAD LABEL' in c.source)
        lab = Mock(database="dw_course_l1_test")
        lab.query.return_value = [(1,"label","CANCELLED","reason")]
        namespace = dict(lab=lab,history_ddl=lambda table: table,HISTORY_COLUMNS=("order_id",),
                         tvf="fake",uuid4=lambda:Mock(hex="test"),uri="s3://test/file",ACCESS_KEY="test",SECRET_KEY="test",show_sql=Mock())
        with self.assertRaisesRegex(RuntimeError,"Broker Load cancelled"):
            exec(compile(source,"broker-cell","exec"),namespace)
        self.assertEqual(lab.query.call_count, 1)

    def test_broker_timeout_cancels_only_its_label(self):
        from unittest.mock import patch
        nb = self.notebook("extension45_files_and_group_commit.ipynb")
        source = next(c.source for c in nb.cells if c.cell_type == "code" and 'LOAD LABEL' in c.source)
        lab = Mock(database="dw_course_l1_test")
        lab.query.return_value = [(1,"label","LOADING")]
        namespace = dict(lab=lab,history_ddl=lambda table: table,HISTORY_COLUMNS=("order_id",),
                         tvf="fake",uuid4=lambda:Mock(hex="test"),uri="s3://test/file",ACCESS_KEY="test",SECRET_KEY="test",show_sql=Mock())
        with patch("time.monotonic", side_effect=[0,151]):
            with self.assertRaisesRegex(TimeoutError,"Broker Load timeout"):
                exec(compile(source,"broker-cell","exec"),namespace)
        lab.execute.assert_called_with("CANCEL LOAD WHERE LABEL = %s", ("ext_broker_test",))

    def test_old_finished_schema_job_does_not_prove_new_column_exists(self):
        from unittest.mock import MagicMock, patch
        nb = self.notebook("extension67_schema_and_delete.ipynb")
        source = next(c.source for c in nb.cells if c.cell_type == "code" and 'for statement, column' in c.source)
        lab = Mock()
        def query(sql):
            if sql.startswith("DESC"):
                return [("order_id","bigint"),("amount_cents","int")]
            if "COUNT(*)" in sql:
                return [(10,140000)]
            return [(900001,10000)]
        lab.query.side_effect = query
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.description = [("State",)]
        cursor.fetchall.return_value = [("FINISHED",)]
        lab.connection.cursor.return_value = cursor
        from dw_course.runtime import expect
        with patch("time.monotonic", side_effect=[0,121]):
            with self.assertRaises(TimeoutError):
                exec(compile(source,"schema-cell","exec"),dict(lab=lab,expect=expect,show_sql=Mock()))

    def test_defaults_deletion_and_conflict_have_concrete_oracles(self):
        ingest = "\n".join(c.source for c in self.notebook("extension45_files_and_group_commit.ipynb").cells)
        state = "\n".join(c.source for c in self.notebook("extension67_schema_and_delete.ipynb").cells)
        for text in ('"CREATED","180.00"', '"PAID","80.00"', 'result["GroupCommit"]', 'order_rows(fixture("orders.json"))'):
            self.assertIn(text,ingest)
        for text in ('"merge_type":"MERGE"', '"delete":"op=\'DELETE\'"', '[(900001,"PAID",3)]', 'HAVING COUNT(*)>1', 'expected_failure'):
            self.assertIn(text,state)

    def test_profile_and_group_settings_are_restored(self):
        nb = self.notebook("extension23_physical_design.ipynb")
        source = next(c.source for c in nb.cells if c.cell_type == "code" and 'previous_profile' in c.source)
        lab = Mock()
        lab.query.return_value = [(False,)]
        lab.sql.side_effect = RuntimeError("expected-query-failure")
        with self.assertRaisesRegex(RuntimeError,"expected-query-failure"):
            exec(compile(source,"profile-cell","exec"),dict(lab=lab))
        lab.execute.assert_called_with("SET enable_profile = %s", (False,))

    def test_backlog_distinguishes_optional_integrations(self):
        text = (REPO / "maintenance/02-data-warehousing/integration-backlog.md").read_text()
        self.assertNotRegex(text,r'\bD0[1-7]\b')
        for label in ('Module 5.6', 'Module 5.7', 'Module 5.8', 'Module 5.9', '不是当前结课门槛', 'Lab 5A / 5B 均选做'):
            self.assertIn(label,text)
        self.assertNotIn("仍需交付的持续集成实验", text)
        self.assertNotIn("不能因主线与扩展全部通过而宣布完整 Level 1 已结课验收", text)

    def test_readings_separate_main_scope_and_optional_integrations(self):
        level = REPO / "doris-course/02-data-warehousing/level1"
        expectations = {
            "README.md": ("not required to set up external pipelines", "continuous ingestion Labs are all optional", "optional5_kafka_routine_load.ipynb", "optional5_flink_mysql_cdc.ipynb"),
            "module05-ingestion/course5_batch_and_streaming_ingestion.md": (
                "Sections 5.6–5.9 are introductions", "continuous concurrency validation is not a completion requirement"),
            "module07-state-changes/course7_updates_deletes_and_replay.md": (
                "does not require real CDC setup", "Lab 7 uses simulated events", "controlled Savepoint"),
        }
        for name, phrases in expectations.items():
            with self.subTest(reading=name):
                text = (level / name).read_text()
                for phrase in phrases:
                    self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
