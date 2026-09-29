# 模块 14：资源隔离与查询保护

| 课程信息 | 说明 |
| --- | --- |
| 所属课程 | Data Warehousing with Apache Doris · Level 3 |
| 产品范围 | Apache Doris 4.x；示例使用课程单节点沙箱 |
| 前置知识 | Module 12 的角色授权和看板发布；Module 13 的按月分区 |
| 建议用时 | 约 65 分钟：阅读 30 分钟、实验 30 分钟、测验 5 分钟 |

[Level 3 目录](../README.md) · [打开 Lab 14](lab14_resource_isolation.ipynb) · [打开 Quiz 14](quiz14_resource_isolation.ipynb)

## 单元目标

Module 12 发布的 BI 看板上线一周，平时刷新一次不到 1 秒。周一上午的月度复盘会上，分析师开始提交不带日期条件的明细查询和几条大聚合，看板刷新随即变成 20 秒，有时直接超时。排查后发现：

- 看板查询和临时分析都落在默认的 `normal` 组，共用同一份内存、CPU 和扫描线程；
- `normal` 组不限并发、没有队列，同时来多少查询就执行多少；
- 查询没有管理员设定的执行时限，也没有人限制一条查询最多扫描多少分区。

Module 12 解决的是“谁能看到哪些数据”，这里的问题是“一条查询能用多少资源”。本单元把看板和临时分析拆进两个 Workload Group，让角色落到正确的组，再用执行时限和 SQL Block Rule 挡住失控查询，最后把这些配置写成一份可以观察、也可以撤销的资源 Runbook。

### 学习目标

完成本单元后，你应当能够：

1. 说明一条查询按什么顺序选定 Workload Group；
2. 根据 `max_concurrency`、`max_queue_size` 和 `queue_timeout` 判断查询会执行、排队还是被拒绝；
3. 说明内存和 CPU 上限作用在哪里，以及 CPU 上限生效的前提；
4. 用 `USAGE_PRIV` 和 `default_workload_group` 让查询落到正确的组，并说明 `bypass_workload_group` 为什么不是隔离边界；
5. 区分 `query_timeout`、Workload Policy 和 SQL Block Rule 的生效时机和作用范围；
6. 编写包含资源组、路由、保护规则、观测证据和撤销顺序的资源 Runbook。

## 单元安排

| 小节 | 核心问题 | 建议用时 |
| --- | --- | ---: |
| 14.1 谁在和看板抢资源？ | 查询争用哪些资源，怎样落到某个组 | 5 分钟 |
| 14.2 Workload Group 怎样划分并发、排队和内存边界？ | 执行、排队、拒绝，以及每个 BE 上的资源上限 | 9 分钟 |
| 14.3 怎样让 BI 角色落到正确的组？ | 授权、默认组和绕过排队 | 6 分钟 |
| 14.4 怎样挡住失控查询？ | 执行时限、Workload Policy 和 SQL Block Rule | 6 分钟 |
| 14.5 如何把资源配置写成 Runbook？ | 资源组、路由、保护、证据和撤销 | 4 分钟 |
| Lab 14 | 为看板和临时分析划分资源组，观察排队和拦截 | 30 分钟 |
| Quiz 14 | 检查资源隔离和查询保护概念 | 5 分钟 |

## 14.1 谁在和看板抢资源？

看板查询和临时分析对资源的需求完全不同：

| 维度 | 看板查询 | 临时分析 |
| --- | --- | --- |
| 频率 | 高，每次刷新都会同时触发多个图表查询 | 低，但一条可能跑很久 |
| 扫描范围 | 小，通常只看最近一两个月 | 不确定，经常忘记加日期条件 |
| 延迟要求 | 1 秒左右 | 几十秒也能接受 |

两类查询挤在同一个组里，BE 的内存、CPU 和扫描线程就是先到先得。几条大扫描占住资源之后，看板的小查询只能跟着变慢。

