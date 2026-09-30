# Level 3: Permissions, Resources, and Operations

## From Level 2 to Level 3

### What have you learned so far?

- Level 1: query Iceberg tables through a Catalog, join lake and internal tables, load 10 orders into `orders_imported`, reject invalid data, and handle state changes with deletion and replay.
- Level 2: standardize definitions with views and Materialized Views (MVs), join dimensions without changing the intended grain, build `daily_order_metrics_l2` from a metric contract, and deliver `bi_order_metrics_l2` to business intelligence (BI) and artificial intelligence (AI) consumers.

The data can now be queried and reconciled, and consumers have an interface. Level 3 covers what happens after delivery: access, retention, and shared resources.

### What new problems does Level 3 solve?

The first problem is publishing. The BI owner asks for an account before the dashboard launch. Sharing root or granting `SELECT_PRIV ON *.*.*` can produce charts immediately, but both approaches leave unnecessary access:

- A shared root identity permits administrative changes and prevents the audit log from distinguishing the people using it.
- A global read grant exposes detail tables and future objects even when the dashboard needs only one view.
- When the dashboard is retired, its original access scope may be difficult to reconstruct.

The second problem is data growth. An order table contains two years of data. In February 2026, retention requires **the current calendar month and the preceding 12 calendar months**: February 2025 through February 2026. Older complete months must be archived first.

A conditional `DELETE` can remove older orders from query results while their physical files remain. Without a verified recovery source, a mistaken condition can also leave the operator with no dependable recovery path. Calendar-month retention differs from a rolling interval measured backward from today's date.

The third problem is contention. Ad hoc analysis without date filters makes dashboard refreshes rise from under one second to 20 seconds. Both workloads use `normal`, with no workload-specific concurrency, queue, or administrator-enforced execution boundary.

Level 3 turns account delivery, expired-data cleanup, and resource allocation into changes that can be reviewed and verified. Access and resource changes include revocation; data cleanup requires a recovery path before execution.

## Level 3 Learning Path

| Module | Main question | Why now? | Problem addressed |
| --- | --- | --- | --- |
| 12 | How do you deliver a data product with scoped access? | Level 2 has created consumer views | Shared root, broad grants, missing evidence, and unclear revocation |
| 13 | How do you remove expired data and recover mistakes? | Published products continue accumulating data | Confusing logical deletion with reclaimed space, and cleaning up without recovery |
| 14 | How do you keep ad hoc work from overwhelming dashboards? | Consumers now compete for shared resources | Unbounded scans, queue contention, and queries without enforced limits |

### What can you do after Level 3?

- Write a consumer contract and grant only the required object privileges through a dedicated role.
- Explain the different evidence provided by `SHOW GRANTS`, `SHOW ROLES`, change records, and audit logs.
- Retire access by checking dependencies, revoking the appropriate grant or membership, and verifying ordinary-user results.
- Align partitions with retention and write a maintenance runbook covering evidence and recovery.
- Configure Workload Group concurrency, queue, and memory limits, combine query protection mechanisms, and document rollback.

## Module List

Complete each module in the order **Course → Lab → Quiz**. The Course explains the scenario and Doris mechanisms, the Lab executes and verifies them in the sandbox, and the Quiz tests decisions without connecting to a database.

| Module | Topic | Materials |
| --- | --- | --- |
| 12 | Publishing, permissions, and audit | [Course](module12-publishing-permissions-audit/course.md) · [Lab](module12-publishing-permissions-audit/lab12_publishing_permissions_audit.ipynb) · [Quiz](module12-publishing-permissions-audit/quiz12_publishing_permissions_audit.ipynb) |
| 13 | Storage and lifecycle management | [Course](module13-storage-lifecycle/course.md) · [Lab](module13-storage-lifecycle/lab13_storage_and_lifecycle.ipynb) · [Quiz](module13-storage-lifecycle/quiz13_storage_lifecycle.ipynb) |
| 14 | Resource isolation and query protection | [Course](module14-resource-isolation/course.md) · [Lab](module14-resource-isolation/lab14_resource_isolation.ipynb) · [Quiz](module14-resource-isolation/quiz14_resource_isolation.ipynb) |

## Lab Setup

All three Labs connect to a dedicated `dw_course_l1_*` database, creating it if needed, and use objects marked with `_l3`.

Lab 12 creates a view and role, tests view access and base-table denial with a randomly named ordinary user, and removes the user, grants, role, and view afterward. Lab 13 rebuilds `ops_orders_l3` and `ops_orders_drop_l3` to compare truncation, dropping, and recovery. Lab 14 removes leftover course rules, roles, and groups, rebuilds `orders_monthly_l3`, and cleans up its configuration afterward. Each Lab can be rerun.

Roles, Workload Groups, and SQL Block Rules are cluster-wide objects. Lab 14's global rule briefly affects every sandbox session. It is created, checked, and deleted within one cell, with cleanup in `finally`.

### Lab Dependencies

| Lab | Required earlier Lab | Reason |
| --- | --- | --- |
| Lab 12 | Level 1 Lab 5 | Uses 10 `orders_imported` rows totaling 1400.00 as the authorization object |
| Lab 13 | None | Creates its own two `_l3` tables |
| Lab 14 | None | Creates its own table, groups, and role |

