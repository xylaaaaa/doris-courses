"""Learner-facing checks, including expected errors and independent exercises."""

import ast
import json
import re
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

ROOT = Path(__file__).resolve().parents[3] / "doris-course/02-data-warehousing"
sys.path.insert(0, str(ROOT))
from dw_course import runtime
from dw_course import wwi


class LearningFlowTest(unittest.TestCase):
    def notebook_cells(self, module):
        path = next((ROOT / "level1" / module).glob("lab*.ipynb"))
        return {c["id"]: "".join(c["source"]) for c in json.loads(path.read_text())["cells"]}

    def reading(self, module):
        return next((ROOT / "level1" / module).glob("course*.md")).read_text()

    def test_reading_ddl_and_classification_match_lab_sql(self):
        for module, prefix in (("module03-table-design", "CREATE TABLE orders_partitioned"),
                               ("module06-data-quality", "CREATE VIEW orders_classified")):
            blocks = re.findall(r"```sql\n(.*?)```", self.reading(module), re.DOTALL)
            excerpt = next(block for block in blocks if block.startswith(prefix))
            source = "\n".join(self.notebook_cells(module).values())
            self.assertIn(" ".join(excerpt.strip().rstrip(";").split()), " ".join(source.split()))
        quality = self.reading("module06-data-quality")
        self.assertIn("CASE WHEN", quality)
        for fragment in ("WHERE reject_reason IS NULL", "WHERE reject_reason IS NOT NULL",
                         "Lightweight Schema Change", "Heavyweight Schema Change"):
            self.assertIn(fragment, quality)

    def test_profile_example_restores_session_and_explains_fields(self):
        reading = self.reading("module02-architecture")
        source = re.search(r"```python\n(.*?)```", reading, re.DOTALL)[1]
        lab = Mock()
        for previous in (True, False):
            lab.reset_mock()
            lab.query.return_value = [(previous,)]
            exec(compile(source, "profile-reading", "exec"), {"lab": lab})
            lab.execute.assert_any_call("SET enable_profile = %s", (previous,))
        lab.sql.side_effect = RuntimeError("query failed")
        with self.assertRaisesRegex(RuntimeError, "query failed"):
            exec(compile(source, "profile-reading", "exec"), {"lab": lab})
        self.assertEqual(lab.execute.call_args.args, ("SET enable_profile = %s", (False,)))
        for field in ("VersionCount", "CompactionStatus", "TabletId", "SHOW QUERY PROFILE"):
            self.assertIn(field, reading)

    def test_catalog_reading_matches_fixture_properties(self):
        reading = self.reading("module04-external-access")
        fixture_source = (ROOT / "dw_course/lakehouse.py").read_text()
        for fragment in ('"type"="iceberg"', '"iceberg.catalog.type"="rest"',
                         '"use_path_style"="true"', '"iceberg.rest.view-enabled"="false"'):
            self.assertIn(fragment, reading)
            self.assertIn(fragment, fixture_source)
        self.assertIn("External environment example; do not rerun it alongside the lab", reading)

    def test_ingestion_keeps_cdc_boundary_and_optional_accounting(self):
        reading = self.reading("module05-ingestion")
        cdc = reading.split("## 5.8 Streaming Job and CDC_STREAM", 1)[1].split("## 5.9", 1)[0]
        self.assertIn("Experimental", cdc.split("###", 1)[0])
        self.assertIn('DEFAULT "CREATED"', reading)
        self.assertIn("optional_invoice_and_receipts.md", reading)
        cells = self.notebook_cells("module05-ingestion")
        self.assertNotIn("TransactionTypeName", cells["historical-check"])
        self.assertIn("wwi_order_lines", cells["historical-check"])
        optional = (ROOT / "level1/module05-ingestion/optional_invoice_and_receipts.md").read_text()
        self.assertIn("267011.44", optional)
        self.assertIn("TransactionTypeName", optional)
        for block in re.findall(r"```sql\n(.*?)```", optional, re.DOTALL):
            for statement in (part.strip() for part in block.split(";") if part.strip()):
                self.assertTrue(statement.startswith("SELECT"))

    def test_update_reading_teaches_operations_and_distinct_delete_mechanisms(self):
        reading = self.reading("module07-state-changes")
        for fragment in ("INSERT INTO orders_partial_update", "UPDATE orders_delete_demo",
                         "DELETE FROM orders_delete_demo", "__DORIS_DELETE_SIGN__", "Delete Bitmap",
                         "try/finally", "does not run a load deletion marker experiment"):
            self.assertIn(fragment, reading)

    def test_first_load_teaches_http_before_independent_work(self):
        cells = self.notebook_cells("module05-ingestion")
        source = cells["cell-4"]
        lab = Mock(database="dw_course_l1_test", user="root", password="")
        lab.query.return_value = [(10, "1400.00")]
        response = Mock()
        response.json.return_value = {"Status": "Success", "NumberLoadedRows": 10,
                                      "NumberFilteredRows": 0}
        namespace = {"lab": lab, "order_ddl": lambda _: "DDL", "show_sql": Mock(),
                     "show_response": Mock(), "expect": runtime.expect, "COURSE_ROOT": ROOT,
                     "dataset_path": runtime.dataset_path,
                     "ORDER_COLUMNS": ("order_id", "customer_id"), "uuid4": lambda: Mock(hex="test")}
        with patch.dict("os.environ", {"DW_BE_HTTP_URL": "http://example.invalid:8040"}), \
                patch("requests.put", return_value=response) as put:
            exec(compile(source, "first-http-load", "exec"), namespace)
        self.assertEqual(put.call_args.args[0],
                         "http://example.invalid:8040/api/dw_course_l1_test/orders_imported/_stream_load")
        args = put.call_args.kwargs
        self.assertEqual(args["headers"]["columns"], "order_id,customer_id")
        self.assertEqual(args["headers"]["label"], namespace["label"])
        self.assertEqual(args["headers"]["group_commit"], "off_mode")
        self.assertEqual(args["headers"]["max_filter_ratio"], "0")
        self.assertEqual(args["auth"], ("root", ""))
        self.assertFalse(args["allow_redirects"])
        response.raise_for_status.assert_called_once()
        lab.stream_load.assert_not_called()
        self.assertIn('label, columns)', cells["cell-6"])

    def test_sequence_ddl_is_shown_before_first_update(self):
        from dw_course.schema import order_ddl
        cells = self.notebook_cells("module07-state-changes")
        source = cells["update-walkthrough"]
        self.assertLess(source.index("show_sql("), source.index("lab.execute(ddl)"))
        self.assertLess(source.index("lab.execute(ddl)"), source.index("lab.insert("))
        for fragment in ('UNIQUE KEY(order_id)', '"function_column.sequence_col"="event_version"',
                         '"enable_unique_key_merge_on_write"="true"'):
            self.assertIn(fragment, order_ddl("orders_update_walkthrough", current=True))
            self.assertIn(fragment, cells["update-walkthrough-help"])

    def test_business_ledger_restores_only_missing_products(self):
        cells = self.notebook_cells("module07-state-changes")
        source = cells["business-ledger"].split("for attempt in range(2):", 1)[0]
        for existing in (False, True):
            with self.subTest(existing=existing):
                lab = Mock()
                lab.query.side_effect = [[("wwi_products",)] if existing else [], [(227,)]]
                lab.stream_load.return_value = {
                    "Status": "Success", "NumberLoadedRows": 227, "NumberFilteredRows": 0,
                }
                paths = Mock(return_value={"products": Path("products.parquet")})
                namespace = {
                    "lab": lab, "fixture": runtime.fixture, "expect": runtime.expect,
                    "show_sql": Mock(), "show_response": Mock(),
                    "manifest": wwi.manifest, "parquet_ddl": wwi.parquet_ddl,
                    "parquet_paths": paths, "uuid4": lambda: Mock(hex="test"),
                }
                exec(compile(source, "business-ledger-setup", "exec"), namespace)
                lab.execute.assert_any_call(
                    "INSERT INTO products SELECT StockItemID, StockItemName FROM wwi_products")
                ddl = wwi.parquet_ddl("products", "wwi_products")
                if existing:
                    paths.assert_not_called()
                    lab.stream_load.assert_not_called()
                    self.assertNotIn(ddl, [call.args[0] for call in lab.execute.call_args_list])
                else:
                    paths.assert_called_once_with()
                    lab.execute.assert_any_call(ddl)
                    lab.stream_load.assert_called_once_with(
                        "wwi_products", Path("products.parquet"), "module7_wwi_test", format="parquet")

    def test_business_ledger_stops_on_invalid_product_load(self):
        source = self.notebook_cells("module07-state-changes")["business-ledger"]
        for response in (
            {"Status": "Fail", "NumberLoadedRows": 0, "NumberFilteredRows": 0},
            {"Status": "Success", "NumberLoadedRows": 226, "NumberFilteredRows": 0},
            {"Status": "Success", "NumberLoadedRows": 227, "NumberFilteredRows": 1},
        ):
            with self.subTest(response=response):
                lab = Mock()
                lab.query.return_value = []
                lab.stream_load.return_value = response
                namespace = {
                    "lab": lab, "fixture": runtime.fixture, "expect": runtime.expect,
                    "show_sql": Mock(), "show_response": Mock(),
                    "manifest": wwi.manifest, "parquet_ddl": wwi.parquet_ddl,
                    "parquet_paths": lambda: {"products": Path("products.parquet")},
                    "uuid4": lambda: Mock(hex="test"),
                }
                with self.assertRaises(runtime.CourseCheckError):
                    exec(compile(source, "business-ledger-failed-load", "exec"), namespace)
                self.assertNotIn(
                    "INSERT INTO products SELECT StockItemID, StockItemName FROM wwi_products",
                    [call.args[0] for call in lab.execute.call_args_list])
                lab.insert.assert_not_called()

    def test_quality_negative_cases_target_uniqueness(self):
        source = self.notebook_cells("module06-data-quality")["cell-8"]
        cases = [n for n in ast.parse(source).body if isinstance(n, ast.With)]
        self.assertEqual(len(cases), 2)
        for case in cases:
            self.assertEqual(ast.unparse(case.body[0]), "check_unique_orders()")
            self.assertEqual(len(case.body), 1)

    def test_uniqueness_detects_duplicates_without_total_changes(self):
        from decimal import Decimal
        rows = runtime.fixture("orders.json")
        wrong = [dict(r) for r in rows]
        wrong[1]["order_id"] = wrong[0]["order_id"]
        self.assertEqual(len(wrong), len(rows))
        self.assertEqual(sum(Decimal(r["order_amount"]) for r in wrong),
                         sum(Decimal(r["order_amount"]) for r in rows))
        source = self.notebook_cells("module06-data-quality")["cell-8"]
        check = next(n for n in ast.parse(source).body
                     if isinstance(n, ast.FunctionDef) and n.name == "check_unique_orders")
        lab = Mock()
        namespace = {"lab": lab, "expect": runtime.expect}
        exec(compile(ast.Module(body=[check], type_ignores=[]), "uniqueness", "exec"), namespace)
        for records, duplicates in ((rows, 0), (wrong, 1), (rows + [rows[0]], 1)):
            lab.query.return_value = [(len(records) - len({r["order_id"] for r in records}),)]
            if duplicates:
                with self.assertRaises(runtime.CourseCheckError):
                    namespace["check_unique_orders"]()
            else:
                namespace["check_unique_orders"]()
            lab.query.assert_called_with(
                "SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM orders_clean")

    def test_external_examples_have_explicit_scope_and_observation(self):
        path = next((ROOT / "level1/module05-ingestion").glob("course*.md"))
        content = path.read_text()
        examples = re.findall(r"### Reading example:(.*?)(?=\n## |\Z)", content, re.DOTALL)
        self.assertEqual(len(examples), 4)
        for example in examples:
            self.assertIn("External-environment example; not executed in the lab", example)
            self.assertIn("<!-- external-service-example -->\n```sql", example)
            self.assertIn("SELECT", example)
            self.assertRegex(example, "[Ee]xpect|should (?:become|contain|show)")
        self.assertIn("SHOW ROUTINE LOAD FOR orders_kafka_job", content)
        self.assertIn("Name = 'orders_mysql_job'", content)
        self.assertIn("Name = 'orders_files_job'", content)

    def test_every_module_has_blank_exercise_and_folded_executable_solution(self):
        paths = list((ROOT / "level1").glob("*/lab*.ipynb"))
        self.assertEqual(len(paths), 7)
        for path in paths:
            cells = json.loads(path.read_text())["cells"]
            work = [c for c in cells if "course_exercise" in c.get("metadata", {}).get("tags", [])]
            solutions = [c for c in cells if "course_solution" in c.get("metadata", {}).get("tags", [])]
            self.assertEqual(len(work), 1, path)
            self.assertEqual(ast.parse("".join(work[0]["source"])).body, [], path)
            self.assertEqual(len(solutions), 1, path)
            source = "".join(solutions[0]["source"])
            self.assertIn("<details>", source)
            self.assertNotIn("<details open", source)
            blocks = re.findall(r"```python\n(.*?)```", source, re.DOTALL)
            self.assertEqual(len(blocks), 1, path)
            tree = ast.parse(blocks[0])
            self.assertTrue(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                                and n.func.id == "expect" for n in ast.walk(tree)), path)
            self.assertLess(cells.index(work[0]), cells.index(solutions[0]))

    def test_ingestion_progresses_from_one_file_to_history(self):
        path = next((ROOT / "level1/module05-ingestion").glob("lab*.ipynb"))
        ids = [c["id"] for c in json.loads(path.read_text())["cells"]]
        self.assertLess(ids.index("cell-8"), ids.index("historical-load"))

    def test_lake_preparation_requires_explicit_start(self):
        from dw_course import lakehouse
        with patch.object(lakehouse, "_run") as run:
            with self.assertRaises(ValueError):
                lakehouse.prepare_lakehouse(None)
            run.assert_not_called()

    def test_notebooks_keep_connections_for_independent_work(self):
        for path in (ROOT / "level1").glob("*/lab*.ipynb"):
            for cell in json.loads(path.read_text())["cells"]:
                if cell["cell_type"] != "code":
                    continue
                tree = ast.parse("".join(cell["source"]))
                closes = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                          and isinstance(node.func, ast.Attribute)
                          and isinstance(node.func.value, ast.Name)
                          and node.func.value.id == "lab" and node.func.attr == "close"]
                self.assertEqual(closes, [], path)

    def test_expected_quality_error_has_no_failure_card(self):
        with patch.object(runtime, "in_notebook", return_value=True), patch.object(runtime, "card") as card:
            with runtime.expected_failure("重复订单检查", "已识别重复订单，质量规则生效"):
                runtime.expect([(11,)], [(10,)])
            self.assertEqual([call.args[1] for call in card.call_args_list], ["ok"])
            self.assertIn("已识别重复订单", card.call_args.args[0])

    def test_missing_expected_error_is_a_real_failure(self):
        with patch.object(runtime, "in_notebook", return_value=False):
            with self.assertRaises(AssertionError):
                with runtime.expected_failure("重复检查", "识别成功"):
                    runtime.expect([(10,)], [(10,)])

    def test_unrelated_exception_is_not_treated_as_learning_success(self):
        with patch.object(runtime, "in_notebook", return_value=True), patch.object(runtime, "card") as card:
            with self.assertRaises(RuntimeError):
                with runtime.expected_failure("重复检查", "识别成功"):
                    raise RuntimeError("connection failed")
            card.assert_not_called()

    def test_successful_internal_checks_do_not_flood_notebook(self):
        with patch.object(runtime, "in_notebook", return_value=True), patch.object(runtime, "card") as card:
            runtime.expect([(10,)], [(10,)])
            card.assert_not_called()
            runtime.expect([(10,)], [(10,)], title="订单数符合预期")
            self.assertEqual(card.call_args.args[2], "订单数符合预期")


