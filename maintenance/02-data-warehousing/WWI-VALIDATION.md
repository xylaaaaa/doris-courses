# WWI 数据集可用性验证

2026-09-18，本地实测；未上传对象存储，未替换正式课程数据。

这是选型验证时的记录。后续 Level 1 已接入这些历史数据和独立模拟事件，
当前课程验收见 [VALIDATION.md](VALIDATION.md)；原始 WWI 的支付、退款边界没有因此改变。

## 结论

WWI 可以作为销售、履约、客户账款数仓的教学数据源。10 张表共 701,846 行，
已完成 SQL Server 恢复、指定字段导出 Parquet、Doris 导入和跨库一致性校验。
Parquet 总计 16,938,378 字节（约 16.2 MiB），适合入门实验。

但它不是完整的电商支付、退款、订单状态流水：

- 26,637 条收款记录的 `InvoiceID` 全部为空，不能直接分摊为每笔订单的支付金额。
- 这份备份实际只有发票和收款两种客户交易，贷项发票为零；字典中存在某种类型不代表有对应业务样本。
- 配送 JSON 有备货、配送尝试事件及签收结果，但不能据此声称有完整快递轨迹或订单状态历史。
- 尚未执行 CDC、退款、乱序重放实验；这部分需要另外设计并标注模拟数据。

因此，批量接入、多表分析、分层建模和账款核对可以继续使用它试作；
如果课程必须围绕订单逐笔支付及退款展开，仍需补充数据，不能直接定稿为完整业务底座。

## 实际数据规模

本次对以下表保留全部行、选择课程相关字段；不是全部 WWI 表或全部字段。
字段白名单、源端 SQL 和目标 DDL 见 [验证脚本](scripts/wwi_probe.py)，生成的 manifest 记录完整清单。

| 文件 | 行数 | 业务用途 |
| --- | ---: | --- |
| orders.parquet | 73,595 | 订单，日期 2013-01-01 至 2016-05-31 |
| order_lines.parquet | 231,412 | 订单明细 |
| customers.parquet | 663 | 客户及开票账户关系 |
| products.parquet | 227 | 商品 |
| invoices.parquet | 70,510 | 发票及配送信息 |
| invoice_lines.parquet | 228,265 | 发票明细 |
| customer_transactions.parquet | 97,147 | 发票记账 70,510 条、收款 26,637 条 |
| payment_methods.parquet | 4 | 付款方式字典，实际收款样本仅 EFT |
| transaction_types.parquet | 13 | 交易类型字典 |
| delivery_methods.parquet | 10 | 配送方式字典 |

## 通过的检查

- 10 张表均通过 Stream Load 导入，严格模式、错误行容忍比例为零；每张表过滤行数为零。
- 将源端和 Doris 按主键排序后，对全部导出字段逐行计算摘要，10 张表摘要和行数一致。
  时间字段在导出 SQL 中明确截断到微秒，比较基准是转换后的源端值，不宣称保留 SQL Server 的第七位小数。
- 10 张表的主键均无重复；检查的 10 条关联关系均无悬空引用。
- 日粒度订单分析同时关联订单、明细、客户、商品，两端得到相同的 1,069 行日报结果。
- 订单明细数量合计 9,310,904，`Quantity * UnitPrice` 合计 177,634,276.40，两端一致。
- 发票明细 `ExtendedPrice` 合计 198,043,439.45、税额 25,782,098.25，两端一致。
- 客户收款记账合计 -197,776,428.01；与发票记账净额为 267,011.44，等于未结余额合计。
  逐客户检查也一致。负数是这份数据的收款记账方向，不能直接解释为退款。
- 发票记账的客户关联到 `Invoices.BillToCustomerID`，不是默认按订单客户分摊收款。

业务覆盖检查还发现：3,085 张订单尚未完成拣货且没有发票；7,538 张订单引用了补货订单；
70,510 张发票均有配送 JSON，其中 70,426 张已确认送达。
JSON 内共 70,510 个 `Ready for collection` 和 70,426 个 `DeliveryAttempt` 事件。
这些是真实读取样例备份得到的结果，不是人为补造的记录。

