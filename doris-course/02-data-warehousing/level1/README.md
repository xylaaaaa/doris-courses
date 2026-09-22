# Level 1: Data Ingestion, Cleaning, and Updates

This stage starts with ten historical WWI orders and gradually answers three questions:
How does data enter Doris? How are invalid records identified? How do you keep analytical results correct when orders change?

**For your first pass, start with the [Module 1 lesson](module01-introduction/course1_introduction_to_apache_doris.md).**
You do not need to run all Notebooks or learn every architectural concept first.

## Learning Order

For each module, read the lesson first, then run the Lab, and finally complete the five interactive quiz questions.
Click “Lab” or “Quiz” in the table below to open its Notebook.

This course initially provides an English edition, with lessons organized in the following order:
Course Information → Module Goals → Learning Objectives → Module Plan → Section-by-Section Explanations →
Hands-on Lab → Module Summary → Knowledge Quiz → Official References.
SQL, APIs, and product names remain unchanged; the course topics and learning order follow the overall data warehousing outline.

| Order | Module and Business Questions | Hands-on Lab | Knowledge Quiz |
| --- | --- | --- | --- |
| Module 1 | [Introduction to Doris and Basic SQL](module01-introduction/course1_introduction_to_apache_doris.md) | [Lab 1](module01-introduction/lab1_connect_and_query.ipynb) | [Quiz 1](module01-introduction/quiz1_doris_fundamentals.ipynb) |
| Module 2 | [Doris Storage Architecture and Write Mechanisms](module02-architecture/course2_doris_architecture.md) | [Lab 2](module02-architecture/lab2_observe_storage.ipynb) | [Quiz 2](module02-architecture/quiz2_storage_and_write_batches.ipynb) |
| Module 3 | [Doris Table Models, Partitioning, and Bucketing](module03-table-design/course3_models_partitioning_and_bucketing.md) | [Lab 3](module03-table-design/lab3_models_and_pruning.ipynb) | [Quiz 3](module03-table-design/quiz3_models_and_data_distribution.ipynb) |
| Module 4 | [Querying External Data and Joining Lake Tables](module04-external-access/course4_querying_external_data.md) | [Lab 4](module04-external-access/lab4_query_iceberg.ipynb) | [Quiz 4](module04-external-access/quiz4_internal_files_and_lake_tables.ipynb) |
| Module 5 | [Batch and Continuous Data Ingestion](module05-ingestion/course5_batch_and_streaming_ingestion.md) | [Lab 5](module05-ingestion/lab5_stream_load.ipynb) | [Quiz 5](module05-ingestion/quiz5_load_methods_and_retry_safety.ipynb) |
| Module 6 | [Data Quality and Schema Validation](module06-data-quality/course6_data_quality_and_schema_validation.md) | [Lab 6](module06-data-quality/lab6_validate_orders.ipynb) | [Quiz 6](module06-data-quality/quiz6_data_quality_and_rejection.ipynb) |
| Module 7 | [Data Updates, Deletes, and Event Replay](module07-state-changes/course7_updates_deletes_and_replay.md) | [Lab 7](module07-state-changes/lab7_current_state_and_replay.ipynb) | [Quiz 7](module07-state-changes/quiz7_state_changes_and_replay.ipynb) |

Follow Modules 1–7 in order. Module 6 completes data quality validation, and Module 7 uses the valid orders to handle state changes and event replay.

## Completion Requirements

Complete the seven main Labs, independent exercises, and Quizzes. For Kafka, Flink CDC, CDC_STREAM, continuous file ingestion, and recovery from real source positions, you only need to understand the scenarios, architecture, configuration process, and caveats; you are not required to set up external pipelines. The three existing basic extension Notebooks and the two newly added continuous ingestion Labs are all optional; continuous concurrency validation is advanced material. Configuration-reading examples in the lessons and the fixed environments of the optional Labs are managed separately.

## Optional: Real Continuous Ingestion

After completing the main sequence, you can separately start the [Continuous Ingestion Environment](../environments/streaming/README.md):

| Lab | Content | Suggested Time |
|---|---|---|
| [Lab 5A: Kafka and Routine Load](module05-ingestion/optional5_kafka_routine_load.ipynb) | Send orders, inspect progress, pause to build a backlog, resume, and update | 25–40 minutes |
| [Lab 5B: MySQL and Flink CDC](module05-ingestion/optional5_flink_mysql_cdc.ipynb) | Single-table snapshot, inserts/deletes/updates, Checkpoint and Savepoint recovery; reusable in Module 7 | 35–50 minutes |

