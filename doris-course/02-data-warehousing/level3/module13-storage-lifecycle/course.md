# 模块 13：存储与生命周期管理

| 课程信息 | 说明 |
| --- | --- |
| 所属课程 | Data Warehousing with Apache Doris · Level 3 |
| 产品范围 | Apache Doris 4.x；示例使用课程单节点沙箱 |
| 前置知识 | Level 1 的表模型和导入；Module 12 的变更证据与撤销思路 |
| 建议用时 | 约 65 分钟：阅读 30 分钟、实验 30 分钟、测验 5 分钟 |

[Level 3 目录](../README.md) · [打开 Lab 13](lab13_storage_and_lifecycle.ipynb) · [打开 Quiz 13](quiz13_storage_lifecycle.ipynb)

## 单元目标

订单明细表 `orders` 已经积累了两年数据，保留策略是只留最近 13 个月。这是一张 Duplicate Key 表。同事执行了 `DELETE FROM orders WHERE order_date < '2025-02-01'`，语句很快返回，查询里也看不到这些订单了。可接下来的几件事让人不安：

- 磁盘占用几乎没变：`DELETE` 只记下了一个删除条件，这些行还留在原来的数据文件里；
- 之后的每次查询都要过滤这个删除条件，直到后台 Compaction 真正清除这些行；
- 有人问“如果条件写错了，怎么恢复”，没人答得上来。

问题不在 `DELETE` 这条语句本身，而在执行前少想了四件事：按什么边界清理、数据在物理上存放在哪里、执行前后留什么证据、出错后怎么恢复。本单元在一张隔离表上把这四件事走一遍，最后写成一份维护 Runbook。

### 学习目标

完成本单元后，你应当能够：

1. 根据保留策略和查询时间语义选择分区边界；
2. 区分 Partition、Bucket、Tablet、副本、Rowset 和 Segment；
3. 用 `SHOW PARTITIONS`、`SHOW TABLETS` 和 `SHOW CREATE TABLE` 记录维护前后的证据；
4. 在不清空整张表的情况下执行分区级生命周期操作；
5. 区分查询可见性、元数据变化、物理空间回收和 Compaction 的作用；
6. 编写包含范围、前置检查、变更、证据和恢复路径的维护 Runbook。

## 单元安排

| 小节 | 核心问题 | 建议用时 |
| --- | --- | ---: |
| 13.1 为什么要按分区清理？ | 保留策略如何决定分区边界 | 8 分钟 |
| 13.2 一行数据落在哪里？ | Partition、Tablet、副本和 Rowset 的关系 | 6 分钟 |
| 13.3 维护前后留什么证据？ | 三类 SHOW 语句各自证明什么 | 6 分钟 |
| 13.4 TRUNCATE 之后数据和空间怎样变化？ | 可见性、元数据和物理空间 | 6 分钟 |
| 13.5 如何把维护写成 Runbook？ | 范围、检查、变更、证据和恢复 | 4 分钟 |
| Lab 13 | 创建、检查并清理一个隔离分区 | 30 分钟 |
| Quiz 13 | 检查生命周期概念 | 5 分钟 |

## 13.1 为什么要按分区清理？

写清理 SQL 之前，先回答四个问题：

| 问题 | 订单明细的示例答案 |
| --- | --- |
| 一行代表什么 | 一笔订单 |
| 保留多久 | 最近 13 个月，更早的数据先归档 |
| 按哪个时间判断过期 | 订单日期 `order_date`，不是导入时间 |
| 删除后怎样恢复 | 从归档文件或上游批次重新装载 |

第三个问题决定分区键。如果按导入时间分区，一笔 1 月的订单在 2 月才补录，就会落进 2 月分区：清理 1 月分区时它会被漏掉，按 `order_date` 查询时也用不上分区裁剪。所以分区边界要同时和保留策略、查询的时间语义保持一致。

分区粒度决定了清理一个月时要动多大的范围。以清理 2025 年 1 月为例：

| 分区方式 | 怎样清理 1 月 | 影响范围 |
| --- | --- | --- |
| 按月分区 | `TRUNCATE` 一个分区 | 只动 1 月分区，其他月份不受影响 |
| 按年分区 | 对 2025 年分区执行条件 `DELETE` | 删除条件记在整个 2025 年分区上，查询 2 月到 12 月的数据时也要过滤它 |
| 不分区 | 对整张表执行条件 `DELETE` | 删除条件作用于整张表，所有查询都要过滤它 |

