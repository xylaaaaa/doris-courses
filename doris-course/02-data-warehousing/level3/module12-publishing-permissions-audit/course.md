# 模块 12：发布、权限与审计

| 课程信息 | 说明 |
| --- | --- |
| 所属课程 | Data Warehousing with Apache Doris · Level 3 |
| 产品范围 | Apache Doris 4.x；示例使用课程单节点沙箱 |
| 前置知识 | Level 1 的订单表；Level 2 的消费者视图仅用于独立练习 |
| 建议用时 | 约 65 分钟：阅读 30 分钟、实验 30 分钟、测验 5 分钟 |

[Level 3 目录](../README.md) · [打开 Lab 12](lab12_publishing_permissions_audit.ipynb) · [打开 Quiz 12](quiz12_publishing_permissions_audit.ipynb)

## 单元目标

Level 2 最后发布了语义视图 `bi_order_metrics_l2`。现在 BI 负责人找到你：“看板下周上线，给我开个账号。”

有两种很快的做法，代价都在后面：

- 把 root 密码发过去：BI 同事同时拥有了删表、改权限的能力，审计日志里只有 root，分不清是谁执行的；
- 新建账号并授予 `SELECT_PRIV ON *.*.*`：看板只需要一个视图，这个账号却能读所有明细表，以后新建的表也会自动可读。

几个月后看板下线，没人记得当初开了哪些权限，也就说不清该收回什么。

本单元把“开个账号”拆成四步：先写清交付什么，再用专用角色只授予需要的权限，然后留下可以复核的证据，最后在下线时干净地撤销。

### 学习目标

完成本单元后，你应当能够：

1. 为数据产品写出对象、粒度、字段语义、新鲜度、访问范围和责任人的消费者契约；
2. 区分用户、角色、权限和对象范围，并区分数据访问权限与 `GRANT_PRIV`、`ADMIN_PRIV` 等管理权限；
3. 通过专用角色只授予消费者需要的对象权限，而不是共享 root 或授予全局权限；
4. 用 `SHOW GRANTS`、`SHOW ROLES` 和审计记录保留发布证据，并说明每类证据证明不了什么；
5. 按“确认影响、撤销授权、删除角色、复核结果”的顺序撤销访问，并说明撤销只改变访问、不改变数据产品；
6. 判断什么时候表级权限不够，需要列权限、Row Policy 或脱敏。

## 单元安排

| 小节 | 核心问题 | 建议用时 |
| --- | --- | ---: |
| 12.1 BI 要的到底是什么？ | 交付对象、粒度和字段语义怎样写成契约 | 7 分钟 |
| 12.2 应该给多大的权限？ | 角色、权限类型和对象范围如何取舍 | 8 分钟 |
| 12.3 如何证明授权刚好够用？ | 发布证据各自证明什么 | 6 分钟 |
| 12.4 看板下线后如何收回权限？ | 撤销顺序和影响范围 | 5 分钟 |
| 12.5 表级权限不够细怎么办？ | 列权限、Row Policy 和脱敏 | 4 分钟 |
| Lab 12 | 创建、复核并清理 BI 读者角色 | 30 分钟 |
| Quiz 12 | 检查发布治理概念 | 5 分钟 |

## 12.1 BI 要的到底是什么？

开账号之前，先问清楚看板要读哪个对象。课程里有两个候选：

| 候选对象 | 一行代表什么 | 包含什么 |
| --- | --- | --- |
| `orders_imported` | 一笔订单 | 客户、金额、状态、事件时间、实付和退款、地区等原始字段；10 行合计 1400.00 |
| `bi_order_metrics_l2` | 一天 | `order_date`、`order_count`、`gross_amount`、`average_order_amount` |

如果看板直接接明细表，每张图都要自己写一遍聚合逻辑；上游字段一改，看板就会悄悄算错。Level 2 做语义视图，就是为了给 BI 一个稳定的接口，所以要交付的是视图，不是明细表。

