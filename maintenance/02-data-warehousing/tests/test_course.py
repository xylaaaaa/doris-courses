"""Offline course checks. These tests do not connect to Doris."""

import ast
import json
import re
import sys
import unittest
from collections import Counter
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

import nbformat
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
MAINTENANCE_ROOT = REPO_ROOT / "maintenance/02-data-warehousing"
sys.path.insert(0, str(REPO_ROOT / "doris-course/02-data-warehousing"))

from dw_course.runtime import COURSE_ROOT, WarehouseLab, dataset_path, expect, fixture, identifier
from dw_course.schema import ORDER_COLUMNS, order_ddl, order_rows
from dw_course.wwi import HISTORY_COLUMNS, history_ddl, history_rows, manifest, parquet_paths, sample


class FixturesTest(unittest.TestCase):
    def test_initial_contract(self):
        orders = fixture("orders.json")
        expected = fixture("expected_summary.json")
        self.assertEqual(len(orders), expected["initial_rows"])
        self.assertEqual(sum(Decimal(x["order_amount"]) for x in orders), Decimal("1400.00"))
        self.assertEqual(len({x["order_id"] for x in orders}), 10)
        raw = fixture("raw_orders.json")
        self.assertEqual(len(raw), 13)
        self.assertEqual([r["input_id"] for r in raw if r["order_id"] is None], [12])
        self.assertTrue(all(r["data_source"] == "COURSE_SIMULATION" for r in orders))
        self.assertEqual(min(r["order_id"] for r in orders), 900001)

    def test_replay_independent_oracle(self):
        initial = fixture("orders.json")
        deliveries = fixture("deliveries.json")
        current = {x["order_id"]: x for x in initial}
        history = {x["event_id"]: x for x in initial}
        for attempt in range(2):
            for delivered in deliveries:
                record = {key: value for key, value in delivered.items() if key != "delivery_id"}
                if record["event_id"] in history:
                    self.assertEqual(history[record["event_id"]], record)
                history[record["event_id"]] = record
                old = current.get(record["order_id"])
                if old is None or record["event_version"] > old["event_version"]:
                    current[record["order_id"]] = record
            self.assertEqual([current[key] for key in sorted(current)], fixture("expected_current.json"))
            self.assertEqual(len(history), 18)
        summary = fixture("expected_summary.json")
        self.assertEqual(Counter(row["status"] for row in current.values()), summary["statuses"])
        for column, expected in [("order_amount", "1510.00"), ("paid_amount", "250.00"), ("refund_amount", "150.00")]:
            self.assertEqual(sum(Decimal(row[column]) for row in current.values()), Decimal(expected))

    def test_csv_matches_json(self):
        import csv
        from dw_course.schema import ORDER_COLUMNS
        with dataset_path("orders.csv").open() as stream:
            rows = list(csv.reader(stream))
        expected = [[str(record[col]) for col in ORDER_COLUMNS] for record in fixture("orders.json")]
        self.assertEqual(rows, expected)

    def test_wwi_subset_has_real_relationships_and_independent_totals(self):
        data = sample()
        self.assertEqual([r["order_id"] for r in data["orders"]], [1, 2, 3, 4, 5, 80, 81, 82, 83, 84])
        self.assertEqual(sum(Decimal(r["order_amount"]) for r in data["orders"]), Decimal("12220.60"))
        customers = {r["customer_id"] for r in data["customers"]}
        products = {r["product_id"] for r in data["products"]}
        for order in data["orders"]:
            self.assertIn(order["customer_id"], customers)
            lines = [r for r in data["order_lines"] if r["order_id"] == order["order_id"]]
            self.assertEqual(len(lines), order["line_count"])
            self.assertEqual(sum(r["quantity"] * Decimal(r["unit_price"]) for r in lines), Decimal(order["order_amount"]))
            self.assertTrue(all(r["product_id"] in products for r in lines))
            self.assertEqual(order["data_source"], "WWI")
        self.assertEqual(sum(t["rows"] for t in manifest()["tables"].values()), 701846)

    def test_simulation_business_ledgers_reconcile(self):
        business = fixture("business_events.json")
        current = fixture("expected_current.json")
        customers = {r["customer_id"] for r in sample()["customers"]}
        products = {r["product_id"] for r in sample()["products"]}
        events = {r["event_id"]: r for r in fixture("deliveries.json")}
        payments = {r["payment_id"]: r for r in business["payments"]}
        for r in business["order_lines"]:
            self.assertIn(r["product_id"], products)
        for r in business["refunds"]:
            self.assertEqual(r["order_id"], payments[r["payment_id"]]["order_id"])
            self.assertLessEqual(Decimal(r["amount"]), Decimal(payments[r["payment_id"]]["amount"]))
        for order in current:
            self.assertIn(order["customer_id"], customers)
            amount = sum(r["quantity"] * Decimal(r["unit_price"]) for r in business["order_lines"] if r["order_id"] == order["order_id"])
            self.assertEqual(amount, Decimal(order["order_amount"]))
            for collection, column in [("payments", "paid_amount"), ("refunds", "refund_amount")]:
                total = sum(Decimal(r["amount"]) for r in business[collection] if r["order_id"] == order["order_id"])
                self.assertEqual(total, Decimal(order[column]))
        for collection in ("payments", "refunds", "shipments"):
            for record in business[collection]:
                self.assertEqual(record["order_id"], events[record["event_id"]]["order_id"])
                self.assertEqual(record["event_time"], events[record["event_id"]]["event_time"])
        self.assertEqual(len(fixture("deliveries.json")), 9)
        self.assertEqual(len(events), 8)
        self.assertEqual(current[0]["status"], "DELIVERED")
        self.assertEqual(current[2]["status"], "REFUNDED")


