# Module 9: Warehouse Modeling and Joins

| Course Information | Details |
| --- | --- |
| Course | Data Warehousing with Apache Doris · Level 2 |
| Product scope | Apache Doris 4.x; examples use the course's 4.1.3 sandbox |
| Prerequisites | Level 1 orders and customers; Module 8 views |
| Estimated time | About 85 minutes: reading 45, Lab 35, Quiz 5 |

[Level 2 contents](../README.md) · [Open Lab 9](lab9_modeling_and_joins.ipynb) · [Open Quiz 9](quiz9_modeling_and_joins.ipynb)

## Module Goal

A team first queries an order table, then asks for sales by customer region, product category, or date. A join looks easy—until Finance finds that a 100-unit order became 200 units. This module starts with **grain**, the precise meaning of one row. It then connects warehouse layers and fact/dimension modeling to logical join results, physical join plans, and checks that detect duplicate or missing matches.

## Learning Objectives

After this module, you should be able to:

1. State the grain of a fact and a dimension table before joining them.
2. Choose a table model and key based on whether source records append or overwrite current state.
3. Check one-to-one versus one-to-many join cardinality using rows, distinct keys, and amounts.
4. Find missing dimensions with a left join or anti-join.
5. Read join type, distribution, exchanges, and scans in `EXPLAIN` without confusing a plan with actual runtime evidence.

## Module Schedule

| Section | Question | Time |
| --- | --- | ---: |
| 9.1 Warehouse layers | Why keep raw data as well as report-ready data? | 12 min |
| 9.2 Grain and joins | Why can a join double an amount? | 15 min |
| 9.3 Physical joins | Where do matching rows meet? | 10 min |
| 9.4 Acceptance checks | How do we verify keys, rows, and amounts together? | 8 min |
| Lab 9 / Quiz 9 | Build and check the order/customer example | 35 / 5 min |

## 9.1 Give Each Warehouse Layer a Job

Suppose an incoming order has a damaged amount. BI must still publish a valid daily total, while the data team must retain evidence of the rejected record. Keeping only the final aggregate loses that evidence; keeping only raw input makes every report repeat cleaning logic.

| Question | Logical layer | Responsibility |
| --- | --- | --- |
| What did the source actually send? | ODS | Preserve ingested records and source context. |
| Which orders passed validation? | DWD | Clean detail at a declared business grain. |
| What are daily regional totals? | DWS | Reusable aggregates at a declared grain. |
| What does a dashboard query? | ADS | Published consumer results and contracts. |

```text
Source → ODS (raw) → DWD (validated detail) → DWS (aggregates) → ADS (delivery)
             │                  │
             └→ rejected rows   └→ detail drill-down
```

ODS/DWD/DWS/ADS are **modeling conventions**, not four Doris storage engines. Prefixing four tables does not create a trustworthy pipeline. Describe how data is transformed, when each result is refreshed, how rejected records are preserved, and how a failed batch is rerun. A layer may be a table or a view; it need not copy every column.

A star schema keeps facts and shared dimensions separate, improving dimension reuse but requiring carefully checked joins. A wide table can simplify frequent queries at the cost of redundant attributes and more expensive updates. Choose from the actual query and update patterns, not from a universal rule.

## 9.2 Join at the Right Grain

A **fact** records a business process or measure, such as an order amount, item quantity, or payment event. A **dimension** explains it, such as customer name, region, or product category. Grain comes before column selection:

| Object | One row means | Not equivalent to |
| --- | --- | --- |
| Current order | One order's current snapshot | Every state-change event |
| Order item | One item line within an order | A whole-order amount |
| Payment event | One payment action | The order's accumulated paid amount |
| Current customer dimension | One customer's current attributes | All historical attribute versions |

### Why can a customer key appear twice?

