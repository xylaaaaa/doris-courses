# Module 3: Doris table models, partitioning, and bucketing

| Course Information | Details |
| --- | --- |
| Course | Data Warehousing with Apache Doris · Level 1 |
| Product Version | Apache Doris 4.x |
| Lab Version | Apache Doris 4.1.3 |
| Estimated Time | About 55 minutes, including reading, the hands-on lab, and quiz |

[Course contents](../README.md) · [Open Lab 3](lab3_models_and_pruning.ipynb) · [Open Quiz 3](quiz3_models_and_data_distribution.ipynb)

## Module Goal

This module introduces the three Doris table models and the roles of partitioning and bucketing.

After completing this module, you will be able to compare how different models handle duplicate keys and use EXPLAIN to inspect query scan ranges.

## Learning Objectives

After completing this module, you should be able to:

1. Predict the results of the same input in the Duplicate, Unique, and Aggregate models.
2. Choose logical keys and table models for detail records, current state, or aggregate metrics.
3. Distinguish the roles of partitions, buckets, sort keys, and business unique keys.
4. Use EXPLAIN to compare scan ranges with date filters and bucket-key filters.
5. Verify results using both detail records and amounts, without equating plan pruning with performance gains.

## Module Schedule

| Section | Learning Format | Suggested Time | Learning Outcome |
| --- | --- | --- | --- |
| 3.1 Doris Key Model | Compare input and results | 10 minutes | Choose models for detail records, current state, and aggregates |
| 3.2 Partitioning, bucketing, and data distribution | DDL and query plans | 15 minutes | Distinguish physical organization from logical uniqueness |
| Lab 3 | Hands-on practice | 25 minutes | Verify results for three models and compare three filter plans |
| Quiz 3 | Interactive quiz | 5 minutes | Check model selection, keys, and plan evidence |

## 3.1 Doris Key Model

The Key Model selected when creating a table determines how data with identical keys is handled.
A raw ingestion table needs to retain every input, a current-order table needs to reflect the latest amounts, and a sales summary table needs to accumulate metrics.
These three needs correspond to retaining detail records, updating by key, and aggregating by function. First determine the business meaning of a row,
then choose a model so that write behavior matches the report's metric definitions.

### Why does the same input produce different results?

WWI order 1 has an amount of 2300.00, and order 2 has an amount of 405.00. Now, in isolated lab tables,
simulate correcting the amount of order 1 to 2250.00.
Submit three writes in the order below, waiting for each write to complete:

| Write order | id | amount | Meaning |
| --- | ---: | ---: | --- |
| 1 | 1 | 2300.00 | Original amount of order 1 |
| 2 | 1 | 2250.00 | Corrected amount of order 1 |
| 3 | 2 | 405.00 | Amount of order 2 |

**Duplicate Key: retain every detail record.** The key determines sorting; it is not a uniqueness constraint.

| id | amount |
| ---: | ---: |
| 1 | 2250.00 |
| 1 | 2300.00 |
| 2 | 405.00 |

**Unique Key: retain the current value for each key.** With sequential submissions and no Sequence column in this example,
a later write replaces the earlier value with the same key; handling out-of-order business versions also requires the version rules in Module 7.

| id | amount |
| ---: | ---: |
| 1 | 2250.00 |
| 2 | 405.00 |

**Aggregate Key: merge values using the declared function.** In this example, amount is declared as SUM:

| id | amount |
| ---: | ---: |
| 1 | 4550.00 |
| 2 | 405.00 |

4550.00 is 2300.00 + 2250.00. The engine performed SUM correctly,
but this is not the current amount of order 1: two snapshots cannot be added together as two sales.

After completing Lab 3, you can verify each result:

```sql
SELECT id, amount FROM orders_duplicate ORDER BY id, amount;
SELECT id, amount FROM orders_unique ORDER BY id;
SELECT id, amount FROM orders_aggregate ORDER BY id;
```

