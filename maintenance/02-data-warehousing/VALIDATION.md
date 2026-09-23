# Validation record

## English translation of the complete course 02 learner materials

- Translated all authored Chinese under `doris-course/02-data-warehousing`: seven lessons, seven main Labs and their reference solutions, seven Quiz notebooks and YAML question sets, three extension notebooks, course/environment/dataset guides, and runtime UI messages. The two streaming labs were already English.
- Preserved lesson structure, SQL, data fixtures, numeric baselines, quiz answer keys, notebook cell IDs, and execution logic. Removed only the UI wrapper that replaced the shared renderer's English status labels with Chinese.
- Updated language-dependent assertions and added checks for Chinese in authored sources and broken translated Markdown heading fragments. Historical notebook outputs and ignored checkpoints are excluded from the language scan.
- Validation: **103 offline tests passed** on a clean HEAD export overlaid with translated sources. Tests exercise all Quiz choices and feedback, notebook syntax, examples, objectives/schedules, links, and runtime behavior. A separate AST/SQL comparison confirmed unchanged notebook/reference-solution code structure and executable reading examples; original ASCII literals and quiz answer keys were preserved.
- Existing user outputs, execution counts, metadata, and added blank cells remain in the working tree. The commit contains only translated sources applied to the committed notebook structure, without those pre-existing changes.
- This is a language-only change. Live database labs and browser rendering were not rerun for this translation; previous integration results remain historical evidence, not new runs. Test log: `/tmp/dw-english-tests.log`.

## 2026-09-20: Streaming review fixes and English optional-lab text

This follow-up fixes the first two review findings. Startup output buffering remains unchanged.

### Changes

- Data waits now require a job-health callback. Kafka polls include `SHOW ALL ROUTINE LOAD FOR ...` and report unexpected PAUSED/STOPPED/CANCELLED states, the job name, state-change reason, and error URLs. Intentional pause checks still query the table directly.
- Flink data and checkpoint waits check the job on every poll. An old completed checkpoint cannot hide a failed or unexpectedly finished job. Diagnostics include the job ID and exception-page URL.
- `prepare_environment(start=True, streaming=True, streaming_profile=...)` checks Docker-visible total RAM/CPU before startup and applies the matching resource overlay. The Kafka profile uses an 8 GiB Doris limit and requires 10 GiB/2 CPUs; the CDC profile retains the 12 GiB Doris limit and requires 18 GiB/4 CPUs. Base main-course startup is unchanged. These are conservative preparation policies, not checks of free RAM. README commands explain configuration, inspection, and shared-host pressure.
- Both optional Notebook bodies, code-cell labels, and the streaming environment README are now English. Other course lessons, main notebooks, and shared Chinese display widgets have not been translated in this follow-up.

### Evidence

- **101 offline tests passed** against a clean HEAD export overlaid with only this task's files, excluding existing user Notebook outputs. New tests cover health checks on each poll, stale checkpoint rejection, stopped/suspended jobs, Routine Load error details, capacity failures before startup, overlay propagation, and English Notebook text with checked data waits.
- Both updated English Notebooks passed `run_streaming_labs.py all` against the local Docker environment. Kafka: pause retains two rows, resume/duplicate/update yields three rows totaling 350.00. CDC: snapshot 350.00, source mutations 225.00, controlled savepoint restoration 240.00, with the restored path checked.
- Initial Flink job: `5a181f6318aab36328a29e2620005467`; restored job: `205acd3419e06bef494218d8f71da256`. Both finished normally. Final savepoint: `file:/opt/flink/state/savepoints/savepoint-205acd-3081500352a1`.
- Actual negative probes rejected the stopped Kafka job `course_orders_00d46ce84c38` and rejected checkpoint acceptance for the finished restored Flink job immediately. These were read-only probes after the labs, not injected production failures.
- Docker inspect confirmed both Doris limits at `12884901888` bytes. The overlay recreated the course container while retaining BackendId `1789708590884`, host `127.0.0.1`, and `Alive=true`; BE `SUM(numbers(10))` remained 45. No active Routine Load jobs remained.
- Execution log: `/tmp/dw-streaming-review-fixes.log`; offline test log: `/tmp/dw-review-unit.log`. Source Notebooks retain empty outputs. This run used locally cached images and existing volumes, not a fresh-install or Docker Desktop/ARM test. A fresh Jupyter kernel/browser rendering pass was not repeated for this follow-up.

### Review checkpoints

- Goal and scope: two reported defects fixed, two optional labs translated; SQL, data baselines, and the third review finding are unchanged.
- Reuse and parallel paths: shared polling accepts health callbacks; both Kafka and Flink call sites are covered. Existing main-course startup retains its default behavior.
- Concurrency and lifecycle: single-user execution remains required. No new locks or automatic cleanup of failed jobs; normal completion stops only lab jobs and retains volumes. Applying/removing the overlay can recreate Doris, so README warns against concurrent main-course work.
- Configuration and compatibility: resource changes take effect through Compose recreation, not a live BE configuration change. No kernel, storage-format, Delete Bitmap, C++ lifetime, or memory-tracking changes.
- Failure paths and tests: missing jobs and terminal states raise; preflight rejects insufficient capacity before container commands. Unit negatives and real stopped-job probes supplement full normal-path runs; arbitrary crash recovery is not claimed.

## 2026-09-20：新增 Kafka 与 MySQL/Flink CDC 选做 Lab

在同日“主线仅要求理解持续接入”的范围上，补充两个**选做**实验；主线七个 Lab 的完成条件不变。
CDC_STREAM、对象存储持续文件和生产并发仍未实测。

### 交付与实测环境

- `optional5_kafka_routine_load.ipynb`：Kafka JSON → Routine Load → 独立 MoW 表。
- `optional5_flink_mysql_cdc.ipynb`：真实 MySQL Binlog → Flink SQL CDC → Doris Connector；Module 7 可复用。
- `environments/streaming` 提供 Compose profiles、固定 JAR 版本的 Dockerfile、MySQL 初始化及启动/停止/排查说明；无 JAR 二进制入库。
- 共用原单 FE/BE 沙箱，实际 BE 版本 `doris-4.1.3-rc02-7126cf65d96`，BackendId `1789708590884`，注册地址仍为 `127.0.0.1`。连接器显式使用 `benodes=doris:8040`，不修改 BE 注册身份。
- Kafka 3.9.0；MySQL 8.0.33（ROW/FULL、+08:00）；Flink 1.20.1 / Java 11；CDC SQL JAR 3.4.0；Doris Connector 25.0.0；MySQL JDBC 8.0.27。
- 所有写入限定在 `dw_course_l1_streaming.ext_kafka_orders` / `ext_cdc_orders` 和新建 MySQL 服务的 `course_cdc.orders`。没有修改既有主线 Notebook 或其未提交的学员输出。

