# 模块 9：数仓建模与 JOIN

| 课程信息 | 说明 |
| --- | --- |
| 所属课程 | Data Warehousing with Apache Doris · Level 2 |
| 产品范围 | Apache Doris 4.x；示例使用课程 4.1.3 沙箱 |
| 前置知识 | Level 1 的订单、客户、质量与状态数据；Module 8 的视图 |
| 建议用时 | 约 85 分钟：阅读 45 分钟、实验 35 分钟、测验 5 分钟 |

[Level 2 目录](../README.md) · [打开 Lab 9](lab9_modeling_and_joins.ipynb) · [打开 Quiz 9](quiz9_modeling_and_joins.ipynb)

## 单元目标

业务最初只查询订单表。三个月后，需求来了：

- "按客户地域分析销售额"
- "按商品类别统计订单量"
- "给我客户名称，别只显示 customer_id"

你写了一个 JOIN，查询返回了。但财务说："这个月销售额怎么从 1 万变成 2 万了？"

**问题出在哪？** 一笔 100 元的订单，JOIN 后变成了 200 元。

本单元从"一行代表什么"出发，设计数仓分层与事实维度关系，再解释 JOIN 的逻辑语义和物理执行方式。

### 学习目标

完成本单元后，你应当能够：

1. 说明事实表和维表的粒度
2. 根据更新语义选择表模型和键
3. 验证一对一和一对多 JOIN 基数
4. 使用 LEFT JOIN 和反连接检查缺失维度
5. 从 EXPLAIN 中读取 JOIN 分布证据

## 单元安排

| 小节 | 核心问题 | 建议用时 |
| --- | --- | --- |
| 9.1 为什么要分层？ | 脏数据和报表需求的冲突 | 12 分钟 |
| 9.2 为什么 JOIN 后金额会翻倍？ | 粒度变化导致的重复计算 | 15 分钟 |
| 9.3 数据在哪里匹配？ | JOIN 的物理执行 | 10 分钟 |
| 9.4 如何验收？ | 键、行数、金额一起检查 | 8 分钟 |
| Lab 9 / Quiz 9 | 事实维度关联与知识检查 | 35 / 5 分钟 |

---

## 9.1 为什么要分层？

### 从一个真实场景开始

假设订单持续接入，但今天有一条记录的金额字段损坏了：

**业务需求 A（BI 团队）:**
"我要看今天的销售总额，报表必须出数"

**业务需求 B（数据团队）:**
"我要追查这条脏数据为什么进来了，不能直接丢掉"

**如果只保留最终汇总：**
- ✅ 报表能出数（只显示干净的总额）
- ❌ 无法追查脏数据（原始记录被丢弃了）

**如果只保留原始数据：**
- ✅ 能追查脏数据（所有原始记录都在）
- ❌ 每个报表都要写一遍清洗逻辑

**分层的本质：让不同职责有明确落点**

### 你想回答什么问题，就查哪一层

| 问题 | 应该查哪一层 | 这一层叫什么 |
| --- | --- | --- |
| "这条记录源端长什么样？" | 原始数据层 | ODS（原始接入层）|
| "清洗后有多少笔有效订单？" | 清洗明细层 | DWD（清洗明细层）|
| "每天每个地区的销售额是多少？" | 汇总层 | DWS（汇总层）|
| "BI 看板显示什么？" | 应用服务层 | ADS（应用服务层）|

```text
源端投递 → ODS（保留原始） → DWD（清洗去重） → DWS（汇总） → ADS（发布）
                  │                │
                  └→ 拒收记录       └→ 明细下钻
```

### 关于分层的重要说明

**ODS/DWD/DWS/ADS 是建模约定，不是 Doris 的四种引擎。**

- ❌ 错误理解：创建 4 张带前缀的表就完成了分层
- ✅ 正确理解：说清数据如何加工、何时更新、失败如何重做

**每一层可以用表或视图实现，也不要求每层都复制全部字段。**

---

## 9.2 为什么 JOIN 后金额会翻倍？

### 先理解事实表和维表

