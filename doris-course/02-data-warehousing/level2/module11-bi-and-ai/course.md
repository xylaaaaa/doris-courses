# 模块 11：BI 与 AI 应用

| 课程信息 | 说明 |
| --- | --- |
| 所属课程 | Data Warehousing with Apache Doris · Level 2 |
| 产品范围 | Apache Doris 4.x；示例使用课程 4.1.3 沙箱 |
| 前置知识 | Module 8 的视图、Module 9 的粒度、Module 10 的指标契约 |
| 建议用时 | 约 80 分钟：阅读 45 分钟、实验 30 分钟、测验 5 分钟 |

[Level 2 目录](../README.md) · [打开 Lab 11](lab11_bi_and_ai_delivery.ipynb) · [打开 Quiz 11](quiz11_bi_and_ai.ipynb)

## 单元目标

BI 和 AI 消费者需要的不是一张“能查出来”的表，而是可理解、可授权、可刷新、可验收的数据接口。本单元把 Module 10 的指标包装成语义视图，说明看板如何连接 Doris、哪些列是维度或度量，再介绍 Apache Doris MCP Server 如何提供受 SQL 安全约束的只读工具。AI 生成查询可以辅助探索，但不能替代权限、指标定义和人工审核。

### 学习目标

1. 设计名称稳定的消费者语义视图
2. 区分看板维度和指标度量
3. 准备特征投影，但不夸大模型质量结论
4. 在服务消费者前验证空值、新鲜度和行数
5. 记录 Doris SQL 与下游 BI 或 AI 工具之间的边界

## 单元安排

| 小节 | 核心问题 | 建议用时 |
| --- | --- | --- |
| 11.1 语义视图与消费者契约 | 看板应该依赖哪些列？ | 10 分钟 |
| 11.2 BI 看板连接与 SLA | 如何把指标交给 Superset？ | 10 分钟 |
| 11.3 特征投影与数据边界 | 哪些字段可以交给下游模型？ | 10 分钟 |
| 11.4 Doris MCP Server | AI 工具如何安全读取 Doris？ | 10 分钟 |
| 11.5 发布前检查 | 如何确认新鲜度、空值和总数？ | 5 分钟 |
| Lab 11 / Quiz 11 | 语义服务与知识检查 | 30 / 5 分钟 |

## 11.1 语义视图与消费者契约

### 维度、度量和过滤条件

看板通常由三类内容组成：

| 类型 | 含义 | 本课示例 |
| --- | --- | --- |
| 维度 Dimension | 用来切分、筛选或排列结果的属性 | `order_date`、地区、产品类别 |
| 度量 Measure | 在当前维度组合上计算的数值 | `order_count`、`gross_amount` |
| 计算度量 | 从已审核度量进一步计算的指标 | `average_order_amount` |

日期在图表中作为时间维度，订单数和总金额是度量。把日期当作金额求和、把已聚合客单价再次平均，都属于粒度错误。语义视图的列名应该让消费者知道含义，例如 `gross_amount` 不应在没有说明的情况下突然改成“退款后净额”。

Module 10 的服务表按日期 × 来源保存，Module 11 再发布按日期的一层消费者视图。以下为 Lab 中的 DDL 阅读示例，由 Notebook 统一创建：

<!-- reading-only-example -->

```sql
CREATE VIEW bi_order_metrics_l2 AS
SELECT order_date,
       SUM(order_count) AS order_count,
       SUM(gross_amount) AS gross_amount,
       CASE WHEN SUM(order_count) = 0 THEN NULL
            ELSE SUM(gross_amount) / SUM(order_count) END AS average_order_amount
FROM daily_order_metrics_l2
GROUP BY order_date;
```

这段 SQL 保留分子和分母到发布时才计算客单价；当某个已有分组的订单数合计为 0 时返回 NULL，表示没有有效分母，而不是声称客单价为零。若某天在服务表中根本没有记录，GROUP BY 不会自动生成该日行；需要先关联日历表才能展示连续日期。视图没有客户列，所以它是日级服务接口，不是客户明细接口。

### 契约要比 SQL 更稳定

消费者契约应记录：

- 字段名称、类型和业务含义；
- 行粒度与唯一性；
- 时间字段、时区和覆盖范围；
- 刷新频率、数据延迟和迟到数据处理；
- 空值、零值和缺失日期；
- 访问账号和敏感字段范围；
- Doris 保证什么，下游 BI/AI 负责什么。

底层表可以增加内部列或更换物化实现，只要视图的输出契约没有改变。契约不是永久不变：字段废弃、语义修改和粒度变化都应通过版本、公告和迁移窗口处理。一个能执行的 View 不自动具备版本治理。

## 11.2 BI 看板连接与 SLA

### Doris 与 Superset 的连接边界

Apache Superset 是外部 BI 应用，Doris 提供 SQL 数据源；Doris 不负责绘制图表、缓存策略或看板页面权限。官方连接文档给出的 SQLAlchemy URI 形态为：

