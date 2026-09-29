# Module 10: Metric Processing and Delivery

| Course Information | Details |
| --- | --- |
| Course | Data Warehousing with Apache Doris · Level 2 |
| Product scope | Apache Doris 4.x; examples use the course's 4.1.3 sandbox |
| Prerequisites | Level 1 ingestion and quality checks; Module 9 grain and joins |
| Estimated time | About 95 minutes: reading 50, Lab 40, Quiz 5 |

[Level 2 contents](../README.md) · [Open Lab 10](lab10_metric_processing.ipynb) · [Open Quiz 10](quiz10_metric_processing.ipynb)

## Module Goal

Three teams may all report “average order value,” yet one divides total amount by total orders while another averages daily ratios. Both formulas run, but they answer different questions. This module turns a metric into a reviewable contract, creates a service table at a declared grain, reconciles it against an independent detail query, and explains where window functions, approximate distinct counts, and Query Profile fit.

## Learning Objectives

After this module, you should be able to:

1. Define a metric's population, numerator, denominator, grain, filters, time rule, unit, and null rule.
2. Distinguish order detail from an aggregate service table.
3. Reconcile service results against an independent detail query.
4. Use window functions and conditional aggregation without accidentally changing the intended grain.
5. Publish a bounded query result for dashboard consumers and separate correctness checks from performance checks.

## Module Schedule

| Section | Question | Time |
| --- | --- | ---: |
| 10.1 Metric contract | What exactly is being counted? | 12 min |
| 10.2 Pre-aggregation | When should calculation move into a service table? | 12 min |
| 10.3 Window and conditional logic | What happens to row grain? | 12 min |
| 10.4 Distinct counts and evidence | Exact or approximate; plan or execution? | 10 min |
| 10.5 Acceptance | Can detail independently reproduce the service value? | 4 min |
| Lab 10 / Quiz 10 | Build, reconcile, and explain | 40 / 5 min |

## 10.1 Write a Metric Contract Before SQL

“Daily order count” is not precise until you answer these questions:

| Contract item | Course definition | Risk if omitted |
| --- | --- | --- |
| Population | Initial order snapshots in `orders_imported` | Mix orders, item lines, and payment events. |
| Grain | `DATE(event_time)` × `data_source` | Duplicate values across customers or events. |
| Numerator | Number of order rows | Count refunds or item lines as orders. |
| Filter | All course orders; no extra amount filter | Different dashboards cannot reconcile. |
| Time rule | Date derived from `event_time` in the course environment | UTC and business-day boundaries differ. |
| Unit | Orders and the dataset's amount unit | Misread cents, currency, or tax treatment. |
| Zero denominator | Return `NULL` | Confuse “no orders” with a genuine zero ratio. |

For the sample, define:

```text
Daily order count  = COUNT(*)
Daily order amount = SUM(order_amount)
Group both by DATE(event_time) and data_source.
Average order value = daily order amount / daily order count;
                      return NULL if the count is zero.
```

The ten Lab 5 rows for `2026-01-01` have count 10 and total amount 1400.00, so the average is 140.00. This is a **simulated initial order snapshot**, not an actual company's GMV, collected revenue, or net amount after refunds. A different business metric needs its own source and time rules.

### Why keep numerator and denominator?

Suppose day 1 has one order worth 100 and day 2 has 100 orders worth 1000. Their daily averages are 100 and 10. The simple average of those two ratios is 55, while the combined average is `1100 / 101 ≈ 10.89`. A service table that stores amount and count can recompute the correct value at a new grain; averaging stored ratios cannot in general. Order amount is additive only if the source has not been duplicated by a join. Account balance is semi-additive: summing across customers may make sense, but summing the same balance across dates usually does not.

## 10.2 Build a Service Table at a Declared Grain

Detail supports drill-down and audit. A service table answers a frequently repeated, stable question with fewer rows, at the cost of storage, refresh work, and reconciliation. If a million orders span one year, a daily service result might contain roughly one row per date and source rather than one row per order. That is a **hypothetical workload illustration**, not a performance measurement from this ten-row Lab.

