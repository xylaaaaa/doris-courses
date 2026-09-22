"""Publication validates content and never replaces an existing release object."""

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/publish_datasets.py"
spec = importlib.util.spec_from_file_location("publish_datasets", SCRIPT)
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


class PublishTest(unittest.TestCase):
    def test_publish_and_verify_existing_or_missing_object(self):
        for exists in [True, False]:
            with self.subTest(exists=exists), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "datasets").mkdir()
                data = b"course data"
                (root / "sample.json").write_bytes(data)
                (root / "datasets/catalog.json").write_text(json.dumps({"files": {
                    "sample.json": {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                }}))
                client = Mock()
                if not exists:
                    client.head_object.side_effect = ClientError({"Error": {"Code": "404"}}, "HeadObject")
                client.download_file.side_effect = lambda b, k, dest, **kwargs: Path(dest).write_bytes(data)
                args = ["publish", "--source", directory, "--bucket", "course"]
                with patch.object(publisher, "ROOT", root), patch("sys.argv", args), patch.object(
                    publisher.boto3, "client", return_value=client
                ) as factory:
                    publisher.main()
                    self.assertEqual(client.upload_file.call_count, 0 if exists else 1)
                    config = factory.call_args.kwargs["config"]
                    self.assertEqual(config.s3["addressing_style"], "virtual")
                    self.assertEqual(config.request_checksum_calculation, "when_required")
                    client.download_file.side_effect = lambda b, k, dest, **kwargs: Path(dest).write_bytes(b"corrupt")
                    client.head_object.side_effect = None
                    client.upload_file.reset_mock()
                    with self.assertRaisesRegex(ValueError, "Remote object differs"):
                        publisher.main()
                    client.upload_file.assert_not_called()