### 验证结果

- 在干净 HEAD 导出副本叠加任务文件后，**90 项离线测试通过**。覆盖既有材料、19 个 Notebook、新增 profile/显式启动、超时、命令与 SQL Client 失败、终态错误、Savepoint 响应、时区对齐和本地端口范围。
- 两个 Notebook 均通过专用脚本执行；随后用独立 Jupyter 内核重跑并导出 HTML，两个 Notebook 都无错误输出。再停止四个依赖容器，从停止状态用 `run_streaming_labs.py all` 重新启动并完整通过两项实验。没有声称浏览器交互截图已验收。
- Kafka：初始两笔；PAUSED 时追加第三笔仍保持两笔；恢复并重复发送、更新后为三笔 / 350.00，910001=PAID。一次脚本运行的最终 Progress 为 partition 0 offset 4、Lag=0、loadedRows=5；结束时 STOP 本次任务并删除本次随机 Topic。
- CDC：快照三笔 / 350.00；源端 UPDATE/DELETE/INSERT 后三笔 / 225.00；停止后源端再次增删改，目标保持原结果；从 Savepoint 恢复后为三笔 / 240.00，逐行匹配固定预期和源端展示结果。
- 独立内核运行：初始 Job `e4eaa6b93d8632d171a99c16c1ecf353`；恢复 Job `51a6452dff10704e3820b7bc407b0351`。
  REST 的 `latest.restored.is_savepoint=true`、`external_path=file:/opt/flink/state/savepoints/savepoint-e4eaa6-631acac11de6`；该路径与停止返回值一致。结束时再次保存状态并停止恢复后的作业。
- 验证后无活动 Routine Load；Flink 成功运行的作业均 FINISHED（早期时区失败的作业已定向 CANCELED）。Doris `Alive=true`，BE 计算 `SUM(numbers(10))=45`。
- 验证后已停止本次新增的 Kafka、MySQL 和 Flink 容器，保留其卷；Notebook 的启动单元可再次拉起。原 Doris 沙箱保持运行并通过 BE 查询复检。
- 本机日志：`/tmp/dw-kafka-test2.log`、`/tmp/dw-cdc-test2.log`、`/tmp/dw-stream-kernel-final.log`、`/tmp/dw-stream-all-unit-final.log`、`/tmp/dw-stream-index-tests.log`、`/tmp/dw-stream-restart-test.log`。执行产物保存在 `/tmp/optional5_*-executed.ipynb` 及同名 HTML，不回写学员源文件。

### 调试记录与运行边界

- 首次 Routine Load 被共享宿主机低可用内存水位拒绝，未将 RUNNING 当作导入成功。为**本机课程容器**设置 12 GiB memory / memory-swap 上限后重启原容器，保留 FE 元数据、BE 存储和注册身份，再通过查询验证。该本机限制保留，未写入通用单节点 Compose；其他容器未调整，未关闭内存保护。
- 首次 CDC 因 MySQL UTC 与 CDC Asia/Shanghai 不一致重启；最终 Compose 固定 `--default-time-zone=+08:00`，重建该课程 MySQL 容器（保留卷）后重跑及独立内核验证通过。健康检查使用 TCP，避免在初始化临时 socket 服务就绪时提前运行。
- 新实验前检查活动任务，避免运行中重建表。演示限定一人顺序执行，不提供跨 Notebook 的并发锁；失败时保留作业供排查，README 给出定向停止方法。共享卷保留 Checkpoint / Savepoint，服务重启不会自动提交已停止的作业。
- 本次只验证固定 Schema 单表、受控停止与恢复；不宣称整库同步、自动 Schema 演进、任意故障 exactly-once、源库故障恢复或生产 SLA。

### 自检

- 目标/证据：两条可操作链路与结果、恢复信息均有实测；测试结果没有预写成功输出。
- 范围/复用：复用 `connect_sandbox`、`expect` 和既有 Notebook 执行器；新增辅助代码仅处理课程服务编排和轮询，教学 SQL 留在 Notebook。
- 并发/生命周期/写入：异步任务等待明确状态或结果；重置前检查活动任务，正常结束定向停止，保留结果与持久卷；多用户并发与崩溃原子性不在验收范围。
- 配置/兼容：新环境固定镜像、连接器和端口；配置变更需按 Compose 重建相应服务，不宣称动态生效；既有主线接口与数据格式不变。
- 分支/失败路径：Kafka 与 CDC 独立 profile；已同步讲义、目录、维护清单；命令非零、SQL Client ERROR、终态失败及等待超时均抛错，有负例测试。
- 可观测性/性能：展示 Routine Load Progress、Flink Job ID、Checkpoint 和恢复路径；固定三笔小样本仅验证正确性，不作为性能结论。
- 内核相关项：未修改 FE/BE、EditLog、版本发布、Delete Bitmap、跨端变量、C++ 初始化或内存追踪逻辑；不涉及滚动升级兼容变更。

## 2026-09-20：持续接入调整为介绍型教学

按课程范围决定，Kafka、Flink CDC、CDC_STREAM、持续文件与真实位点恢复仅作介绍，
不要求学员搭建外部链路；持续并发验证留给进阶内容。七个主线 Lab、独立练习和 Quiz
为学习完成条件，已有三份扩展 Notebook 选做。此前记录中的“仍需交付”是当时计划，
当前范围以 Level 1 README 和 integration-backlog.md 为准；未实测事实没有变化。

- 同步课程目录、Module 5/7 讲义与维护清单，保留配置示例及未实测边界。
- 更新范围一致性测试；在干净 HEAD 导出副本叠加本次修改后，79 项离线测试通过。
- 本次未改 SQL、Notebook 或运行逻辑，未重跑数据库实验，也未新增 Kafka/Flink 等环境。
- 自检：目标与测试一致；改动仅限教学范围及对应测试；并发、生命周期、配置与存储兼容性不涉及。
  同步检查目录、讲义和维护清单等对应入口；既有数据基线和历史运行证据保留。

