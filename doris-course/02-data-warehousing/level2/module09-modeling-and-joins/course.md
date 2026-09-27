# 模块 9：数仓建模与 JOIN

| 课程信息 | 说明 |
| --- | --- |
| 所属课程 | Data Warehousing with Apache Doris · Level 2 |
| 产品范围 | Apache Doris 4.x；示例使用课程 4.1.3 沙箱 |
| 前置知识 | Level 1 的订单、客户、质量与状态数据；Module 8 的视图 |
| 建议用时 | 约 85 分钟：阅读 45 分钟、实验 35 分钟、测验 5 分钟 |

[Level 2 目录](../README.md) · [打开 Lab 9](lab9_modeling_and_joins.ipynb) · [打开 Quiz 9](quiz9_modeling_and_joins.ipynb)

## 单元目标

业务最初只查询订单表，随后会要求按客户地域、商品类别和日期分析。新增一个 JOIN 看起来很容易，却可能让一笔 100 元订单被计算两次。本单元从“一行代表什么”出发，设计数仓分层与事实维度关系，再解释 JOIN 的逻辑语义和物理执行方式。

### 学习目标

1. 说明事实表和维表的粒度
2. 根据更新语义选择表模型和键
3. 验证一对一和一对多 JOIN 基数
4. 使用 LEFT JOIN 和反连接检查缺失维度
5. 从 EXPLAIN 中读取 JOIN 分布证据

## 单元安排

| 小节 | 核心问题 | 建议用时 |
| --- | --- | --- |
| 9.1 分层与维度建模 | ODS、DWD、DWS、ADS 分别解决什么问题？ | 12 分钟 |
| 9.2 JOIN 语义与粒度 | 为什么关联后金额会翻倍或订单会消失？ | 15 分钟 |
| 9.3 JOIN 分布与 Runtime Filter | 数据在哪里匹配，为什么会产生网络开销？ | 10 分钟 |
| 9.4 订单域落地与验收 | 如何把逻辑模型映射到课程对象？ | 8 分钟 |
| Lab 9 / Quiz 9 | 事实维度关联与知识检查 | 35 / 5 分钟 |

## 9.1 分层与维度建模

### 分层是在划分责任

设想订单持续接入，但某条记录金额无法解析；业务既需要每天的销售额，也需要追查这条记录为什么没进入报表。只保留最终汇总无法追查，只保留源数据又让每张看板重复清洗。分层让不同职责有明确落点。

| 层 | 常用名称 | 一行可能代表什么 | 主要责任 |
| --- | --- | --- | --- |
| ODS | 原始接入层 | 一次源端投递 | 保留来源、原始字段、接收标识，支持回查与重放 |
| DWD | 清洗明细层 | 一笔有效订单或一个业务事件 | 统一类型、质量、去重与状态语义 |
| DWS | 汇总层 | 日期 × 地区的一组指标 | 复用聚合口径，减少重复计算 |
| ADS | 应用服务层 | 看板需要的一行服务结果 | 稳定列名、筛选规则、粒度和刷新承诺 |

这些名称是建模约定，不是 Doris 的四种内置引擎。层可以用表或视图实现，也不要求每层都复制一遍全部字段。单纯创建四张名字带前缀的表，不能证明分层已经完成；需要说清数据如何加工、何时更新、失败如何重做。

```text
源端投递 → ODS 原始记录 → 质量/去重/状态处理 → DWD 明细
                             │                   │
                             └→ 拒收记录         ├→ 维表关联 → DWS 汇总 → ADS / BI
                                                 └→ 明细下钻与对账
```

### 事实与维度如何分工？

事实表记录可以被分析的业务过程或度量，例如下单金额、商品数量、支付金额。维表记录解释这些事实的属性，例如客户名称和商品类别。**粒度**是对“一行代表什么”的精确定义，应该先于字段清单和建表语句。

