# Lab Environment Setup

This course uses the official All-in-One image to run one FE and one BE in a single Docker container.
The single-node environment is for learning, not a production deployment plan.

## 1. Install the Python Environment

Keep the entire repository and run the following in `doris-course/02-data-warehousing`:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Display and quiz functionality depend on shared components in the repository; do not copy this course directory on its own.
If Jupyter runs on a remote server, “local machine” below refers to the server, not the Mac running your browser.

## 2. Start the Course Sandbox

Start Docker Desktop (macOS) or Docker Engine (Linux) first, and install the Compose plugin.
We recommend reserving 4 CPUs, 8 GB of memory, and 20 GB of free disk space.

Open [Lab 1](../../level1/module01-introduction/lab1_connect_and_query.ipynb) directly:

```bash
.venv/bin/jupyter lab level1/module01-introduction/lab1_connect_and_query.ipynb
```

Run “Initialize Lab Tools” first, then run the startup code under “Start the Single-Container Lab Environment.”
The startup interface displays a progress bar and six step-status cards in two columns: completed steps are green, the current step is yellow,
failed steps are red, and subsequent steps remain gray. Full logs expand on failure; success logs are collapsed by default.
The course tools validate [compose.yml](compose.yml), start or reuse the sandbox, wait for health checks,
verify the FE connection and BE computation, and then connect to the lab database. The first download and startup may take several minutes.

Subsequent Labs automatically connect to the same sandbox without creating more containers or requiring manual connection environment variables.
Each Notebook configures the same set of connection parameters anew, without depending on the in-memory state of other Notebook kernels.
Read the reset notice before starting a Lab; running the connection and lab code confirms that you agree to the corresponding teaching tables being rebuilt.

| Item | Configuration |
| --- | --- |
| Image | apache/doris:all-in-one-4.1.3 |
| Compose project | doris-warehousing-course |
| Service count | One doris service, containing one FE and one BE in the container |
| FE query port | Host 52030 → container 9030 |
| FE HTTP port | Host 51030 → container 8030 |
| BE HTTP port | Host 51040 → container 8040 |
| Default lab database | dw_course_l1_demo |
| Data retention | Project-specific FE metadata volume and BE storage volume |
| Network exposure | Bound only to host 127.0.0.1 |

Passwordless root is used only for this local teaching sandbox, not as an example for remote deployment.
The course uses a separate project, ports, and data volumes, and will not reuse or stop other services' containers.
When multiple people share the same sandbox, the instructor can set a different DW_DATABASE for each person before starting their Jupyter instance;
lab database names must start with dw_course_l1_.

## 3. Prepare the Module 5 Historical Data Package

The small WWI sample for Modules 1–3 and simulated events for Module 6/Module 7 are downloaded from the course bucket on first use.
The complete Module 5 Parquet archive is downloaded into the ignored local runtime cache and automatically extracted and validated on first use; see [Dataset Documentation](../../datasets/README.md).
By default, it is extracted to `.runtime/wwi/` in the course directory; if you already have data files from the same version, you can also set the following before starting Jupyter:

```bash
export DW_WWI_DATA_DIR=/absolute/path/to/wwi-parquet
```

The path refers to the machine running the Jupyter kernel. Module 5 validates all files; no Kaggle account, SQL Server, or S3 keys are required.

## 4. Troubleshooting

| Symptom | What to Check |
| --- | --- |
| Python package import fails | Confirm that the Notebook uses the Python kernel where course dependencies are installed |
| Connection refused | Verify the FE query port and check whether the service is ready |
| Access denied | Verify the user, password, connection source, and permissions to create databases and tables |
| BE is not alive, or tables cannot be created or written to | Check SHOW BACKENDS and the BE logs |
| Docker port is in use | Ask the instructor to coordinate the course environment; do not stop services you do not own |
| Module 1 succeeds but the next Lab cannot connect | Confirm that the kernel is on the same machine and the sandbox is still running; run the initialization and connection steps in the current Notebook |

To troubleshoot your own sandbox, run the following in the course directory:

```bash
docker compose --project-name doris-warehousing-course --file environments/single-node/compose.yml ps
docker compose --project-name doris-warehousing-course --file environments/single-node/compose.yml logs --tail 100 doris
```

## 5. Finish and Resume Learning

Stop your own sandbox while retaining its data volumes:

```bash
docker compose --project-name doris-warehousing-course --file environments/single-node/compose.yml stop
```

Restart an already-created sandbox:

```bash
docker compose --project-name doris-warehousing-course --file environments/single-node/compose.yml start --wait
```

Do not delete data volumes as a retry strategy, and do not operate on containers that do not belong to this course.

Tables are named for their business meaning or lab purpose; see [Level 1 Table Naming](../../level1/README.md#how-are-lab-tables-named) for their meanings.
When resuming, confirm that prerequisite Labs' tables are ready; if data needs to be rebuilt, rerun the relevant Labs in learning order.

Each Lab states at the beginning which tables it rebuilds. Module 1 rebuilds only orders_sample;
Module 7 reads the valid orders from Module 6 and rebuilds only its own order state, event, and business transaction lab tables.

Before the first data download, copy `course_secrets.env.example` to `course_secrets.env` and configure the current bucket and read credentials as described in the [data guide](../../datasets/README.md). A new clone needs read credentials for the OSS dataset prefix; the catalog already supplies the bucket and endpoint.
