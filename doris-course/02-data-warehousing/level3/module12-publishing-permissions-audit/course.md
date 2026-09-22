# Module 12: Publishing, permissions, and audit

## Module Goal

Module 12: Publishing, permissions, and audit teaches a controlled operational boundary for a data warehouse. Review scope, evidence, and recovery before changing access or storage.

## Learning Objectives

1. define an owner and consumer contract for a published data product
2. use roles and grants to give consumers only the required table privilege
3. distinguish database privileges from administrative privileges
4. inspect grants and record an audit trail for a release
5. revoke access without changing the published data product

## Module Schedule

| Section | Learning Format | Suggested Time | Learning Outcome |
| --- | --- | --- | --- |
| 12.1–12.5 | Lesson and guided examples | 25 minutes | Explain the operational boundary and its evidence |
| Lab | Hands-on notebook | 30 minutes | Apply a controlled governance or maintenance operation |
| Quiz | Interactive knowledge check | 5 minutes | Check the learning objectives |

## Hands-on Lab

[`lab12_publishing_permissions_audit.ipynb`](lab12_publishing_permissions_audit.ipynb) uses a dedicated `dw_course_l1_*` database. Review the reset scope before any write or privilege statement.

## Module Summary

- Inspect metadata and ownership before changing data or access.
- Treat successful SQL execution as one observation, not a complete operational proof.
- Record scope, evidence, and recovery steps in the maintenance handoff.

## Knowledge Quiz

[`quiz12_publishing_permissions_audit.ipynb`](quiz12_publishing_permissions_audit.ipynb) contains five offline questions.