对象选定后，把交付内容写成消费者契约。每一项都对应一种常见的误用：

| 契约项 | `bi_order_metrics_l2` 示例 | 不写清楚会怎样 |
| --- | --- | --- |
| 对象 | `bi_order_metrics_l2` 视图 | BI 连到名字相近的其他表 |
| 粒度 | 一行是一天 | BI 把每天的客单价再平均一次，结果和整体客单价对不上 |
| 字段语义 | `gross_amount` 是模拟的税前订单金额，不是实收款 | 看板把它当成收入展示 |
| 新鲜度 | 每批数据加工完成后更新 | 数据延迟被当成系统故障 |
| 消费者和访问范围 | BI 看板，只读这一个视图 | 授权时顺手给了明细表 |
| 责任人 | 数据产品负责人、BI 负责人和审批人 | 出了问题不知道找谁复核，下线时不知道找谁确认 |
| 验收证据 | 行数、总额、日期覆盖和授权记录 | 发布结果无法复核 |

契约要先于授权：授权语句里的对象和范围，直接来自契约里的“对象”和“消费者和访问范围”两行。

Lab 12 为了减少前置依赖，用 Level 1 的 `orders_imported` 演示授权流程。它是订单明细，不是交付给 BI 的服务视图；本单元的独立练习会把同一套流程用到 `bi_order_metrics_l2` 上。

## 12.2 应该给多大的权限？

### 为什么授给角色而不是用户？

BI 团队有 5 个人要看这个看板。如果逐个给用户授权，就要执行 5 遍同样的授权；有人转岗时容易忘记收回；新人入职时也说不清该照着谁的权限开。

Doris 内置授权分三层：**权限 → 角色 → 用户**。权限说明可以对哪个对象做什么；角色把一组权限命名并复用；用户通过持有角色获得权限。人员进出只需要调整用户持有的角色，所以角色是集中授权、撤销和审计的边界。Lab 12 只创建角色 `course_bi_reader_l3`，不创建真实用户，也不把角色授给任何人。

### 看板需要哪种权限？

| 权限 | 能做什么 | BI 看板需要吗 |
| --- | --- | --- |
| `SELECT_PRIV` | 读取指定范围内的数据 | 需要 |
| `LOAD_PRIV`、`ALTER_PRIV`、`DROP_PRIV` | 写入或删除数据、修改表结构、删除对象 | 不需要，看板只读 |
| `GRANT_PRIV` | 把权限授给别人，管理用户和角色 | 不需要，否则 BI 可以自行扩大授权、绕开审批 |
| `ADMIN_PRIV`、`NODE_PRIV` | 集群管理和节点变更 | 不需要 |

这些权限不能互相替代：`GRANT_PRIV` 本身不包含读取能力，`SELECT_PRIV` 也不能把权限转授给别人。`ADMIN_PRIV` 本身就能通过读取检查，正因为它什么都能做，才更不能为了查一张表而授予。执行授权的人需要 `GRANT_PRIV` 或 `ADMIN_PRIV`，这也是课程用 root 执行授权的原因。

### 同样是 SELECT_PRIV，范围差多少？

即使只授予 `SELECT_PRIV`，`ON` 后面的范围也决定了风险有多大：

| 写法 | 覆盖范围 | 以后新建的对象 |
| --- | --- | --- |
| `*.*.*` | 所有 Catalog 中的所有库表 | 自动可读 |
| `internal.*.*` | 内部 Catalog 中的所有库表 | 自动可读 |
| `internal.<db>.*` | 一个数据库中的所有表和视图 | 该库中新建的表自动可读 |
| `internal.<db>.<table>` | 一张表或一个视图 | 不受影响 |
| `SELECT_PRIV(col1, col2) ON internal.<db>.<table>` | 一张表的指定列 | 以后新增的列不在授权范围内 |

