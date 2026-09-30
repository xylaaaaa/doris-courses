"""Offline checks for the Data Warehousing Level 2 learner materials."""

import ast
import re
import unittest
from pathlib import Path

import nbformat
import yaml

ROOT = Path(__file__).resolve().parents[3] / "doris-course/02-data-warehousing"
LEVEL2 = ROOT / "level2"


class Level2MaterialsTest(unittest.TestCase):
    modules = {
        "module08-views-materialized-views": "views_and_materialized_views",
        "module09-modeling-and-joins": "modeling_and_joins",
        "module10-metric-processing": "metric_processing",
        "module11-bi-and-ai": "bi_and_ai",
    }

    def test_each_module_has_guide_lab_and_quiz(self):
        for module, slug in self.modules.items():
            path = LEVEL2 / module
            self.assertTrue((path / "course.md").is_file(), module)
            number = module[6:8]
            self.assertTrue((path / f"lab{int(number)}_{slug if number != '11' else 'bi_and_ai_delivery'}.ipynb").is_file(), module)
            quiz = next(path.glob("quiz*.yaml"))
            self.assertTrue((path / quiz.name.replace(".yaml", ".ipynb")).is_file(), module)
            payload = yaml.safe_load(quiz.read_text())
            self.assertEqual(len(payload["questions"]), 6, quiz)
            self.assertEqual([len(q["options"]) for q in payload["questions"]], [4] * 6)
            self.assertEqual(len({q["objective"] for q in payload["questions"]}), 6, quiz)
            guide = (path / "course.md").read_text()
            goals = guide.split("## Learning Objectives\n", 1)[1].split("\n## ", 1)[0]
            self.assertEqual(len(re.findall(r"^\d+\. ", goals, re.MULTILINE)), 6, path)
            for question in payload["questions"]:
                with self.subTest(quiz=quiz.name, question=question["id"]):
                    self.assertEqual([option["id"] for option in question["options"]], ["a", "b", "c", "d"])
                    self.assertEqual(len({option["text"] for option in question["options"]}), 4)
                    self.assertIn(question["answer"], {option["id"] for option in question["options"]})
                    for option in question["options"]:
                        self.assertIn(f"{option['id'].upper()}: ", question["explanation"])
                    self.assertIn(f"{question['answer'].upper()}: Correct.", question["explanation"])

    def test_new_notebooks_are_source_only_and_valid(self):
        notebooks = sorted(LEVEL2.glob("module*/*.ipynb"))
        self.assertEqual(len(notebooks), 8)
        for path in notebooks:
            notebook = nbformat.read(path, as_version=4)
            nbformat.validate(notebook)
            ids = [cell["id"] for cell in notebook.cells]
            self.assertEqual(len(ids), len(set(ids)), path)
            for cell in notebook.cells:
                if cell.cell_type == "code":
                    ast.parse(cell.source, filename=str(path))
                    self.assertFalse(cell.get("outputs"), path)
                    self.assertIsNone(cell.get("execution_count"), path)

    def test_level2_labs_do_not_mutate_level1_tables(self):
        for path in sorted(LEVEL2.glob("module*/*.ipynb")):
            notebook = nbformat.read(path, as_version=4)
            source = "\n".join(cell.source for cell in notebook.cells if cell.cell_type == "code")
            for forbidden in ("DROP TABLE orders_imported", "TRUNCATE TABLE orders_imported", "DROP TABLE customers"):
                self.assertNotIn(forbidden, source, path)

    def test_level2_labs_use_the_scoped_sandbox_connection(self):
        for path in sorted(LEVEL2.glob("module*/lab*.ipynb")):
            notebook = nbformat.read(path, as_version=4)
            source = "\n".join(cell.source for cell in notebook.cells if cell.cell_type == "code")
            self.assertIn("from dw_course.docker_runtime import connect_sandbox", source, path)
            self.assertIn("lab = connect_sandbox()", source, path)
            self.assertNotIn("lab = WarehouseLab()", source, path)

    def test_level2_query_cells_suppress_duplicate_pandas_output(self):
        for path in sorted(LEVEL2.glob("module*/lab*.ipynb")):
            notebook = nbformat.read(path, as_version=4)
            for cell in notebook.cells:
                if cell.cell_type == "code" and "lab.sql(" in cell.source:
                    tree = ast.parse(cell.source, filename=str(path))
                    calls = [
                        node for node in ast.walk(tree)
                        if isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "lab"
                        and node.func.attr == "sql"
                    ]
                    last_call = max(calls, key=lambda node: (node.end_lineno, node.end_col_offset))
                    line = cell.source.splitlines()[last_call.end_lineno - 1]
                    self.assertTrue(line[last_call.end_col_offset:].strip().startswith(";"), path)

    def test_level2_root_links_exist(self):
        readme = (LEVEL2 / "README.md").read_text()
        for link in ("module08-views-materialized-views", "module09-modeling-and-joins", "module10-metric-processing", "module11-bi-and-ai"):
            self.assertIn(link, readme)

    def test_level2_guides_follow_the_level1_learning_structure(self):
        required_sections = (
            "Course Information",
            "Module Goal",
            "Learning Objectives",
            "Module Schedule",
            "Hands-on Lab",
            "Module Summary",
            "Knowledge Quiz",
            "Official References",
        )
        for module in self.modules:
            guide = (LEVEL2 / module / "course.md").read_text()
            for section in required_sections:
                self.assertIn(section, guide, module)
            self.assertGreaterEqual(len(guide), 4000, module)

    def test_level2_labs_explain_and_verify_the_work(self):
        required_markdown = ("What You Will Do", "Prerequisites", "Independent Exercise", "Reference Explanation", "Lab Review")
        for path in sorted(LEVEL2.glob("module*/lab*.ipynb")):
            notebook = nbformat.read(path, as_version=4)
            markdown = "\n".join(cell.source for cell in notebook.cells if cell.cell_type == "markdown")
            source = "\n".join(cell.source for cell in notebook.cells if cell.cell_type == "code")
            for section in required_markdown:
                self.assertIn(section, markdown, path)
            self.assertGreaterEqual(markdown.count("## "), 5, path)
            self.assertIn("expect(", source, path)
            self.assertIn("TODO:", source, path)

    def test_level2_exercise_precedes_answer_and_reference(self):
        for path in sorted(LEVEL2.glob("module*/lab*.ipynb")):
            notebook = nbformat.read(path, as_version=4)
            sources = [cell.source for cell in notebook.cells]
            prompt = next(i for i, source in enumerate(sources) if source.startswith("## Independent Exercise"))
            answer = next(i for i, source in enumerate(sources) if "# TODO:" in source)
            reference = next(i for i, source in enumerate(sources) if source.startswith("<details>\n<summary>Reference Explanation"))
            self.assertLess(prompt, answer, path)
            self.assertLess(answer, reference, path)


if __name__ == "__main__":
    unittest.main()
