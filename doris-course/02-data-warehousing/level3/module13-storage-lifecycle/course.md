# Module 13: Storage and Lifecycle Management

| Course Information | Details |
| --- | --- |
| Course | Data Warehousing with Apache Doris · Level 3 |
| Product scope | Apache Doris 4.x; examples use the single-node course sandbox |
| Prerequisites | Level 1 table models and ingestion; Module 12 change evidence and revocation |
| Suggested time | About 78 minutes: 30 minutes reading, 40 minutes Lab, 8 minutes Quiz |

[Level 3 contents](../README.md) · [Open Lab 13](lab13_storage_and_lifecycle.ipynb) · [Open Quiz 13](quiz13_storage_lifecycle.ipynb)

## Module Goal

The `orders` detail table contains two years of data. The retention rule keeps **the current calendar month and the preceding 12 calendar months**. If maintenance takes place in February 2026, retain February 2025 through February 2026; archive and remove complete months ending in January 2025 or earlier.

This is a Duplicate Key table. A colleague runs `DELETE FROM orders WHERE order_date < '2025-02-01'`. The statement returns quickly and queries no longer show those orders, but several questions remain:

- Disk usage barely changes. The delete condition is recorded, while the rows remain in the existing data files.
- Queries must apply the delete condition until background Compaction removes the rows.
- Nobody has a recovery plan if the condition was wrong.

Before maintenance, decide four things: the cleanup boundary, the physical layout, the evidence to record, and the recovery path. This module compares `TRUNCATE` with `DROP/RECOVER` on isolated tables and turns the procedure into a maintenance runbook.

### Learning Objectives

After this module, you should be able to:

1. Choose partition boundaries that match retention rules and query time semantics.
2. Distinguish partitions, buckets, tablets, replicas, rowsets, and segments.
3. Record before-and-after maintenance evidence with SHOW PARTITIONS, SHOW TABLETS, and SHOW CREATE TABLE.
4. Perform partition-level lifecycle operations without clearing the whole table.
5. Distinguish query visibility, metadata changes, physical space reclamation, and the role of Compaction.
6. Write a maintenance runbook covering scope, prechecks, changes, evidence, and recovery.

## Module Schedule

| Section | Main question | Suggested time |
| --- | --- | ---: |
| 13.1 Why clean up by partition? | How does retention determine partition boundaries? | 8 minutes |
| 13.2 Where does a row live? | How do partitions, tablets, replicas, and rowsets relate? | 6 minutes |
| 13.3 What evidence should maintenance retain? | What does each SHOW statement establish? | 6 minutes |
| 13.4 What changes after TRUNCATE? | How do visibility, metadata, and physical space differ? | 6 minutes |
| 13.5 How do you write a maintenance runbook? | What scope, checks, evidence, and recovery steps are required? | 4 minutes |
| Lab 13 | Compare TRUNCATE and DROP/RECOVER on isolated tables | 40 minutes |
| Quiz 13 | Check lifecycle decisions | 8 minutes |

## 13.1 Why Clean Up by Partition?

Before writing cleanup SQL, answer four questions:

| Question | Example answer for order details |
| --- | --- |
| What does one row represent? | One order |
| How long is it retained? | The current month and the preceding 12 calendar months; February 2025 through February 2026 in this example |
| Which time determines expiry? | The order date, `order_date`, rather than ingestion time |
| How can deleted data be restored? | A verified archive or replayable upstream batch; the recycle bin is a temporary emergency option |

The third answer determines the partition key. If partitions use ingestion time, a January order arriving in February enters February's partition. Dropping January's partition misses it, and a filter on `order_date` does not align with partition pruning.

Partition boundaries should match both retention and query time semantics. A rolling window measured backward from today's date is a different rule. Deleting one **complete** monthly partition cannot implement that daily boundary exactly, so agree on the time rule first.

Partition granularity determines how much data a monthly cleanup affects:

| Partition design | How to remove January 2025 | Scope |
| --- | --- | --- |
| Monthly | `DROP PARTITION` for expired months; `TRUNCATE ... PARTITION` when retaining the boundary for reload | January only; adjacent months are unaffected |
| Yearly | Conditional `DELETE` in the 2025 partition | The delete predicate belongs to the whole annual partition, so queries for February through December also apply it |
| Unpartitioned | Conditional `DELETE` on the table | Queries on the table must apply the delete predicate |

On a Duplicate Key table, a conditional `DELETE` does not immediately rewrite the data files. It creates a version containing a delete predicate. Subsequent queries apply that predicate until Compaction merges the data and removes the affected rows. Accumulating predicates can add query overhead.

For such a delete, `SHOW DELETE` can show the table, partition, condition such as `order_date LT "2025-02-01"`, and state `FINISHED`; the affected tablet's version also advances. Lab 13 does not execute this delete. See [Delete Operation](https://doris.apache.org/docs/4.x/data-operate/delete/delete-manual/) for the semantics.

With monthly partitions, two cleanup operations have different purposes:

| Statement | Partition definition | Suitable use |
| --- | --- | --- |
| `TRUNCATE TABLE ... PARTITION (p202501)` | Retained; the month can be reloaded | Clear and rebuild the month's contents |
| `ALTER TABLE ... DROP PARTITION p202501` | Removed with the partition | Remove an expired month after its archive has been verified |

Lab 13 compares these operations. It is not a complete rolling-retention job: it does not archive data, schedule cleanup, or measure physical space reclamation. A production runbook must also specify the cutoff month, archive validation, late-arriving data, and whether the expired partition should disappear or remain empty.

