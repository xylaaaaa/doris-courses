# Module 12: Publishing, Permissions, and Audit

| Course Information | Details |
| --- | --- |
| Course | Data Warehousing with Apache Doris · Level 3 |
| Product scope | Apache Doris 4.x; examples use the single-node course sandbox |
| Prerequisites | Level 1 order tables; the Level 2 consumer view is used only in the independent exercise |
| Suggested time | About 118 minutes: reading 40, Lab 70, Quiz 8; first-start image downloads/builds are additional |

[Level 3 contents](../README.md) · [Open Lab 12](lab12_publishing_permissions_audit.ipynb) · [Open Quiz 12](quiz12_publishing_permissions_audit.ipynb)

## Module Goal

Level 2 ended by publishing the semantic view `bi_order_metrics_l2`. The business intelligence (BI) owner now asks: “The dashboard goes live next week. Can you give us an account?”

Two quick approaches create problems later:

- Share the root password. BI users can now drop tables and change permissions. The audit log records root, so it cannot distinguish the people using that account.
- Create an account with `SELECT_PRIV ON *.*.*`. The dashboard needs one view, but the account can read every detail table, including tables created later.

When the dashboard is retired a few months later, nobody remembers which permissions were granted or which ones should be removed.

This module breaks account delivery into four steps: define the data product, grant only the required privileges through a dedicated role, retain evidence that another person can check, and revoke access when the product is retired.

### Learning Objectives

After this module, you should be able to:

1. Plan a validated publication cutoff and distinguish safe rollback from a stale retained copy.
2. Distinguish users, roles, privileges, and object scopes, including data access and administrative privileges.
3. Grant only the required object privileges through a dedicated role.
4. Retain release evidence using SHOW GRANTS, SHOW ROLES, and a change record, and distinguish it from audit logs.
5. Distinguish revoking role membership from revoking a role's privileges, and verify the effect of each.
6. Decide when table privileges need column privileges, a Row Policy, or data masking.

## Module Schedule

| Section | Main question | Suggested time |
| --- | --- | ---: |
| 12.1 What does BI actually need? | How do object, grain, and field meanings become a contract? | 7 minutes |
| 12.2 How much access should you grant? | How do roles, privilege types, and object scopes differ? | 8 minutes |
| 12.3 How do you prove the grant is sufficient and scoped? | What can each piece of release evidence establish? | 6 minutes |
| 12.4 How do you retire dashboard access? | What should be revoked, and who is affected? | 5 minutes |
| 12.5 What if table privileges are too broad? | When do you need column privileges, a Row Policy, or masking? | 4 minutes |
| Lab 12 | Existing foundations and extended core evidence | 70 minutes |
| Quiz 12 | Check publishing and access-governance decisions | 8 minutes |

## 12.1 What Does BI Actually Need?

Before creating an account, identify the object the dashboard must read. The course provides two candidates:

| Candidate object | What one row represents | Contents |
| --- | --- | --- |
| `orders_imported` | One order | Customer, amount, status, event time, paid and refunded amounts, region, and other detail fields; 10 rows total 1400.00 |
| `bi_order_metrics_l2` | One day | `order_date`, `order_count`, `gross_amount`, and `average_order_amount` |

If the dashboard reads the detail table directly, each chart must repeat the aggregation logic. An upstream field change can then alter dashboard calculations. The Level 2 semantic view provides a stable interface, so that view is the object to deliver for this dashboard.

Once the object is chosen, record a consumer contract. Each item prevents a common misuse:

| Contract item | Example for `bi_order_metrics_l2` | What can go wrong if it is missing? |
| --- | --- | --- |
| Object | The `bi_order_metrics_l2` view | BI connects to a different object with a similar name |
| Grain | One row represents one day | BI averages daily average order amounts again, producing a different value from the overall average |
| Field meanings | `gross_amount` is simulated pre-tax order value, not cash received | The dashboard labels it as revenue |
| Freshness | Updated after each processing batch completes | A data delay is mistaken for a system failure |
| Consumer and access scope | BI dashboard; read this view only | Detail-table access is granted along with the view |
| Owners | Data product owner, BI owner, and approver | Nobody knows who should investigate a problem or approve retirement |
| Acceptance evidence | Row counts, totals, date coverage, and grant records | Another person cannot verify the release |

