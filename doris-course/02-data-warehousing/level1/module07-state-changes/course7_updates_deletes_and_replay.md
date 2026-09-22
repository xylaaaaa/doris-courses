# Module 7: Data Updates, Deletion, and Event Replay

| Course Information | Details |
| --- | --- |
| Course | Data Warehousing with Apache Doris · Level 1 |
| Product Version | Apache Doris 4.x |
| Lab Version | Apache Doris 4.1.3 |
| Estimated Time | About 75 minutes, including course notes, hands-on lab, and quiz |

[Course contents](../README.md) · [Open Lab 7](lab7_current_state_and_replay.ipynb) · [Open Quiz 7](quiz7_state_changes_and_replay.ipynb)

## Module Goal

This module introduces order state updates, duplicate and out-of-order event handling, and methods for retaining history and replaying events.

After completing this module, you will be able to maintain current order state and history using simulated events and verify replay results after an interruption.

## Learning Objectives

After completing this module, you should be able to:

1. Distinguish the keys and purposes of current order state, event history, and raw deliveries.
2. Use business versions to explain the handling of duplicate and out-of-order events.
3. Distinguish partial column updates from full-row writes that omit fields.
4. Distinguish soft deletion, SQL deletion, and physical file reclamation.
5. Verify recovery through repeated replay, row-by-row comparison, and independent business transaction records.

## Module Schedule

| Section | Learning Format | Suggested Time | Learning Outcome |
| --- | --- | --- | --- |
| 7.1 Current State and Updates | Compare table granularities | 5 minutes | Choose keys for current state, history, and deliveries |
| 7.2 Idempotency and Out-of-Order Events | Event timeline | 10 minutes | Explain why late old events do not overwrite newer states |
| 7.3 Merge-on-Write and Partial Column Updates | Compare before and after updates | 10 minutes | Check whether omitted business fields are preserved |
| 7.4 Soft Deletion, SQL Deletion, and Reclamation | Compare visibility | 5 minutes | Distinguish hiding, deletion, and physical reclamation |
| 7.5 History, Replay, and Recovery | Interruption examples and reconciliation | 10 minutes | Explain recovery after an interruption between steps |
| Lab 7 | Hands-on practice | 30 minutes | Verify 11 current orders, 18 history records, and 19 deliveries |
| Quiz 7 | Interactive quiz | 5 minutes | Check states, versions, partial updates, deletion, and recovery |

## 7.1 Current State and Updates

### Business Users Need Both "What Is True Now" and "What Happened"

Operational dashboards need current state, while refund investigations need the historical process.
Keeping only current state loses that process; keeping only history requires selecting the correct version on every query.
This lab separates these two needs:

| Table | What one row represents | Key and purpose |
| --- | --- | --- |
| orders_current | The current state of one order | UNIQUE KEY(order_id), resolved by event_version |
| order_events | One distinct business event | UNIQUE KEY(event_id); redelivering the same event does not add logical history |
| event_deliveries | One delivery within an attempt | Records attempt_id, delivery_id, and raw content, preserving redeliveries |

One order_id can have multiple event_id values, and one event_id may be delivered multiple times.
Here, delivery_id is a delivery identifier, not a shipment tracking number.

### Build Current-State and History Tables from Accepted New Orders

Module 6's `orders_clean` provides ten accepted simulated orders; Module 7 initializes them as
current state and initial history. All have source COURSE_SIMULATION, and the `wwi_*` history tables are not updated.

A Unique Key update changes the logical current value for the same key; it does not mean old physical files are immediately reclaimed.
The current table uses Merge-on-Write (MoW) to handle visibility among versions of the same key on the write side,
making current results easy to read in business queries.

## 7.2 Idempotency and Out-of-Order Events

### Business Order Is Not Arrival Order

The business flow for order 900001 is:

```text
Version 1 CREATED → Version 2 PAID → Version 3 SHIPPED → Version 4 DELIVERED
```

In this lab, however, version 1 is already initialized and subsequent events deliberately arrive out of order:

| Position in first delivery round | event_id | event_version | Event status | Current status after processing |
| --- | --- | ---: | --- | --- |
| 1 | E08 | 4 | DELIVERED | DELIVERED, version 4 |
| 2 | E02 | 3 | SHIPPED | Still DELIVERED, version 4 |
| 3 | E01 | 2 | PAID | Still DELIVERED, version 4 |
| 9 | E02 | 3 | SHIPPED, duplicate delivery | Still DELIVERED, version 4 |