**事实表**记录可以被分析的业务过程：
- 下单金额、商品数量、支付金额

**维表**记录解释这些事实的属性：
- 客户名称、客户地域、商品类别

**粒度**是"一行代表什么"的精确定义：

| 对象 | 粒度 | 不能直接等同 |
| --- | --- | --- |
| 当前订单 | 一笔订单的当前状态 | 多条状态事件 |
| 订单商品明细 | 一笔订单的一条商品明细 | 整单金额 |
| 支付流水 | 一次支付事件 | 订单当前累计已付金额 |
| 当前客户维度 | 一个客户的当前属性 | 客户历次属性版本 |

### 真实场景：为什么客户维表会有重复记录？

在开始看 SQL 例子之前，先理解**为什么客户维表会出现两条记录**。

#### **场景 1：CDC 同步时没有正确去重**

假设你用 Flink CDC 从 MySQL 同步客户表到 Doris：

**MySQL 中的客户表（source）：**
```sql
-- 客户表，主键是 customer_id
CREATE TABLE customers (
    customer_id INT PRIMARY KEY,
    customer_name VARCHAR(100),
    region VARCHAR(50)
);

-- 只有一条客户 1 的记录
INSERT INTO customers VALUES (1, '张三', 'EAST');
```

**Doris 中的客户维表（target）：**
```sql
-- 如果用 DUPLICATE KEY（错误的选择）
CREATE TABLE customers_dim (
    customer_id INT,
    customer_name VARCHAR(100),
    region VARCHAR(50)
)
DUPLICATE KEY(customer_id)  -- ❌ 不会去重！
...;
```

**CDC 同步过程中发生了什么：**

1. **初始快照：** 插入客户 1 的记录
   ```
   customer_id=1, name='张三', region='EAST'
   ```

2. **客户 1 更新了地域：** MySQL 执行 `UPDATE customers SET region='WEST' WHERE customer_id=1`

3. **CDC 抓到 UPDATE 事件：** 
   - 如果 Doris 目标表是 **DUPLICATE KEY**，CDC 会再插入一条新记录
   - 结果：客户 1 有两条记录（EAST 和 WEST）

**正确的做法：**
```sql
-- 应该用 UNIQUE KEY
CREATE TABLE customers_dim (
    customer_id INT,
    customer_name VARCHAR(100),
    region VARCHAR(50)
)
UNIQUE KEY(customer_id)  -- ✅ 自动覆盖更新
...;
```

**关于表模型的选择：**

这里必须用 UNIQUE KEY，因为客户维度需要"当前状态覆盖更新"。

| 表模型 | 适合的场景 | 关键点 |
| --- | --- | --- |
| Unique Key | 当前客户属性，覆盖更新 | 按客户 ID 更新 |
| Duplicate Key | 保留原始投递，允许重复 | 每次 INSERT 都追加，不去重 |
| Aggregate Key | 按维度累计可加指标 | 相同键的值会累加 |

**星型模型 vs 宽表：**

| 建模方式 | 优点 | 代价 |
| --- | --- | --- |
| 星型（事实 + 维度）| 属性集中管理，复用维度 | 需要 JOIN，管理粒度 |
| 宽表（属性写进事实）| 查询少做 JOIN | 属性冗余，更新成本高 |

---

#### **场景 2：手动 INSERT 时没有检查唯一性**

假设你手动导入客户数据：

```sql
-- 第一次导入
INSERT INTO customers_dim VALUES (1, '张三', 'EAST');

-- 后来发现地域错了，又导入一次
INSERT INTO customers_dim VALUES (1, '张三', 'WEST');  -- ❌ 如果是 DUPLICATE KEY，会追加！
```

**如果表是 DUPLICATE KEY：**
- 结果：客户 1 有两条记录

**如果表是 UNIQUE KEY：**
- 结果：第二次 INSERT 覆盖第一次，客户 1 只有一条记录（WEST）

---

#### **场景 3：维表保留了历史版本（但没有加有效期）**

假设你想保留客户地域的历史变更：

