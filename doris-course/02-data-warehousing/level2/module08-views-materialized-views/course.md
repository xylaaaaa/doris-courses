# 模块 8：视图与物化视图

| 课程信息 | 说明 |
| --- | --- |
| 所属课程 | Data Warehousing with Apache Doris · Level 2 |
| 产品范围 | Apache Doris 4.x；示例使用课程 4.1.3 沙箱 |
| 前置知识 | Level 1 的表模型、导入、质量检查与订单状态 |
| 建议用时 | 约 75 分钟：阅读 40 分钟、实验 30 分钟、测验 5 分钟；不含环境准备 |

[Level 2 目录](../README.md) · [打开 Lab 8](lab8_views_and_materialized_views.ipynb) · [打开 Quiz 8](quiz8_views_and_materialized_views.ipynb)

## 单元目标

三个团队同时想知道"每天有多少订单、总金额多少"：

- **运营团队** 写了 `SELECT ... WHERE status = 'DELIVERED'`
- **财务团队** 写了 `SELECT ... WHERE amount > 0`
- **BI 看板** 每 5 分钟扫描一次全部明细

一个月后，三份报表的数字对不上了。更头疼的是，每次查询都重复计算同样的聚合，扫描大量明细。

**能不能让三个团队用同一个 SQL 定义，并且把计算结果存下来，查询时直接读取？**

本单元先用普通视图统一查询定义，再解释何时值得存储预计算结果，以及如何证明结果新鲜、正确且被查询使用。

### 学习目标

完成本单元后，你应当能够：

1. 区分逻辑视图和已存储的物化结果
2. 根据新鲜度和成本要求选择刷新策略
3. 通过元数据和结果检查验证物化视图
4. 使用 EXPLAIN 证明查询改写，而不是凭对象名称猜测
5. 在改变实现方式时保持已发布视图契约稳定

## 单元安排

| 小节 | 核心问题 | 建议用时 |
| --- | --- | --- |
| 8.1 为什么需要视图？ | 三个团队的 SQL 为什么会逐渐不同？ | 8 分钟 |
| 8.2 什么时候值得预计算？ | 物化视图解决什么问题，带来什么代价？ | 10 分钟 |
| 8.3 增量刷新是如何工作的？ | AUTO 真的只计算新增数据吗？ | 12 分钟 |
| 8.4 如何证明查询用了物化视图？ | 创建成功 ≠ 查询采用 | 10 分钟 |
| Lab 8 / Quiz 8 | 创建对象、阅读计划、核对概念 | 30 / 5 分钟 |

---

## 8.1 为什么需要视图？

### 从一个真实场景开始

假设你在 Lab 5 中导入了 10 条订单，现在三个团队都想知道"每天有多少订单、总金额多少"。

**运营团队的查询：**
```sql
SELECT DATE(event_time) AS order_date,
       COUNT(*) AS order_count,
       SUM(order_amount) AS gross_amount
FROM orders_imported
WHERE status = 'DELIVERED'  -- 只统计已送达订单
GROUP BY DATE(event_time);
```

**财务团队的查询：**
```sql
SELECT DATE(event_time) AS order_date,
       COUNT(*) AS order_count,
       SUM(order_amount) AS gross_amount
FROM orders_imported
WHERE order_amount > 0  -- 只统计有金额的订单
GROUP BY DATE(event_time);
```

**问题来了：**
1. 两份 SQL 的 `WHERE` 条件不同，结果可能不一致
2. 如果运营改成 `WHERE status IN ('DELIVERED', 'SHIPPED')`，财务不知道
3. 每个看板都要重复扫描 `orders_imported`，浪费资源

### 普通视图：统一 SQL 定义

普通视图（View）是一个**保存的 SQL 定义**。你创建视图时，Doris 只记录定义，不生成结果副本。查询视图时，Doris 根据定义实时计算。