class LocalBundleTest(unittest.TestCase):
    def test_default_bundle_prepares_and_reuses_verified_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "datasets").symlink_to(ROOT / "datasets", target_is_directory=True)
            with patch.object(wwi, "COURSE_ROOT", root), patch.dict("os.environ", {}, clear=True):
                paths = wwi.parquet_paths()
                self.assertEqual(len(paths), 10)
                modified = {k: p.stat().st_mtime_ns for k, p in paths.items()}
                self.assertEqual(wwi.parquet_paths(), paths)
                self.assertEqual({k: p.stat().st_mtime_ns for k, p in paths.items()}, modified)

    def test_explicit_missing_directory_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(wwi, "_unpack_bundle") as unpack:
                with self.assertRaises(FileNotFoundError):
                    wwi.parquet_paths(Path(directory) / "missing")
                unpack.assert_not_called()

    def test_archive_members_must_be_exact_regular_files(self):
        entries = {"orders": {"bytes": 1, "sha256": "unused"}}
        for name, kind in [("../orders.parquet", tarfile.REGTYPE),
                           ("orders.parquet", tarfile.SYMTYPE)]:
            member = tarfile.TarInfo(name)
            member.type, member.size = kind, 1
            with tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / "wwi"
                with patch.object(wwi, "manifest", return_value={"tables": entries}), patch("tarfile.open") as opened:
                    opened.return_value.__enter__.return_value.getmembers.return_value = [member]
                    with self.assertRaises(ValueError):
                        wwi._unpack_bundle(target)
                    self.assertFalse(target.exists())

    def test_bad_checksum_does_not_publish_partial_bundle(self):
        bad = wwi.manifest()
        next(iter(bad["tables"].values()))["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "wwi"
            with patch.object(wwi, "manifest", return_value=bad):
                with self.assertRaises(ValueError):
                    wwi._unpack_bundle(target)
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