**错误的做法（没有有效期）：**
```sql
-- 只是简单追加，没有 valid_from / valid_to
INSERT INTO customers_dim VALUES (1, '张三', 'EAST');   -- 2024-01-01 更新
INSERT INTO customers_dim VALUES (1, '张三', 'WEST');   -- 2024-02-01 更新
```

**问题：**
- 查询时不知道哪条是"当前"记录
- JOIN 时会匹配两条，导致金额翻倍

**正确的做法（加有效期）：**
```sql
CREATE TABLE customers_dim_history (
    customer_id INT,
    customer_name VARCHAR(100),
    region VARCHAR(50),
    valid_from DATE,
    valid_to DATE  -- NULL 表示当前有效
)
DUPLICATE KEY(customer_id, valid_from)
...;

-- 正确的历史记录
INSERT INTO customers_dim_history VALUES 
    (1, '张三', 'EAST', '2024-01-01', '2024-01-31'),  -- 历史记录
    (1, '张三', 'WEST', '2024-02-01', NULL);          -- 当前记录

-- JOIN 时只匹配当前记录
SELECT ...
FROM orders_fact f
JOIN customers_dim_history d 
  ON f.customer_id = d.customer_id 
  AND d.valid_to IS NULL;  -- 只要当前有效的记录
```

---

### 用 SQL 例子看金额翻倍

现在我们模拟"维表有重复记录"的场景：

```sql
WITH facts AS (
    SELECT 1 AS order_id, 1 AS customer_id, 100 AS amount
    UNION ALL SELECT 2, 2, 200
), dim AS (
    -- 客户 1 有两条记录（可能是 CDC 同步错误，或手动插入重复）
    SELECT 1 AS customer_id, 'EAST' AS region
    UNION ALL SELECT 1, 'WEST'  
    UNION ALL SELECT 2, 'EAST'
)
SELECT COUNT(*) AS joined_rows, SUM(f.amount) AS joined_amount
FROM facts f
JOIN dim d ON f.customer_id = d.customer_id;
```

**JOIN 的匹配过程：**

| order_id | customer_id (facts) | amount | customer_id (dim) | region | 匹配结果 |
| --- | --- | ---: | --- | --- | --- |
| 1 | 1 | 100 | 1 | EAST | ✅ 匹配 |
| 1 | 1 | 100 | 1 | WEST | ✅ 匹配（同一笔订单匹配了两次！）|
| 2 | 2 | 200 | 2 | EAST | ✅ 匹配 |

**结果：**

| 检查点 | 行数 | 金额 |
| --- | ---: | ---: |
| 原始事实 | 2 | 300 |
| JOIN 后 | 3 | 400 |

**发生了什么？**

订单 1（100 元）匹配了维表中的两行（EAST 和 WEST），所以：
- 订单 1 变成 2 行，金额被计算了 2 次
- 总金额从 300 变成 400

---

### 为什么常见的检查方法发现不了？

#### **方法 1：`COUNT(DISTINCT order_id)`**

```sql
SELECT COUNT(DISTINCT order_id) FROM (JOIN 后的结果);
-- 返回: 2  （看起来没问题）
```

**为什么发现不了？**
- 订单 ID 去重后仍然是 2 个
- 但金额已经放大了

---

#### **方法 2：`SUM(DISTINCT amount)`**

```sql
SELECT SUM(DISTINCT amount) FROM (JOIN 后的结果);
-- 返回: 300  （100 + 200）
```

**为什么不可靠？**
- 如果两笔不同订单恰好都是 100 元
- `SUM(DISTINCT 100)` 只会计算一次，错误地丢掉一笔订单

---

### 正确的检查方法

**同时检查三个指标：**

```sql
-- 检查 JOIN 前后的行数、订单数、金额
SELECT 'before_join' AS stage,
       COUNT(*) AS row_count,
       COUNT(DISTINCT order_id) AS order_count,
       SUM(amount) AS total_amount
FROM facts
UNION ALL
SELECT 'after_join',
       COUNT(*),
       COUNT(DISTINCT f.order_id),
       SUM(f.amount)
FROM facts f
JOIN dim d ON f.customer_id = d.customer_id;
```

