# Module 11: BI and AI applications

## Module Goal

Deliver reviewed metrics to BI and AI consumers through stable SQL contracts. Separate semantic correctness, access boundaries, and feature freshness from the visualization or model itself.

## Learning Objectives

1. design a consumer-facing semantic view with stable names
2. distinguish dashboard dimensions from metric measures
3. prepare a feature projection without claiming model quality
4. validate nulls, freshness, and row counts before serving consumers
5. document the boundary between Doris SQL and downstream BI or AI tools

## Module Schedule

| Section | Learning Format | Suggested Time | Learning Outcome |
| --- | --- | --- | --- |
| 11.1–11.5 | Lesson and guided examples | 25 minutes | Apply the module concepts to the order domain |
| Lab | Hands-on notebook | 30 minutes | Produce and validate an independent result |
| Quiz | Interactive knowledge check | 5 minutes | Check the learning objectives |

## Hands-on Lab

[`lab11_bi_and_ai_delivery.ipynb`](lab11_bi_and_ai_delivery.ipynb) uses tables owned by this module. Complete Level 1 first and set `DW_ALLOW_WRITES=yes` with a dedicated `DW_DATABASE` before running it.

## Module Summary

- Deliver reviewed metrics to BI and AI consumers through stable SQL contracts. Separate semantic correctness, access boundaries, and feature freshness from the visualization or model itself.
- Validate business results independently before making performance or freshness claims.
- Keep consumer contracts separate from physical implementation details.

## Knowledge Quiz

[`quiz11_bi_and_ai.ipynb`](quiz11_bi_and_ai.ipynb) contains five offline questions.