class RuntimeTest(unittest.TestCase):
    def test_scoped_database_and_opt_in(self):
        with patch.dict("os.environ", {}, clear=True), patch("pymysql.connect") as connect:
            with self.assertRaises(RuntimeError):
                WarehouseLab()
            connect.assert_not_called()
        with patch.dict("os.environ", {"DW_ALLOW_WRITES": "yes", "DW_DATABASE": "production"}, clear=True), patch("pymysql.connect") as connect:
            with self.assertRaises(ValueError):
                WarehouseLab()
            connect.assert_not_called()

    def test_identifiers_and_fixture_scope(self):
        for value in ["a; DROP TABLE t", "catalog.table", "../orders"]:
            with self.assertRaises(ValueError):
                identifier(value)
        with self.assertRaises(ValueError):
            fixture("../orders.json")

    def test_expect_catches_mismatch(self):
        with self.assertRaises(AssertionError):
            expect([(11, Decimal("1400.00"))], [(10, "1400.00")])

    def test_model_contract(self):
        self.assertIn('UNIQUE KEY(order_id)', order_ddl("orders_current", current=True))
        self.assertIn('"function_column.sequence_col"="event_version"', order_ddl("orders_current", current=True))
        self.assertIn("UNIQUE KEY(event_id)", order_ddl("order_events", history=True))
        with self.assertRaises(ValueError):
            order_ddl("invalid", current=True, history=True)

    def test_stream_load_does_not_follow_redirect(self):
        lab = WarehouseLab.__new__(WarehouseLab)
        lab.database, lab.user, lab.password = "dw_course_l1_test", "student", "not-a-real-password"
        response = Mock(status_code=307)
        with patch("requests.put", return_value=response) as put:
            with self.assertRaises(RuntimeError):
                lab.stream_load("orders", dataset_path("orders.csv"), "test", "order_id")
        self.assertFalse(put.call_args.kwargs["allow_redirects"])

    def test_parquet_stream_load_headers(self):
        lab = WarehouseLab.__new__(WarehouseLab)
        lab.database, lab.user, lab.password = "dw_course_l1_test", "student", "not-a-real-password"
        response = Mock(status_code=200)
        response.json.return_value = {"Status": "Success"}
        with patch("requests.put", return_value=response) as put:
            lab.stream_load("orders", dataset_path("orders.csv"), "test", format="parquet")
        headers = put.call_args.kwargs["headers"]
        self.assertEqual(headers["format"], "parquet")
        self.assertNotIn("column_separator", headers)
        self.assertNotIn("columns", headers)
        self.assertFalse(put.call_args.kwargs["allow_redirects"])

    def test_wwi_bundle_rejects_missing_or_changed_files(self):
        import hashlib
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            payload = b"fixture-only-not-parquet"
            metadata = {"tables": {"orders": {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}}}
            with patch("dw_course.wwi.manifest", return_value=metadata):
                with self.assertRaises(FileNotFoundError):
                    parquet_paths(directory)
                path = Path(directory) / "orders.parquet"
                path.write_bytes(payload)
                self.assertEqual(parquet_paths(directory), {"orders": path})
                path.write_bytes(b"changed")
                with self.assertRaises(ValueError):
                    parquet_paths(directory)