A common mistake is to append a source update into a **Duplicate Key** current-state dimension. Suppose a customer changes region from `EAST` to `WEST`: appending both rows means that an order now matches the customer twice. A **Unique Key** table keyed by `customer_id` is the right model for a dimension that should expose only one current row. Duplicate Key remains useful for raw deliveries or intentional history; it does not enforce business-key uniqueness. An Aggregate Key model is for compatible additive aggregates, not a current customer attribute.

The same duplication can come from a manual retry or from storing historical versions without an effective-time rule. If history is required, keep version boundaries such as `valid_from` and `valid_to`, make them non-overlapping for each customer, and join an order to the version that was valid at its business event time. Selecting only `valid_to IS NULL` answers a different question: “What is this customer's **current** region?” It does not reconstruct the region at order time.

### A small counterexample

The following self-contained query has two orders. Customer 1 appears twice in the dimension; customer 2 appears once:

```sql
WITH facts AS (
    SELECT 1 AS order_id, 1 AS customer_id, 100 AS amount
    UNION ALL SELECT 2, 2, 200
), dim AS (
    SELECT 1 AS customer_id, 'EAST' AS region
    UNION ALL SELECT 1, 'WEST'
    UNION ALL SELECT 2, 'EAST'
)
SELECT COUNT(*) AS joined_rows, SUM(f.amount) AS joined_amount
FROM facts f
JOIN dim d ON f.customer_id = d.customer_id;
```

| Order | Amount | Dimension match | Amount after join |
| --- | ---: | --- | ---: |
| 1 | 100 | `EAST` | 100 |
| 1 | 100 | `WEST` | 100 again |
| 2 | 200 | `EAST` | 200 |
| **Total** | **300 before** | **3 joined rows** | **400 after** |

`COUNT(DISTINCT order_id)` would still be 2 and therefore miss the amount inflation. `SUM(DISTINCT amount)` is not a repair: two different orders may legitimately have the same amount, and that expression would count it only once. Instead, compare **row count, distinct order count, and amount** before and after a join, and check the dimension's key separately.

### Missing matches are a separate problem

| Join | Which fact rows survive? | Typical use |
| --- | --- | --- |
| `INNER JOIN` | Only matched combinations | Analyze known customers, but missing orders disappear. |
| `LEFT JOIN` | Every fact row; unmatched dimension columns become `NULL` | Keep all orders and expose missing customers. |
| `FULL OUTER JOIN` | Unmatched rows from both sides | Reconcile two sets. |
| `LEFT SEMI JOIN` | A fact row once if a match exists | Filter to a customer set. |
| `LEFT ANTI JOIN` | Only fact rows without a match | Find missing dimensions. |

After Lab 9, find unmatched customer IDs with a left join:

```sql
SELECT f.customer_id, COUNT(*) AS orders_without_dimension
FROM orders_fact_l2 f
LEFT JOIN customers_dim_l2 d ON f.customer_id = d.customer_id
WHERE d.customer_id IS NULL
GROUP BY f.customer_id;
```

An empty result means all current Lab orders found a customer. Do not use an inner join as this check: it silently removes the very rows you are trying to find. Duplicates and missing matches may occur together, so test them independently.

## 9.3 Separate Join Meaning from Data Movement

The logical join (`INNER`, `LEFT`, and so on) defines which rows appear. The physical strategy determines how Doris moves data to perform the match:

| Strategy | Data movement | When it may help |
| --- | --- | --- |
| Broadcast | Send one side to every relevant node | Small dimension joined to a large fact |
| Shuffle | Redistribute rows by join key | Both sides are large |
| Bucket Shuffle | Reuse an existing compatible distribution on one side | Join and distribution keys align |
| Colocate | Match compatible colocated buckets locally | Tables share a valid colocation layout |

Putting `HASH(customer_id)` in two DDL statements does **not** by itself establish colocation. The course sandbox has one BE and one bucket; it teaches plan interpretation, not a multi-node performance comparison.

Inspect a plan after Lab 9:

