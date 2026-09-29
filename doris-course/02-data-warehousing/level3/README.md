# Level 3：权限、资源与运维

## 从 Level 2 到 Level 3

### 前两个 Level 你学会了什么？

- Level 1：通过 Iceberg Catalog 查询湖表并与内部表关联，把 10 条订单导入 `orders_imported`，检查质量并拒收脏数据，再用 `DELETE` 和重放处理状态变更；
- Level 2：用视图和物化视图统一查询定义，安全地 JOIN 维表，按指标契约加工 `daily_order_metrics_l2`，再通过语义视图 `bi_order_metrics_l2` 交给 BI 和 AI 消费者。

到这里，数据已经可以查询、可以核对，也有了面向消费者的接口。接下来的问题不再是“怎么算对”，而是“交出去以后怎么管”。

### Level 3 要解决什么新问题？

第一类问题来自发布。BI 负责人找到你：“看板下周上线，给我开个账号。”最快的做法有两种：把 root 密码发过去，或者新建一个账号并执行 `GRANT SELECT_PRIV ON *.*.*`。两种做法当天都能出图，问题在之后才出现：

- 共享 root 后，BI 同事也能删表、改权限，审计日志里只能看到 root，分不清是谁执行的；
- 看板只需要一个指标视图，`*.*.*` 却让所有明细表都可读，以后新建的表也会自动可读；
- 半年后看板下线，没人记得当初开了哪些权限，也就不知道该收回什么。

第二类问题来自数据增长。订单表已经积累了两年数据。假设维护月是 2026 年 2 月，策略要求保留**当月及之前 12 个自然月**（2025 年 2 月至 2026 年 2 月），先归档更早的完整月份。同事执行了一条 `DELETE FROM orders WHERE order_date < '2025-02-01'`，语句很快返回，查询里也看不到这些订单了；可磁盘占用几乎没降，删错了怎么恢复也没人说得清。这种按自然月计算的策略不同于“从今天起倒推 13 个月”的逐日滚动窗口。

这两条 SQL 都只有一行，难的是执行前想清楚影响范围、留下什么证据、出错后怎么收回或恢复。

第三类问题来自资源争用。看板上线后，分析师在月度复盘时提交了几条不带日期条件的明细查询，看板刷新从不到 1 秒变成 20 秒。这次没有哪条 SQL 写错：所有查询都落在默认的 `normal` 组，不限并发、没有队列，也没有管理员设定的执行时限和扫描范围。缺的是事先划好的资源边界。

Level 3 教你把“开个账号”“清一下旧数据”和“给看板留出资源”都做成可复核、可撤销的变更，数据清理还要事先写好恢复路径。

## Level 3 学习路径

| Module | 核心问题 | 为什么在这个位置 | 解决什么痛点 |
| --- | --- | --- | --- |
| Module 12 | 如何安全地把数据产品交给消费者？ | Level 2 做好了服务视图，下一步是交付 | 共享 root 或授予 `*.*.*` 后，谁查了什么说不清，该收回什么也说不清 |
| Module 13 | 数据到期后如何清理，删错了能否恢复？ | 数据产品发布后，数据仍在持续增长 | 条件 `DELETE` 后磁盘不降，查询仍要过滤删除条件，删错了不知道如何恢复 |
| Module 14 | 如何让看板不被临时分析拖慢？ | 看板上线后，看板查询和临时分析开始争用同一批资源 | 所有查询挤在 `normal` 组，不限并发、没有队列，几条大扫描就能拖慢看板，失控的查询也没人拦 |

### 完成 Level 3 后你能做什么？

- 发布：写出消费者契约，用专用角色只授予消费者需要的对象权限；
- 证据：区分 `SHOW GRANTS`、`SHOW ROLES`、变更说明与真实审计日志，并说明各自证明不了什么；
- 撤销：按“确认影响、撤销授权、删除角色、复核结果”的顺序收回访问，不改动数据产品本身；
- 运维：按保留策略划分分区，只清理目标分区，写出带证据和恢复路径的维护 Runbook；
- 资源：用 Workload Group 为看板和临时分析划分并发、排队和内存边界，用执行时限和 SQL Block Rule 挡住失控查询，并写出可以撤销的资源 Runbook。

## 模块清单

每个模块都按“课程正文 → Lab → Quiz”完成。正文从业务场景讲到 Doris 机制；Lab 在课程沙箱中执行并验证；Quiz 检查概念和取舍，不需要连接数据库。