## 2026-09-20：交付三份扩展 Notebook，同步实验状态

- 新增 level1/extensions 下三份可运行 Notebook：100,000 行批次/分区与 Profile；
  Parquet TVF、INSERT SELECT、Broker Load、默认值/生成列、Group Commit；
  Schema 加列与 INT→BIGINT、导入删除的版本裁决、事件 ID 内容冲突检测。
- 原七个主线 Notebook 未修改。新增 ext_* 表与每次唯一对象路径，保留结果供排查；
  课程湖表环境仍复用已有 prepare_lakehouse。PyArrow 19.0.1 作为 extensions 可选依赖。
- 预设 run_labs.py 增加 --extensions / --extensions-only，抽取共用执行函数；
  失败仍抛异常并恢复目录、关闭连接，不写回 Notebook 输出。
- integration-backlog.md 改为当前 Module/小节编号，分开“主线/扩展已覆盖”和“仍未交付”；
  不再把已验证的示例与整个单元都写成待实现。

验证：

- 干净 HEAD 导出副本叠加本次文件，78 项离线测试通过。新增检查包括扩展清单、
  无输出与可编译性、局部重置、失败关闭连接、Broker 取消/超时、旧 FINISHED 任务
  不能代替新列检查、Profile 恢复、固定结果与待办边界。
- 首次运行缺少 PyArrow，补为明确可选依赖后安装验证；首次材料检查因原来写死
  14 个 Notebook 和缺少统一封面失败，增加三份扩展后更新为 17 个并补齐相同封面。
- 在独立库 dw_course_l1_extensions_20260920 用预设脚本执行
  --iceberg --solutions --extensions，七个主线 Lab、七份参考解答、三份扩展全部通过；
  重新运行同一数据库仍通过。用户工作区 Notebook 编辑与输出未混入验证副本。
- 三份扩展分别经全新 Jupyter 内核执行并导出 HTML，均无执行错误；输出仅存临时目录。
  没有进行浏览器视觉检查、学员试讲或生产负载测试。
- WWI 文件、湖表和两种落地路径逐行一致；Broker 等待 FINISHED。默认值/生成列为
  CREATED/180.00 与 PAID/80.00；Schema 下游投影不变；删除实验普通查询行数为 1→0→0→1。
- 一轮 Group Commit 观察：off/sync/async 响应约 49.89/2046.53/9.14 ms，首次完整可见
  约 58.57/2056.18/2050.77 ms；async 响应后首查 0 行。仅是本次单请求观测，
  不写成固定时间或吞吐结论，不代表 WAL 故障恢复或多请求合批验收。
- 运行复用课程单容器 doris-4.1.3-rc02-7126cf65d96 与本地 MinIO/REST，未改其他集群。

自查结论：复用已有连接、数据契约和执行工具；没有 FE/BE 或持久化协议变化。
实验按单写者顺序执行，异步导入与 Schema Change 有状态检查和超时，任务失败不算成功。
会话设置用 finally 恢复；新增依赖可选，不改变基础安装。数据库写入限制在实验库和其湖表
命名空间内，跨表操作不宣称原子性。HTTP 导入保留响应且不自动跟随重定向；本轮不是安全审查。
Kafka、Flink CDC、CDC_STREAM、持续文件、真实位点恢复及持续并发负载仍未交付。

## 2026-09-20：补齐关键操作讲解，精简接入主线

- 保留 Module 1 的简洁阅读和全部 Level/Module 顺序；Module 2 增加 Tablet 字段、
  Rowset 状态入口和可恢复会话设置的 Profile 观察；不制造固定版本数量或性能结论。
- Module 3 展开实际分区 DDL；Module 4 展开课程 REST Catalog 配置与两类地址。
  Module 6 展开与 Lab 相同的 CASE 分类 SQL、两条分流写入，以及 Schema Change 基础。
  Module 7 展开部分更新和软删除/SQL DELETE，区分导入删除标记与内部 Delete Bitmap。
- 写入片段明确标为 SQL 阅读示例，说明初始化、重试和会话恢复条件。
  新增标记的材料检查限制可写目标，不将讲义写入混入默认只读查询；外部连接仍使用占位符。
- Module 5 保留九小节，将 5.8 的实验性与版本前提提前，合并重复 CDC 概念；
  增加省略字段的 DEFAULT 示例及金额单位映射解释。详细账务查询从 Lab 主流程移到
  optional_invoice_and_receipts.md；十表导入、订单关联、重试及独立练习保留。
- 建议学习时间调整为 Module 2/4/5/6 的 60/50/110/65 分钟，目录表与总时长相符；
  这是内容估算，不是学员试讲计时。

验证与自查：

- 干净 HEAD 导出副本叠加本次相关文件后，69 项离线测试通过；新增五项验证 DDL/分类
  与 Lab 一致、Profile 成功及失败后恢复开关、Catalog 参数、接入边界和删除机制讲解。
  首次检查误用了 Notebook 单元格编号，改为实际稳定 ID historical-check 后通过。
- 预设 scripts/run_labs.py --iceberg --solutions 在独立库
  dw_course_l1_teaching_20260920 运行七个 Lab 与七份参考解答，全部通过。
- 在上述独立验证库手工执行新增讲义片段：实际分区 DDL、REST Catalog（替换为本地
  fixture 参数）、DEFAULT、CASE 分流、部分更新及删除对照全部通过；Schema 加列只在
  orders_schema_reading 副本执行，十行旧数据的新列均为 NULL，未修改主线 Schema。
- Profile 示例成功生成记录并恢复开关；沿 SHOW TABLET / DetailCmd 读取 Rowset 状态。
  可选账务查询核对 267011.44 和 70426。所有数据库写入均限独立验证库及其专用 Catalog。
- 八份阅读材料经过 Jupyter Markdown 渲染，所有表格列数一致；Lab 5 在全新 Jupyter
  内核、独立库 dw_course_l1_teaching_kernel_20260920 中执行并导出 HTML，无执行错误，
  参考答案保持折叠。输出只保存在临时验证目录，没有写回学员 Notebook。
- 自查：没有修改 FE/BE、运行时辅助代码、数据样本或 Level 划分；没有新增并发、
  持久化格式、跨组件协议或权限行为。复用既有 Lab SQL 与环境配置，不重复实现工具逻辑。
  用户原有 Notebook 编辑和执行输出保留；只提交本次相关文件。
