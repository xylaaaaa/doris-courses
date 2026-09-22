# Data Warehousing with Apache Doris

From order data to trustworthy business analysis: learn how to ingest data, handle invalid records and state changes,
then progress through data warehouse modeling, analytics services, and operational governance.

This course is for data engineers and analytics engineers preparing to build a data warehouse with Doris.
You need to be able to read basic SQL; the first module walks you through connecting to the environment and creating your first order table.

## Start Here

1. Read [Environment Setup](environments/single-node/README.md) to prepare your Python environment.
2. Open the [Level 1 Learning Guide](level1/README.md) and start with the Module 1 lesson.
3. In each module, complete the lesson, Lab, and Quiz in that order. Run the Labs in module order; Quizzes do not require a database.

The materials explain the content in English, keeping SQL and product names unchanged.
Lessons explain “why,” Labs show “how,” and Quizzes help you check your understanding.

## Learning Path

| Stage | Questions You Will Address | Learning Outcomes |
| --- | --- | --- |
| [Level 1: Ingestion, Cleaning, and Updates](level1/README.md) | How does data enter the warehouse, and how are errors and changes handled? | Explain order inputs, quality results, current state, and history |
| [Level 2: Modeling, Analytics, and Service Delivery](level2/README.md) | How is data organized and delivered to the business? | Layered modeling, JOINs, metric processing, and dashboards |
| [Level 3: Permissions, Resources, and Operations](level3/README.md) | How do you manage multiple users and ongoing operation? | Access governance, resource control, and operations and maintenance |

The course uses historical WWI business data and separate simulated new orders; no paid data services are required.
Module 1 starts with ten historical WWI orders downloaded into the local runtime cache; Module 5 imports the complete 10-table Parquet package;
Modules 6 and 7 handle new orders referencing the same customers and products, covering quality, payments and refunds, and duplicate and out-of-order delivery.
Historical account receipts and simulated order payments are analyzed at their respective business grains. See [Dataset Documentation](datasets/README.md) for sources, licensing, and local data preparation.

## Install and Open the Course

Keep the entire repository; display and quiz functionality depend on shared components within it.
Run the following from this course directory:

As in Course 01, copy the credential template once and fill in the two values in
your local `course_secrets.env` before downloading datasets:

```bash
cp -n course_secrets.env.example course_secrets.env
```

Keep both values empty in the committed `course_secrets.env.example`.
The runtime reads `course_secrets.env`, which is ignored by Git.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/jupyter lab level1/module01-introduction/lab1_connect_and_query.ipynb
```

Start Docker first, then initialize the tools and start the course's single-container sandbox in Lab 1; read the lab table reset notice before running it.
Subsequent Labs automatically connect to the same sandbox, without requiring you to select the environment again or enter a connection address.
Do not put passwords in Notebooks; see [Environment Setup](environments/single-node/README.md) for details.

## Course and Lab Plan

Level 1 provides seven modules, each containing a lesson, a Lab, and five interactive quiz questions.

| Lab | Required Environment and Data |
| --- | --- |
| Modules 1–3 | Course single-container sandbox and the ten-order sample downloaded from the course bucket |
| Module 4 | Sandbox; local Iceberg lake table environment automatically prepared by the Lab |
| Module 5 | Sandbox, historical Parquet archive and simulated CSV downloaded from the course bucket |
| Modules 6–7 | Sandbox and tables produced by the previous module, simulated events downloaded from the course bucket |

The course image is apache/doris:all-in-one-4.1.3. The Module 5 Lab practices Stream Load,
while the lesson also introduces the use cases and workings of continuous ingestion with Kafka, CDC, and object storage.
The optional [Lab 5A: Kafka / Routine Load](level1/module05-ingestion/optional5_kafka_routine_load.ipynb) and
[Lab 5B: MySQL / Flink CDC](level1/module05-ingestion/optional5_flink_mysql_cdc.ipynb) provide real pipelines you can start;
see [Continuous Ingestion Environment](environments/streaming/README.md) for prerequisites, separate data, and shutdown instructions. They do not change the completion requirements for the seven main Labs.
Module 4 starts two lake table helper containers on demand; see [Lake Table Environment](environments/lakehouse/README.md) for setup instructions.

## Maintainer Resources

[Course Maintenance Resources](../../maintenance/02-data-warehousing/README.md) document environment validation, testing methods, and integration lab preparation status.