| 模块 | 主题 | 材料 |
| --- | --- | --- |
| 12 | 发布、权限与审计 | [课程](module12-publishing-permissions-audit/course.md) · [实验](module12-publishing-permissions-audit/lab12_publishing_permissions_audit.ipynb) · [测验](module12-publishing-permissions-audit/quiz12_publishing_permissions_audit.ipynb) |
| 13 | 存储与生命周期管理 | [课程](module13-storage-lifecycle/course.md) · [实验](module13-storage-lifecycle/lab13_storage_and_lifecycle.ipynb) · [测验](module13-storage-lifecycle/quiz13_storage_lifecycle.ipynb) |
| 14 | 资源隔离与查询保护 | [课程](module14-resource-isolation/course.md) · [实验](module14-resource-isolation/lab14_resource_isolation.ipynb) · [测验](module14-resource-isolation/quiz14_resource_isolation.ipynb) |

## 实验说明

三个实验都连接课程专用的 `dw_course_l1_*` 数据库（连接时自动创建），只创建带 `_l3` 后缀的对象。Lab 12 开始时会删除上次遗留的 `course_bi_reader_l3` 角色，结束时撤销授权并删除该角色；Lab 13 开始时会删除并重建 `ops_orders_l3`；Lab 14 开始时会删除上次遗留的 SQL Block Rule、角色和两个 Workload Group，并重建 `orders_monthly_l3`，结束时回收授权并删除角色和组。三个实验都可以重复执行。

角色、Workload Group 和 SQL Block Rule 都是集群级对象，不属于课程库。Lab 14 的全局 SQL Block Rule 生效期间会影响沙箱里的所有会话，所以它只存在于一个单元格内，无论成功与否都会在这个单元格结束前删除。

### Lab 依赖关系

| Lab | 需要的前置 Lab | 为什么需要 |
| --- | --- | --- |
| Lab 12 | Level 1 Lab 5 | 需要 `orders_imported` 的 10 条订单（总额 1400.00）作为授权对象 |
| Lab 13 | 无 | 只使用实验自己创建的 `ops_orders_l3` |
| Lab 14 | 无 | 只使用实验自己创建的 `orders_monthly_l3`、两个 Workload Group 和课程角色 |

Lab 12 的独立练习会用到 Level 2 Lab 11 的 `bi_order_metrics_l2`，但只要求写出方案，不在 Notebook 中执行。

建议顺序：Level 1 Lab 5 → Lab 12 → Lab 13 → Lab 14。

### 实验范围说明

Notebook 使用 root 连接单节点 Doris 4.1.3 沙箱，验证的是授权、撤销、分区清理，以及资源组排队、两种时限和扫描拦截的核心路径。以下内容只在正文中说明边界，沙箱没有验证：

- 创建真实消费者用户，并以该身份登录验证访问结果，包括使用未授权的 Workload Group 时被拒绝；
- 生产环境的主机范围、密钥管理和审批流程；
- 多 BE 下的 Tablet 分布和副本修复；
- 物理空间回收的实际时间，以及从归档恢复数据；
- CPU 上限（沙箱没有配置 CPU cgroup）、组内存超限后的暂停和取消，以及 Workload Policy 自动取消查询；
- 多 FE 集群中每个 FE 各自排队的效果。

## Module 间的衔接

### Module 12 → Module 13

Module 12 结束时，你已经能为数据产品写出消费者契约，用专用角色只授予需要的对象权限并留下证据，也能在看板下线时按顺序撤销访问，而不改动数据产品本身。

可数据产品发布后，订单仍在每天写入，存储不会自己变小，过期数据迟早要清理。清理和授权有一个关键区别：授权错了，一条 `REVOKE` 就能收回；数据删错了，没有这样一条随时可用的撤销语句。所以清理前要先想清楚影响范围、维护证据和恢复路径。

Module 13 会教你按保留策略设计分区、只清理目标分区，并区分“查询看不到了”和“磁盘空间已经回收”。

### Module 13 → Module 14

Module 13 结束时，你已经能按保留策略划分分区、只清理目标分区，并写出带证据和恢复路径的维护 Runbook。

前两个模块管的是数据：谁能读、保留多久。看板上线后，新的问题来自查询本身：看板查询和临时分析共用同一份内存、CPU 和执行名额，几条大扫描就能把看板拖慢。Module 13 的按月分区在这里还有一个用处：不带日期条件的查询要扫描全部分区，可以按扫描的分区数把它拦在执行之前。

Module 14 会教你用 Workload Group 划分并发、排队和内存边界，用执行时限和 SQL Block Rule 挡住失控查询，并把这些配置写成可以观察、也可以撤销的资源 Runbook。