| stage | row_count | order_count | total_amount |
| --- | ---: | ---: | ---: |
| before_join | 2 | 2 | 300 |
| after_join | 3 ✗ | 2 | 400 ✗ |

**发现问题：**
- `row_count` 从 2 变成 3（一对一 JOIN 不应该改变行数）
- `total_amount` 从 300 变成 400（金额放大了）

**正确做法：**
1. 确保维表的客户维度唯一（一个客户只有一条"当前"记录）
2. JOIN 后检查行数和金额是否符合预期

### 不同 JOIN 保留哪些行？

假设左侧有订单，右侧有客户。

| JOIN 类型 | 结果含义 | 订单场景 |
| --- | --- | --- |
| INNER JOIN | 只保留匹配成功的组合 | 只分析能关联到客户的订单 |
| LEFT JOIN | 保留所有左侧行，未匹配填 NULL | 保留订单，显示哪些客户缺失 |
| FULL OUTER JOIN | 两侧未匹配行也保留 | 对账时同时发现多余和缺失 |
| LEFT SEMI JOIN | 左侧存在匹配则保留一次 | 找到属于某客户集合的订单 |
| LEFT ANTI JOIN | 保留没有匹配的左侧行 | 找出没有客户维度的订单 |

### 如何检查缺失维度？

完成 Lab 9 后运行：

```sql
SELECT f.customer_id, COUNT(*) AS orders_without_dimension
FROM orders_fact_l2 f
LEFT JOIN customers_dim_l2 d ON f.customer_id = d.customer_id
WHERE d.customer_id IS NULL
GROUP BY f.customer_id;
```

**如果有结果：** 说明有订单找不到对应的客户维度  
**如果返回 0 行：** 说明所有订单都能匹配到客户

**重要：** 不能用 INNER JOIN 代替 LEFT JOIN，因为 INNER JOIN 会悄悄丢掉缺失维度的订单。

---

## 9.3 数据在哪里匹配？

### 逻辑 JOIN vs 物理执行

**逻辑 JOIN** 定义结果语义（INNER/LEFT/...）  
**物理策略** 决定数据如何送到执行节点（Broadcast/Shuffle/...）

| 物理策略 | 如何组织数据 | 适合的场景 |
| --- | --- | --- |
| Broadcast | 将一侧数据发送到所有节点 | 小表 JOIN 大表 |
| Shuffle | 按连接键重新分发数据 | 两侧都比较大 |
| Bucket Shuffle | 利用已有分桶，减少重分发 | 连接键与分布键一致 |
| Colocate | 对齐分桶和副本，本地匹配 | 同组、兼容分桶、满足连接条件 |

**关键点：**
- 两张表都写 `HASH(customer_id)` 不代表已经 Colocate
- 本课一台 BE、一个桶，无法证明多节点优化

### 如何查看 JOIN 执行计划？

完成 Lab 9 后运行：

```sql
EXPLAIN
SELECT f.order_id, d.customer_name
FROM orders_fact_l2 f
JOIN customers_dim_l2 d ON d.customer_id = f.customer_id;
```

**在计划中查找：**
1. JOIN 类型（INNER/LEFT/...）
2. 分布方式（Broadcast/Shuffle/...）
3. Exchange 节点（数据传输）
4. 扫描对象（实际读哪张表）

**实际执行的证据在 Query Profile 中**，EXPLAIN 只是计划。

---

## 9.4 如何验收？

### 同时检查键、行数、金额

完成 Lab 9 后运行：

```sql
SELECT 'before_join' AS stage,
       COUNT(*) AS row_count,
       COUNT(DISTINCT order_id) AS order_count,
       SUM(order_amount) AS amount
FROM orders_fact_l2
UNION ALL
SELECT 'after_left_join',
       COUNT(*),
       COUNT(DISTINCT f.order_id),
       SUM(f.order_amount)
FROM orders_fact_l2 f
LEFT JOIN customers_dim_l2 d ON f.customer_id = d.customer_id
ORDER BY stage;
```

