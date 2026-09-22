"""Publish validated data from a local directory to a versioned S3 prefix."""

import argparse
import json
from pathlib import Path
import sys
import tempfile

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[3] / "doris-course/02-data-warehousing"
sys.path.insert(0, str(ROOT))
from dw_course.runtime import _dataset_matches, _download_dataset_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--prefix", default="doris-course/data-warehousing/v1")
    parser.add_argument("--endpoint")
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()
    catalog = json.loads((ROOT / "datasets/catalog.json").read_text())
    # Validate the complete release before issuing the first write.
    for name, entry in catalog["files"].items():
        if not _dataset_matches(args.source / name, entry):
            raise ValueError(f"Missing or changed source dataset: {name}")
    client = boto3.client("s3", endpoint_url=args.endpoint, region_name=args.region,
                          config=Config(s3={"addressing_style": "virtual"},
                                        request_checksum_calculation="when_required"))
    for name, entry in catalog["files"].items():
        key = "/".join(part for part in [args.prefix.strip("/"), name] if part)
        try:
            client.head_object(Bucket=args.bucket, Key=key)
        except ClientError as error:
            if error.response["Error"]["Code"] not in {"404", "NoSuchKey"}:
                raise
            client.upload_file(str(args.source / name), args.bucket, key)
        with tempfile.TemporaryDirectory(prefix="dataset-verify-") as directory:
            downloaded = Path(directory) / name
            _download_dataset_file(client, args.bucket, key, downloaded)
            if not _dataset_matches(downloaded, entry):
                raise ValueError(f"Remote object differs from catalog: {key}; use a new release prefix")
        print(f"Verified s3://{args.bucket}/{key}", flush=True)


if __name__ == "__main__":
    main()