These events carry complete updated states (after-images), not patches containing only changed fields.
The current table configures `event_version` as the Sequence column, comparing business versions for the same order
rather than overwriting with the last message to arrive. The history table still retains all three distinct events.

A complete updated state means version 4 carries not just DELIVERED, but also the amount, customer, payment, and other fields at that time.
Even before versions 2 and 3 arrive, version 4 is sufficient to build the current row. If a message contains only a changed field,
it must be handled with partial-update semantics rather than directly applying the full-row state write method.

The lab displays the actual DDL before the first write. First locate the following key and property fragments:

```text
UNIQUE KEY(order_id)
"enable_unique_key_merge_on_write"="true"
"function_column.sequence_col"="event_version"
```

The first identifies the order, the second enables merge-on-write, and the third specifies the business version column.
Merely naming an ordinary field event_version does not enable version resolution.
Include these settings in the table creation statement for the current order table. The following example uses this configuration and provides the complete order state on each write.

The Sequence column is how Doris compares which record is newer under the same Key.
For order 900001, if version 4 already exists, a late version 2 will not revert the current status to PAID.
This requires upstream to provide comparable versions that express business order for each order;
versions need not be compared across different orders, while same-version conflicts need additional handling rules.

After completing the lab, verify in the same lab database:

```sql
SELECT order_id, status, event_version, paid_amount, refund_amount
FROM orders_current
WHERE order_id IN (900001, 900003)
ORDER BY order_id;
```

| order_id | status | event_version | paid_amount | refund_amount |
| ---: | --- | ---: | ---: | ---: |
| 900001 | DELIVERED | 4 | 100.00 | 0.00 |
| 900003 | REFUNDED | 4 | 150.00 | 150.00 |

### What Counts as a Safe Duplicate?

Idempotency means processing the same thing repeatedly does not change an already correct business result.
This course requires redeliveries with the same event_id to carry identical business content; the same ID with different content is a conflict
and cannot be explained as "overwrite duplicates."

