# Module 14: Resource Isolation and Query Protection

| Course Information | Details |
| --- | --- |
| Course | Data Warehousing with Apache Doris · Level 3 |
| Product scope | Apache Doris 4.x; examples use the single-node course sandbox |
| Prerequisites | Module 12 roles and dashboard delivery; Module 13 monthly partitions |
| Suggested time | About 68 minutes: 30 minutes reading, 30 minutes Lab, 8 minutes Quiz |

[Level 3 contents](../README.md) · [Open Lab 14](lab14_resource_isolation.ipynb) · [Open Quiz 14](quiz14_resource_isolation.ipynb)

## Module Goal

The business intelligence (BI) dashboard published in Module 12 normally refreshes in under one second. During Monday's monthly review, analysts submit detail queries without date filters and several large aggregations. Refresh time rises to 20 seconds, and some dashboard queries time out.

Investigation finds that:

- Dashboard and ad hoc queries use the default `normal` group and compete for memory, central processing unit (CPU) time, and scan threads.
- The group has no practical concurrency restriction or waiting queue under its default configuration.
- Analysts have no administrator-enforced execution limit or scan-scope rule.

Module 12 controlled who could read each object. This module controls resource consumption. Separate dashboard and ad hoc work into Workload Groups, route accounts to the intended groups, apply execution and scan limits, and document observation and rollback in a resource runbook.

### Learning Objectives

After this module, you should be able to:

1. Explain the precedence used to select a query's Workload Group.
2. Predict execution, queuing, or rejection from max_concurrency, max_queue_size, and queue_timeout.
3. Explain where memory and CPU limits apply and what CPU enforcement requires.
4. Route queries with USAGE_PRIV and default_workload_group, and explain why bypass_workload_group is not an isolation boundary.
5. Distinguish the timing and scope of query_timeout, Workload Policy, and SQL Block Rule.
6. Write a resource runbook covering groups, routing, protection rules, observations, and rollback order.

## Module Schedule

| Section | Main question | Suggested time |
| --- | --- | ---: |
| 14.1 Who competes with the dashboard? | Which resources are shared, and how is a group selected? | 5 minutes |
| 14.2 How do groups control concurrency, queues, and memory? | When does a query run, wait, or fail? Where do limits apply? | 9 minutes |
| 14.3 How do BI queries reach the intended group? | What do usage grants, defaults, and queue bypass do? | 6 minutes |
| 14.4 How do you stop excessive queries? | How do timeouts, Workload Policy, and SQL Block Rule differ? | 6 minutes |
| 14.5 How do you write a resource runbook? | How are configuration, evidence, and rollback connected? | 4 minutes |
| Lab 14 | Configure groups and observe queuing and scan rejection | 30 minutes |
| Quiz 14 | Check resource and query-protection decisions | 8 minutes |

## 14.1 Who Competes with the Dashboard?

Dashboard queries and ad hoc analysis have different needs:

| Dimension | Dashboard queries | Ad hoc analysis |
| --- | --- | --- |
| Frequency | High; each refresh triggers several chart queries | Lower, but one query may run for a long time |
| Scan scope | Small, often the latest one or two months | Variable; date filters are easily omitted |
| Latency target | Around one second | Tens of seconds may be acceptable |

When these workloads share a group, large scans can consume memory, CPU, and scan-thread capacity before small dashboard queries obtain what they need.

A Workload Group applies configured limits to a set of queries. Controls operate at two layers:

| Location | Controls | Main properties |
| --- | --- | --- |
| Frontend (FE) | Running queries, queue capacity, and wait time | `max_concurrency`, `max_queue_size`, `queue_timeout` |
| Each Backend (BE) | Group memory, CPU, and scan resources | `max_memory_percent`, `max_cpu_percent`, `scan_thread_num`, `read_bytes_per_second` |

Separate groups keep ad hoc queries from occupying the dashboard group's execution slots and bound the resources controlled by each group. Workload Groups provide isolation within a BE process, where components such as caches and remote procedure call (RPC) thread pools remain shared. They reduce interference but do not guarantee complete latency isolation. [The Workload Group guide](https://doris.apache.org/docs/4.x/admin-manual/workload-management/workload-group/) explains when dedicated nodes are needed instead.

Doris selects a query's group in this order:

1. A query-level `SET_VAR(workload_group=...)` hint.
2. A nonempty session variable `workload_group`.
3. The account property `default_workload_group`.
4. The built-in `normal` group if no earlier option selects one.

