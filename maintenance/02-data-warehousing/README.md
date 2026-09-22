# Data Warehousing 课程维护

学员入口：[课程首页](../../doris-course/02-data-warehousing/README.md)。
本目录只供课程作者和评审者使用，不是学员的学习步骤。

## 讲义结构约定

沿用课程 01 的章节顺序，先制作中文版本：课程信息表、单元目标、
学习目标、单元安排、分节讲解、动手实验（含数据说明）、单元总结、
知识测验、官方参考资料。课程单元按学习顺序连续编号，数据集围绕数仓业务组织。

测验链接指向可交互的 ipynb，YAML 只作为题库源文件。
官方参考资料按本单元主题选择；版本限制和未完成实验需保留明确说明。
正文按业务问题、概念、示例与结果解释组织，不以“观察与练习”或录制待办代替讲解。
分节标题保留简洁的功能名称，例如 Streaming Job 与 CDC_STREAM；业务场景、术语含义和工作过程放在正文讲清楚。
学员材料保留实验前置条件、操作风险与功能成熟度；制作状态和测试记录集中在本目录。
Level 1 的 Iceberg Lab 已实测；三份基础扩展覆盖文件查询、Group Commit 等操作，新增 Lab 5A / 5B 覆盖 Kafka 与 MySQL/Flink CDC 的选做链路。Streaming Job / CDC_STREAM 和持续文件仍仅介绍。具体实测边界见 VALIDATION.md。
七份讲义的学习目标与五道测验逐项对应，单元总结回扣相同目标；题目定义中的
objective 保存对应的学习目标原文，离线测试检查覆盖关系。
教学时间是包含讲义、实验和测验的估计，不含环境准备，仍需试讲校准。
讲义完善不代表外部集成实验或目标发布版本已经验证；实际范围见验证记录。

| 文件或目录 | 用途 |
| --- | --- |
| [VALIDATION.md](VALIDATION.md) | 实际验证结果与未验证范围 |
| [WWI-VALIDATION.md](WWI-VALIDATION.md) | 候选 WWI 数据集的实际导入结果与业务缺口 |
| [integration-backlog.md](integration-backlog.md) | 已覆盖范围及未验证边界 |
| [PR_DRAFT.md](PR_DRAFT.md) | PR 说明草稿 |
| scripts/run_labs.py | 执行主线与三份基础扩展的代码单元 |
| scripts/run_streaming_labs.py | 显式选择 Kafka / CDC 选做 Lab，固定独立库 dw_course_l1_streaming |
| scripts/prepare_wwi.py | 校验并暂存本地 WWI Parquet 包，不上传 |
| tests/test_course.py | 离线检查材料、数据与辅助工具 |

安装课程依赖后，从仓库根目录执行：

```bash
.venv/bin/python -m unittest discover -s maintenance/02-data-warehousing/tests -v
# 使用课程单容器沙箱；先选择独立测试库并确认实验表重置范围。
export DW_DATABASE=dw_course_l1_validation
export DW_ALLOW_WRITES=yes
.venv/bin/python maintenance/02-data-warehousing/scripts/run_labs.py
# 加入本地湖表实验，并执行所有折叠参考答案：
.venv/bin/python maintenance/02-data-warehousing/scripts/run_labs.py --iceberg --solutions
# 单独选做持续接入；先读 environments/streaming/README.md，使用固定独立实验库：
.venv/bin/python maintenance/02-data-warehousing/scripts/run_streaming_labs.py all
```

如果 Python 环境安装在课程目录，将上面的 .venv/bin/python 换成对应路径。
测试检查待提交 Notebook 不带执行输出；不要为通过检查清空学员的本地记录，
可导出 Git 暂存区到临时目录后验证。

## 编号迁移记录（2026-09-18）

学员材料采用连续编号：Level 1 为 D01–D07，Level 2 为 D08–D11，
Level 3 为 D12–D13。视频、Lab 和 Quiz 随所属单元编号；课程内容与学习顺序保持不变。
此前验证记录中的编号保留原样，查阅时按下表对应。

| 原编号 | 当前编号 | 内容 |
| --- | --- | --- |
| D09-A | D06 | 数据质量与 Schema 校验；视频 D06-01～03 |
| D06 | D07 | 更新、删除与事件重放 |
| D07 | D08 | 视图与物化视图 |
| D08 | D09 | 数仓建模与 Join |
| D12 | D11 | BI 与 AI 应用 |
| D09-B | D12 | 发布、权限与审计；原视频 D09-04～08 改为 D12-01～05 |
| D11 | D13 | 存储与生命周期管理 |

D01–D05、D10 编号保持不变。Level 1 的两个目录已改为
`module06-data-quality` 和 `module07-state-changes`，对应讲义、Lab、Quiz 文件同步更名。
Jupyter 中打开旧路径的标签页需关闭，再从课程目录进入新路径。

## Jupyter 浏览入口

从仓库根目录启动，01 和 02 使用同一个界面：

```bash
.venv/bin/jupyter lab --config=maintenance/jupyter_lab_config.py --ServerApp.port=18890 --ServerApp.port_retries=0
```

配置以仓库为文件根目录，默认打开 doris-course，确保维护资料的相对链接也可访问。
安装元数据、Python 缓存和 Jupyter 检查点只从文件列表隐藏，不删除；
仍保留默认认证机制。学员无需预设连接地址；各 Lab 固定连接课程单容器沙箱。
主线多人使用时，可在启动前用 DW_DATABASE 分配独立实验库；Lab 5A / 5B 使用固定的课程服务和独立库，不能在同一沙箱并发执行。


## Publishing course datasets

Payloads live in an S3-compatible bucket; Git retains `datasets/catalog.json`,
the WWI schema manifest, and license. To publish a validated local release:

```bash
.venv/bin/python maintenance/02-data-warehousing/scripts/publish_datasets.py \
  --source /absolute/path/to/dw-v1 \
  --bucket doris-regression-hk \
  --prefix regression/datalake/pipeline_data/doris-course/data-warehousing/v1 \
  --endpoint https://oss-cn-hongkong.aliyuncs.com --region cn-hongkong
```

Add `--endpoint` for MinIO or another S3-compatible service. The script uses the
standard boto3 credential chain for publication; keep write credentials outside
Git and outside learner notebooks. Include the WWI MIT license and schema
manifest when distributing the source package. After verifying publication,
update the catalog source and distribute read-only credentials separately.
Data-contract tests require a populated cache or access to the configured bucket;
`test_datasets.py` uses mocked downloads and runs offline.