### Ask "what does one row represent?" before choosing a model

| What to retain | Logical identifier | Model used in this course |
| --- | --- | --- |
| Every raw delivery | Delivery ID | Duplicate Key retains every record |
| The current state of an order | order_id | Unique Key, with business versions added in Module 7 |
| Each distinct business event | event_id | Unique Key deduplicates redeliveries of identical content |
| Additive metrics accumulated by dimension | A combination of dimensions such as date and product | Aggregate Key, with explicit functions such as SUM |

Both current-state and history tables can use Unique Key, but their keys and purposes differ.
Using order_id in a history table would overwrite distinct events for the same order.
See the official references for the three models at the end for their precise semantics.

## 3.2 Partitioning, bucketing, and data distribution

### Do not confuse these four design choices

After deciding "how to handle the same order," you also need to decide "where to store the data." For example, for daily order reports,
partition by date so that a query for yesterday focuses on yesterday's data; then bucket each day's data by order ID,
distributing it across multiple Tablets to provide shards for parallel processing.

| Design | Question answered | Example in this section |
| --- | --- | --- |
| Partitioning | Which data belongs to the same range, and which ranges can be skipped? | Two days partitioned by order_date |
| Bucketing | How is data within a partition distributed across Tablets? | HASH(order_id), four buckets per partition |
| Sort key | How is data sorted in storage? | order_date, order_id |
| Business unique key | What identifies the same business object? | The current state of an order is identified by order_id |

The lab's partitioned table uses Duplicate Key to retain historical detail records, with date and order ID used for sorting.
When creating a separate current-order table, recheck the business unique key: if an order's date can be corrected,
including the date in the unique key would identify the records before and after correction as two different keys.

### Specify partitioning and bucketing in the CREATE TABLE statement

**SQL reading example: corresponds to the table creation step in Lab 3. Do not rerun it after completing the lab.**
Initialization and resets are still performed in the lab. First read the statement below to understand the layout:

<!-- reading-only-example -->
```sql
CREATE TABLE orders_partitioned (
    order_date DATE, order_id BIGINT, amount DECIMAL(18,2)
) DUPLICATE KEY(order_date, order_id)
PARTITION BY RANGE(order_date) (
    PARTITION p_day1 VALUES [('2013-01-01'), ('2013-01-02')),
    PARTITION p_day2 VALUES [('2013-01-02'), ('2013-01-03'))
)
DISTRIBUTED BY HASH(order_id) BUCKETS 4
PROPERTIES("replication_num"="1");
```

- The date and order ID in DUPLICATE KEY organize sorting; they do not guarantee unique order IDs.
- PARTITION BY RANGE partitions by date; each range includes its left endpoint and excludes its right endpoint.
- DISTRIBUTED BY HASH buckets by order ID; BUCKETS 4 means four buckets per partition, not four BEs.
- replication_num=1 is a single-replica setting for the teaching sandbox, not a production disaster recovery solution.

Therefore, orders dated 2013-01-02 belong to p_day2; the target bucket within the partition is then calculated from the order ID.
This example has only a base index, with the following physical layout:

```text
orders_partitioned
├── p_day1: 2013-01-01 ≤ order_date < 2013-01-02
│   └── HASH(order_id), 4 Tablets
└── p_day2: 2013-01-02 ≤ order_date < 2013-01-03
    └── HASH(order_id), 4 Tablets
```

### Compare three query plans

