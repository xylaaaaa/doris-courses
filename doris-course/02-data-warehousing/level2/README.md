# Level 2：数据仓库建模与服务

Level 2 建立在 Level 1 的数据接入、质量检查和状态变更基础上，回答一条数据如何变成可复用、可核对、可交付的业务指标。学习顺序是：先统一查询定义，再确定事实与维度粒度，然后加工指标服务表，最后发布给 BI 和 AI 消费者。

每个模块都按“课程正文 → Lab → Quiz”完成。正文先解释业务问题、数据粒度和 Doris 机制，再给出与 Lab 对应的 SQL 阅读示例；Lab 验证可执行路径，Quiz 检查概念和取舍。

| 模块 | 主题 | 材料 |
| --- | --- | --- |
| 8 | 视图与物化视图 | [课程](module08-views-materialized-views/course.md) · [实验](module08-views-materialized-views/lab8_views_and_materialized_views.ipynb) · [测验](module08-views-materialized-views/quiz8_views_and_materialized_views.ipynb) |
| 9 | 数仓建模与 JOIN | [课程](module09-modeling-and-joins/course.md) · [实验](module09-modeling-and-joins/lab9_modeling_and_joins.ipynb) · [测验](module09-modeling-and-joins/quiz9_modeling_and_joins.ipynb) |
| 10 | 指标加工与服务交付 | [课程](module10-metric-processing/course.md) · [实验](module10-metric-processing/lab10_metric_processing.ipynb) · [测验](module10-metric-processing/quiz10_metric_processing.ipynb) |
| 11 | BI 与 AI 应用 | [课程](module11-bi-and-ai/course.md) · [实验](module11-bi-and-ai/lab11_bi_and_ai_delivery.ipynb) · [测验](module11-bi-and-ai/quiz11_bi_and_ai.ipynb) |

实验只创建带 `_l2` 后缀的对象，并将查询结果以表格展示。实验使用 Level 1 已准备的专用 `dw_course_l1_*` 数据库；Lab 8 和 Lab 10/11 需要 `orders_imported`，Lab 9 还需要 Lab 6 建立的 `customers`。建议按 5 → 6 → 8 → 9 → 10 → 11 的顺序运行；每个 Lab 会在写入前检查自己的前置数据并给出下一步提示。当前 Notebook 验证单节点课程环境中的核心路径；Superset、MCP、多节点 JOIN 策略和大规模性能对比在正文中说明使用边界，不冒充已由课程沙箱完成的外部集成实验。
