"""Run only explicitly selected optional streaming notebooks; keep outputs in logs."""
import argparse
import os
from run_labs import ROOT, execute_notebook


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lab", choices=["kafka", "cdc", "all"])
    args = parser.parse_args()
    if os.environ.get("DW_ALLOW_WRITES") != "yes":
        parser.error("Read environments/streaming/README.md and set DW_ALLOW_WRITES=yes")
    names = {"kafka": "optional5_kafka_routine_load.ipynb", "cdc": "optional5_flink_mysql_cdc.ipynb"}
    for key, name in names.items():
        if args.lab in (key, "all"):
            execute_notebook(ROOT / "level1/module05-ingestion" / name)


if __name__ == "__main__":
    main()