Hash bucketing calculates the target bucket from the bucket column's value. Within a partition, identical order IDs go into the same bucket;
the bucket number is calculated by Hash, so the order ID itself is not the bucket number. When a query specifies equality conditions on both date and order ID,
Doris can potentially narrow the scan to one day and then to the bucket containing that order.
The bucket count determines the number of shards. More buckets also mean more management overhead, so choose the count based on data volume.
For the relevant rules, see [Partitioning and bucketing](https://doris.apache.org/docs/4.x/table-design/data-partitioning/basic-concepts/).

Run after initializing the lab:

```sql
EXPLAIN SELECT * FROM orders_partitioned;
EXPLAIN SELECT * FROM orders_partitioned WHERE order_date = '2013-01-01';
EXPLAIN SELECT * FROM orders_partitioned
WHERE order_date = '2013-01-01' AND order_id = 1;
```

| Query | Changes to observe | Reason |
| --- | --- | --- |
| No filter | Both partitions and their Tablets | No dates or orders are excluded |
| Date filter | Only the first day's partition is needed | The second day's data does not meet the date condition |
| Date + order ID | Further narrows the Tablet range within the first day | A Hash-key equality condition can be used for bucket pruning |

Find the selected partition and Tablet counts in the scan node; exact field names vary by version.
EXPLAIN shows the planned scan range. Actual query duration also depends on scan volume, caching, and computation overhead;
analyze it alongside execution results and the Query Profile.

### Pruning must not change the answer

```sql
SELECT COUNT(*) AS sample_orders, SUM(amount) AS order_amount
FROM orders_partitioned
WHERE order_date = '2013-01-01';
```

The result should be five orders and 3944.20. Adding order_id=1 should return the original amount of 2300.00 for order 1,
not the corrected value of 2250.00 in the isolated model experiment; the data in these two sets of tables serves different purposes.
This section only verifies model semantics and plan pruning; it does not use a ten-order sample to compare production performance.

## Hands-on Lab 3: Model semantics, partitioning, and bucketing

Before starting, complete Module 1 and Module 2 to understand the order fields and basic storage structure, and use the course's isolated lab database.

Open [Lab 3](lab3_models_and_pruning.ipynb) and complete these steps in order:

1. Write different amounts with the same key to the three models and verify the results row by row.
2. Create a separate date-partitioned detail table and prepare different filters for the same query.
3. Compare plans and results with no filter, a date filter, and a date plus order ID filter.

### Data sources and notes

The lab uses a historical subset of Microsoft's official WWI simulated wholesale business, retaining the original customer and product identifiers.
See the [data notes](../../datasets/README.md) for fields, business definitions, and expected results.

See the [Level 1 extension labs](../extensions/README.md) for additional exercises, run in separate `ext_*` tables without rewriting this lab's business results.

## Module Summary

- Duplicate retains three rows, Unique retains the current values for two orders, and Aggregate SUM produces 4550.00 for order 1; identical input does not imply identical business semantics.
- Determine the row grain and logical key before choosing a model; order_id maintains current state, while event_id preserves distinct events.
- Partitions manage ranges, buckets manage distribution, and sort keys manage ordering; these physical design choices must not silently change business uniqueness.
- Date conditions and Hash-key conditions can prune at different levels; use EXPLAIN to inspect the partitions and Tablets actually selected.
- Verify detail records and amounts before discussing efficiency; a correctly executed SUM does not mean the metric definition is correct, and a smaller plan does not mean a speedup has been measured.

## Knowledge Quiz 3: Model semantics, partitioning, and bucketing

After completing the reading and lab, open [Quiz 3](quiz3_models_and_data_distribution.ipynb).
The quiz contains five single-choice questions and does not require Doris or external services; read the answer explanations after submitting.

## Official References

- [Duplicate Key detail model](https://doris.apache.org/docs/4.x/table-design/data-model/duplicate/)
- [Unique Key primary key model](https://doris.apache.org/docs/4.x/table-design/data-model/unique/)
- [Aggregate Key aggregate model](https://doris.apache.org/docs/4.x/table-design/data-model/aggregate/)
- [Partitioning and bucketing basics](https://doris.apache.org/docs/4.x/table-design/data-partitioning/basic-concepts/)
- [Data bucketing](https://doris.apache.org/docs/4.x/table-design/data-partitioning/data-bucketing/)
- [EXPLAIN](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-query/EXPLAIN/)
