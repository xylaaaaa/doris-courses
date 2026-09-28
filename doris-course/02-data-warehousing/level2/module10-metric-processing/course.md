# 模块 10：指标加工与服务交付

| 课程信息 | 说明 |
| --- | --- |
| 所属课程 | Data Warehousing with Apache Doris · Level 2 |
| 产品范围 | Apache Doris 4.x；示例使用课程 4.1.3 沙箱 |
| 前置知识 | Level 1 的导入、质量检查、状态表；Module 9 的事实维度粒度 |
| 建议用时 | 约 90 分钟：阅读 50 分钟、实验 35 分钟、测验 5 分钟 |

[Level 2 目录](../README.md) · [打开 Lab 10](lab10_metric_processing.ipynb) · [打开 Quiz 10](quiz10_metric_processing.ipynb)

## 单元目标

三个团队都在计算"客单价"：

- **运营团队：** `SUM(amount) / COUNT(order_id)` = 140 元
- **财务团队：** `AVG(amount)` = 140 元
- **BI 看板：** 把两天的客单价 `(100 + 10) / 2` = 55 元

**问题：** 哪个是对的？还是都不对？

答案取决于你如何定义"客单价"：
- 是用总金额除以总订单数？（整体口径）
- 还是每天算一次客单价，再求平均？（简单平均）

**如果这些规则只存在于看板配置里，同一个指标很容易在不同报表中得到不同答案。**

本单元把指标写成可审查的契约，按声明粒度加工服务表，用独立明细查询核对结果，并介绍窗口函数、近似去重和 Query Profile 的使用边界。

### 学习目标

完成本单元后，你应当能够：

1. 定义包含分子、分母、粒度和过滤条件的指标
2. 区分明细事实与聚合服务表
3. 使用独立明细查询验证指标
4. 使用窗口函数和条件聚合，同时避免意外改变粒度
5. 为看板消费者发布范围清晰的服务查询

## 单元安排

| 小节 | 核心问题 | 建议用时 |
| --- | --- | --- |
| 10.1 什么是指标契约？ | 一个指标究竟统计什么？ | 12 分钟 |
| 10.2 为什么要提前聚合？ | 明细 vs 服务表 | 12 分钟 |
| 10.3 如何在不改变行数的情况下计算？ | 窗口函数 vs GROUP BY | 12 分钟 |
| 10.4 精确 vs 近似去重 | COUNT DISTINCT、Bitmap、HLL | 10 分钟 |
| 10.5 如何验收？ | 独立核对 + 证据保留 | 4 分钟 |
| Lab 10 / Quiz 10 | 生成、对账与知识检查 | 35 / 5 分钟 |

---

## 10.1 什么是指标契约？

### 指标不是一个列名

假设你要计算"日订单量"，至少要先回答：

| 问题 | 示例答案 | 如果不写清楚会怎样？ |
| --- | --- | --- |
| 统计什么对象？ | 初始订单快照 `orders_imported` | 把订单、订单明细、支付流水混为一谈 |
| 一行代表什么？ | 日期 × 数据来源 | 按客户重复统计 |
| 分子是什么？ | 满足过滤条件的订单行数 | 把退款事件也算成订单 |
| 有过滤条件吗？ | 本实验统计全部订单 | 不同看板过滤不同，无法对账 |
| 时间口径？ | `DATE(event_time)` | UTC 与业务日边界不同 |
| 单位？ | 笔数、金额为元 | 金额单位不明 |
| 分母为 0 怎么办？ | 返回 NULL | 把"没有订单"和"比例为 0"混淆 |

### 用一个具体例子说明

**本课样本的日指标定义：**

```text
日订单量 = COUNT(*)
          按 DATE(event_time)、data_source 分组

日订单金额 = SUM(order_amount)
            使用相同分组

客单价 = 日订单金额 / 日订单量
        订单量为 0 时返回 NULL
```

**示例数据（Lab 5 导入的 10 条订单）：**

| order_date | order_count | gross_amount | 客单价 |
| --- | ---: | ---: | ---: |
| 2026-01-01 | 10 | 1400.00 | 140.00 |

这是课程模拟订单的教学数据，不代表实际公司 GMV。

### 为什么客单价不能直接存储？

**错误示例：两天的客单价**

| 日期 | 订单数 | 金额 | 客单价 |
| --- | ---: | ---: | ---: |
| Day 1 | 1 | 100 | 100.00 |
| Day 2 | 10 | 1000 | 100.00 |
| **简单平均** | - | - | **(100+100)/2 = 100** ❌ |
| **整体口径** | **11** | **1100** | **1100/11 = 100** ✅ |

**如果是：**

| 日期 | 订单数 | 金额 | 客单价 |
| --- | ---: | ---: | ---: |
| Day 1 | 1 | 100 | 100.00 |
| Day 2 | 100 | 1000 | 10.00 |
| **简单平均** | - | - | **(100+10)/2 = 55** ❌ |
| **整体口径** | **101** | **1100** | **1100/101 ≈ 10.89** ✅ |

**结论：** 服务表应保留 `order_count` 和 `gross_amount`，由消费查询计算客单价。

