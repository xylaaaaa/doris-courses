# Module 10: Metric processing and service delivery

## Module Goal

Define metrics at a declared grain, build a reusable aggregate result, and expose a stable query for downstream dashboards. Correctness comes before refresh or latency claims.

## Learning Objectives

1. define a metric with numerator, denominator, grain, and filter
2. separate detail facts from an aggregate serving table
3. validate metrics against an independent detail query
4. use windows and conditional aggregation without changing grain accidentally
5. publish a narrow serving query for a dashboard consumer

## Module Schedule

| Section | Learning Format | Suggested Time | Learning Outcome |
| --- | --- | --- | --- |
| 10.1–10.5 | Lesson and guided examples | 25 minutes | Apply the module concepts to the order domain |
| Lab | Hands-on notebook | 30 minutes | Produce and validate an independent result |
| Quiz | Interactive knowledge check | 5 minutes | Check the learning objectives |

## Hands-on Lab

[`lab10_metric_processing.ipynb`](lab10_metric_processing.ipynb) uses tables owned by this module. Complete Level 1 first and set `DW_ALLOW_WRITES=yes` with a dedicated `DW_DATABASE` before running it.

## Module Summary

- Define metrics at a declared grain, build a reusable aggregate result, and expose a stable query for downstream dashboards. Correctness comes before refresh or latency claims.
- Validate business results independently before making performance or freshness claims.
- Keep consumer contracts separate from physical implementation details.

## Knowledge Quiz

[`quiz10_metric_processing.ipynb`](quiz10_metric_processing.ipynb) contains five offline questions.
