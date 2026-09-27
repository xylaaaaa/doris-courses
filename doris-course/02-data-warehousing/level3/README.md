# Level 3：权限、资源与运维

Level 3 面向 Level 1 和 Level 2 数据产品建成后的发布治理与持续运维。请使用专用的 `dw_course_l1_*` 数据库，并在执行每条管理语句前检查对象范围。

| 模块 | 主题 | 材料 |
| --- | --- | --- |
| 12 | 发布、权限与审计 | [课程](module12-publishing-permissions-audit/course.md) · [实验](module12-publishing-permissions-audit/lab12_publishing_permissions_audit.ipynb) · [测验](module12-publishing-permissions-audit/quiz12_publishing_permissions_audit.ipynb) |
| 13 | 存储与生命周期管理 | [课程](module13-storage-lifecycle/course.md) · [实验](module13-storage-lifecycle/lab13_storage_and_lifecycle.ipynb) · [测验](module13-storage-lifecycle/quiz13_storage_lifecycle.ipynb) |

两个实验分别展示访问治理和数据维护，并把运维证据保留在表格中。建议先完成 Level 1 Lab 5 和 Level 2 Lab 10；Lab 12 会检查 `orders_imported`，Lab 13 使用完全隔离的运维表，不依赖业务表。每个实验都包含前置检查、结果断言、独立练习和清理步骤；课程沙箱的 root 执行成功不等于生产环境已经完成权限审批或容量验证。
