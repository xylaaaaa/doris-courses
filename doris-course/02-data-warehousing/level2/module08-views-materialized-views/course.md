# Module 8: Views and Materialized Views

| Course Information | Details |
| --- | --- |
| Course | Data Warehousing with Apache Doris · Level 2 |
| Product scope | Apache Doris 4.x; examples use the course's 4.1.3 sandbox |
| Prerequisites | Level 1 Lab 5 and its `orders_imported` table |
| Suggested time | About 118 minutes: reading 45, Lab 65, Quiz 8; first-start image downloads/builds are additional |

[Level 2 contents](../README.md) · [Open Lab 8](lab8_views_and_materialized_views.ipynb) · [Open Quiz 8](quiz8_views_and_materialized_views.ipynb)

## Module Goal

Operations, Finance, and BI all ask for daily order counts and amounts. If each team copies and edits its own SQL, their filters will drift; if every dashboard repeatedly scans detail rows, the same aggregation is calculated again and again. This module first uses a regular view to share a definition, then explains when a stored result is worthwhile and how to prove that it is fresh, correct, and actually used by a query.

## Learning Objectives

After this module, you should be able to:

1. Distinguish a regular view's saved SQL definition from a materialized view's stored result.
2. Choose a refresh strategy based on freshness, write cost, and query cost.
3. Verify materialized-view status and values rather than relying on a successful `CREATE` response.
4. Use `EXPLAIN` to look for transparent rewriting instead of assuming it happened.
5. Keep a published consumer contract stable when its physical implementation changes.
6. Decide whether repeated query cost justifies maintaining a stored result.

## Module Schedule

| Section | Question | Time |
| --- | --- | ---: |
| 8.1 Regular views | Why do three teams' SQL definitions drift? | 8 min |
| 8.2 Precomputation | When is a materialized view worth its cost? | 10 min |
| 8.3 Incremental refresh | Does `AUTO` mean row-by-row accumulation? | 12 min |
| 8.4 Rewrite evidence | How do we know which object a query scanned? | 10 min |
| Lab 8 / Quiz 8 | Existing foundations and extended core evidence | 65 / 8 min |

## 8.1 Use a Regular View to Share Meaning

### One question, different filters

Imagine two teams querying the ten orders loaded in Lab 5. Operations counts only delivered orders; Finance counts all positive-amount orders:

```sql
-- Operations' definition
SELECT DATE(event_time) AS order_date,
       COUNT(*) AS order_count,
       SUM(order_amount) AS gross_amount
FROM orders_imported
WHERE status = 'DELIVERED'
GROUP BY DATE(event_time);
```

```sql
-- Finance's definition
SELECT DATE(event_time) AS order_date,
       COUNT(*) AS order_count,
       SUM(order_amount) AS gross_amount
FROM orders_imported
WHERE order_amount > 0
GROUP BY DATE(event_time);
```

Both statements run, but they answer different questions. If Operations later includes `SHIPPED` orders without telling Finance, the reports can diverge without an SQL error. Before optimizing a query, decide which business definition consumers should share.

A regular view saves a SQL definition, not a copy of its result. Lab 8 creates this service view (the example below is for reading; the Notebook executes it):

<!-- reading-only-example -->
```sql
CREATE VIEW orders_service_view_l2 AS
SELECT DATE(event_time) AS order_date,
       customer_id,
       order_amount,
       data_source
FROM orders_imported
WHERE order_amount > 0;
```

The view names the date expression, centralizes a filter, and exposes only four intended columns. A query against it still reads and calculates from the base table. **A regular view is a semantic interface, not a result cache or an automatic speed-up.**

A consumer contract should also state what each column means: whether `order_amount` is pre-tax order value or money collected, its currency and unit, whether `order_date` is order time or payment time, what `NULL` means, and who owns corrections. A view can provide a stable name while the underlying implementation changes, but silently changing a column's meaning breaks the contract. Creating a view also does not grant users access; Module 12 covers permissions.

## 8.2 Decide Whether to Store a Result

Suppose a million detail rows are queried every five minutes for the same daily aggregation. A regular view shares the definition but still repeats the scan and aggregation. A materialized view stores a precomputed result at the cost of storage and refresh work. On the course's ten-row sample, precomputation is useful for learning semantics—not for proving a performance gain.

| Object | What it stores | Work at query time | Main trade-off |
| --- | --- | --- | --- |
| Regular view | SQL definition | Runs the underlying query | Stable meaning, no stored result |
| Synchronous materialized view | Materialized index on a base table | Reads a maintained result when matched | Write-path maintenance and model restrictions |
| Asynchronous materialized view | Separately refreshed result | Reads the result directly or through rewrite | Refresh cost and possible staleness |