---

## 10.2 为什么要提前聚合？

### 明细表 vs 服务表

**明细表**适合下钻和审计  
**服务表**适合稳定地回答高频问题

**场景：** 假设 `orders_imported` 有 100 万行

每个 BI 看板都查询：
```sql
SELECT DATE(event_time), COUNT(*), SUM(order_amount)
FROM orders_imported
GROUP BY DATE(event_time);
```

**问题：**
- 每次都扫描 100 万行
- 每次都计算 `DATE(event_time)`
- BI 每 5 分钟刷新一次 = 每小时扫描 1200 万行

**如果提前聚合成服务表：**
- 100 万行 → 365 行（一天一行）
- 查询只扫描 365 行
- 代价：额外存储 + 刷新任务

### 创建聚合服务表

**以下是 Lab 10 的 DDL（阅读即可，由 Notebook 执行）：**

<!-- reading-only-example -->
```sql
CREATE TABLE daily_order_metrics_l2 (
    order_date DATE NOT NULL,
    data_source VARCHAR(32) NOT NULL,
    order_count BIGINT SUM NOT NULL DEFAULT "0",
    gross_amount DECIMAL(18,2) SUM NOT NULL DEFAULT "0.00"
)
AGGREGATE KEY(order_date, data_source)
DISTRIBUTED BY HASH(order_date) BUCKETS 1
PROPERTIES ("replication_num"="1");
```

**关键点：**

| 字段 | 含义 | 注意 |
| --- | --- | --- |
| `AGGREGATE KEY(...)` | 相同键的输入会累加 | 不自动知道是否同一批次 |
| `order_count BIGINT SUM` | `SUM` 聚合列 | 重复 INSERT 会再次累加 |
| `BUCKETS 1` | 教学沙箱布局 | 不是生产建议 |
| `replication_num=1` | 单节点环境 | 不提供故障冗余 |

**重要：** 如果对相同输入再次执行 INSERT，结果可能再次累加。生产流程需要批次标签、分区重算或幂等写入。

### 聚合表 vs 物化视图 vs 普通视图

| 方案 | 适合 | 主要控制点 |
| --- | --- | --- |
| 聚合服务表 | 需要编排清洗、批次、质量闸门 | 写入幂等、重算范围、表版本 |
| 异步物化视图 | 复用稳定查询，Doris 管理刷新 | 刷新状态、改写条件、资源 |
| 普通视图 | 只想统一定义，不需要预计算 | 查询时计算成本 |

---

## 10.3 如何在不改变行数的情况下计算？

### 窗口函数保留输入行数

**GROUP BY：** 把多行折叠为分组结果  
**窗口函数：** 在每行旁边补充一个跨行计算

**示例（只读，不修改课程表）：**

```sql
WITH daily AS (
    SELECT DATE(event_time) AS order_date,
           COUNT(*) AS order_count,
           SUM(order_amount) AS gross_amount
    FROM orders_imported
    GROUP BY DATE(event_time)
)
SELECT order_date,
       order_count,
       gross_amount,
       SUM(gross_amount) OVER (
           ORDER BY order_date
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS cumulative_amount,
       LAG(gross_amount) OVER (ORDER BY order_date) AS previous_day_amount
FROM daily
ORDER BY order_date;
```

**解释：**
- 输入已经是"日"粒度（一天一行）
- 输出仍是"日"粒度（一天一行）
- `cumulative_amount`：累计到当天的总金额
- `previous_day_amount`：上一天的金额（如果有）

**常见窗口函数：**
- `ROW_NUMBER()`：行号
- `RANK()`, `DENSE_RANK()`：排名
- `SUM()`, `AVG()`：累计和移动平均
- `LAG()`, `LEAD()`：取前/后一行

### 条件聚合保持同一粒度

**场景：** 想知道"模拟订单"和"所有订单"的数量

```sql
SELECT order_date,
       SUM(CASE WHEN data_source = 'COURSE_SIMULATION'
                THEN order_count ELSE 0 END) AS simulated_orders,
       SUM(order_count) AS all_orders,
       SUM(gross_amount) AS gross_amount
FROM daily_order_metrics_l2
GROUP BY order_date
HAVING SUM(order_count) > 0;
```

**关键点：**
- 所有表达式都按 `order_date` 聚合 → 结果仍是日期粒度
- `CASE` 中的 `ELSE 0`：该日没有该来源时返回 0
- `HAVING` 过滤分组后的结果；`WHERE` 过滤聚合前的输入

---

## 10.4 精确 vs 近似去重

### COUNT DISTINCT、Bitmap、HLL 的区别

**场景：** 统计 UV（独立访客数）

| 方案 | 结果承诺 | 适合 | 代价或限制 |
| --- | --- | --- | --- |
| `COUNT(DISTINCT id)` | 精确 | 数据量可控、必须精确 | 资源随规模增长 |
| Bitmap | 精确去重 | 整数 ID 的大规模 UV | 需要整数 ID，预聚合用 BITMAP_UNION |
| HLL | 近似基数 | 可接受误差的超大规模 UV | 不是精确值，必须向业务说明 |

