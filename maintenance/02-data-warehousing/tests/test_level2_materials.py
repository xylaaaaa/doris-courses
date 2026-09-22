"""Offline checks for the Data Warehousing Level 2 learner materials."""

import ast
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
            self.assertEqual(len(payload["questions"]), 5, quiz)
            self.assertEqual([len(q["options"]) for q in payload["questions"]], [4] * 5)

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

    def test_level2_root_links_exist(self):
        readme = (LEVEL2 / "README.md").read_text()
        for link in ("module08-views-materialized-views", "module09-modeling-and-joins", "module10-metric-processing", "module11-bi-and-ai"):
            self.assertIn(link, readme)


if __name__ == "__main__":
    unittest.main()
