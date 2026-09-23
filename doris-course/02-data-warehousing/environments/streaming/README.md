# Optional streaming lab environment

These independent optional labs do not change the completion requirements for the seven main labs:

- [Lab 5A: Kafka → Routine Load](../../level1/module05-ingestion/optional5_kafka_routine_load.ipynb): continuous consumption, progress, pause/resume, duplicate orders, and state updates.
- [Lab 5B: MySQL → Flink CDC → Doris](../../level1/module05-ingestion/optional5_flink_mysql_cdc.ipynb): a single-table snapshot, inserts/updates/deletes, checkpoints, and controlled savepoint stop/restore. Module 7 can reuse this lab.

## Prerequisites and startup

Use Linux Docker Engine or Docker Desktop with Linux containers, Docker Compose v2, and the course Python dependencies. Run Jupyter on the Docker host; use SSH port forwarding for remote browser access. This configuration is not for remote Docker daemons or production clusters.

The optional labs use different resource profiles. The Kafka-only lab requires **at least 10 GiB of Docker-visible RAM and 2 CPUs**; it uses an 8 GiB Doris cap and limits Kafka's JVM to 512 MiB. The MySQL/Flink CDC lab requires **at least 18 GiB and 4 CPUs** because it runs Doris, MySQL, JobManager, and TaskManager together. Also allow at least 8 GB of additional disk space. These are conservative course profiles, not production sizing claims. On Docker Desktop, allocate these resources to the Docker VM, not just the physical host.

The first notebook cell runs `docker info` and rejects insufficient total capacity before starting containers. It selects the Kafka or CDC profile explicitly; it does not measure free memory or reserve resources. On a shared host, check current memory pressure and disk space yourself; meeting the total-capacity check does not guarantee success. Initial startup needs Docker Hub and Maven Central access.

Start Jupyter from the course root, open a notebook, and run its cells in order. The notebooks pass `streaming_profile="kafka"` or `streaming_profile="cdc"` to select the matching resource overlay, then start only the selected streaming dependency profile.

**Finish other course work before the first streaming startup.** Applying the overlay may recreate the existing course Doris container; it retains the same Compose project, FE metadata volume, BE storage volume, and ports. It does not delete data volumes. The Kafka notebook applies `doris-resources-kafka.yml` and limits Doris to 8 GiB; the CDC notebook applies `doris-resources.yml` and limits Doris to 12 GiB. Both overlays set memory and memory-plus-swap limits explicitly rather than relying on an undocumented `docker update`.

Both labs reuse `environments/single-node`. Do not run two instances of the same lab concurrently, or start a main-course notebook while a streaming lab is running: the main-course startup uses the base configuration without this overlay and may recreate the container without the cap.

| Component | Pinned version / purpose |
|---|---|
| Doris | Reuses `apache/doris:all-in-one-4.1.3`, one FE/BE sandbox |
| Kafka | `apache/kafka:3.9.0`, single-node KRaft and a single-partition demonstration |
| MySQL | `mysql:8.0.33`, ROW/FULL Binlog, seven-day retention, server timezone +08:00 matching CDC Asia/Shanghai |
| Flink | `flink:1.20.1-scala_2.12-java11` |
| Flink MySQL CDC SQL JAR | `3.4.0` |
| Flink Doris Connector | `flink-doris-connector-1.20:25.0.0` |
| MySQL JDBC | `8.0.27`, downloaded separately for licensing reasons; see the CDC documentation below |

### Manual startup and resource checks

From the course root, with the course Python environment activated:

```bash
# Kafka capacity preflight; use check_resources("cdc") for the CDC lab.
python -c 'from dw_course.streaming import check_resources; check_resources("kafka")'
# Check Docker disk usage and current container memory use as well.
docker system df
docker stats --no-stream
# Kafka notebook overlay; retain the project and volumes.
docker compose --project-name doris-warehousing-course \
  -f environments/single-node/compose.yml \
  -f environments/streaming/doris-resources-kafka.yml up -d --wait --wait-timeout 300
# For Kafka, the Doris limit should be 8589934592 bytes. The CDC overlay uses 12884901888.
docker inspect doris-warehousing-course-doris-1 \
  --format 'Memory={{.HostConfig.Memory}} MemorySwap={{.HostConfig.MemorySwap}}'
# Start only the dependencies for the lab you selected.
docker compose -f environments/streaming/compose.yml --profile kafka up -d
docker compose -f environments/streaming/compose.yml --profile cdc up -d --build
```

Kafka shares the course Doris network and advertises `course-stream-kafka:9092`; the producer runs inside the Kafka container. MySQL is reachable only on the streaming network. Flink joins both networks, reaches FE through `doris:8030`, and explicitly sets `benodes=doris:8040` and `auto-redirect=false`. This avoids treating the single-container sandbox's registered BE loopback address as Flink's own loopback address. Do not substitute container `localhost` or host-mapped ports for these service addresses.

The only additional host port is a Docker-selected free localhost port for the Flink Web UI. `prepare_streaming("cdc", start=True)` discovers that port and updates the Python REST client automatically, so it does not collide with Jupyter's randomly allocated ZMQ ports. Kafka and MySQL publish no host ports. Demonstration accounts and plaintext passwords are for local course tests only; Doris retains the sandbox root account with an empty password. Do not copy these settings to shared or production environments.