**创建一个统一的视图：**
<!-- reading-only-example -->
```sql
CREATE VIEW orders_service_view_l2 AS
SELECT DATE(event_time) AS order_date,
       customer_id,
       order_amount,
       data_source
FROM orders_imported
WHERE order_amount > 0;
```

现在三个团队都可以查询 `orders_service_view_l2`，不用再担心过滤条件不同。

**视图做了什么？**
- ✅ 统一字段定义（`DATE(event_time)` 统一命名为 `order_date`）
- ✅ 统一业务规则（`WHERE order_amount > 0`）
- ✅ 隐藏不需要的列（不暴露内部字段）

**视图没做什么？**
- ❌ 不存储数据（每次查询仍然扫描 `orders_imported`）
- ❌ 不自动加速（查询时仍然计算 `DATE(event_time)`）

```text
订单明细表 → 普通视图（保存定义） → 消费者查询（实时计算）
```

### 关于语义层的补充

"语义层"就是对消费者统一说明名称、含义和计算规则的接口层。

**你应该记录：**
- 每列的业务含义（`order_amount` 是税前金额还是实收款？）
- 金额单位（元？分？美元？）
- 时间口径（`order_date` 是下单日还是支付日？）
- 空值含义（`NULL` 是"未支付"还是"数据丢失"？）
- 负责人（数据异常时找谁？）

**为什么要记录这些？**

即使 SQL 仍能运行，改名、换日期含义、把含退款金额改成净金额，都可能破坏契约。消费者会悄悄得到错误结果，而不是收到报错。

> **注意：** 普通视图常作为发布入口，但创建 View 不等于配置了用户权限。账号授权和实际可访问范围需要单独验证，权限操作放在 Module 12。

---

## 8.2 什么时候值得预计算？

### 视图解决了定义统一的问题，但查询还是慢

假设 `orders_imported` 有 100 万行，每次查询都要：
1. 扫描 100 万行
2. 计算 `DATE(event_time)`
3. 按日期分组聚合

如果 BI 看板每 5 分钟查一次，每次都重复上面的计算。

**能不能提前计算好结果，存下来？**

这就是**物化视图（Materialized View）**的核心思路。

### 普通视图 vs 物化视图

| 方式 | 保存什么 | 查询时做什么 | 适合的场景 |
| --- | --- | --- | --- |
| 普通视图 | SQL 定义 | 实时计算 | 统一字段和业务逻辑 |
| 物化视图 | 计算好的结果 | 直接读取结果 | 固定的聚合查询，查询频率 >> 数据更新频率 |

### 物化视图的两种类型

Doris 支持两种物化视图：

**1. 同步物化视图（Sync Materialized View）**
- 写入时同步维护（和基表的写入在一个事务里）
- 保证一致性，但有限制：
  - 只支持单表
  - 基表是 Unique Key 时，只能调整列顺序，不能聚合
  - 聚合表达式有限制

**2. 异步物化视图（Async Materialized View）**
- 独立的刷新任务（不在写入链路）
- 支持多表 JOIN、复杂聚合
- 可以接受数据延迟

本课重点讲**异步物化视图**，因为它更灵活，适合大多数数仓场景。

### 创建一个异步物化视图

**以下是 Lab 8 的定义（仅阅读，由 Notebook 执行）：**

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

**拆解这个定义：**

| 关键字 | 含义 | 常见误解 |
| --- | --- | --- |
| `BUILD IMMEDIATE` | 创建后立即开始首次构建 | ❌ CREATE 返回 ≠ 数据已就绪 |
| `REFRESH AUTO` | 尝试增量刷新，无法增量时全量刷新 | ❌ 每次只计算新增的几行 |
| `ON MANUAL` | 需要手动触发刷新 | ❌ 每次 SELECT 自动刷新 |
| `GROUP BY DATE(...)` | 结果按天聚合 | ❌ 仍能按客户下钻 |

**这个物化视图做了什么？**
- ✅ 把 100 万行明细聚合成 365 行（一天一行）
- ✅ 预计算了 `COUNT(*)` 和 `SUM(order_amount)`
- ✅ 查询时直接读 365 行，而不是扫描 100 万行

