# Module 11: BI and AI Applications

| Course Information | Details |
| --- | --- |
| Course | Data Warehousing with Apache Doris · Level 2 |
| Product scope | Apache Doris 4.x; examples use the course's 4.1.3 sandbox |
| Prerequisites | Module 8 views, Module 9 grain, and Module 10 metric contracts |
| Estimated time | About 88 minutes: reading 45, Lab 35, Quiz 8 |

[Level 2 contents](../README.md) · [Open Lab 11](lab11_bi_and_ai_delivery.ipynb) · [Open Quiz 11](quiz11_bi_and_ai.ipynb)

## Module Goal

A BI team can query a table and still build a wrong dashboard if it mistakes a pre-tax order amount for money collected. Query access alone is not a data product. BI and AI consumers need an understandable, access-controlled, refreshed, and testable interface. This module wraps Module 10's metrics in a semantic view, explains dashboard dimensions and measures, and draws a clear boundary around feature projections and the separate Apache Doris MCP Server.

## Learning Objectives

After this module, you should be able to:

1. Design a consumer view with stable names and declared row grain.
2. Distinguish dimensions, additive measures, and calculated ratios in a dashboard.
3. Prepare reviewed feature inputs without claiming that a downstream model is accurate.
4. Check nulls, coverage, freshness, counts, and amounts before publication.
5. State what Doris SQL proves and what BI or AI tools must validate separately.
6. Scope an external Model Context Protocol server to reviewed Doris data.

## Module Schedule

| Section | Question | Time |
| --- | --- | ---: |
| 11.1 Consumer contract | Which columns and meanings should a dashboard depend on? | 10 min |
| 11.2 BI connection | What do Doris and Superset each own? | 10 min |
| 11.3 AI feature inputs | What can a data projection prove? | 10 min |
| 11.4 MCP access | How can an AI tool read Doris safely? | 10 min |
| 11.5 Publication checks | How do we validate the interface? | 5 min |
| Lab 11 / Quiz 11 | Publish a view and explain its limits | 35 / 8 min |

## 11.1 Publish a Consumer Contract, Not Just a Query

A dashboard commonly uses three kinds of fields:

| Kind | Meaning | Course example |
| --- | --- | --- |
| Dimension | Splits, filters, or orders results | `order_date` |
| Measure | Numeric quantity at the declared grain | `order_count`, `gross_amount` |
| Calculated measure | Derives a result from checked components | `average_order_amount` |

Do not sum a date or average an already aggregated average order value without revisiting its numerator and denominator. Lab 11 creates this semantic view over Module 10's service table (read here; the Notebook executes it):

<!-- reading-only-example -->
```sql
CREATE VIEW bi_order_metrics_l2 AS
SELECT order_date,
       SUM(order_count) AS order_count,
       SUM(gross_amount) AS gross_amount,
       CASE WHEN SUM(order_count) = 0 THEN NULL
            ELSE SUM(gross_amount) / SUM(order_count) END AS average_order_amount
FROM daily_order_metrics_l2
GROUP BY order_date;
```

It has **one row per represented date**, not one row per customer. It retains amount and count until the final division. A date with no source rows does not appear automatically; a calendar table would be needed to create such rows. A zero denominator yields `NULL`, not an invented zero average.

A consumer contract should record:

1. **Names, types, and business meanings:** `order_date` derives from `event_time`; `order_count` counts the course's initial orders; `gross_amount` is simulated pre-tax order amount, not collected cash; `average_order_amount` is amount divided by count.
2. **Grain and uniqueness:** one row per date; a missing date is different from a date whose measures are zero.
3. **Time and coverage:** the time zone, first covered date, event-time rule, and treatment of late data.
4. **Freshness:** the refresh trigger, acceptable delay, and which date or partition must be rebuilt after late arrivals.
5. **Null and zero rules:** why the calculated ratio can be `NULL`.
6. **Access and ownership:** which read-only account may see the published view, and who approves a definition change.
7. **Downstream duties:** Doris can expose checked rows; a BI tool owns its chart filters, caching, and rendering; an AI application owns its model and evaluation.

The implementation under a view can change without breaking consumers only if the published columns **and their meanings** remain stable.

## 11.2 Connect BI Without Confusing Responsibilities

Superset can use Doris as an SQL source; Superset handles charts, dashboard configuration, its cache, and its own access model. The documented connection URI has this form:

<!-- Reading-only URI template; do not paste a real password into course files. -->

```text
doris://<username>:<password>@<host>:<port>/internal.<database>
```

The MySQL query port inside the course container is 9030; a client on the host must use the mapped host port instead. Do not mix container and host coordinates. Before creating a BI dataset, verify that the account can read only its intended published objects, the catalog and database are correct, the SQL result matches the independent Module 10 reconciliation, amounts remain numeric, and the time zone and refresh assumptions are documented.

A useful service-level agreement separates three outcomes:

| Goal | Doris-side evidence | Other owner or dependency |
| --- | --- | --- |
| Speed | Query latency, scanned rows, operator time in Query Profile | BI query, concurrency, and cache settings |
| Freshness | Latest successful refresh and maximum event time | Scheduler, late data, and BI cache |
| Accuracy | Fixed expectations, independent detail reconciliation, null and count checks | Metric owner and chart filters |

A 200 ms response does **not** prove that the data is fresh. A displayed number does **not** prove that the business definition is correct. The Lab does not install Superset; it first verifies the consumer query in Doris:

```sql
SELECT order_date, order_count, gross_amount, average_order_amount
FROM bi_order_metrics_l2
WHERE order_date >= '2026-01-01'
ORDER BY order_date;
```

Use `order_date` as the time dimension and the count and amount as measures. Do not sum `average_order_amount` over dates in the BI layer; aggregate its amount and count components first.

## 11.3 Give AI Checked Inputs, Not Unsupported Conclusions

A feature projection can provide consistently named, typed, and checked columns to a downstream model. It does not prove predictive quality, prevent target leakage, or by itself resolve differences between training-time and serving-time data. Lab 11 reads this projection without writing a new table:

```sql
SELECT order_date,
       order_count AS feature_order_count,
       gross_amount AS feature_gross_amount,
       average_order_amount AS feature_average_amount,
       CASE WHEN order_count = 0 THEN 1 ELSE 0 END AS zero_order_flag
FROM bi_order_metrics_l2
ORDER BY order_date;
```

| Feature | Possible use | Still needs a decision about |
| --- | --- | --- |
| `feature_order_count` | Order activity | Whether the day is final and how late events are handled |
| `feature_gross_amount` | Amount scale | Currency, tax, and refund scope |
| `feature_average_amount` | Per-order average | What to do with a zero denominator |
| `zero_order_flag` | Zero-count rows that actually exist | Missing dates do not appear automatically |

Doris also has vector storage and approximate-nearest-neighbor index features, but neither turns a monetary column into a good model feature nor replaces offline evaluation. This Lab does not create a vector index.

## 11.4 Put a Boundary Around MCP Access

The [Apache Doris MCP Server](https://doris.apache.org/docs/4.x/key-features/mcp-server/) is a **separate service**, not a built-in SQL statement in the FE. It connects to Doris through the MySQL protocol and exposes tools to MCP clients for schema exploration and read-oriented analysis. A possible flow is:

```text
MCP client → Doris MCP Server → Doris connection as a named database user
```

The server's tool-level filtering, timeouts, result limits, and audit settings supplement—not replace—Doris account permissions. A safe deployment uses a dedicated read-only account scoped to published views, keeps credentials out of notebooks and prompts, reviews generated SQL (especially sensitive columns and wide scans), limits result rows and time range, treats business text returned from tables as untrusted input, and retains audit records. Do not connect MCP as root or treat an AI model's confidence as metric acceptance evidence.

The current Notebook does **not** install or contact an external MCP Server. The deployment notes are reading material for a later environment.

## 11.5 Check the Published Interface

After Lab 11, run an integrity query:

```sql
SELECT COUNT(*) AS serving_days,
       SUM(CASE WHEN order_count IS NULL THEN 1 ELSE 0 END) AS null_order_days,
       MIN(order_date) AS first_date,
       MAX(order_date) AS last_date,
       SUM(order_count) AS served_orders
FROM bi_order_metrics_l2;
```

| Check | Current teaching sample |
| --- | --- |
| Service days / null-count days | 1 / 0 |
| First / last date | `2026-01-01` / `2026-01-01` |
| Served orders / amount | 10 / 1400.00 |
| Average order amount | 140.00 |

Before production publication, also check schema and grain, critical nulls, independent count and amount totals, maximum event time, latest successful refresh, source batches, and read-only account scope. An unexpected result should lead back to its source and definition before any dashboard is released.

## Hands-on Lab: Publish a Stable Consumer Interface

Complete Lab 10, then open [Lab 11](lab11_bi_and_ai_delivery.ipynb). It rebuilds `bi_order_metrics_l2`, queries reviewed dashboard fields and feature projections, and performs integrity checks. A temporary broken view proves that a missing published column is detectable; fixed teaching reference dates show a one-day freshness rule passing and then failing. The input is Module 10's service table; Modules 8–9 are conceptual context but not direct Lab 11 inputs. Results appear as tables. The Lab neither launches Superset nor connects to an external MCP Server.

### Independent exercise

A BI team now wants a customer-region filter. The current view cannot provide it: every row is already aggregated by date and contains no customer or region. A date-by-region service needs new aggregation from appropriate detail and dimension data, a new or versioned consumer contract, and its own refresh, access, and acceptance rules. Do not add a region column to the daily view while still claiming one row represents a whole day.

## Module Summary

- A semantic view is a consumer contract: dimensions, measures, grain, units, and ownership must be explicit.
- Doris provides SQL data; BI tools own presentation, caching, and their own access settings. Speed, freshness, and accuracy need separate checks.
- A feature projection supplies reviewed inputs, not a guarantee of model quality.
- MCP access needs a separate service and a least-privilege Doris identity; tool filters do not replace database permissions.
- Check schema, nulls, coverage, counts, amounts, freshness, and account scope before publishing.

## Knowledge Quiz

Open [Quiz 11](quiz11_bi_and_ai.ipynb) to check semantic views, dimensions and measures, feature projections, publication checks, Doris/BI/AI boundaries, and least-privilege MCP access.

## Official References

- [Apache Superset integration](https://doris.apache.org/docs/4.x/connection-integration/data-integration/superset/)
- [Apache Doris MCP Server](https://doris.apache.org/docs/4.x/key-features/mcp-server/)
- [Vector indexes](https://doris.apache.org/docs/4.x/table-design/index/vector-index/overview/)
- [CREATE VIEW](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/table-and-view/view/CREATE-VIEW/)