Synchronous materialized views target single-table queries and are maintained with writes. On a **Unique Key** base table they can change column order but cannot aggregate. This course's `orders_imported` is a **Duplicate Key** table, so do not transfer Unique Key restrictions or examples to it without checking the model. [Doris's synchronous materialized-view guide](https://doris.apache.org/docs/4.x/query-acceleration/materialized-view/sync-materialized-view/) documents the limitations.

Lab 8 focuses on an asynchronous view. The Notebook executes this definition:

<!-- reading-only-example -->
```sql
CREATE MATERIALIZED VIEW orders_daily_mv_l2
BUILD IMMEDIATE
REFRESH AUTO ON MANUAL
AS
SELECT DATE(event_time) AS order_date,
       COUNT(*) AS order_count,
       SUM(order_amount) AS gross_amount
FROM orders_imported
GROUP BY DATE(event_time);
```

| Clause | Meaning | Do not assume |
| --- | --- | --- |
| `BUILD IMMEDIATE` | Start the first build after creation | `CREATE` returning means the data is ready |
| `REFRESH AUTO` | Let Doris choose the applicable refresh scope | Only newly inserted rows are always processed |
| `ON MANUAL` | Refresh is triggered manually | Every `SELECT` refreshes automatically |
| `GROUP BY DATE(event_time)` | Store daily aggregates | A customer-level filter remains possible |

The view stores daily `COUNT(*)` and `SUM(order_amount)` values but not `customer_id`. A customer-filtered query therefore cannot be answered from this result alone. The definition has no partition mapping, so this first MV does not demonstrate refreshing only one day; Section 8.5 uses a separate partitioned MV to observe that path. It also does not schedule automatic refresh. These are separate design choices, not hidden benefits of creating an MV.

A materialized view is most useful for stable, frequently repeated expensive queries when its freshness contract can be met. It is less compelling for one-off exploration, tiny data, rapidly changing query shapes, or a refresh schedule that cannot keep up with updates. Compare both the read savings and write/refresh cost before adopting one.

## 8.3 Understand Incremental Refresh

Here, “incremental” can mean **recomputing only affected partitions**, not adding each changed row to the previous `SUM`. Consider a base table and MV whose date partitions can be mapped to one another:

| Date | Base partition | Orders |
| --- | --- | ---: |
| 2026-01-01 | `p20260101` | 100 |
| 2026-01-02 | `p20260102` | 150 |
| 2026-01-03 | `p20260103` | 200 |

If only January 3 changes, a partition-aware refresh can recalculate the corresponding MV partition rather than every day. That requires compatible base and MV partitioning and a relationship Doris can infer. A change to an unpartitioned dimension table in a join may affect many dates and require a wider refresh; if partition mapping cannot be derived, a full refresh may be necessary. `AUTO` is not a promise of row-level delta arithmetic.

For example, if a day's amount changes from 200 to 180, adding 180 to 200 to obtain 380 is wrong. Recompute the affected day's aggregate from its current source rows to obtain 180. Module 10 returns to the difference between snapshot recomputation and adding new business events.

After building the MV, inspect its status:

<!-- reading-only-example -->
```python
lab.sql(
    f"SELECT * FROM mv_infos('database'='{lab.database}') "
    "WHERE Name = 'orders_daily_mv_l2'",
    title="Materialized-view status and refresh details",
)
```

`State`, `RefreshState`, and `SyncWithBaseTables` answer different questions about object state, refresh execution, and synchronization with the base table. A successful first build should be followed by a direct value check. For the Lab 5 sample, the daily result is one row for `2026-01-01` with 10 orders and 1400.00 in order amount. This is an initial teaching snapshot, not money collected or the current state after Lab 7 replay.

## 8.4 Prove Whether Rewriting Happened

Four outcomes must not be conflated: (1) creation succeeded, (2) refresh completed, (3) a direct `SELECT` from the MV returned correct data, and (4) a query written against the base table was transparently rewritten to use the MV. The first three do **not** prove the fourth.

Directly querying the MV name is not a rewrite. To investigate rewriting, explain a compatible query written against the base table:

```sql
EXPLAIN
SELECT DATE(event_time) AS order_date,
       COUNT(*) AS order_count,
       SUM(order_amount) AS gross_amount
FROM orders_imported
GROUP BY DATE(event_time)
ORDER BY order_date;
```

Read the scan nodes in the actual plan. Scanning `orders_daily_mv_l2` is evidence of rewrite; scanning `orders_imported` means this plan did not use the MV. In either case, compare the result with an independent base-table aggregation. A planner can choose not to rewrite even when an MV exists.

If no rewrite appears, check three groups of causes:

1. **MV readiness:** Has refresh completed? Are `State`, `RefreshState`, and synchronization status appropriate?
2. **Query compatibility:** Do filters, grain, and required columns match what the MV can answer? The service view filters `order_amount > 0`, while this MV has no such filter. The current ten positive sample rows may yield equal totals, but sample equality does not make the SQL definitions interchangeable.
3. **Planner choice:** Is the rewrite setting enabled? Are statistics adequate? Has an allowed freshness or `grace_period` setting affected eligibility?

Do not use `FROM orders_daily_mv_l2` as “proof” of transparent rewrite, and do not infer rewrite from a descriptive object name or one matching answer.

## 8.5 Observe Three Different Maintenance Paths

The extended Lab uses isolated sources rather than modifying the shared Level 1 input. First it builds a synchronous aggregate index on a Duplicate Key table. After its initial DDL job finishes, a new committed order is included without a separate refresh. The cost moves into write maintenance; `EXPLAIN` still decides whether a compatible read uses that index.

Next, two daily fact partitions join an unpartitioned customer dimension. The asynchronous MV groups by `(order_date, region)` and maps its partitions to the fact date. Adding an order on the second day causes one result partition to be republished. Updating a customer's region invalidates the unpartitioned dependency and causes both result partitions to be republished in this example. One day can have identical values before and after a wider refresh, so value equality alone cannot establish refresh scope.

| Path | Trigger used in the Lab | Evidence to inspect |
| --- | --- | --- |
| Synchronous aggregate index | A committed base-table write after the initial build | Current aggregate and the selected index in `EXPLAIN` |
| Partitioned asynchronous join MV; one fact date changes | Manual `REFRESH ... AUTO` | Values, partition-identity/version changes, and the task's refresh-partition list |
| Same MV; unpartitioned dimension changes | Manual `REFRESH ... AUTO` | Both result partitions republished, even if one day's values are unchanged |

A replaced partition can retain the same visible version number. Compare partition identity together with visible version. These describe publication, not operator CPU or scan cost. Use task records to explain scope and Query Profile to measure work. The Lab proves these controlled refresh paths; it does not pretend to validate automatic scheduling, refresh-failure recovery, or production latency. The partition mapping and non-partitioned dependency rules are documented in [CREATE ASYNC MATERIALIZED VIEW](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/table-and-view/async-materialized-view/CREATE-ASYNC-MATERIALIZED-VIEW/).

## Hands-on Lab: From Shared Definition to Verified Materialization

Open [Lab 8](lab8_views_and_materialized_views.ipynb). It connects to the course database, creates `orders_service_view_l2` and `orders_daily_mv_l2`, checks `mv_infos`, compares direct MV values with a canonical aggregation, and records the `EXPLAIN` plan. A second, isolated `_l2` source then receives a new order: its regular view changes immediately, while its manual-trigger MV changes only after an explicit refresh. It then compares synchronous write maintenance, fact-partition refresh, and a full refresh after an unpartitioned dimension change. The Lab never writes to the Level 1 source table.

| Check | Expected observation |
| --- | --- |
| Regular view | Ten positive-amount sample rows |
| Base-table daily aggregation | One day, 10 orders, 1400.00 |
| Materialized result | Same values as the base-table aggregation |
| `EXPLAIN` | Record whether the actual scan uses the MV; do not assume it does |
| Refresh contrast | After a new 50.00 order, the regular view shows 2 / 150.00 while the stored MV still shows 1 / 100.00; after manual refresh both show 2 / 150.00 |

### Independent exercise

A consumer now wants to filter the daily result by customer. Is the existing MV sufficient? No: its only columns are date, count, and amount. One option is to aggregate by `(order_date, customer_id)` so a consumer can filter a customer or roll up to a day; this increases stored rows. Another option is a second customer-level MV, which adds storage and refresh work. In either case, do not silently change the existing consumer view's column names or amount meaning.

## Module Summary

- Regular views save definitions and stabilize business meaning; queries still compute from source data.
- Materialized views store results but incur storage, maintenance, and freshness costs.
- Synchronous and asynchronous MVs differ in maintenance and supported definitions.
- Partition-aware incremental refresh narrows the recomputation scope; it is not row-by-row addition to a prior sum.
- `CREATE`, refresh, direct query, and transparent rewriting are separate checks.
- A view contract includes grain, filters, units, and ownership; physical optimization must not silently change it.

## Knowledge Quiz

Open [Quiz 8](quiz8_views_and_materialized_views.ipynb) after the reading and Lab. Its six scenario questions cover view types, refresh trade-offs, result checks, rewrite evidence, contract stability, and when precomputation pays off.

## Official References

- [Synchronous materialized views](https://doris.apache.org/docs/4.x/query-acceleration/materialized-view/sync-materialized-view/)
- [Asynchronous materialized-view overview](https://doris.apache.org/docs/4.x/query-acceleration/materialized-view/async-materialized-view/overview/)
- [Asynchronous materialized-view use guide](https://doris.apache.org/docs/4.x/query-acceleration/materialized-view/async-materialized-view/use-guide/)
- [CREATE ASYNC MATERIALIZED VIEW](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/table-and-view/async-materialized-view/CREATE-ASYNC-MATERIALIZED-VIEW/)
