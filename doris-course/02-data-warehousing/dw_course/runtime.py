"""Explicit connection and assertion helpers; never start or stop a cluster."""

import hashlib
import json
import os
import re
import tempfile
from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal
from pathlib import Path

import pymysql
import requests
import pandas as pd

from .ui import card, in_notebook, install_styles, show_frame, show_sql

COURSE_ROOT = Path(__file__).resolve().parents[1]
DATASET_CATALOG = COURSE_ROOT / "datasets" / "catalog.json"


def _dataset_catalog():
    return json.loads(DATASET_CATALOG.read_text(encoding="utf-8"))


def _dataset_entry(name):
    if Path(name).name != name:
        raise ValueError("Dataset must be a basename")
    try:
        return _dataset_catalog()["files"][name]
    except KeyError as error:
        raise FileNotFoundError(f"Unknown course dataset: {name}") from error


def _dataset_cache():
    return Path(os.environ.get("DW_DATA_DIR", COURSE_ROOT / ".runtime" / "datasets")).resolve()


def _dataset_matches(path, entry):
    if not path.is_file() or path.stat().st_size != entry["bytes"]:
        return False
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest() == entry["sha256"]


def _download_dataset_file(client, bucket, key, destination):
    from boto3.s3.transfer import TransferConfig

    # Smaller ranges limit the work lost when a remote connection is interrupted.
    client.download_file(bucket, key, str(destination), Config=TransferConfig(
        multipart_threshold=1024 * 1024, multipart_chunksize=1024 * 1024,
        max_concurrency=4,
    ))


def _download_dataset(name, destination, entry):
    try:
        import boto3
        from botocore.config import Config
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError as error:
        raise RuntimeError("boto3 is required to download the course datasets; install requirements.txt") from error

    credentials = {}
    secrets_path = Path(os.environ.get("DW_COURSE_SECRETS", COURSE_ROOT / "course_secrets.env"))
    if secrets_path.exists():
        for raw in secrets_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#"):
                key, separator, value = line.partition("=")
                if not separator:
                    raise ValueError(f"Invalid line in {secrets_path.name}: {raw!r}")
                credentials[key.strip()] = value.strip()
    def setting(key, default=None):
        return os.environ.get(key, credentials.get(key, default))

    access_key = setting("S3_READ_ONLY_ACCESS_KEY")
    secret_key = setting("S3_READ_ONLY_SECRET_KEY")
    if bool(access_key) != bool(secret_key):
        raise ValueError("Set both S3_READ_ONLY_ACCESS_KEY and S3_READ_ONLY_SECRET_KEY")
    source = _dataset_catalog()["source"]
    bucket = setting("DW_DATA_BUCKET", source["bucket"])
    prefix = setting("DW_DATA_PREFIX", source["prefix"]).strip("/")
    client = boto3.client(
        "s3",
        config=Config(s3={"addressing_style": "virtual"}),
        endpoint_url=setting("DW_DATA_ENDPOINT", source["endpoint"]),
        region_name=setting("DW_DATA_REGION", source["region"]),
        aws_access_key_id=access_key or None,
        aws_secret_access_key=secret_key or None,
    )
    with tempfile.TemporaryDirectory(prefix=".download-", dir=destination.parent) as directory:
        temporary = Path(directory) / name
        try:
            _download_dataset_file(client, bucket, f"{prefix}/{name}" if prefix else name, temporary)
        except (BotoCoreError, ClientError, OSError) as error:
            raise RuntimeError(
                f"Could not download {name}. Check the bucket settings and read-only "
                f"credentials in {secrets_path}, or the standard boto3 credential chain."
            ) from error
        if not _dataset_matches(temporary, entry):
            raise ValueError(f"Downloaded dataset does not match its catalog entry: {name}")
        os.replace(temporary, destination)


def dataset_path(name):
    """Return a validated local path, downloading the authored object on first use."""
    entry = _dataset_entry(name)
    destination = _dataset_cache() / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not _dataset_matches(destination, entry):
        _download_dataset(name, destination, entry)
    return destination


def identifier(value):
    if re.fullmatch(r"[a-z][a-z0-9_]*", value) is None:
        raise ValueError("Expected a lowercase SQL identifier")
    return value


def fixture(name):
    """Read a validated course fixture from the local cache or course bucket."""
    return json.loads(dataset_path(name).read_text(encoding="utf-8"))


def normalized(value):
    if isinstance(value, Decimal):
        return format(value, ".2f")
    if isinstance(value, (tuple, list)):
        return [normalized(item) for item in value]
    return value


_expected_failure = ContextVar("course_expected_failure", default=False)