- 边界：此轮复用单容器构建 doris-4.1.3-rc02-7126cf65d96，不代表其他版本或平台验证。
  未执行 Kafka、真实源库 CDC、S3 持续文件、Group Commit sync/async、重型 Schema Change
  或导入删除标记实验；概念补齐不代表这些集成已交付。未进行浏览器视觉检查或学员试讲。


## 2026-09-20：统一学员材料的 Module 命名

- 七份讲义、测验标题、课程导航、实验说明及数据/环境说明统一使用 Module 1–7，
  不再在学员正文中混用 D01–D07；小节仍使用 1.1、2.1 等编号。目录名、数据与执行代码不变。
- 干净 HEAD 副本叠加本次命名修改后，64 项离线测试通过；新增检查覆盖旧编号残留、
  讲义与测验标题。仅替换文字，本轮未重跑数据库实验。
- 四个修改过的 Notebook 仅调整 Markdown source，代码、输出与执行元数据保持不变。
  Module 1 Lab 只提交基于 HEAD 的命名替换，不提交用户执行输出；其他用户编辑未覆盖。
  下方历史维护记录保留当时编号，不作为当前学员命名。

## 2026-09-20：简化 D01 入门讲义

- 保留 1.1–1.3、五个学习目标及 Lab/Quiz 入口，主线改为认识 Doris、查询订单、按天汇总。
  压缩重复说明，去掉提前展开的 MPP、存算分离、资源组与后续课程能力清单，
  不再在第一课叠加筛选后汇总、HAVING 和重复检测 SQL。
- 保留 FE/BE 分工、基础建表字段、三个查询示例及完整结果，仍提醒重复写入、
  样本范围和订单金额不等于收款。预计时间调整为 50 分钟，是建议值而非试讲计时。
- 不改 Lab、Quiz 或样本；材料测试改为检查保留的结果及其独立样本依据，
  不再要求讲义列出已移除的商品逐行计算表和筛选后日期汇总表。
- 干净 HEAD 副本叠加修改后，63 项离线测试通过；讲义 HTML 的九张表列数一致，
  代码块正常渲染。保留的五条 SQL 与修改前完全相同，本轮未重跑数据库实验。
  本轮只做教学简化，不涉及运行时代码、数据模型、并发或配置变更；学员 Notebook 编辑与输出保留。

## 2026-09-20：补齐示范到独立练习的衔接

- D05 首次 CSV 导入展开 HTTP 请求，逐项说明地址、认证、列映射、请求体和响应；
  后续重试继续复用原 label 与课程封装，独立练习再更换文件、表和映射。
- D05 增加 S3 批量、Kafka Routine Load、MySQL SQL 映射和 S3 持续文件四个阅读示例，
  包含输入、独立目标表、SQL、观测方法和预期结果。按当前官方 4.x 文档核对，
  链接放在对应小节；外部地址及凭据保留占位符，不随 Lab 自动执行。
  新增内容计入建议时间：D05 120 分钟、D06 55 分钟，均未经过真实学员试讲计时。
- D07 在第一个更新例子之前显示实际 DDL，解释 Unique Key、MoW 与 Sequence 属性。
  讲义明确普通字段命名不会自动启用版本裁决。
- D06 抽出唯一性检查，两个预期失败都直接调用它，避免总量检查先失败。
  新反例只替换第二行订单号，行数与总金额保持不变，仍须检出重复；
  每个反例后从分类输入恢复并逐字段验收，再交给 D07。

### 验证与自查

- 干净 HEAD 副本叠加本次变更，63 项离线测试通过。新增五项覆盖首次 HTTP 请求、
  首次展示 Sequence DDL、两个反例的检查入口、总量不变的重复及外部示例边界。
- 使用预设 `scripts/run_labs.py --solutions`，在独立库
  `dw_course_l1_followup_20260920` 执行六个核心 Lab 和六份参考答案，全部通过。
  复用课程单容器，BE 报告 `doris-4.1.3-rc02-7126cf65d96`。
- D05、D06、D07 分别在全新 Jupyter 内核中执行，使用另一独立库
  `dw_course_l1_followup_kernel_20260920`，无 error 或 stderr。
  导出的 HTML 包含两次唯一性检查成功提示，未出现误报的“验收未通过”；答案保持折叠。
- 三份讲义经 Jupyter Markdown 渲染器检查表格列数与代码块，四个外部 SQL 块正常显示。
  最初渲染检查脚本误将高亮代码块定位为 `pre code`，改按渲染器实际的 `pre` 结构检查后通过；
  这不是讲义内容或 Notebook 执行失败。
- 正确性与复用：D06 复用同一个唯一性函数与恢复函数，负例不修改固定预期数据；
  D05 后续请求仍用已有封装，D07 沿用已有 DDL 生成器，没有改变业务模型。
- 范围与兼容性：只修改三单元的讲义、Lab 与对应维护测试；没有新增运行时配置、
  并发、锁、FE/BE 协议或存储格式变更。实验写入仅限上述独立验证库。
  更新的三个 Notebook 的原有输出、执行计数和其他非 source 字段均保持不变；
  课程 01、D01、D02 的用户修改未覆盖或提交。
- 观测与生命周期：HTTP 响应与表内核对都保留；重复反例展示具体订单号。
  外部持续任务示例提供暂停方式，但本次没有实际创建外部任务。
- 未验证：新增外部示例的端到端运行、D04 重跑、浏览器像素级展示和学员完成率。
  真实 S3/Kafka/CDC 集成仍列在 integration-backlog.md，不以文档示例代替集成验收。

## 2026-09-18：Level 1 学习流程与自助实验

- 七个单元保留简洁的功能小节标题，调整模块总标题与时间分配。
  D01 将基础 SQL 单列为阅读小节 D01-03；这次调整不表示新增视频已经录制。
  D05 按单文件、重试、错误批次、历史十表推进；D07 先观察正常更新、重复与乱序，再进入多表中断恢复。
- 七个 Lab 各增加独立任务、空白代码格和默认折叠的参考解答。
  参考答案通过 `run_labs.py --solutions` 单独执行验证；普通 Run All 不会自动完成独立练习。
  七份题库各增加一个新场景，保持五题、四选项、逐选项解释与学习目标对应。
