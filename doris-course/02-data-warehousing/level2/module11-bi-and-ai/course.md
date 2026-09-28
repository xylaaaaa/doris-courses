# 模块 11：BI 与 AI 应用

| 课程信息 | 说明 |
| --- | --- |
| 所属课程 | Data Warehousing with Apache Doris · Level 2 |
| 产品范围 | Apache Doris 4.x；示例使用课程 4.1.3 沙箱 |
| 前置知识 | Module 8 的视图、Module 9 的粒度、Module 10 的指标契约 |
| 建议用时 | 约 80 分钟：阅读 45 分钟、实验 30 分钟、测验 5 分钟 |

[Level 2 目录](../README.md) · [打开 Lab 11](lab11_bi_and_ai_delivery.ipynb) · [打开 Quiz 11](quiz11_bi_and_ai.ipynb)

## 单元目标

你给 BI 团队开通了 `orders` 表的查询权限，一周后：

**BI 团队：** "为什么我们的销售额比财务的少 10%？"  
**你：** "哦，`order_amount` 字段是税前金额，不是实收款"  
**BI 团队：** "那我们之前做的 100 张报表全错了？"

**问题出在哪？**
- ✅ 权限授对了（BI 能查到数据）
- ❌ 契约没说清（BI 不知道字段的业务含义）

**BI 和 AI 消费者需要的不是一张"能查出来"的表，而是可理解、可授权、可刷新、可验收的数据接口。**

本单元把 Module 10 的指标包装成语义视图，说明看板如何连接 Doris、哪些列是维度或度量，再介绍 Apache Doris MCP Server 如何提供受 SQL 安全约束的只读工具。

### 学习目标

完成本单元后，你应当能够：

1. 设计名称稳定的消费者语义视图
2. 区分看板维度和指标度量
3. 准备特征投影，但不夸大模型质量结论
4. 在服务消费者前验证空值、新鲜度和行数
5. 记录 Doris SQL 与下游 BI 或 AI 工具之间的边界

## 单元安排

| 小节 | 核心问题 | 建议用时 |
| --- | --- | --- |
| 11.1 什么是消费者契约？ | 看板应该依赖哪些列？ | 10 分钟 |
| 11.2 如何连接 BI 看板？ | Superset + Doris | 10 分钟 |
| 11.3 什么可以交给 AI？ | 特征投影 vs 模型质量 | 10 分钟 |
| 11.4 AI 如何安全读取 Doris？ | Doris MCP Server | 10 分钟 |
| 11.5 发布前检查什么？ | 新鲜度、空值、总数 | 5 分钟 |
| Lab 11 / Quiz 11 | 语义服务与知识检查 | 30 / 5 分钟 |

---

## 11.1 什么是消费者契约？

### 维度、度量和计算度量

看板通常由三类内容组成：

| 类型 | 含义 | 本课示例 |
| --- | --- | --- |
| 维度（Dimension）| 用来切分、筛选、排列结果的属性 | `order_date`、地区、产品类别 |
| 度量（Measure）| 在当前维度组合上计算的数值 | `order_count`、`gross_amount` |
| 计算度量 | 从已审核度量进一步计算的指标 | `average_order_amount` |

**常见错误：**
- ❌ 把日期当作金额求和
- ❌ 把已聚合客单价再次平均

### 创建语义视图

**以下是 Lab 11 的 DDL（阅读即可，由 Notebook 执行）：**

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

**关键点：**

| 设计选择 | 原因 |
| --- | --- |
| 保留分子和分母到发布时才计算客单价 | 避免简单平均的错误 |
| 订单数为 0 时返回 NULL | 表示没有有效分母，而不是客单价为 0 |
| 没有客户列 | 这是日级服务接口，不是客户明细接口 |
| 没有日历表关联 | 如果某天没有订单，GROUP BY 不会自动生成该日行 |

### 契约要写什么？

**消费者契约应记录：**

1. **字段名称、类型和业务含义**
   - `order_date`：订单日期（基于 `event_time`）
   - `order_count`：订单数（笔）
   - `gross_amount`：订单总金额（元，税前）
   - `average_order_amount`：客单价（元，可能为 NULL）

2. **行粒度与唯一性**
   - 一行 = 一天的汇总
   - 某天没有订单 → 不会有该日期的行

3. **时间字段、时区和覆盖范围**
   - `order_date` 来自 `DATE(event_time)`
   - 时区：课程环境设置
   - 覆盖范围：从首次导入开始

4. **刷新频率、数据延迟和迟到数据处理**
   - 手动刷新或按批次触发
   - 迟到数据：需要重刷对应日期

5. **空值、零值和缺失日期**
   - `average_order_amount` 为 NULL = 该日订单数为 0
   - 缺失日期 = 该日没有订单

