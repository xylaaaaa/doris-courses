"""Offline checks for the Data Warehousing Level 3 learner materials."""

import ast
import io
import re
import tokenize
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit

import nbformat
import yaml

ROOT = Path(__file__).resolve().parents[3] / "doris-course/02-data-warehousing"
LEVEL3 = ROOT / "level3"


def ends_with_bare_lab_call(source):
    """Return True when a cell's last statement is a bare lab.<method>(...) call."""
    statements = ast.parse(source).body
    if not statements or not isinstance(statements[-1], ast.Expr):
        return False
    call = statements[-1].value
    return (
        isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "lab"
    )


def hides_trailing_result(source):
    """Like IPython, skip trailing comments and blank lines, then look for a final ";"."""
    skipped = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.ENDMARKER}
    tokens = [t for t in tokenize.generate_tokens(io.StringIO(source).readline) if t.type not in skipped]
    return tokens[-1].type == tokenize.OP and tokens[-1].string == ";"


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

    def test_quizzes_explain_every_option_and_track_reading_goals(self):
        for module in self.modules:
            guide = (LEVEL3 / module / "course.md").read_text()
            goals = guide.split("### 学习目标\n", 1)[1].split("\n## ", 1)[0]
            objectives = {
                re.sub(r"[；。]$", "", goal.replace("`", ""))
                for goal in re.findall(r"^\d+\. (.+)$", goals, re.MULTILINE)
            }
            quiz = next((LEVEL3 / module).glob("quiz*.yaml"))
            questions = yaml.safe_load(quiz.read_text())["questions"]
            self.assertEqual(len({q["objective"] for q in questions}), len(questions), quiz)
            for question in questions:
                with self.subTest(quiz=quiz.name, question=question["id"]):
                    self.assertIn(question["objective"], objectives)
                    letters = [option["id"] for option in question["options"]]
                    self.assertEqual(letters, ["a", "b", "c", "d"])
                    self.assertEqual(len({option["text"] for option in question["options"]}), 4)
                    self.assertIn(question["answer"], letters)
                    for option in question["options"]:
                        self.assertTrue(option["text"].startswith(f"{option['id'].upper()}. "))
                        self.assertIn(f"{option['id'].upper()}: ", question["explanation"])
                    self.assertIn(f"{question['answer'].upper()}: 正确。", question["explanation"])

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

    def test_exercise_precedes_answer_and_reference(self):
        for path in sorted(LEVEL3.glob("module*/lab*.ipynb")):
            notebook = nbformat.read(path, as_version=4)
            sources = [cell.source for cell in notebook.cells]
            prompt = next(i for i, source in enumerate(sources) if source.startswith("## 独立练习"))
            answer = next(i for i, source in enumerate(sources) if "# TODO:" in source)
            reference = next(i for i, source in enumerate(sources) if source.startswith("<details>\n<summary>参考解释"))
            self.assertLess(prompt, answer, path)
            self.assertLess(answer, reference, path)

    def test_labs_use_the_scoped_sandbox_connection(self):
        for path in sorted(LEVEL3.glob("module*/lab*.ipynb")):
            notebook = nbformat.read(path, as_version=4)
            source = "\n".join(cell.source for cell in notebook.cells if cell.cell_type == "code")
            self.assertIn("from dw_course.docker_runtime import connect_sandbox", source, path)
            self.assertIn("lab = connect_sandbox()", source, path)

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

    def test_level3_local_links_resolve(self):
        for path in sorted(LEVEL3.rglob("*")):
            if path.suffix not in {".md", ".ipynb"} or ".ipynb_checkpoints" in path.parts:
                continue
            for target in re.findall(r"\]\(([^\s)]+)\)", path.read_text()):
                url = urlsplit(target)
                if url.scheme or url.netloc or not url.path:
                    continue
                with self.subTest(source=str(path.relative_to(LEVEL3)), target=target):
                    self.assertTrue((path.parent / unquote(url.path)).exists())

    def test_trailing_lab_calls_end_with_semicolon(self):
        # Jupyter echoes a cell's last value: lab.sql() would show its table twice,
        # lab.execute() would print a stray row count.
        for path in sorted(LEVEL3.glob("module*/lab*.ipynb")):
            notebook = nbformat.read(path, as_version=4)
            for cell in notebook.cells:
                if cell.cell_type != "code" or not ends_with_bare_lab_call(cell.source):
                    continue
                with self.subTest(notebook=path.name, cell=cell.get("id")):
                    self.assertTrue(hides_trailing_result(cell.source))


if __name__ == "__main__":
    unittest.main()
