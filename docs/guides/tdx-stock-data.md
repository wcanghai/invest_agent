# 指南：通达信十股全维度数据试采集

## 运行命令

启动并登录通达信后，在项目根目录运行：

```powershell
python -m tdx_history.stock_data
# 安装项目后也可使用：tdx-stock-data
```

默认配置为 `config/tdx_stock_samples.json`，数据库为
`data/tdx_stock_data.sqlite3`，字段汇总写入
`data/history/tdx_stock_data_summary.json`。数据库和汇总文件都只保存在本地。

可指定其他位置或截止日：

```powershell
tdx-stock-data `
  --config .\config\tdx_stock_samples.json `
  --database .\data\tdx_stock_data.sqlite3 `
  --output .\data\history\tdx_stock_data_summary.json `
  --years 10 `
  --as-of 2026-08-22
```

配置必须显式包含十只 `kind=stock` 股票，并为每只股票提供
`sample_type`。当前样本覆盖沪市主板、深市主板、创业板、科创板和北交所。

## 数据表

- `instruments`：证券代码、名称、类型和复权方式。
- `stock_sample_tags`：试验样本类型。
- `daily_bars`：不复权日线，主键为代码和交易日。
- `corporate_actions`：分红、送股、配股等公司行为。
- `share_capital`：季度观察日的流通股本和总股本。
- `financial_facts`：按报告时间、公告时间保存的 Fn 财务长表。
- `stock_relations`：行业、地区、概念、风格和指数等关系快照。
- `stock_dataset_records`：行情快照、基础资料、扩展指标、GP/GO 数据 JSON。
- `stock_dataset_fields`：实际观测到的字段目录。
- `stock_collection_runs`、`stock_collection_results`：运行及逐接口结果。

字段变化较大的接口保存 JSON，可以使用 SQLite JSON1 查询，例如：

```sql
SELECT
    code,
    json_extract(payload_json, '$.DynaPE') AS pe,
    json_extract(payload_json, '$.PB_MRQ') AS pb
FROM stock_dataset_records
WHERE dataset = 'more_info'
  AND observed_date = '2026-08-22';
```

## 增量和时间口径

- 日线只从库中最新交易日的下一天追加，并使用 `fill_data=False`。
- 周末运行时，日线截止到最近已完成工作日；快照仍记录实际采集日期。
- 公司行为和财务事实通过自然键幂等更新。
- 当前快照一天保存一个版本，重复运行会覆盖当日同数据集记录。
- 板块关系是采集日当前快照，不代表历史成分。
- 财务同时保存 `report_time` 和 `announce_time` 两个口径。

## 本次验证结果

2026-08-22 对十只股票实际调用 11 类数据集，共 110 个结果：109 个成功，
1 个为空，0 个失败。唯一空数据为中芯国际的分红送配接口，表示该接口在本次十年区间
未返回记录，不是程序异常。

数据库内共有 18,830 条不复权日线，最晚交易日为 2026-08-21。上市不足十年的股票
从实际上市日起保存。

已验证字段组：

- 日线：交易日、开高低收、成交量、成交额。
- 分红送配：日期、类型、现金分红、配股价、送股数、配股数。
- 市场快照：26 个字段，含最新价、昨收、开高低、成交、内外盘及五档盘口。
- 股票基础资料：63 个字段，含交易参数、上市/ST状态、通道资格、行业地区及最新财务摘要。
- 扩展信息：88 个字段，含估值、市值、收益、资金、事件日期、股本和部分基本面。
- 股本：日期、流通股本、总股本。
- 专业财务：FN193-FN200，以及报告/公告时间标签。
- GP 交易序列：日期、GP1-GP5，已由嵌套返回结构拆成按日期记录。
- GO 单值：GO1、GO2、GO3、GO4、GO47。
- 股票关系：板块代码、名称、类型和成分数量。

没有采集账户、持仓、委托、下单、撤单、用户自定义板块写操作、通达信公式结果及
非股票维度的市场/板块公共序列。