Workload Group 让 Doris 按组划分资源：每个组有自己的一套上限，组内查询只能在这些上限之内争用。这些属性作用在两个地方：

| 作用位置 | 控制什么 | 主要属性 |
| --- | --- | --- |
| FE | 同时执行多少条、还能排队多少条、最多等多久 | `max_concurrency`、`max_queue_size`、`queue_timeout` |
| 每个 BE | 组内查询能用的内存、CPU 和扫描资源 | `max_memory_percent`、`max_cpu_percent`、`scan_thread_num`、`read_bytes_per_second` |

把看板和临时分析拆进两个组之后，临时分析最多只能用满自己那一份，看板组的执行名额也不会被它占掉。

一条查询落在哪个组，Doris 按下面的顺序决定：

1. 会话变量 `workload_group` 不为空，就用它指定的组；
2. 否则使用账号属性 `default_workload_group`；
3. 两者都没有设置时，使用内置的 `normal` 组。

`normal` 组对所有账号开放，也不能被删除。在没有配置任何资源组的集群里，包括 root 在内的所有查询都落在这里，这正是单元开头看板和临时分析互相拖累的原因。Lab 14 的第一步会在沙箱里确认这一点：root 的会话变量为空，`SHOW PROPERTY` 显示的 `default_workload_group` 是 `normal`。

## 14.2 Workload Group 怎样划分并发、排队和内存边界？

### 执行、排队还是拒绝？

查询进入一个组后，FE 依次判断：

1. 组内正在执行的查询少于 `max_concurrency`：立即执行；
2. 执行名额已满，排队的查询少于 `max_queue_size`：进入队列等待；
3. 队列也满了：立即拒绝，报错 `query waiting queue is full`；
4. 排队超过等待上限仍没轮到：报错 `query queue timeout`。

Lab 14 把临时分析组的 `max_concurrency` 和 `max_queue_size` 都设为 1。同时提交三条慢查询：第一条执行，第二条排队，第三条立即被拒绝。

三个属性的默认值需要特别留意：

| 属性 | 默认值 | 含义 |
| --- | --- | --- |
| `max_concurrency` | 2147483647 | 相当于不限并发 |
| `max_queue_size` | 0 | 没有队列，名额满了就直接拒绝 |
| `queue_timeout` | 0 | 单位毫秒；0 表示不单独限制，最多等到 `query_timeout` |

所以只设置 `max_concurrency`、不设置 `max_queue_size` 的组，名额一满，后面的查询不会排队，而是直接失败。设置了 `queue_timeout` 时，实际等待上限取它和 `query_timeout` 中较小的一个；前者以毫秒计，后者以秒计。

排队还有四个边界：

- 排队发生在 FE 上，而且只针对要扫描数据的查询；`SELECT 1` 或只读 `information_schema` 的查询不排队；
- 命中 SQL Cache 的查询直接返回缓存的结果，也不排队。会话变量 `enable_sql_cache` 为 `true` 时（课程沙箱就是这样），表的数据超过约 30 秒没有变化后，重复执行的同一条 SQL 就可能命中；
- 会话变量 `bypass_workload_group` 为 `true` 的查询跳过排队，14.3 会说明它为什么不是隔离边界；
- 每个 FE 各自维护队列和计数。多 FE 集群里，一个组实际能同时执行的查询数是各 FE 上限之和，规划容量时要按 FE 数量折算。

观察排队有两个入口：`SHOW WORKLOAD GROUPS` 的 `running_query_num` 和 `waiting_query_num` 列，以及 `information_schema.active_queries` 中 `QUERY_STATUS` 为 `WAIT_IN_QUEUE` 的查询；已经拿到名额的查询显示为 `RUNNING`。

### 内存和 CPU 上限作用在哪里？

内存和 CPU 属性作用在每个 BE 上，按 BE 分别计算，而不是整个集群共用一份额度：