```text
doris://<username>:<password>@<host>:<port>/internal.<database>
```

课程容器中的查询端口是 9030；从宿主机连接时使用课程映射的本地端口，不能把容器内部端口和宿主机端口混写。实际环境应使用专用只读账号，不把 root 账号配置给 BI 服务。Superset 侧需要安装对应 Doris Python 客户端并按其版本文档配置。

**连接前检查：**

1. Doris 用户只能访问发布视图和必要的数据库对象。
2. 连接使用 `internal` Catalog 和正确数据库。
3. 直接查询视图的结果与 Lab 10 的独立核对一致。
4. BI 数据集没有把金额字段误设为字符串或把已聚合指标再次聚合。
5. 时间列、默认时区和刷新频率写入数据集说明。

### 把“看板好用”拆成三个 SLA

| 目标 | 数据库侧指标 | 还需要谁负责 |
| --- | --- | --- |
| 速度 | 查询延迟、扫描行数、Profile 中算子耗时 | BI 查询配置、并发与缓存 |
| 新鲜度 | 最后成功刷新时间、数据最大事件时间 | 调度、迟到数据处理、BI 缓存 |
| 准确性 | 固定期望、独立明细核对、空值/行数检查 | 指标负责人、图表过滤和展示 |

不能用“查询返回 200 ms”证明看板数据新鲜；也不能用“图表显示了数字”证明指标口径正确。发布前应留下检查结果和失败处理方式。

### 看板指标的最小示例

本课不强制安装 Superset。完成 Lab 11 后，可先用 Doris SQL 验证看板数据集：

```sql
SELECT order_date,
       order_count,
       gross_amount,
       average_order_amount
FROM bi_order_metrics_l2
WHERE order_date >= '2026-01-01'
ORDER BY order_date;
```

然后再在 BI 工具中将 `order_date` 作为时间维度，将 `order_count` 和 `gross_amount` 作为度量。不要在 BI 层把 `average_order_amount` 按行 `SUM`；如果要跨日期计算客单价，应使用总金额除以总订单数。