These two Labs use separate demonstration databases, do not change the main sequence's data baseline, and do not increase the video count. CDC_STREAM and continuous file ingestion remain introductory topics only.

## How Does Data Carry Through Level 1?

| Module | Data and Business Results |
| --- | --- |
| Modules 1–3 | Ten-order WWI projection, pre-tax amount 12220.60; querying, storage, models, and partitioning |
| Module 4 | Prepare the same WWI subset as a real Iceberg table and join it with internal customers |
| Module 5 | Import 10 simulated new orders first, then expand to 10 historical WWI tables with 701,846 rows |
| Module 6 | 13 simulated input rows → 10 valid, 3 rejected; validate WWI customer references |
| Module 7 | 11 current orders, 18 logical history records, 19 deliveries; reconcile products, payments, refunds, and shipping |

Historical business data is labeled WWI, and simulated new orders are labeled COURSE_SIMULATION; account receipts and per-order payments are each analyzed using their corresponding business data.

## How Are Lab Tables Named?

Table names describe the data's business meaning or lab purpose; module numbers are used only for course navigation.
For example, sample means a small sample, current means current state, and raw means the original input is retained.

| Table Name | Meaning |
| --- | --- |
| orders_sample | Sample of ten historical orders for introductory queries |
| orders_batch, orders_rowwise | Comparison tables holding the same orders written in batches and row by row, respectively |
| orders_duplicate, orders_unique, orders_aggregate | Lab tables for comparing the three table models |
| orders_partitioned | Order table for observing date partitioning and bucket pruning |
| orders_from_lake, customers_sample | Lake table import results and customer sample for joins |
| wwi_orders, wwi_customers, and other wwi_ tables | Ten complete historical business tables retaining their WWI provenance |
| orders_imported | Simulated new orders imported through Stream Load |
| orders_raw, orders_classified | Raw order inputs and a classification view with validation results |
| orders_clean, orders_rejected | Valid orders and rejected records |
| orders_current, order_events, event_deliveries | Current orders, business event history, and message delivery records |
| order_items, payments, refunds, shipment_events | Item details, payments, refunds, and shipment events |

customers and products are the customer and product dimensions extracted from historical WWI tables, respectively.
Partial update and delete exercises use orders_partial_update and orders_delete_demo,
without modifying the current orders table. Each Lab rebuilds only the tables it owns; tables depended on across modules are read-only.

## What Should You Prepare Before Starting?

- Be able to read basic SQL such as SELECT, WHERE, and GROUP BY.
- Install Python dependencies following [Environment Setup](../environments/single-node/README.md).
- Prepare Docker Desktop / Engine and the Compose plugin; the course uses a single-container Doris sandbox.
- Module 1 starts the sandbox; subsequent Labs automatically connect to the same environment. Read each Lab's table reset scope before running it.
- The WWI sample, complete historical archive, and simulated events are downloaded into the local runtime cache; see [Dataset Documentation](../datasets/README.md) for sources and business definitions.

## How Do You Complete a Lab?

1. Read each step's purpose and expected results, then run the code immediately following it.
2. Compare the actual results and explain what the amounts, states, and row counts each represent.
3. If results differ, inspect the details and execution order first; do not directly change the expected values.
4. Complete the tasks in the blank code cells under “Independent Exercise,” then expand the reference answers to check your work. Running all code does not complete the independent exercises for you.
5. Complete the five quiz questions to check your conceptual understanding and practical choices.

After restarting the kernel, rerun that Notebook's initialization and connection cells.
Course Labs rebuild only their own tables; the exact scope is stated at the beginning of each Lab.

## Which Parts Require Extra Preparation?

Running the Module 4 Lab starts two helper containers on demand to prepare real Iceberg lake tables.
The first start requires image downloads; see [Lake Table Environment](../environments/lakehouse/README.md) for ports and shutdown instructions.

The Module 5 Lab practices Stream Load using downloaded files in the local cache; the historical package is automatically extracted and validated on first read.
The Kafka, CDC, object storage, and Group Commit sections in the lesson teach ingestion choices and operating mechanisms.
Modules 2 and 3 use ten orders to explain storage and models; performance evaluation requires separately prepared data volumes and workloads appropriate to the evaluation.

Connections remain available after you finish a Lab, so you can continue querying. When you finish studying, shut down that Notebook's kernel to release the connections; course data in the database is retained.

## Supplementary Activities

After completing the main sequence, you can continue with the [Level 1 Extension Labs](extensions/README.md): scaling up data and Profile, batch file ingestion, defaults/generated columns, batch commit acknowledgment, schema changes, and deletes through ingestion. Extensions do not increase the video count; their dependencies and reset scopes are documented separately.
