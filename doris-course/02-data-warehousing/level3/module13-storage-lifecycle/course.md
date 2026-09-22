# Module 13: Storage and lifecycle management

## Module Goal

Module 13: Storage and lifecycle management teaches a controlled operational boundary for a data warehouse. Review scope, evidence, and recovery before changing access or storage.

## Learning Objectives

1. choose a partition boundary from data retention semantics
2. inspect partitions, buckets, tablets, and replica metadata
3. apply a partition-level retention operation without truncating the table
4. explain the relationship between rowsets, compaction, and physical space
5. write a maintenance runbook with a rollback or recovery check

## Module Schedule

| Section | Learning Format | Suggested Time | Learning Outcome |
| --- | --- | --- | --- |
| 13.1–13.5 | Lesson and guided examples | 25 minutes | Explain the operational boundary and its evidence |
| Lab | Hands-on notebook | 30 minutes | Apply a controlled governance or maintenance operation |
| Quiz | Interactive knowledge check | 5 minutes | Check the learning objectives |

## Hands-on Lab

[`lab13_storage_and_lifecycle.ipynb`](lab13_storage_and_lifecycle.ipynb) uses a dedicated `dw_course_l1_*` database. Review the reset scope before any write or privilege statement.

## Module Summary

- Inspect metadata and ownership before changing data or access.
- Treat successful SQL execution as one observation, not a complete operational proof.
- Record scope, evidence, and recovery steps in the maintenance handoff.

## Knowledge Quiz

[`quiz13_storage_lifecycle.ipynb`](quiz13_storage_lifecycle.ipynb) contains five offline questions.
