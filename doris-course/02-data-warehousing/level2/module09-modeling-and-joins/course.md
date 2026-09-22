# Module 9: Warehouse modeling and joins

## Module Goal

Move from a single imported order table to a small fact-and-dimension model. Choose grain and keys first, then validate join cardinality and plan data movement.

## Learning Objectives

1. state the grain of a fact and a dimension table
2. choose a table model and key from update semantics
3. validate one-to-one and one-to-many join cardinality
4. use LEFT JOIN and anti-join checks to find missing dimensions
5. read join distribution evidence from EXPLAIN

## Module Schedule

| Section | Learning Format | Suggested Time | Learning Outcome |
| --- | --- | --- | --- |
| 9.1–9.5 | Lesson and guided examples | 25 minutes | Apply the module concepts to the order domain |
| Lab | Hands-on notebook | 30 minutes | Produce and validate an independent result |
| Quiz | Interactive knowledge check | 5 minutes | Check the learning objectives |

## Hands-on Lab

[`lab9_modeling_and_joins.ipynb`](lab9_modeling_and_joins.ipynb) uses tables owned by this module. Complete Level 1 first and set `DW_ALLOW_WRITES=yes` with a dedicated `DW_DATABASE` before running it.

## Module Summary

- Move from a single imported order table to a small fact-and-dimension model. Choose grain and keys first, then validate join cardinality and plan data movement.
- Validate business results independently before making performance or freshness claims.
- Keep consumer contracts separate from physical implementation details.

## Knowledge Quiz

[`quiz9_modeling_and_joins.ipynb`](quiz9_modeling_and_joins.ipynb) contains five offline questions.