| 属性 | 含义 | 默认值 |
| --- | --- | --- |
| `max_memory_percent` | 组内查询在一个 BE 上最多能用的内存，按 BE 进程内存上限 `mem_limit` 的百分比计算 | 100% |
| `min_memory_percent` | 内存紧张时为该组保留的份额；用量不超过这个份额的组不会被回收内存 | 0% |
| `memory_high_watermark` | 组内内存超过上限的这个比例后，新的内存申请开始失败 | 85% |
| `memory_low_watermark` | 因内存不足暂停的查询，通常要等组内内存回落到这个比例以下才恢复 | 75% |
| `max_cpu_percent` | CPU 硬上限，即使 BE 空闲也不能超过；需要 CPU cgroup，见下文 | 100% |
| `min_cpu_percent` | CPU 紧张时为该组保底的份额 | 0% |

同一个计算组里，所有组的 `min_memory_percent` 之和、`min_cpu_percent` 之和都不能超过 100%；`max_*` 是各组自己的上限，加起来可以超过 100%。

组内内存接近上限时，新的内存申请会失败，查询先暂停。Doris 会尝试让可落盘的算子把中间数据写到磁盘，或者等组内内存回落后让查询继续；都不行时取消查询，报错中包含 `memory limit is exceeded while handling workload group memory pressure`。具体走哪条路取决于当时 BE 上的负载，单节点沙箱无法稳定复现，所以 Lab 14 只创建带内存上限的组，不演示超限。

CPU 上限依赖 Linux 的 CPU cgroup。BE 的 `doris_cgroup_cpu_path` 为空时，BE 不会为组创建 cgroup，`max_cpu_percent` 和 `min_cpu_percent` 只是记录在组上，不会限制任何查询的 CPU。课程沙箱没有配置这个路径，Lab 14 里的 CPU 上限只是一条配置。内存上限由 BE 自己统计和限制，不依赖 cgroup。

## 14.3 怎样让 BI 角色落到正确的组？

要让 BI 账号的查询默认进入看板组，需要做两件事。第一件是授权组的 `USAGE_PRIV`。Lab 14 把它授予课程角色，下面的语句由 Lab 14 执行，这里只阅读：

<!-- reading-only-example -->
```sql
GRANT USAGE_PRIV ON WORKLOAD GROUP 'course_dashboard_l3'
TO ROLE 'course_dashboard_reader_l3';
```

第二件是把账号的默认组指向看板组。下面的语句只用于阅读，Lab 14 不会执行，其中的账号名只是示例：

<!-- reading-only-example -->
```sql
SET PROPERTY FOR 'bi_dashboard_user' 'default_workload_group' = 'course_dashboard_l3';
```

只做其中一件都不够：

| 只做了 | 结果 |
| --- | --- |
| 授权，没有设置默认组 | 查询仍然落在 `normal`，继续和临时分析抢资源 |
| 设置默认组，没有授权 | 查询被拒绝：`Access denied; you need (at least one of) the USAGE/ADMIN privilege(s) to use workload group` |

注意权限检查的时机。`SET workload_group = ...` 和设置 `default_workload_group` 时都不检查权限，执行查询时才检查，所以切换到没有权限的组要到下一条查询才报错。普通账号可以修改自己的 `default_workload_group`，但它只能换到自己有 `USAGE_PRIV` 的组，换到别的组，查询同样会被拒绝；`query_timeout`、`sql_block_rules` 等其他账号属性只有管理员能用 `SET PROPERTY FOR` 设置。

`normal` 组是所有没有默认组的账号的去处，它本身也应该设置合理的上限，而不是一直不限。修改 `normal` 会影响所有会话，所以 Lab 14 不修改它。

### 绕过排队为什么不是隔离边界？

会话变量 `bypass_workload_group` 设为 `true` 后，查询跳过 FE 的排队。设置它不需要任何权限，普通账号在自己的会话里就能执行：

