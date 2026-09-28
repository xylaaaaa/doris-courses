# 模块 10：指标加工与服务交付

| 课程信息 | 说明 |
| --- | --- |
| 所属课程 | Data Warehousing with Apache Doris · Level 2 |
| 产品范围 | Apache Doris 4.x；示例使用课程 4.1.3 沙箱 |
| 前置知识 | Level 1 的导入、质量检查、状态表；Module 9 的事实维度粒度 |
| 建议用时 | 约 90 分钟：阅读 50 分钟、实验 35 分钟、测验 5 分钟 |

[Level 2 目录](../README.md) · [打开 Lab 10](lab10_metric_processing.ipynb) · [打开 Quiz 10](quiz10_metric_processing.ipynb)

## 单元目标

“订单量”“订单金额”“客单价”和“转化率”看起来只是几个聚合函数，实际都包含业务口径、时间粒度、过滤范围和空值规则。如果这些规则只存在于看板配置里，同一个指标很容易在不同报表中得到不同答案。本单元把指标写成可审查的契约，按声明粒度加工服务表，用独立明细查询核对结果，并介绍窗口函数、近似去重和 Query Profile 的使用边界。

### 学习目标

1. 定义包含分子、分母、粒度和过滤条件的指标
2. 区分明细事实与聚合服务表
3. 使用独立明细查询验证指标
4. 使用窗口函数和条件聚合，同时避免意外改变粒度
5. 为看板消费者发布范围清晰的服务查询

## 单元安排

| 小节 | 核心问题 | 建议用时 |
| --- | --- | --- |
| 10.1 指标契约与粒度 | 一个指标究竟统计什么？ | 12 分钟 |
| 10.2 聚合服务表 | 什么时候把计算提前做成服务结果？ | 12 分钟 |
| 10.3 窗口函数与条件聚合 | 如何增加分析列而不改变行数？ | 12 分钟 |
| 10.4 精确、近似与运行证据 | UV 精度如何选择，执行代价如何验证？ | 10 分钟 |
| 10.5 服务发布与独立核对 | 如何让看板得到可复查的结果？ | 4 分钟 |
| Lab 10 / Quiz 10 | 生成、对账与知识检查 | 35 / 5 分钟 |

## 10.1 指标契约与粒度

### 指标不是一个列名

以“日订单量”为例，至少要先回答以下问题：

| 契约部分 | 示例定义 | 如果不写清楚会发生什么 |
| --- | --- | --- |
| 对象 | 初始订单快照 `orders_imported` | 把订单、订单明细和支付流水混为一谈 |
| 粒度 | 日期 × 数据来源 | 结果可能按客户或按事件行重复统计 |
| 分子 | 满足过滤条件的订单行数 | 将退款事件或明细行误算成订单 |
| 过滤 | 本实验统计全部订单，不额外按金额筛选 | 不同看板过滤不同，无法对账 |
| 时间口径 | `DATE(event_time)`，时区为课程环境设置 | UTC 与业务日边界不同 |
| 单位 | 笔数、金额为货币单位 | 金额缩放或币种含义不明 |
| 空值规则 | 分母为 0 时返回 NULL | 把“没有订单”和“比例为 0”混为一谈 |

本课样本的初始日指标可以写成：

```text
日订单量 = COUNT(*)，按 DATE(event_time)、data_source 分组
日订单金额 = SUM(order_amount)，使用相同分组
客单价 = 日订单金额 / 日订单量，订单量为 0 时为 NULL
```

`orders_imported` 的 10 行样本在 `2026-01-01` 汇总为 10 笔、1400.00。这个结果是课程模拟订单快照的教学数据，不代表实际公司的 GMV，也不包括后续支付、退款或发货事件。若业务要统计净收入，应把收款与退款的来源、粒度和时间规则另行定义。

### 先确认一行代表什么

同一份数据在不同粒度下可以得到不同的合法指标：

| 数据行粒度 | 可以直接统计 | 不能直接当作 |
| --- | --- | --- |
| 订单 | 订单数、订单金额 | 商品销量 |
| 订单商品明细 | 商品件数、商品明细金额 | 不去重的订单数 |
| 支付事件 | 支付事件数、收款金额 | 订单当前金额 |
| 日 × 来源汇总 | 服务订单量和金额 | 任意客户筛选后的明细 |

