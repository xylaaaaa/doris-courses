# Repository recovery drill for Lab 13

Lab 13 explicitly starts this S3-compatible MinIO service, performs a real full `BACKUP SNAPSHOT`, force-drops only its dedicated source table, restores into a separate course database, and verifies ordered rows, count and amount.

- Pinned image; at most 512 MiB RAM; loopback port 51910 only.
- Public local teaching credentials (`course_backup` / `course_backup_local_only`), not production secrets.
- The FE and BE use the container endpoint, not the host's loopback endpoint.
- The source is a coupled-mode ordinary table without an asynchronous MV or Storage Policy.
- Doris and MinIO share one host: this is **not** independent disaster-recovery storage.

From the course root, stop while retaining snapshot objects:

```bash
docker compose --project-name doris-warehousing-backup --file environments/backup/compose.yml stop
```

The snapshot label and timestamp come from the actual completed backup. Restoring a snapshot does not replay later writes. The repository, object volume and isolated target remain for inspection; dropping the repository registration does not delete remote objects. Never delete the volume without an explicit retention decision.