为什么条件 `DELETE` 会带来这些影响？在 Duplicate Key 表上，`DELETE` 不会立刻改写数据文件，而是写入一个记录删除条件的新版本；之后的查询都要按这个条件过滤，直到 Compaction 合并数据时才把这些行真正清除。删除条件积累得越多，查询的额外开销越大。例如，对一张 Duplicate Key 表执行这类 `DELETE` 后，`SHOW DELETE` 会列出表名、分区名、删除条件（显示为 `order_date LT "2025-02-01"`）和状态 `FINISHED`，对应 Tablet 的 Version 也会加 1。Lab 13 不执行 `DELETE`，语义详见 [DELETE 操作](https://doris.apache.org/docs/4.x/data-operate/delete/delete-manual/)。

按月分区后，清理一个月有两种写法：

| 语句 | 分区定义 | 适合什么情况 |
| --- | --- | --- |
| `TRUNCATE TABLE ... PARTITION (p202501)` | 保留，之后还能向这个月份重新装载数据 | 清空数据但保留月份边界，Lab 13 使用这种方式 |
| `ALTER TABLE ... DROP PARTITION p202501` | 一并删除 | 这个月份不再需要，例如滚动保留时删除最旧的分区 |

生产环境中，这类滚动清理也可以交给动态分区自动完成：设置 `dynamic_partition.start` 后，Doris 会定期删除超出范围的历史分区；不设置时，默认不删除任何历史分区。详见 [Dynamic Partitioning](https://doris.apache.org/docs/4.x/table-design/data-partitioning/dynamic-partitioning)。

无论手工还是自动删除，分区都不是备份：执行之前先确认归档数据可读。

## 13.2 一行数据落在哪里？

我们说的是“清理 1 月的数据”，Doris 在磁盘上管理的却是 Tablet 和 Rowset。跟着 Lab 13 的一行订单走一遍：

| 层次 | 订单 130001（2025-01-15，PAID，100.00）落在哪里 | 运维关注点 |
| --- | --- | --- |
| Table | `ops_orders_l3` | 模型、权限和负责人 |
| Partition | `order_date` 小于 `2025-02-01`，进入 `p202501` | 分区裁剪、保留和清理边界 |
| Bucket / Tablet | 按 `HASH(order_id)` 分桶；`BUCKETS 1` 表示这个分区只有 1 个 Tablet | 并行度、数据倾斜、Tablet 数量 |
| 副本 | `replication_num` 为 1，唯一的 BE 上保存这个 Tablet 的 1 个副本 | 副本数、分布和健康状态 |
| Rowset | 这次 `INSERT` 在 Tablet 上生成一个新版本，也就是一个不可变的 Rowset | 版本数量、Compaction 压力 |
| Segment | Rowset 内按列组织的数据文件 | 扫描和索引的实现细节，日常维护很少直接接触 |

这条路径说明了分区级清理为什么只影响一个月：1 月的订单只存在于 `p202501` 的 Tablet 里，处理这个分区不会碰到 2 月、3 月的 Tablet。

Tablet 和副本的数量也由这几层相乘得到：

| 表 | 分区 | 每分区 Bucket | 副本数 | Tablet（分区 × Bucket） | `SHOW TABLETS` 行数（Tablet × 副本） |
| --- | ---: | ---: | ---: | ---: | ---: |
| Lab 13 的 `ops_orders_l3` | 3 | 1 | 1 | 3 | 3 |
| 假设保留 13 个月的生产订单表 | 13 | 8 | 3 | 104 | 312 |

`SHOW TABLETS` 每行是一个副本，生产表的输出有 312 行，这也是 13.3 要用 `PARTITION` 子句缩小范围的原因。Bucket 数是一种取舍：太少时单个 Tablet 过大，查询并行度受限；太多时产生大量小 Tablet，元数据和调度开销变大。课程沙箱只有一个 BE、一个副本和几行数据，适合观察这些关系，不能用来推导生产桶数。分区和分桶的设计方法见 [Partitioning and Bucketing](https://doris.apache.org/docs/4.x/key-features/partitioning-and-bucketing/)。

## 13.3 维护前后留什么证据？

Module 12 里授权错了，一条 `REVOKE` 就能收回；清理错了，没有对应的撤销语句。所以维护前先记录现状，维护后用同样的命令再查一遍，两份结果对比才能说明到底改了什么。

### SHOW PARTITIONS：有哪些分区，各处于什么版本？

```sql
SHOW PARTITIONS FROM ops_orders_l3 ORDER BY PartitionName;
```

每行是一个分区。维护前后重点记录 `PartitionName` 和 `Range`（分区名和边界）、`PartitionId`（分区编号，`TRUNCATE` 后会变化）、`VisibleVersion`（当前可见版本，写入后立即更新）和 `State`（正常时为 `NORMAL`）。

`RowCount` 和 `DataSize` 不是实时统计，而是来自 BE 的定期汇报。在课程沙箱里，写入后约 2 分钟内会先显示 -1、再显示 0，之后才是实际值。需要当场核对行数时，直接查询目标分区：

```sql
SELECT COUNT(*) FROM ops_orders_l3 PARTITION (p202501);
```

### SHOW TABLETS：数据落在哪些 Tablet 和副本上？

```sql
SHOW TABLETS FROM ops_orders_l3 PARTITION (p202501);
```

每行是一个副本，输出中没有分区列。不加 `PARTITION` 时，所有分区的 Tablet 会混在一起，要靠 `PARTITION` 子句限定范围。重点记录 `TabletId`、`BackendId`（副本所在的 BE）、`Version` 和 `State`。

`RowCount`、`LocalDataSize` 和 `VersionCount` 同样来自 BE 汇报，变更后短时间内可能显示 0 或 -1。存算分离模式下数据大小字段的含义与存算一体不同，读数前先确认部署模式。

### SHOW CREATE TABLE：表是按什么规则设计的？

`SHOW CREATE TABLE ops_orders_l3` 给出表级契约：Key 模型、分区边界、分桶方式、副本数，以及是否配置了动态分区。维护前保存一份，可以确认要清理的分区边界和你以为的一致。

### 每类证据能证明什么？

| 证据 | 能证明 | 不能证明 |
| --- | --- | --- |
| `SHOW PARTITIONS` | 有哪些分区、边界、版本和状态 | 此刻的准确行数，它有汇报延迟 |
| `SHOW TABLETS` | 数据在哪些 Tablet 和副本上、版本是多少 | 旧 Tablet 不再显示时，它的文件是否已从磁盘删除 |
| `SHOW CREATE TABLE` | 表的设计：Key、分区、分桶和副本 | 历史数据是否已归档，Compaction 是否完成 |
| 分区 `COUNT(*)` | 此刻查询能看到多少行 | 物理空间是否已经回收 |

语法见 [SHOW PARTITIONS](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/table-and-view/table/SHOW-PARTITIONS) 和 [SHOW TABLET](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/table-and-view/data-and-status-management/SHOW-TABLET/)。

## 13.4 TRUNCATE 之后数据和空间怎样变化？

下面的语句由 Lab 13 执行，这里只阅读：

<!-- reading-only-example -->
```sql
TRUNCATE TABLE ops_orders_l3 PARTITION (p202501);
```

语句返回后，三个层面的变化并不同步：

| 层面 | 看到什么 | 什么时候 |
| --- | --- | --- |
| 查询结果 | 只剩 2 月和 3 月的 2 行，合计 500.00 | 立即 |
| 分区元数据 | `p202501` 的 `PartitionId` 和 `TabletId` 都换成新值，`VisibleVersion` 变为 1；`p202502`、`p202503` 不变 | 立即 |
| 物理空间 | 旧分区进入 FE 回收站，数据文件仍在磁盘上 | 回收站保留期结束后才删除 |

### 为什么分区编号会变？

`TRUNCATE` 不逐行处理数据，也不像条件 `DELETE` 那样记下删除条件。Doris 新建一个同名的空分区替换旧分区，旧分区连同它的 Tablet 移进 FE 的回收站。所以查询立刻看不到旧数据，也不需要等待 Compaction。旧分区还能在回收站里看到：

```sql
SHOW CATALOG RECYCLE BIN WHERE NAME = 'p202501';
```

重复执行 Lab 13 会留下多条同名记录，每次 `TRUNCATE` 一条。

### 磁盘空间什么时候释放？

回收站的保留期由 FE 配置 `catalog_trash_expire_second` 决定，默认 86400 秒，也就是 1 天。过期后 FE 才彻底删除旧分区，BE 上的数据文件随后异步删除。这是课程沙箱这类存算一体部署的行为；存算分离模式由 Recycler 服务负责回收，时间和方式不同。

回收站不是备份：它有保留期，到期就清除；旧分区的名称和范围已经被新的空分区占用，也不能直接原样换回。`TRUNCATE ... FORCE` 会跳过回收站直接删除，不要为了省空间随手加上。真正的恢复路径是归档文件或上游批次。

### Compaction 和 TRUNCATE 有什么关系？

Compaction 是 BE 的后台任务，把同一个 Tablet 上积累的多个 Rowset 合并成更少、更大的文件，并在合并时真正清除被条件 `DELETE` 标记的行。单元开头那次 `DELETE` 之后磁盘几乎没变，就是在等它。

`TRUNCATE` 整体替换分区，旧 Tablet 直接退出查询，和 Compaction 无关，所以不能用 Compaction 状态判断 `TRUNCATE` 是否完成。生产环境判断 Compaction 压力，要结合 `VersionCount`、Compaction score、写入频率和查询负载；不要用课程小样本的执行时间推断生产性能。Lab 13 不手动触发 Compaction。语义详见 [TRUNCATE 操作](https://doris.apache.org/docs/4.x/data-operate/delete/truncate-manual/)和 [Data Compaction](https://doris.apache.org/docs/4.x/key-features/data-compaction/)。

## 13.5 如何把维护写成 Runbook？

下个月轮到值班同事做清理。只交代一句“把 1 月的数据清掉”远远不够：清哪张表、哪个分区？执行前确认什么？执行后看到什么算成功？出错了怎么办？Runbook 就是把这些问题的答案写在执行之前。以 Lab 13 为例：

| 部分 | Lab 13 的写法 |
| --- | --- |
| 范围 | 只处理 `ops_orders_l3` 的 `p202501`，不动其他分区和其他表 |
| 前置检查 | 分区存在；`SELECT COUNT(*) FROM ops_orders_l3 PARTITION (p202501)` 返回 1（订单 130001，100.00），全表 3 行；记录各分区的 `PartitionId` 和 `VisibleVersion`，以及 `p202501` 的 `TabletId`。生产环境还要确认归档可读、变更已获批准 |
| 变更 | `TRUNCATE TABLE ops_orders_l3 PARTITION (p202501)` |
| 证据 | 全表剩 2 行、合计 500.00；`p202501` 的 `PartitionId` 已变化；`p202502`、`p202503` 的 `PartitionId` 和 `VisibleVersion` 不变 |
| 恢复路径 | 实验中重新写入 `(2025-01-15, 130001, PAID, 100.00)` 这一行；生产环境从归档文件或上游批次重新装载该分区 |

恢复路径要在执行之前验证：确认归档文件能读出来、行数对得上，而不是误删之后才发现归档不可用。

## 动手实验：隔离表上的分区生命周期

打开 [Lab 13](lab13_storage_and_lifecycle.ipynb)，按顺序完成：

1. 在课程专用库中创建带三个按月分区的 `ops_orders_l3`；
2. 写入 1 到 3 月各一行样本，核对业务行；
3. 用 `SHOW PARTITIONS`、`SHOW TABLETS` 和 `SHOW CREATE TABLE` 记录维护前的证据；
4. 只清理 `p202501`，确认 2 月和 3 月的数据仍在；
5. 再次查看分区元数据，对比维护前后的变化；
6. 完成独立练习：为 13 个月保留策略写一份 Runbook。

### 前置条件和安全说明

Lab 13 不依赖 Level 1 的业务表，只需要课程沙箱连接。它开始时会删除并重建 `ops_orders_l3`，只对这张表执行 `TRUNCATE`，不会触碰 `orders_imported` 或其他共享对象。示例中的分区名只适用于这张实验表，不要复制到生产表上执行。

### 完成标准

| 检查 | 预期 |
| --- | --- |
| 初始数据 | 3 行，分别位于 2025 年 1、2、3 月分区 |
| 分区证据 | `p202501`、`p202502`、`p202503` 均存在，并记下了各分区的 `PartitionId` 和 `VisibleVersion` |
| Tablet 证据 | `SHOW TABLETS` 返回 3 行，每个分区一个 Tablet 副本 |
| 清理范围 | 只清空 `p202501`，剩余 2 行，合计 500.00 |
| 元数据变化 | `p202501` 的 `PartitionId` 已变化，其他两个分区不变 |
| 解释边界 | 能区分查询可见性、元数据变化和物理空间回收 |

Notebook 在清理后只重新读取分区元数据。如需对比 `TabletId`，可以自己再执行一次 `SHOW TABLETS FROM ops_orders_l3`。

## 独立练习

把 Lab 13 的做法用到单元开头的订单明细表上：保留最近 13 个月，每月清理一个完整分区，而且各月数据量差异很大。请写一份简短 Runbook，至少包括：

1. 分区键和边界选择；
2. 维护前要保存的 `SHOW PARTITIONS`、`SHOW TABLETS` 和归档证据；
3. 为什么不能直接 `TRUNCATE TABLE`；
4. 清理后如何验证逻辑结果；
5. 如果误删一个月，如何从归档或上游批次恢复。

<details>
<summary>参考解释</summary>

分区键用订单日期 `order_date`，按完整月份划分，与“最近 13 个月”的保留策略对齐。数据量差异影响的是每个分区的 Bucket 数，新增分区时可以单独指定；它不改变按月划分的边界。

维护前保存目标分区的 `SHOW PARTITIONS` 行（`PartitionId`、`Range`、`VisibleVersion`）、`SHOW TABLETS ... PARTITION (...)` 的输出和分区 `COUNT(*)`，并确认这个月份的归档文件可读、行数与分区一致、变更已获批准。

不带 `PARTITION` 的 `TRUNCATE TABLE` 会清空全部 13 个月，远远超出这次维护的范围。

清理后，目标月份的 `COUNT(*)` 为 0，其他月份的行数与维护前一致；`SHOW PARTITIONS` 中只有目标分区的 `PartitionId` 发生变化。

误删后，从归档文件或上游批次重新装载这个分区，再用维护前记录的行数核对。回收站有保留期，旧分区的名称和范围也已被新分区占用，不能当作备份；`FORCE` 会跳过回收站，所以 Runbook 里要写明不使用它。

</details>

## 单元总结

- 分区边界要同时和保留策略、查询的时间语义对齐，按 `order_date` 而不是导入时间划分；
- 一行数据按分区键进入 Partition、按分桶进入 Tablet，再落到副本、Rowset 和 Segment；分区级清理只影响目标分区的 Tablet；
- `SHOW PARTITIONS`、`SHOW TABLETS` 和 `SHOW CREATE TABLE` 回答不同层面的问题，核对行数用分区 `COUNT(*)`；
- 分区级 `TRUNCATE` 立即改变查询结果和分区元数据，旧分区先进入回收站，物理空间在保留期后才回收；
- Compaction 合并 Rowset、清除被 `DELETE` 标记的行，与 `TRUNCATE` 是否完成无关；
- 维护 Runbook 写明范围、前置检查、变更、证据和恢复路径，恢复路径在执行前验证。

## 知识测验

[Quiz 13](quiz13_storage_lifecycle.ipynb) 包含 5 道离线题目，检查分区边界、物理布局证据、分区级清理、Compaction 边界和维护 Runbook。

## 官方参考资料

- [Partitioning and Bucketing](https://doris.apache.org/docs/4.x/key-features/partitioning-and-bucketing/)
- [Dynamic Partitioning](https://doris.apache.org/docs/4.x/table-design/data-partitioning/dynamic-partitioning)
- [SHOW PARTITIONS](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/table-and-view/table/SHOW-PARTITIONS)
- [SHOW TABLET](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/table-and-view/data-and-status-management/SHOW-TABLET/)
- [DELETE 操作](https://doris.apache.org/docs/4.x/data-operate/delete/delete-manual/)
- [TRUNCATE 操作](https://doris.apache.org/docs/4.x/data-operate/delete/truncate-manual/)
- [SHOW CATALOG RECYCLE BIN](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/recycle/SHOW-CATALOG-RECYCLE-BIN)
- [Data Compaction](https://doris.apache.org/docs/4.x/key-features/data-compaction/)
