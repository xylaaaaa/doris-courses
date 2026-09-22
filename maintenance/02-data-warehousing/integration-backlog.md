# Level 1 教学范围与实验验证清单

更新于 2026-09-20。课程讲义、七个主线 Lab、三份基础扩展 Notebook 与两个持续接入选做 Lab 是不同交付物；
“有讲解”“手工验证片段”“已有可重跑 Notebook”分开记录，不能互相替代。
数据基线以课程 `datasets/README.md`、manifest 和独立预期文件为准。
运行条件与结果见 [VALIDATION.md](VALIDATION.md)。

## 已有可运行材料

| 单元 | 主线 / 扩展已覆盖 | 尚未覆盖的边界 |
|---|---|---|
| Module 1 | WWI 十单连接、查询与汇总，10 行、12220.60 | 不验证容灾或生产规模 |
| Module 2–3 | 主线模型与小批次；扩展 100,000 行、100 批 vs 1 批、分区对照、逐行一致性与 Profile；Rowset 状态入口已有手工验证 | 持续写入压力、多请求合批、多节点分布与受控 Compaction 观察；不能从一次耗时推断性能 |
| Module 4 | Iceberg Catalog、关联与落地；扩展独立 Parquet TVF 与同一 WWI 十单逐行对账 | 其他 Catalog、演进和生产规模 |
| Module 5.3 | 讲义省略字段示例；扩展 DEFAULT、生成列按分转元，结果逐行核对 | 更多类型、表达式与模型组合 |
| Module 5.4 | 主线 Stream Load 失败与 label 重试；扩展 off/sync/async 的响应、首次完整可见时间、GroupCommit 标志与最终结果 | 多请求共享事务、持续吞吐、WAL 故障；不能把 off_mode label 结论套到合批 |
| Module 5.5 | WWI 十表 Parquet Stream Load；扩展 S3 TVF + INSERT SELECT、Broker Load，等 FINISHED 并逐行核对 | 更大批次、导入中断与失败恢复 |
| Module 5.6 | Lab 5A：真实 Kafka / Routine Load，暂停积压、恢复、重复订单与状态更新，最终三笔 / 350.00 | 跨分区乱序、坏数据与生产吞吐；不等同于源库 CDC |
| Module 5.7 | Lab 5B：真实 MySQL Binlog、Flink CDC、Doris Connector；单表快照、增删改、Checkpoint、Savepoint 停止/恢复，最终三笔 / 240.00 | 整库同步、自动 Schema 演进、源库故障与崩溃恢复 |
| Module 6 | 13 输入 → 10 合格、3 拒收；完整质量对账与错误注入；扩展独立表加列和 INT→BIGINT，检查任务与下游投影 | 更复杂 Schema Change、真实动态新鲜度、调度集成 |
| Module 7 | 主线部分更新、软删除、SQL DELETE、乱序和人工重放；扩展导入删除版本裁决、暂存事件内容冲突检测 | 主线模拟重放不能代替真实恢复；选做 Lab 5B 仅覆盖受控 Savepoint 恢复；多写者原子拒收；不能把暂存检查叫作生产冲突处理服务 |

持续接入选做入口：[Lab 5A / 5B 环境与运行说明](../../doris-course/02-data-warehousing/environments/streaming/README.md)。

基础扩展入口：[Level 1 扩展实验](../../doris-course/02-data-warehousing/level1/extensions/README.md)。
扩展在独立 ext_* 表执行，不修改主线数据，不增加视频数。需要 PyArrow 的扩展依赖单独安装。

## 介绍型内容与可选的后续集成验证

Kafka 和 MySQL/Flink CDC 已增加选做实验，七个主线 Lab 的完成条件不变。下表列出仍仅介绍或留待进阶验证的内容，不是当前结课门槛。

| 单元 | 若另做集成实验，需要什么 | 届时的验证范围 |
|---|---|---|
| Module 5.8 | Doris 4.1 CDC_STREAM 目标补丁验证 | 明确模式、源表要求、位点和恢复；不能只凭语法示例验收 |
| Module 5.9 | Streaming Job 对象存储持续文件实验 | 文件发现、处理进度、迟到与补数按目标版本实测；批量 Broker Load 不代替此项 |
| Module 7 | 超出受控 Savepoint 的恢复场景 | 源库故障、Binlog 丢失、历史逐行对账与业务版本映射；不能由 Lab 5B 当前状态表验收代替 |

先固定输入、预期和版本，再写演示，最后录制。没有通过运行的路径不得进入录制稿的成功结果。
Level 1 的学习完成条件为七个主线 Lab、独立练习及 Quiz，三份基础扩展 Notebook 与 Lab 5A / 5B 均选做。介绍型内容无需外部链路运行记录；不能把主线通过或两个选做 Lab 通过说成所有持续接入、恢复路径或生产并发已验证。视频录制状态另行记录。
