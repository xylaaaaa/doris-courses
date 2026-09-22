"""Stage an already validated local WWI Parquet bundle; never download or upload."""

import argparse
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[3] / "doris-course/02-data-warehousing"
sys.path.insert(0, str(ROOT))
from dw_course.wwi import parquet_paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", type=Path, default=ROOT / ".runtime/wwi")
    args = parser.parse_args()
    files = parquet_paths(args.source)
    args.destination.mkdir(parents=True, exist_ok=True)
    for name in files:
        destination = args.destination / f"{name}.parquet"
        if destination.exists():
            # Do not replace potentially user-modified data. Check the complete bundle.
            raise FileExistsError(f"Destination exists: {destination}; use a fresh directory")
    for name, source in files.items():
        shutil.copyfile(source, args.destination / f"{name}.parquet")
    parquet_paths(args.destination)
    print(f"Prepared {len(files)} Parquet files at {args.destination}")


if __name__ == "__main__":
    main()