All accounts can use `normal`, and it cannot be dropped. Without workload-specific routing, dashboard and analyst queries both land there. Lab 14 does not use query-level routing hints. It first confirms that root's session variable is empty and `SHOW PROPERTY` reports `default_workload_group=normal`.

## 14.2 How Do Groups Control Concurrency, Queues, and Memory?

### Run, queue, or reject?

For the Lab's one-slot-per-query requests, FE makes these decisions:

1. Fewer queries are running than `max_concurrency`: start the query.
2. Running capacity is full but fewer queries are waiting than `max_queue_size`: enqueue it.
3. The queue is also full: reject it with `query waiting queue is full`.
4. The query waits beyond its permitted interval: fail with `query queue timeout`.

Lab 14 sets both concurrency and queue capacity to 1 for ad hoc work. Of three slow queries, the first runs, the second waits, and the third is rejected immediately.

The defaults matter:

| Property | Default | Meaning |
| --- | --- | --- |
| `max_concurrency` | 2147483647 | Effectively unrestricted concurrency |
| `max_queue_size` | 0 | No waiting queue; reject when running capacity is full |
| `queue_timeout` | 0 | Milliseconds; no separate positive queue-wait cap in the course version, so the query timeout bounds waiting |

Setting only `max_concurrency` does not create a queue. Configure `max_queue_size` too if excess requests should wait. A positive `queue_timeout` bounds waiting together with `query_timeout`; the smaller applicable interval wins. Queue timeout is measured in milliseconds, while query timeout is measured in seconds.

Four boundaries affect queuing:

- FE queues queries that scan data. `SELECT 1` and queries confined to `information_schema` do not enter this queue.
- SQL Cache hits return cached results without queuing. With `enable_sql_cache=true`, as in the sandbox, repeated SQL may become cacheable after table data has remained unchanged for roughly 30 seconds.
- `bypass_workload_group=true` skips queuing. Section 14.3 explains the consequence for isolation.
- Each FE has its own counters and queue. Cluster-wide running capacity is the sum of the capacities reached on individual FEs, subject to connection distribution.

Observe `running_query_num` and `waiting_query_num` in `SHOW WORKLOAD GROUPS`. In `information_schema.active_queries`, a queued query has `QUERY_STATUS=WAIT_IN_QUEUE`; a query that obtained its slot is `RUNNING`.

### Where do memory and CPU limits apply?

Memory and CPU properties apply **on each BE**, rather than to one shared cluster-wide allowance:

| Property | Meaning | Default |
| --- | --- | --- |
| `max_memory_percent` | Maximum group memory on one BE, as a percentage of that BE process's `mem_limit` | 100% |
| `min_memory_percent` | Reserved share under memory pressure; a group below this share is protected from group-memory reclamation | 0% |
| `memory_high_watermark` | Threshold relative to the group's maximum at which new memory requests begin failing | 85% |
| `memory_low_watermark` | Threshold below which queries paused for group-memory pressure can normally resume | 75% |
| `max_cpu_percent` | Hard CPU cap, even when CPU is otherwise idle; requires CPU cgroup configuration | 100% |
| `min_cpu_percent` | Minimum CPU share under contention | 0% |

Within the applicable compute group, minimum memory shares must sum to at most 100%, as must minimum CPU shares. Maximums are individual group caps and can sum to more than 100%.

When group memory approaches its limit, memory requests can fail and queries may pause. Doris may spill intermediate data to disk or resume a query after pressure falls. If it cannot recover, it cancels the query with an error containing `memory limit is exceeded while handling workload group memory pressure`.

The path depends on current BE load. Lab 14 configures a memory limit but does not claim to reproduce overload deterministically.

CPU enforcement requires Linux CPU cgroups. If `doris_cgroup_cpu_path` is empty, BE does not create group cgroups; the CPU percentages remain configured values without enforcing CPU consumption. The course sandbox has no such path configured. Memory control uses Doris's own accounting and does not require cgroups.

## 14.3 How Do BI Queries Reach the Intended Group?

Default routing needs two steps.

First, grant the group's `USAGE_PRIV`. Lab 14 grants it to the course role; read the statement here:

<!-- reading-only-example -->
```sql
GRANT USAGE_PRIV ON WORKLOAD GROUP 'course_dashboard_l3'
TO ROLE 'course_dashboard_reader_l3';
```