Lab 10 creates the following Aggregate Key table. Read the DDL here; the Notebook runs it on its `_l2` object:

<!-- reading-only-example -->
```sql
CREATE TABLE daily_order_metrics_l2 (
    order_date DATE NOT NULL,
    data_source VARCHAR(32) NOT NULL,
    order_count BIGINT SUM NOT NULL DEFAULT "0",
    gross_amount DECIMAL(18,2) SUM NOT NULL DEFAULT "0.00"
)
AGGREGATE KEY(order_date, data_source)
DISTRIBUTED BY HASH(order_date) BUCKETS 1
PROPERTIES ("replication_num"="1");
```

`SUM` columns add inputs with the same key; they do **not** know that two inserts represent the same source batch. Repeating an `INSERT` can double the amount. Production jobs need an explicit batch, replacement, or idempotency strategy. One bucket and one replica are choices for this single-node teaching sandbox, not production defaults or fault tolerance.

| Option | Best fit | What must be controlled |
| --- | --- | --- |
| Explicit aggregate service table | Cleaning, batches, quality gates, and service publishing need orchestration | Idempotency, rebuild scope, and reconciliation |
| Asynchronous MV | A stable query can use Doris-managed refresh and possible rewriting | Refresh status, freshness, rewrite eligibility, resources |
| Regular view | Share a definition without stored computation | Query-time cost and base-data semantics |

Do not discard detail just because service queries are fast: detail is the independent evidence used to find aggregate errors.

## 10.3 Calculate Without Losing Track of Grain

`GROUP BY` folds many input rows into groups. A window function calculates across related rows while generally keeping each input row. Apply a window to an already daily result when you want one row per day plus a cumulative value:

```sql
WITH daily AS (
    SELECT DATE(event_time) AS order_date,
           COUNT(*) AS order_count,
           SUM(order_amount) AS gross_amount
    FROM orders_imported
    GROUP BY DATE(event_time)
)
SELECT order_date,
       order_count,
       gross_amount,
       SUM(gross_amount) OVER (
           ORDER BY order_date
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS cumulative_amount,
       LAG(gross_amount) OVER (ORDER BY order_date) AS previous_available_day_amount
FROM daily
ORDER BY order_date;
```

The CTE establishes a daily grain, and the final query keeps it. `LAG` returns the previous **available row**, not necessarily yesterday; a true calendar-day comparison needs a complete date series. Applying a daily window sum directly to every order row would repeat that daily result on each order, so summing the window column again would inflate it. Ranking functions also need a defined tie rule; moving windows need explicit boundaries.

Conditional aggregation can produce several slices at one grain:

```sql
SELECT order_date,
       SUM(CASE WHEN data_source = 'COURSE_SIMULATION'
                THEN order_count ELSE 0 END) AS simulated_orders,
       SUM(order_count) AS all_orders,
       SUM(gross_amount) AS gross_amount
FROM daily_order_metrics_l2
GROUP BY order_date
HAVING SUM(order_count) > 0
ORDER BY order_date;
```

The output is one row per date. `WHERE` filters source rows before grouping; `HAVING` filters groups afterward. `ELSE 0` treats an absent source as zero within an existing date group; decide separately whether consumers need to distinguish an absent row from a genuine zero.

## 10.4 Choose Precision and Read the Right Evidence

Distinct visitors (UV) require an accuracy promise before a function choice:

| Method | Result | Appropriate when | Cost or limitation |
| --- | --- | --- | --- |
| `COUNT(DISTINCT id)` | Exact | Reconciliation must be exact and resources permit | Maintains a distinct set. |
| Bitmap | Exact | Integer IDs and large reusable distinct aggregates | Uses Bitmap-compatible IDs and aggregation functions. |
| HLL | Approximate | Scale matters more than an exact count | Approximation must be disclosed to consumers. |

Do not call HLL exact because it happens to match a small example, or assume arbitrary strings can be placed directly in a Bitmap aggregate.

