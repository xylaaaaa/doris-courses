# Module 6: Data Quality and Schema Validation

| Course Information | Details |
| --- | --- |
| Course | Data Warehousing with Apache Doris · Level 1 |
| Product Version | Apache Doris 4.x |
| Lab Version | Apache Doris 4.1.3 |
| Estimated Time | About 65 minutes, including course notes, hands-on lab, and quiz |

[Course contents](../README.md) · [Open Lab 6](lab6_validate_orders.ipynb) · [Open Quiz 6](quiz6_data_quality_and_rejection.ipynb)

## Module Goal

This module introduces data type validation and business quality rules, and how to preserve and handle invalid records.

After completing this module, you will be able to separate orders into accepted and rejected records, trace rejection reasons, and validate checking rules with known errors.

## Learning Objectives

After completing this module, you should be able to:

1. Distinguish field type validation from business quality rules.
2. Preserve input identifiers and raw fields to trace every rejected record.
3. Use an independent customer dimension and explicit rules to route accepted and rejected data.
4. Check input coverage, business uniqueness, amounts, and row-by-row results together.
5. Use known errors to verify that checks fail, and distinguish offline time criteria from actual freshness.

## Module Schedule

| Section | Learning Format | Suggested Time | Learning Outcome |
| --- | --- | --- | --- |
| 6.1 Schema and Business Quality | Compare fields, schema changes, and rules | 10 minutes | Explain why correct types do not imply business correctness |
| 6.2 Staging and Rejection | Classification SQL and routing results | 13 minutes | Trace raw fields and each rejection reason |
| 6.3 Quality Tests and Validation | Error injection examples | 7 minutes | Prove that checks detect known errors |
| Lab 6 | Hands-on practice | 30 minutes | Complete the 13→10＋3 split and produce accepted input for Module 7 |
| Quiz 6 | Interactive quiz | 5 minutes | Check rules, sources, routing, reconciliation, and validation effectiveness |

## 6.1 Schema and Business Quality

### Two Different Checks

Module 5 already explained that data accepted by an interface is not necessarily ready for business reports.
This section first preserves all raw input, then routes it according to business rules.

| Input | Type check | Business check |
| --- | --- | --- |
| Amount not-a-number | Cannot convert to DECIMAL | Must not enter the accepted table as a normal amount |
| Empty order ID | Cannot obtain a valid integer identifier | Cannot identify the order; reject it |
| Customer ID 999999 | Can convert to an integer | Not in the customer dimension; still reject it |
| Negative amount | Can be a valid decimal | Whether it is allowed depends on the business contract; this sample disallows it |

Doris table field constraints, strict load mode, and this course's SQL quality rules operate at different levels.
Business checks such as dimension joins are implemented with explicit SQL in this course, not automatically by declaring a field type.

### Define the Data Contract for This Batch First

A data contract is a shared agreement between upstream and downstream systems on field meanings and acceptance criteria.
For example, all inputs in this batch are "new orders," so an order ID is required, the amount must be nonnegative, and the customer must be registered.
Expressing these agreements as checks tells downstream systems which data can be used for analysis and which must be returned for processing.

Accepted data must have a usable order ID, a nonnegative amount, a valid customer reference, and a source of
COURSE_SIMULATION. The customer dimension comes from the WWI customer table loaded in Module 5. Do not generate
a temporary "customer list" from the current input, or invalid customers will also be treated as valid.

When field structure changes, recheck column mappings, types, and business rules.
For example, if upstream changes the amount to include tax, the original pretax aggregation rules must change even if the field remains a decimal.
This lab implements the contract as SQL classification rules and result checks.

### When Fields Change, Do the Existing Checks Still Apply?

Schema validation checks whether a batch of input matches the table structure; Schema Change modifies the table structure itself.
For example, after adding a nullable `order_channel`, the value for old data can remain unknown for now, but load mappings and downstream SELECT statements must be checked;
changing an amount from pretax to tax-inclusive requires a new agreement on its meaning even if the type stays the same.

