"""Keep authored course 02 material English without rewriting learner outputs."""

import json
from pathlib import Path
import re
import unittest
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[3] / "doris-course/02-data-warehousing"
SKIP = {".runtime", ".venv", ".ipynb_checkpoints", "__pycache__"}


def authored_files():
    for path in ROOT.rglob("*"):
        if any(part in SKIP or part.startswith(".") for part in path.relative_to(ROOT).parts):
            continue
        if path.suffix not in {".md", ".py", ".yaml", ".yml", ".ipynb"}:
            continue
        if path.suffix == ".ipynb":
            cells = json.loads(path.read_text())["cells"]
            yield path, "\n".join("".join(cell["source"]) for cell in cells)
        else:
            yield path, path.read_text()


def heading_ids(text):
    counts = {}
    for heading in re.findall(r"^#{1,6}\s+(.+)$", text, re.MULTILINE):
        heading = re.sub(r"<[^>]*>", "", heading).lower()
        slug = re.sub(r"[^\w\- ]", "", heading).replace(" ", "-")
        index = counts.get(slug, 0)
        counts[slug] = index + 1
        yield slug if index == 0 else f"{slug}-{index}"


class EnglishMaterialTest(unittest.TestCase):
    def test_authored_text_is_english(self):
        for path, text in authored_files():
            with self.subTest(path=str(path.relative_to(ROOT))):
                self.assertNotRegex(text, r"[\u3400-\u4dbf\u4e00-\u9fff]")

    def test_local_markdown_fragments_match_translated_headings(self):
        for path, text in authored_files():
            if path.suffix not in {".md", ".ipynb"}:
                continue
            for target in re.findall(r"\]\(([^\s)]+)\)", text):
                url = urlsplit(target)
                if url.scheme or url.netloc or not url.fragment:
                    continue
                dest = (path.parent / unquote(url.path)).resolve() if url.path else path
                if dest.suffix != ".md":
                    continue
                with self.subTest(source=str(path), target=target):
                    self.assertTrue(dest.is_file())
                    self.assertIn(unquote(url.fragment), set(heading_ids(dest.read_text())))


if __name__ == "__main__":
    unittest.main()
