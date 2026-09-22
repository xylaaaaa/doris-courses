# Module 5: Batch and Continuous Data Ingestion

| Course Information | Details |
| --- | --- |
| Course | Data Warehousing with Apache Doris · Level 1 |
| Product Version | Apache Doris 4.x |
| Lab Version | Apache Doris 4.1.3 |
| Estimated Time | About 110 minutes, including reading, hands-on work, and the quiz |

[Course contents](../README.md) · [Open Lab 5](lab5_stream_load.ipynb) · [Open Quiz 5](quiz5_load_methods_and_retry_safety.ipynb)

## Module Goal

This module introduces common data ingestion methods and the basics of checking load results and retrying loads.

After completing this module, you will be able to load order files with Stream Load, verify the results, and check how data changes after failures and retries.

**Scope:** Sections 5.6–5.9 are introductions taught through architecture diagrams, configuration examples, and the quiz. You do not need to set up Kafka, Flink, or real CDC/continuous-file pipelines. The main hands-on lab uses Stream Load; the existing object-storage batch and Group Commit extensions remain optional. Understanding the principles of recovery from actual source positions is required, but continuous concurrency validation is not a completion requirement. External configuration examples in the reading are not directly runnable labs.

**Optional labs:** [Lab 5A: Kafka / Routine Load](optional5_kafka_routine_load.ipynb) and [Lab 5B: MySQL / Flink CDC](optional5_flink_mysql_cdc.ipynb) provide isolated Docker environments and result checks. The latter practices snapshots, inserts, updates, deletes, and controlled savepoint restoration for a single table with a fixed schema; it is not whole-database synchronization, automatic schema evolution, or crash recovery. See the [continuous ingestion environment](../../environments/streaming/README.md) for prerequisites.

## Learning Objectives

After completing this module, you should be able to:

1. Choose ingestion paths for local files, object storage, message streams, and database changes.
2. Explain the roles of CSV column mappings, Parquet fields, and default values.
3. Judge correctness using load responses, loaded row counts, relationships, and amounts.
4. Distinguish load-batch retries, business-event deduplication, and continuous-job recovery.
5. Distinguish the grain and measurement definitions of WWI historical orders, account receipts, and new orders simulated for the course.

## Module Schedule

| Section | Learning Format | Suggested Time | Learning Outcome |
| --- | --- | --- | --- |
| 5.1 Decide whether to access or load | Ingestion selection table | 5 minutes | Choose an ingestion path by source and completion method |
| 5.2 Data types and schema | Field comparison | 5 minutes | Distinguish parseable data from valid business records |
| 5.3 Defaults and column mappings | Mapping and default examples | 8 minutes | Determine field order and the meaning of omitted fields |
| 5.4 Stream Load, result checks, and retries | Requests and responses | 5 minutes | Identify success, rejection, and uncertain states |
| 5.5 Object-storage batches and INSERT SELECT | SQL and workflow comparison | 8 minutes | Distinguish querying, persistence, and asynchronous loading |
| 5.6 Kafka and Routine Load | SQL and job workflow | 10 minutes | Explain consumption progress versus business state |
| 5.7 Flink CDC and Doris Connector | Change-flow diagram | 5 minutes | Explain snapshots, incremental changes, and recovery |
| 5.8 Streaming Job and CDC_STREAM | Synchronization SQL and mode selection | 8 minutes | Explain how Streaming Job, CDC_STREAM, and target tables work together |
| 5.9 Incremental files in object storage | Job SQL and file progress | 6 minutes | Identify duplicate-file and late-data issues |
| Lab 5 | Hands-on work | 45 minutes | Load ten WWI tables and check retries and rejection of simulated CSV data |
| Quiz 5 | Interactive quiz | 5 minutes | Check path selection, mappings, results, retries, and amount definitions |

## 5.1 Decide whether to access or load

### Choose an entry point by data source

Building a warehouse usually starts with historical data, followed by continuous changes. The file extension alone cannot determine the solution:
even for Parquet, local files, fixed file sets in object storage, and continually growing directories
require different transfer methods and progress management.