**预期结果（本课样本）：**

| stage | row_count | order_count | amount |
| --- | ---: | ---: | ---: |
| before_join | 10 | 10 | 1400.00 |
| after_left_join | 10 | 10 | 1400.00 |

**如果行数或金额变了：**
- 检查维表是否有重复的客户 ID
- 检查是否用错了 INNER JOIN（丢失了缺维度的订单）

### 验收清单

| 检查项 | 如何验证 | 预期结果 |
| --- | --- | --- |
| 键唯一性 | `COUNT(*)` vs `COUNT(DISTINCT customer_id)` | 维表中客户 ID 唯一 |
| 缺失维度 | LEFT JOIN + WHERE d.customer_id IS NULL | 返回 0 行 |
| 行数不变 | JOIN 前后的 `COUNT(*)` | 一对一 JOIN 不改变行数 |
| 金额不变 | JOIN 前后的 `SUM(order_amount)` | 金额不放大 |

## 动手实验：订单事实与客户维度

打开 [Lab 9](lab9_modeling_and_joins.ipynb)，在已完成 Lab 5 和 Lab 6 的同一专用库中依次：

1. 创建事实表 `orders_fact_l2`
2. 创建维表 `customers_dim_l2`
3. JOIN 订单和客户
4. 检查缺失维度
5. 验证行数和金额
6. 查看执行计划

### 数据说明

- 事实来源：Lab 5 导入的 10 条模拟订单
- 客户来源：Lab 6 的 WWI 客户（选取 customer_id 1–20）
- 地域字段：当前填入 `known`（示例占位，不是真实地域）

### 验收标准

| 检查 | 预期 |
| --- | --- |
| 事实表行数 | 10 |
| 维表行数 | 20 |
| JOIN 后行数 | 10（一对一匹配）|
| JOIN 后金额 | 1400.00（不放大）|
| 缺失维度 | 0 行（所有订单都能匹配）|

### 独立练习

将 9.2 第一个反例中的客户 2 从维表中移除：

**问题：** 分别预测 INNER JOIN 和 LEFT JOIN 的行数与金额

<details>
<summary>参考解释</summary>

**INNER JOIN：**
- 保留订单 1 的两次匹配（客户 1 有两条记录）
- 订单 2 消失（客户 2 不在维表中）
- 结果：2 行，金额 200

**LEFT JOIN：**
- 保留订单 1 的两次匹配
- 保留订单 2（右侧填 NULL）
- 结果：3 行，金额 400

**教训：** 缺失与重复可能同时存在，甚至相互抵消部分误差。应该分别检查：
- 右侧键唯一性
- 未匹配事实
- JOIN 后行数和金额

</details>

---

## 单元总结

- **分层**划分接入、明细、汇总和服务职责；对象前缀不能替代真实加工流程
- **粒度**先于字段清单；一对多 JOIN 会放大事实行
- **LEFT JOIN** 让缺失维度可见；INNER JOIN 会悄悄丢掉订单
- **验收**要同时检查键唯一性、行数、订单去重数、金额
- **物理执行**与逻辑 JOIN 不同；EXPLAIN 和 Profile 是不同层次的证据

---

## 知识测验

打开 [Quiz 9](quiz9_modeling_and_joins.ipynb)，检查：
1. 粒度定义
2. 表模型选择
3. JOIN 基数
4. 缺失维度检查
5. 执行计划阅读

---

## 官方参考资料

- [JOIN 语义](https://doris.apache.org/docs/4.x/query-data/join/)：INNER、OUTER、SEMI 与 ANTI JOIN
- [表模型](https://doris.apache.org/docs/4.x/table-design/data-model/overview/)：Duplicate、Unique 与 Aggregate
- [Colocation Join](https://doris.apache.org/docs/4.x/query-acceleration/colocation-join/)：分桶、同组布局与适用条件
- [Query Profile](https://doris.apache.org/docs/4.x/query-acceleration/query-profile/)：实际运行证据