| Change method | Main work | Impact to understand in this section |
| --- | --- | --- |
| Lightweight Schema Change | Supported operations modify metadata only, without rewriting existing data files | Examples include eligible additions of value columns; still check defaults, column mappings, and downstream compatibility |
| Heavyweight Schema Change | Converts or rewrites data files in the background | Some type or column-order changes; monitor job status, resources, and conversion results |

Do not assume all tables use the same path based only on labels such as "add column" or "change type"; consider the target version and table model.
The following shows the operation on a separate copy; do not run it on orders_clean:

```text
ALTER TABLE <separate_copy_table> ADD COLUMN order_channel VARCHAR(20) NULL;
DESC <separate_copy_table>;
```

Before running it, check whether existing writes explicitly name columns; afterward, verify the table definition, the new column values in old rows, and loading of new batches.
For background conversions, use `SHOW ALTER TABLE COLUMN` to inspect job status, then verify the converted data.
Do not confuse successful submission with completed conversion. Full rollout and rollback are covered in Level 3, Module 12.
This lab keeps fields unchanged and focuses on data acceptance. [Schema Change](https://doris.apache.org/docs/4.x/table-design/schema-change/)

## 6.2 Staging and Rejection

### Trace Every Error to Its Source

The raw layer `orders_raw` initially stores business fields as strings and adds a stable input_id.
Original values are not discarded when conversion fails, so you can later explain which row and field had a problem.

Two identifiers are needed here: `input_id` identifies a particular input received in this batch, while `order_id` identifies the business order.
Even if an input lacks an order ID, input_id can still locate the raw record; when the same order arrives repeatedly,
different input_id values also preserve a trace of each arrival.

| input_id | Raw order_id | Raw order_amount | customer_id | Expected destination |
| ---: | --- | --- | --- | --- |
| 1–10 | 900001–900010 | Valid amounts totaling 1400.00 | 1–10 | Accepted |
| 11 | 900012 | not-a-number | 1 | INVALID_AMOUNT |
| 12 | NULL | 100.00 | 1 | INVALID_ORDER_ID |
| 13 | 900013 | 100.00 | 999999 | INVALID_CUSTOMER |

`TRY_CAST` attempts a field type conversion and returns NULL if it fails, making errors easy to identify in routing rules.
For example, `TRY_CAST('not-a-number' AS DECIMAL(18, 2))` returns NULL,
so the classification rule marks the corresponding input as INVALID_AMOUNT; valid amounts pass this check.
The original text remains in orders_raw for reprocessing after correction.
For conversion behavior, see [CAST and TRY_CAST](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/conversion/cast-expr/).
Rules select the first rejection reason in this order: order ID → amount → customer reference → source.
If a row has multiple problems, record the first matching reason; after correcting and reprocessing it, check for remaining problems.

### Express Rules in SQL with CASE

CASE WHEN checks conditions from top to bottom; THEN supplies the matching result, and ELSE applies if none match.
The following view preserves the raw fields and only adds reject_reason. TRY_CAST checks validity;
when data is actually written to the accepted table, the target column types constrain the stored values.

**SQL reading example: corresponds to the classification step in Lab 6. Do not rerun it on a completed lab.**
First prepare orders_raw and the independent customers dimension table in the lab:

<!-- reading-only-example -->
```sql
CREATE VIEW orders_classified AS
SELECT *, CASE
    WHEN TRY_CAST(order_id AS BIGINT) IS NULL THEN 'INVALID_ORDER_ID'
    WHEN TRY_CAST(order_amount AS DECIMAL(12,2)) IS NULL
      OR TRY_CAST(order_amount AS DECIMAL(12,2)) < 0 THEN 'INVALID_AMOUNT'
    WHEN TRY_CAST(customer_id AS BIGINT) IS NULL THEN 'INVALID_CUSTOMER'
    WHEN TRY_CAST(customer_id AS BIGINT) NOT IN (SELECT customer_id FROM customers) THEN 'INVALID_CUSTOMER'
    WHEN data_source IS NULL OR data_source <> 'COURSE_SIMULATION' THEN 'INVALID_SOURCE'
    ELSE NULL END AS reject_reason
FROM orders_raw;
```

In this example, customers.customer_id cannot be NULL; do not apply NOT IN directly to a customer set that might contain NULL.
input_id=11 passes the order ID check before matching the amount rule; input_id=13 has a valid amount,
but its customer reference does not exist, so it matches INVALID_CUSTOMER. The ten normal inputs have NULL reject_reason values.

`orders_classified` is a regular view that stores the classification SQL; querying it runs conversion checks and classification logic.
The view computes reject_reason for every input. Subsequent writes send records with a NULL reason to the accepted table
and records with a reason to the rejected table. Two explicit writes in the lab perform the routing; creating the view alone does not move data automatically.

```text
13 raw input rows in orders_raw
          │ Check against the independent customer dimension
          ▼
Classification view orders_classified (with reject_reason)
          ├─ NULL reason → orders_clean: 10 rows
          └─ Non-NULL reason → orders_rejected: 3 rows, preserving input_id
```

### Two WHERE Clauses Decide the Destination

**SQL reading example: corresponds to the routing step in Lab 6. Do not rerun it on a completed lab.**
The lab first creates empty orders_clean and orders_rejected tables, then performs the following two writes.
The accepted table uses Duplicate Key; rerunning appends data rather than updating existing routing results.

<!-- reading-only-example -->
```sql
INSERT INTO orders_clean (
    order_id,customer_id,order_amount,status,event_version,event_id,
    event_time,paid_amount,refund_amount,region,data_source
)
SELECT order_id,customer_id,order_amount,status,event_version,event_id,
       event_time,paid_amount,refund_amount,region,data_source
FROM orders_classified WHERE reject_reason IS NULL;

INSERT INTO orders_rejected (input_id, reason)
SELECT input_id, reject_reason
FROM orders_classified WHERE reject_reason IS NOT NULL;
```

IS NULL and IS NOT NULL split the same classification result into two mutually exclusive groups: ten accepted rows and three rejected rows.
These writes are not automatically an atomic cross-table transaction; if interrupted between the steps, success of the first step does not mean everything is complete.
This lab preserves static raw input. To redo it, recreate the result tables in the lab's initialization order, then complete both steps and verify them.

After learning CASE, you can write a read-only SELECT to try out a new rule before deciding whether to use it for actual routing.
The lab's independent exercise asks you to add an amount review rule without changing the accepted table used by Module 7.

### Trace Rejected Records Back to Raw Fields

After completing the routing steps in the lab, run:

```sql
SELECT r.input_id, r.order_id, r.order_amount, r.customer_id, x.reason
FROM orders_rejected x
JOIN orders_raw r ON x.input_id = r.input_id
ORDER BY r.input_id;
```

The result should match rows 11, 12, and 13 in the table above. The rejected table stores identifiers and reasons, while the raw table stores original text;
the two are joined by input_id. A temporary ErrorURL does not replace these business records that remain available for long-term queries.

A customer ID that converts successfully but references a nonexistent customer still cannot enter the accepted table.
A NULL source or a source other than COURSE_SIMULATION is also rejected, although the current thirteen-row sample has no additional source-error rows.

## 6.3 Quality Tests and Validation

### Preserving the Total Count Is Only the First Step

```sql
SELECT reject_reason, COUNT(*) AS input_rows
FROM orders_classified
GROUP BY reject_reason
ORDER BY reject_reason;
```

Expect ten rows with a NULL reason and one row for each of the three rejection reasons. Ensure both coverage and no overlap:
an input must not enter both the accepted and rejected tables, and no input may be omitted.

```sql
SELECT COUNT(*) AS orders,
       COUNT(DISTINCT order_id) AS unique_orders,
       SUM(order_amount) AS amount
FROM orders_clean;
```

The query result should be 10, 10, and 1400.00. Next, compare order fields row by row to check that the details match the raw input and business rules.
Detailed checks can reveal differences hidden in aggregates, such as two incorrect amounts that increase and decrease by the same amount, leaving the total unchanged.

| Check level | What this lab verifies |
| --- | --- |
| Input coverage | All 13 inputs have a destination: 10 accepted, 3 rejected |
| Identifiers and relationships | No duplicate order IDs, customers exist, and sources are correct |
| Amounts and statuses | Initial total 1400.00, status CREATED, and zero payments/refunds |
| Time criteria | Event times are non-NULL and do not exceed the fixed business cutoff |
| Complete records | Every field matches the independent sample row by row |

### Deliberately Introduce Errors to Verify That Checks Work

The lab uses two counterexamples to test order ID uniqueness separately: first append an existing order, then restore the data
and change the second row's order ID to the first row's order ID. The second counterexample preserves all amounts, still with ten rows totaling 1400.00,
but contains a duplicate order ID and omits the original second order.

Both counterexamples call the uniqueness check directly, preventing aggregate checks from failing first and obscuring whether the uniqueness rule works.
Each time, display the duplicate order ID, confirm that the uniqueness check fails, then restore from the preserved classified input and run all checks.

```text
Correct input → Checks pass
Appended duplicate / Duplicate with unchanged totals → Uniqueness check fails (expected)
Restore data → Checks pass again → Hand over to Module 7
```

Expected results come from fixed input and business rules; restoration reclassifies the preserved raw data.
This provides an independent basis for judging whether restoration is correct even if the target table was written incorrectly.

The fixed cutoff `2026-01-02 12:00:00` checks event times for this offline sample batch.
Continuous ingestion also requires recording business event time, ingestion time, and observation time
to distinguish late business events, transmission delays, and processing backlogs.

## Hands-on Lab 6: Preserve Input, Route Rejections, and Automate Validation

Before starting, complete Module 5, understand the distinction between load responses and business quality, and use the course's dedicated lab database.

Open [Lab 6](lab6_validate_orders.ipynb) and complete these steps in order:

1. Stage thirteen input rows, including an invalid amount, a missing order ID, and an invalid customer.
2. Explicitly route them into ten accepted rows and three rejected rows, tracing reasons by input_id.
3. Check accepted records row by row, inject duplicate orders to verify that checks fail, then restore the correct data.

### Data Sources and Notes

The historical portion uses Microsoft WWI; new orders and changes are marked COURSE_SIMULATION and reference WWI customers and products without backfilling history.
See [Data notes](../../datasets/README.md) for fields, business definitions, and expected results.

For additional operations, see [Level 1 Extension Labs](../extensions/README.md). They run on separate `ext_*` tables without repeatedly rewriting this lab's business results.

## Module Summary

- Type validation asks whether a value can be parsed; business rules ask whether it belongs in reports. An integer customer ID does not prove the customer exists.
- Preserve input_id and original text to trace rejection reasons; error logs do not automatically become a business rejection table.
- Use Module 5's independent customer dimension and route by order ID, amount, customer, and source rules. This sample has 13 inputs, 10 accepted and 3 rejected.
- Totals, uniqueness, relationships, amounts, and field-by-field comparisons complement each other; one total cannot prove data is complete and correct.
- Known duplicates must cause checks to fail, and restored data must pass again; a fixed cutoff is not a freshness metric for a running system.

## Knowledge Quiz 6: Preserve Input, Route Rejections, and Automate Validation

After completing the course notes and lab, open [Quiz 6](quiz6_data_quality_and_rejection.ipynb).
The quiz contains five single-choice questions and requires no Doris or external services; read the explanations after submitting.

## Official References

- [Stream Load: Type conversion and quality parameters](https://doris.apache.org/docs/4.x/data-operate/import/import-way/stream-load-manual/)
- [CAST and TRY_CAST](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/conversion/cast-expr/)
- [Schema Change](https://doris.apache.org/docs/4.x/table-design/schema-change/)
