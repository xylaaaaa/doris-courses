# Module 4: Joining lake tables and internal tables

| Course Information | Details |
| --- | --- |
| Course | Data Warehousing with Apache Doris · Level 1 |
| Product Version | Apache Doris 4.x |
| Lab Version | Apache Doris 4.1.3 |
| Estimated Time | About 50 minutes, including reading, the hands-on lab, and quiz |

[Course contents](../README.md) · [Open Lab 4](lab4_query_iceberg.ipynb) · [Open Quiz 4](quiz4_internal_files_and_lake_tables.ipynb)

## Module Goal

This module introduces the differences between internal tables, external files, and lake tables, and how to access existing lake tables through Doris.

Once the Iceberg environment is ready, you will be able to query orders in the lake, join internal tables, and verify results before and after loading.

## Learning Objectives

After completing this module, you should be able to:

1. Distinguish Doris internal tables, Parquet files, Iceberg tables, and External Catalogs.
2. Choose between direct external queries and loading into internal tables based on exploration and repeated-analysis needs.
3. Explain how Catalog, Database, and Table identify an external table.
4. Identify duplicate dimension records or missing matches by comparing results before and after a join.
5. With an Iceberg environment available, verify the same batch of orders through direct queries, joins, and after loading.

## Module Schedule

| Section | Learning Format | Suggested Time | Learning Outcome |
| --- | --- | --- | --- |
| 4.1 Querying internal tables, external files, and lake tables | Objects, configuration, and SQL | 15 minutes | Distinguish access paths and explain the boundaries of JOIN and loading |
| Lab 4 | Hands-on practice (requires Iceberg) | 30 minutes | Verify that direct queries, joins, and loading all yield ten orders and 12220.60 |
| Quiz 4 | Interactive quiz | 5 minutes | Check objects, access choices, table identification, and join results |

## 4.1 Querying internal tables, external files, and lake tables

### First distinguish files, tables, and access entry points

Suppose historical orders are already stored in a data lake, while recent customer information is in Doris.
Analysts want to query them together without migrating all historical data just to explore one question.
First distinguish these four types of objects:

| Object | What it manages | Relationship to other objects |
| --- | --- | --- |
| Doris internal table | Table schemas and data managed by Doris | Can serve as an analytical table after loading |
| Parquet file | A column-encoded data file | Can be read independently or serve as a lake table's data file |
| Iceberg table | Table metadata, snapshots, and referenced data files | Uses table metadata to determine which files a query reads |
| External Catalog | An entry point for Doris to access external system metadata and tables | Makes external tables queryable through Doris SQL |

Parquet describes the columns and data within a file; Iceberg organizes multiple files into a manageable table.
A snapshot records the data files referenced by a particular version of a table. When the table changes, metadata describes the new table state,
which readers use to select files. Querying an Iceberg table therefore requires access to both its metadata and data files.

