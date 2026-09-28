# 模块 8：视图与物化视图

| 课程信息 | 说明 |
| --- | --- |
| 所属课程 | Data Warehousing with Apache Doris · Level 2 |
| 产品范围 | Apache Doris 4.x；示例使用课程 4.1.3 沙箱 |
| 前置知识 | Level 1 的表模型、导入、质量检查与订单状态 |
| 建议用时 | 约 75 分钟：阅读 40 分钟、实验 30 分钟、测验 5 分钟；不含环境准备 |

[Level 2 目录](../README.md) · [打开 Lab 8](lab8_views_and_materialized_views.ipynb) · [打开 Quiz 8](quiz8_views_and_materialized_views.ipynb)

## 单元目标

运营、财务和 BI 同时询问“每天有多少订单、订单总金额是多少”。如果三个团队各自复制一份 SQL，过滤条件很容易逐渐不同；如果每张看板都反复扫描大量明细，相同计算又会被执行很多次。本单元先用普通视图统一查询定义，再解释何时值得存储预计算结果，以及如何证明结果新鲜、正确且被查询使用。

### 学习目标

1. 区分逻辑视图和已存储的物化结果
2. 根据新鲜度和成本要求选择刷新策略
3. 通过元数据和结果检查验证物化视图
4. 使用 EXPLAIN 证明查询改写，不凭对象命中猜测
5. 在改变实现方式时保持已发布视图契约稳定

## 单元安排

| 小节 | 核心问题 | 建议用时 |
| --- | --- | --- |
| 8.1 普通视图与语义层 | 如何统一字段含义和业务过滤条件？ | 8 分钟 |
| 8.2 同步与异步物化视图 | 预计算结果在哪里维护，有什么代价？ | 10 分钟 |
| 8.3 分区增量刷新 | AUTO 到底增量在哪里？ | 12 分钟 |
| 8.4 刷新策略与改写验证 | 如何检查新鲜度、恢复失败并确认改写？ | 10 分钟 |
| Lab 8 / Quiz 8 | 创建对象、阅读计划、核对概念 | 30 / 5 分钟 |

## 8.1 普通视图与语义层

### 从一个明确的业务定义开始

本单元使用 Lab 5 导入的 `orders_imported`：10 条模拟订单，初始金额合计 1400.00，来源为 `COURSE_SIMULATION`。它保存初始快照，不是 Lab 7 重放后的当前状态，也不是收款流水。这里的日期来自 `DATE(event_time)`；在初始快照中表示样本事件所在日。不能把未来状态更新的事件日直接当作不可变的下单日期。

**完成 Lab 5 后，可在同一实验库运行以下只读查询：**

```sql
SELECT DATE(event_time) AS order_date,
       COUNT(*) AS order_count,
       SUM(order_amount) AS gross_amount
FROM orders_imported
GROUP BY DATE(event_time)
ORDER BY order_date;
```

| order_date | order_count | gross_amount |
| --- | ---: | ---: |
| 2026-01-01 | 10 | 1400.00 |

`COUNT(*)` 数的是订单快照行，`SUM(order_amount)` 累加订单金额。初始订单均未支付，因此 1400.00 不能解释成已收款收入。视图能统一计算方式，却不能替业务决定“订单金额”和“收款”是否是一回事。

### 普通视图保存查询定义

普通 View 是一个具名 SQL 定义。查询视图时，Doris 根据定义读取底层数据并执行计算；创建视图本身不会生成一份独立的结果副本，也不会启动定时任务。

**下面是 Lab 8 的建视图语句阅读示例。由 Notebook 统一初始化，不要在完成实验后重复创建。**

<!-- reading-only-example -->
```sql
CREATE VIEW orders_service_view_l2 AS
SELECT DATE(event_time) AS order_date, customer_id, order_amount, data_source
FROM orders_imported
WHERE order_amount > 0;
```

这层定义做了三件事：将日期表达式命名为 `order_date`，只提供四个面向分析的字段，排除金额不大于零的记录。消费者不需要重复书写这些规则。底层表增加一列时，视图的输出不会因为 `SELECT *` 自动扩展，发布接口也更容易保持稳定。

但 `order_amount > 0` 是业务选择，不是通用数据质量规则。例如业务允许零元订单时，它们仍是有效订单；这个视图就不适合回答“全部订单数”。本课样本金额全部为正，所以过滤前后结果相同。以后换样本，必须重新检查两份查询的过滤语义。