Superset 的安装、Doris URI、数据集和图表配置见 [Apache Superset 集成](https://doris.apache.org/docs/4.x/connection-integration/data-integration/superset/)。

## 11.3 特征投影与数据边界

### 特征列不是模型结论

特征投影把经过类型、命名和质量检查的输入交给下游模型或服务。它可以包含订单量、金额、均价、最近活动日期等输入，但不会证明模型预测准确，也不会自动处理训练/服务时间穿越、标签泄漏和样本偏差。

Lab 11 的只读特征投影如下：

```sql
SELECT order_date,
       order_count AS feature_order_count,
       gross_amount AS feature_gross_amount,
       average_order_amount AS feature_average_amount,
       CASE WHEN order_count = 0 THEN 1 ELSE 0 END AS zero_order_flag
FROM bi_order_metrics_l2
ORDER BY order_date;
```

| 特征 | 用途 | 需要确认 |
| --- | --- | --- |
| `feature_order_count` | 订单活动强度 | 是否是当天最终值，迟到事件如何处理 |
| `feature_gross_amount` | 金额规模 | 是否含退款、币种和金额单位 |
| `feature_average_amount` | 单笔平均金额 | 分母为零时的 NULL 处理 |
| `zero_order_flag` | 已有行的零订单标记 | 缺失日期不会自动补行；NULL 订单数还需单独检查 |

向量检索是另一种能力：Doris 4.x 官方文档说明向量以 `Array<Float>` 存储并使用 ANN 索引进行近似邻居检索。它不等于把一列金额直接变成“AI 特征”，也不替代离线评估。本课程当前 Lab 不创建向量索引，相关内容应作为独立实验而不是已经验证的交付能力。

## 11.4 Doris MCP Server

### MCP 连接了什么？

Apache Doris MCP Server 是独立的 Python 服务，通过 MySQL 协议连接 Doris，并向 MCP 客户端提供工具。官方文档列出的工具包括数据库/表清单、表结构、列注释、索引、只读 SQL 和审计日志。它不是 Doris FE 内置的 SQL 语法，也不是一个自动拥有所有数据库权限的 AI 用户。

```text
MCP 客户端（Cursor / Claude 等）
             │ 工具调用
             ▼
Doris MCP Server：连接、SQL 安全过滤、超时、结果行数限制、审计
             │ MySQL 协议
             ▼
Doris：按连接用户权限读取数据
```

官方文档说明，默认安全过滤会阻止 `DROP`、`DELETE`、`INSERT`、`UPDATE`、`ALTER` 和 `CREATE` 等修改语句，并可以给没有 LIMIT 的 SELECT 增加限制。具体版本配置以 MCP Server 仓库为准。过滤器不是完整的权限系统：数据库用户本身能读什么，MCP 服务就可能读到什么。

### 安全使用的最小边界

1. 为 MCP 使用单独的只读 Doris 用户，并只授予发布视图所需权限。
2. 设置数据库、主机和端口环境变量，不把密码写进 Notebook、提示词或仓库。
3. 审核每次工具调用及生成的 SQL，尤其是涉及敏感列和大范围扫描的查询。
4. 使用 `max_rows`、聚合和明确的时间范围，避免把大量明细直接放进模型上下文。
5. 将表中业务文本视为不可信数据；模型读取的内容不能改变工具安全规则。
6. 记录审计日志，保留谁在什么时间通过什么工具读了什么对象的证据。

MCP 适合 Schema 探索、只读分析和运维查询辅助；不应放进生产写入链路，也不能把“模型说查询正确”当作指标验收。官方说明和配置示例见 [Apache Doris MCP Server](https://doris.apache.org/docs/4.x/key-features/mcp-server/)。

## 11.5 发布前检查

完成 Lab 11 后检查语义视图和特征投影：

```sql
SELECT
    COUNT(*) AS serving_days,
    SUM(CASE WHEN order_count IS NULL THEN 1 ELSE 0 END) AS null_order_days,
    MIN(order_date) AS first_date,
    MAX(order_date) AS last_date,
    SUM(order_count) AS served_orders
FROM bi_order_metrics_l2;
```

当前样本预期为 1 个服务日、0 个空订单日、日期为 `2026-01-01`、订单数为 10。这个结果只验证当前专用库的样本，不是永远适用的硬编码事实。生产验收应将日期覆盖范围、最大事件时间、最后成功刷新时间和期望批次一起检查。

| 检查 | 通过条件 | 失败时先查什么 |
| --- | --- | --- |
| Schema | 列名、类型、粒度与契约一致 | View 定义和下游数据集映射 |
| 完整性 | 关键日期/度量空值符合规则 | 上游过滤、分母和迟到数据 |
| 数量 | 服务日数和订单量与独立查询一致 | 重复写入、漏分区、错误 JOIN |
| 金额 | 金额与明细聚合一致 | 粒度放大、币种、退款口径 |
| 新鲜度 | 最大事件时间和刷新时间达到承诺 | 调度、队列、BI 缓存 |
| 权限 | 只读用户只能看到发布范围 | 数据库授权和 BI 连接账号 |

## 动手实验：发布稳定的消费者接口

请先完成 Lab 10，再打开 [Lab 11](lab11_bi_and_ai_delivery.ipynb)。实验使用同一个专用 `dw_course_l1_*` 数据库，重建 `bi_order_metrics_l2`，并以表格输出结果和完整性检查。输入来自 Module 10 服务表；Lab 8–9 的对象不是直接输入。Notebook 不启动 Superset，也不连接外部 MCP Server；正文中的连接配置供部署时参考。

### 独立练习

假设 BI 团队要求增加“客户地域”筛选。先判断当前 `bi_order_metrics_l2` 是否包含所需粒度，再选择在事实表关联维度后重建服务表、发布新的接口，或提供另一张明确的服务视图。不要把地域列硬加到日粒度视图中后继续声称每行仍是日粒度。

<details>
<summary>参考解释</summary>

当前接口每行是一天，没有客户或地域。增加地域后，粒度至少变为日期 × 地域，订单数和金额必须重新聚合；这会改变接口的行粒度，属于契约变更。若既要保持原接口又要支持筛选，可以发布新的视图或新的数据集，并分别记录刷新、权限和验收规则。

</details>

## 单元总结

- 语义视图是消费者契约，维度、度量、粒度和单位必须清楚；SQL 能执行不等于口径正确。
- Superset 负责数据集和图表，Doris 负责 SQL 数据服务；速度、新鲜度和准确性要分别定义 SLA。
- 特征投影提供经过检查的输入列，不保证模型质量，也不处理所有训练和服务风险。
- Doris MCP Server 通过 MySQL 连接和受限工具提供只读辅助；只读账号、SQL 审核、结果限制和审计仍然需要配置。
- 发布前检查 Schema、空值、行数、金额、新鲜度和权限；当前 Notebook 的实测范围不能扩写成完整外部集成验收。

## 知识测验

打开 [Quiz 11](quiz11_bi_and_ai.ipynb)，检查语义视图、维度度量、特征投影、发布校验和 Doris/BI/AI 边界。测验不需要数据库。

## 官方参考资料

- [Apache Superset 集成](https://doris.apache.org/docs/4.x/connection-integration/data-integration/superset/)：连接串、数据集和图表配置。
- [Apache Doris MCP Server](https://doris.apache.org/docs/4.x/key-features/mcp-server/)：工具、连接、安全过滤和使用边界。
- [向量索引](https://doris.apache.org/docs/4.x/table-design/index/vector-index/overview/)：Array<Float>、ANN 检索和索引限制。
- [视图](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/table-and-view/view/CREATE-VIEW/)：视图定义与消费者接口。
