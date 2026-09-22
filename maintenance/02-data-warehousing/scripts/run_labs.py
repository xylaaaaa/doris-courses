"""Execute the committed notebook code cells; never rewrite notebook outputs."""

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "doris-course/02-data-warehousing"
sys.path.insert(0, str(ROOT))
CORE = [
    "module01-introduction",
    "module02-architecture",
    "module03-table-design",
    "module05-ingestion",
    "module06-data-quality",
    "module07-state-changes",
]


EXTENSIONS = [
    "extension23_physical_design.ipynb",
    "extension45_files_and_group_commit.ipynb",
    "extension67_schema_and_delete.ipynb",
]


def execute_notebook(path, *, solutions=False):
    notebook = json.loads(path.read_text())
    namespace = {"__name__": "__main__"}
    previous_directory = Path.cwd()
    print(f"RUN {path.name}", flush=True)
    try:
        os.chdir(path.parent)
        for index, cell in enumerate(notebook["cells"]):
            if solutions and "course_solution" in cell.get("metadata", {}).get("tags", []):
                source = "".join(cell["source"])
                solution_blocks = re.findall(r"```python\n(.*?)```", source, re.DOTALL)
                if len(solution_blocks) != 1:
                    raise ValueError("Expected one reference solution: " + cell["id"])
                exec(compile(solution_blocks[0], f"{path.name}:solution-{index}", "exec"), namespace)
                print("PASS reference solution: " + path.name, flush=True)
            if cell["cell_type"] == "code":
                source = cell["source"]
                source = "".join(source) if isinstance(source, list) else source
                exec(compile(source, f"{path.name}:cell-{index}", "exec"), namespace)
    finally:
        os.chdir(previous_directory)
        if "lab" in namespace and namespace["lab"].connection.open:
            namespace["lab"].close()
    print(f"PASS {path.name}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iceberg", action="store_true", help="Also prepare the local lakehouse fixture and execute Module 4")
    parser.add_argument("--solutions", action="store_true", help="Validate folded reference solutions after each independent exercise")
    parser.add_argument("--extensions", action="store_true", help="Run the three additional Level 1 notebooks after the main Labs")
    parser.add_argument("--extensions-only", action="store_true", help="Run only extensions; main Labs 1, 4, 5, 6 and 7 must already be complete")
    args = parser.parse_args()
    if os.environ.get("DW_ALLOW_WRITES") != "yes":
        parser.error("Set DW_ALLOW_WRITES=yes after reading environments/single-node/README.md")
    modules = list(CORE)
    if args.iceberg:
        modules.insert(3, "module04-external-access")
    if args.extensions_only:
        modules = []
    for module in modules:
        paths = list((ROOT / "level1" / module).glob("lab*.ipynb"))
        if len(paths) != 1:
            raise RuntimeError(f"Expected exactly one lab in {module}")
        execute_notebook(paths[0], solutions=args.solutions)
    if args.extensions or args.extensions_only:
        for name in EXTENSIONS:
            execute_notebook(ROOT / "level1/extensions" / name)
    print("PASS: selected notebook code cells. This does not validate the browser UI.")
    if not args.iceberg:
        print("NOT RUN: main Lab 4 Iceberg integration. See maintenance/02-data-warehousing/integration-backlog.md.")


if __name__ == "__main__":
    main()