- 修复实验结束时提前关闭连接的问题，连接保持到内核结束。
  常规一致性检查成功时不再重复输出通用绿色卡片，改为展示订单明细、分流原因和业务汇总。
  预期重复错误仅捕获课程结果不匹配异常；没有出现预期错误或发生连接等异常时仍然失败。
- 完整 WWI Parquet 包随仓库提供，压缩后 10,508,150 字节。
  首次使用先在临时目录验证十个文件的大小和 SHA-256，再发布到 `.runtime/wwi/`；已有数据不覆盖。
  Microsoft MIT 许可和来源 manifest 保留；本轮没有上传对象存储或创建远程 PR。
- D04 新增课程专用 MinIO 与 Iceberg REST Catalog，端口 51900/51818 仅监听本机。
  初始化时发现 REST fixture 默认用户无法写入 Docker 命名卷中的 SQLite，修正本地 fixture 用户后启动成功。
  Doris 单容器加入课程湖表网络；按实验库隔离 Catalog/namespace，校验已有 Catalog 的目标与已有样本内容。
  真实 Iceberg 表的直查、关联、导入与重复准备均通过；无须讲师预先提供外部表名。
- 测试平台：Linux x86_64；Doris 镜像标签 `apache/doris:all-in-one-4.1.3`，
  实际构建报告 `doris-4.1.3-rc02-7126cf65d96`。
  MinIO `RELEASE.2025-01-20T14-49-07Z`，Iceberg REST fixture `1.10.0`。
- 暂存区导出的独立目录中 **58 项离线测试通过**：材料结构、35 题四选项交互、
  练习与答案结构、预期错误处理、文件完整性、解包与已有数据保留等。
  工作区存在学员执行输出，因此清洁状态检查在暂存区副本运行；没有清空学员记录。
- 七个 Lab 与七份参考答案在 `dw_course_l1_learning_20260918` 执行通过；
  暂存区副本中再次以 `dw_course_l1_staged_learning_20260918` 全量执行通过，
  未设置 `DW_WWI_DATA_DIR`，从随仓库分发的压缩包完成解包与 701,846 行历史导入。
- 在新 Jupyter 内核执行 D04、D06，输出无 error、无 stderr；
  HTML 包含湖表准备进度、订单结果和“已识别重复订单”，不含误报的“验收未通过”。
  七份 Notebook 导出的 HTML 中参考答案均默认折叠且代码块正常生成。
  原有 14 个 Notebook 的每个既存单元格，输出和非 source 字段的哈希均保持一致。
- 测试库和课程辅助容器保留便于复查；未写入默认学员库、未停止其他项目服务。
  尚未验证：macOS/ARM64 启动、浏览器像素级展示、真实学员独立完成率与试讲时长；
  Kafka/真实 CDC、Group Commit、文件 TVF 等后续实验仍见 [integration-backlog.md](integration-backlog.md)。

## 2026-09-18：Module 1 独立阅读讲义

- 扩充交易与分析场景、Doris 定位、FE/BE 查询路径、表定义解读，以及明细、筛选、
  分组和数据核对的完整示例。保留原有五个学习目标和 Quiz，讲义阅读加 Lab、Quiz 预计 65 分钟。
- 对照 Doris 4.x 官方产品介绍、架构、Duplicate Key、数据类型和 SELECT 文档核对技术说明。
  WWI 订单 4 的三条商品明细、筛选结果及分组金额由本地样本独立核对。
- 在现有课程沙箱的 `dw_course_l1_demo` 上，以只读 SELECT / SHOW 执行全部 10 条讲义 SQL。
  明细、筛选、两种日期汇总、总量和重复检查结果符合讲义；未执行写入或重建表。
  重复 INSERT 后的金额属于模型语义推演，本轮没有实际重复写入学员表。
- 暂存区独立副本上的完整 44 项离线检查通过，新增示例明细和筛选结果与样本一致性检查。
  本轮未修改 Lab/Quiz Notebook，也未重录或修改已有执行输出。

## 2026-09-18：按学习顺序连续编号

- Level 1 改为 Module 1–7：数据质量为 D06，更新与重放为 D07。
  目录、讲义、Lab、Quiz、题库加载路径、跨单元链接和实验执行器同步更新。
- 在暂存区导出的独立副本上，完整 43 项离线检查通过，包含连续编号、
  文件命名、执行器顺序、题库路径、本地链接及 Notebook 语法与清洁状态检查。
- 原工作区 14 个 Notebook 的运行输出及元数据校验保持不变；Jupyter 检查点随目录移动保留。
  本轮仅调整编号和导航，未启动容器、重跑数据库实验或修改业务数据。