**这个物化视图没做什么？**
- ❌ 没有保留 `customer_id`（不能按客户筛选）
- ❌ 没有声明分区映射（不能演示"只刷新某一天"）
- ❌ 不会自动刷新（需要手动或定时触发）

### 什么时候不该用物化视图？

**❌ 不适合的场景：**

1. **查询模式变化频繁**
   - 今天按日期汇总，明天按客户汇总，后天按地区汇总
   - 每次都要重建物化视图，成本太高

2. **数据更新非常频繁**
   - 每秒导入 1000 行
   - 物化视图刷新跟不上，查询时数据总是旧的

3. **只查询一次的临时分析**
   - 一次性的探索查询
   - 创建物化视图的成本 > 直接查询的成本

4. **样本数据太小**
   - 本课的 10 行订单，预计算反而更复杂
   - 样本用于理解语义，不用于证明加速倍率

**✅ 适合的场景：**

1. **固定的报表查询**（每天早上 9 点的销售日报）
2. **复杂的聚合计算**（跨 7 张表的 JOIN + GROUP BY）
3. **查询频率 >> 数据更新频率**（每小时查 100 次，每天更新 1 次）

---

## 8.3 增量刷新是如何工作的？

### AUTO 不等于"只计算新增数据"

你可能听说过"增量刷新"，以为 Doris 会自动识别新增的几行数据，只计算这几行。

**实际上，"增量"指的是刷新范围缩小到分区，而不是逐行累加。**

### 增量刷新的工作原理

假设基表按订单日期分区：

| 日期 | 分区名 | 订单数 |
| --- | --- | --- |
| 2026-01-01 | p20260101 | 100 |
| 2026-01-02 | p20260102 | 150 |
| 2026-01-03 | p20260103 | 200 |

**如果 1 月 3 日的分区发生变化：**
- ✅ 增量刷新：只重新计算 `p20260103` 对应的物化分区
- ❌ 全量刷新：重新计算 1 月 1 日到 3 日的所有分区

**关键前提：**
1. 基表按日期分区
2. 物化视图也按日期聚合
3. Doris 能推导出"基表分区 → 物化视图分区"的映射关系

### 什么时候会退化成全量刷新？

| 基表变化 | 能否增量刷新？ | 原因 |
| --- | --- | --- |
| 新增 1 月 4 日的分区 | ✅ 可以 | 只需创建新的物化分区 |
| 修改 1 月 2 日的某条订单 | ✅ 可以 | 只需刷新 1 月 2 日的物化分区 |
| JOIN 的客户维表改了地域 | ❌ 可能需要全量刷新 | 客户维表没有分区，影响所有日期 |
| 无法推导分区映射 | ❌ 需要全量刷新 | 比如物化视图按周聚合，基表按天分区 |

**一个常见误解：**

假设 1 月 2 日的金额从 200 改成 180，有人以为 Doris 会：
```
旧值: 200
增量: 180
新值: 200 + 180 = 380  ❌ 错误！
```

**实际上，Doris 会重新计算整个分区：**
```
1 月 2 日的所有订单 → 重新 SUM → 180  ✅ 正确
```

增量刷新是"刷新范围缩小到分区"，不是"对 SUM 列追加值"。Module 10 会继续讨论快照重算与增量事件的区别。

### 如何查看物化视图的状态？

完成 Lab 8 的建视图步骤后，执行：

```python
lab.sql(
    f"SELECT * FROM mv_infos('database'='{lab.database}') "
    "WHERE Name = 'orders_daily_mv_l2'",
    title="物化视图状态与刷新信息",
)
```

**重点看这几个字段：**

| 字段 | 含义 | 如果异常怎么办？ |
| --- | --- | --- |
| `State` | 物化视图状态 | `INIT` 表示还在构建中 |
| `RefreshState` | 刷新任务状态 | 失败时查对应任务的错误日志 |
| `SyncWithBaseTables` | 是否与基表同步 | 如果基表还在变化，这个标志会是 false |