## Level 3 常见问题

### Lab 12 提示找不到 `orders_imported` 怎么办？

先完成 Level 1 Lab 5，并确认连接的是同一个 `dw_course_l1_*` 数据库。不要为了让实验跑通，把授权改到其他表上。

### 课程用 root 授权，生产环境也可以这样做吗？

不可以。课程用 root 只是为了让实验可重复。生产环境应由经过审批的授权管理员执行，消费者使用独立账号，并配置主机范围和密钥管理；不要把密码写进 Notebook 或课程文件。

### 为什么 `SHOW PARTITIONS` 里的 RowCount 显示 -1 或 0？

RowCount 和 DataSize 来自 BE 的定期汇报。在课程沙箱里，写入后约 2 分钟内会先显示 -1、再显示 0，之后才是实际行数；VisibleVersion 则在写入后立即变化。需要当场核对行数时，直接查询分区：

```sql
SELECT COUNT(*) FROM ops_orders_l3 PARTITION (p202501);
```

### 为什么 TRUNCATE 之后磁盘占用没有立刻下降？

`TRUNCATE TABLE ... PARTITION` 用一个新的空分区替换旧分区，旧分区进入 FE 的回收站，保留期（`catalog_trash_expire_second`，课程沙箱为 1 天）结束后才被清除，BE 上的文件也是异步删除。回收站有期限，不能当作备份。

### Lab 14 输出了 `query waiting queue is full` 或 `query timeout`，是实验失败了吗？

不是。Lab 14 的“3. 同时提交五条查询”和“4. 分别限制等待时间和执行时间”有意让查询被拒绝、排队超时或执行超时，Notebook 会核对这些报错的原文。只有检查单元格显示 Validation failed，才说明结果和预期不一致。

### Lab 14 中途中断后，全局 SQL Block Rule 还在怎么办？

规则的创建和删除在同一个单元格里，查询报错时也会删除。但如果在这个单元格执行中途中断或重启内核，规则可能留在集群里，之后沙箱中扫描超过 2 个分区的查询都会被拒绝。重新运行 Lab 14 的“1. 准备实验表并清理遗留对象”即可，它会先删除规则，再删除角色、组和实验表；如果内核已经重启，先运行开头的连接单元格。

## 完成 Level 3 的检验

### 发布与审计

- [ ] 为数据产品写出对象、粒度、字段语义、新鲜度、访问范围和责任人
- [ ] 通过专用角色只授予消费者需要的对象权限
- [ ] 区分 `SELECT_PRIV` 与 `GRANT_PRIV`、`ADMIN_PRIV` 等管理权限
- [ ] 区分执行者的 `SHOW GRANTS`、角色前后的 `SHOW ROLES`、变更说明和真实审计日志
- [ ] 按“确认影响、撤销授权、删除角色、复核结果”的顺序撤销访问
- [ ] 判断何时需要列权限、Row Policy 或脱敏

### 存储与生命周期

- [ ] 根据保留策略和查询时间语义选择分区边界
- [ ] 说明一行数据如何落到 Partition、Tablet、副本和 Rowset
- [ ] 用 `SHOW PARTITIONS`、`SHOW TABLETS` 和 `SHOW CREATE TABLE` 记录维护前后的证据
- [ ] 区分查询可见性、元数据变化和物理空间回收
- [ ] 为“当月及之前 12 个自然月”写出包含范围、前置检查、变更、证据和恢复路径的 Runbook

### 资源隔离与查询保护

- [ ] 说明一条查询按会话变量、账号属性、`normal` 的顺序选定 Workload Group
- [ ] 根据 `max_concurrency`、`max_queue_size` 和 `queue_timeout` 判断查询会执行、排队还是被拒绝
- [ ] 说明内存上限在每个 BE 上生效，CPU 上限还依赖 CPU cgroup
- [ ] 用 `USAGE_PRIV` 和 `default_workload_group` 让账号落到正确的组，并说明 `bypass_workload_group` 为什么不是隔离边界
- [ ] 区分 `query_timeout`、Workload Policy 和 SQL Block Rule 的生效时机和作用范围
- [ ] 写出包含资源组、路由、保护规则、观测证据和撤销顺序的资源 Runbook

接下来，可以在隔离的多节点环境中重做三个实验：用真实的测试消费者验证“视图可读、明细不可读”和“只能使用被授权的 Workload Group”，在多副本表上观察 Tablet 和副本证据，并在配置了 CPU cgroup 的多 FE 集群上观察 CPU 上限和各 FE 分别排队的效果。