```sql
EXPLAIN
SELECT f.order_id, d.customer_name
FROM orders_fact_l2 f
JOIN customers_dim_l2 d ON d.customer_id = f.customer_id;
```

Look for join type, distribution mode, exchange nodes, and scanned objects. `EXPLAIN` describes the chosen plan; **Query Profile** records what happened during actual execution. Neither a plausible plan nor a fast single-node example proves production performance.

## 9.4 Accept a Join with Multiple Checks

Lab 9 builds `orders_fact_l2` and `customers_dim_l2`. The former represents one order snapshot per row in this controlled sample; its Duplicate Key model does not enforce business uniqueness. The latter represents one customer's **current** attributes and uses `UNIQUE KEY(customer_id)`.

Compare before and after a left join:

```sql
SELECT 'before_join' AS stage,
       COUNT(*) AS row_count,
       COUNT(DISTINCT order_id) AS order_count,
       SUM(order_amount) AS amount
FROM orders_fact_l2
UNION ALL
SELECT 'after_left_join',
       COUNT(*),
       COUNT(DISTINCT f.order_id),
       SUM(f.order_amount)
FROM orders_fact_l2 f
LEFT JOIN customers_dim_l2 d ON f.customer_id = d.customer_id
ORDER BY stage;
```

| Stage | Rows | Distinct orders | Amount |
| --- | ---: | ---: | ---: |
| Before join | 10 | 10 | 1400.00 |
| After left join | 10 | 10 | 1400.00 |

Also check that the dimension's customer IDs are unique and the missing-dimension query returns no rows. If the totals differ, determine whether duplicate dimension keys inflated facts or a mistaken inner join dropped them. Passing just one check is insufficient.

## Hands-on Lab: Order Facts and Customer Dimensions

Open [Lab 9](lab9_modeling_and_joins.ipynb) after completing Level 1 Labs 5 and 6 in the same course database. The Lab creates its own `_l2` fact and dimension tables, joins them, checks missing customers, reconciles rows and amounts, and reads the plan.

| Input or result | Expected in this sample |
| --- | --- |
| Fact source | Ten simulated orders from Lab 5 |
| Customer source | WWI customers with IDs 1–20 from Lab 6 |
| Region | A `known` teaching placeholder, not a real geographic classification |
| Fact rows / dimension rows | 10 / 20 |
| Joined rows / amount | 10 / 1400.00 |
| Missing customer matches | 0 |

### Independent exercise

Remove customer 2 from the **counterexample** dimension, which still has two records for customer 1. An inner join returns two matches for order 1 and drops order 2: **2 rows, amount 200**. A left join keeps order 2 with `NULL` dimension fields: **3 rows, amount 400**. This illustrates why duplicates and missing matches can coexist. Check key uniqueness, unmatched facts, joined row counts, and measures separately.

## Module Summary

- Warehouse layers separate raw evidence, validated detail, reusable aggregates, and consumer delivery; names alone do not implement a pipeline.
- Grain is the meaning of one row. Joining to multiple matching dimension rows multiplies a fact's measures.
- A current-state customer dimension needs a key model and process that yield one current row per customer; intentional history needs valid-time rules.
- Inner joins can hide missing dimensions; left joins and anti-joins make them observable.
- Verify joins with unique keys, unmatched rows, row counts, distinct business keys, and amounts.
- Logical join semantics and physical data movement are different; use `EXPLAIN` and Query Profile for different evidence.

## Knowledge Quiz

Open [Quiz 9](quiz9_modeling_and_joins.ipynb) to check grain, table-model choice, join cardinality, missing dimensions, and plan reading.

## Official References

- [JOIN semantics](https://doris.apache.org/docs/4.x/query-data/join/)
- [Table models](https://doris.apache.org/docs/4.x/table-design/data-model/overview/)
- [Colocation Join](https://doris.apache.org/docs/4.x/query-acceleration/colocation-join/)
- [Query Profile](https://doris.apache.org/docs/4.x/query-acceleration/query-profile/)
