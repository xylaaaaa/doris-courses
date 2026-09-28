# Level 2：数据仓库建模与服务

## 从 Level 1 到 Level 2

### Level 1 你学会了什么？

- ✅ 导入 10 条订单到 `orders_imported`
- ✅ 检查数据质量，拒收脏数据
- ✅ 用 `DELETE` 和重放处理状态变更
- ✅ 用 TVF 查询 Iceberg 外部表

### Level 2 要解决什么新问题？

Level 1 的 10 条订单变成了 100 万条，三个团队都要查询：

**运营团队：** "给我每天的订单数和金额"  
**财务团队：** "我也要，但我的过滤条件不一样"  
**BI 看板：** "我每 5 分钟刷新一次，扫描 100 万行太慢了"

**更复杂的需求来了：**
- "按客户地域分析销售额" → 需要 JOIN 客户维表
- "计算客单价" → 需要定义指标口径
- "发布给 BI 看板" → 需要稳定的消费者接口

**Level 2 教你如何设计数据服务，让 BI 和 AI 消费者能安全、稳定地使用你的数据。**

---

## Level 2 学习路径

四个 Module 按递进的问题组织：

| Module | 核心问题 | 为什么在这个位置 | 解决什么痛点 |
| --- | --- | --- | --- |
| **Module 8** | 如何统一查询定义？ | 先学会用视图封装逻辑 | 三个团队的 SQL 过滤条件不同，报表数字对不上 |
| **Module 9** | 如何关联多张表？ | 有了视图后，需要 JOIN 维度 | 按地域分析，但 100 元订单 JOIN 后变成 200 元 |
| **Module 10** | 如何定义指标？ | JOIN 后的数据需要聚合成指标 | 三个团队计算的"客单价"结果不同 |
| **Module 11** | 如何发布给消费者？ | 指标做好后，发布给 BI/AI | BI 做了 100 张报表，后来发现字段含义理解错了 |

### 完成 Level 2 后你能做什么？

**设计能力：**
- ✅ 设计事实表和维表，说明粒度
- ✅ 选择合适的表模型（Duplicate/Unique/Aggregate）
- ✅ 设计星型模型或宽表

**实现能力：**
- ✅ 创建普通视图统一查询定义
- ✅ 创建物化视图加速查询，并验证透明改写
- ✅ JOIN 两张表，避免金额翻倍
- ✅ 创建聚合服务表并用独立明细查询核对

**发布能力：**
- ✅ 定义指标契约（分子、分母、粒度、过滤条件）
- ✅ 创建语义视图发布给 BI
- ✅ 准备特征投影交给 AI
- ✅ 检查新鲜度、空值、行数、金额

---

## 模块清单

每个模块都按"课程正文 → Lab → Quiz"完成。正文先解释业务问题、数据粒度和 Doris 机制，再给出与 Lab 对应的 SQL 阅读示例；Lab 验证可执行路径，Quiz 检查概念和取舍。

| 模块 | 主题 | 材料 |
| --- | --- | --- |
| 8 | 视图与物化视图 | [课程](module08-views-materialized-views/course.md) · [实验](module08-views-materialized-views/lab8_views_and_materialized_views.ipynb) · [测验](module08-views-materialized-views/quiz8_views_and_materialized_views.ipynb) |
| 9 | 数仓建模与 JOIN | [课程](module09-modeling-and-joins/course.md) · [实验](module09-modeling-and-joins/lab9_modeling_and_joins.ipynb) · [测验](module09-modeling-and-joins/quiz9_modeling_and_joins.ipynb) |
| 10 | 指标加工与服务交付 | [课程](module10-metric-processing/course.md) · [实验](module10-metric-processing/lab10_metric_processing.ipynb) · [测验](module10-metric-processing/quiz10_metric_processing.ipynb) |
| 11 | BI 与 AI 应用 | [课程](module11-bi-and-ai/course.md) · [实验](module11-bi-and-ai/lab11_bi_and_ai_delivery.ipynb) · [测验](module11-bi-and-ai/quiz11_bi_and_ai.ipynb) |

---

## 实验说明

实验只创建带 `_l2` 后缀的对象，并将查询结果以表格展示。实验使用 Level 1 已准备的专用 `dw_course_l1_*` 数据库。

### Lab 依赖关系

| Lab | 需要的前置 Lab | 为什么需要 |
| --- | --- | --- |
| Lab 8 | Lab 5 | 需要 `orders_imported` 的 10 条订单 |
| Lab 9 | Lab 5 + Lab 6 | 需要 `orders_imported` 和 `customers` |
| Lab 10 | Lab 5 | 需要 `orders_imported` |
| Lab 11 | Lab 10 | 需要 Lab 10 创建的 `daily_order_metrics_l2` |