class MaterialsTest(unittest.TestCase):
    def test_learner_materials_use_module_labels(self):
        for path in COURSE_ROOT.rglob("*"):
            if path.suffix not in {".md", ".yaml", ".ipynb"}:
                continue
            if any(part in {".runtime", ".venv", ".ipynb_checkpoints"} for part in path.parts):
                continue
            if path.suffix == ".ipynb":
                notebook = nbformat.read(path, as_version=4)
                # Executed learner outputs are historical records, not authored text.
                content = "\n".join(cell.source for cell in notebook.cells)
            else:
                content = path.read_text()
            self.assertNotRegex(content, r"(?<![A-Za-z0-9_])D0?[1-7](?![A-Za-z0-9_])", path)
        for module in (COURSE_ROOT / "level1").glob("module*"):
            number = int(re.match(r"module(\d+)", module.name)[1])
            reading = next(module.glob("course*.md")).read_text()
            quiz = yaml.safe_load(next(module.glob("quiz*.yaml")).read_text())
            self.assertTrue(reading.startswith(f"# Module {number}:"), module)
            self.assertTrue(quiz["title"].startswith(f"Module {number}:"), module)

    def test_reading_schedule_titles_match_sections(self):
        for path in (COURSE_ROOT / "level1").glob("*/course*.md"):
            content = path.read_text()
            schedule = content.split("## Module Schedule\n\n", 1)[1].split("\n## ", 1)[0]
            listed = re.findall(r"^\| (\d+\.\d+ [^|]+) \|", schedule, re.MULTILINE)
            sections = re.findall(r"^## (\d+\.\d+ .+)$", content, re.MULTILINE)
            self.assertTrue(sections, path)
            self.assertEqual(listed, sections, path)
            module = int(re.match(r"module(\d+)", path.parent.name)[1])
            self.assertEqual([section.split(" ", 1)[0] for section in sections],
                             [f"{module}.{i}" for i in range(1, len(sections) + 1)], path)
            self.assertNotRegex(content, r"D\d+-\d+")

    def test_learner_prose_excludes_author_status_notes(self):
        paths = list((COURSE_ROOT / "level1").glob("*/course*.md"))
        paths += list((COURSE_ROOT / "level1").glob("*/*.ipynb"))
        for path in paths:
            content = path.read_text()
            if path.suffix == ".ipynb":
                notebook = nbformat.read(path, as_version=4)
                content = "\n".join(c.source for c in notebook.cells if c.cell_type == "markdown")
            self.assertNotRegex(content, r"(?i)candidate experiment|candidate lab|not yet tested|initial lab draft|acceptance evidence|do not mark unexecuted steps as complete|maintenance/.*/VALIDATION\.md", path)
        for path in (COURSE_ROOT / "level1").glob("*/quiz*.ipynb"):
            notebook = nbformat.read(path, as_version=4)
            content = "\n".join(c.source for c in notebook.cells if c.cell_type == "markdown")
            self.assertIn("### Load the Quiz", content, path)
            self.assertIn("## Start the Quiz", content, path)

    def test_reading_information_and_schedules_are_consistent(self):
        for path in (COURSE_ROOT / "level1").glob("*/course*.md"):
            content = path.read_text()
            opening = content.split("## Module Goal", 1)[0]
            fields = re.findall(r"^\| ([^|]+) \|", opening, re.MULTILINE)
            self.assertEqual(fields, ["Course Information", "---", "Course", "Product Version", "Lab Version", "Estimated Time"], path)
            schedule = content.split("## Module Schedule\n\n", 1)[1].split("\n## ", 1)[0]
            self.assertIn("| Section | Learning Format | Suggested Time | Learning Outcome |", schedule, path)
            minutes = [int(value) for value in re.findall(r"\| (\d+) minutes \|", schedule)]
            total = int(re.search(r"\| Estimated Time \| About (\d+) minutes", opening)[1])
            self.assertEqual(sum(minutes), total, path)
            self.assertNotIn("Complete the lab below and check the results", schedule, path)

    def test_quiz_objectives_cover_each_reading_goal(self):
        for path in (COURSE_ROOT / "level1").glob("*/course*.md"):
            content = path.read_text()
            goals = content.split("## Learning Objectives\n\n", 1)[1].split("\n## ", 1)[0]
            objectives = re.findall(r"^\d+\. (.+)$", goals, re.MULTILINE)
            quiz = yaml.safe_load(next(path.parent.glob("quiz*.yaml")).read_text())
            self.assertEqual([q["objective"] for q in quiz["questions"]], objectives, path)
            summary = content.split("## Module Summary\n\n", 1)[1].split("\n## ", 1)[0]
            self.assertEqual(len(re.findall(r"^- ", summary, re.MULTILINE)), len(objectives), path)

    def test_readings_keep_examples_separate_from_lab_writes(self):
        for path in (COURSE_ROOT / "level1").glob("*/course*.md"):
            content = path.read_text()
            blocks = re.findall(
                r"(?:(^<!-- (?:external-service-example|reading-only-example) -->\n))?^```sql\n(.*?)^```",
                content, re.MULTILINE | re.DOTALL,
            )
            self.assertTrue(blocks, path)
            for marker, block in blocks:
                if "reading-only-example" in marker:
                    self.assertIn("SQL reading example:", content)
                    allowed_targets = {
                        "module03-table-design": {"orders_partitioned"},
                        "module05-ingestion": {"orders_defaults_reading"},
                        "module06-data-quality": {"orders_classified", "orders_clean", "orders_rejected"},
                        "module07-state-changes": {"orders_partial_update", "orders_delete_demo"},
                    }
                    self.assertIn(path.parent.name, allowed_targets)
                    targets = re.findall(
                        r"(?:CREATE TABLE|CREATE VIEW|INSERT INTO|UPDATE|DELETE FROM)\s+(\w+)", block)
                    self.assertTrue(targets, path)
                    self.assertLessEqual(set(targets), allowed_targets[path.parent.name])
                    self.assertNotRegex(block, r"\b(DROP|TRUNCATE|ALTER|GRANT|REVOKE)\b")
                    for statement in (s.strip() for s in block.split(";") if s.strip()):
                        self.assertRegex(statement, r"^(CREATE TABLE|CREATE VIEW|INSERT INTO|UPDATE|DELETE FROM|SET|SELECT)\b")
                        if statement.startswith("SET"):
                            self.assertEqual(path.parent.name, "module07-state-changes")
                            self.assertEqual(statement, "SET enable_unique_key_partial_update = true")
                    continue
                if "external-service-example" in marker:
                    self.assertIn(path.parent.name, ("module04-external-access", "module05-ingestion"))
                    self.assertIn("<", block)  # Requires external connection parameters.
                    self.assertNotRegex(block, r"\b(orders_imported|wwi_\w+)\b")
                    continue
                statements = [s.strip() for s in block.split(";") if s.strip()]
                for statement in statements:
                    self.assertRegex(statement, r"^(SELECT|EXPLAIN|SHOW)\b", path)
            self.assertNotRegex(content, r"待补录制|待固定环境|录制所需|首版列出待验证|\*\*观察与练习：\*\*")

    def test_reading_result_tables_match_wwi_and_replay_fixtures(self):
        intro = next((COURSE_ROOT / "level1/module01-introduction").glob("course*.md")).read_text()
        dates = sorted({row["order_date"] for row in sample()["orders"]})
        for date in dates:
            rows = [row for row in sample()["orders"] if row["order_date"] == date]
            amount = sum(Decimal(row["order_amount"]) for row in rows)
            self.assertIn(f"| {date} | {len(rows)} | {amount:.2f} |", intro)
        changes = next((COURSE_ROOT / "level1/module07-state-changes").glob("course*.md")).read_text()
        for row in fixture("deliveries.json"):
            if row["order_id"] == 900001:
                prefix = f'| {row["delivery_id"]} | {row["event_id"]} | {row["event_version"]} | {row["status"]}'
                self.assertIn(prefix, changes)
        for row in fixture("expected_current.json"):
            if row["order_id"] in (900001, 900003):
                expected = (f'| {row["order_id"]} | {row["status"]} | {row["event_version"]} '
                            f'| {row["paid_amount"]} | {row["refund_amount"]} |')
                self.assertIn(expected, changes)

    def test_intro_walkthrough_matches_sample_line_items_and_filters(self):
        intro = next((COURSE_ROOT / "level1/module01-introduction").glob("course*.md")).read_text()
        data = sample()
        order = next(row for row in data["orders"] if row["order_id"] == 4)
        self.assertIn(
            f'| 4 | {order["customer_id"]} | {order["order_date"]} | '
            f'{order["order_amount"]} | {order["line_count"]} |', intro,
        )
        lines = [line for line in data["order_lines"] if line["order_id"] == 4]
        self.assertEqual(len(lines), order["line_count"])
        self.assertEqual(sum(line["quantity"] * Decimal(line["unit_price"]) for line in lines),
                         Decimal(order["order_amount"]))
        selected = [row for row in data["orders"] if Decimal(row["order_amount"]) >= 1000]
        for order in selected:
            self.assertIn(
                f'| {order["order_id"]} | {order["order_date"]} | {order["order_amount"]} |', intro,
            )
        selected_amount = sum(Decimal(row["order_amount"]) for row in selected)
        self.assertIn(f"three orders total {selected_amount:.2f}", intro)
        doubled = 2 * sum(Decimal(row["order_amount"]) for row in data["orders"])
        self.assertIn(f"twenty rows and an amount of {doubled:.2f}", intro)

    def test_readings_follow_english_course_structure(self):
        readings = list((COURSE_ROOT / "level1").glob("*/course*.md"))
        self.assertEqual(len(readings), 7)
        for path in readings:
            content = path.read_text()
            headings = re.findall(r"^## (.+)$", content, re.MULTILINE)
            self.assertEqual(headings[:3], ["Module Goal", "Learning Objectives", "Module Schedule"], path)
            self.assertRegex(headings[3], r"^\d+\.1 ")
            self.assertTrue(headings[-4].startswith("Hands-on Lab "), path)
            self.assertEqual(headings[-3], "Module Summary", path)
            self.assertTrue(headings[-2].startswith("Knowledge Quiz "), path)
            self.assertEqual(headings[-1], "Official References", path)
            self.assertIn("| Course Information | Details |", content, path)
            self.assertNotRegex(content, r"\]\(quiz[^)]+\.yaml\)")
            references = content.split("## Official References", 1)[1]
            self.assertGreaterEqual(len(re.findall(r"https://doris\.apache\.org/", references)), 2, path)

    def test_numbered_material_names(self):
        import runpy
        modules = sorted((COURSE_ROOT / "level1").glob("module*"))
        self.assertEqual([module.name for module in modules], [
            "module01-introduction", "module02-architecture", "module03-table-design",
            "module04-external-access", "module05-ingestion", "module06-data-quality",
            "module07-state-changes",
        ])
        runner = runpy.run_path(str(MAINTENANCE_ROOT / "scripts/run_labs.py"))
        self.assertEqual(runner["CORE"], [
            module.name for module in modules if module.name != "module04-external-access"
        ])
        for module in (COURSE_ROOT / "level1").glob("module*"):
            match = re.match(r"module(\d+)([a-z]?)", module.name)
            number = str(int(match[1])) + match[2]
            self.assertEqual(len(list(module.glob(f"course{number}_*.md"))), 1)
            self.assertEqual(len(list(module.glob(f"lab{number}_*.ipynb"))), 1)
            self.assertEqual(len(list(module.glob(f"quiz{number}_*.yaml"))), 1)
            self.assertEqual(len(list(module.glob(f"quiz{number}_*.ipynb"))), 1)
            quiz_path = next(module.glob(f"quiz{number}_*.ipynb"))
            quiz_source = "\n".join(cell.source for cell in nbformat.read(quiz_path, as_version=4).cells)
            yaml_path = next(module.glob(f"quiz{number}_*.yaml"))
            self.assertIn(str(yaml_path.relative_to(COURSE_ROOT)), quiz_source)
            self.assertFalse((module / "course.md").exists())
            self.assertFalse((module / "quiz.ipynb").exists())

    def test_notebooks_are_valid_clean_and_compilable(self):
        paths = list((COURSE_ROOT / "level1").glob("*/*.ipynb"))
        self.assertEqual(len(paths), 19)  # Seven Lab/Quiz pairs, three extensions, two streaming Labs.
        for path in paths:
            notebook = nbformat.read(path, as_version=4)
            nbformat.validate(notebook)
            for cell in notebook.cells:
                if cell.cell_type == "code":
                    self.assertEqual(cell.outputs, [], path)
                    self.assertIsNone(cell.execution_count, path)
                    ast.parse(cell.source, filename=str(path))

    def test_quiz_contract_and_shared_renderer(self):
        from dw_course.quiz import CourseQuiz
        paths = list((COURSE_ROOT / "level1").glob("*/quiz*.yaml"))
        self.assertEqual(len(paths), 7)
        for path in paths:
            data = yaml.safe_load(path.read_text())
            self.assertEqual(len(data["questions"]), 5, path)
            ids = [q["id"] for q in data["questions"]]
            self.assertEqual(len(ids), len(set(ids)), path)
            for question in data["questions"]:
                options = [option["id"] for option in question["options"]]
                self.assertEqual(options, ["a", "b", "c", "d"], (path, question["id"]))
                texts = [option["text"].strip() for option in question["options"]]
                self.assertTrue(all(texts), (path, question["id"]))
                self.assertEqual(len(set(texts)), 4, (path, question["id"]))
                self.assertEqual(len(options), len(set(options)))
                self.assertIn(question["answer"], options)
                self.assertTrue(question["explanation"])
                for option in question["options"]:
                    letter = option["id"].upper()
                    self.assertTrue(option["text"].startswith(f"{letter}. "))
                    self.assertIn(f"{letter}:", question["explanation"])
            self.assertIsInstance(CourseQuiz.from_yaml(path), CourseQuiz)

    def test_quiz_four_choices_and_feedback_render(self):
        from dw_course.quiz import CourseQuiz

        for path in (COURSE_ROOT / "level1").glob("*/quiz*.yaml"):
            quiz = CourseQuiz.from_yaml(path)
            for index, question in enumerate(quiz.questions):
                for option in question.options:
                    with self.subTest(path=path.name, question=question.question_id,
                                      option=option.option_id):
                        quiz._current = index
                        quiz._answers.clear()
                        quiz._render_question()
                        _, choices, feedback, controls = quiz._root.children[0].children
                        self.assertEqual(
                            list(choices.options),
                            [(item.text, item.option_id) for item in question.options],
                        )
                        self.assertEqual(len(choices.options), 4)
                        choices.value = option.option_id
                        controls.children[1].click()
                        self.assertEqual(quiz._answers[question.question_id], option.option_id)
                        self.assertEqual(
                            "Not quite." in feedback.value, option.option_id != question.answer
                        )
                        for letter in "ABCD":
                            self.assertIn(f"{letter}:", feedback.value)

    def test_learner_table_names_and_upstream_references(self):
        for path in COURSE_ROOT.rglob("*"):
            if path.suffix not in {".md", ".yaml", ".ipynb", ".py"}:
                continue
            if any(part in {".runtime", ".venv", ".ipynb_checkpoints"} for part in path.parts):
                continue
            self.assertNotRegex(path.read_text(), r"\bd[0-9]{2}[a-z]?_", path)

        sources = {}
        for path in (COURSE_ROOT / "level1").glob("*/lab*.ipynb"):
            notebook = nbformat.read(path, as_version=4)
            nbformat.validate(notebook)
            code = "\n".join(cell.source for cell in notebook.cells if cell.cell_type == "code")
            ast.parse(code, filename=str(path))
            sources[path.parent.name] = code

        self.assertIn("CREATE TABLE orders_sample", sources["module01-introduction"])
        self.assertIn('target = "wwi_" + name', sources["module05-ingestion"])
        quality = sources["module06-data-quality"]
        replay = sources["module07-state-changes"]
        self.assertIn("INSERT INTO customers SELECT CustomerID, CustomerName FROM wwi_customers", quality)
        self.assertIn("CREATE VIEW orders_classified", quality)
        self.assertIn('order_ddl("orders_clean")', quality)
        self.assertIn("FROM orders_clean", replay)
        self.assertIn("INSERT INTO products SELECT StockItemID, StockItemName FROM wwi_products", replay)
        self.assertIn('("order_items", business["order_lines"])', replay)
        self.assertIn('("shipment_events", business["shipments"])', replay)
        self.assertIn("lab.insert(table, columns,", replay)
        for upstream in ("orders_clean", "customers", "wwi_customers", "wwi_products"):
            self.assertNotIn(f"DROP TABLE IF EXISTS {upstream}", replay)

    def test_local_markdown_links(self):
        paths = [
            *COURSE_ROOT.rglob("*.md"),
            *MAINTENANCE_ROOT.rglob("*.md"),
            REPO_ROOT / "README.md",
        ]
        for path in paths:
            if any(part in {".venv", ".runtime", ".ipynb_checkpoints"} for part in path.parts):
                continue
            for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
                if target.startswith(("https://", "http://", "#")):
                    continue
                self.assertTrue((path.parent / target.split("#")[0]).exists(), f"{path}: {target}")


    def test_notebook_markdown_links_and_covers(self):
        for path in (COURSE_ROOT / "level1").glob("*/*.ipynb"):
            notebook = nbformat.read(path, as_version=4)
            self.assertIn("DATA WAREHOUSING WITH APACHE DORIS", notebook.cells[0].source)
            self.assertIn("border-top:4px solid #0f766e", notebook.cells[0].source)
            self.assertNotIn("10 million", notebook.cells[0].source, path)
            for cell in notebook.cells:
                if cell.cell_type != "markdown":
                    continue
                for target in re.findall(r"\]\(([^)]+)\)", cell.source):
                    if target.startswith(("https://", "http://", "#")):
                        continue
                    self.assertTrue((path.parent / target.split("#")[0]).exists(), f"{path}: {target}")


