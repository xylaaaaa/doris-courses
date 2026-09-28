# 模块 13：存储与生命周期管理

| 课程信息 | 说明 |
| --- | --- |
| 所属课程 | Data Warehousing with Apache Doris · Level 3 |
| 产品范围 | Apache Doris 4.x；示例使用课程单节点沙箱 |
| 前置知识 | Level 1 表模型和导入；Level 2 指标服务；Module 12 的运维证据意识 |
| 建议用时 | 约 65 分钟：阅读 30 分钟、实验 30 分钟、测验 5 分钟 |

[Level 3 目录](../README.md) · [打开 Lab 13](lab13_storage_and_lifecycle.ipynb) · [打开 Quiz 13](quiz13_storage_lifecycle.ipynb)

## 单元目标

数据生命周期不是简单地执行 `DELETE`。在 Doris 中，分区、Bucket、Tablet、Rowset 和 Compaction 处于不同层次，分别影响数据裁剪、并行度、复制、版本管理和物理存储。运维人员应先记录对象和影响范围，再选择分区级维护；维护后核对查询结果和元数据，物理空间回收需要另外观察。

### 学习目标

完成本单元后，你应当能够：

1. 根据保留策略选择时间分区边界；
2. 区分 Partition、Bucket、Tablet、Rowset 和 Segment；
3. 用 `SHOW PARTITIONS`、`SHOW TABLETS` 和 `SHOW CREATE TABLE` 记录物理布局证据；
4. 在不清空整张表的情况下执行分区级生命周期操作；
5. 区分分区 TRUNCATE 的查询可见性、旧文件回收与 Rowset Compaction 的作用；
6. 编写包含前置检查、执行、验证和恢复说明的维护 Runbook。

## 单元安排

| 小节 | 核心问题 | 建议用时 |
| --- | --- | ---: |
| 13.1 生命周期与保留策略 | 为什么要按时间分区？ | 8 分钟 |
| 13.2 从表到 Tablet | 数据如何落到物理布局？ | 8 分钟 |
| 13.3 元数据与版本证据 | 如何知道维护影响了什么？ | 8 分钟 |
| 13.4 TRUNCATE 与 Compaction | 清空分区后空间是否立即释放？ | 6 分钟 |
| Lab 13 | 创建、检查并清理一个隔离分区 | 30 分钟 |
| Quiz 13 | 检查生命周期概念 | 5 分钟 |

## 13.1 从保留策略开始，而不是从 SQL 开始

先回答四个业务问题：

| 问题 | 示例答案 |
| --- | --- |
| 一行代表什么 | 某天的一笔订单事件 |
| 保留多久 | 保留近 13 个月，历史数据归档 |
| 清理边界 | 只清空完整月份分区的数据，保留分区定义 |
| 恢复方式 | 从归档文件或上游批次重新装载该分区 |

如果保留边界是月份，却用逐行 `DELETE` 清理几亿行，系统需要处理大量数据和版本；如果分区边界与业务保留周期一致，就能把清理范围限制在指定分区。本实验使用 `TRUNCATE TABLE ... PARTITION` 清空旧数据，**保留分区定义**，并没有删除分区本身。分区不是备份，清空前仍应确认归档和恢复证据已经存在。

## 13.2 Partition、Bucket 和 Tablet 的关系

Doris 的物理布局可以简化为：

```text
Table → Partition → Tablet → Rowset → Segment
                     ↑
              每个 Bucket 对应 Tablet
```

| 层次 | 作用 | 运维关注点 |
| --- | --- | --- |
| Table | 业务表和 schema 边界 | 对象所有权、权限、模型 |
| Partition | 按范围或列表切分数据 | 分区裁剪、归档、生命周期 |
| Bucket | 将一个分区分片 | 并行度、数据倾斜、调度开销 |
| Tablet | 与分桶对应的数据分片；副本是它在 BE 上的拷贝 | 复制、版本、Compaction、大小 |
| Rowset | 一次写入形成的不可变文件组 | 版本数量、合并压力 |
| Segment | Rowset 内部的数据组织 | 扫描和索引实现细节 |

一行数据先根据分区键找到 Partition，再根据分桶方式找到 Tablet。分区数量过少会扩大扫描和删除范围；Bucket 过多会产生许多小 Tablet 和调度开销；Bucket 过少则可能限制并行度。课程沙箱只有一个 BE、一个副本和很小的数据量，因此实验用于理解证据，不用于推导生产桶数。