| Where data resides and how it is produced | Ingestion choice | Main checks |
| --- | --- | --- |
| Local CSV, JSON, or Parquet; one finite batch | Stream Load | Request results, loaded row counts, and target table |
| Fixed file set in object storage to inspect with SQL first | S3 TVF; combine with INSERT INTO SELECT when persisting to a table | Whether querying and writing each completed |
| Large file batches in object storage using asynchronous load jobs | Broker Load | Final load-job state and target data |
| Kafka continuously produces messages | Routine Load | Job state, committed progress, and target data |
| Business database with ongoing inserts, updates, and deletes | CDC path, such as Flink CDC + Doris Connector | Initial snapshot, incremental changes, and recovery position |
| Many very small write requests | Evaluate Group Commit for compatible write methods | Acknowledgment mode, response, and visibility |

These are paths to choose by need, not six steps that must run in sequence.
Direct queries in Module 4 can also avoid persisting data; whether to refresh a persisted table continuously is a separate decision.

### Historical business data and new orders

```text
WWI historical Parquet ─ Stream Load → wwi_* (10 business tables)
Simulated new-order CSV ─ Stream Load → orders_imported (10 teaching orders)
                                      │
                                      └─ Later: Module 6 admission checks, Module 7 state changes
```

The historical package retains orders, lines, customers, products, invoices, account transactions, and lookup tables, totaling 701,846 rows.
The “total row count” is the sum across ten tables, not the number of orders.
Simulated order IDs 900001–900010 reference WWI customers and products, but the course defines their prices, regions, and event times.

**Learning sequence:** Learn file loading, field mappings, and retries first, then continuous jobs and their progress.
This section explains three ingestion paths: files, messages, and database changes.
The lab starts with one CSV to practice Stream Load, load verification, and retries, then extends to ten historical Parquet tables.
The Kafka, Flink, and object-storage sections explain continuous ingestion choices and workflows.

## 5.2 Data types and schema

A schema defines a table's structure, including column names, types, and nullability.
Before loading, align file fields with this definition: order IDs identify orders, amounts support calculations,
and dates support daily summaries. Choose a field's type according to how it will be used.