Write the contract before granting access. The object and scope in the grant statement come directly from the “Object” and “Consumer and access scope” rows.

To reduce prerequisites, Lab 12 first demonstrates table-level authorization on Level 1's `orders_imported`. It then creates `course_bi_orders_view_l3`, narrows the role to that view, and verifies with an ordinary user that the base table is inaccessible. Level 2 is not required for the Lab; the independent exercise applies the same procedure to `bi_order_metrics_l2`.

## 12.2 How Much Access Should You Grant?

### Why grant privileges to a role?

Five people on the BI team need this dashboard. Direct grants to individual users require five copies of the same configuration. Staff changes make it easy to leave access behind, and new employees lack a clear role to request.

Doris built-in authorization follows **privileges → roles → users**. A privilege describes an allowed operation on an object. A role names a reusable set of privileges. Users obtain those privileges through role membership. Staff changes can therefore be handled by changing membership, while the role provides a common scope for grants, revocation, and review.

Lab 12 creates `course_bi_reader_l3`, briefly assigns it to a randomly named test user, and removes the user after testing.

### Which privileges does a dashboard need?

| Privilege | Capability | Needed by the BI dashboard? |
| --- | --- | --- |
| `SELECT_PRIV` | Read data within the granted scope | Yes |
| `LOAD_PRIV`, `ALTER_PRIV`, `DROP_PRIV` | Write or delete data, change table structure, or delete objects | No; this dashboard is read-only |
| `GRANT_PRIV` | Delegate privileges and manage users or roles | No; BI should not expand its own access |
| `ADMIN_PRIV` | Administrative capabilities, including reading and granting access, but excluding node operations | No |
| `NODE_PRIV` | Add, remove, and manage Frontend (FE) and Backend (BE) nodes | No |

These privileges have different responsibilities. `GRANT_PRIV` does not itself grant read access, and `SELECT_PRIV` does not permit delegation. `ADMIN_PRIV` includes read access but excludes `NODE_PRIV`; granting it to read one table gives the consumer far more capability than required.

The grantor needs the appropriate `GRANT_PRIV` or administrative privilege. In Doris 4.x, a delegated grantor must also hold the object privilege being delegated; `GRANT_PRIV` alone does not permit granting `SELECT_PRIV` on an arbitrary table. The course uses root to make authorization experiments repeatable in a personal sandbox.

### How much does the SELECT_PRIV scope matter?

Even when the privilege is only `SELECT_PRIV`, the scope after `ON` determines which objects become readable:

| Grant scope | Coverage | Effect on future objects |
| --- | --- | --- |
| `*.*.*` | All databases and tables in all Catalogs | New objects are automatically readable |
| `internal.*.*` | All databases and tables in the internal Catalog | New internal objects are automatically readable |
| `internal.<db>.*` | All tables and views in one database | New tables in that database are automatically readable |
| `internal.<db>.<table>` | One table or view | Other new objects are unaffected |
| `SELECT_PRIV(col1, col2) ON internal.<db>.<table>` | Named columns in one table | New columns are outside this grant |

If the dashboard needs one object, grant that object. Lab 12 executes the following form; read it here rather than running it alongside the Lab:

<!-- reading-only-example -->
```sql
GRANT SELECT_PRIV
ON internal.dw_course_l1_demo.orders_imported
TO ROLE 'course_bi_reader_l3';
```

Lab 12 first runs `CREATE ROLE IF NOT EXISTS course_bi_reader_l3` and generates the object name from `lab.database`, so your database name may differ. In production, an approved authorization administrator should perform the change. Consumers need separate identities, appropriate host scopes, and managed credentials.

