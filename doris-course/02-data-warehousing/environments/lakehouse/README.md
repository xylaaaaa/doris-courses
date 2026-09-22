# Lake Table Lab Environment

Lab 4 uses the course Doris instance to query real Iceberg tables. Running the preparation cell starts two helper containers:

| Service | Pinned Image | Local Port | Stored Content |
| --- | --- | --- | --- |
| MinIO | minio/minio:RELEASE.2025-01-20T14-49-07Z | 51900 | Iceberg metadata files and Parquet data |
| Iceberg REST Catalog | apache/iceberg-rest-fixture:1.10.0 | 51818 | SQLite table catalog |

Complete Lab 1 first, install the dependencies in the course requirements.txt, and confirm that both ports are free.
Then run the code in Lab 4 in order; preparation displays progress and verifies the ten orders.
The first run requires network access to download images. Later runs reuse data in the named volumes and check that the sample matches the course manifest.

The helper containers join the same Docker network as the course Doris instance. Each lab database uses a separate Catalog and lake table namespace;
the preparation step preserves existing tables and stops to report differences if the sample contents do not match.

These services are for local teaching: ports bind only to 127.0.0.1, and credentials are openly specified in compose.yml.
The REST fixture runs as root so it can write to SQLite in the Docker named volume; production requires separately designed identity and access management.

## Stop and Reuse

Run the following command from this course directory to stop the helper services while retaining data in the named volumes:

```bash
docker compose -f environments/lakehouse/compose.yml stop
```

Running the Lab 4 preparation cell next time will restart them. This command does not stop Doris.
For connection errors, first check Docker's status and port usage, then inspect the course helper service logs:

```bash
docker compose -f environments/lakehouse/compose.yml ps
docker compose -f environments/lakehouse/compose.yml logs --tail 80 rest minio
```