## 环境、证据与复现

原始数据：[微软 WWI v1.0 官方发布](https://github.com/microsoft/sql-server-samples/releases/tag/wide-world-importers-v1.0)，
文件 `WideWorldImporters-Full.bak`，127,111,168 字节。
SHA-256：`e842bad6ce02f74f166947e559dab1b476edd7eaae3da2ab9e3f522f1dd87124`。
发布来源及转换后分发须保留 [Microsoft MIT 许可](https://github.com/microsoft/sql-server-samples/blob/master/license.txt)。

测试使用独立容器 `course02-wwi-validation-20260918`，本机随机映射端口，限 2 CPU / 4 GiB。
复用已有测试镜像 `doristhirdpartydocker/mssql-server:2022-latest`，实际为 SQL Server 2022 CU5
Developer 16.0.4045.3；这不是学员依赖，也没有操作已有 SQL Server 容器。
测试完成后停掉该容器，保留恢复的数据供复查。

Doris 使用现有本地开发集群，独立库 `dw_course_l1_wwi_probe_20260918`：
FE `doris-0.0.0-ad8644154c3`（19030），BE `doris-0.0.0-8bafeb1e4c4`（HTTP 18040）。
不是目标 4.1.3 发布镜像的兼容性验收，也不是性能测试。目标表暂用单副本、2 桶 Duplicate Key，
用途是保真导入，不代表最终数仓表设计。

本机生成文件保留在 `/mnt/disk1/chenjunwei/doris_build/wwi-validation-itiJM02K/`：

- `wwi.bak`、`MICROSOFT-MIT-LICENSE.txt`：下载原件。
- 10 个 Parquet：待评估的课程文件，不上传、不提交 Git。
- `manifest.json`：字段、类型、源 SQL、DDL、行数、文件校验和。
- `load-results.json`：导入返回结果及源端/Doris 的全字段摘要。
- `profile-results.json`：业务检查 SQL 与实际结果。
- `venv/`：隔离的作者验证依赖，不改变 Jupyter 或学员环境。

脚本不创建容器，不上传文件，不删除表。需要先准备独立 SQL Server 容器，
绑定本机端口并设置随机 `MSSQL_SA_PASSWORD`，将官方备份下载为产物目录的 `wwi.bak`。
安装 [验证依赖](scripts/requirements-wwi-probe.txt) 后，依次运行：

```bash
# 在 doris-courses 仓库根目录；使用隔离环境的 Python。
python maintenance/02-data-warehousing/scripts/wwi_probe.py restore \
  --artifacts /path/to/artifacts --container course02-wwi-validation-YOUR_RUN
python maintenance/02-data-warehousing/scripts/wwi_probe.py export \
  --artifacts /path/to/artifacts --container course02-wwi-validation-YOUR_RUN
python maintenance/02-data-warehousing/scripts/wwi_probe.py load \
  --artifacts /path/to/artifacts --container course02-wwi-validation-YOUR_RUN \
  --database dw_course_l1_wwi_probe_your_run --doris-port 19030 --be-http 18040
python maintenance/02-data-warehousing/scripts/wwi_probe.py profile \
  --artifacts /path/to/artifacts --container course02-wwi-validation-YOUR_RUN \
  --database dw_course_l1_wwi_probe_your_run --doris-port 19030
```

restore 和 load 分别要求源库、目标库不存在，重复执行会报错而不是清空或追加。
连接仅限本地测试环境，Doris 密码可通过 `DW_PASSWORD` 提供，不把凭证写入产物。
当前容器恢复启动后可直接运行 profile 复查，不要重新运行 restore 或 load。

本轮未验证：S3 TVF 路径、对象存储凭证、Iceberg、Kafka/CDC、版本重放和课程 Notebook 改造。
本地使用 Stream Load 只是验证同一批 Parquet 的可读性与数据质量；最终沿用 01 的
`S3() + INSERT INTO SELECT` 路径仍需独立验收。
