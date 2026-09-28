# 模块 12：发布、权限与审计

| 课程信息 | 说明 |
| --- | --- |
| 所属课程 | Data Warehousing with Apache Doris · Level 3 |
| 产品范围 | Apache Doris 4.x；示例使用课程单节点沙箱 |
| 前置知识 | Level 1 的订单表；Level 2 的消费者视图仅用于独立练习 |
| 建议用时 | 约 65 分钟：阅读 30 分钟、实验 30 分钟、测验 5 分钟 |

[Level 3 目录](../README.md) · [打开 Lab 12](lab12_publishing_permissions_audit.ipynb) · [打开 Quiz 12](quiz12_publishing_permissions_audit.ipynb)

## 单元目标

数据产品发布不是执行一条 `GRANT` 就结束。发布者需要先确认对象范围、消费者需要的最小权限、授权者是否有 `GRANT_PRIV`，再保留可以复核和撤销的证据。本单元用一个只读 BI 角色演示这条流程，同时明确课程沙箱和生产环境的边界。

### 学习目标

完成本单元后，你应当能够：

1. 为数据产品写出对象、列、粒度、新鲜度和责任人的消费者契约；
2. 区分用户、角色、权限、对象范围和 `GRANT_PRIV`；
3. 用最小权限原则为 BI 消费者授权，而不是授予全局管理员权限；
4. 用 `SHOW GRANTS`、`SHOW ROLES` 和对象查询保留发布前后的证据；
5. 在变更失败或发布撤回时，按范围执行 `REVOKE` 和清理；
6. 说明 Doris SQL 能证明什么，不能替 BI 图表和 AI 模型证明什么。

## 单元安排

| 小节 | 核心问题 | 建议用时 |
| --- | --- | ---: |
| 12.1 发布不是单条 SQL | 什么是数据产品契约？ | 8 分钟 |
| 12.2 RBAC 与最小权限 | 用户、角色和权限如何分工？ | 8 分钟 |
| 12.3 范围与授权证据 | 如何避免误授整个集群？ | 8 分钟 |
| 12.4 撤销与审计 | 如何证明变更可逆？ | 6 分钟 |
| Lab 12 | 创建、复核并清理 BI 读者角色 | 30 分钟 |
| Quiz 12 | 检查治理概念 | 5 分钟 |

## 12.1 发布前先定义数据产品

一个消费者接口至少要写清楚下面这些内容：

| 契约项 | 本课程示例 | 为什么要写 |
| --- | --- | --- |
| 对象 | `orders_imported` 或 Level 2 的消费者视图 | 避免把相似表误当成同一产品 |
| 粒度 | 一行是一笔订单，或一行是一天 | 防止下游重复求和 |
| 字段语义 | 订单金额不是已收款金额 | 防止业务含义漂移 |
| 新鲜度 | 每次加载后更新，或接受固定延迟 | 决定刷新和告警方式 |
| 访问范围 | 只读、指定数据库和表 | 将权限限制在消费需要的范围 |
| 责任人 | 数据产品负责人和消费者负责人 | 发生异常时知道谁复核 |
| 验收证据 | 行数、总额、日期覆盖、授权记录 | 让发布结果可重现 |

如果只记录“SQL 执行成功”，仍然不知道对象是否正确、金额是否被放大、授权是否过宽，或发布后如何撤销。发布步骤应先读元数据和当前权限，再执行变更。

## 12.2 Doris 的 RBAC 基础

Doris 内置授权可以理解成三层关系：**权限 → 角色 → 用户**。权限说明可以对某个对象做什么；角色将一组权限命名并复用；用户通过角色获得权限。角色变化会影响持有该角色的用户，因此角色是集中撤销和审计的边界。

### 权限不是身份

`SELECT_PRIV` 允许读取指定范围的数据，不能自动创建用户、授予其他人权限或执行集群管理。`GRANT_PRIV` 是授权能力，通常应只给受控的管理员或委托角色。`ADMIN_PRIV` 和 `NODE_PRIV` 属于更高的管理范围，不应为了查询一张表而授予给 BI 账号。

### 权限范围从大到小

授权语句的对象范围必须与消费者需求一致。范围越大，误用和泄露影响越大。本实验为减少前置依赖，选用当前课程数据库的 `orders_imported` 表演示表级授权；它是订单明细，不是正式交付给 BI 的服务视图。

```sql
-- 只读指定表；catalog 使用 internal，数据库使用当前课程库
GRANT SELECT_PRIV
ON internal.dw_course_l1_demo.orders_imported
TO ROLE 'course_bi_reader_l3';
```

Notebook 会使用当前 `lab.database` 生成对象名，避免把示例库名硬编码到用户环境。生产环境还应使用正式的用户、主机范围、密钥管理和审批流程；课程沙箱的 root 账号只是为了让实验可重复，不是生产授权范例。