`EXPLAIN` shows the planned scans, filters, aggregates, and joins. Query Profile shows measured operator rows, time, and memory for an actual execution. In a course sandbox you can learn what fields mean; you cannot infer production performance from one tiny query.

```sql
SET enable_profile = true;
SELECT order_date, SUM(gross_amount)
FROM daily_order_metrics_l2
GROUP BY order_date;
SHOW QUERY PROFILE;
```

## 10.5 Reconcile Service Data Independently

Lab 10 should produce:

| order_date | data_source | order_count | gross_amount |
| --- | --- | ---: | ---: |
| 2026-01-01 | COURSE_SIMULATION | 10 | 1400.00 |

Recompute from **detail**, not by reading the service table twice:

```sql
WITH detail AS (
    SELECT DATE(event_time) AS order_date,
           COUNT(*) AS order_count,
           SUM(order_amount) AS gross_amount
    FROM orders_imported
    GROUP BY DATE(event_time)
), serving AS (
    SELECT order_date,
           SUM(order_count) AS order_count,
           SUM(gross_amount) AS gross_amount
    FROM daily_order_metrics_l2
    GROUP BY order_date
)
SELECT COALESCE(d.order_date, s.order_date) AS order_date,
       d.order_count AS detail_orders,
       s.order_count AS serving_orders,
       d.gross_amount AS detail_amount,
       s.gross_amount AS serving_amount
FROM detail d
FULL OUTER JOIN serving s ON s.order_date = d.order_date
ORDER BY order_date;
```

A full outer join retains a date that appears on only one side. Do not replace a missing-side `NULL` with zero before investigating: a missing aggregate row is not the same as a real zero. Check row counts, amounts, date coverage, nulls, and important dimensions before tuning a plan. Optimizing an incorrect answer only returns the incorrect answer faster.

## Hands-on Lab: Build and Reconcile Daily Metrics

Open [Lab 10](lab10_metric_processing.ipynb) after Level 1 Lab 5. It creates `daily_order_metrics_l2`, inserts date-by-source aggregates, queries dashboard-style results, and independently reconciles detail and service values. A read-only two-date, two-source CTE then makes conditional aggregation, a cumulative window, and the error of averaging source-level ratios visible without changing the service table used by Lab 11.

| Acceptance check | Expected |
| --- | --- |
| Service grain | Date × data source |
| Current sample | One row for `2026-01-01` and `COURSE_SIMULATION` |
| Orders / amount | 10 / 1400.00 |
| Independent detail comparison | Same count and amount on both sides |
| Contrast sample | January 1 has APP count 1 versus total count 10; average-of-averages 55.00 versus correct weighted average 19.00; cumulative amount reaches 230.00 on January 2 |

### Independent exercise

Run a new date-by-customer query over `orders_imported` and reconcile it independently to 10 orders and 1400.00. The existing service table cannot answer this request because `customer_id` was discarded; do not copy a daily amount onto each customer and sum the copies.

## Module Summary

- A metric contract states population, grain, numerator, denominator, filters, time, units, and null rules.
- Additive amounts, semi-additive balances, and non-additive ratios need different roll-up rules; preserve ratio components.
- Aggregate service tables avoid repeated work but require idempotency, refresh control, and independent reconciliation.
- Window functions generally preserve input rows; conditional aggregation still needs an explicit output grain.
- Bitmap and exact distinct counts differ from HLL approximation; `EXPLAIN` and Query Profile provide different evidence.
- Establish correctness before performance optimization.

## Knowledge Quiz

Open [Quiz 10](quiz10_metric_processing.ipynb) to check metric contracts, service tables, reconciliation, window functions, and consumer queries.

## Official References

- [Window functions](https://doris.apache.org/docs/4.x/query-data/window-function/)
- [Bitmap exact distinct counts](https://doris.apache.org/docs/4.x/query-acceleration/distinct-counts/bitmap-precise-deduplication/)
- [HLL approximate distinct counts](https://doris.apache.org/docs/4.x/query-acceleration/distinct-counts/hll-approximate-deduplication/)
- [Query Profile](https://doris.apache.org/docs/4.x/query-acceleration/query-profile/)