An External Catalog tells Doris where to find the table: after the metadata service connection and permissions are configured,
Doris can retrieve the schema, plan reads, access the corresponding files, and perform filtering, joins, and aggregation.
When configuring a Catalog, check access permissions for both the metadata service and file storage.
For specific connection types, see [Iceberg Catalog](https://doris.apache.org/docs/4.x/lakehouse/catalogs/iceberg-catalog/).

```text
Standalone Parquet ── File TVF ──────────┐
                                 ├─ SQL query results
Iceberg metadata and data files ─ Catalog ┘      │
                                       └─ INSERT INTO ... SELECT
                                                  │
                                                  ▼
                                             Doris internal table
```

### When should you query directly, and when should you load?

| Scenario | Initial choice | Other considerations |
| --- | --- | --- |
| First exploration of historical data | Query directly through a Catalog | Availability of external services, network, permissions, and metadata |
| Join historical lake data with internal customers | Cross-Catalog JOIN | Whether join keys are unique and any customers are missing |
| Repeatedly query the same business snapshot | Load into an internal table for analysis | Synchronization frequency, storage cost, and how changes are applied |
| Inspect a single standalone file | File TVF | File format, fields, and access parameters |

"Query directly first" is an access choice, not a guarantee that all external queries are equally fast;
"loading" saves the results of this query; it does not automatically create an ongoing synchronization task.
Object-storage access through a file TVF is introduced in Module 5; this lab does not include a standalone-file experiment.

### Which two types of addresses must be configured to connect to lake tables?

The lab setup tool creates the Catalog automatically. The same REST connection configuration is shown below to explain what the tool does.
**External environment example; do not rerun it alongside the lab.** Names and connection parameters are placeholders; the lab actually uses the lab database name
to generate a separate Catalog, and the returned source is the entry point for this query. Do not create another entry point and mix up table names.

<!-- external-service-example -->
```sql
CREATE CATALOG <catalog_name> PROPERTIES (
    "type"="iceberg", "iceberg.catalog.type"="rest",
    "iceberg.rest.uri"="<rest_service_url>",
    "warehouse"="s3://<warehouse_bucket>/",
    "s3.endpoint"="<object_storage_url>", "s3.region"="us-east-1",
    "s3.access_key"="<access_key>", "s3.secret_key"="<secret_key>",
    "use_path_style"="true", "iceberg.rest.view-enabled"="false"
);
```

| Configuration | Purpose in this course |
| --- | --- |
| type, iceberg.catalog.type | Select the Iceberg table format and REST metadata service |
| iceberg.rest.uri | Find tables, snapshots, and file lists through the metadata service |
| warehouse | Object-storage location used by the course sample; must match the REST service configuration |
| s3.endpoint, region, access credentials | Allow Doris nodes to read the actual data files |
| use_path_style | Match the course MinIO path-style access |
| iceberg.rest.view-enabled | Disable external view support because this lab uses only lake tables |

The service addresses on the course container network are `http://course-lake-rest:8181` and
`http://course-lake-minio:9000`, not localhost on the host running the notebook.
If you can retrieve the table definition but cannot read orders, check the metadata and file entry points separately.
Configure credentials only in the lab environment; do not put real secrets in the course notes.

### How does a Catalog identify an external table?

The fully qualified table name is `catalog.database.table`. For example, a lake table can be registered as
`wwi_lake.sales.orders`: wwi_lake is the Catalog name in Doris, sales is the external database,
and orders is the lake table. This is not a Parquet file path.

The following illustrates the query structure; use the actual fully qualified table name when running it.
After preparing the lake table, the course notebook saves its fully qualified name in the `source` variable for subsequent queries to reference directly.

```sql
SELECT order_date, COUNT(*) AS sample_orders, SUM(order_amount) AS amount
FROM wwi_lake.sales.orders
GROUP BY order_date
ORDER BY order_date;
```

If the external table contains this course's ten-order projection, expect five orders and 3944.20 on the first day,
and five orders and 8276.40 on the second day. This queries the external table; no data has been written to a Doris internal table yet.

### Why count rows after a JOIN?

If a customer has two dimension-table records, an order for 100.00 may produce two joined rows,
totaling 200.00 after aggregation. Correct JOIN syntax does not guarantee correct business amounts.
Conversely, a missing customer can cause an order to disappear in an inner join.

```text
Order: order_id=1, customer_id=832, amount=2300.00
          │ Join on customer_id
          ├─ Customer row A → One order result
          └─ Customer row B → Another order result (duplicate)
```

The diagram uses duplicate customers to illustrate join fanout. The lab uses a unique-key customer table so each order matches at most one customer record;
then it checks row counts and amounts before and after the join, and compares results field by field after loading.

LEFT JOIN retains the orders on the left; orders with no matching customer still appear, with NULL customer fields;
INNER JOIN retains only matched orders. When reconciling all orders, first use LEFT JOIN to identify missing customers
to avoid misinterpreting "fewer orders after the join" as a decline in business volume.

After completing the external lab, run the following query in the course's internal lab database to check again for missing join matches:

```sql
SELECT COUNT(*) AS missing_customers
FROM orders_from_lake o
LEFT JOIN customers_sample c ON o.customer_id = c.customer_id
WHERE c.customer_id IS NULL;
```

The expected result is 0; otherwise, check customer keys and the data scope first rather than treating an aggregate with missing orders as a complete answer.

### What should you check after loading?

The lab explicitly selects six fields to write into `orders_from_lake`, rather than relying on the implicit order of external fields.
After the query results have been loaded into the internal table, run:

```sql
SELECT order_date, COUNT(*) AS sample_orders, SUM(order_amount) AS amount
FROM orders_from_lake
GROUP BY order_date
ORDER BY order_date;
```

This result should match a direct query of the lake table; also compare order IDs, customers, dates, amounts, line counts, and sources
to avoid different errors canceling each other out in the aggregate.

**Lab requirements:** The course Doris instance is running, and Docker is available. The lab starts MinIO and Iceberg REST Catalog
as two auxiliary containers and prepares the sample; see the [lake table environment notes](../../environments/lakehouse/README.md) for ports and data retention.

## Hands-on Lab 4: Joining lake tables and internal tables

Before starting, complete Module 1–3 and continue using the course's isolated lab database.

Open [Lab 4](lab4_query_iceberg.ipynb) and complete these steps in order:

1. Run the setup step to start the lake table services and obtain the actual Iceberg table name.
2. Query the ten orders in the lake directly and verify the amount of 12220.60.
3. Join the internal customer table and check the row count, then load into an internal orders table for reconciliation.

### Data sources and notes

The lab uses a historical subset of Microsoft's official WWI simulated wholesale business, retaining the original customer and product identifiers.
See the [data notes](../../datasets/README.md) for fields, business definitions, and expected results.
The setup step writes the six fields and ten rows from orders in the downloaded sample.json into an Iceberg table; the data files are stored in the course object storage.

See the [Level 1 extension labs](../extensions/README.md) for additional exercises, run in separate `ext_*` tables without rewriting this lab's business results.

## Module Summary

- Parquet is a file format, Iceberg is a table format that manages snapshots and files, and an External Catalog is an access entry point, not data replication.
- Start with direct queries for exploration and consider loading for repeated analysis; refreshing and handling changes after loading still require an explicit design.
- catalog.database.table identifies an external table; the notebook uses the fully qualified name returned by the setup step.
- Duplicate dimension keys multiply JOIN results, while missing keys drop rows from inner joins; check row counts, amounts, and detail records together.
- Verify direct lake-table queries, join results, and the internal table after loading separately; this sample has ten orders and a pre-tax amount of 12220.60 in each case.

## Knowledge Quiz 4: Joining lake tables and internal tables

After completing the reading and lab, open [Quiz 4](quiz4_internal_files_and_lake_tables.ipynb).
The quiz contains five single-choice questions and does not require Doris or external services; read the answer explanations after submitting.

## Official References

- [Data catalog overview](https://doris.apache.org/docs/4.x/lakehouse/catalog-overview/)
- [Iceberg Catalog](https://doris.apache.org/docs/4.x/lakehouse/catalogs/iceberg-catalog/)
- [S3 file table-valued function](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/table-valued-functions/s3/)
- [INSERT INTO SELECT](https://doris.apache.org/docs/4.x/data-operate/import/import-way/insert-into-manual/)