For example, a pre-tax amount requiring two decimal places can use `DECIMAL(18, 2)`: 18 is the total number of digits,
and 2 is the number of decimal places. Both amount range and precision must meet business requirements. Order IDs can use integers;
fields that only need a calendar date can use DATE, while fields recording when an event occurred use DATETIME.
For nullable fields, define what NULL means, such as “payment time unknown,” to avoid confusing it with zero.
See [Data types](https://doris.apache.org/docs/4.x/table-design/data-type/) for range and precision rules.

### Convertible does not necessarily mean business-valid

| Field | Technical requirement | Business requirement |
| --- | --- | --- |
| order_id | Representable as an integer | Must exist, with one order as the grain |
| order_amount | Representable as a decimal with defined precision | Sign and business definition must be appropriate |
| customer_id | Representable as an integer | Customer must exist in the customer dimension table |
| event_time | Representable as a datetime | Represents business event time, not ingestion time |
| data_source | Representable as a string | Distinguishes WWI from COURSE_SIMULATION |

`not-a-number` cannot be loaded as an amount; customer ID `999999` can be converted to an integer,
yet may have no matching customer. The former is a type issue; the latter requires business relationship validation.
Module 6 retains the raw text and routes invalid records separately.

### When loading multiple tables, check orders and lines first

Each Orders row is an order; each OrderLines row is a product line.
Using COUNT(*) directly after a JOIN counts lines, not orders.
The main path in this module checks only the row counts, relationships, and amounts for orders, lines, customers, and products.
All ten tables are still loaded for later use; mastering the complete accounting model is not required here.
WWI customer transactions are at account level and cannot be directly allocated as per-order payments;
detailed SQL is in [Further reading: Invoices and account receipts](optional_invoice_and_receipts.md), which is not a required lab in this section.

After loading the historical tables, you can run the lab's date analysis:

```sql
SELECT o.OrderDate,
       COUNT(DISTINCT o.OrderID) AS orders,
       SUM(l.Quantity * l.UnitPrice) AS order_amount
FROM wwi_orders o
JOIN wwi_order_lines l ON o.OrderID = l.OrderID
GROUP BY o.OrderDate
ORDER BY o.OrderDate
LIMIT 10;
```

COUNT(DISTINCT) counts orders, while SUM calculates pre-tax amounts from lines.
This historical daily report does not cover the same scope as the ten-order subset in Module 1.

## 5.3 Defaults and column mappings

A CSV may put the customer ID before the order ID, while the Doris table defines fields in a different order.
Column mapping explicitly tells the load process what each input position means and which column receives it.
When all values convert successfully, an incorrect column order can silently swap order and customer IDs,
so also spot-check fields of individual orders after loading.

### Specify CSV order and align Parquet fields

The simulated CSV has no header. The lab explicitly supplies this column order:

```text
order_id,customer_id,order_amount,status,event_version,event_id,
event_time,paid_amount,refund_amount,region,data_source
```

`columns` describes how input values map to target columns; it does not ask Doris to guess each value's business meaning.
For this course's Parquet files, target tables use the field definitions in the manifest, not CSV comma-separator settings.

| Input | Format settings | Field interpretation |
| --- | --- | --- |
| Simulated orders.csv | format=csv, column_separator=comma | Explicit columns matching file order |
| WWI orders.parquet and others | format=parquet | File fields aligned with course DDL |

### Define defaults for omitted fields

A default specifies what to fill in when a write omits a column. For example, an entry point dedicated to new orders can define
CREATED as the initial state; an entry point receiving multiple order states should retain the source state.
A data-source field can also use the source identifier defined for that ingestion job.
Business facts such as payment success and actual payment amount must come from the source system.

**SQL reading example: not executed in the lab.** To try it, use an orders_defaults_reading table that does not yet exist
in an isolated lab database, and run it only once; do not write this example into orders_imported.

<!-- reading-only-example -->
```sql
CREATE TABLE orders_defaults_reading (
    order_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT "CREATED"
) DUPLICATE KEY(order_id)
DISTRIBUTED BY HASH(order_id) BUCKETS 1
PROPERTIES("replication_num"="1");
INSERT INTO orders_defaults_reading (order_id) VALUES (901001);
INSERT INTO orders_defaults_reading (order_id, status) VALUES (901002, 'PAID');
SELECT order_id, status FROM orders_defaults_reading ORDER BY order_id;
```

The first row omits status and produces `(901001, CREATED)`; the second explicitly supplies it and produces `(901002, PAID)`.
A default handles “this column was not supplied”; it does not correct arbitrary invalid values to CREATED.
This table only illustrates defaults and does not indicate that payment has been verified.

Column mappings can also transform values through expressions, for example by formatting source fields for target columns;
generated columns place calculation expressions in the table definition for the table to compute, with supported expressions depending on the target version.
Choose according to where the rule belongs: source-specific format conversion belongs in load mappings,
while derived fields maintained consistently with the table may suit generated columns. For example, if a source file records amounts in cents,
the load mapping can use `order_amount=amount_cents/100.0`; 18000 cents should produce 180.00 yuan,
with the target decimal type also configured. In contrast, a generated column is an expression in the table definition, independent of a particular CSV's column order.
This lab practices explicit field mappings; generated columns are not part of the lab operations.
See the [Stream Load documentation](https://doris.apache.org/docs/4.x/data-operate/import/import-way/stream-load-manual/) for configuration details and limits.

## 5.4 Stream Load, result checks, and retries

Stream Load sends file contents to Doris through an HTTP request.
Prepare the target table and file, send the request, and check the results using the returned load status.
It suits the local files in this section: the client pushes data, and Doris parses fields, checks data, and commits the load transaction.

### Understand the request components

This lab sends files directly to the course sandbox's BE HTTP address, where the BE receives data and participates in the load transaction.
Below, `DW_BE_HTTP_URL` is that address and `DW_DATABASE` is the target database.

The following placeholders illustrate the lab request structure:

```text
PUT <DW_BE_HTTP_URL>/api/<DW_DATABASE>/orders_imported/_stream_load
label: <unique identifier for this batch, retained for retries>
format: csv
column_separator: ,
columns: <column order from the previous section>
strict_mode: true
max_filter_ratio: 0
group_commit: off_mode
Request body: raw bytes of orders.csv
```

Historical Parquet uses format=parquet without a CSV separator.
Parameters determine parsing and data-quality handling; check the returned JSON for every request, not just the HTTP status.

The lab's first load shows the complete Python HTTP request: the URL selects the target table, headers correspond to the parameters above,
`requests.put(..., data=payload)` sends file bytes, and `response.json()` obtains the load result.
Later, `lab.stream_load()` wraps the repeated operations. The independent exercise uses the same request structure,
changing only the file, target table, batch label, and column mapping, without having to work out the HTTP request from scratch.

### Check both the response and table contents

The following illustrates fields to verify after successfully loading the ten simulated orders; it is not a complete response:

```json
{
  "Status": "Success",
  "NumberLoadedRows": 10,
  "NumberFilteredRows": 0
}
```

Then verify the business results:

```sql
SELECT COUNT(*) AS orders, SUM(order_amount) AS amount
FROM orders_imported;
```

Expect ten orders and 1400.00. For historical data, also check duplicate primary keys, customer/product relationships, and amounts,
because successful loads of all ten tables may still involve incorrect relationship definitions.

| Response scenario | Interpretation and next step |
| --- | --- |
| Success | Check loaded/filtered row counts, then verify the target table |
| Label Already Exists | Check the original batch's state; this does not mean another batch was successfully written |
| Fail | Retain error details, determine the rejection cause, and do not count the failed batch as business data |
| Publish Timeout or uncertain request result | Retain the label and transaction details and confirm the original transaction's outcome; do not blindly append with a new label |

### Retry protection is not permanent deduplication

The lab resends the same file with the same label within the label's retention period, expecting no additional ten rows.
A new label appends another batch to a Duplicate Key table; business deduplication still requires stable keys and versions.

The bad-data experiment uses a new label and two input rows, one with an amount that cannot be converted.
With this course's strict_mode=true and max_filter_ratio=0 settings, the entire batch should be rejected,
leaving the original ten rows and 1400.00 unchanged. ErrorURL is a troubleshooting clue, not a long-term rejection table.

If an application writes only a few rows at a time, frequent commits increase transaction and storage-version overhead.
Group Commit can combine compatible small writes into larger batches to reduce fixed per-batch overhead.
When choosing a mode, focus on when the application receives acknowledgment: `sync_mode` returns after the grouped load completes,
while `async_mode` returns after data is written to the WAL (write-ahead log); query visibility still waits for a subsequent commit.
This lab uses `off_mode` to make per-batch transaction results and label retry behavior easier to observe.
Before enabling grouped commits, check the parameters and label-support conditions for the interface used; see the [Group Commit documentation](https://doris.apache.org/docs/4.x/data-operate/import/load-best-practices/group-commit-manual/).

## 5.5 Object-storage batches and INSERT SELECT

If historical orders are already in S3 or compatible object storage, Doris can read the files directly.
Prepare file paths, formats, and read permissions, then decide whether to query and inspect first or submit a batch load job.

### Querying files and saving results are separate actions

```text
Fixed file set in object storage → S3 TVF → SELECT results
                                  │
                                  └─ INSERT INTO SELECT → Internal table
Fixed file set in object storage → Broker Load job ── Verify after completion → Internal table
```

A TVF (table-valued function) exposes files as a relation readable by SQL.
SELECT alone does not create a persistent internal table; INSERT INTO SELECT writes selected results into the target table.
Broker Load is asynchronous: acceptance of a submission does not mean the job has completed.

For example, with a month's order files, first use a TVF to inspect fields, date ranges, and total amounts,
then use INSERT INTO SELECT to select target columns and write them to an internal table. This SQL expresses reading, transformation, and persistence together.
With Broker Load, submit a job specifying paths, format, and target table, check that it reaches FINISHED,
then verify target data. The former expresses processing conveniently in SQL; the latter organizes batch loading as asynchronous jobs.

Before repeating an operation, determine whether the batch should be appended, updated by key, or used to rebuild a specified range.
For example, appending the same month's files to a detail table again double-counts sales;
the retry strategy must consider both the load job and the target table model.
See [Broker Load](https://doris.apache.org/docs/4.x/data-operate/import/import-way/broker-load-manual/) for operations.

### Reading example: inspect files, then persist to a table

**External-environment example; not executed in the lab.** This section and the later Kafka and CDC examples use separate demonstration tables,
not the main orders_imported table. Before running them, switch to an isolated lab database, prepare external services,
and replace angle-bracket placeholders. Addresses must be reachable by Doris nodes; do not simply copy localhost from the notebook's machine.
Use credentials supplied by the lab environment; do not save real secrets in the reading or notebooks.

Assume a Parquet file you prepare has only order_id and order_amount, containing
`(901001, 180.00)` and `(901002, 80.00)`. This is not the complete WWI file in the repository.
First create an empty detail table, then write from the file:

<!-- external-service-example -->
```sql
CREATE TABLE orders_s3_demo (
    order_id BIGINT, order_amount DECIMAL(18,2)
) DUPLICATE KEY(order_id)
DISTRIBUTED BY HASH(order_id) BUCKETS 1
PROPERTIES("replication_num"="1");

INSERT INTO orders_s3_demo (order_id, order_amount)
SELECT order_id, order_amount FROM S3(
    "uri"="s3://<bucket>/batch/orders.parquet",
    "s3.endpoint"="<endpoint>", "s3.region"="<region>",
    "s3.access_key"="<access_key>", "s3.secret_key"="<secret_key>",
    "format"="parquet"
);
SELECT COUNT(*) AS orders, SUM(order_amount) AS amount FROM orders_s3_demo;
```

Read and perform this in three steps:

1. First run `SELECT ... FROM S3(...)` alone. Expect two file records, while the internal table remains empty.
2. Then run the complete INSERT INTO SELECT to write these two columns into the internal table; uri selects the file and format specifies how to parse it.
3. Expect 2 and 260.00 from the final query. Do not run INSERT again to “confirm success,” or the detail table will append the same records again.

For S3 TVF parameters, see
[S3 TVF](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/table-valued-functions/s3/)。

## 5.6 Kafka and Routine Load

When upstream systems continually produce order messages, you cannot wait for “the entire file to be ready” before loading.
Kafka stores continuously arriving messages; Routine Load is a continuous consumption job created in Doris:
it reads from a specified Topic, writes batches into the target table, and maintains consumption progress.

### Continuous jobs must save progress

```text
Business producer → Kafka Topic / Partition
                         │ Continuous consumption
                         ▼
                  Routine Load Job
                         │ Write batches and advance consumption progress
                         ▼
                    Doris target table
```

A Topic is a collection of messages; Partitions divide it, and offsets identify positions within each partition.
For example, if a partition has order messages at positions 100 and 101, after the job writes this batch and commits progress,
it continues with subsequent messages. If Kafka has produced many new messages at the next check but job progress has stalled for a long time,
inspect pause reasons, error records, or processing capacity.
Each Partition has its own position numbering; offsets from different partitions cannot establish business-event order.
The job consumes continuously; monitor job state and pause reasons along with committed progress, error rows, and target data.
Pausing, resuming, and stopping a job concern its lifecycle, not starting or stopping the Doris cluster.

offset answers “how far has consumption reached,” while business event_version answers “which version of the same order is newer.”
For example, consuming a delivery-confirmation event before a late payment event advances consumption progress but should not roll back the order state.
Module 7 further explains version resolution using order events. For job parameters and management, see
[Routine Load](https://doris.apache.org/docs/4.x/data-operate/import/import-way/routine-load-manual/)。

### Reading example: after creating a job, check consumption results

**External-environment example; not executed in the lab.** Prepare a dedicated Kafka Topic and send only two headerless CSV messages:
`901001,180.00` and `901002,80.00`. The following maps the first and second columns to order ID and amount:

<!-- external-service-example -->
```sql
CREATE TABLE orders_kafka_demo (
    order_id BIGINT, order_amount DECIMAL(18,2)
) DUPLICATE KEY(order_id)
DISTRIBUTED BY HASH(order_id) BUCKETS 1
PROPERTIES("replication_num"="1");

CREATE ROUTINE LOAD orders_kafka_job ON orders_kafka_demo
COLUMNS TERMINATED BY ",",
COLUMNS(order_id, order_amount)
PROPERTIES("strict_mode"="true", "max_filter_ratio"="0", "max_error_number"="0")
FROM KAFKA(
    "kafka_broker_list"="<broker>:9092",
    "kafka_topic"="<dedicated_topic>",
    "property.kafka_default_offsets"="OFFSET_BEGINNING"
);
SHOW ROUTINE LOAD FOR orders_kafka_job;
SELECT COUNT(*) AS orders, SUM(order_amount) AS amount FROM orders_kafka_demo;
```

`OFFSET_BEGINNING` makes a new job start at the beginning of each partition; it does not restart every batch from the beginning.
After both messages are committed, the empty table should contain 2 rows totaling 260.00; the job continues waiting for new messages rather than ending when the current Topic is exhausted.
Inspect State, Progress, and Statistic in SHOW results; if paused, check ReasonOfStateChanged and ErrorLogUrls.
Do not recreate the job instead of resuming normally, as that may consume old messages again. See the official Routine Load documentation above for operational fields.
After observing, pause with `PAUSE ROUTINE LOAD FOR orders_kafka_job`,
and resume with `RESUME ROUTINE LOAD FOR orders_kafka_job` when continuing.

## 5.7 Flink CDC and Doris Connector

### From business database logs to the warehouse

CDC (Change Data Capture) reads committed inserts, updates, and deletes from a business database.
For example, when an order changes from CREATED to PAID, CDC sends the change downstream so the warehouse can update that order.
Flink CDC reads source data and changes, which a Flink job can further process;
Doris Connector writes the processed results into Doris.

```text
Source business database: initial snapshot + subsequent change logs
                 │
                 ▼
            Flink CDC
       Process changes and maintain recovery state
                 │ Doris Connector
                 ▼
              Doris table
```

When connecting an existing order database, typically read an initial snapshot to establish existing order states, then transition to subsequent change logs.
During execution, the job records checkpoints that save read positions and processing state for recovery.
After a failure, the job recovers from a checkpoint; source logs must also be retained back to the position needed for recovery.

An UPDATE in the source usually becomes a new state for the same primary key in Doris;
the connector must also convey DELETE semantics so the target table correctly removes the corresponding logical row.
Therefore, verify the source primary key, target Unique Key, and connector update/delete configuration together,
and check synchronization using changes to the same order, such as creation, payment, and cancellation.

When choosing this path, check Flink, CDC, Connector, and database versions together,
then test inserts, updates, deletes, and recovery after interruption.
For configuration, see [Flink Doris Connector](https://doris.apache.org/docs/4.x/connection-integration/data-integration/flink-doris-connector/).

## 5.8 Streaming Job and CDC_STREAM

**Version and scope:** This section introduces continuous synchronization available from Doris 4.1; the official documentation marks MySQL and PostgreSQL
capabilities as Experimental. The following single-table MySQL example is not executed in the lab;
before running it, prepare the source database, driver, and synchronization permissions for the target patch version.
[MySQL SQL-mapped synchronization](https://doris.apache.org/docs/4.x/data-operate/import/import-way/streaming-job/continuous-load-mysql-table/)

### How does this differ from the Flink path?

Both paths handle the previous section's “snapshot → incremental changes → recovery.” The difference is what orchestrates synchronization:
the Flink path runs as an external Flink job; here, a Streaming Job is created in Doris,
reading the source through the CDC_STREAM table-valued function and writing to the target through SQL mappings.

```text
MySQL existing orders and Binlog → CDC_STREAM → SELECT field mappings → Doris Unique Key table
                         └──── Streaming Job orchestrates continuous execution and records progress ────┘
```

| Component | Responsibility | What to provide in this example |
| --- | --- | --- |
| CDC_STREAM | Read source data and changes | JDBC URL, driver, account, source database, and source table |
| SELECT / INSERT INTO | Map fields and select the target | order_id, status, and the pre-created target table |
| Streaming Job | Orchestrate continuous execution and save progress | Job name, starting position, and runtime configuration |

`CREATE JOB ... ON STREAMING` creates a continuous job;
`INSERT INTO ... SELECT ... FROM CDC_STREAM(...)` describes how read results are persisted.
SQL mapping mode requires a pre-created Unique Key target table; verify source-delete propagation and primary-key mappings as well.
[CDC_STREAM](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/table-valued-functions/cdc-stream/)

### How should you choose the starting position and synchronization scope?

- `offset="initial"`: read existing orders first, then transition to incremental changes.
- `offset="latest"`: receive only changes after startup, without backfilling earlier orders.
- Use this example's SQL mapping mode when a single table requires column selection, renaming, or type conversion.
- For a group of tables following the source structure, evaluate automatic table-creation synchronization with `FROM MYSQL (...) TO DATABASE ...`.
  Initial table creation and subsequent schema changes are separate concerns; do not assume every change is automatically compatible.
  [Automatic table-creation synchronization](https://doris.apache.org/docs/4.x/data-operate/import/import-way/streaming-job/continuous-load-mysql-database/)

Before starting, verify MySQL row-based Binlog, the synchronization account, JDBC driver, source table, and target primary key;
source logs must be retained back to the position needed for recovery. Job progress answers “how far synchronization has reached,”
while Module 7's business-version rules answer “which state of the same order is newer.” Check both against target data.

### Reading example: relate the configuration to one order

**External-environment example; not executed in the lab.** Prepare MySQL and the driver as described above; source table demo.orders
contains primary key order_id and status, initially holding only `(901001, 'CREATED')`.
First create a target table at the same grain in Doris, then create the synchronization job:

<!-- external-service-example -->
```sql
CREATE TABLE orders_cdc_demo (
    order_id BIGINT NOT NULL, status VARCHAR(20)
) UNIQUE KEY(order_id)
DISTRIBUTED BY HASH(order_id) BUCKETS 1
PROPERTIES("replication_num"="1", "enable_unique_key_merge_on_write"="true");

CREATE JOB orders_mysql_job ON STREAMING DO
INSERT INTO orders_cdc_demo (order_id, status)
SELECT order_id, status FROM CDC_STREAM(
    "type"="mysql", "jdbc_url"="jdbc:mysql://<mysql_host>:3306",
    "driver_url"="<driver_jar_url>", "driver_class"="com.mysql.cj.jdbc.Driver",
    "user"="<sync_user>", "password"="<sync_password>",
    "database"="demo", "table"="orders", "offset"="initial"
);
SELECT * FROM jobs("type"="insert")
WHERE ExecuteType = 'STREAMING' AND Name = 'orders_mysql_job';
SELECT order_id, status FROM orders_cdc_demo ORDER BY order_id;
```

Observe “initialize → generate changes → verify results”: first wait for CREATED to appear in the target table,
then change the same order to PAID in MySQL, wait for synchronization, and query Doris. Expect one row still, now with status PAID.
`offset=initial` determines the snapshot-to-incremental transition, the two SELECT columns determine the mapping, and Unique Key determines target-row identity.
Observe state and progress in jobs(), but use the final order query to confirm that the business change has arrived.
For this reading example's version prerequisites and configuration, see
[MySQL SQL-mapped synchronization](https://doris.apache.org/docs/4.x/data-operate/import/import-way/streaming-job/continuous-load-mysql-table/).
After observing, pause with `PAUSE JOB WHERE jobName = 'orders_mysql_job'`,
and resume with `RESUME JOB WHERE jobName = 'orders_mysql_job'` when continuing.
For operation syntax, see [Continuous load job management](https://doris.apache.org/docs/4.x/data-operate/import/import-way/streaming-job/continuous-load-overview/).

## 5.9 Incremental files in object storage

### Discovering new files is also a progress problem

A fixed file set is finished once loaded; a continuous directory keeps gaining files.
The official Streaming Job + S3 TVF path addresses the latter need;
a regular S3 query alone is not a continuous job.

| Scenario | Handling |
| --- | --- |
| orders-001.parquet appears at 09:00 | Read the file and record file-processing progress |
| orders-002.parquet appears at 09:05 | Its filename is greater than the processed position; read it as a new file |
| orders-000.parquet appears only at 09:10 | Its filename is less than the processed position; arrange a separate backfill |

This path identifies new files by lexicographic filename order: a new filename must be greater than the last loaded filename.
Upstream systems can use fixed-width, increasing batch numbers to keep publication order aligned with filename order.
A late order's business date may be yesterday, but its new file should still use an increasing publication number.

The job's `CurrentOffset` indicates the file processed so far, and `EndOffset` indicates the end position of this batch.
When investigating “the file arrived but is not in the table,” first compare its filename with these two positions, then check path matching, job errors, and target orders.
Overwriting a file with the same name should not be treated as a new publication batch. For rules and parameters, see
[Continuous loading from object storage](https://doris.apache.org/docs/4.x/data-operate/import/import-way/streaming-job/continuous-load-s3/).

### Reading example: add a continuous job to a file query

**External-environment example; not executed in the lab.** Reuse the two-column file structure from 5.5, create another empty table,
and use a dedicated directory containing only incremental files; do not point to a historical directory already batch-loaded.

<!-- external-service-example -->
```sql
CREATE TABLE orders_files_demo LIKE orders_s3_demo;
CREATE JOB orders_files_job ON STREAMING DO
INSERT INTO orders_files_demo (order_id, order_amount)
SELECT order_id, order_amount FROM S3(
    "uri"="s3://<bucket>/incremental/orders-*.parquet",
    "s3.endpoint"="<endpoint>", "s3.region"="<region>",
    "s3.access_key"="<access_key>", "s3.secret_key"="<secret_key>",
    "format"="parquet"
);
SELECT * FROM jobs("type"="insert")
WHERE ExecuteType = 'STREAMING' AND Name = 'orders_files_job';
SELECT order_id, order_amount FROM orders_files_demo ORDER BY order_id;
```

First publish orders-001.parquet containing only `(901001, 180.00)`, then wait for CurrentOffset to advance and the row to appear;
next publish orders-002.parquet containing only `(901002, 80.00)`. Expect two rows totaling 260.00.
Unlike 5.5, CREATE JOB keeps the file query running continuously; there is no need to repeat INSERT manually.
If orders-000.parquet is published afterward, it will not be read as a new file under this section's rules; arrange a separate backfill.
See the object-storage continuous-loading documentation above for job syntax and progress fields.
After observing, also pause this job with `PAUSE JOB WHERE jobName = 'orders_files_job'` to avoid consuming subsequent files.

## Hands-on Lab 5: Batch loading, failures, and retries

Before starting, complete the relevant concepts from Modules 1–4 and keep the course sandbox running; the tools automatically configure the BE HTTP address in the same container, continuing to use the isolated course lab database.

Open [Lab 5](lab5_stream_load.ipynb) and complete these steps in order:

1. Load the simulated new-order CSV, inspect the response, and verify ten rows and 1400.00.
2. Retry the same batch within the label's retention period, then observe rejection of the invalid batch.
3. Extend the same ingestion method to ten WWI historical Parquet tables, checking primary keys, relationships, and amounts.
4. Independently map columns for a new CSV and verify order IDs, customer IDs, and amounts.

### Data sources and notes

Historical data comes from Microsoft WWI; new orders and changes are marked COURSE_SIMULATION, referencing WWI customers and products without backfilling history.
See the [Data guide](../../datasets/README.md) for fields, business definitions, and expected results.

See [Level 1 extension labs](../extensions/README.md) for additional operations, performed in separate `ext_*` tables without repeatedly modifying this lab's business results.

## Module Summary

- Choose ingestion paths by source, batch versus continuous operation, and completion method; Stream Load, S3 TVF, Routine Load, and CDC are not a fixed pipeline.
- CSV requires explicit column order and separators; Parquet requires fields aligned with DDL. Defaults cannot invent business facts such as payments.
- Check load transactions and loaded/filtered row counts first, then query target details, relationships, and amounts; HTTP success is insufficient.
- The same label identifies same-batch requests within a limited period, business keys identify events, and job progress supports recovery; none replaces the others.
- Historical order lines, account receipts, and simulated orders have different grains and sources; preserve WWI history rather than forcing account receipts onto individual orders.

## Knowledge Quiz 5: Batch loading, failures, and retries

After completing the reading and lab, open [Quiz 5](quiz5_load_methods_and_retry_safety.ipynb).
The quiz has five single-choice questions and requires neither Doris nor external services; read the explanations after submitting.

## Official References

- [Data loading overview](https://doris.apache.org/docs/4.x/data-operate/import/load-manual/)
- [Stream Load](https://doris.apache.org/docs/4.x/data-operate/import/import-way/stream-load-manual/)
- [S3 file table-valued function](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/table-valued-functions/s3/)
- [INSERT INTO SELECT](https://doris.apache.org/docs/4.x/data-operate/import/import-way/insert-into-manual/)
- [Broker Load](https://doris.apache.org/docs/4.x/data-operate/import/import-way/broker-load-manual/)
- [Routine Load](https://doris.apache.org/docs/4.x/data-operate/import/import-way/routine-load-manual/)
- [Group Commit](https://doris.apache.org/docs/4.x/data-operate/import/load-best-practices/group-commit-manual/)
- [Flink Doris Connector](https://doris.apache.org/docs/4.x/connection-integration/data-integration/flink-doris-connector/)
- [CREATE STREAMING JOB](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/job/CREATE-STREAMING-JOB/)
- [CDC_STREAM table-valued function](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/table-valued-functions/cdc-stream/)
- [MySQL single-table SQL-mapped synchronization](https://doris.apache.org/docs/4.x/data-operate/import/import-way/streaming-job/continuous-load-mysql-table/)
- [MySQL automatic table-creation synchronization](https://doris.apache.org/docs/4.x/data-operate/import/import-way/streaming-job/continuous-load-mysql-database/)
- [Continuous loading from object storage](https://doris.apache.org/docs/4.x/data-operate/import/import-way/streaming-job/continuous-load-s3/)
