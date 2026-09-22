"""Offline checks for remote downloads, cache integrity, and credential settings."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[3] / "doris-course/02-data-warehousing"
sys.path.insert(0, str(ROOT))
from dw_course import runtime


class DatasetTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.payload = b'[{"order_id": 1}]\n'
        self.entry = {"bytes": len(self.payload), "sha256": hashlib.sha256(self.payload).hexdigest()}
        self.catalog = {"source": {"bucket": "course", "prefix": "v1", "region": "us-east-1",
                                   "endpoint": "https://s3.us-east-1.amazonaws.com"},
                        "files": {"orders.json": self.entry}}
        for mock in [patch.object(runtime, "_dataset_catalog", return_value=self.catalog),
                     patch.dict("os.environ", {"DW_DATA_DIR": str(self.root / "cache"),
                                               "DW_COURSE_SECRETS": str(self.root / "secrets")}, clear=True)]:
            mock.start()
            self.addCleanup(mock.stop)
        self.client = Mock()
        self.client.download_file.side_effect = self.download
        mock = patch("boto3.client", return_value=self.client)
        self.factory = mock.start()
        self.addCleanup(mock.stop)

    def download(self, bucket, key, destination, **kwargs):
        self.assertEqual((bucket, key), ("course", "v1/orders.json"))
        Path(destination).write_bytes(self.payload)

    def test_first_read_downloads_and_subsequent_read_reuses_cache(self):
        self.assertEqual(runtime.fixture("orders.json"), [{"order_id": 1}])
        self.assertEqual(runtime.fixture("orders.json"), [{"order_id": 1}])
        self.client.download_file.assert_called_once()
        self.assertEqual(self.factory.call_args.kwargs["config"].s3["addressing_style"], "virtual")
        self.assertEqual(list((self.root / "cache").iterdir()), [self.root / "cache/orders.json"])

    def test_corrupt_cached_data_is_replaced_only_after_valid_download(self):
        path = runtime.dataset_path("orders.json")
        path.write_bytes(b"invalid")
        self.client.download_file.side_effect = lambda b, k, dest, **kwargs: Path(dest).write_bytes(b"bad")
        with self.assertRaisesRegex(ValueError, "does not match"):
            runtime.dataset_path("orders.json")
        self.assertEqual(path.read_bytes(), b"invalid")
        self.assertEqual(list(path.parent.iterdir()), [path])
        self.client.download_file.side_effect = self.download
        self.assertEqual(runtime.dataset_path("orders.json").read_bytes(), self.payload)

    def test_failed_partial_download_is_not_published(self):
        def fail(bucket, key, destination, **kwargs):
            Path(destination).write_bytes(b"partial")
            raise ClientError({"Error": {"Code": "AccessDenied", "Message": "denied"}}, "GetObject")
        self.client.download_file.side_effect = fail
        with self.assertRaisesRegex(RuntimeError, "Could not download orders.json"):
            runtime.dataset_path("orders.json")
        self.assertEqual(list((self.root / "cache").iterdir()), [])

    def test_unknown_names_do_not_download(self):
        for name in ("../orders.json", "/orders.json", "unknown.json", "..", ""):
            with self.subTest(name=name), self.assertRaises((ValueError, FileNotFoundError)):
                runtime.dataset_path(name)
        self.factory.assert_not_called()

    def test_local_bucket_and_credentials_override_catalog(self):
        (self.root / "secrets").write_text(
            "DW_DATA_ENDPOINT=http://127.0.0.1:51900\nDW_DATA_BUCKET=local-course\n"
            "DW_DATA_PREFIX=release/v2/\nS3_READ_ONLY_ACCESS_KEY=test-access\n"
            "S3_READ_ONLY_SECRET_KEY=test-secret\n")
        self.client.download_file.side_effect = lambda b, k, dest, **kwargs: Path(dest).write_bytes(self.payload)
        runtime.dataset_path("orders.json")
        self.assertEqual(self.client.download_file.call_args.args[:2], ("local-course", "release/v2/orders.json"))
        self.assertEqual(self.factory.call_args.kwargs["endpoint_url"], "http://127.0.0.1:51900")
        self.assertEqual(self.factory.call_args.kwargs["aws_access_key_id"], "test-access")

    def test_incomplete_credentials_fail_before_download(self):
        (self.root / "secrets").write_text("S3_READ_ONLY_ACCESS_KEY=test-access\n")
        with self.assertRaisesRegex(ValueError, "Set both"):
            runtime.dataset_path("orders.json")
        self.factory.assert_not_called()

    def test_two_kernels_use_separate_download_files(self):
        barrier = threading.Barrier(2)
        paths = []
        def download(bucket, key, destination, **kwargs):
            paths.append(destination)
            barrier.wait(timeout=5)
            Path(destination).write_bytes(self.payload)
        self.client.download_file.side_effect = download
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(runtime.dataset_path, ["orders.json", "orders.json"]))
        self.assertEqual(results[0], results[1])
        self.assertEqual(len(set(paths)), 2)
        self.assertEqual(results[0].read_bytes(), self.payload)


if __name__ == "__main__":
    unittest.main()
