# Design: 通达信股票全维度数据试采集
- 真实十股运行验证每个数据集的行数、字段数及错误信息。
- 真实十股运行验证每个数据集的行数、字段数及错误信息。
## Requirement Link

`docs/requirements/tdx-stock-complete-data.md`

## Current System

`tdx_history` 已有配置解析、TQ 会话、十年日线增量服务和 SQLite 日线表。新能力在同一包内扩展，不改变现有 `tdx-history` 命令。

## Proposed Architecture

```text
JSON 样本配置
    -> StockDataSource（只读 TQ 适配）
    -> StockDataSyncService（逐股票、逐数据集故障隔离）
    -> StockDataRepository（SQLite 幂等持久化）
    -> 控制台矩阵 + 本地 JSON 汇总
```

日线复用 `HistoryRepository` 的规则。其余接口通过明确的数据集方法获取，再由服务层转换为固定核心表或通用 JSON 记录。

## Data Model

- `instruments`、`daily_bars`、`sync_runs`：沿用现有日线 schema。
- `stock_sample_tags(code, sample_type)`：十只样本的板块/行业标签。
- `corporate_actions`：分红送配自然事件。
- `share_capital`：指定日期的总股本和流通股本。
- `financial_facts`：报告/公告时间、Fn 字段和值的长表。
- `stock_relations`：股票与指数、行业、地区、概念、风格的关系快照。
- `stock_dataset_records`：基础资料、市场快照、扩展指标、GP/GO 数据的 JSON 记录。
- `stock_dataset_fields`：数据集字段目录、推断类型及首次/最近观察时间。
- `stock_collection_runs`、`stock_collection_results`：运行和逐接口状态。

历史表使用数据自身日期作为自然键；快照使用 `(code, dataset, observed_date, record_key)`，因此一天重复运行会更新同一快照而不会无限复制。

## Interfaces

- CLI：`tdx-stock-data --config ... --database ... --years 10 --output ...`。
- 数据源：日线、分红、快照、基础资料、扩展指标、股本、财务、GP、GO、关系十类只读方法。
- 数据源返回 Python 基础对象或 DataFrame；序列化层统一处理 numpy/pandas/date 值。

## Security And Permissions

适配器不暴露账户和交易方法。数据库和汇总文件位于被 `.gitignore` 排除的 `data/`。

## Failure Modes

- 单数据集异常：写入失败结果并继续同一股票的其他数据集。
- 单股票异常：继续后续股票。
- 返回空对象：记为 `empty`，与 `failed` 区分。
- 日线首次为空：保持现有失败语义。
- 动态字段类型变化：JSON 保存原值，字段目录更新最近类型。

## Alternatives Considered

- 全部使用宽表：查询直观，但上百动态字段会造成频繁迁移，拒绝。
- 全部使用 EAV：灵活，但行数巨大、还原记录困难，拒绝。
- 混合固定核心表与 JSON：兼顾常用历史查询和完整原始字段，采用。

## Risks

- 财务返回结构需通过真实小样本确认；实现应接受 DataFrame、字典和列表。
- 股本接口要求升序日期列表，服务生成季度末观察日期。
- API 没有稳定 schema 版本，需保留字段目录和采集时间。

## Verification Strategy

- 假 TQ 数据源验证各接口调用参数和返回转换。
- 临时 SQLite 验证 schema、唯一性、快照覆盖和失败隔离。
- 真实十股运行验证每个数据集的行数、字段数及错误信息。