<!-- reading-only-example -->
```sql
SET bypass_workload_group = true;
```

它跳过的只是排队这一步：选组、`USAGE_PRIV` 检查和 BE 上的内存上限照常生效，失效的只有 `max_concurrency`、`max_queue_size` 和 `queue_timeout`。也就是说，对普通账号来说，排队是一种人人都可以选择不遵守的约定。真正兜底的是 BE 上的资源上限、管理员设定的执行时限和 SQL Block Rule，这些不会因为一个会话变量而失效。Lab 14 会让一条查询用这种方式越过已经占满的队列。

## 14.4 怎样挡住失控查询？

资源组限制的是一组查询加起来能用多少资源，一条失控的查询还需要自己的边界。Doris 提供三种手段，生效的时机和对象都不同：

| 手段 | 何时生效 | 作用于谁 | 结果 |
| --- | --- | --- | --- |
| `query_timeout` | 执行中，超过时限 | 每条查询 | 取消查询，报错 `query timeout` |
| Workload Policy | 执行中，满足条件时 | 策略绑定的组内查询；不绑定组时是所有查询 | 执行动作，例如 `cancel_query` |
| SQL Block Rule | 执行前 | 全局规则对所有账号生效，其余只对绑定的账号生效 | 直接拒绝，不执行 |

### 执行时限

`query_timeout` 是单条查询最长的执行时间，单位秒，默认 900。它是会话变量，账号可以自己调大；管理员可以为账号设置同名的账号属性，账号属性优先于会话变量，账号自己也改不了。下面的语句只用于阅读，Lab 14 不会执行：

<!-- reading-only-example -->
```sql
SET PROPERTY FOR 'adhoc_analyst' 'query_timeout' = '600';
```

Lab 14 用会话变量把 `query_timeout` 设为 2 秒，观察超时报错。执行时限是止损，不是预防：查询在被取消之前已经执行了一段时间，也消耗了这段时间的资源。

### Workload Policy

Workload Policy 在查询执行过程中检查条件，满足条件时执行动作。下面的策略取消临时分析组里执行超过 60 秒的查询。语句只用于阅读，Lab 14 不会执行：

<!-- reading-only-example -->
```sql
CREATE WORKLOAD POLICY course_adhoc_guard_l3
CONDITIONS (query_time > 60000)
ACTIONS (cancel_query)
PROPERTIES ("workload_group" = "course_adhoc_l3");
```

使用时注意：

- `query_time` 的单位是毫秒，条件也可以是 `be_scan_rows`、`be_scan_bytes` 或 `query_be_memory_bytes`；
- FE 定期把策略下发到 BE，BE 大约每 500 毫秒检查一次运行中的查询，所以新策略生效有延迟，取消也不是精确到毫秒；被取消的查询报错中包含 `cancelled by workload policy` 和策略名；
- 不设置 `workload_group` 的策略作用于所有查询，条件写错会影响整个集群；
- 被策略引用的组不能直接删除，要先删除策略；已有策略可以在 `information_schema.workload_policy` 中查看。

因为下发有延迟、取消时间不确定，Lab 14 不演示 Workload Policy，Notebook 很难稳定验证它的效果。

### SQL Block Rule

SQL Block Rule 在执行前检查查询，命中就直接拒绝，被拒绝的查询不会占用 BE 资源。规则分两类，一条规则只能属于其中一类：

| 类型 | 属性 | 判断依据 |
| --- | --- | --- |
| 文本规则 | `sql`（正则）或 `sqlHash` | 原始 SQL 文本 |
| 扫描规则 | `partition_num`、`tablet_num`、`cardinality` | 执行计划中每个扫描节点的分区数、Tablet 数和估计行数 |

Lab 14 用一条扫描规则限制单次查询最多扫描 2 个分区。下面的语句由 Lab 14 执行，这里只阅读：