Startup, Flink job, checkpoint, and data waits show a live status card in Jupyter with elapsed time, check count, and timeout. A wait is expected while local services initialize; a red failure card means the wait stopped and includes the last observation or error.

## Data and restoration boundaries

- The labs rebuild only their respective tables, `ext_kafka_orders` and `ext_cdc_orders`, in the isolated Doris database `dw_course_l1_streaming`. They do not modify the main business tables.
- MySQL initialization scripts run only when creating the volume. Each new CDC experiment clears and reloads the dedicated `course_cdc.orders` table. Restoration steps do not clear the source or target.
- Each Kafka run creates a random topic and Routine Load job. Successful completion stops the job and deletes only that topic, retaining Doris results.
- Each new Flink experiment uses a unique label prefix. Restoration reuses the same SQL, prefix, and parallelism. Checkpoints and savepoints reside in a shared named volume.
- CDC does not pass through Kafka; the two labs are independent.
- Real source changes and controlled savepoint restoration are covered. Whole-database synchronization, automatic schema evolution, automatic crash recovery, atomic visibility across tables, and sustained concurrency are not.
- `SHOW MASTER STATUS` shows the source end position, not the position consumed by Flink. Restoration needs saved state, readable Binlog files, and matching job configuration; business timestamps alone are insufficient.

## Troubleshooting and shutdown

From the course root:

```bash
docker compose -f environments/streaming/compose.yml --profile kafka --profile cdc ps
docker compose -f environments/streaming/compose.yml logs --tail=100 kafka mysql jobmanager taskmanager
```

- **Resource preflight failure:** use the Kafka profile for Lab 5A, or increase Docker VM resources for the CDC lab. Do not disable the check to claim the profile is validated on a smaller machine. A Docker Desktop allocation below 10 GiB cannot run the Kafka profile reliably.
- **`MEM_LIMIT_EXCEEDED`:** confirm the Doris limits with the inspect command above, then check host/VM free memory, container usage, and Doris memory watermarks. If another main-course startup removed the overlay, finish active work and reapply the documented overlay. Do not disable memory protection or delete volumes to bypass the error.
- **Routine Load failure:** data waits report unexpected PAUSED/STOPPED/CANCELLED states with the job name, `ReasonOfStateChanged`, and `ErrorLogUrls`. Run the supplied `SHOW ALL ROUTINE LOAD FOR ...` statement for details. Confirm that Doris can reach the advertised broker address. Intentional pause verification uses a direct query, not the healthy-job wait.
- **Interrupted Kafka notebook:** the notebook stops stale jobs matching its own `course_orders_<12-hex-chars>` name and `ext_kafka_orders` target before rebuilding the table. If it finds another job, it refuses to stop it and asks you to inspect it; do not stop jobs in other databases.
- **Flink failure:** data and checkpoint waits check job state on every poll and fail on terminal states, even if an earlier checkpoint completed. Follow the exception-page link and inspect SQL Client, JobManager, and TaskManager logs. Check JARs, networking, and source permissions. A SQL Client exit code alone does not establish success.
- **Interrupted CDC notebook:** the notebook cancels stale jobs named `course_mysql_orders` before resetting the source and target. If it finds another active Flink job, it refuses to cancel it and asks you to inspect it. Use `flink stop` below when you intend to preserve a savepoint rather than start a new experiment.
- **Restoration timeout:** inspect job exceptions and checkpoints. Do not delete state or rerun initialization to disguise a failed restore. Expired Binlog history requires a new snapshot and separate consistency checks.
- **Port conflict:** Docker selects a free localhost port automatically. If a previously created container still has the old fixed-port mapping, rerun `up` so Compose recreates the JobManager; do not stop unrelated processes.

```bash
docker compose -f environments/streaming/compose.yml exec -T jobmanager \
  /opt/flink/bin/flink stop --savepointPath file:///opt/flink/state/savepoints <job-id>
# Stop dependencies only after stopping this run's Routine Load / Flink jobs.
docker compose -f environments/streaming/compose.yml --profile kafka --profile cdc stop
```

Stopping retains all volumes and Doris results. `up -d` does not automatically restore a stopped Flink job: resubmit using the SQL and savepoint path saved in the notebook. Save these before closing the kernel if you plan to restore later. The course does not automatically run `down -v`, stop Doris, or clean unrelated projects.

## Maintainer validation

From the repository root, using Python with the course dependencies installed; keep logs outside the working tree:

```bash
DW_ALLOW_WRITES=yes .venv/bin/python \
  maintenance/02-data-warehousing/scripts/run_streaming_labs.py all
```

Replace `all` with `kafka` or `cdc` to select one lab. This executes notebook code without saving outputs; browser UI inspection is separate. Validation records are in `maintenance/02-data-warehousing/VALIDATION.md` at the repository root. Linux local validation does not establish a clean-install or Docker Desktop/ARM compatibility guarantee.

## Official references

- [Routine Load syntax](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-modification/load-and-export/CREATE-ROUTINE-LOAD/)
- [Flink Doris Connector versions and configuration](https://doris.apache.org/docs/4.x/connection-integration/data-integration/flink-doris-connector/)
- [Flink CDC 3.4 MySQL SQL Connector](https://nightlies.apache.org/flink/flink-cdc-docs-release-3.4/docs/connectors/flink-sources/mysql-cdc/)