官方边界见 [Doris 内置授权](https://doris.apache.org/docs/4.x/admin-manual/auth/authorization/internal/)、[GRANT TO](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/account-management/GRANT-TO) 和 [SHOW PRIVILEGES](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/account-management/SHOW-PRIVILEGES/)。

## 12.3 发布流程中的证据

建议把发布拆成五个可以单独复核的检查点：

1. **身份检查**：记录当前用户和当前数据库；
2. **对象检查**：确认目标库、表、视图和字段；
3. **授权前检查**：查看已有 `SHOW GRANTS`，防止重复或意外叠加；
4. **授权后检查**：查看 `SHOW ROLES` 或 `SHOW GRANTS`，确认权限范围和角色名称；
5. **业务检查**：用只读查询核对行数、指标总额和日期覆盖范围。

这些证据回答的是不同问题。`SHOW ROLES` 说明角色配置，不能证明消费者已经用该角色成功登录；业务查询说明数据值，不能证明权限没有超范围。完整的发布记录应把两类证据关联到同一个变更编号或运行批次。

## 12.4 撤销、回滚与安全边界

授权变更应设计对应的撤销动作：

```sql
REVOKE SELECT_PRIV
ON internal.dw_course_l1_demo.orders_imported
FROM ROLE 'course_bi_reader_l3';

DROP ROLE IF EXISTS course_bi_reader_l3;
```

先撤销权限，再删除临时角色；执行前仍要确认角色没有被其他消费者使用。`DROP ROLE` 不是“撤销所有历史业务责任”的替代品，生产环境应保留审计记录和审批信息。

Doris 的 [REVOKE FROM](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/account-management/REVOKE-FROM) 和 [DROP ROLE](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/account-management/DROP-ROLE/) 文档说明了语法和权限要求。课程实验最后提供清理步骤，避免反复运行在沙箱中积累角色。

## 12.5 细粒度访问的边界

表级 `SELECT_PRIV` 不能表达所有治理需求。若不同消费者需要不同列，应考虑列权限；若不同租户只能看自己的行，应研究 Row Policy；若敏感字段需要脱敏，还要结合相应的数据访问控制或 Ranger。不要在本实验中把 root 用户执行成功误解为普通消费者已经被隔离，因为默认管理用户不代表真实消费者权限。

官方的 [Data Access Control](https://doris.apache.org/docs/4.x/admin-manual/auth/authorization/data/) 介绍了 Row Policy、列权限和数据脱敏的边界。选择机制时先写威胁、对象和验收方式，再决定具体实现。

## 动手实验：受控发布一个 BI 读者角色

打开 [Lab 12](lab12_publishing_permissions_audit.ipynb)，按顺序完成：

1. 检查当前用户、数据库和已有授权；
2. 创建课程专用的 `course_bi_reader_l3` 角色；
3. 只授予当前课程库中 `orders_imported` 的 `SELECT_PRIV`；
4. 输出角色和审计记录，确认对象范围；
5. 撤销授权并删除角色，验证实验不会留下权限垃圾。

### 前置条件和安全说明

Lab 12 只需 Level 1 Lab 5 的 `orders_imported` 即可运行；Level 2 的服务视图用于后面的独立练习。Notebook 会在变更前检查表是否存在。它只使用专用的 `dw_course_l1_*` 数据库，不创建真实用户，不打印密码，也不会向共享生产对象授权。实验验证的是角色配置和数据值，没有将角色授给真实用户，也没有验证消费者登录后的访问结果。

### 完成标准

| 检查 | 预期 |
| --- | --- |
| 发布前身份 | 当前课程用户和专用数据库 |
| 授权对象 | 当前库的 `orders_imported`，不是全局或整库 |
| 授权类型 | `SELECT_PRIV`，不是 `ADMIN_PRIV` |
| 审计记录 | 角色、对象、权限、理由均有表格记录 |
| 清理后 | 授权已撤销，临时角色已删除 |

## 独立练习

假设 BI 团队还需要读取 Level 2 的 `bi_order_metrics_l2`，但不能读取明细订单。请写出：

1. 角色需要的最小对象范围；
2. 应检查的两个权限证据；
3. 发布失败时的撤销步骤；
4. 为什么不能直接授予 `SELECT_PRIV ON internal.*.*`。

<details>
<summary>参考解释</summary>

应把权限限制在目标数据库的 `bi_order_metrics_l2` 视图，并只授予 `SELECT_PRIV`，不能顺手授予订单明细表。发布前后分别保存 `SHOW GRANTS`/`SHOW ROLES` 和对象范围证据；若在隔离环境实际发布，还应以测试消费者身份验证“视图可读、明细不可读”。失败时撤销已授予的对象权限，再清理临时角色。全局范围会把当前和未来对象一起暴露，超出 BI 的最小需求，也增加误授权影响面。

</details>

## 单元总结

- 数据产品发布包括契约、对象范围、权限、业务值和责任记录；
- 角色用于集中管理，但不应替代对象范围和最小权限设计；
- `SHOW GRANTS`、`SHOW ROLES` 和业务查询分别提供不同证据；
- 可逆的发布必须包含明确的 `REVOKE` 和清理步骤；
- root 在沙箱中执行成功，不等于普通消费者权限设计正确。

## 知识测验

[Quiz 12](quiz12_publishing_permissions_audit.ipynb) 包含 5 道离线题目，重点检查 RBAC、最小权限、授权证据和撤销边界。

## 官方参考资料

- [Built-in Authorization](https://doris.apache.org/docs/4.x/admin-manual/auth/authorization/internal/)
- [GRANT TO](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/account-management/GRANT-TO)
- [REVOKE FROM](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/account-management/REVOKE-FROM)
- [SHOW ROLES](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/account-management/SHOW-ROLES/)
- [Data Access Control](https://doris.apache.org/docs/4.x/admin-manual/auth/authorization/data/)