<!-- reading-only-example -->
```sql
CREATE SQL_BLOCK_RULE course_scan_guard_l3
PROPERTIES ("partition_num" = "2", "global" = "true", "enable" = "true");
```

`orders_monthly_l3` 有三个按月分区。不带日期条件的查询要扫描全部 3 个分区，会被拒绝，报错为 `sql hits sql block rule: course_scan_guard_l3, reach partition_num : 2`，其中的数字是规则的上限，不是实际扫描的分区数。只查一个月的看板查询经过分区裁剪后只扫描 1 个分区，照常执行。

写规则时注意四点：

- `global` 默认为 `false`，规则只对管理员用账号属性 `sql_block_rules` 绑定的账号生效，账号自己不能解除这项绑定；设为 `true` 后对所有账号生效，包括 root 和管理员自己；
- 文本规则默认区分大小写，而且直接匹配原始 SQL。按 `select * from orders_monthly_l3` 写的规则挡不住 `SELECT * FROM orders_monthly_l3`，也挡不住带库名前缀的写法，所以限制扫描范围时优先用扫描规则；
- 扫描规则看的是实际的执行计划，只在查询真正扫描数据时触发。Duplicate Key 表上不带条件的 `COUNT(*)` 可能直接由 FE 缓存的统计结果回答，不扫描任何分区，也就不会命中规则，所以 Lab 14 用 `SUM(amount)` 演示拦截；
- 同样的原因，规则创建之前已经进入 SQL Cache 的查询，在表的数据变化之前仍会直接返回缓存的结果，不受新规则影响。验证新规则时，要用没有执行过的 SQL，或者先在会话里执行 `SET enable_sql_cache = false`。

三种手段可以组合使用：SQL Block Rule 在入口挡住明显过大的扫描，Workload Policy 取消临时分析组里执行过久的查询，管理员设定的 `query_timeout` 为每条查询兜底。

## 14.5 如何把资源配置写成 Runbook？

资源配置和 Module 12 的看板发布一样，要能审阅、能观察、能撤销。值班同事需要知道每个组为谁服务、出了问题先看哪里、按什么顺序回滚。以 Lab 14 为例：

| 部分 | Lab 14 的写法 |
| --- | --- |
| 资源组 | 看板组 `course_dashboard_l3`：并发 8、队列 20、最多等待 10 秒、内存上限 50%；临时分析组 `course_adhoc_l3`：并发 1、队列 1、最多等待 30 秒、内存上限 30%，CPU 上限 30% 在沙箱中不生效 |
| 路由 | 角色 `course_dashboard_reader_l3` 只有看板组的 `USAGE_PRIV`；真实账号还要由管理员设置 `default_workload_group` |
| 保护规则 | 全局扫描规则 `course_scan_guard_l3` 限制单次查询最多扫描 2 个分区；临时分析的执行时限由管理员用账号属性设定 |
| 观测证据 | `SHOW WORKLOAD GROUPS` 的执行和排队计数；`information_schema.active_queries` 中的 `WAIT_IN_QUEUE`；三类报错的原文 |
| 撤销顺序 | 删除引用这些组的 Workload Policy；把账号的 `default_workload_group` 改回其他组；回收 `USAGE_PRIV`；删除角色和组；删除规则；用 `SHOW WORKLOAD GROUPS`、`SHOW ROLES` 和 `SHOW SQL_BLOCK_RULE` 核实 |

撤销顺序有两个原因。第一，Doris 会阻止删除仍被引用的组：被 Workload Policy 引用的组，删除时报错 `can't be dropped, because it has related policy`；仍是某个账号 `default_workload_group` 的组，删除时报错并提示先修改该账号的属性。第二，删除组不会清理角色上的授权。之后如果重建一个同名的组，旧的 `USAGE_PRIV` 会重新出现在 `SHOW ROLES` 中，所以要先 `REVOKE`，或者删除角色，让授权随角色一起消失。