Dynamic Partitioning can automate rolling cleanup. Setting `dynamic_partition.start` enables removal of historical partitions outside the configured range; by default, without such a setting, historical partitions are not deleted. See [Dynamic Partitioning](https://doris.apache.org/docs/4.x/table-design/data-partitioning/dynamic-partitioning).

Whether cleanup is manual or automatic, verify that the archived data is readable before deleting a partition.

## 13.2 Where Does a Row Live?

The business request refers to January orders, but Doris manages their physical data as tablets and rowsets. Follow one Lab 13 order through the layout:

| Layer | Placement of order 130001: 2025-01-15, PAID, 100.00 | Operational concern |
| --- | --- | --- |
| Table | `ops_orders_l3` | Model, privileges, and owner |
| Partition | The date is below `2025-02-01`, so it enters `p202501` | Pruning, retention, and cleanup scope |
| Bucket / Tablet | `HASH(order_id)`; `BUCKETS 1` gives this partition one tablet | Parallelism, skew, and tablet count |
| Replica | `replication_num=1`; the single Backend (BE) stores one replica of the tablet | Replica count, placement, and health |
| Rowset | This `INSERT` adds a version represented by an immutable rowset | Version count and Compaction pressure |
| Segment | Column-oriented data files within a rowset | Scan and index implementation; rarely manipulated directly during routine maintenance |

January's orders live in the tablets belonging to `p202501`. Operating on that partition leaves February's and March's tablets outside the cleanup scope.

Tablet and replica counts follow from the layout:

| Table | Partitions | Buckets per partition | Replicas | Tablets: partitions × buckets | SHOW TABLETS rows: tablets × replicas |
| --- | ---: | ---: | ---: | ---: | ---: |
| Lab 13's `ops_orders_l3` | 3 | 1 | 1 | 3 | 3 |
| Example production table retaining 13 months | 13 | 8 | 3 | 104 | 312 |

Each `SHOW TABLETS` row represents a replica. The production example has 312 rows, which makes partition-scoped inspection useful.

Too few buckets can produce large tablets and limit scan parallelism. Too many can produce small tablets with higher metadata and scheduling overhead. One BE, one replica, and a few sample rows illustrate the relationships but do not determine a production bucket count. See [Partitioning and Bucketing](https://doris.apache.org/docs/4.x/key-features/partitioning-and-bucketing/).

## 13.3 What Evidence Should Maintenance Retain?

A mistaken grant can be revoked. A mistaken cleanup does not have an equivalent always-available undo statement. Record the current state before maintenance and run the same checks afterward.

### SHOW PARTITIONS: boundaries, identity, and versions

```sql
SHOW PARTITIONS FROM ops_orders_l3 ORDER BY PartitionName;
```

Each row represents a partition. Record `PartitionName` and `Range` for names and boundaries, `PartitionId` for identity, `VisibleVersion` for the current visible version, and `State`, normally `NORMAL`.

`PartitionId` changes after `TRUNCATE`. `VisibleVersion` changes immediately after writes. `RowCount` and `DataSize`, however, come from periodic BE reports. In the course sandbox, reports observed after ingestion can temporarily show -1 or 0 before reflecting the new data; the earlier experiment took roughly two minutes. That timing is an observation, not a freshness guarantee. For an immediate row-count check, query the partition:

```sql
SELECT COUNT(*) FROM ops_orders_l3 PARTITION (p202501);
```

### SHOW TABLETS: tablet and replica placement

```sql
SHOW TABLETS FROM ops_orders_l3 PARTITION (p202501);
```

Each row represents a replica, and the output has no partition column. Without the `PARTITION` clause, tablets from all partitions appear together. Record `TabletId`, `BackendId`, `Version`, and `State`.

`RowCount`, `LocalDataSize`, and `VersionCount` also depend on BE reports and may lag a recent change. Data-size fields have different meanings in storage-compute coupled and storage-compute decoupled deployments, so establish the deployment mode before interpreting them.

### SHOW CREATE TABLE: the table's design contract

`SHOW CREATE TABLE ops_orders_l3` records the Key model, partition boundaries, distribution, replica count, and Dynamic Partitioning settings. Save it before maintenance to verify that the actual boundaries match the intended scope.

### What can each observation establish?

| Evidence | What it can establish | What it cannot establish |
| --- | --- | --- |
| `SHOW PARTITIONS` | Partition definitions, boundaries, versions, and states | An immediate exact row count; reporting can lag |
| `SHOW TABLETS` | Tablet and replica placement and reported versions | That files for an absent tablet have already been deleted from disk |
| `SHOW CREATE TABLE` | Key model, partitioning, distribution, and replicas | That historical data is archived or Compaction has completed |
| Partition `COUNT(*)` | Rows visible to the current query | That physical space has been reclaimed |

See [SHOW PARTITIONS](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/table-and-view/table/SHOW-PARTITIONS) and [SHOW TABLET](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/table-and-view/data-and-status-management/SHOW-TABLET/).

## 13.4 What Changes After TRUNCATE?

Lab 13 executes the following statement; read it here:

<!-- reading-only-example -->
```sql
TRUNCATE TABLE ops_orders_l3 PARTITION (p202501);
```

The resulting changes occur at different stages:

| Layer | Observation | Timing |
| --- | --- | --- |
| Query result | Only February and March remain: two rows totaling 500.00 | Immediate |
| Partition metadata | New `PartitionId` and `TabletId` for `p202501`, with `VisibleVersion=1`; adjacent partitions are unchanged | Immediate |
| Physical storage | The old partition is retained in the FE recycle bin and its files remain on disk | Removal follows recycle-bin expiry and asynchronous cleanup |

### Why does the partition ID change?

`TRUNCATE` replaces the target with a new empty partition of the same name. The old partition and its tablets enter the Frontend (FE) recycle bin. It does not process each row or record a conditional delete predicate, so queries stop seeing the old data without waiting for Compaction.

Inspect retained entries with:

```sql
SHOW CATALOG RECYCLE BIN WHERE NAME = 'p202501';
```

Repeated Lab runs can leave several entries with the same name, one for each truncation.

### When is disk space released?

The FE setting `catalog_trash_expire_second` controls recycle-bin retention; its default is 86400 seconds, or one day. After expiry, FE removes the retained partition metadata and BE files are cleaned up asynchronously. This describes the storage-compute coupled course sandbox. Storage-compute decoupled deployments use the Recycler service and have different reclamation procedures.

The recycle bin has an expiry and does not replace a backup. After `TRUNCATE`, the new empty partition already occupies the old name and range, so a direct `RECOVER PARTITION` fails because the partition exists.

Recovery can still be possible within the recycle-bin retention period. In the Doris 4.1.3 course sandbox, pause writes, verify that the replacement partition is empty, record the old `PartitionId`, remove the empty replacement, and recover the old partition. If the replacement already contains new data, removing it would lose those writes; plan a merge or rebuild from an archive instead. Validate this procedure for the target version and deployment.

`TRUNCATE ... FORCE` skips recycle-bin retention. The durable recovery source should be an archive or upstream batch verified before maintenance.

### How does Compaction relate to TRUNCATE?

Compaction is a background BE operation that merges rowsets within a tablet into fewer, larger files. It also removes rows covered by conditional delete predicates. That is why the module's opening `DELETE` can change query results before disk usage decreases.

`TRUNCATE` replaces the partition and removes its old tablets from queries, independently of Compaction. Compaction status therefore does not establish whether truncation succeeded.

Assess production Compaction pressure using `VersionCount`, Compaction score, ingestion frequency, and query load. Small-sample execution times do not establish production performance. Lab 13 does not manually trigger Compaction. See [Truncate Operation](https://doris.apache.org/docs/4.x/data-operate/delete/truncate-manual/) and [Data Compaction](https://doris.apache.org/docs/4.x/key-features/data-compaction/).

## 13.5 How Do You Write a Maintenance Runbook?

The next operator needs more than “clear January.” Specify the table and partition, prechecks, success evidence, and recovery steps before execution.

| Runbook section | Lab 13 example |
| --- | --- |
| Scope | Only `ops_orders_l3.p202501`; leave other partitions and tables unchanged |
| Prechecks | Partition exists; its count is 1, order 130001 worth 100.00; whole-table count is 3. Record each partition's `PartitionId` and `VisibleVersion`, and January's `TabletId`. Production also needs a verified archive and approval |
| Change | `TRUNCATE TABLE ops_orders_l3 PARTITION (p202501)` |
| Evidence | Two remaining rows total 500.00; January's `PartitionId` changes; February and March keep their IDs and visible versions |
| Recovery | The experiment can reload `(2025-01-15, 130001, PAID, 100.00)`; production reloads the partition from its verified archive or upstream batch |

Verify recovery before cleanup: read the archived data and reconcile its rows with the target partition. Do not wait for a mistaken deletion to discover that the archive is unusable. Recycle-bin recovery is a time-limited emergency option in addition to this precheck.

## Hands-on Lab: Partition Lifecycle on Isolated Tables

Open [Lab 13](lab13_storage_and_lifecycle.ipynb) and complete these steps:

1. Create `ops_orders_l3` with three monthly partitions in the dedicated database.
2. Insert one row per month for January through March and check the business rows.
3. Record `SHOW PARTITIONS`, `SHOW TABLETS`, and `SHOW CREATE TABLE`.
4. Clear only `p202501` and confirm that February and March remain.
5. Compare partition IDs, versions, and per-partition counts with assertions.
6. On a second isolated table, drop January without `FORCE`, then recover it within recycle-bin retention.
7. Write a runbook for retaining the current calendar month and the preceding 12 calendar months.

### Prerequisites and Scope

Lab 13 needs only the course sandbox connection. It rebuilds `ops_orders_l3` and `ops_orders_drop_l3`: the first demonstrates partition truncation, and the second demonstrates `DROP/RECOVER` without `FORCE`. Both names end in `_l3`. The sample partition names belong to these Lab tables.

### Acceptance Criteria

| Check | Expected result |
| --- | --- |
| Initial data | Three rows in January, February, and March 2025 |
| Partition evidence | All three monthly partitions exist; their `PartitionId` and `VisibleVersion` values are recorded |
| Tablet evidence | Three `SHOW TABLETS` rows: one replica per partition |
| Cleanup scope | January alone is empty; two rows totaling 500.00 remain |
| Metadata changes | January receives a new partition ID; the other IDs remain unchanged |
| DROP/RECOVER comparison | January disappears from the second table, then returns with its original row within recycle-bin retention |
| Interpretation | Query visibility, metadata changes, and physical reclamation are distinguished |

The Notebook compares partition IDs and row counts automatically. To compare tablet IDs as well, run `SHOW TABLETS FROM ops_orders_l3` after truncation. The single-node sample does not measure production space-reclamation timing.

## Independent Exercise

Apply the Lab's boundaries and acceptance method to a production order-detail table. Retain **the current calendar month and the preceding 12 calendar months**, archiving and removing one expired complete month each month. Monthly data volumes vary greatly.

Write a short runbook covering:

1. The partition key and boundaries.
2. The partition, tablet, and archive evidence to save before maintenance.
3. Why whole-table `TRUNCATE` is outside scope, and whether an expired partition should be dropped or truncated.
4. Verification of the logical result.
5. The roles of the recycle bin and archive after mistakenly removing a month that must remain.

<details>
<summary>Reference Explanation</summary>

Partition by complete calendar months using `order_date`. For maintenance in February 2026, retain February 2025 through February 2026 and remove January 2025 and earlier. A rolling interval measured backward from today's date has a different boundary.

Different monthly volumes may justify different bucket counts when adding partitions; they do not change the monthly retention boundaries.

Before maintenance, save the target's `SHOW PARTITIONS` row, including ID, range, and visible version; save `SHOW TABLETS ... PARTITION (...)` and a partition `COUNT(*)`. Verify that the month's archive is readable, its rows reconcile, and the change is approved.

Whole-table `TRUNCATE` exceeds scope. The Lab truncates a partition to retain a boundary for reload. For an archived month that has expired under production retention, `DROP PARTITION p202501` removes the obsolete definition instead of leaving an empty partition indefinitely.

After a production drop, `SHOW PARTITIONS` should omit `p202501`, while adjacent months' counts match their recorded values. Do not query a partition that no longer exists. After the Lab's truncation, January still exists, its count is zero, and its partition ID changes.

For recovery, recreate the month and reload a verified archive or upstream batch, then reconcile against the pre-maintenance evidence. Within recycle-bin retention, also evaluate `RECOVER PARTITION`. A truncated partition has a same-name replacement: verify that it contains no new writes before removing that conflict. A dropped partition requires identification of the correct retained partition ID. Record the decision not to use `FORCE` when retaining this emergency option.

</details>

## Module Summary

- Align partition boundaries with retention and query time semantics.
- Distinguish calendar-month retention from a daily rolling window.
- Rows enter partitions, tablets, replicas, rowsets, and segments; partition-level maintenance affects only the target partition's tablets.
- SHOW statements describe different layers. Use a partition query for an immediate row-count check.
- Truncation keeps an empty partition for reload; rolling expiry usually removes the partition.
- Query visibility, recycle-bin retention, and physical reclamation are separate stages.
- Compaction merges rowsets and applies delete predicates independently of truncation.
- Verify the recovery path before performing the change.

## Knowledge Quiz

[Quiz 13](quiz13_storage_lifecycle.ipynb) contains six scenario-based single-choice questions covering retention boundaries, physical-layout evidence, partition operations, logical visibility, physical reclamation, and maintenance runbooks.

## Official References

- [Partitioning and Bucketing](https://doris.apache.org/docs/4.x/key-features/partitioning-and-bucketing/)
- [Dynamic Partitioning](https://doris.apache.org/docs/4.x/table-design/data-partitioning/dynamic-partitioning)
- [SHOW PARTITIONS](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/table-and-view/table/SHOW-PARTITIONS)
- [SHOW TABLET](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/table-and-view/data-and-status-management/SHOW-TABLET/)
- [Delete Operation](https://doris.apache.org/docs/4.x/data-operate/delete/delete-manual/)
- [Truncate Operation](https://doris.apache.org/docs/4.x/data-operate/delete/truncate-manual/)
- [SHOW CATALOG RECYCLE BIN](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/recycle/SHOW-CATALOG-RECYCLE-BIN)
- [Data Compaction](https://doris.apache.org/docs/4.x/key-features/data-compaction/)