例如一笔订单有三条商品明细，`COUNT(*)` 统计明细会得到 3，`COUNT(DISTINCT order_id)` 才可能得到 1。先选函数再想粒度，通常已经把错误写进 SQL 了。

指标还要区分可加性：

- **可加指标**：订单金额在不重复关联的前提下可以按日期、地区求和。
- **半可加指标**：账户余额可以按客户相加，但跨时间直接相加通常没有意义。
- **不可加指标**：客单价、转化率不能先分别求平均再当作整体结果；应保存分子和分母，在目标粒度重新计算。

例如两天的客单价分别为 `100/1=100` 和 `1000/10=100`，简单平均仍是 100；如果是 `100/1=100` 和 `1000/100=10`，简单平均为 55，而整体口径是 `1100/101≈10.89`。因此服务表应保留 `order_count` 和 `gross_amount`，由消费查询计算客单价。

## 10.2 聚合服务表

### 为什么不让每个看板都扫描明细？

明细表适合下钻和审计，服务表适合稳定地回答高频问题。把日 × 来源的订单数和金额提前汇总，读取时只需要扫描服务粒度；代价是需要额外存储、刷新任务和对账流程。服务表不能成为删除明细的理由，明细仍然是发现聚合错误的重要证据。

**下面的 DDL 与 Lab 10 对应，阅读即可；Notebook 会在自己的 `_l2` 表上执行。**

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

这里使用 Aggregate Key 模型，是因为表中的 `order_count` 和 `gross_amount` 被声明为 `SUM` 聚合列。它表达的是“相同键的输入如何累加”，并不自动知道一次重跑是不是同一批次。如果对相同输入再次执行 INSERT，结果可能再次累加；生产流程需要批次标签、分区重算、幂等写入或其他去重设计。

`DISTRIBUTED BY HASH(order_date)` 说明数据如何分到 Tablet；`BUCKETS 1` 是教学沙箱的布局选择，不是生产建议。复制数为 1 只用于单节点课程环境，不能提供生产级故障冗余。

### 聚合表和物化视图如何选择？

两者都可以提前计算，但责任不同：

| 方案 | 适合 | 主要控制点 |
| --- | --- | --- |
| 明确的聚合服务表 | 需要编排清洗、批次、质量闸门和发布流程 | 写入幂等、重算范围、表版本和交付依赖 |
| 异步物化视图 | 复用稳定查询并让 Doris 管理刷新和透明改写 | 刷新状态、最终一致性、改写条件和资源 |
| 普通视图 | 只想统一定义，不需要存储预计算结果 | 查询时计算成本和底层数据权限 |

不要因为服务表查询快，就省略独立核对；也不要因为物化视图能透明改写，就把业务口径藏在优化器行为里。指标定义仍要有可读的 SQL 和负责人。

### 用两个方向核对聚合结果

完成 Lab 10 后，服务表查询应得到：

| order_date | data_source | order_count | gross_amount |
| --- | --- | ---: | ---: |
| 2026-01-01 | COURSE_SIMULATION | 10 | 1400.00 |

然后用一条**独立写法**从明细重新聚合，不复用服务表的 SELECT：

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

预期两边都是 10 和 1400.00。全外连接保留任一侧独有的日期，对应另一侧显示 NULL；不要先把这些 NULL 填成 0，否则会隐藏“缺少汇总行”和“真实零值”的区别。若把服务表放进 detail CTE，查询即使返回一致，也只是在重复读取同一份错误。独立核对至少应覆盖行数、金额、日期范围和关键维度；重要交付还要做逐行或抽样核对。

## 10.3 窗口函数与条件聚合

### 窗口函数保留输入行数

`GROUP BY` 把多行折叠为分组结果；窗口函数在相关行上计算，却通常保留输入行。可以把它理解成“在每行旁边补充一个跨行计算”，而不是再次改变事实表粒度。

**下面是只读 CTE 示例，不修改课程表。**

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
       LAG(gross_amount) OVER (ORDER BY order_date) AS previous_available_day_amount