| 对象 | 粒度 | 可能的业务键 | 不能直接等同的对象 |
| --- | --- | --- | --- |
| 当前订单 | 一笔订单的当前状态 | order_id | 多条状态事件 |
| 订单商品明细 | 一笔订单的一条商品明细 | order_id + 明细编号 | 整单金额 |
| 支付流水 | 一次支付事件 | payment_id | 订单当前累计已付金额 |
| 当前客户维度 | 一个客户的当前属性 | customer_id | 客户历次属性版本 |

例如一个订单有两行商品，总金额 100，商品金额为 60 和 40。订单与商品明细关联后会产生两行；若每行都携带整单 100 再求和，就变成 200。问题发生在粒度变换，不是 SUM 算错。

本课 `orders_fact_l2` 每行来自初始订单快照。虽然它使用 `DUPLICATE KEY(order_date, order_id)`，这两个键主要组织排序，并不会强制订单唯一。Lab 每次先清空重建再写入一次，所以样本保持 10 个订单；单独重复执行 INSERT 会追加重复行。

### 选择模型时考虑更新与历史

当前客户属性适合以 `customer_id` 为 Unique Key 更新；原始投递若要保留重复内容，可以用 Duplicate Key；按维度累计可加指标可以使用 Aggregate Key。表模型是写入语义，星型还是宽表是业务组织方式，两者不能互相替代。

| 建模方式 | 优点 | 必须承担的代价 |
| --- | --- | --- |
| 星型模型：事实 + 共享维度 | 属性集中管理，多种分析复用同一维度 | JOIN 粒度、键唯一性和属性历史需要管理 |
| 宽表：把常用属性写进事实 | 常见查询少做关联，消费更直接 | 属性冗余；更正客户属性可能要更新大量记录 |
| Data Vault：Hub、Link、Satellite | 分离业务键、关系和描述历史，适合多源追溯 | 对业务查询不够直接，通常还需服务模型 |

Data Vault 的 Hub 保存稳定业务键，Link 保存业务关系，Satellite 保存带历史的描述属性。它是一种建模方法，不是 Doris 自动启用的功能。本课围绕订单域采用事实与维度模型，不展开完整 Data Vault 实现。

还有一个常被忽略的选择：查询按客户**当前地域**归类，还是按**下单时地域**归类？覆盖更新客户维表后，历史订单关联出来的地域也可能改变。如果报表要求按发生时属性解释，就需要保留维度版本与有效时间，在 JOIN 中匹配相应时段，并确保时间区间不重叠。给维表加一个更新时间，并不会自动完成这种历史匹配。

## 9.2 JOIN 语义与粒度

### 不同 JOIN 保留哪些行？

假设左侧有订单，右侧有客户。一位客户可以有多笔订单，但每笔订单在当前客户维表中应至多匹配一行。JOIN 首先决定保留哪些匹配，再由后续 GROUP BY 决定是否聚合。

| 类型 | 结果含义 | 订单场景 |
| --- | --- | --- |
| INNER JOIN | 只保留匹配成功的组合 | 只分析能关联到客户的订单 |
| LEFT JOIN | 保留所有左侧行，未匹配右侧填 NULL | 保留订单，并显示客户缺失 |
| FULL OUTER JOIN | 两侧未匹配行也保留 | 对账时同时发现多余和缺失日期 |
| LEFT SEMI JOIN | 左侧存在匹配则保留一次，不输出右列 | 找到属于某客户集合的订单 |
| LEFT ANTI JOIN | 保留没有匹配的左侧行 | 找出没有客户维度的订单 |