class CourseCheckError(AssertionError):
    """A result mismatch, distinct from unrelated execution errors."""


@contextmanager
def expected_failure(title, message):
    """Show success only when a course result check detects an intended mismatch."""
    token = _expected_failure.set(True)
    detected = False
    try:
        yield
    except CourseCheckError:
        detected = True
    finally:
        _expected_failure.reset(token)
    if not detected:
        expect("Expected error not detected", "Expected error detected")
    if in_notebook():
        card(message, "ok", title)
    else:
        print(title + ": " + message)


def expect(actual, expected, *, title=None):
    """Raise on mismatch even when Python runs with optimization enabled."""
    if normalized(actual) != normalized(expected):
        if in_notebook() and not _expected_failure.get():
            card("The actual result differs from the expected result. See the exception details below.", "fail", "Validation failed")
        raise CourseCheckError(f"Expected {expected!r}, got {actual!r}")
    if in_notebook():
        if title is not None:
            card("The result matches the expectation.", "ok", title)
    else:
        print("PASS", normalized(expected))


class WarehouseLab:
    def __init__(self, *, allow_writes=False):
        if not allow_writes and os.environ.get("DW_ALLOW_WRITES") != "yes":
            raise RuntimeError("Read the reset scope, then set DW_ALLOW_WRITES=yes")
        self.database = identifier(os.environ.get("DW_DATABASE", "dw_course_l1_demo"))
        if not self.database.startswith("dw_course_l1_"):
            raise ValueError("Use a dedicated database with prefix dw_course_l1_")
        self.user = os.environ.get("DW_USER", "root")
        self.password = os.environ.get("DW_PASSWORD", "")
        self.connection = pymysql.connect(
            host=os.environ.get("DW_HOST", "127.0.0.1"),
            port=int(os.environ.get("DW_PORT", "9030")),
            user=self.user,
            password=self.password,
            charset="utf8mb4",
            autocommit=True,
            connect_timeout=5,
            read_timeout=120,
            write_timeout=120,
        )
        self.execute(f"CREATE DATABASE IF NOT EXISTS {self.database}")
        self.execute(f"USE {self.database}")
        self.execute("SET time_zone = '+08:00'")
        self.execute("SET group_commit = 'off_mode'")
        if in_notebook():
            install_styles()
            card(self.database, "ok", "Connected to the lab database")

    def query(self, sql, params=None):
        with self.connection.cursor() as cursor:
            cursor.execute(sql, params)
            return list(cursor.fetchall())

    def sql(self, statement, params=None, *, title="Query result"):
        """Display named columns like course 01; query() remains assertion-friendly."""
        with self.connection.cursor() as cursor:
            if in_notebook():
                show_sql(title, cursor.mogrify(statement, params))
            cursor.execute(statement, params)
            rows = list(cursor.fetchall())
            columns = [column[0] for column in cursor.description]
        frame = pd.DataFrame(rows, columns=columns)
        if in_notebook():
            show_frame(title, frame)
        else:
            print(frame.to_string(index=False))
        return frame

    def execute(self, sql, params=None):
        with self.connection.cursor() as cursor:
            return cursor.execute(sql, params)

    def insert(self, table, columns, rows):
        table = identifier(table)
        columns = [identifier(col) for col in columns]
        statement = f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join(['%s'] * len(columns))})"
        with self.connection.cursor() as cursor:
            return cursor.executemany(statement, rows)

    def stream_load(self, table, path, label, columns=None, *, format="csv"):
        """Use an explicitly configured BE HTTP endpoint; do not forward secrets on redirects."""
        table = identifier(table)
        if format not in ("csv", "parquet"):
            raise ValueError("This lab supports CSV and Parquet")
        headers = {
            "label": label, "format": format, "strict_mode": "true",
            "max_filter_ratio": "0", "group_commit": "off_mode",
        }
        if format == "csv":
            headers["column_separator"] = ","
        if columns is not None:
            headers["columns"] = columns
        endpoint = os.environ.get("DW_BE_HTTP_URL", "http://127.0.0.1:8040").rstrip("/")
        with Path(path).open("rb") as payload:
            response = requests.put(
                f"{endpoint}/api/{self.database}/{table}/_stream_load",
                auth=(self.user, self.password),
                headers=headers,
                data=payload,
                allow_redirects=False,
                timeout=120,
            )
        if 300 <= response.status_code < 400:
            raise RuntimeError("Set DW_BE_HTTP_URL to the trusted BE HTTP endpoint, not FE")
        response.raise_for_status()
        return response.json()

    def close(self):
        self.connection.close()