FROM daily
ORDER BY order_date;
```

窗口计算的输入已经是“日”粒度，所以输出仍是一日一行。`LAG` 取得排序后的上一行，不一定是日历上的昨天；缺失日期需要先补齐日历，再计算要求连续日期的环比或移动平均。如果直接对订单明细使用 `SUM(order_amount) OVER (PARTITION BY DATE(event_time))`，每一笔订单都会带上当天总额；这适合展示或后续去重，不适合再直接 SUM 这些重复的窗口列。

常见窗口函数包括 `ROW_NUMBER`、`RANK`、`DENSE_RANK`、`SUM`、`AVG`、`LAG` 和 `LEAD`。排名要定义并列处理；累计值要定义排序稳定性；移动平均要明确窗口边界。语法和边界见 [窗口函数](https://doris.apache.org/docs/4.x/query-data/window-function/)。

### 条件聚合要保持同一粒度

条件聚合把多个业务切片放在一次扫描中：

```sql
SELECT order_date,
       SUM(CASE WHEN data_source = 'COURSE_SIMULATION'
                THEN order_count ELSE 0 END) AS simulated_orders,
       SUM(order_count) AS all_orders,
       SUM(gross_amount) AS gross_amount
FROM daily_order_metrics_l2
GROUP BY order_date
HAVING SUM(order_count) > 0
ORDER BY order_date;
```

所有表达式都按 `order_date` 聚合，所以结果仍是日期粒度。`CASE` 中的 `ELSE 0` 表示该日没有该来源时返回零；如果业务要区分“没有来源行”和“来源值为空”，就需要更明确的 NULL 规则。`HAVING` 过滤分组后的结果，`WHERE` 过滤聚合前的输入，两者不能随意替换。

## 10.4 精确、近似与运行证据

### COUNT DISTINCT、Bitmap 和 HLL 不是同一个承诺

用户去重数需要先确认精度要求、ID 类型和数据规模。Doris 官方文档对 Bitmap 和 HLL 的定位不同：Bitmap 用于精确去重，HLL 用概率方法估算基数，具体误差取决于数据和哈希过程。

| 方案 | 结果承诺 | 适合 | 代价或限制 |
| --- | --- | --- | --- |
| `COUNT(DISTINCT id)` | 精确 | 数据量可控、必须精确的核算 | 需要维护去重集合，资源随规模增长 |
| Bitmap | 精确去重 | 整数 ID 的大规模 UV 汇总 | 预聚合常使用 BITMAP_UNION 列；计数需通过 Bitmap 函数获取 |
| HLL | 近似基数 | 可接受误差的超大规模 UV | 不是精确值，必须向业务说明估算性质 |

Bitmap 的“精确”不等于所有字符串都能直接放入 Bitmap；官方示例使用整数 ID 和 `to_bitmap`，其他类型需要设计编码；要求严格精确时必须保证映射无冲突，直接哈希字符串可能产生碰撞。HLL 也不能因为某次样本恰好相等就宣称精确。详细语法见 [Bitmap 精确去重](https://doris.apache.org/docs/4.x/query-acceleration/distinct-counts/bitmap-precise-deduplication/) 和 [HLL 近似去重](https://doris.apache.org/docs/4.x/query-acceleration/distinct-counts/hll-approximate-deduplication/)。

### EXPLAIN 与 Query Profile 回答不同问题

`EXPLAIN` 是执行计划：可以阅读扫描对象、过滤条件、聚合、JOIN 和 Exchange，但它不是实际运行结果。Query Profile 是一次实际执行的诊断记录，包含算子耗时、行数、内存等运行指标。

```sql
SET enable_profile = true;
SELECT order_date, SUM(gross_amount)
FROM daily_order_metrics_l2
GROUP BY order_date;
SHOW QUERY PROFILE;
```

课程单节点适合学习字段含义，不适合据少量数据得出生产性能结论。比较性能时应固定数据、SQL、会话设置和并发，重复执行并记录扫描行数、主要算子耗时、内存和网络；一次快或慢都不能证明索引或分桶策略普遍有效。Profile 的收集和参数见 [Query Profile 分析指南](https://doris.apache.org/docs/4.x/query-acceleration/query-profile/)。

## 10.5 服务发布与验收

### 服务查询要窄，但口径要完整

面向看板的查询只暴露消费者需要的列，可以减少耦合；“窄”不意味着隐藏定义。服务接口至少要说明：

- 时间字段和时区；
- 指标粒度、单位和过滤条件；
- 是否包含迟到数据、退款或取消订单；
- 刷新触发方式和允许延迟；
- 空值、零值和无数据日期的表示；
- 发生错误时消费者应该如何处理。

例如 Module 11 的 `bi_order_metrics_l2` 输出日期、订单数、金额和客单价。它不输出客户 ID，因此不能直接支持客户下钻；它也没有把支付流水混入金额，所以不能称为净收入。接口少一列可能是契约设计，也可能是能力缺失，必须写清楚。

### 先验收数据，再优化查询

建议按以下顺序交付：

1. 用独立明细查询确认行数、金额和日期范围。
2. 检查空值、分母为零、重复键和缺失日期。
3. 将服务结果与上一版本或固定期望结果比较。
4. 再使用 EXPLAIN 和 Profile 定位资源问题。
5. 最后决定是否需要物化视图、索引、分桶或刷新策略。

如果第 1 步不通过，优化只会让错误更快地返回。质量检查和性能检查分别回答“结果对不对”和“执行代价如何”，不能互相替代。

## 动手实验：构建日指标并独立核对

打开 [Lab 10](lab10_metric_processing.ipynb)，依次创建 `daily_order_metrics_l2`、写入日期 × 来源聚合、查询看板指标，并用独立明细 CTE 对账。实验会重建带 `_l2` 后缀的表，Notebook 使用课程专用的 `connect_sandbox()` 连接函数，并连接已有 Level 1 数据的专用 `dw_course_l1_*` 数据库；若用维护脚本执行，才需要设置 `DW_ALLOW_WRITES=yes`。

| 检查 | 预期 |
| --- | --- |
| 服务表粒度 | 日期 × 数据来源 |
| 当前样本服务行 | 1 行：2026-01-01 / COURSE_SIMULATION |
| 服务订单数 | 10 |
| 服务金额 | 1400.00 |
| 独立明细核对 | detail 与 serving 的订单数和金额一致 |

当前 Lab 重点验证聚合和对账；窗口函数、Bitmap/HLL 和 Query Profile 是本讲的只读阅读示例，没有被伪装成已经完成的性能实验。生产规模、并发和误差需要用目标数据集另行验证。

### 独立练习

将指标从“订单日”改为“客户日”。先写出新的粒度和需要保留的键，再判断现有 `daily_order_metrics_l2` 是否足够。

<details>
<summary>参考解释</summary>

现有服务表没有 customer_id，因此无法从它恢复客户日结果。应从订单明细重新聚合，或建立日期 × 客户的服务表；如果同时需要看板的日期汇总，可以在保留客户粒度的结果上卷，也可以维护两个明确的服务粒度。不能把日期级金额复制给每个客户再求和。

</details>

## 单元总结

- 指标先定义对象、粒度、分子、过滤、时间和空值规则，再选择 SQL。
- 可加、半可加和不可加指标的汇总方式不同；分子分母通常比预先存储比率更可靠。
- 服务表减少重复计算，但必须有批次、刷新和独立对账语义；它不替代明细证据。
- 窗口函数通常保留输入行，条件聚合仍需保持目标粒度。
- Bitmap 是精确去重方案，HLL 是近似基数方案；EXPLAIN 和 Profile 分别描述计划与实际执行。
- 正确性验收通过后，才有理由讨论物化视图、索引、分桶和资源优化。

## 知识测验

打开 [Quiz 10](quiz10_metric_processing.ipynb)，检查指标契约、服务表、独立对账、窗口函数和消费者查询。测验不需要数据库。

## 官方参考资料

- [窗口函数](https://doris.apache.org/docs/4.x/query-data/window-function/)：窗口边界、排序和常用分析函数。
- [Bitmap 精确去重](https://doris.apache.org/docs/4.x/query-acceleration/distinct-counts/bitmap-precise-deduplication/)：Bitmap 聚合与查询。
- [HLL 近似去重](https://doris.apache.org/docs/4.x/query-acceleration/distinct-counts/hll-approximate-deduplication/)：近似基数统计。
- [Query Profile](https://doris.apache.org/docs/4.x/query-acceleration/query-profile/)：实际执行诊断。
