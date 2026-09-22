# Module 8: Views and materialized views

## Module Goal

Turn a stable business query into a logical view, then use a materialized view to precompute a repeated aggregate. Verify refresh state and query-rewrite evidence separately.

## Learning Objectives

1. distinguish a logical view from stored materialized results
2. choose a refresh policy from freshness and cost requirements
3. verify a materialized view with metadata and result checks
4. use EXPLAIN as evidence for query rewrite rather than assuming a hit
5. keep a published view contract stable while changing its implementation

## Module Schedule

| Section | Learning Format | Suggested Time | Learning Outcome |
| --- | --- | --- | --- |
| 8.1–8.5 | Lesson and guided examples | 25 minutes | Apply the module concepts to the order domain |
| Lab | Hands-on notebook | 30 minutes | Produce and validate an independent result |
| Quiz | Interactive knowledge check | 5 minutes | Check the learning objectives |

## Hands-on Lab

[`lab8_views_and_materialized_views.ipynb`](lab8_views_and_materialized_views.ipynb) uses tables owned by this module. Complete Level 1 first and set `DW_ALLOW_WRITES=yes` with a dedicated `DW_DATABASE` before running it.

## Module Summary

- Turn a stable business query into a logical view, then use a materialized view to precompute a repeated aggregate. Verify refresh state and query-rewrite evidence separately.
- Validate business results independently before making performance or freshness claims.
- Keep consumer contracts separate from physical implementation details.

## Knowledge Quiz

[`quiz8_views_and_materialized_views.ipynb`](quiz8_views_and_materialized_views.ipynb) contains five offline questions.
