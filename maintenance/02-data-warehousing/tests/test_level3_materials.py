"""Offline checks for the Data Warehousing Level 3 learner materials."""

import ast
import unittest
from pathlib import Path

import nbformat
import yaml

ROOT = Path(__file__).resolve().parents[3] / "doris-course/02-data-warehousing"
LEVEL3 = ROOT / "level3"


class Level3MaterialsTest(unittest.TestCase):
    modules = {
        "module12-publishing-permissions-audit": "publishing_permissions_audit",
        "module13-storage-lifecycle": "storage_and_lifecycle",
    }

    def test_each_module_has_guide_lab_and_quiz(self):
        for module, slug in self.modules.items():
            path = LEVEL3 / module
            self.assertTrue((path / "course.md").is_file(), module)
            number = int(module[6:8])
            self.assertTrue((path / f"lab{number}_{slug}.ipynb").is_file(), module)
            quiz = next(path.glob("quiz*.yaml"))
            self.assertTrue((path / quiz.name.replace(".yaml", ".ipynb")).is_file(), module)
            payload = yaml.safe_load(quiz.read_text())
            self.assertEqual(len(payload["questions"]), 5, quiz)
            self.assertEqual([len(q["options"]) for q in payload["questions"]], [4] * 5)

    def test_new_notebooks_are_source_only_and_valid(self):
        notebooks = sorted(LEVEL3.glob("module*/*.ipynb"))
        self.assertEqual(len(notebooks), 4)
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

    def test_operational_labs_keep_scope_explicit(self):
        for path in sorted(LEVEL3.glob("module*/*.ipynb")):
            notebook = nbformat.read(path, as_version=4)
            source = "\n".join(cell.source for cell in notebook.cells if cell.cell_type == "code")
            self.assertIn("l3", source, path)
            self.assertNotIn("DROP TABLE orders_imported", source, path)
            self.assertNotIn("TRUNCATE TABLE orders_imported", source, path)

    def test_level3_root_links_exist(self):
        readme = (LEVEL3 / "README.md").read_text()
        for link in ("module12-publishing-permissions-audit", "module13-storage-lifecycle"):
            self.assertIn(link, readme)


if __name__ == "__main__":
    unittest.main()
