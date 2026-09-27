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
            number = module[6:8]
            self.assertTrue((path / "course.md").is_file(), module)
            self.assertTrue((path / f"lab{int(number)}_{slug}.ipynb").is_file(), module)
            quiz = next(path.glob("quiz*.yaml"))
            self.assertTrue((path / quiz.name.replace(".yaml", ".ipynb")).is_file(), module)
            payload = yaml.safe_load(quiz.read_text())
            self.assertEqual(len(payload["questions"]), 5, quiz)
            self.assertEqual([len(q["options"]) for q in payload["questions"]], [4] * 5)

    def test_guides_follow_the_level1_learning_structure(self):
        required_sections = (
            "课程信息",
            "单元目标",
            "学习目标",
            "单元安排",
            "动手实验",
            "单元总结",
            "知识测验",
            "官方参考资料",
        )
        for module in self.modules:
            guide = (LEVEL3 / module / "course.md").read_text()
            for section in required_sections:
                self.assertIn(section, guide, module)
            self.assertGreaterEqual(len(guide), 4000, module)

    def test_labs_explain_verify_and_clean_up_the_work(self):
        required_markdown = ("你将完成什么", "前置条件", "独立练习", "参考解释", "实验回顾")
        for path in sorted(LEVEL3.glob("module*/lab*.ipynb")):
            notebook = nbformat.read(path, as_version=4)
            nbformat.validate(notebook)
            markdown = "\n".join(cell.source for cell in notebook.cells if cell.cell_type == "markdown")
            source = "\n".join(cell.source for cell in notebook.cells if cell.cell_type == "code")
            for cell in notebook.cells:
                if cell.cell_type == "code":
                    ast.parse(cell.source, filename=str(path))
                    self.assertFalse(cell.get("outputs"), path)
                    self.assertIsNone(cell.get("execution_count"), path)
            for section in required_markdown:
                self.assertIn(section, markdown, path)
            self.assertGreaterEqual(markdown.count("## "), 5, path)
            self.assertIn("expect(", source, path)
            self.assertIn("TODO:", source, path)

    def test_labs_use_the_scoped_sandbox_connection(self):
        for path in sorted(LEVEL3.glob("module*/lab*.ipynb")):
            notebook = nbformat.read(path, as_version=4)
            source = "\n".join(cell.source for cell in notebook.cells if cell.cell_type == "code")
            self.assertIn("from dw_course.docker_runtime import connect_sandbox", source, path)
            self.assertIn("lab = connect_sandbox()", source, path)


if __name__ == "__main__":
    unittest.main()
