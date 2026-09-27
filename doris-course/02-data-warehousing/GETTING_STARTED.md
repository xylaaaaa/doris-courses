# First-time setup

Use this page when you are opening the course for the first time or when a Lab says that setup is required.

## What you need

- The complete repository, including the shared course components.
- Python 3.10–3.13 and a virtual environment.
- Docker Desktop on macOS or Windows, or Docker Engine with the Compose plugin on Linux.
- About 4 CPUs, 8 GB of memory, and 20 GB of free disk space for the learning sandbox.

Docker and Jupyter must run on the same machine. The browser may be on another machine, but the Python kernel starts the container and connects to Doris locally.

## Install the Python tools

From this directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Start Jupyter with the course root:

```bash
.venv/bin/jupyter lab level1/module01-introduction/lab1_connect_and_query.ipynb
```

Select the matching `.venv` Python kernel if Jupyter offers more than one kernel.

## Start the database from Lab 1

1. Start Docker Desktop or Docker Engine and wait until `docker info` succeeds.
2. In Lab 1, run **Initialize the Lab Tools**.
3. Read the reset notice, then run **Start and Connect**.
4. Continue only when the result shows `connection_ok = 1`.

The first start downloads `apache/doris:all-in-one-4.1.3` and can take several minutes. The Lab creates the dedicated `dw_course_l1_demo` database and keeps the course container and volumes separate from other Docker projects.

## Follow the data dependencies

Complete the main Labs in order: Lab 1, Lab 2, Lab 3, Lab 4, Lab 5, Lab 6, and Lab 7. Lab 6 reads the historical customer table created by Lab 5. Lab 7 reads the cleaned orders and customer data produced by Lab 6.

After a kernel restart, rerun that Notebook's initialization and connection cells. The connection cell does not start Docker; return to Lab 1 if the sandbox is stopped or has never been created.

## Optional Kafka and Flink labs

The optional Lab 5A Kafka notebook needs Docker-visible capacity of at least 14 GiB RAM and 4 CPUs. The optional Lab 5B Flink CDC notebook needs 18 GiB RAM and 4 CPUs. Set Docker Desktop's **Resources** before running either notebook; the notebook checks capacity before it starts any streaming containers. A 16 GiB Mac can run Lab 5A after allocating about 15 GiB to Docker, but it cannot meet the CDC profile's 18 GiB requirement. These optional labs are independent of the seven main Labs.

## If setup fails

Run these checks from this directory:

```bash
docker info
docker compose version
docker compose --project-name doris-warehousing-course --file environments/single-node/compose.yml ps
```

For `command not found`, install Docker and open a new terminal. For a refused connection, start Lab 1's **Start and Connect** cell and wait for its health check. For missing prerequisite tables, return to the first Lab named in the message and complete it in the same course database.