## 动手实验：为看板和临时分析划分资源

打开 [Lab 14](lab14_resource_isolation.ipynb)，按顺序完成：

1. 确认当前查询落在 `normal` 组；
2. 重建带三个按月分区的实验表 `orders_monthly_l3`；
3. 创建看板组和临时分析组，只把看板组的 `USAGE_PRIV` 授予课程角色；
4. 在多个会话里同时提交慢查询，观察执行、排队、拒绝和绕过排队；
5. 用 `queue_timeout` 和 `query_timeout` 分别限制等待和执行时间；
6. 用 SQL Block Rule 拦截不带日期条件的全表扫描；
7. 回收授权，删除角色和两个组，确认环境已清理；
8. 完成独立练习：为看板上线写一份资源配置清单。

### 前置条件和安全说明

Lab 14 不依赖 Level 1 的业务表，只需要课程沙箱连接。它会在课程专用库中重建 `orders_monthly_l3`，并创建两个 Workload Group、一个课程角色和一条全局 SQL Block Rule。这些对象都是集群级的，不属于课程库，所以 Lab 开始时会清理上次遗留的同名对象，结束时全部删除。

全局规则生效期间会影响沙箱里的所有会话，所以它只存在于一个单元格内，无论成功与否都会在这个单元格结束前删除。如果这个单元格执行中途被中断或内核被重启，规则可能留在集群里，请重新运行 Lab 14 的“1. 准备实验表并清理遗留对象”再继续。

Lab 14 不修改 `normal` 组和任何账号属性，也不创建真实账号，所以不演示权限被拒绝的场景。慢查询用 `sleep()` 模拟，额外的会话由 `dw_course.workload` 用课程连接打开，并在会话中关闭 SQL Cache，让每条查询都真正排队和执行。沙箱只有一个 FE 和一个 BE，也没有配置 CPU cgroup，因此 CPU 上限、内存超限和 Workload Policy 自动取消都只在阅读中说明。

### 完成标准

| 检查 | 预期 |
| --- | --- |
| 初始路由 | root 的会话变量 `workload_group` 为空，`default_workload_group` 为 `normal` |
| 资源组 | 两个组的并发、队列、等待时间和内存上限与设计一致 |
| 授权范围 | 课程角色只有看板组的 `USAGE_PRIV` |
| 排队与拒绝 | A 执行，B 排队后执行，C 立即被拒绝，D 和 E 不等待就执行 |
| 两种时限 | 排队约 1 秒后报 `query queue timeout`，执行约 2 秒后报 `query timeout` |
| 扫描拦截 | 全表 `SUM` 命中 `course_scan_guard_l3`，只查一个月的查询照常执行，单元格结束后规则已删除 |
| 清理 | 课程的组、角色、规则和组权限都已删除，`normal` 未被修改 |

## 独立练习

看板要正式上线：BI 团队有 5 个账号，高峰期大约 20 个看板查询同时刷新；分析团队有 3 个账号，查询不定时、范围不确定。集群有 3 个 FE。请写一份资源配置清单，至少包括：

1. 看板组和临时分析组的并发、队列和等待时间，以及理由；
2. 两类账号怎样落到各自的组，需要哪些授权和账号属性；
3. 分析师的查询在队列满、排队超时和执行超时时分别看到什么报错；
4. 用什么拦住不带日期条件的全表扫描，它对谁生效；
5. 撤销整套配置的顺序和核实方法。

<details>
<summary>参考解释</summary>

