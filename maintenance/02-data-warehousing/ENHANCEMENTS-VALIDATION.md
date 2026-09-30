# Extended Level 2/3 core validation — 2026-09-30

## Delivered and executed

- Module 8: synchronous write maintenance; a partitioned join MV refreshes one fact partition, then all result partitions after a non-partitioned dimension change. Observe partition identity **and** visible version plus actual task scope.
- Modules 9–11: independent ODS/DWD/DWS/ADS teaching case, invalid-order rejection, version resolution, payment-retry deduplication, payment/cohort/repeat/refund contracts, exact/Bitmap/HLL comparison and executed Profile observations. A real three-chart Superset dashboard uses a view-only Doris account; direct detail access is denied.
- Module 12: validated table-name swap and rollback at a simulated paused-writer boundary; post-release write gap; two ordinary regional Row Policy identities; tagged queries matched to real FE audit records.
- Module 13: actual full repository backup, forced source deletion, isolated restore from the returned timestamp, and ordered-row/count/amount reconciliation. Recycle-bin recovery is a separate earlier drill.

Environment: independent Docker projects, loopback SQL/HTTP/BI/storage ports, Doris image `apache/doris:all-in-one-4.1.3` (reported build `doris-4.1.3-rc02-7126cf65d96`), one FE/BE, 6 GiB memory cap and two CPUs. Superset 4.1.2, pydoris 1.1.0 and pinned MinIO. Existing learner containers were not reconfigured.

The integrated current learner source executed Labs 8–14 and reference solutions successfully, using Lab 5/6 prerequisites executed earlier in the same isolated database. The final helper refinements were re-executed in Labs 8/10/11. Branch-native extended cells for Modules 8/10/11 and 12/13 also passed. This round did not rerun all Level 1, Kafka/Flink extensions or production workloads.

Offline tests: **139** on the Level 2 branch, **158** on the Level 3 branch, **183** on the integrated preview. Test-count differences reflect the other Level snapshots retained on each branch. **82** current learner/runtime files passed English/source-only checks. Quiz IDs, option IDs and answer keys were preserved; only three scenarios/objectives were revised. No executed Notebook outputs were saved into learner files.

Superset API checks verified actual values and explicit chart/dashboard associations. Chromium rendered all three charts (660.00, 5, 62.5%) without page errors. Rerunning updated the same named BI objects rather than duplicating them. These are observations of the teaching case, not production guarantees.

Local evidence is under `/tmp/dw-enhance-20260930/`: `full-final.log`, `final-adjusted.log`, `m8-final.log`, `bi-final.log`, `native-l2.log`, `native-l3.log`, three test logs, `browser-review.log` and `dashboard.png`. Initial failures were repaired and retested: partition replacement can preserve its visible-version number; BACKUP/RESTORE use different job-label columns; dataset POST/PUT have different schemas; dashboard layout does not itself attach chart relationships; a Profile fingerprint must not shadow the normalization function.

## Self-review conclusions

| Checkpoint | Conclusion |
| --- | --- |
| Goal and evidence | Missing core experiments were implemented, executed and independently reconciled; remaining original targets are not relabeled complete. |
| Focus and reuse | Level 1 learning scope/fixtures stay unchanged. Reuse existing display, wait, Notebook runner and Profile parsers; teaching transformation SQL remains visible in Labs. |
| Concurrency | Designed for one learner executing Labs sequentially. Asynchronous MV/backup jobs are polled to completion; concurrent notebook resets are not supported. No new engine threads or locks. |
| Lifecycle | Temporary ordinary users/policies are cleaned in `finally`; session settings are restored. Superset metadata, its scoped read account and backup objects intentionally remain, with documented stop/retirement boundaries. |
| Configuration | Explicit-start local sidecars, pinned dependencies, loopback ports and memory caps. No production TLS, multi-user Superset authorization or live config-change claim. |
| Compatibility and parallel paths | Add a shared session-recovery method without changing existing initialization semantics. BI/backup use identical sidecar/session helpers on both branches. No engine symbol, storage-format or rolling-upgrade changes. |
| Failure paths | SQL/Compose/API errors and failed jobs raise. Missing prerequisites and expected access denial are distinguished; bucket creation accepts only an actual 404. Credential-bearing API payloads are not echoed. |
| Tests and results | Independent ledgers and negative unit cases plus real SQL/API/browser execution. Deterministic rows are ordered. Learner notebooks remain source-only; no generated regression results are handwritten. |
| Observability | Real Profile IDs/counters, MV task partitions, audit Query IDs/outcomes, and repository labels/timestamps are displayed. Unrelated credential statements are excluded from audit output. |
| Transactions and writes | Only dedicated course objects are rebuilt. Table replacement is atomic, but writer pause/catch-up is simulated; no continuous CDC, crash-atomic release or zero-data-loss claim. Backup restores only its recorded cutoff. |
| Persistence and FE/BE variables | Existing Doris SQL APIs own persistence; no EditLog, Delete Bitmap, memory-accounting or cross-end variable changes. Volumes are preserved, not deleted during testing. |
| Performance and remaining limits | Measured fewer scanned rows, not a promised proportional speedup. Twenty sequential warmed samples are not production P95 capacity. Same-host object storage is not disaster recovery. ARM64, multi-node recovery, Ranger, Storage Vaults and continuous CDC remain unverified. |