看板只需要一个对象，就只授予这一个对象。下面的语句由 Lab 12 执行，这里只阅读：

<!-- reading-only-example -->
```sql
GRANT SELECT_PRIV
ON internal.dw_course_l1_demo.orders_imported
TO ROLE 'course_bi_reader_l3';
```

Lab 12 会先执行 `CREATE ROLE IF NOT EXISTS course_bi_reader_l3`，并用当前连接的 `lab.database` 生成对象名，所以你的环境里库名可能不同。课程用 root 授权只是为了让实验可以重复执行；生产环境应由经过审批的授权管理员执行，消费者使用独立账号，并配置主机范围和密钥管理。

语法和完整的权限列表见 [Doris 内置授权](https://doris.apache.org/docs/4.x/admin-manual/auth/authorization/internal/)、[GRANT TO](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/account-management/GRANT-TO) 和 [SHOW PRIVILEGES](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/account-management/SHOW-PRIVILEGES/)。

## 12.3 如何证明授权刚好够用？

看板上线三个月后，审计来问：这个角色是谁开的？开了什么？为什么开？开之前它有什么权限？只回答“SQL 执行成功了”，一个问题都答不上。所以 Lab 12 在每个检查点都留下证据：

| 检查点 | Lab 12 中的 SQL | 回答什么问题 |
| --- | --- | --- |
| 身份 | `SELECT CURRENT_USER(), DATABASE()` | 谁在执行，连接在哪个数据库 |
| 对象 | `SELECT COUNT(*), SUM(order_amount) FROM orders_imported` | 授权对象存在，而且是预期的 10 行、合计 1400.00 |
| 授权前 | `SHOW GRANTS` | 执行者当前有哪些权限，是否具备授权能力 |
| 授权后 | `SHOW ROLES` | 新角色拿到了什么权限，范围是否正确 |
| 业务值复核 | 再次查询行数和总额 | 授权没有改动数据产品本身 |

读 `SHOW ROLES` 的结果时，找到 `course_bi_reader_l3` 这一行：`TablePrivs` 列应显示 `internal.<当前库>.orders_imported: Select_priv`。如果这条授权出现在 `GlobalPrivs`、`CatalogPrivs` 或 `DatabasePrivs` 列，说明范围被放大了。`Users` 列为空，因为 Lab 12 没有把角色授给任何用户。

每类证据只能回答一部分问题：

| 证据 | 能证明 | 不能证明 |
| --- | --- | --- |
| `SHOW ROLES` | 角色拥有什么权限、范围多大 | 真实消费者能否登录并读到数据 |
| 业务查询 | 对象存在，值符合预期 | 权限没有超出范围 |
| 手写的审计 `SELECT` | 记录了角色、对象、权限和理由 | 这些操作真的执行过；它只是一份声明，要和 `SHOW ROLES` 对照 |
| 以测试消费者身份查询 | 这个身份实际能读什么、不能读什么 | 其他身份或其他主机的访问结果 |

最后一类证据最接近真实访问，但课程沙箱没有演示。它在隔离环境中的表现是：只被授予视图 `SELECT_PRIV` 的用户可以查询视图；直接查询底层明细表时，Doris 返回 `Access denied; you need (at least one of) the (Admin_priv,Select_priv) privilege(s) on table ...`。这也印证了 12.2 的结论：`ADMIN_PRIV` 和 `SELECT_PRIV` 都能通过读取检查，`GRANT_PRIV` 不能。

一份完整的发布记录应包含身份、对象、权限、原因和发布标识，并把权限证据和业务值证据关联到同一个变更编号上。

## 12.4 看板下线后如何收回权限？

半年后看板下线。如果没人主动收回，`course_bi_reader_l3` 和它的授权会一直留在系统里；以后有人把这个角色授给新用户，就会带出早已没人记得的访问权限。

下面的语句由 Lab 12 执行，这里只阅读：

<!-- reading-only-example -->
```sql
REVOKE SELECT_PRIV
ON internal.dw_course_l1_demo.orders_imported
FROM ROLE 'course_bi_reader_l3';

DROP ROLE IF EXISTS course_bi_reader_l3;
```

撤销按固定顺序进行：

1. 确认影响范围：用 `SHOW ROLES` 查看角色的 `Users` 列。撤销角色上的权限会影响所有持有者，如果还有其他消费者持有这个角色，先和他们的负责人确认；
2. 撤销授权：用 `REVOKE` 显式收回本次发布授予的权限，变更记录里就能写清楚收回了哪一项；如果发现角色仍有人使用，可以停在这一步；
3. 删除角色：确认角色不再需要后，执行 `DROP ROLE`；
4. 复核结果：再执行一次 `SHOW ROLES`，确认角色和授权都已经不在。

在 Lab 12 中，授权后的 `SHOW ROLES` 已经显示 `Users` 列为空，所以撤权后可以直接删除角色，最后再用 `SHOW ROLES` 复核。

撤销只改变访问，不改变数据产品：

- 持有该角色的用户之后查询 `orders_imported` 会被拒绝；如果这是该用户在这个库中唯一的权限，连以这个库为默认库建立连接都会失败，返回 1044 错误；
- `orders_imported` 仍然是 10 行、合计 1400.00，粒度和字段都不变；
- 通过其他角色获得权限的用户不受影响。

生产环境还要保留审批和撤销的记录。`DROP ROLE` 删除的是角色本身，不能代替审计记录；撤销前后两次 `SHOW ROLES` 的输出就是撤销证据。语法和权限要求见 [REVOKE FROM](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/account-management/REVOKE-FROM) 和 [DROP ROLE](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/account-management/DROP-ROLE/)。

## 12.5 表级权限不够细怎么办？

看板上线后又来了两个需求：订单明细里的 `paid_amount` 和 `refund_amount` 只允许财务查看；东区团队只能看到 `region = 'EAST'` 的订单。表级 `SELECT_PRIV` 只能整张表授予或不授予，这两个需求都表达不了：

| 需求 | 可以考虑的机制 | 注意什么 |
| --- | --- | --- |
| 部分列只给特定角色 | 列权限，如 `SELECT_PRIV(order_id, order_amount)` | 表新增列时要重新评审授权范围 |
| 按条件只看部分行 | Row Policy，可以绑定到用户或角色 | 过滤条件要用真实消费者身份验证 |
| 敏感字段只显示部分内容 | 数据脱敏 | 需要结合相应的数据访问控制方案或 Ranger |

不管选哪种机制，都要用真实的普通消费者身份验证效果；root 或管理员执行成功，不能说明普通用户已经被隔离。先写清楚要防什么、涉及哪些对象、怎样验收，再选择具体实现。各机制的边界见 [Data Access Control](https://doris.apache.org/docs/4.x/admin-manual/auth/authorization/data/)。

## 动手实验：受控发布一个 BI 读者角色

打开 [Lab 12](lab12_publishing_permissions_audit.ipynb)，按顺序完成：

1. 检查当前用户、数据库和已有授权；
2. 创建课程专用的 `course_bi_reader_l3` 角色；
3. 只授予当前课程库中 `orders_imported` 的 `SELECT_PRIV`；
4. 输出角色和审计记录，确认对象范围；
5. 撤销授权并删除角色，确认实验没有留下多余权限。

### 前置条件和安全说明

Lab 12 只需要 Level 1 Lab 5 加载的 `orders_imported`；Level 2 的服务视图只在独立练习中使用。Notebook 会在变更前检查这张表是否存在。实验只使用专用的 `dw_course_l1_*` 数据库，不创建真实用户，不打印密码，也不向共享生产对象授权。它验证的是角色配置和数据值；角色没有授给真实用户，所以也没有验证消费者登录后的访问结果。

### 完成标准

| 检查 | 预期 |
| --- | --- |
| 前置数据 | `orders_imported` 为 10 行、合计 1400.00 |
| 发布前身份 | 显示当前课程用户和专用数据库 |
| 授权范围 | `TablePrivs` 中只有当前库的 `orders_imported`，不是全局或整库 |
| 授权类型 | `Select_priv`，没有 `Admin_priv` 或 `Grant_priv` |
| 审计记录 | 角色、对象、权限和理由四项都有记录 |
| 清理后 | `SHOW ROLES` 中不再出现 `course_bi_reader_l3` |

## 独立练习

假设 BI 团队还需要读取 Level 2 的 `bi_order_metrics_l2`，但不能读取订单明细。请写出：

1. 角色需要的最小对象范围；
2. 应检查的两个权限证据；
3. 发布失败时的撤销步骤；
4. 为什么不能直接授予 `SELECT_PRIV ON internal.*.*`。

<details>
<summary>参考解释</summary>

最小范围是只授予这个视图的 `SELECT_PRIV`。下面的语句只用于阅读，Lab 12 不会执行：

<!-- reading-only-example -->
```sql
GRANT SELECT_PRIV
ON internal.dw_course_l1_demo.bi_order_metrics_l2
TO ROLE 'course_bi_reader_l3';
```

不需要给它依赖的 `daily_order_metrics_l2` 或 `orders_imported` 授权。只拿到视图权限的角色可以查询视图；如果把明细表也授给它，它就能绕开视图直接读取订单明细。

权限证据至少留两份：授权前的 `SHOW GRANTS`，记录执行者和变更前的状态；授权后的 `SHOW ROLES`，确认 `TablePrivs` 中只有这个视图。在隔离环境中实际发布时，还应以测试消费者身份验证“视图可读、明细不可读”。

发布失败时，先确认没有其他消费者持有这个角色，再 `REVOKE` 刚才的授权；角色不再需要时执行 `DROP ROLE`，最后用 `SHOW ROLES` 复核。

`internal.*.*` 会覆盖内部 Catalog 中现有和以后新建的所有库表，其中就包括订单明细。它远远超出契约承诺的访问范围，一旦误授，影响面也最大。

</details>

## 单元总结

- 授权之前先写消费者契约：对象、粒度、字段语义、新鲜度、访问范围和责任人；
- 权限授给专用角色而不是直接授给用户，数据访问权限 `SELECT_PRIV` 要和 `GRANT_PRIV`、`ADMIN_PRIV` 等管理权限分开；
- 授权范围收窄到契约里的对象，不共享 root，也不授予 `*.*.*` 或 `internal.*.*`；
- `SHOW GRANTS`、`SHOW ROLES`、业务查询和审计记录各自回答不同的问题，root 在沙箱中执行成功不等于消费者权限设计正确；
- 撤销按“确认影响、撤销授权、删除角色、复核结果”的顺序进行，只改变访问，不改变数据产品；
- 表级权限不够细时，考虑列权限、Row Policy 或脱敏，并用真实的普通消费者身份验证。

## 知识测验

[Quiz 12](quiz12_publishing_permissions_audit.ipynb) 包含 5 道离线题目，检查消费者契约、最小权限、数据权限与管理权限的区别、发布审计证据和撤销边界。

## 官方参考资料

- [Built-in Authorization](https://doris.apache.org/docs/4.x/admin-manual/auth/authorization/internal/)
- [GRANT TO](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/account-management/GRANT-TO)
- [REVOKE FROM](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/account-management/REVOKE-FROM)
- [SHOW GRANTS](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/account-management/SHOW-GRANTS)
- [SHOW ROLES](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/account-management/SHOW-ROLES/)
- [Data Access Control](https://doris.apache.org/docs/4.x/admin-manual/auth/authorization/data/)