**重要：**
- Bitmap 的"精确"不等于所有字符串都能直接放入
- HLL 不能因为某次样本恰好相等就宣称精确

### EXPLAIN vs Query Profile

**EXPLAIN：** 执行计划（扫描对象、过滤条件、聚合、JOIN）  
**Query Profile：** 实际执行记录（算子耗时、行数、内存）

```sql
SET enable_profile = true;
SELECT order_date, SUM(gross_amount)
FROM daily_order_metrics_l2
GROUP BY order_date;
SHOW QUERY PROFILE;
```

**课程单节点适合学习字段含义，不适合得出生产性能结论。**

---

## 10.5 如何验收？

### 用独立明细查询核对

完成 Lab 10 后，服务表查询应得到：

| order_date | data_source | order_count | gross_amount |
| --- | --- | ---: | ---: |
| 2026-01-01 | COURSE_SIMULATION | 10 | 1400.00 |

**然后用独立写法从明细重新聚合：**

```sql
WITH detail AS (
    SELECT DATE(event_time) AS order_date,
           COUNT(*) AS order_count,
           SUM(order_amount) AS gross_amount
    FROM orders_imported
    GROUP BY DATE(event_time)
), serving AS (
    SELECT order_date,
           SUM(order_count) AS order_count,
           SUM(gross_amount) AS gross_amount
    FROM daily_order_metrics_l2
    GROUP BY order_date
)
SELECT COALESCE(d.order_date, s.order_date) AS order_date,
       d.order_count AS detail_orders,
       s.order_count AS serving_orders,
       d.gross_amount AS detail_amount,
       s.gross_amount AS serving_amount
FROM detail d
FULL OUTER JOIN serving s ON s.order_date = d.order_date
ORDER BY order_date;
```

**预期：** 两边都是 10 和 1400.00

**关键点：**
- 全外连接保留任一侧独有的日期
- 不要先把 NULL 填成 0（会隐藏"缺少汇总行"和"真实零值"的区别）
- 不要把服务表放进 detail CTE（只是在重复读取同一份错误）

### 先验收数据，再优化查询

**建议顺序：**

1. ✅ 用独立明细查询确认行数、金额、日期范围
2. ✅ 检查空值、分母为零、重复键、缺失日期
3. ✅ 将服务结果与上一版本或固定期望比较
4. 再使用 EXPLAIN 和 Profile 定位资源问题
5. 最后决定是否需要物化视图、索引、分桶

**如果第 1 步不通过，优化只会让错误更快地返回。**

## 动手实验：构建日指标并独立核对

打开 [Lab 10](lab10_metric_processing.ipynb)，依次：

1. 创建 `daily_order_metrics_l2`（Aggregate Key 表）
2. 写入日期 × 来源聚合
3. 查询看板指标
4. 用独立明细 CTE 对账

### 验收标准

| 检查 | 预期 |
| --- | --- |
| 服务表粒度 | 日期 × 数据来源 |
| 当前样本服务行 | 1 行：2026-01-01 / COURSE_SIMULATION |
| 服务订单数 | 10 |
| 服务金额 | 1400.00 |
| 独立明细核对 | detail 与 serving 的订单数和金额一致 |

### 独立练习

将指标从"订单日"改为"客户日"。

**问题：** 现有 `daily_order_metrics_l2` 是否足够？

<details>
<summary>参考解释</summary>

**不足够。**

现有服务表没有 `customer_id`，无法恢复客户日结果。

**解决方案：**
1. 从订单明细重新聚合（按日期 × 客户）
2. 或建立日期 × 客户的服务表
3. 如果同时需要日期汇总，可以在保留客户粒度的结果上卷

**不能把日期级金额复制给每个客户再求和。**

</details>

---

## 单元总结

- **指标契约**包含对象、粒度、分子、分母、过滤、时间、单位、空值规则
- **可加/半可加/不可加**指标的汇总方式不同；分子分母比预存比率更可靠
- **服务表**减少重复计算，但必须有批次、刷新和独立对账语义
- **窗口函数**通常保留输入行；条件聚合仍需保持目标粒度
- **Bitmap 精确，HLL 近似**；EXPLAIN 和 Profile 描述计划与执行
- **正确性验收通过后，才讨论性能优化**

---

## 知识测验

打开 [Quiz 10](quiz10_metric_processing.ipynb)，检查：
1. 指标契约
2. 服务表
3. 独立对账
4. 窗口函数
5. 消费者查询

---

## 官方参考资料

- [窗口函数](https://doris.apache.org/docs/4.x/query-data/window-function/)：窗口边界、排序、分析函数
- [Bitmap 精确去重](https://doris.apache.org/docs/4.x/query-acceleration/distinct-counts/bitmap-precise-deduplication/)：Bitmap 聚合与查询
- [HLL 近似去重](https://doris.apache.org/docs/4.x/query-acceleration/distinct-counts/hll-approximate-deduplication/)：近似基数统计
- [Query Profile](https://doris.apache.org/docs/4.x/query-acceleration/query-profile/)：实际执行诊断