普通等值条件中，NULL 不与 NULL 匹配。`COUNT(*)` 统计结果行，而 `COUNT(d.customer_id)` 忽略 NULL；LEFT JOIN 后两者不同往往正好反映缺失维度。具体语法见 [JOIN](https://doris.apache.org/docs/4.x/query-data/join/)。

### 先用反例理解金额放大

下面是**不依赖任何表的只读反例**。客户 1 被错误地放入两条“当前维度记录”：

```sql
WITH facts AS (
    SELECT 1 AS order_id, 1 AS customer_id, 100 AS amount
    UNION ALL SELECT 2, 2, 200
), dim AS (
    SELECT 1 AS customer_id, 'EAST' AS region
    UNION ALL SELECT 1, 'WEST'
    UNION ALL SELECT 2, 'EAST'
)
SELECT COUNT(*) AS joined_rows, SUM(f.amount) AS joined_amount
FROM facts f
JOIN dim d ON f.customer_id = d.customer_id;
```

| 检查点 | 行数 | 金额 |
| --- | ---: | ---: |
| 原始事实 | 2 | 300 |
| JOIN 后 | 3 | 400 |

订单 1 匹配了两行，100 元被累计两次。`COUNT(DISTINCT order_id)` 此时仍然是 2，单独看订单去重数发现不了金额放大。`SUM(DISTINCT amount)` 也不是修复办法：两笔不同订单可以恰好都是 100 元，这样会错误去掉一笔金额。

正确做法是先恢复维度粒度：确定哪个版本代表当前状态，或按有效期匹配历史版本；然后重新检查 JOIN 行数与金额。不能随便 `MAX(region)` 挑一个字符串冒充业务版本裁决。

### 缺失维度不应该被 INNER JOIN 悄悄隐藏

完成 Lab 9 后运行：

```sql
SELECT f.customer_id, COUNT(*) AS orders_without_dimension
FROM orders_fact_l2 f
LEFT JOIN customers_dim_l2 d ON f.customer_id = d.customer_id
WHERE d.customer_id IS NULL
GROUP BY f.customer_id
ORDER BY f.customer_id;
```

右侧 `customer_id` 在本实验中声明为 NOT NULL，因此空值可以表示未匹配。若没有缺失，查询返回零行；出现结果时，需要选择补维度、暂存待处理记录，或按明确的“未知客户”规则展示，而不是因为少了 JOIN 结果就认为订单不存在。

当前 Lab 从 `customers` 取 `LIMIT 20` 条记录，没有排序。它是一个简化维表样本，不保证任何数据库状态下都覆盖所有事实客户；不要把“恰好返回空表”当作无条件保证。完整服务模型应加载所有相关客户，或按事实客户集合精确选取维度，并用上述查询验收。

把右表过滤放在 WHERE 中也会改变保留行为。例如 `LEFT JOIN ... WHERE d.region = 'EAST'` 会排除未匹配订单；如果需求是保留全部订单，只在能匹配 EAST 时补属性，应将该条件放入 ON，并解释剩余行的 NULL 含义。

### 先聚合再 JOIN 的前提

一笔订单有两条商品和两笔支付，直接把两张明细按 order_id 连接，会得到 2 × 2 = 4 行。商品金额和支付金额都会被重复累计。若最终需要每单一行，应先将每张明细各自汇总到订单粒度再关联：

```sql
WITH items AS (
    SELECT 1 AS order_id, 60 AS amount
    UNION ALL SELECT 1, 40
), payments AS (
    SELECT 1 AS order_id, 30 AS amount
    UNION ALL SELECT 1, 70
), item_total AS (
    SELECT order_id, SUM(amount) AS order_amount
    FROM items GROUP BY order_id
), payment_total AS (
    SELECT order_id, SUM(amount) AS paid_amount
    FROM payments GROUP BY order_id
)
SELECT i.order_id, i.order_amount, p.paid_amount
FROM item_total i
LEFT JOIN payment_total p ON i.order_id = p.order_id
ORDER BY i.order_id;
```

预期为 `1 / 100 / 100`。这里的依据是最终需要订单粒度，两边也都能安全聚合到订单粒度。若需求改为按商品类别统计，提前丢掉商品维度就会损失必要信息；若维表业务键本身重复，先聚合事实也不能修复重复匹配。不能将“先聚合再 JOIN”作为无条件优化规则。

## 9.3 JOIN 分布与 Runtime Filter

### 逻辑 JOIN 与物理搬运是两回事

INNER/LEFT 规定结果语义；Broadcast/Shuffle 决定数据如何送到执行匹配的节点。改变物理策略的前提是结果语义保持一致。

| 策略 | 如何组织数据 | 适用条件与主要成本 |
| --- | --- | --- |
| Broadcast | 将一侧数据发送到参与 JOIN 的节点 | 适合较小构建侧；每份复制占内存，多节点和高并发会放大成本 |
| Shuffle | 按连接键重新分发数据 | 两侧较大时常见；承担网络与分区处理成本 |
| Bucket Shuffle | 利用一侧已有分桶，按对应桶路由另一侧 | 连接键与已有分布满足条件；减少部分重分发 |
| Colocate | 对齐相关表的桶及副本放置，使匹配在本地进行 | 相同 Colocation Group、兼容的分桶列类型/数量、桶数与副本布局，并满足连接条件 |

两张表都写 `HASH(customer_id)` 不代表已经 Colocate。还要有正确的同组配置和稳定的布局；本课一台 BE、一个桶的 Lab 也不能证明多节点网络传输已经被消除。详见 [Colocation Join](https://doris.apache.org/docs/4.x/query-acceleration/colocation-join/)。

Runtime Filter 是执行期间从 JOIN 构建侧生成的过滤信息，用来提前减少另一侧不可能匹配的数据。例如客户集合只包含一小部分 ID，可以让订单扫描尽早跳过无关数据。它不替代最终 JOIN 判断，也不保证所有 JOIN 类型和数据分布都获得收益；过滤器形成时间、选择性和传输成本都会影响效果。

### 先看计划，再看实际执行

完成 Lab 9 后，对同一个关联查询读取计划：

```sql
EXPLAIN
SELECT f.order_id, d.customer_name
FROM orders_fact_l2 f
JOIN customers_dim_l2 d ON d.customer_id = f.customer_id;
```

先找 JOIN 类型和等值条件，再找分布方式、Exchange 节点和两侧扫描对象。`EXPLAIN SHAPE PLAN` 可用于简化阅读计划结构；实际 SQL 执行后的 Query Profile 才能帮助判断行数、算子耗时和内存。相关方法在 Module 10 展开。

当统计信息不足或过时，优化器可能错误估计构建侧大小。排查应先核对表行数、过滤选择性与统计信息，再判断是否需要调整分桶或使用 Hint。强制 Broadcast 可能把小样本查询变快，却让真实大表在并发下内存吃紧。

[JOIN 分布调整文档](https://doris.apache.org/docs/4.x/query-acceleration/tuning/tuning-plan/adjusting-join-shuffle/)提供 Hint 的语法和边界。本讲不设置全局参数，也不把一次 Notebook 耗时作为推荐策略的依据。

## 9.4 订单域落地与验收

### 把分层映射到已有对象

Level 1 已经处理导入、坏数据和重放，不需要为了展示分层再次启动一套 CDC。先画清现有对象的职责，再识别仍需补足的加工环节。

| 层次职责 | 已有或后续对象 | 实际边界 |
| --- | --- | --- |
| 原始输入 | `orders_raw` 与模拟输入文件 | 保留质量练习原始文本；不是完整生产 ODS |
| 合格明细 | `orders_clean` | Lab 6 的合格初始记录；当前状态另见 Lab 7 |
| 本模块事实/维度 | `orders_fact_l2`、`customers_dim_l2` | 从初始快照复制用于 JOIN，不自动订阅 CDC |
| 日汇总 | Module 10 的 `daily_order_metrics_l2` | 粒度为日期 × 来源 |
| 消费者接口 | Module 11 的 `bi_order_metrics_l2` | 对日汇总再聚合，发布日指标 |

当前 Lab 9 使用 `orders_imported`，没有直接连接到 `orders_clean` 或 Lab 7 的状态表。这是为了固定初始样本、单独观察 JOIN 语义；不能把上述职责映射说成已经运行的 ODS→DWD→DWS→ADS 自动流水线。生产加工还需要调度、数据批次、质量闸门和发布失败恢复。

在真实流水线中，更稳妥的顺序是：记录输入批次，清洗去重，验证维度，生成候选汇总，核对结果，再发布给消费者。中途失败时，重做哪一层和哪些分区必须明确；Duplicate/Aggregate 表重复追加不会自动实现整条链路幂等。

### 同时检查键、行数与金额

完成 Lab 9 后运行下面的只读诊断：

```sql
SELECT 'before_join' AS stage,
       COUNT(*) AS row_count, COUNT(DISTINCT order_id) AS order_count,
       SUM(order_amount) AS amount
FROM orders_fact_l2
UNION ALL
SELECT 'after_left_join', COUNT(*), COUNT(DISTINCT f.order_id), SUM(f.order_amount)
FROM orders_fact_l2 f
LEFT JOIN customers_dim_l2 d ON f.customer_id = d.customer_id
ORDER BY stage;
```

正常初始样本中，两行都应为 `10 / 10 / 1400.00`。这个比较能发现行数或金额放大，但 LEFT JOIN 下缺维度仍可能保留这些总数，所以还要结合 9.2 的反连接检查。仅有金额相等也不足以发现两笔订单一增一减、相互抵消的错误，重要发布还应核对字段明细。

`customers_dim_l2.region` 在当前 Notebook 中统一填入字符串 `known`。它只是示例占位属性，不能解释成 WWI 客户真实地域，也不能据此交付东西区销售报表。需要地域时，应明确采用哪份可信维度及发生时/当前口径。

## 动手实验：订单事实与客户维度

打开 [Lab 9](lab9_modeling_and_joins.ipynb)，在已完成 Lab 5 和 Lab 6 的同一专用库中依次建事实表和维表、关联客户、检查缺失维度、查看聚合和执行计划。Lab 5 提供 `orders_imported`，Lab 6 提供经过质量处理的 `customers`；Notebook 会在写入前检查这两项前置数据。初始化只重建本模块 `_l2` 表；逐段执行 INSERT 前注意重复追加语义。

### 数据说明与验收

初始事实来自 [课程模拟订单](../../datasets/README.md)，客户名称来自 WWI。实验完成后应能解释：为什么事实表是 10 行、为什么 LEFT JOIN 不应放大金额、`known` 的来源是什么，以及缺失客户检查为何不能省略。

多节点四种 JOIN 策略对比、完整四层调度和客户历史维度属于扩展场景，当前 Notebook 没有实现这些完整实验。正文中的两个 CTE 反例可以独立执行，不会修改课程对象。

### 独立练习

将 9.2 第一个反例中的客户 2 从维表中移除，分别预测 INNER JOIN 和 LEFT JOIN 的行数与金额；再解释为什么只检查总金额危险。

<details>
<summary>参考解释</summary>

INNER JOIN 保留订单 1 的两次匹配，得到 2 行、200；订单 2 消失。LEFT JOIN 保留订单 2，并仍让订单 1 匹配两次，得到 3 行、400。缺失与重复可能同时存在，甚至相互抵消部分总量误差。应该分别检查右侧键唯一性、未匹配事实和关联后行数/金额，而不是选一个恰好相等的数字作为验收。

</details>

## 单元总结

- 分层划分接入、明细、汇总和服务职责；对象前缀不能替代真实加工关系。
- 先定义事实和维度粒度，再选表模型与业务键；当前属性和历史属性回答不同问题。
- 一对多 JOIN 会放大事实行；先聚合只有在目标粒度允许时才正确。
- LEFT JOIN 与反连接让缺失维度可见，行数、键唯一性、金额和明细检查相互补充。
- 逻辑 JOIN 定义结果，物理分布定义数据搬运；EXPLAIN 与 Profile 是不同层次的证据。

## 知识测验

打开 [Quiz 9](quiz9_modeling_and_joins.ipynb)，检查粒度、模型选择、JOIN 基数、缺失维度和计划阅读。测验不需要数据库。

## 官方参考资料

- [JOIN 语义](https://doris.apache.org/docs/4.x/query-data/join/)：INNER、OUTER、SEMI 与 ANTI JOIN。
- [表模型](https://doris.apache.org/docs/4.x/table-design/data-model/overview/)：Duplicate、Unique 与 Aggregate 模型。
- [Colocation Join](https://doris.apache.org/docs/4.x/query-acceleration/colocation-join/)：分桶、同组布局与适用条件。
- [Query Profile](https://doris.apache.org/docs/4.x/query-acceleration/query-profile/)：实际运行证据。