```text
订单明细 → 普通视图：约定列、粒度、过滤条件 → 消费者查询
                   保存定义，查询时计算
```

“语义层”就是对消费者统一说明名称、含义和计算规则的接口层。应记录每列的业务含义、金额单位、时间口径、空值含义和负责人。改名、换日期含义、把含退款金额改成净金额，都可能破坏契约，即使 SQL 仍能运行。

普通视图也常作为发布入口，但创建 View 不等于配置了用户权限。账号授权和实际可访问范围需要单独验证，权限操作放在 Module 12。普通视图语法与支持范围见 [CREATE VIEW](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/table-and-view/view/CREATE-VIEW/)。

## 8.2 同步与异步物化视图

### 什么时候值得把计算结果存下来？

如果同一个按日聚合被许多消费者反复读取，可以把聚合结果提前计算并存储。每次读取的数据量可能从大量明细减少到少量日汇总行；代价是额外存储、维护写入和刷新资源。对于本课的 10 行数据，预计算很可能比直接查询更复杂，样本用于理解语义，不用于证明加速倍率。

| 方式 | 保存什么 | 维护时机 | 适合的问题 |
| --- | --- | --- | --- |
| 普通视图 | SQL 定义 | 查询时计算 | 统一字段和业务逻辑 |
| 同步物化视图 | 基表关联的物化索引 | 建成后随基表写入维护 | 支持范围内的单表查询加速 |
| 异步物化视图 | 可查询的物化结果 | 独立刷新任务 | 聚合、多表关联、可接受刷新延迟的服务 |