- 总纲和 Level 1 实验设计文档同步编号；总纲 13 个单元、50 个视频连续且无重号。
  下方历史验证记录沿用当时编号，映射见[课程维护说明](README.md#编号迁移记录2026-09-18)。

## 2026-09-18：启动进度面板

- 启动流程复用仓库已有的 workflow HTML 和 CSS，显示双列六步卡片、
  进度条、绿勾、红色失败及灰色未执行步骤；标题和状态文字为中文。
- 六步与实际动作对应：Docker / Compose 检查、配置校验、按 missing 策略准备镜像、
  启动并等待容器健康、FE / BE 查询验证、查看课程容器。
  命令输出汇入折叠日志，失败时展开；异常仍向调用方抛出，不继续后续步骤。
- 41 项离线检查通过，覆盖成功、端口占用、下载超时、HTML 转义和原有课程检查。
  保留学员运行记录，未执行要求 Notebook 输出为空的检查。
- 使用新 Jupyter 内核执行真实初始化与启动调用，验证最终输出含六个成功卡片、
  100% 进度及可折叠日志；复用健康的课程容器，未执行表重建。
  验证输出只保存在内存，没有改写学员 Notebook。
- 本轮未执行浏览器截图或像素级视觉比较；布局使用现有共享样式，
  实测范围为 Notebook 输出协议、HTML 内容及真实启动结果。

## 2026-09-18：统一单容器学员启动流程

- D01 去掉已有实例 / Docker 选择与手工连接配置。初始化不启动服务；
  显式执行 prepare_environment(start=True) 才启动课程沙箱，再由 connect_sandbox() 连接。
- 后续六个 Lab 使用相同的 connect_sandbox()，不再启动容器。
  各内核独立配置固定的 FE / BE HTTP 端点，覆盖继承的旧连接地址；
  不需要先导出 DW_ALLOW_WRITES 或让其他 Notebook 继承 D01 的环境。
  执行实验连接单元是对文中重置范围的显式确认，实验库前缀限制仍生效。
- 在 Linux x86_64 上新建并启动 doris-warehousing-course-doris-1，只有一个容器，
  内含一个 FE 和一个 BE；使用项目专属网络、元数据卷和存储卷。
  没有停止、删除或重新配置其他服务。
- 镜像标签为 apache/doris:all-in-one-4.1.3，本机镜像 ID 为
  sha256:5d45eb13bf5e5434c3a2a0fab73ca75a39a5504a6b5ae8dc153efcab60683464；
  FE / BE 实际报告 doris-4.1.3-rc02-7126cf65d96，应保留此构建标识而非仅凭标签推断。
- Compose 健康检查通过；SHOW BACKENDS 显示 Alive=true；
  SELECT SUM(number) FROM numbers("number"="10") 返回 45，验证了 BE 计算。
- 独立库 dw_course_l1_container_20260918 中六个核心 Lab 顺序执行通过，
  包括全部 WWI 文件导入、质量分流、状态重放与业务对账。
  新 Python 进程携带错误的旧连接变量时，仍成功连接课程沙箱并查得
  orders_sample 十行、金额 12220.60。
- 38 项离线检查通过，包括单容器配置、显式启动、健康 / BE 失败分支、
  新内核连接、非实验库拦截、材料及四选项测验检查。
  保留用户 Notebook 执行记录，未运行要求所有输出为空的检查。
- 容器和验证数据保留用于继续学习。BE 报告磁盘使用率约 96.12%，
  可用空间约 78.24 GB，后续应关注空间；本轮没有清理或删除其他数据。
- 未验证：macOS / ARM64 启动、浏览器视觉效果、真实 Iceberg 及其他外部集成。
  Docker 容器日志可按环境说明中的 Compose logs 命令查看。

## 2026-09-18：按业务含义与实验用途命名表

- 七份讲义、七个 Lab、相关测验与环境说明统一使用业务表名；目录和标题仍保留单元编号。
  表名含义见 [Level 1](../../doris-course/02-data-warehousing/level1/README.md#how-are-lab-tables-named)。
- WWI 历史表保留 wwi_ 来源前缀；orders_sample、orders_current、order_events 等名称
  表达数据用途。orders_batch / orders_rowwise 等对照表及更新、删除练习表仍独立，
  不因去掉编号而合并实验数据。
- 同步修改动态目标表名与上游引用：质量实验读取 wwi_customers，
  状态实验读取 orders_clean、customers 和 wwi_products；不改数据集、模型或金额口径。
- 32 项离线检查通过，涵盖四选项测验、上游引用、Notebook 语法与本地链接。
  保留学员已有执行记录，因此未运行要求 Notebook 输出为空的检查。
  七个 Lab 的非 source 单元字段与修改前逐项相同，未写入执行输出。
- 通过 scripts/run_labs.py，在新建独立库 dw_course_l1_names_20260918 顺序执行
  六个核心 Lab 两次，全部通过。库中共有 33 个表或视图对象，保留供复查。
  六份核心讲义的 24 条 SELECT / EXPLAIN / SHOW 语句执行通过。
- 验证复用现有 FE 19030 / BE HTTP 18040，没有重启或修改服务配置。
  FE 构建为 doris-0.0.0-ad8644154c3，BE 构建为 doris-0.0.0-8bafeb1e4c4；
  不能据此宣称已验证 4.1.3 发布镜像。
- 本轮没有迁移或删除任何已有学员库、旧版实验表；新版下游需先运行新版上游 Lab。
  未验证 D04 的真实 Iceberg 接入及浏览器视觉效果。

## 2026-09-18：七份讲义的教学内容与课程 01 对齐

本轮完善讲义与测验，数据和 Lab 执行代码沿用下方 WWI 集成版本。
没有增加外部集成环境，不将文档完善视为那些实验已经交付。

### 内容验收

| 单元 | 本轮检查过的讲解与例子 |
| --- | --- |
| D01 | 统一安排表；新增按日期聚合 SQL、两日样本结果与粒度解释；总结补 FE/BE 与第一条查询 |
| D02 | SQL 查询流程、存储层次、写入与 Compaction、受控批次对照、计划/元数据/Profile 的证据区别 |
| D03 | 三次输入与三种模型的逐行输出；逻辑键选择；分区/分桶布局及三个过滤计划 |
| D04 | 文件/表/Catalog 对照、直查与导入选择、完整表名、关联放大与缺失、导入核对；真实环境前置条件保留 |
| D05 | 接入选择表、字段和粒度、CSV/Parquet 映射、请求/响应、重试、对象存储/Kafka/两类 CDC 路径及持续文件概念 |
| D06 | 当前/历史/投递三种粒度、乱序时间线、部分更新前后、删除可见性、中断恢复及独立业务对账 |
| D09-A | 类型与业务规则、十三行输入的去向、拒收回查 SQL、总量与逐行核对、错误注入与新鲜度边界 |

- 七份开头与单元安排采用相同格式；时间分项之和匹配预计时间。
- 每份五个学习目标、五条总结、五道测验逐项核对；题目不再考课程维护待办。
- 作者录制/环境待办保留在 integration-backlog.md；学员仍看到必要的实验限制。
- 官方参考资料按实际主题补齐。检查 29 个不同 Doris 官方入口，修正 TRY_CAST 地址，
  并把产品介绍的旧 meta-refresh 地址改为 getting-started 下的正文地址。

### 本轮验证

- 在干净 HEAD 导出副本叠加本轮材料后，31 项离线测试通过。新增检查覆盖信息表、
  时间安排、目标与测验映射、只读讲义 SQL、WWI 日期结果和模拟事件时间线。
  这些结构检查不代替上表的内容审阅。
- 使用 `scripts/run_labs.py` 在独立库 `dw_course_l1_readings_20260918` 完整执行六个核心 Lab，全部通过。
  复用现有 FE 19030 / BE HTTP 18040，构建版本仍为下方记录的开发构建；没有重启、重配集群。
- 从六份核心讲义的 SQL 代码块提取 24 条 SELECT/EXPLAIN/SHOW 并实际执行，全部通过。
  业务结果与明确预期比较，历史每日汇总另从源 Parquet 独立计算后比对；
  EXPLAIN 和元数据检查执行与返回内容，不断言固定采样版本数或性能倍数。
- 七份讲义通过 Jupyter/nbconvert Markdown 渲染器生成 HTML，检查表格列数、代码块和章节。
- 七套测验分别在全新 Python 内核中执行，并触发每题正确和错误答案的提交按钮：
  核对解释与最终 5/5、0/5 分数，合计 70 次提交。未保存 Notebook 输出。
- 七个 Lab 的代码单元字典与改动前逐项相同（含执行元数据）；只调整其中五个 Lab 的说明文字。
  课程 01 以及用户已有的 Quiz 1 执行记录未清空、未提交。

### 自查与未验证范围

- 目标与范围：覆盖七份讲义、七套测验及相关维护说明；没有改数据契约、运行工具或集群配置。
- 正确性：例子使用现有 WWI/模拟数据，明确粒度与金额；新的只读查询已与实验结果核对。
- 复用与一致性：沿用课程 01 的章节与共享测验渲染器；新增测试延续现有 unittest 风格。
- 测试与结果：离线、真实查询、内核交互和静态 HTML 分别验证，不用结构检查代替端到端证明。
- 并发、生命周期、持久化、FE/BE 参数传递及运行时性能：本轮无相关实现变更；
  实验只写上述独立验证库，不修改现有课程库。
- 未验证：D04 的三条示例查询和真实 Iceberg 接入、S3/Kafka/CDC/Group Commit 扩展实验、
  目标 Doris 4.1.3 发布镜像以及浏览器视觉效果。D04 示例名需替换成讲师提供的实际表名。

## 2026-09-18：Level 1 接入 WWI 与模拟新订单

当前材料以本节记录为准；下方 2026-09-17 内容是旧合成样本的历史验证记录。

- 七份讲义和七个 Lab 已调整数据来源、字段及验收口径，保留课程 01 的模块结构与中文呈现。
- D01–D03 使用 WWI 十单投影，税前金额 12220.60；D04 的候选湖表契约同步更新。
- D05 从本地 Parquet 导入 10 张历史表、701,846 行，核对主键、关联和金额；随后导入模拟新订单 CSV。
- D09-A 使用 WWI 客户维度校验模拟订单：13 行输入、10 行合格、3 行拒收。
- D06 引用同一批客户和商品，覆盖支付、发货、签收、取消、退款；11 笔当前订单、18 条历史、19 次投递。
  独立商品明细、支付、退款、配送流水用于关系与金额核对，支付 250.00、退款 150.00。
- 模拟来源标为 COURSE_SIMULATION，不将 WWI 客户账户收款伪造成逐订单支付。
- 六个核心 Lab 的实际代码单元在独立库 `dw_course_l1_wwi_course_20260918` 顺序运行通过。
  使用下方同一开发 FE/BE，未重启集群，未修改原演示库。
- 同一验证库完整重跑也通过，覆盖实验表重置和重新导入。
- 六个核心 Lab 均在新的 Jupyter 内核中通过，使用独立库 `dw_course_l1_wwi_kernel_20260918`。
  D09-A/D06 改为读取 D05 导入的完整客户、商品维度后，又分别在新内核中通过。
- 27 项离线检查在导出的 Git 暂存区快照上通过，包括历史子集金额/关联、模拟流水对账、
  Parquet 请求参数、缺失/被改写文件拒绝、Notebook 结构、链接和测验定义。
  工作目录只因用户已执行 Quiz 1 的 execution_count 不为空而不满足清洁性检查，未清空用户结果。
- 大文件只放本机忽略目录 `.runtime/wwi/`，与固定 manifest 校验和一致；没有上传桶或提交 Parquet。
- 未验证 D04 Iceberg、S3 TVF、真实 Kafka/CDC、Doris 4.1.3 发布镜像及浏览器视觉效果。
  D05 本地 Stream Load 不冒充最终课程 S3 路径。
- 用户已有的 Quiz 1 执行记录和课程 01 修改保留；不会为清洁性检查清空它们。

复用数据的来源、许可和准备方法见[学员数据说明](../../doris-course/02-data-warehousing/datasets/README.md)，
原始备份实测结果见 [WWI-VALIDATION.md](WWI-VALIDATION.md)。

## Earlier validation history

Date: 2026-09-17. Status: first Level 1 draft, not release-qualified.

## Chinese module structure alignment

Date: 2026-09-17.

- All seven Level 1 readings follow course 01's section order with Chinese
  headings: course information, module goal, learning objectives, module
  structure, topic sections, lab, module summary, quiz and official references.
- Each reading has topic-specific objectives, lab steps and references.
  Quiz links open the interactive notebook rather than the authoring YAML.
- Official reference pages were checked through web access on this date;
  version limitations remain explicit. Suggested lesson times are estimates,
  not measurements from a recorded or trial lesson.
- Removed unrelated ten-million-event claims from the six remaining lab covers,
  replacing them with their actual order-domain goals and environment limits.
- All seven lab code-cell dictionaries (source and execution metadata) were
  compared with HEAD and were unchanged. This was a materials-only revision;
  no new database execution or server restart was needed.
- All 23 offline tests passed on an exported Git index snapshot, including the
  new Chinese section-order check and existing local-link/notebook checks.
  Learner changes to course 01 and the executed course 02 quiz were preserved
  and excluded from the revision.
- Structure alignment does not complete the missing integration labs or bring
  all remaining teaching text to D01's depth; those follow-up tasks remain.

## Database execution

Six core notebooks were executed cell by cell through `maintenance/02-data-warehousing/scripts/run_labs.py`
against an existing, single-node integrated development cluster. The runner
executes the committed Python cells, not an alternate SQL implementation.
The complete core sequence passed twice against the same dedicated database,
including table reset and reinitialization on the second run.
All six core notebooks also passed a third run using real Jupyter kernels
through nbclient, starting each notebook in its own module directory.

- FE: `doris-0.0.0-ad8644154c3`.
- BE: `doris-0.0.0-8bafeb1e4c4`.
- The two components are development builds at different commits.
- Target recording release remains 4.1.3; these results do **not** qualify it.
- A dedicated `dw_course_l1_` database was used. No existing course/business
  tables were reset, and no cluster processes or global settings were changed.

Observed assertions:

| Lab | Evidence |
|---|---|
| D01 | Ten initial orders; order amount 1400.00 |
| D02 | Identical row totals for bulk and individual writes; Tablet metadata inspected |
| D03 | Duplicate/Unique/Aggregate row semantics; partition and bucket plan output |
| D05 | Ten-row Stream Load success; duplicate label rejection without added rows; bad batch rejected |
| D09-A | 12 raw, 10 valid, 2 rejected; full-row comparison; injected duplicate detected and repaired |
| D06 | 11 current orders, 16 historical events; out-of-order and repeat delivery; step-interruption recovery; partial update; isolated soft/SQL deletion |

D06 records one initial interrupted delivery and two seven-delivery attempts,
so the raw delivery table contains 15 rows. Business current/history results
remain unchanged. Paid GMV is 250.00 and refund amount 150.00.

## Validation methods and exclusions

Run offline checks with `python -m unittest discover -s maintenance/02-data-warehousing/tests -v`.
The initial delivery passed 11 tests; structure/presentation alignment passed
18 tests. The D01 learner-facing revision below passes 20 tests.
They validate fixtures against an independent replay calculation, clean notebook
structure and Python syntax, quiz definitions and shared renderer loading,
relative Markdown links, explicit write opt-in and scoped database names,
assertion failure, model DDL generation, and rejection of HTTP redirects.

Notebook outputs remain empty in git. Browser rendering, recorded videos,
Doris 4.1.3, Iceberg and the paths listed in
[integration-backlog.md](integration-backlog.md) are **not verified**.
The small correctness fixtures do not establish performance or resilience.

## Course 01 structure and presentation alignment

- Numbered reading/quiz filenames and single-node environment layout match the
  existing course conventions; Markdown and Notebook links are checked.
- Shared display functions are imported from course 01, not copied into a second
  CSS implementation. Column-name preservation is unit-tested.
- The six core labs passed another cell-runner pass and another real Jupyter
  kernel pass after alignment. Kernel output includes the shared HTML success
  cards and, where queries are displayed, the shared result-table markup.
- All seven quiz notebooks executed in fresh kernels and emitted widget-view
  output. Browser layout and user interaction were not visually inspected.
- Docker Compose configuration validation passed. The locally available pinned
  image contains the expected healthcheck. Startup ordering, explicit opt-in
  and project/port/volume scope were unit-tested with mocks.
- No new container was started or restarted; the new Compose startup path and
  macOS execution remain unverified. Existing-instance mode was used for SQL tests.

Local D01 execution metadata and quiz output were backed up under ignored
`.runtime/alignment-backup/` before editing. Notebook source changes and the
learner's added empty cell were retained; committed outputs remain cleared.

## D01 learner-facing revision

Date: 2026-09-17. This revision expands D01, not every Level 1 reading.

- Course and Level 1 entry pages now lead with prerequisites, learning order
  and links to readings, labs and quizzes. Implementation status is kept in
  maintenance documents, with necessary learner-facing limitations retained.
- D01 explains the order scenario, FE/BE responsibilities, data grain and
  metrics. The lab contains explicit CREATE TABLE and ten-row INSERT SQL,
  expected results, troubleshooting and a read-only filtering exercise.
- Initialization imports tools and styles without connecting. Connection and
  the optional Docker startup are separate, explicitly confirmed steps.
- Removed the unrelated ten-million-event claim from the notebook cover.
- The five quiz questions cover workload fit, result verification, FE/BE,
  order versus paid amount, and Duplicate Key replay behavior.

Validation:

- All 20 offline tests passed against an exported Git index snapshot. The
  working directory still contains the learner's executed Quiz 1 notebook:
  its execution count causes the clean-notebook check to fail there. It was
  neither cleared nor included in this revision. The unrelated course 01
  Untitled notebook was also left untouched.
- Two new tests verify that the visible D01 DDL/INSERT match the shared order
  contract and that initialization is separate from connection/startup.
- The updated D01 notebook passed twice in fresh Jupyter kernels, with its
  module directory as the working directory. SQL checked all ten records,
  1400.00 total order amount, zero paid/refund amounts, EAST=720.00,
  WEST=680.00, and four orders totaling 900.00 for the >=150.00 exercise.
- The D01 quiz executed in a fresh kernel and emitted interactive widget output.
- All six core labs passed the notebook-cell runner after this revision.
- SQL tests used the same development FE/BE builds recorded above and a new
  dedicated database, dw_course_l1_d01_learner_20260917. The learner's existing
  demonstration database and course 01 data were not changed.
- Notebook execution stayed in memory; no generated results were saved into
  course files. HTML result tables and success cards were checked in kernel
  output, but browser layout and interactive clicks were not visually tested.

The Docker lifecycle, target 4.1.3 release, macOS execution and D04 integration
remain unverified. No cluster process was started, stopped or reconfigured.

### Maintainer commands

From the repository root, with the course dependencies installed:

```bash
python -m unittest discover -s maintenance/02-data-warehousing/tests -v
# Configure DW_* and explicitly acknowledge owned-table resets first.
python maintenance/02-data-warehousing/scripts/run_labs.py
# Only when a real Iceberg table is configured:
python maintenance/02-data-warehousing/scripts/run_labs.py --iceberg
```

Use an independent test database. Do not clear a learner's notebook outputs
just to satisfy the clean-source check; validate the staged source separately.

## Learner directory cleanup

Date: 2026-09-17.

- Moved PR/status/backlog documents, the runner and offline tests to
  maintenance/02-data-warehousing at repository level. Updated relative links.
- The runner resolves the course from its own file location and executes each
  notebook from its module directory. It can now run from the repository root.
- All 22 offline tests passed against an exported index snapshot, including
  maintenance separation, link checks and generated-file hiding configuration.
- All six core labs passed using the moved runner and dedicated development
  database dw_course_l1_layout_check_20260917. No learner tables were changed.
- Restarted the localhost Jupyter server with the repository as its file root.
  Its authenticated contents API lists exactly datasets, dw_course,
  environments, level1, README.md, pyproject.toml and requirements.txt under
  course 02. The moved validation document is also accessible through the API.
- Generated installation metadata and caches remain on disk; they are hidden
  from Jupyter's file list. Existing learner notebooks were left unchanged.
- This verifies the file-list response, not a browser screenshot or new
  Docker/target-release qualification.