Second, set the account's default group. This is a reading-only example; Lab 14 does not modify this example account:

<!-- reading-only-example -->
```sql
SET PROPERTY FOR 'bi_dashboard_user' 'default_workload_group' = 'course_dashboard_l3';
```

Either step alone leaves a problem:

| Configuration | Result |
| --- | --- |
| Usage grant without a default or other routing setting | Queries still use `normal` |
| Default group without usage privilege | Queries fail with `Access denied; you need (at least one of) the USAGE/ADMIN privilege(s) to use workload group` |

The privilege check occurs when the query runs, rather than when `workload_group` or `default_workload_group` is set. A session can select an unauthorized group, but its next query is denied.

An ordinary user can change their own `default_workload_group`, yet queries succeed only for groups they can use. Other account properties such as `query_timeout` and `sql_block_rules` require an administrator's `SET PROPERTY FOR`.

The shared `normal` group also needs deliberate production limits. Changes to it affect many accounts. Lab 14 uses dedicated groups.

### Why is queue bypass not an isolation boundary?

An ordinary user can set this session variable:

<!-- reading-only-example -->
```sql
SET bypass_workload_group = true;
```

It skips FE queuing, including `max_concurrency`, `max_queue_size`, and `queue_timeout`. It does not change group selection, bypass `USAGE_PRIV`, or remove BE memory limits.

Queuing is therefore not an enforceable boundary against a user who chooses to bypass it. BE limits, administrator-set execution limits, and SQL Block Rules still apply. Lab 14 demonstrates a query entering execution while the group's ordinary running slot and queue are occupied.

## 14.4 How Do You Stop Excessive Queries?

Group limits control aggregate consumption. A single excessive query also needs a boundary. Doris provides three mechanisms with different timing and scope:

| Mechanism | When it acts | Scope | Outcome |
| --- | --- | --- | --- |
| `query_timeout` | During execution after the time limit | Each query | Cancellation with `query timeout` |
| Workload Policy | During execution when a condition matches | Queries in the associated group, or all queries if no group is specified | An action such as `cancel_query` |
| SQL Block Rule | Before execution | All accounts for a global rule; otherwise the accounts associated with it | Rejection before the scan runs |

### Execution timeout

`query_timeout` is measured in seconds and defaults to 900. A user can increase the session value. An administrator can set the same-named account property, which takes precedence over the session variable and cannot be changed by that user.

This example is for reading only:

<!-- reading-only-example -->
```sql
SET PROPERTY FOR 'adhoc_analyst' 'query_timeout' = '600';
```

Lab 14 uses a two-second session timeout to observe the error. A timeout limits ongoing cost; the query has already consumed resources before it is cancelled.

### Workload Policy

A Workload Policy checks running queries and applies its action when a condition matches. This reading-only example cancels ad hoc queries running for more than 60 seconds:

<!-- reading-only-example -->
```sql
CREATE WORKLOAD POLICY course_adhoc_guard_l3
CONDITIONS (query_time > 60000)
ACTIONS (cancel_query)
PROPERTIES ("workload_group" = "course_adhoc_l3");
```

Consider these properties:

- `query_time` is measured in milliseconds. Other conditions include `be_scan_rows`, `be_scan_bytes`, and `query_be_memory_bytes`.
- FE distributes policies to BEs periodically. BEs check running queries at roughly 500-millisecond intervals, so propagation and cancellation have delays. The cancellation message contains `cancelled by workload policy` and the policy name.
- A policy without `workload_group` applies to all queries, increasing the impact of an incorrect condition.
- A referenced group cannot be dropped until its policy dependency is removed. Inspect policies through `information_schema.workload_policy`.

Lab 14 describes this mechanism without running it because asynchronous propagation makes cancellation timing unsuitable for a deterministic Notebook assertion.

### SQL Block Rule

SQL Block Rules reject matching queries before execution. A rule is either text-based or scan-based:

| Rule type | Properties | Evidence used |
| --- | --- | --- |
| Text | `sql` regular expression or `sqlHash` | Original SQL text |
| Scan | `partition_num`, `tablet_num`, `cardinality` | Partition count, tablet count, or estimated row count for scan nodes in the plan |

Lab 14 limits a scan to two partitions:

<!-- reading-only-example -->
```sql
CREATE SQL_BLOCK_RULE course_scan_guard_l3
PROPERTIES ("partition_num" = "2", "global" = "true", "enable" = "true");
```