同步物化视图在写入链路维护一致性，但创建过程本身也需要构建完成。它不支持任意 SQL：例如单表限制、聚合表达式和基表模型限制需要一起满足。本课 `orders_imported` 是 Unique Key 表，不能直接照搬 Duplicate Key 表的同步聚合示例。详细约束见 [同步物化视图](https://doris.apache.org/docs/4.x/query-acceleration/materialized-view/sync-materialized-view/)。

异步物化视图将维护工作拆成独立任务。消费者可以直接查询其名称，也可以继续查询基表，由优化器在满足条件时透明改写。创建成功、刷新成功、直接查询成功和透明改写成功，是四个不同的检查点。

### 拆开阅读 Lab 8 的定义

**以下是 Notebook 中的 DDL 阅读示例，不额外执行。**

<!-- reading-only-example -->
```sql
CREATE MATERIALIZED VIEW orders_daily_mv_l2
BUILD IMMEDIATE
REFRESH AUTO ON MANUAL
AS
SELECT DATE(event_time) AS order_date,
       COUNT(*) AS order_count,
       SUM(order_amount) AS gross_amount
FROM orders_imported
GROUP BY DATE(event_time);
```

| 片段 | 含义 | 不能据此推断的事情 |
| --- | --- | --- |
| `BUILD IMMEDIATE` | 创建后触发首次构建 | CREATE 返回就代表数据已全部就绪 |
| `REFRESH AUTO` | 尝试根据变化判断刷新范围，无法增量时全量刷新 | 每次只计算新增的几行 |
| `ON MANUAL` | 后续刷新由手动操作触发 | 每次 SELECT 都自动刷新 |
| `GROUP BY DATE(event_time)` | 结果为一天一行 | 结果仍然能按每个客户下钻 |

这个物化视图没有声明分区映射，因此不能用它演示“只有某一天的分区被刷新”。它也没有保留 `customer_id`，不能用来回答任意客户过滤后的总金额。预计算省掉了明细信息，也减少了之后可以自由组合的查询维度。

语法及 `AUTO` 的全量回退规则见 [创建异步物化视图](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/table-and-view/async-materialized-view/CREATE-ASYNC-MATERIALIZED-VIEW/)。

## 8.3 分区增量刷新

### 增量刷新与逐条事件累加不同

假设基表按订单日期分区，物化视图也能根据查询定义建立明确的分区映射。1 月 3 日分区发生变化时，Doris 可以只重新计算受影响的物化视图分区，避免重新计算所有历史分区。这里的“增量”是刷新范围缩小到分区；受影响分区内部仍可能需要重算。

| 基表变化 | 有可推导分区映射时的分析 | 需要观察的证据 |
| --- | --- | --- |
| 新增一个日期分区 | 可能创建并刷新对应物化分区 | 基表/视图分区对应关系、任务范围 |
| 订正历史某天订单 | 对应旧分区可能失效并需要刷新 | 旧分区是否被纳入任务 |
| JOIN 的客户维表修改地域 | 影响可能跨越多个日期，不能只看订单新增分区 | 非分区关联表变化对刷新范围的影响 |
| 无法推导分区对应关系 | AUTO 可能需要全量刷新 | 实际任务策略，而不是只看 AUTO 字样 |

具体支持哪些基表、分区表达式和外部 Catalog，以及 JOIN 变化如何影响分区有效性，应按目标版本的[异步物化视图使用指南](https://doris.apache.org/docs/4.x/query-acceleration/materialized-view/async-materialized-view/use-guide/)核对。不能把分区增量刷新理解为数据库对所有 DISTINCT、JOIN 和窗口 SQL 都能逐行维护。

例如 1 月 2 日金额从 200 改成 180，简单地再次向一个 `SUM` 列追加 180，会得到 380，而不是 180。刷新正确的当天结果和追加一条汇总值，是不同操作。Module 10 会继续讨论快照重算与增量事件的区别。

### 查看状态后再读取结果

完成 Lab 8 的建视图步骤后，先在该 Notebook 内执行下面的 Python 单元。`lab.database` 使用当前实验库，避免把另一个人的演示库写死在 SQL 中。

```python
lab.sql(
    f"SELECT * FROM mv_infos('database'='{lab.database}') "
    "WHERE Name = 'orders_daily_mv_l2'",
    title="物化视图状态与刷新信息",
)
```

重点看 `State`、`RefreshState`、`RefreshInfo` 和 `SyncWithBaseTables`。`INIT` 表示还不能据此宣布构建完成；刷新失败应查对应任务和错误原因；同步标志要结合基表是否仍在变化解释。不同版本的状态字段细节以实际返回为准。

**确认刷新成功且基表在核对期间不再变化后**，直接读取物化结果：

```sql
SELECT order_date, order_count, gross_amount
FROM orders_daily_mv_l2
ORDER BY order_date;
```

应与 8.1 的独立基表聚合一样，返回 `2026-01-01 / 10 / 1400.00`。直接查到正确结果只证明这次物化数据正确，还没有证明消费者查询使用了它。

## 8.4 刷新策略与改写验证

### 将触发时机、刷新范围和新鲜度分开

刷新策略需要回答三个问题：什么时候启动、重算哪些数据、允许消费者看到多旧的数据。定时刷新决定启动时机；AUTO/COMPLETE 决定范围策略；`grace_period` 则影响透明改写时允许的数据延迟，它不会替你启动刷新任务。

| 需求 | 可以考虑的方案 | 必须检查 |
| --- | --- | --- |
| 数据批次完成后再发布 | 导入完成后手动刷新并验收 | 导入完成信号、任务完成状态、批次核对 |
| 周期性更新看板 | 定时刷新 | 周期间隔、排队/执行耗时、失败重试 |
| 修复需要重算全部物化数据 | COMPLETE 全量刷新 | 资源预算、源数据可用性、结果核对 |
| 接受有限的旧结果以提高改写机会 | 明确配置并评审 `grace_period` | 可接受延迟、业务告知、超时行为 |

如果任务每 5 分钟启动一次，还要排队 1 分钟、执行 2 分钟，就不能宣称数据最多延迟 5 分钟。迟到源数据、刷新队列和 BI 缓存还会继续增加端到端延迟。

下面是**故障恢复操作说明，仅在自己的实验库需要重刷时执行**。它会提交刷新任务，任务完成仍需要检查状态；不是日常查询的一部分。

<!-- manual-operation -->
```sql
REFRESH MATERIALIZED VIEW orders_daily_mv_l2 COMPLETE;
```

失败恢复应依次确认基表可读、定义仍有效、执行账号权限与资源满足要求，修复原因后重新刷新。重试成功后再核对结果；不要只修改容忍延迟来掩盖一直失败的刷新。语法见 [REFRESH MATERIALIZED VIEW](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/table-and-view/async-materialized-view/REFRESH-MATERIALIZED-VIEW/)。

### 用基表查询证明透明改写

透明改写意味着消费者仍然查询基表，优化器选用等价且允许使用的物化结果。直接 `SELECT ... FROM orders_daily_mv_l2` 不是透明改写证据，因为查询已经明确指定了物化视图。

```sql
EXPLAIN
SELECT DATE(event_time) AS order_date,
       COUNT(*) AS order_count,
       SUM(order_amount) AS gross_amount
FROM orders_imported
GROUP BY DATE(event_time)
ORDER BY order_date;
```

在扫描节点中查找实际使用的对象。计划若仍扫描 `orders_imported`，就应记录“本次未采用该物化视图”，不能因为建过视图就写成“命中”。从以下顺序排查更容易定位问题：

1. 物化结果是否构建完成、状态有效，基表是否刚发生变化？
2. 两个查询的过滤条件、JOIN、聚合函数和粒度是否匹配？
3. 查询要求的列是否在物化结果中保留，是否满足改写支持范围？
4. 会话改写设置、统计信息和优化器成本选择是否使基表计划更合适？

例如服务视图有 `order_amount > 0`，而物化视图定义没有该过滤。当前样本结果恰好相等，不代表在所有输入上两条 SQL 等价。应使用上面与物化定义一致的基表查询研究改写，避免把样本巧合当作优化器必须采用视图的理由。

完整验收应同时保留：刷新成功的状态、与独立基表查询一致的结果、基表查询的 EXPLAIN。性能结论还需要实际 Profile 与同条件下多次测量；它不由这三个正确性检查自动产生。

## 动手实验：从稳定定义到可核对的物化结果

打开 [Lab 8](lab8_views_and_materialized_views.ipynb)，依次连接实验库、创建普通视图、创建异步物化视图、查询元数据并阅读 EXPLAIN。实验只重建 `_l2` 对象，源表来自 Lab 5。Notebook 使用课程专用的 `connect_sandbox()` 连接函数，并只重建本模块 `_l2` 对象；`DW_DATABASE` 使用已有数据的 `dw_course_l1_*` 专用库。若用维护脚本执行，而不是在 Notebook 中逐单元运行，才需要先设置 `DW_ALLOW_WRITES=yes`。

### 数据说明与验收

[数据说明](../../datasets/README.md)记录了初始订单的来源和金额口径。实验的 10 条模拟订单与 WWI 历史订单分开存储；不要把不同日期和来源的样本混成全站销售额。

| 检查 | 预期 |
| --- | --- |
| 普通视图在当前样本上的行数 | 10 |
| 基表日汇总 | 一行，订单数 10，金额 1400.00 |
| 刷新完成后的物化结果 | 与相同口径的基表日汇总一致 |
| EXPLAIN | 根据真实扫描节点记录采用/未采用物化视图 |

当前 Notebook 会等待首次刷新完成，并核对物化结果；如 30 秒内未完成，会提示检查刷新状态。还需结合 EXPLAIN 判断查询是否采用物化视图。同步物化视图、分区映射、追加分区和刷新失败恢复是本讲解释的扩展场景，当前 Notebook 没有自动完成这些实验。

### 独立思考与参考解释

假设消费者增加“按客户筛选”的要求，现有日物化视图是否足够？先写出新查询需要的列，再决定是否调整物化粒度。

<details>
<summary>参考解释</summary>

日汇总只剩日期、订单数和金额，客户信息已丢失。可以保留日期与客户的组合粒度，再按日期做上卷；这通常增加物化行数和存储。是否值得保留，应由查询需求和维护成本决定。无论如何，发布给既有消费者的列名和金额含义都不能悄悄改变。

</details>

## 单元总结

- 普通视图保存定义；物化视图保存结果，省去的查询工作转移到了维护阶段。
- 同步与异步物化视图的支持范围和一致性不同；先核对基表模型，再选择方案。
- AUTO 尝试分区增量刷新，无法增量时可能全量刷新；手动、定时和延迟容忍各管不同问题。
- 状态、结果和基表查询计划共同构成验收证据；结果存在不等于采用了改写。
- 视图接口的粒度、过滤与业务含义需要保持稳定，底层优化不能改变指标定义。

## 知识测验

完成讲义和实验后打开 [Quiz 8](quiz8_views_and_materialized_views.ipynb)。5 道单选题分别检查定义、刷新选择、结果验证、改写证据和服务契约；不需要数据库。

## 官方参考资料

- [同步物化视图](https://doris.apache.org/docs/4.x/query-acceleration/materialized-view/sync-materialized-view/)：单表范围、基表模型与表达式约束。
- [异步物化视图概述](https://doris.apache.org/docs/4.x/query-acceleration/materialized-view/async-materialized-view/overview/)：构建、刷新与透明改写。
- [异步物化视图使用指南](https://doris.apache.org/docs/4.x/query-acceleration/materialized-view/async-materialized-view/use-guide/)：分区映射、刷新策略及适用场景。
