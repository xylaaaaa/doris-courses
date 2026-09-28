# Level 2: Data Warehouse Modeling and Delivery

## From Level 1 to Level 2

In Level 1, you loaded ten orders into `orders_imported`, checked data quality, handled state changes and replay, and queried an external Iceberg table through a table-valued function (TVF).

Now imagine that ten orders have become one million. Operations needs daily order counts and amounts; Finance applies a different filter; and a BI dashboard refreshes every five minutes. New requests for sales by customer region, average order value, and stable BI access make the problem more than a collection of SQL queries. **Level 2 teaches you to design data services that BI and AI consumers can use safely and predictably.**

## Learning path

| Module | Core question | Why this comes next | Typical failure |
| --- | --- | --- | --- |
| **8** | How do we share one query definition? | Encapsulate business logic in views. | Teams use different filters and report different totals. |
| **9** | How do we join tables correctly? | Add dimensions to answer regional questions. | A 100-unit order becomes 200 units after a one-to-many join. |
| **10** | How do we define metrics? | Aggregate only after declaring the grain and rules. | Teams calculate different versions of average order value. |
| **11** | How do we publish data? | Give consumers a stable interface after validating metrics. | BI users misinterpret an amount field and build incorrect reports. |

Complete each module in the order **Course → Lab → Quiz**. The course explains the business problem, data grain, and Doris mechanism; the Lab exercises the runnable path; the Quiz checks concepts and trade-offs.

| Module | Topic | Materials |
| --- | --- | --- |
| 8 | Views and materialized views | [Course](module08-views-materialized-views/course.md) · [Lab](module08-views-materialized-views/lab8_views_and_materialized_views.ipynb) · [Quiz](module08-views-materialized-views/quiz8_views_and_materialized_views.ipynb) |
| 9 | Warehouse modeling and joins | [Course](module09-modeling-and-joins/course.md) · [Lab](module09-modeling-and-joins/lab9_modeling_and_joins.ipynb) · [Quiz](module09-modeling-and-joins/quiz9_modeling_and_joins.ipynb) |
| 10 | Metric processing and delivery | [Course](module10-metric-processing/course.md) · [Lab](module10-metric-processing/lab10_metric_processing.ipynb) · [Quiz](module10-metric-processing/quiz10_metric_processing.ipynb) |
| 11 | BI and AI applications | [Course](module11-bi-and-ai/course.md) · [Lab](module11-bi-and-ai/lab11_bi_and_ai_delivery.ipynb) · [Quiz](module11-bi-and-ai/quiz11_bi_and_ai.ipynb) |

## What you will be able to do

- **Design:** Declare fact and dimension grains; choose Duplicate, Unique, or Aggregate Key models; compare star schemas with wide tables.
- **Implement:** Create regular and materialized views, check transparent rewriting, join without duplicating measures, and reconcile an aggregate service table with independent detail queries.
- **Publish:** Define a metric contract (numerator, denominator, grain, filters, freshness), expose a semantic view to BI, prepare a reviewed feature projection for AI, and check freshness, nulls, row counts, and amounts.

## Lab scope and prerequisites

The Labs create only objects with an `_l2` suffix, display query results as tables, and use the dedicated `dw_course_l1_*` database prepared in Level 1. Each Lab checks its input before writing and explains what to do if it is missing.

| Lab | Prerequisite | Input |
| --- | --- | --- |
| Lab 8 | Level 1 Lab 5 | Ten rows in `orders_imported` |
| Lab 9 | Level 1 Labs 5 and 6 | Orders and the `customers` table |
| Lab 10 | Level 1 Lab 5 | `orders_imported` |
| Lab 11 | Level 2 Lab 10 | `daily_order_metrics_l2` |

**Suggested sequence:** Lab 5 → Lab 6 → Lab 8 → Lab 9 → Lab 10 → Lab 11.

The single-node sandbox demonstrates the core path. The reading discusses, but the Notebooks do not claim to complete, Superset chart configuration, MCP Server installation and tool calls, multi-node join comparisons, or large-scale performance tests.

## How the modules connect

**Module 8 → 9:** A view can standardize an order query, but a request for sales by region requires joining the order fact to the customer dimension. Module 9 shows how to avoid turning one 100-unit order into 200 units.

**Module 9 → 10:** After checking joins, teams can still disagree about a metric: an overall amount divided by total orders is not necessarily the simple average of daily averages. Module 10 turns such choices into an explicit metric contract.

**Module 10 → 11:** A checked aggregate service table needs a consumer interface. If `order_amount` means pre-tax order amount rather than money collected, that distinction belongs in the contract before consumers build dashboards. Module 11 publishes a semantic view and states what the sandbox does and does not verify.

## Common questions

### Why does Lab 9 say `orders_imported` is missing?

Complete Level 1 Lab 5 and confirm that you are using the intended `dw_course_l1_*` database.

### Why does `EXPLAIN` still scan the base table after I created a materialized view?

Check that refresh finished (`mv_infos`), the query matches the view's filters and columns, and the relevant rewrite setting is enabled. Creation alone does not prove rewriting.

### Why did the amount double after a join?

Check whether the dimension has more than one matching row per key. In Lab 9, inspect `customers_dim_l2`:

```sql
SELECT customer_id, COUNT(*)
FROM customers_dim_l2
GROUP BY customer_id
HAVING COUNT(*) > 1;
```

### Why did the service-table amount become 2800 instead of 1400?

An Aggregate Key `SUM` column accumulates repeated inserts. In this isolated Lab, rebuild the `_l2` table using the Lab's steps rather than inserting the same source batch twice. Production jobs need an explicit idempotency or replacement strategy.

## Completion checklist

- [ ] State the grain of a fact and a dimension table, and choose an appropriate key model.
- [ ] Explain the trade-off between a star schema and a wide table.
- [ ] Create a regular view and a materialized view; verify any transparent rewrite with `EXPLAIN`.
- [ ] Join facts and dimensions without silently losing or duplicating orders.
- [ ] Build an aggregate service table and reconcile it with an independent detail query.
- [ ] Define a metric's numerator, denominator, grain, filters, and freshness requirements.
- [ ] Publish a semantic view and check freshness, nulls, row counts, and amounts.
- [ ] Use an anti-join, `EXPLAIN`, and Query Profile to investigate incorrect or slow results.

After Level 2, continue to Level 3 for publishing, access control, audit, and storage lifecycle management—or revisit Level 1 with a larger dataset.