class AlignmentTest(unittest.TestCase):
    def test_learner_root_excludes_maintenance_materials(self):
        for name in ("PR_DRAFT.md", "VALIDATION.md", "integration-backlog.md", "scripts", "tests"):
            self.assertFalse((COURSE_ROOT / name).exists(), name)
            self.assertTrue((MAINTENANCE_ROOT / name).exists(), name)

    def test_jupyter_config_hides_generated_files_without_hiding_course(self):
        from traitlets.config import Config
        config = Config()
        path = REPO_ROOT / "maintenance/jupyter_lab_config.py"
        namespace = {"__file__": str(path), "get_config": lambda: config}
        exec(compile(path.read_text(), str(path), "exec"), namespace)
        self.assertEqual(config.ServerApp.root_dir, str(REPO_ROOT))
        self.assertIn("*.egg-info", config.ContentsManager.hide_globs)
        self.assertNotIn("dw_course", config.ContentsManager.hide_globs)
        self.assertNotIn("maintenance", config.ContentsManager.hide_globs)

    def test_d01_teaches_explicit_sql_matching_order_contract(self):
        path = COURSE_ROOT / "level1/module01-introduction/lab1_connect_and_query.ipynb"
        notebook = nbformat.read(path, as_version=4)
        statements = []
        for cell in notebook.cells:
            if cell.cell_type != "code":
                continue
            for node in ast.walk(ast.parse(cell.source)):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "execute"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                ):
                    statements.append(node.args[0].value)
        create, = [sql for sql in statements if sql.lstrip().startswith("CREATE TABLE")]
        self.assertEqual(
            re.sub(r"\s+", "", create),
            re.sub(r"\s+", "", history_ddl("orders_sample")),
        )
        insert, = [sql for sql in statements if sql.lstrip().startswith("INSERT INTO")]
        header, values = insert.split("VALUES", 1)
        columns = header[header.index("(") + 1:header.index(")")].split(",")
        self.assertEqual(tuple(column.strip() for column in columns), HISTORY_COLUMNS)
        rows = ast.literal_eval("[" + values.strip() + "]")
        actual = []
        for row in rows:
            record = dict(zip(HISTORY_COLUMNS, row))
            for column in ("order_amount",):
                record[column] = format(Decimal(str(record[column])), ".2f")
            actual.append(record)
        self.assertEqual([tuple(r[col] for col in HISTORY_COLUMNS) for r in actual], history_rows())

    def test_d01_initialization_is_separate_from_connection(self):
        path = COURSE_ROOT / "level1/module01-introduction/lab1_connect_and_query.ipynb"
        notebook = nbformat.read(path, as_version=4)
        initialize, = [cell for cell in notebook.cells if cell.id == "initialize"]
        calls = [
            node.func.id
            for node in ast.walk(ast.parse(initialize.source))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        self.assertNotIn("WarehouseLab", calls)
        self.assertNotIn("prepare_environment", calls)
        self.assertIn("install_styles", calls)
        source = "\n".join(cell.source for cell in notebook.cells)
        self.assertNotIn("10 million", source)
        self.assertNotIn("order_ddl(", source)
        self.assertIn("Your turn", source)
        self.assertIn("3944.20", source)
        self.assertIn("8276.40", source)

    def test_display_components_are_reused(self):
        from dw_course import ui
        from dw_course._shared import load_component
        shared = load_component("doris_client")
        self.assertIs(ui.show_frame, shared.show_frame)
        self.assertIs(ui.card, shared.card)
        self.assertIs(ui.install_styles, shared.install_styles)
        self.assertIs(ui.workflow_html, shared.DorisLab._workflow_html)

    def test_sql_keeps_column_names(self):
        lab = WarehouseLab.__new__(WarehouseLab)
        cursor = Mock()
        cursor.description = [("order_id",), ("amount",)]
        cursor.fetchall.return_value = [(1001, Decimal("100.00"))]
        manager = Mock()
        manager.__enter__ = Mock(return_value=cursor)
        manager.__exit__ = Mock(return_value=False)
        lab.connection = Mock()
        lab.connection.cursor.return_value = manager
        with patch("dw_course.runtime.in_notebook", return_value=True), patch("dw_course.runtime.show_sql"), patch("dw_course.runtime.show_frame") as show:
            frame = lab.sql("SELECT order_id, amount FROM example")
        self.assertEqual(list(frame.columns), ["order_id", "amount"])
        self.assertEqual(frame.iloc[0]["amount"], Decimal("100.00"))
        show.assert_called_once()

    def test_compose_scope_and_persistence(self):
        from dw_course.docker_runtime import COMPOSE_FILE, CONNECTION, PROJECT
        config = yaml.safe_load(COMPOSE_FILE.read_text())
        self.assertEqual(config["name"], PROJECT)
        self.assertEqual(set(config["services"]), {"doris"})
        service = config["services"]["doris"]
        self.assertEqual(service["image"], "apache/doris:all-in-one-4.1.3")
        self.assertEqual(service["ports"], ["127.0.0.1:52030:9030", "127.0.0.1:51030:8030", "127.0.0.1:51040:8040"])
        self.assertEqual(CONNECTION["DW_PORT"], "52030")
        self.assertEqual(set(config["volumes"]), {"fe-meta", "be-storage"})

    def test_docker_start_requires_explicit_opt_in(self):
        from dw_course.docker_runtime import prepare_environment
        with patch.dict("os.environ", {}, clear=True), patch("subprocess.run") as run:
            with self.assertRaises(RuntimeError):
                prepare_environment()
            run.assert_not_called()

    def test_docker_start_checks_health_before_connection(self):
        from dw_course.docker_runtime import prepare_environment, CONNECTION, compose_command
        cursor = Mock()
        cursor.fetchone.side_effect = [(1,), (45,)]
        manager = Mock()
        manager.__enter__ = Mock(return_value=cursor)
        manager.__exit__ = Mock(return_value=False)
        connection = Mock()
        connection.cursor.return_value = manager
        with patch.dict("os.environ", {"DW_START_SANDBOX": "yes"}, clear=True), patch("subprocess.run", return_value=Mock(stdout="")) as run, patch("pymysql.connect", return_value=connection):
            self.assertEqual(prepare_environment(), CONNECTION)
            self.assertEqual(run.call_args_list[2].args[0], compose_command("config", "--quiet"))
            self.assertEqual(run.call_args_list[3].args[0], compose_command("pull", "--policy", "missing"))
            self.assertEqual(run.call_args_list[4].args[0], compose_command("up", "-d", "--wait", "--wait-timeout", "300"))
            self.assertEqual(run.call_args_list[5].args[0], compose_command("ps"))
            self.assertEqual(cursor.execute.call_args_list[-1].args[0],
                             'SELECT SUM(number) FROM numbers("number"="10")')
            connection.close.assert_called_once()

    def test_notebooks_use_one_sandbox_without_environment_selection(self):
        for path in (COURSE_ROOT / "level1").glob("*/lab*.ipynb"):
            notebook = nbformat.read(path, as_version=4)
            code = "\n".join(c.source for c in notebook.cells if c.cell_type == "code")
            self.assertIn("lab = connect_sandbox()", code, path)
            self.assertNotIn("USE_DOCKER", code, path)
            self.assertNotIn("FE_HOST =", code, path)
            self.assertNotIn("ALLOW_LAB_WRITES =", code, path)
            if path.parent.name == "module01-introduction":
                self.assertIn("prepare_environment(start=True)", code)
            else:
                self.assertNotIn("prepare_environment(", code, path)

    def test_fresh_notebook_connection_uses_sandbox_not_stale_environment(self):
        from dw_course.docker_runtime import CONNECTION, connect_sandbox
        import os
        for environment in ({}, {"DW_HOST": "another-server", "DW_PORT": "19030",
                                  "DW_BE_HTTP_URL": "http://another-server:8040",
                                  "DW_USER": "another-user", "DW_PASSWORD": "not-a-real-password"}):
            with patch.dict(os.environ, environment, clear=True), patch(
                "dw_course.docker_runtime.WarehouseLab"
            ) as constructor, patch("subprocess.run") as run:
                self.assertIs(connect_sandbox(), constructor.return_value)
                constructor.assert_called_once_with(allow_writes=True)
                self.assertEqual({key: os.environ[key] for key in CONNECTION}, CONNECTION)
                run.assert_not_called()

    def test_explicit_sandbox_start_and_be_readiness(self):
        from dw_course.docker_runtime import prepare_environment
        cursor = Mock()
        cursor.fetchone.side_effect = [(1,), (45,)]
        connection = Mock()
        connection.cursor.return_value.__enter__ = Mock(return_value=cursor)
        connection.cursor.return_value.__exit__ = Mock(return_value=False)
        with patch.dict("os.environ", {}, clear=True), patch("subprocess.run", return_value=Mock(stdout="")), patch(
            "pymysql.connect", return_value=connection
        ):
            prepare_environment(start=True)
        connection.close.assert_called_once()

    def test_sandbox_health_failure_does_not_connect(self):
        from dw_course.docker_runtime import prepare_environment
        import subprocess
        with patch("subprocess.run", side_effect=[
            *[Mock(stdout="") for _ in range(4)], subprocess.CalledProcessError(1, "up")
        ]), patch(
            "pymysql.connect"
        ) as connect:
            with self.assertRaises(subprocess.CalledProcessError):
                prepare_environment(start=True)
            connect.assert_not_called()

    def test_sandbox_be_failure_does_not_publish_connection(self):
        from dw_course.docker_runtime import prepare_environment
        import os
        cursor = Mock()
        cursor.fetchone.side_effect = [(1,), (None,)]
        connection = Mock()
        connection.cursor.return_value.__enter__ = Mock(return_value=cursor)
        connection.cursor.return_value.__exit__ = Mock(return_value=False)
        with patch.dict(os.environ, {"DW_PORT": "19030"}, clear=True), patch(
            "subprocess.run", return_value=Mock(stdout="")
        ), patch("pymysql.connect", return_value=connection):
            with self.assertRaisesRegex(RuntimeError, "BE execution"):
                prepare_environment(start=True)
            self.assertEqual(os.environ["DW_PORT"], "19030")
        connection.close.assert_called_once()

    def test_startup_workflow_success_uses_shared_panel(self):
        from dw_course.ui import WorkflowProgress
        from dw_course.docker_runtime import STARTUP_STEPS
        with patch("dw_course.ui.in_notebook", return_value=True), patch(
            "dw_course.ui.display"
        ) as display, patch("dw_course.ui.show_log") as log:
            progress = WorkflowProgress("Prepare the Doris lab environment", STARTUP_STEPS)
            for step in STARTUP_STEPS:
                progress.advance(step)
            progress.finish()
            display.assert_called_once()
            panel = display.return_value.update.call_args.args[0].data
            self.assertEqual(panel.count('doris-workflow-item success'), 6)
            self.assertIn("<span>Completed</span>", panel)
            self.assertIn("width:100%", panel)
            self.assertNotIn("failure", panel)
            log.assert_called_once()
            self.assertEqual(log.call_args.args[0], "View complete startup logs")

    def test_successful_subprocess_stderr_is_kept_in_folded_log(self):
        from dw_course.docker_runtime import _run, STARTUP_STEPS
        from dw_course.ui import WorkflowProgress
        with patch("dw_course.ui.in_notebook", return_value=True), patch(
            "dw_course.ui.display"
        ), patch("dw_course.ui.show_log") as log:
            progress = WorkflowProgress("Prepare the Doris lab environment", STARTUP_STEPS)
            _run([
                sys.executable, "-c",
                "import sys; print('Container Healthy', file=sys.stderr)",
            ], progress)
            self.assertEqual(progress.logs[-1], "Container Healthy\n")
            progress.finish()
            self.assertIn("Container Healthy", log.call_args.args[1])
            self.assertFalse(log.call_args.kwargs.get("opened", False))

    def test_startup_workflow_failure_keeps_remaining_steps_pending(self):
        import subprocess
        from dw_course.docker_runtime import prepare_environment
        error = subprocess.CalledProcessError(
            1, "up", output="bind: address already in use <script>"
        )
        with patch("dw_course.ui.in_notebook", return_value=True), patch(
            "dw_course.ui.display"
        ) as display, patch("dw_course.ui.show_log") as log, patch(
            "subprocess.run", side_effect=[*[Mock(stdout="") for _ in range(4)], error]
        ), patch("pymysql.connect") as connect:
            with self.assertRaises(subprocess.CalledProcessError):
                prepare_environment(start=True)
            panel = display.return_value.update.call_args.args[0].data
            self.assertEqual(panel.count("doris-workflow-item success"), 3)
            self.assertEqual(panel.count("doris-workflow-item failure"), 1)
            self.assertEqual(panel.count("doris-workflow-item pending"), 2)
            self.assertIn("<span>Failed</span>", panel)
            self.assertIn("width:50%", panel)
            self.assertIn("address already in use", panel)
            self.assertNotIn("<script>", panel)
            self.assertIn("&lt;script&gt;", panel)
            self.assertIn("address already in use", log.call_args.args[1])
            self.assertTrue(log.call_args.kwargs["opened"])
            connect.assert_not_called()

    def test_startup_workflow_timeout_marks_current_step_failed(self):
        import subprocess
        from dw_course.docker_runtime import prepare_environment
        error = subprocess.TimeoutExpired("pull", 1800, output=b"download stalled")
        with patch("dw_course.ui.in_notebook", return_value=True), patch(
            "dw_course.ui.display"
        ) as display, patch("dw_course.ui.show_log"), patch(
            "subprocess.run", side_effect=[*[Mock(stdout="") for _ in range(3)], error]
        ), patch("pymysql.connect") as connect:
            with self.assertRaises(subprocess.TimeoutExpired):
                prepare_environment(start=True)
            panel = display.return_value.update.call_args.args[0].data
            self.assertEqual(panel.count("doris-workflow-item success"), 2)
            self.assertEqual(panel.count("doris-workflow-item failure"), 1)
            self.assertEqual(panel.count("doris-workflow-item pending"), 3)
            self.assertIn("download stalled", panel)
            connect.assert_not_called()

    def test_explicit_write_confirmation_still_requires_scoped_database(self):
        with patch.dict("os.environ", {"DW_DATABASE": "production"}, clear=True), patch(
            "pymysql.connect"
        ) as connect:
            with self.assertRaises(ValueError):
                WarehouseLab(allow_writes=True)
            connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