Lab 12's independent exercise refers to Level 2 Lab 11's `bi_order_metrics_l2`, but asks you to write a plan rather than execute it.

Suggested order: Level 1 Lab 5 → Lab 12 → Lab 13 → Lab 14.

### What the Sandbox Demonstrates

The Notebooks primarily use root to administer a single-node Doris 4.1.3 sandbox. Lab 12 additionally tests an ordinary consumer's actual access. Lab 13 tests partition cleanup and recovery within recycle-bin retention. Lab 14 tests queuing, queue and execution timeouts, and scan-rule rejection.

The following remain reading topics rather than sandbox-validated results:

- Production consumer-account lifecycle, host scope, credential management, and approvals.
- Lab 14 denial when an ordinary user selects an unauthorized Workload Group.
- Tablet placement and replica repair across multiple Backend (BE) nodes.
- Physical reclamation timing and reload from an archive.
- CPU enforcement without configured cgroups, group-memory overload behavior, and Workload Policy cancellation.
- Independent queues on multiple Frontend (FE) nodes.

## Connections Between Modules

### Module 12 → Module 13

Module 12 delivers a consumer contract, scoped role grants, and release evidence. It also shows how to revoke access without changing the data product.

Orders continue arriving after release, so expired data eventually needs cleanup. A mistaken grant can be revoked; a mistaken data deletion needs a verified recovery source. Module 13 adds partition boundaries, maintenance evidence, and a recovery plan, while separating query visibility from physical space reclamation.

### Module 13 → Module 14

Module 13 establishes how long data remains and how to maintain its partitions. Module 14 addresses the queries competing to read it.

Monthly partitions also support scan protection: a date-filtered query can prune partitions, while an unrestricted scan may exceed a configured partition-count limit. Workload Groups, execution limits, and SQL Block Rules provide different controls, each with its own observation and rollback steps.

## Frequently Asked Questions

### Lab 12 cannot find orders_imported. What should I do?

Complete Level 1 Lab 5 and confirm that the Notebook uses the same `dw_course_l1_*` database.

### The course grants privileges as root. Should production do the same?

Production changes should be made by an approved authorization administrator. Give consumers separate accounts with appropriate host scope and managed credentials. The sandbox uses root for repeatable demonstrations; keep passwords out of Notebooks and course files.

### Why does SHOW PARTITIONS report RowCount as -1 or 0?

`RowCount` and `DataSize` come from periodic BE reports and can lag recent writes. In earlier sandbox observations, they took roughly two minutes to reflect the data. `VisibleVersion` changes immediately. Query the partition when an immediate count is required:

```sql
SELECT COUNT(*) FROM ops_orders_l3 PARTITION (p202501);
```

### Why does disk usage remain after TRUNCATE?

Partition truncation replaces the old partition with a new empty one. The old partition remains in the FE recycle bin until `catalog_trash_expire_second` expires; the sandbox uses the default one-day retention. BE files are deleted asynchronously afterward. Recycle-bin retention is limited and does not replace a backup.

### Are `query waiting queue is full` and `query timeout` Lab failures?

Lab 14 deliberately produces rejection, queue-wait timeout, and execution-timeout errors in steps 3 and 4. Its assertions check the exact outcomes. A `Validation failed` result means an observed outcome differs from the expectation.

### What if a global SQL Block Rule remains after Lab 14 is interrupted?

An interruption or kernel restart can prevent the cell's cleanup from completing. The leftover rule can then reject sandbox scans exceeding two partitions.

Rerun Lab 14's “1. Prepare the table and remove leftover objects.” It deletes the rule before rebuilding the other Lab objects. If the kernel restarted, first rerun the connection cell.

## Level 3 Completion Checklist

### Publishing and Audit

- [ ] Record object, grain, field meanings, freshness, access scope, and owners.
- [ ] Grant only required object privileges through a dedicated role.
- [ ] Distinguish `SELECT_PRIV` from administrative privileges.
- [ ] Explain what grantor grants, role configuration, change records, and audit logs establish.
- [ ] Revoke the correct membership or privilege and verify ordinary-user access.
- [ ] Identify requirements for column privileges, a Row Policy, or masking.

### Storage and Lifecycle

- [ ] Align partition boundaries with retention and query time semantics.
- [ ] Explain how a row belongs to a partition, tablet, replica, and rowset.
- [ ] Record before-and-after table, partition, and tablet evidence.
- [ ] Separate query visibility, metadata changes, and physical reclamation.
- [ ] Write a runbook for the current month plus the preceding 12 calendar months, including a verified recovery path.

### Resource Isolation and Query Protection

- [ ] Explain routing precedence: query hint, session variable, account default, then `normal`.
- [ ] Predict execution, queuing, or rejection from group limits.
- [ ] Explain per-BE memory enforcement and the cgroup prerequisite for CPU limits.
- [ ] Configure usage privileges and defaults, and explain queue-bypass limitations.
- [ ] Distinguish execution timeouts, Workload Policy, and SQL Block Rule.
- [ ] Write a resource runbook with configuration, evidence, and dependency-aware rollback.

For further practice, repeat the Labs in an isolated multi-node environment. Test view-only access and unauthorized group denial with ordinary consumers, inspect tablet replicas on multiple BEs, and observe CPU enforcement and per-FE queues with the required cgroup configuration.