**建议顺序：** Lab 5 → Lab 6 → Lab 8 → Lab 9 → Lab 10 → Lab 11

每个 Lab 会在写入前检查自己的前置数据并给出下一步提示。

### 实验范围说明

当前 Notebook 验证单节点课程环境中的核心路径。以下内容在正文中说明使用边界，不冒充已由课程沙箱完成的外部集成实验：
- Superset 连接和图表配置
- MCP Server 安装和工具调用
- 多节点 JOIN 策略对比
- 大规模性能测试

---

## Module 间的衔接

### Module 8 → Module 9

**Module 8 结束时你学会了：**
- 用普通视图统一查询定义
- 用物化视图提前计算并验证透明改写

**为什么接下来要学 JOIN？**

BI 团队说："我想看每个地区的销售额，你的视图里没有地区字段"。

地区信息在 `customers` 表，订单信息在 `orders` 表，需要 JOIN。

但是：一个不小心，100 元的订单变成了 200 元。

**Module 9 会教你如何安全地 JOIN 两张表。**

---

### Module 9 → Module 10

**Module 9 结束时你学会了：**
- 设计事实表和维表
- JOIN 两张表并检查行数、金额

**为什么接下来要学指标？**

三个团队都在计算"客单价"：
- 运营团队：140 元
- 财务团队：140 元
- BI 看板：55 元

问题：哪个是对的？

答案取决于你如何定义"客单价"（整体口径 vs 简单平均）。

**Module 10 会教你如何定义清晰的指标契约。**

---

### Module 10 → Module 11

**Module 10 结束时你学会了：**
- 定义指标契约（分子、分母、粒度、过滤条件）
- 创建聚合服务表并独立核对

**为什么接下来要学发布？**

你给 BI 团队开通了 `orders` 表的查询权限，一周后：

**BI 团队：** "为什么我们的销售额比财务的少 10%？"  
**你：** "哦，`order_amount` 字段是税前金额，不是实收款"  
**BI 团队：** "那我们之前做的 100 张报表全错了？"

**问题：** 权限授对了，但契约没说清。

**Module 11 会教你如何发布稳定的消费者接口。**

---

## Level 2 常见问题

### Q1: 为什么 Lab 9 提示找不到 `orders_imported`？
**A:** 你需要先完成 Lab 5。或者检查是否在正确的数据库中（`dw_course_l1_*`）。

### Q2: 物化视图创建成功，但 EXPLAIN 显示还在扫描基表？
**A:** 检查以下四点：
1. 刷新是否完成？（`mv_infos` 查看状态）
2. 查询条件是否匹配物化视图定义？
3. 查询的列是否都在物化视图中？
4. 改写开关是否打开？

### Q3: JOIN 后金额翻倍了怎么办？
**A:** 检查维表是否有重复的键：
```sql
SELECT customer_id, COUNT(*)
FROM customers_dim_l2
GROUP BY customer_id
HAVING COUNT(*) > 1;
```

### Q4: 服务表的金额变成 2800（应该是 1400）？
**A:** Aggregate Key 表重复 INSERT 会累加。清空重建：
```sql
TRUNCATE TABLE daily_order_metrics_l2;
-- 然后重新执行 INSERT
```

---

## 完成 Level 2 的检验

完成 Level 2 的全部 4 个 Module 后，你应该能够：

### 设计能力
- [ ] 说明事实表和维表的粒度
- [ ] 选择合适的表模型（Duplicate/Unique/Aggregate）
- [ ] 设计星型模型或宽表

### 实现能力
- [ ] 创建普通视图统一查询定义
- [ ] 创建物化视图并验证透明改写
- [ ] JOIN 两张表并检查行数、金额是否符合预期
- [ ] 创建聚合服务表并用独立明细查询核对

### 发布能力
- [ ] 定义指标契约（分子、分母、粒度、过滤条件）
- [ ] 创建语义视图发布给 BI
- [ ] 准备特征投影交给 AI
- [ ] 检查新鲜度、空值、行数、金额

### 疑难排查能力
- [ ] 用 LEFT JOIN + WHERE IS NULL 检查缺失维度
- [ ] 用 EXPLAIN 读取 JOIN 分布策略
- [ ] 用 Query Profile 分析实际执行
- [ ] 用独立明细查询核对服务表结果

**如果上面全部打钩，恭喜你完成了 Level 2！**

接下来：
- **Level 3:** 治理与运维（发布、权限、审计、生命周期管理）
- 或者回到 Level 1，用真实数据集重做一遍