**确认刷新成功后**，直接读取物化结果：

```sql
SELECT order_date, order_count, gross_amount
FROM orders_daily_mv_l2
ORDER BY order_date;
```

应返回 `2026-01-01 / 10 / 1400.00`（与基表聚合结果一致）。

**但这还没有证明消费者查询使用了它！** 接下来我们看如何验证。

---

## 8.4 如何证明查询用了物化视图？

### 四个不同的成功

创建物化视图后，有四个不同的检查点：

1. ✅ **创建成功**（DDL 执行成功）
2. ✅ **刷新成功**（首次构建完成，数据正确）
3. ✅ **直接查询成功**（`SELECT ... FROM orders_daily_mv_l2` 返回结果）
4. ❓ **透明改写成功**（查询基表时，优化器自动用物化视图）

**前三个成功了，不代表第四个也成功！**

### 什么是透明改写？

**透明改写** 意味着：
- 消费者仍然查询基表 `orders_imported`
- 优化器自动识别"这个查询可以用 `orders_daily_mv_l2` 回答"
- 实际执行时扫描物化视图，而不是基表

**为什么需要透明改写？**

如果每个查询都要改成 `FROM orders_daily_mv_l2`，那：
- 消费者需要知道有哪些物化视图
- 物化视图改名或删除时，所有查询都要改
- 无法自动选择最优的物化视图（如果有多个）

### 如何验证透明改写？

**错误的验证方式：**
```sql
SELECT * FROM orders_daily_mv_l2;  -- ❌ 这不是透明改写！
```
这个查询直接指定了物化视图，不需要改写。

**正确的验证方式：**
```sql
EXPLAIN
SELECT DATE(event_time) AS order_date,
       COUNT(*) AS order_count,
       SUM(order_amount) AS gross_amount
FROM orders_imported  -- 查询基表，而不是物化视图
GROUP BY DATE(event_time)
ORDER BY order_date;
```

**在 EXPLAIN 结果中查找扫描节点：**
- ✅ 如果看到 `OlapScanNode(TABLE: orders_daily_mv_l2)`，说明改写成功
- ❌ 如果看到 `OlapScanNode(TABLE: orders_imported)`，说明没有改写

### 为什么物化视图没有被使用？

如果 EXPLAIN 显示仍在扫描基表，按以下顺序排查：

**1. 物化视图本身有问题**
- [ ] 刷新是否完成？（查 `mv_infos`）
- [ ] 状态是否正常？（`State` 和 `RefreshState`）
- [ ] 基表是否刚发生变化？（`SyncWithBaseTables`）

**2. 查询和物化视图不匹配**
- [ ] 过滤条件是否一致？（物化视图有 `WHERE amount > 0`，查询没有）
- [ ] 聚合粒度是否一致？（物化视图按天，查询按客户）
- [ ] 查询的列是否都在物化视图中？（查询要 `customer_id`，但物化视图没保留）

**3. 优化器选择了其他计划**
- [ ] 改写开关是否打开？（会话设置）
- [ ] 统计信息是否准确？（可能基表计划更优）
- [ ] 是否设置了 `grace_period`？（允许的数据延迟）

**一个常见误区：**

本课的服务视图有 `WHERE order_amount > 0`，但物化视图定义没有这个过滤。即使当前 10 行样本的结果相同，优化器也不会认为两个 SQL 等价。

**应该怎么做？**
- 用与物化定义一致的基表查询验证改写
- 不要因为"样本结果相同"就期望优化器改写

### 完整的验收清单

| 检查项 | 如何验证 | 预期结果 |
| --- | --- | --- |
| 刷新成功 | `mv_infos` 查看 `RefreshState` | `SUCCESS` |
| 数据正确 | 直接查询物化视图，与基表聚合对比 | 结果一致 |
| 透明改写 | EXPLAIN 基表查询，查看扫描节点 | 扫描物化视图 |