event_version is a teaching version that increases monotonically for each order, not a Kafka offset or Binlog position.
Different content at the same version requires source-defined conflict rules; this lab does not verify automatic resolution of such conflicts.
For specific Sequence column behavior, see [Concurrent update control](https://doris.apache.org/docs/4.x/data-operate/update/unique-update-concurrent-control/).

## 7.3 Merge-on-Write and Partial Column Updates

Merge-on-Write handles visibility between old and new versions of the same key during writes.
For example, when an order changes from CREATED to PAID, ordinary queries read the new logical row directly once the new state is visible;
background compaction gradually consolidates the old versions' data files. Applications can query the current state directly by order ID.

Partial column updates address a different issue: when a change provides only some fields,
Doris preserves unmodified fields on eligible Unique Key tables and merges the supplied values into the current row.

### If Only Three Fields Are Supplied, What Happens to the Others?

Suppose you only need to cancel order 900001 and do not want to resend the entire order.
Whether "omitted fields" means preserving old values or forming a new row using defaults/NULLs and other rules
depends on the update method, not just on leaving a few columns out of INSERT.

The lab demonstrates this on the independent `orders_partial_update` table without changing the main current table:

| Stage | status | event_version | order_amount | region |
| --- | --- | ---: | ---: | --- |
| Initial row | CREATED | 1 | 100.00 | EAST |
| Partial update submits only status and version | CANCELLED | 2 | 100.00 | EAST |

This step temporarily enables `enable_unique_key_partial_update`, writes the order ID, status, and new version,
then restores session settings. The order ID locates the current row, the new version participates in version resolution, and the status is the field to change;
the amount and region are preserved from the existing row. Before using this method, explicitly enable partial updates and understand the target table's support requirements.

**SQL reading example: corresponds to the partial-update step in Lab 7. Do not rerun it on a completed lab.**
The lab first writes the initial row above to the independent table, then runs the following in the same connection:

<!-- reading-only-example -->
```sql
SET enable_unique_key_partial_update = true;
INSERT INTO orders_partial_update (order_id, status, event_version)
VALUES (900001, 'CANCELLED', 2);
```

SET enables partial-update semantics for this session; INSERT supplies the primary key and the two columns to change.
The lab saves the original setting before execution and uses Python's try/finally to restore it after success or failure;
do not enable the setting in another connection or omit the restoration step.

```sql
SELECT order_id, status, event_version, order_amount, region
FROM orders_partial_update
ORDER BY order_id;
```

The result should match the second row in the table. Seeing CANCELLED alone is insufficient; the amount and region must not be cleared.
For applicable table models and configuration requirements, see [Partial column updates](https://doris.apache.org/docs/4.x/data-operate/update/partial-column-update/).

## 7.4 Soft Deletion, SQL Deletion, and Reclamation

### Distinguish Business Markers, Load Markers, and Internal Bitmaps First

| Name | Used by | Meaning |
| --- | --- | --- |
| is_deleted | Business tables and query SQL | Custom soft-delete field that queries must explicitly filter |
| __DORIS_DELETE_SIGN__ | Unique Key load-based deletion path | Expresses deletion for a key; supply the marker according to the load method, rather than assuming that an ordinary business column with the same name completes the configuration |
| Delete Bitmap | Internal MoW engine | Marks physical rows that are no longer visible to queries; also involved when ordinary Upsert overwrites old rows, not only in business deletion |

For example, if the source database deletes order 900002, the synchronization pipeline must convey deletion semantics rather than simply write the order again.
The load deletion marker expresses this operation; the business is_deleted field means "retain the record, but do not display it in the application."
With either method, an ordinary query no longer returning an old row does not prove that the underlying files have been reclaimed.
This lab compares soft deletion and SQL DELETE below; it does not run a load deletion marker experiment.
[Update and deletion mechanisms](https://doris.apache.org/docs/4.x/data-operate/update/update-overview/)

### Three Operations Answer Different Questions

| Operation | Query result | Data meaning |
| --- | --- | --- |
| Set business field is_deleted=true | Ordinary SELECT still sees it; explicit filtering is required | The application decides not to display it anymore |
| SQL DELETE | Ordinary queries no longer return deleted rows | The database changes logical visibility |
| Background physical reclamation | Not a business query condition | Storage files are released when reclamation conditions are met |

The lab's independent copy starts with two rows: 900001 and 900002.
First soft-delete 900001. The table still has two rows, but `WHERE is_deleted=false` returns only 900002.
Then use SQL DELETE to delete 900002; ordinary queries return only 900001 with its soft-delete marker set to true.

**SQL reading example: corresponds to the deletion step in Lab 7. Do not rerun it on a completed lab.**
First let the lab rebuild the independent copy containing only 900001 and 900002, then observe in order:

<!-- reading-only-example -->
```sql
UPDATE orders_delete_demo SET is_deleted=true WHERE order_id=900001;
SELECT order_id FROM orders_delete_demo WHERE is_deleted=false ORDER BY order_id;
DELETE FROM orders_delete_demo WHERE order_id=900002;
```

UPDATE changes only the business marker; the second query needs an explicit filter to see only 900002.
DELETE removes the other order, so subsequent ordinary queries no longer return 900002.

```sql
SELECT order_id, is_deleted, status
FROM orders_delete_demo
ORDER BY order_id;
```

The final query result is 900001, true, CREATED. Background mechanisms release disk space when reclamation conditions are met.
Business soft-delete fields, load deletion markers, and the internal Delete Bitmap operate at different levels;
this lab runs only soft deletion and SQL DELETE.

A refund is not a deletion: order 900003 in the main workflow should retain its payment and refund amounts with status REFUNDED;
do not delete payment facts simply to make net receipts zero.

## 7.5 History, Replay, and Recovery

### An Interruption Can Occur Between Two Writes

This lab simulates an interruption by stopping a course step, not the database process:

```text
Record first delivery → Write history → [Simulated interruption] → Current table not yet written
                                          │
                 Redeliver the entire event batch ←────────┘
                      │
                      ├─ Continue recording raw deliveries
                      ├─ Deduplicate history by event_id
                      └─ Resolve current state by order_id + version
```

Code maintains these tables in separate steps; it does not assume automatic atomic commits across all three.
Recovery must not check only whether "event_id already exists in history," or it could skip an unfinished current-state write.

### Why Are the Three Row Counts Different?

| Check target | Expected count | Derivation |
| --- | ---: | --- |
| Current orders | 11 | Ten initial orders＋one new order |
| Logical history | 18 | Ten initial snapshots＋eight distinct events |
| Raw deliveries | 19 | One before interruption＋two rounds of nine deliveries each |

Duplicate deliveries should add delivery records, not distinct events or changes to the correct current state.

```sql
SELECT 'current' AS record_type, COUNT(*) AS rows_count FROM orders_current
UNION ALL
SELECT 'history' AS record_type, COUNT(*) AS rows_count FROM order_events
UNION ALL
SELECT 'deliveries' AS record_type, COUNT(*) AS rows_count FROM event_deliveries
ORDER BY record_type;
```

### Verify Amounts with an Independent Set of Business Facts

Use the separately recorded items, payments, refunds, and shipment records in `business_events.json` to verify current order state.
Refunds should link to original payments, shipments to orders, and customers and products should exist in the WWI dimensions loaded in Module 5.

```sql
SELECT SUM(order_amount) AS orders_amount,
       SUM(paid_amount) AS paid,
       SUM(refund_amount) AS refunded,
       SUM(paid_amount - refund_amount) AS net_receipts
FROM orders_current;
```

The expected results, in order, are 1510.00, 250.00, 150.00, and 100.00.
Order 900003 still has cumulative payments of 150.00 and cumulative refunds of 150.00; only net receipts are zero.
These are simulated business transactions for teaching, separate from WWI's original account receipts.

This lab uses simulated events from files to practice replay after an interruption in application steps.
Applying this approach to a CDC pipeline also requires source log positions, snapshot transitions, and connector recovery mechanisms
to ensure the required events can be retrieved during recovery. The main course only introduces these prerequisites for real log-position recovery; Lab 7 uses simulated events to verify replay after interrupted application steps and does not require real CDC setup or source-side failure recovery. Optional [Lab 5B](../module05-ingestion/optional5_flink_mysql_cdc.ipynb) uses a real MySQL Binlog to practice controlled Savepoint stop and recovery; it does not cover source database failures, recovery after Binlog loss, or business history retention.

## Hands-on Lab 7: Resolve Out-of-Order Events, Preserve History, and Replay Recoverably

Before starting, complete Module 6 and use the same dedicated course lab database; this lab reads its orders_clean accepted-orders table.

Open [Lab 7](lab7_current_state_and_replay.ipynb). First observe normal updates, duplicates of the same event, and late old versions in an independent table, then proceed to the complete order workflow:

1. Initialize current-state, history, and delivery tables from Module 6's accepted orders.
2. Simulate one interrupted step, then redeliver events in the specified order and replay the entire batch.
3. Verify 11 current order rows, 18 logical history rows, and order statuses and amounts.
4. Use independent business transaction records to verify amounts and customer, product, and event relationships.
5. Perform partial column updates, soft deletion, and SQL DELETE on independent copies, then check the main data.

### Data Sources and Notes

The historical portion uses Microsoft WWI; new orders and changes are marked COURSE_SIMULATION and reference WWI customers and products without backfilling history.
See [Data notes](../../datasets/README.md) for fields, business definitions, and expected results.

For additional operations, see [Level 1 Extension Labs](../extensions/README.md). They run on separate `ext_*` tables without repeatedly rewriting this lab's business results.

## Module Summary

- Store current state by order_id, event history by event_id, and delivery records per attempt; do not mix these three granularities.
- The Sequence column resolves out-of-order events by business version, and redeliveries require identical content; arrival order cannot replace business versions, while log positions locate consumption progress.
- Partial column updates require the appropriate model and configuration. Check both new state and omitted fields, and restore session settings after the lab.
- Soft deletion, SQL DELETE, and physical reclamation differ; retain business facts for refunds rather than deleting orders as a substitute.
- After recovery, verify the 11/18/19 row counts, complete records, and independent business transactions: payments 250.00, refunds 150.00, and net receipts 100.00.

## Knowledge Quiz 7: Resolve Out-of-Order Events, Preserve History, and Replay Recoverably

After completing the course notes and lab, open [Quiz 7](quiz7_state_changes_and_replay.ipynb).
The quiz contains five single-choice questions and requires no Doris or external services; read the explanations after submitting.

## Official References

- [Unique Key primary key model](https://doris.apache.org/docs/4.x/table-design/data-model/unique/)
- [Sequence columns and concurrent update control](https://doris.apache.org/docs/4.x/data-operate/update/unique-update-concurrent-control/)
- [Partial column updates](https://doris.apache.org/docs/4.x/data-operate/update/partial-column-update/)
- [DELETE](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-modification/DML/DELETE/)
- [Compaction principles](https://doris.apache.org/docs/4.x/admin-manual/trouble-shooting/compaction-principles/)