官方概念见 [Partitioning and Bucketing](https://doris.apache.org/docs/4.x/key-features/partitioning-and-bucketing/)。

## 13.3 如何读取运维证据

### SHOW PARTITIONS

`SHOW PARTITIONS` 主要回答：有哪些分区、分区状态是什么、行数和副本信息是否符合预期。维护前后都应保存结果，特别是目标分区名称和行数。

```sql
SHOW PARTITIONS FROM ops_orders_l3 ORDER BY PartitionName;
```

### SHOW TABLETS

`SHOW TABLETS` 把检查范围下沉到 Tablet。要注意：每个副本可能对应一行；在计算存储分离模式下，数据大小字段的含义与本地耦合模式不同。检查 Tablet 时应至少记录 Tablet ID、Partition、Replica 状态、版本和数据大小，不要只截图一个总数。

```sql
SHOW TABLETS FROM ops_orders_l3;
```

### SHOW CREATE TABLE

`SHOW CREATE TABLE` 是表级契约证据：它能确认分区边界、Key 模型、分桶方式、副本数和保留相关属性。它不能单独证明历史数据已经归档，也不能证明 Compaction 已完成。

官方语法见 [SHOW PARTITIONS](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/table-and-view/table/SHOW-PARTITIONS)、[SHOW TABLET](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/table-and-view/data-and-status-management/SHOW-TABLET/) 和 [Partitioning and Bucketing](https://doris.apache.org/docs/4.x/key-features/partitioning-and-bucketing/)。

## 13.4 分区 TRUNCATE、空间回收与 Compaction

Doris 的写入通常产生新的不可变 Rowset，后台 Compaction 再将多个 Rowset 合并。但本实验的 `TRUNCATE TABLE ... PARTITION` 是按整分区清空，不是逐行 `DELETE`，也不以 Compaction 完成作为查询不可见的条件。旧文件何时释放不能仅从查询结果判断。因而维护验收至少分成：

1. **逻辑验收**：查询结果不再包含目标分区的数据；
2. **元数据验收**：分区状态和行数反映维护后的结果；
3. **物理观察**：在适合的环境中观察存储占用及回收过程；Compaction 状态用于分析写入产生的 Rowset，不能用来判定本次 TRUNCATE 是否完成；
4. **恢复验收**：确认仍有归档、批次或重载路径。

不要把“`TRUNCATE TABLE ... PARTITION` 执行成功”解释成“磁盘空间已经立即归还”。也不要在课程小样本中用一次执行时间推断生产 Compaction 性能。[TRUNCATE 操作](https://doris.apache.org/docs/4.x/data-operate/delete/truncate-manual/)说明了它与逐行 DELETE 的区别。

Compaction 由 BE 后台处理，主要用于合并写入积累的 Rowset；生产中应结合版本数、Compaction score、写入频率和查询压力观察它。Lab 13 不手动触发 Compaction。参考 [Data Compaction](https://doris.apache.org/docs/4.x/key-features/data-compaction/)。

## 动手实验：隔离表上的分区生命周期

打开 [Lab 13](lab13_storage_and_lifecycle.ipynb)，按顺序完成：

1. 在课程专用库创建带三个按月分区的 `ops_orders_l3`；
2. 写入三个月的少量样本，观察表行和分区；
3. 查看分区、Tablet、建表语句三类证据；
4. 只清理 `p202501`，验证二月和三月数据仍在；
5. 复查维护后的行数和分区元数据；
6. 回答为什么逻辑清理与物理回收需要分开观察。

### 前置条件和安全说明

Lab 13 不依赖 Level 1 的业务表，只需要课程沙箱连接。它只创建和删除 `ops_orders_l3`，不会对 `orders_imported` 或其他共享对象执行 `TRUNCATE`。Notebook 会在维护前后进行行数检查；请不要把示例中的分区名复制到生产表。

### 完成标准

| 检查 | 预期 |
| --- | --- |
| 初始行数 | 3 行，分别位于 2025 年 1、2、3 月分区 |
| 分区证据 | `p202501`、`p202502`、`p202503` 均存在 |
| Tablet 证据 | 能看到分区对应的物理 Tablet 信息 |
| 清理范围 | 只删除 `p202501`，剩余 2 行 |
| 维护后查询 | 只返回 2 月和 3 月记录 |
| 解释边界 | 能区分逻辑可见性、物理空间和恢复方案 |

## 独立练习

假设保留策略从“三个月”改为“最近 13 个月”，且每月数据量差异很大。请写一份简短 Runbook，至少包括：

1. 分区键和边界选择；
2. 维护前要保存的 `SHOW PARTITIONS`、`SHOW TABLETS` 和归档证据；
3. 为什么不能直接 `TRUNCATE TABLE`；
4. 清理后如何验证逻辑结果；
5. 如果误删一个月，如何从归档或上游批次恢复。

<details>
<summary>参考解释</summary>

应按完整月份设置时间分区，并在删除前确认目标分区、归档可读、恢复批次和审批范围。执行分区级操作而不是整表操作；维护后查询目标月份、检查分区行数和保存 Tablet 元数据。恢复时重新装载目标分区或从归档恢复，不能把“删除后空间尚未回收”当成可靠备份。

</details>

## 单元总结

- Partition 是生命周期和裁剪边界，Bucket/Tablet 是分布和物理执行边界；
- `SHOW PARTITIONS`、`SHOW TABLETS`、`SHOW CREATE TABLE` 提供不同层次的证据；
- 分区 TRUNCATE 后的查询可见性与旧文件回收不是同一时刻；Compaction 另用于整理写入积累的 Rowset；
- 任何维护操作都应有范围检查、执行记录、结果验证和恢复路径；
- 单节点小样本适合学习语义，不适合推导生产容量和性能参数。

## 知识测验

[Quiz 13](quiz13_storage_lifecycle.ipynb) 包含 5 道离线题目，重点检查分区、Tablet、生命周期操作和 Compaction 边界。

## 官方参考资料

- [Partitioning and Bucketing](https://doris.apache.org/docs/4.x/key-features/partitioning-and-bucketing/)
- [SHOW PARTITIONS](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/table-and-view/table/SHOW-PARTITIONS)
- [SHOW TABLET](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/table-and-view/data-and-status-management/SHOW-TABLET/)
- [Data Compaction](https://doris.apache.org/docs/4.x/key-features/data-compaction/)
- [TRUNCATE 操作](https://doris.apache.org/docs/4.x/data-operate/delete/truncate-manual/)