**三个都成功了，才能说"物化视图工作正常"。**

## 动手实验：从稳定定义到可核对的物化结果

打开 [Lab 8](lab8_views_and_materialized_views.ipynb)，依次：

1. 连接实验库
2. 创建普通视图 `orders_service_view_l2`
3. 创建异步物化视图 `orders_daily_mv_l2`
4. 查询 `mv_infos` 确认刷新状态
5. 直接查询物化视图，验证结果
6. EXPLAIN 基表查询，确认是否改写

### 数据说明

实验使用 Lab 5 导入的 10 条订单：
- 初始金额合计 1400.00
- 来源 `COURSE_SIMULATION`
- 这是初始快照，不是 Lab 7 重放后的当前状态

[数据说明](../../datasets/README.md)记录了详细的来源和金额口径。

### 验收标准

| 检查 | 预期 |
| --- | --- |
| 普通视图行数 | 10 |
| 基表日汇总 | 一行，订单数 10，金额 1400.00 |
| 物化视图结果 | 与基表日汇总一致 |
| EXPLAIN | 记录是否采用物化视图（根据实际扫描节点） |

### 独立思考

**问题：** 假设消费者增加"按客户筛选"的要求，现有日物化视图是否足够？

<details>
<summary>参考解释</summary>

**不足够。**

当前物化视图只保留了 `order_date`、`order_count` 和 `gross_amount`，客户信息已丢失。

**可能的方案：**
1. 保留 `customer_id`，按 `(order_date, customer_id)` 聚合
   - 优点：支持按客户筛选，也可以上卷到天级别
   - 代价：物化行数增加（从 1 天 1 行变成 1 天 N 个客户）

2. 创建第二个按客户聚合的物化视图
   - 优点：不影响现有日汇总视图
   - 代价：额外的存储和刷新成本

**无论如何，发布给既有消费者的列名和金额含义都不能悄悄改变。**

</details>

---

## 单元总结

- **普通视图**保存定义，统一字段和业务规则；查询时仍然计算
- **物化视图**保存结果，省去查询时的计算；代价是存储和刷新成本
- **同步物化视图**在写入时维护，有基表模型和表达式限制
- **异步物化视图**独立刷新，支持多表和复杂聚合，可接受延迟
- **增量刷新**是"刷新范围缩小到分区"，不是"逐行累加"
- **透明改写**需要 EXPLAIN 验证，创建成功 ≠ 查询采用
- **视图契约**包括粒度、过滤和业务含义，底层优化不能改变指标定义

---

## 知识测验

完成讲义和实验后打开 [Quiz 8](quiz8_views_and_materialized_views.ipynb)。

5 道单选题分别检查：
1. 普通视图 vs 物化视图的区别
2. 同步 vs 异步物化视图的选择
3. 增量刷新的工作原理
4. 如何验证透明改写
5. 如何保持视图契约稳定

---

## 官方参考资料

- [同步物化视图](https://doris.apache.org/docs/4.x/query-acceleration/materialized-view/sync-materialized-view/)：单表范围、基表模型与表达式约束
- [异步物化视图概述](https://doris.apache.org/docs/4.x/query-acceleration/materialized-view/async-materialized-view/overview/)：构建、刷新与透明改写
- [异步物化视图使用指南](https://doris.apache.org/docs/4.x/query-acceleration/materialized-view/async-materialized-view/use-guide/)：分区映射、刷新策略及适用场景
- [CREATE VIEW](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/table-and-view/view/CREATE-VIEW/)：普通视图语法
- [CREATE ASYNC MATERIALIZED VIEW](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/table-and-view/async-materialized-view/CREATE-ASYNC-MATERIALIZED-VIEW/)：异步物化视图创建语法
- [REFRESH MATERIALIZED VIEW](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/table-and-view/async-materialized-view/REFRESH-MATERIALIZED-VIEW/)：手动刷新语法