See [Built-in Authorization](https://doris.apache.org/docs/4.x/admin-manual/auth/authorization/internal/), [GRANT TO](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/account-management/GRANT-TO), and [SHOW PRIVILEGES](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/account-management/SHOW-PRIVILEGES/) for syntax and privilege definitions.

## 12.3 How Do You Prove the Grant Is Sufficient and Scoped?

Three months after release, a reviewer asks: Who made the change? What was granted? Why? How did the role change? “The SQL succeeded” does not answer those questions.

Lab 12 deletes its dedicated role at startup, so it records a **baseline after reset**. It does not capture that role's earlier history. A real change must record the original configuration before modifying it.

| Check | SQL or observation in Lab 12 | Question answered |
| --- | --- | --- |
| Identity | `SELECT CURRENT_USER(), DATABASE()` | Who is executing the change, and in which database? |
| Object | `SELECT COUNT(*), SUM(order_amount) FROM orders_imported` | Does the base table contain the expected 10 rows totaling 1400.00? |
| Grantor privileges | `SHOW GRANTS` | What privileges does the current user hold? This is not the target role's previous grant state |
| Role baseline | `SHOW ROLES` after reset | Is the course role currently absent? This does not mean it was never granted privileges |
| After grants | Two `SHOW ROLES` results | First observe table access, then confirm that only view access remains |
| Ordinary user | View, base-table, and post-revocation queries | Does actual access match the least-privilege design? |
| Business values | Repeat the count and total query | Did the authorization change leave the data product unchanged? |

After the first grant, locate `course_bi_reader_l3` in `SHOW ROLES`. Its `TablePrivs` should contain `internal.<current_db>.orders_imported: Select_priv`. After narrowing access, that column should contain only `course_bi_orders_view_l3: Select_priv`, with no base-table grant.

A grant in `GlobalPrivs`, `CatalogPrivs`, or `DatabasePrivs` is broader than the intended object. Initially, `Users` is empty; the test user holds the role only during the later acceptance step.

Each kind of evidence answers part of the question:

| Evidence | What it can establish | What it cannot establish |
| --- | --- | --- |
| `SHOW ROLES` | The role's privileges and their scopes | Whether a real consumer can log in and read the data |
| Business query | The object exists and its values match expectations | That privileges are limited to the intended scope |
| The Lab's change-record `SELECT` | An example record format: change ID, role, object, privilege, and teaching reason | Approval or execution of the grant; this is not a Doris audit log |
| FE audit log and approval record | Executed SQL and the basis for approval, respectively | The resulting access scope or the consumer's actual query outcome on their own |
| Query as a test consumer | What that identity can and cannot read | Access outcomes for other identities or hosts |

Lab 12 checks actual access with a temporary ordinary user: view-only `SELECT_PRIV` allows the view query, direct access to the order details is denied, and revoking role membership denies the view query too. This distinguishes root's administrative capabilities from the consumer's privileges.

The consumer test uses its own connection:

| Test | Expected result | Meaning |
| --- | --- | --- |
| Query `course_bi_orders_view_l3` | Success | View access works |
| Query `orders_imported` directly | Denied | The grant did not expose the base table |
| Query the view after revoking membership | Denied | Revocation changes actual consumer access |

All three assertions execute in the isolated sandbox. Production still requires approval, managed identities, and audit retention.

A complete release record links identity, object, privilege, reason, and release ID under one change identifier. Follow the production operating procedure for the FE's `fe.audit.log` and approval records. Auditing the Lab's constant `SELECT` proves that this `SELECT` ran; it does not turn the displayed reason into an approval or prove that `GRANT` ran. [FE Log Management](https://doris.apache.org/docs/4.x/admin-manual/log-management/fe-log/) describes the audit log's location and purpose.

## 12.4 How Do You Retire Dashboard Access?

When a dashboard is retired, its account may continue reading through `course_bi_reader_l3`. Inspect the role's `Users` first. Decide whether to remove **one user's role membership** or **the role's view privilege**. These operations affect different sets of consumers.

If dashboard A is retired but dashboard B still uses the same role, revoke membership only from A's account. Keep the role's `SELECT_PRIV`, then verify that A is denied and B can still read. Check for direct grants or other roles that could still give A access; removing one membership does not remove every access path.

The following is a reading-only example. Lab 12 does not use this account:

<!-- reading-only-example -->
```sql
REVOKE 'course_bi_reader_l3' FROM 'dashboard_a'@'%';
```

Retire the role itself only after confirming that no consumer still needs it. Record its users and grants, remove or migrate all memberships, revoke the role's view privilege, delete the role, and verify both configuration and ordinary-user access.

Lab 12 executes the next two statements after revoking membership and deleting its test user:

<!-- reading-only-example -->
```sql
REVOKE SELECT_PRIV
ON internal.dw_course_l1_demo.course_bi_orders_view_l3
FROM ROLE 'course_bi_reader_l3';

DROP ROLE IF EXISTS course_bi_reader_l3;
```

Revoking a shared role's privileges interrupts every consumer relying on those privileges. Confirm dependencies before that step. The initial role drill has only one temporary consumer: it tests access, removes that user's membership and account, then revokes the view grant and removes the role and Lab view.

Revocation changes access:

- The test user can no longer query `course_bi_orders_view_l3`; it never had direct access to `orders_imported`.
- `orders_imported` still contains 10 rows totaling 1400.00, with the same grain and fields.
- Users obtaining access through other roles keep those independent access paths.

Retain approval and revocation records in production. `DROP ROLE` removes an object; it does not replace an audit record. Before-and-after `SHOW ROLES` results describe configuration changes, while ordinary-user queries describe their effects. See [REVOKE FROM](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/account-management/REVOKE-FROM) and [DROP ROLE](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/account-management/DROP-ROLE/).

## 12.5 What If Table Privileges Are Too Broad?

Two new requirements arrive: only Finance may see `paid_amount` and `refund_amount`, and the eastern regional team may read only orders with `region = 'EAST'`. Table-level `SELECT_PRIV` cannot express either restriction.

| Requirement | Mechanism to consider | What to verify |
| --- | --- | --- |
| Selected columns for particular roles | Column privileges, such as `SELECT_PRIV(order_id, order_amount)` | Review the grant when new columns are added |
| Selected rows based on a condition | Row Policy, associated with a user or role | Test the filter with the intended consumer identity |
| Hide part of a sensitive field | Data masking | Doris uses Apache Ranger for masking policies; this Lab does not install Ranger |

Test each mechanism with an ordinary consumer. A successful root query does not establish the consumer's access boundary. Define the restriction, affected objects, and acceptance checks before choosing a mechanism. See [Data Access Control](https://doris.apache.org/docs/4.x/admin-manual/auth/authorization/data/).

## 12.6 Prove a Release Boundary and Its Consumer Controls

A stable table name can switch to a prepared table atomically, but Doris does not thereby backfill data, validate a business contract, or catch up a change stream for you. The extended Lab pauses its simulated writer, applies a final delta, reconciles all rows, swaps the names with `swap=true`, and rehearses rollback before resuming writes. Once the released table receives another write, the retained old copy is no longer a current rollback target. See [ALTER TABLE REPLACE](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/table-and-view/table/ALTER-TABLE-REPLACE/).

The next drill separates table privilege from row visibility. Two ordinary users have the same table-level read privilege, while restrictive Row Policies constrain them to different regions. A query asking for the other region still returns no rows. This is database enforcement, unlike a dashboard filter; `root` is not the correct identity for validating it. The scope and policy combination rules are in [CREATE ROW POLICY](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-governance/CREATE-ROW-POLICY/).

Finally, the Lab reads real tagged query entries from the course FE audit file. Grant metadata answers what an identity may do, query results establish the controlled experiment's visible rows, and audit records describe observed execution. Keep those kinds of evidence separate. Collecting one local file does not establish multi-node coverage or compliant retention; consult [FE log management](https://doris.apache.org/docs/4.x/admin-manual/log-management/fe-log/) for production operation.

## Hands-on Lab: Publish a Scoped BI Reader Role

Open [Lab 12](lab12_publishing_permissions_audit.ipynb) and complete these steps:

1. Check identity, database, grantor privileges, and the role baseline after reset.
2. Create `course_bi_reader_l3`.
3. Observe a table grant, then narrow the role to the course view.
4. As a temporary ordinary user, verify that the view is readable, the base table is denied, and the view is denied after membership is revoked.
5. Record the role configuration and example change record; clean up the test user, role, and Lab view.
6. Rehearse a reconciled table cutover and paused-writer rollback, then identify the retained copy's post-release gap.
7. Test two regional ordinary users against restrictive Row Policies, and inspect real tagged FE audit records.
8. Remove the temporary regional users and policies; retain the isolated data tables for review.

### Prerequisites and Scope

Lab 12 needs only `orders_imported` from Level 1 Lab 5. The Level 2 serving view appears in the independent exercise. The Notebook checks the table before changing grants.

Use the dedicated `dw_course_l1_*` database. The test account has a random name; its password stays in memory and is never printed. The account is removed after testing. Its `'%'` host scope supports connectivity inside the personal course container and is not a production account design.

### Acceptance Criteria

| Check | Expected result |
| --- | --- |
| Prerequisite data | 10 `orders_imported` rows totaling 1400.00 |
| Release identity | Current course user and dedicated database displayed |
| Grant scope | First, only the current database's `orders_imported` in `TablePrivs`; then, only `course_bi_orders_view_l3` |
| Privilege type | `Select_priv`, without `Admin_priv` or `Grant_priv` |
| Ordinary-user checks | View succeeds; base table is denied; view is denied after membership revocation |
| Example change record | Change ID, role, object, privilege, and teaching reason, identified as an example rather than approval or audit evidence |
| Cleanup | `course_bi_reader_l3` no longer appears in `SHOW ROLES` |

## Independent Exercise

The BI team needs Level 2's `bi_order_metrics_l2`, but must not read order details. Write down:

1. The role's minimum object scope.
2. Two pieces of privilege evidence to retain.
3. The rollback steps if publication fails.
4. Why `SELECT_PRIV ON internal.*.*` exceeds the requirement.

<details>
<summary>Reference Explanation</summary>

Grant `SELECT_PRIV` on this view only. The following is a reading-only example:

<!-- reading-only-example -->
```sql
GRANT SELECT_PRIV
ON internal.dw_course_l1_demo.bi_order_metrics_l2
TO ROLE 'course_bi_reader_l3';
```

Do not grant its dependencies, `daily_order_metrics_l2` or `orders_imported`. A view-only role can query the view; granting the detail table too would allow the consumer to bypass that interface.

Retain `SHOW GRANTS` for the grantor and before-and-after `SHOW ROLES` for the target role. After the grant, confirm that `TablePrivs` contains only the view. `SHOW GRANTS` does not describe the role's previous state. In an isolated environment, also test that the consumer can read the view but not the details.

For rollback, inspect memberships and other consumers first. If only the newly published account should lose access, revoke its membership and verify access as that user. Keep shared role privileges while other consumers need them. Once the role has no remaining purpose, revoke its privileges, drop it, and verify the resulting configuration and access.

`internal.*.*` covers every existing and future database and table in the internal Catalog, including order details. That scope exceeds the contract and increases the impact of an incorrect grant.

</details>

## Module Summary

- Define the consumer contract before choosing privilege scope.
- Roles centralize grants, revocation, and review; read privileges and administrative privileges serve different purposes.
- `SHOW GRANTS`, `SHOW ROLES`, business queries, ordinary-user tests, and audit logs provide different evidence.
- Revoke one user's membership when only that consumer leaves; revoke the role's privileges when the entire role is retired.
- Column privileges, a Row Policy, and masking address different restrictions.
- A release procedure includes revocation and cleanup as well as grants.

## Knowledge Quiz

[Quiz 12](quiz12_publishing_permissions_audit.ipynb) contains six scenario-based single-choice questions covering consumer contracts, privilege scope, evidence, shared-role revocation, and fine-grained access.

## Official References

- [Built-in Authorization](https://doris.apache.org/docs/4.x/admin-manual/auth/authorization/internal/)
- [Data Access Control](https://doris.apache.org/docs/4.x/admin-manual/auth/authorization/data/)
- [GRANT TO](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/account-management/GRANT-TO)
- [REVOKE FROM](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/account-management/REVOKE-FROM)
- [DROP ROLE](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/account-management/DROP-ROLE/)
- [SHOW GRANTS](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/account-management/SHOW-GRANTS/)
- [SHOW ROLES](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/account-management/SHOW-ROLES/)
- [FE Log Management](https://doris.apache.org/docs/4.x/admin-manual/log-management/fe-log/)