队列按 FE 分别计算，看板组的并发要按 3 个 FE 折算。比如 `max_concurrency` 设为 8，连接在 FE 之间分布均匀时，全集群大约有 24 个名额，能覆盖高峰期的 20 个查询；连接集中在一个 FE 时，这个 FE 上最多只能同时执行 8 个，所以还要确认连接能被均衡。`max_queue_size` 留出刷新突发的余量，`queue_timeout` 设为几秒，让高峰期的查询短暂排队而不是立即失败。临时分析组的并发和队列都有意设得很小，宁可让过多的大查询看到“队列已满”，也不要让它们在 BE 上堆积；`max_memory_percent` 限制它在每个 BE 上的内存，CPU 上限要先确认 BE 配置了 cgroup 才能依赖。

BI 账号通过角色获得看板组的 `USAGE_PRIV`，再由管理员设置 `default_workload_group` 指向看板组。分析师账号只获得临时分析组的 `USAGE_PRIV`，默认组指向临时分析组；他们在会话里切到看板组时，查询会因为缺少 `USAGE_PRIV` 被拒绝。

队列满时报 `query waiting queue is full`，排队超时报 `query queue timeout`，执行超时报 `query timeout`。分析师可以自己调大会话级的 `query_timeout`，所以执行时限要由管理员用账号属性设定；`bypass_workload_group` 能让他们跳过排队，但跳不过执行时限和扫描规则。

用限制 `partition_num` 的 SQL Block Rule，通过账号属性 `sql_block_rules` 只绑定到分析师账号。设为 `global` 会同时影响看板和管理员的查询，要先确认所有看板查询都带日期条件。

撤销时，先删除引用这两个组的 Workload Policy，把账号的 `default_workload_group` 改回 `normal`，再回收 `USAGE_PRIV`，删除角色、组和不再需要的规则，最后用 `SHOW WORKLOAD GROUPS`、`SHOW ROLES` 和 `SHOW SQL_BLOCK_RULE` 核实。

</details>

## 单元总结

- 查询按会话变量 `workload_group`、账号属性 `default_workload_group`、`normal` 的顺序选组，没有配置时所有查询都落在 `normal`；
- `max_concurrency`、`max_queue_size` 和 `queue_timeout` 决定查询执行、排队还是被拒绝；`max_queue_size` 默认为 0，名额满了就直接拒绝；
- 排队在每个 FE 上分别计算，内存和 CPU 上限在每个 BE 上生效，CPU 上限还依赖 BE 配置 cgroup；
- 落到正确的组需要 `USAGE_PRIV` 和 `default_workload_group` 同时配置；`bypass_workload_group` 人人可设，只跳过排队，不是隔离边界；
- SQL Block Rule 在执行前拒绝，Workload Policy 和 `query_timeout` 在执行中取消；执行时限和扫描规则要由管理员设定，账号自己改不了；
- 资源 Runbook 写明资源组、路由、保护规则、观测证据和撤销顺序，删除组之前先回收授权，避免同名组重建后旧授权重新生效。

## 知识测验

[Quiz 14](quiz14_resource_isolation.ipynb) 包含 5 道离线题目，检查选组顺序、执行排队与拒绝、BE 上的资源上限、路由与绕过排队，以及三种查询保护手段。

## 官方参考资料

- [Workload Group](https://doris.apache.org/docs/4.x/admin-manual/workload-management/workload-group/)
- [Concurrency Control and Queuing](https://doris.apache.org/docs/4.x/admin-manual/workload-management/concurrency-control-and-queuing/)
- [Query Circuit Breaking: SQL Block Rule and Workload Policy](https://doris.apache.org/docs/4.x/admin-manual/workload-management/sql-blocking/)
- [CREATE SQL_BLOCK_RULE](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-governance/CREATE-SQL_BLOCK_RULE/)
- [CREATE WORKLOAD POLICY](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/cluster-management/compute-management/CREATE-WORKLOAD-POLICY/)
- [SET PROPERTY](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/account-management/SET-PROPERTY/)
- [active_queries](https://doris.apache.org/docs/4.x/admin-manual/system-tables/information_schema/active_queries/)
- [SQL Cache](https://doris.apache.org/docs/4.x/query-acceleration/sql-cache-manual/)