`orders_monthly_l3` has three monthly partitions. A scan without a date filter exceeds the limit and fails with `sql hits sql block rule: course_scan_guard_l3, reach partition_num : 2`. The number in the error is the configured limit, not the actual three-partition scan count. A one-month query prunes the scan to one partition and succeeds.

Four details matter:

- `global` defaults to `false`. Administrators associate such a rule with accounts through `sql_block_rules`; ordinary users cannot remove that account-property restriction. A global rule also affects root and administrators.
- Text matching is case-sensitive by default and uses the original SQL. A pattern for `select * from orders_monthly_l3` may miss an uppercase or database-qualified query. Use scan rules when the requirement concerns scan scope.
- Scan rules require an actual scan plan. On a Duplicate Key table, an unfiltered `COUNT(*)` may be answered from FE-cached statistics without scanning partitions. Lab 14 therefore uses `SUM(amount)`.
- A query already in SQL Cache can continue returning cached data without exercising the new scan rule. Disable the session cache with `SET enable_sql_cache = false` or use an uncached query when validating it.

These mechanisms can be combined: reject excessive scans at entry, use Workload Policy to cancel long-running ad hoc work, and enforce an account-level timeout as a per-query limit.

## 14.5 How Do You Write a Resource Runbook?

Resource configuration needs an owner, observable results, and a rollback sequence. An operator should be able to identify each group's purpose, inspect current impact, and remove dependencies in the correct order.

| Runbook section | Lab 14 example |
| --- | --- |
| Groups | Dashboard: concurrency 8, queue 20, wait 10 seconds, memory cap 50%. Ad hoc: concurrency 1, queue 1, wait 30 seconds, memory cap 30%; its configured CPU cap of 30% is unenforced in this sandbox |
| Routing | `course_dashboard_reader_l3` holds dashboard-group `USAGE_PRIV`; production accounts also need default-group configuration |
| Protection | `course_scan_guard_l3` limits scans to two partitions globally; administrators configure production account execution limits |
| Observations | Running and waiting counts, `WAIT_IN_QUEUE` entries, and the exact rejection or timeout messages |
| Rollback | Remove policy dependencies, change account defaults, revoke usage grants, remove unused roles and groups, remove rules, then verify all objects |

The order matters for two reasons. Doris rejects dropping a group referenced by a Workload Policy or an account's `default_workload_group`. Remove those references first.

Dropping a group also does not remove its role grants. Recreating the same group name can make old `USAGE_PRIV` grants appear again in `SHOW ROLES`. Revoke grants explicitly, or remove a dedicated role that has no remaining purpose, before dropping the group.

## Hands-on Lab: Separate Dashboard and Ad Hoc Resources

Open [Lab 14](lab14_resource_isolation.ipynb) and complete these steps:

1. Confirm that the initial query uses `normal`.
2. Rebuild `orders_monthly_l3` with three monthly partitions.
3. Create dashboard and ad hoc groups, and grant dashboard-group usage to the dedicated role.
4. Submit slow queries in multiple sessions; observe running, queuing, rejection, and bypass.
5. Compare queue-wait and execution timeouts.
6. Reject an unfiltered full-table scan with a SQL Block Rule.
7. Revoke usage, remove the role and groups, and verify cleanup.
8. Write a dashboard resource-configuration checklist.

### Prerequisites and Scope

Lab 14 requires the sandbox connection but no Level 1 business tables. It rebuilds `orders_monthly_l3` in the dedicated database and creates two Workload Groups, one role, and one global SQL Block Rule.

Those configuration objects are cluster-wide. The Lab removes leftovers with the same dedicated names at startup and removes its objects at completion.

The global rule exists only within one cell and is deleted in its `finally` block. Interrupting that cell or restarting the kernel can leave the rule behind. Rerun “1. Prepare the table and remove leftover objects” before continuing; run the connection cell first if the kernel was restarted.

The Lab uses root and does not create consumer accounts or modify account properties, so it does not test an ordinary user's denied group access. `sleep()` simulates slow scans. `dw_course.workload` opens additional sandbox sessions and disables their SQL Cache so that the queries actually queue and execute.

The sandbox has one FE and one BE, without CPU cgroup configuration. CPU enforcement, memory-overload recovery, and Workload Policy cancellation remain reading topics.

### Acceptance Criteria