6. **访问账号和敏感字段范围**
   - 只读账号，只能访问此视图
   - 不包含客户敏感信息

7. **Doris 保证什么，下游 BI/AI 负责什么**
   - Doris 保证：数据口径、刷新状态
   - BI/AI 负责：图表过滤、缓存、展示

**重要：** 底层表可以更换物化实现，只要视图的输出契约没有改变。

---

## 11.2 如何连接 BI 看板？

### Doris 与 Superset 的连接边界

**Doris 提供：** SQL 数据源  
**Superset 负责：** 图表、缓存、看板权限

**连接串格式：**
```text
doris://<username>:<password>@<host>:<port>/internal.<database>
```

**课程环境：**
- 查询端口：9030（容器内）
- 从宿主机连接：使用映射的本地端口
- 不要把容器内部端口和宿主机端口混写

**连接前检查：**

| 检查项 | 如何验证 |
| --- | --- |
| 用户权限 | 只能访问发布视图和必要对象 |
| Catalog 和数据库 | 使用 `internal` Catalog 和正确数据库 |
| 查询结果 | 与 Lab 10 的独立核对一致 |
| BI 数据集 | 金额字段不是字符串，不重复聚合 |
| 时间列 | 默认时区和刷新频率写入说明 |

### 速度、新鲜度、准确性的 SLA

**把"看板好用"拆成三个 SLA：**

| 目标 | 数据库侧指标 | 还需要谁负责 |
| --- | --- | --- |
| 速度 | 查询延迟、扫描行数、Profile 中算子耗时 | BI 查询配置、并发、缓存 |
| 新鲜度 | 最后成功刷新时间、数据最大事件时间 | 调度、迟到数据处理、BI 缓存 |
| 准确性 | 固定期望、独立明细核对、空值/行数检查 | 指标负责人、图表过滤和展示 |

**不能用"查询返回 200 ms"证明看板数据新鲜。**  
**也不能用"图表显示了数字"证明指标口径正确。**

### 看板指标的最小示例

本课不强制安装 Superset。完成 Lab 11 后，可先用 Doris SQL 验证：

```sql
SELECT order_date,
       order_count,
       gross_amount,
       average_order_amount
FROM bi_order_metrics_l2
WHERE order_date >= '2026-01-01'
ORDER BY order_date;
```

**在 BI 工具中：**
- `order_date` → 时间维度
- `order_count`, `gross_amount` → 度量
- **不要在 BI 层把 `average_order_amount` 按行 SUM**

---

## 11.3 什么可以交给 AI？

### 特征列不是模型结论

**特征投影** 把经过类型、命名和质量检查的输入交给下游模型。

**它可以做什么：**
- ✅ 提供订单量、金额、均价、最近活动日期等输入
- ✅ 确保字段类型、命名、质量检查通过

**它不能做什么：**
- ❌ 不能证明模型预测准确
- ❌ 不能自动处理训练/服务时间穿越
- ❌ 不能避免标签泄漏和样本偏差

### 特征投影示例

Lab 11 的只读特征投影：

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
| `feature_average_amount` | 单笔平均金额 | 分母为 0 时的 NULL 处理 |
| `zero_order_flag` | 已有行的零订单标记 | 缺失日期不会自动补行 |

**关于向量检索：**

Doris 4.x 支持向量以 `Array<Float>` 存储并使用 ANN 索引进行近似邻居检索。

**它不等于：**
- ❌ 把一列金额直接变成"AI 特征"
- ❌ 替代离线评估

本课程当前 Lab 不创建向量索引。

---

## 11.4 AI 如何安全读取 Doris？

### 什么是 Doris MCP Server？

**Apache Doris MCP Server** 是独立的 Python 服务，通过 MySQL 协议连接 Doris，并向 MCP 客户端提供工具。

```text
MCP 客户端（Cursor / Claude 等）
         │ 工具调用
         ▼
Doris MCP Server：SQL 安全过滤、超时、结果行数限制、审计
         │ MySQL 协议
         ▼
Doris：按连接用户权限读取数据
```

**官方工具包括：**
- 数据库/表清单
- 表结构、列注释、索引
- 只读 SQL
- 审计日志

**它不是：**
- ❌ Doris FE 内置的 SQL 语法
- ❌ 自动拥有所有数据库权限的 AI 用户

### 安全使用的最小边界

**1. 为 MCP 使用单独的只读 Doris 用户**
- 只授予发布视图所需权限
- 不把 root 账号配置给 MCP

**2. 设置环境变量，不写密码**
- 数据库、主机、端口用环境变量
- 不把密码写进 Notebook、提示词或仓库

