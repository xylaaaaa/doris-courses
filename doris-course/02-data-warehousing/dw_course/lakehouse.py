"""Explicitly prepare only the course's local Iceberg fixtures."""

import json
import subprocess
import time

import boto3
import requests

from .docker_runtime import compose_command, _run
from .runtime import COURSE_ROOT, expect, identifier
from .ui import WorkflowProgress
from .wwi import HISTORY_COLUMNS, history_rows

PROJECT = "doris-warehousing-lake"
NETWORK = PROJECT + "_default"
COMPOSE = COURSE_ROOT / "environments/lakehouse/compose.yml"
ACCESS_KEY = "course_lake"
SECRET_KEY = "course_lake_local_only"


def _wait_http(url, timeout=90):
    deadline = time.monotonic() + timeout
    last_error = "service not ready"
    while time.monotonic() < deadline:
        try:
            response = requests.get(url, timeout=3)
            response.raise_for_status()
            return
        except requests.RequestException as error:
            last_error = str(error)
        time.sleep(1)
    raise TimeoutError(url + ": " + last_error)


def prepare_lakehouse(lab, *, start=False):
    """Start with explicit consent; create a per-lab namespace and reuse matching data."""
    if not start:
        raise ValueError("Read the Lab 4 environment guide, then set start=True to start the course lakehouse services")
    namespace = identifier(lab.database)
    catalog = identifier(lab.database + "_lake")
    table = catalog + "." + namespace + ".orders"
    progress = WorkflowProgress("Prepare the lakehouse lab", {
        1: "Start the course object storage and Iceberg services",
        2: "Wait for services to become ready",
        3: "Connect Doris to the lakehouse network",
        4: "Prepare storage for the sample",
        5: "Create the catalog and lake tables",
        6: "Verify the ten orders in the lake",
    })
    try:
        progress.advance(1)
        _run(["docker", "compose", "--project-name", PROJECT, "--file", str(COMPOSE),
              "up", "-d", "--pull", "missing"], progress, timeout=1800)
        progress.advance(2)
        _wait_http("http://127.0.0.1:51900/minio/health/live")
        _wait_http("http://127.0.0.1:51818/v1/config")
        progress.advance(3)
        container = subprocess.check_output(compose_command("ps", "-q", "doris"), text=True).strip()
        if not container or "\n" in container:
            raise RuntimeError("Run Lab 1 first to start the single-container Doris sandbox")
        networks = json.loads(subprocess.check_output(
            ["docker", "inspect", "--format", "{{json .NetworkSettings.Networks}}", container], text=True))
        if NETWORK not in networks:
            _run(["docker", "network", "connect", NETWORK, container], progress)
        progress.advance(4)
        client = boto3.client("s3", endpoint_url="http://127.0.0.1:51900",
                              aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY,
                              region_name="us-east-1")
        buckets = {entry["Name"] for entry in client.list_buckets()["Buckets"]}
        if "course-warehouse" not in buckets:
            client.create_bucket(Bucket="course-warehouse")
        progress.advance(5)
        lab.execute(f'''CREATE CATALOG IF NOT EXISTS {catalog} PROPERTIES (
            "type"="iceberg", "iceberg.catalog.type"="rest",
            "iceberg.rest.uri"="http://course-lake-rest:8181",
            "warehouse"="s3://course-warehouse/",
            "s3.endpoint"="http://course-lake-minio:9000", "s3.region"="us-east-1",
            "s3.access_key"="{ACCESS_KEY}", "s3.secret_key"="{SECRET_KEY}",
            "use_path_style"="true", "iceberg.rest.view-enabled"="false"
        )''')
        properties = dict(lab.query(f"SHOW CATALOG {catalog}"))
        expected_properties = {
            "type": "iceberg", "iceberg.catalog.type": "rest",
            "iceberg.rest.uri": "http://course-lake-rest:8181",
            "s3.endpoint": "http://course-lake-minio:9000",
            "warehouse": "s3://course-warehouse/",
        }
        if any(properties.get(key) != value for key, value in expected_properties.items()):
            raise ValueError("The existing catalog with this name points to another environment. Keep its configuration and use a new course lab database")
        lab.execute(f"CREATE DATABASE IF NOT EXISTS {catalog}.{namespace}")
        lab.execute(f'''CREATE TABLE IF NOT EXISTS {table} (
            order_id BIGINT, customer_id BIGINT, order_date DATE,
            order_amount DECIMAL(18,2), line_count INT, data_source STRING
        )''')
        count = lab.query(f"SELECT COUNT(*) FROM {table}")[0][0]
        if count == 0:
            # Identifiers are fixed and validated above; values remain parameterized.
            placeholders = ",".join(["(%s,%s,%s,%s,%s,%s)"] * len(history_rows()))
            lab.execute(f"INSERT INTO {table} ({','.join(HISTORY_COLUMNS)}) VALUES {placeholders}",
                        tuple(value for row in history_rows() for value in row))
        progress.advance(6)
        expect(lab.query(f"SELECT order_id,customer_id,CAST(order_date AS STRING),order_amount,line_count,data_source FROM {table} ORDER BY order_id"), history_rows())
        progress.finish()
        return table
    except Exception as error:
        progress.fail(str(error))
        raise