| Check | Expected result |
| --- | --- |
| Initial routing | Empty root session `workload_group`; account default `normal` |
| Groups | Concurrency, queue, wait, and memory settings match the design |
| Role grant | Only dashboard-group `USAGE_PRIV` |
| Queuing and rejection | A runs; B waits then runs; C is rejected; D and E run without waiting |
| Timeouts | Queue failure after roughly one second; execution failure after roughly two seconds |
| Scan rule | Unfiltered `SUM` is rejected; one-month query succeeds; rule is removed before the cell finishes |
| Cleanup | Lab groups, role, rule, and usage grants are gone; `normal` remains unchanged |

## Independent Exercise

A dashboard is going live. Five BI accounts generate about 20 simultaneous queries at peak refresh. Three analyst accounts submit irregular queries with unpredictable scan scope. The cluster has three FEs.

Write a configuration checklist covering:

1. Each group's concurrency, queue capacity, and wait interval, with reasons.
2. Usage grants and account properties that route each workload.
3. The errors for a full queue, excessive queue wait, and excessive execution time.
4. A rule that rejects scans without a sufficient date restriction, and the accounts affected.
5. Rollback order and verification.

<details>
<summary>Reference Explanation</summary>

Queue capacity is per FE. A dashboard concurrency of 8 permits about 24 running queries across three evenly used FEs, enough for a peak of 20. If connections concentrate on one FE, only its eight slots are available to those requests. Verify connection distribution rather than treating 24 as a guaranteed capacity.

Reserve queue space for short refresh bursts and allow a few seconds of waiting. Keep ad hoc concurrency and queue capacity small enough that excessive scans are rejected instead of accumulating on BEs. Use per-BE memory caps; rely on CPU caps only after cgroup enforcement is configured.

Grant BI accounts dashboard-group `USAGE_PRIV` through a role and set their default group. Give analysts usage only on the ad hoc group and make it their default. Selecting the dashboard group does not grant access: the analyst's query is denied without its usage privilege.

A full queue reports `query waiting queue is full`; excessive waiting reports `query queue timeout`; excessive execution reports `query timeout`. Analysts can change their session timeout, so enforce the production execution limit through the administrator-controlled account property. Queue bypass does not remove that limit or a scan rule.

Create a `partition_num` SQL Block Rule and associate it with analyst accounts using `sql_block_rules`. A global rule also affects dashboards and administrators, so verify their scan requirements before choosing that scope.

For rollback, remove Workload Policies referencing the groups, change account defaults to an appropriate remaining group, revoke usage privileges, remove unused roles and groups, and remove obsolete rules. Verify with `SHOW WORKLOAD GROUPS`, `SHOW ROLES`, and `SHOW SQL_BLOCK_RULE`.

</details>

## Module Summary

- Routing precedence is query hint, session group, account default, then `normal`.
- Concurrency, queue capacity, and wait time determine whether ordinary requests run, wait, or fail.
- FE queues and BE resource limits apply per node; CPU enforcement requires cgroups.
- Default routing needs both a usage grant and a default-group setting.
- Queue bypass is available to ordinary users and does not remove usage checks or BE resource limits.
- SQL Block Rules reject before execution; Workload Policy and timeouts cancel ongoing work.
- A resource runbook records groups, routing, protection, observations, and dependency-aware rollback.

## Knowledge Quiz

[Quiz 14](quiz14_resource_isolation.ipynb) contains six scenario-based single-choice questions covering routing precedence, concurrency, queues, BE limits, queue bypass, query protection, and rollback.

## Official References

- [Workload Group](https://doris.apache.org/docs/4.x/admin-manual/workload-management/workload-group/)
- [Concurrency Control and Queuing](https://doris.apache.org/docs/4.x/admin-manual/workload-management/concurrency-control-and-queuing/)
- [Query Circuit Breaking: SQL Block Rule and Workload Policy](https://doris.apache.org/docs/4.x/admin-manual/workload-management/sql-blocking/)
- [CREATE SQL_BLOCK_RULE](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-governance/CREATE-SQL_BLOCK_RULE/)
- [CREATE WORKLOAD POLICY](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/cluster-management/compute-management/CREATE-WORKLOAD-POLICY/)
- [SET PROPERTY](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/account-management/SET-PROPERTY/)
- [active_queries](https://doris.apache.org/docs/4.x/admin-manual/system-tables/information_schema/active_queries/)
- [SQL Cache](https://doris.apache.org/docs/4.x/query-acceleration/sql-cache-manual/)