**3. 审核每次工具调用及生成的 SQL**
- 尤其是涉及敏感列和大范围扫描的查询
- 默认安全过滤会阻止 `DROP`, `DELETE`, `INSERT` 等

**4. 使用 `max_rows`、聚合和明确的时间范围**
- 避免把大量明细直接放进模型上下文

**5. 将表中业务文本视为不可信数据**
- 模型读取的内容不能改变工具安全规则

**6. 记录审计日志**
- 保留谁在什么时间通过什么工具读了什么对象

**MCP 适合：**
- ✅ Schema 探索
- ✅ 只读分析
- ✅ 运维查询辅助

**MCP 不适合：**
- ❌ 生产写入链路
- ❌ 把"模型说查询正确"当作指标验收

---

## 11.5 发布前检查什么？

### 完整性检查

完成 Lab 11 后运行：

```sql
SELECT
    COUNT(*) AS serving_days,
    SUM(CASE WHEN order_count IS NULL THEN 1 ELSE 0 END) AS null_order_days,
    MIN(order_date) AS first_date,
    MAX(order_date) AS last_date,
    SUM(order_count) AS served_orders
FROM bi_order_metrics_l2;
```

**当前样本预期：**

| 检查项 | 预期值 |
| --- | --- |
| serving_days | 1 |
| null_order_days | 0 |
| first_date | 2026-01-01 |
| last_date | 2026-01-01 |
| served_orders | 10 |

**生产验收应检查：**
- 日期覆盖范围
- 最大事件时间
- 最后成功刷新时间
- 期望批次

### 发布前检查清单

| 检查 | 通过条件 | 失败时先查什么 |
| --- | --- | --- |
| Schema | 列名、类型、粒度与契约一致 | View 定义和下游数据集映射 |
| 完整性 | 关键日期/度量空值符合规则 | 上游过滤、分母和迟到数据 |
| 数量 | 服务日数和订单量与独立查询一致 | 重复写入、漏分区、错误 JOIN |
| 金额 | 金额与明细聚合一致 | 粒度放大、币种、退款口径 |
| 新鲜度 | 最大事件时间和刷新时间达到承诺 | 调度、队列、BI 缓存 |
| 权限 | 只读用户只能看到发布范围 | 数据库授权和 BI 连接账号 |

## 动手实验：发布稳定的消费者接口

请先完成 Lab 10，再打开 [Lab 11](lab11_bi_and_ai_delivery.ipynb)。

实验内容：
1. 创建 `bi_order_metrics_l2` 视图
2. 查询看板指标
3. 准备特征投影
4. 完整性检查

### 验收标准

| 检查 | 预期 |
| --- | --- |
| 视图粒度 | 日期 |
| 服务日数 | 1 |
| 订单数 | 10 |
| 金额 | 1400.00 |
| 客单价 | 140.00 |

### 独立练习

假设 BI 团队要求增加"客户地域"筛选。

**问题：** 当前 `bi_order_metrics_l2` 是否包含所需粒度？

<details>
<summary>参考解释</summary>

**不包含。**

当前接口每行是一天，没有客户或地域。

**如果增加地域筛选：**
- 粒度变为 日期 × 地域
- 订单数和金额必须重新聚合
- 这是契约变更，不是简单加列

**解决方案：**
1. 发布新的视图（日期 × 地域粒度）
2. 或提供新的数据集
3. 分别记录刷新、权限和验收规则

**不要把地域列硬加到日粒度视图中后继续声称每行仍是日粒度。**

</details>

---

## 单元总结

- **语义视图是消费者契约**，维度、度量、粒度、单位必须清楚
- **Superset 负责图表，Doris 负责 SQL**；速度、新鲜度、准确性分别定义 SLA
- **特征投影**提供检查过的输入列，不保证模型质量
- **Doris MCP Server** 提供只读辅助；只读账号、SQL 审核、结果限制、审计仍需配置
- **发布前检查** Schema、空值、行数、金额、新鲜度、权限

---

## 知识测验

打开 [Quiz 11](quiz11_bi_and_ai.ipynb)，检查：
1. 语义视图
2. 维度度量
3. 特征投影
4. 发布校验
5. Doris/BI/AI 边界

---

## 官方参考资料

- [Apache Superset 集成](https://doris.apache.org/docs/4.x/connection-integration/data-integration/superset/)：连接串、数据集、图表配置
- [Apache Doris MCP Server](https://doris.apache.org/docs/4.x/key-features/mcp-server/)：工具、连接、安全过滤、使用边界
- [向量索引](https://doris.apache.org/docs/4.x/table-design/index/vector-index/overview/)：Array<Float>、ANN 检索、索引限制
- [视图](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/table-and-view/view/CREATE-VIEW/)：视图定义与消费者接口
