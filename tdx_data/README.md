# TDX 数据归档

该目录是独立的通达信只读采集模块，不依赖日报模块。默认数据库是 `data/tdx_archive.sqlite3`。

## 核心归档

```powershell
tdx-full-archive --limit 10
# 或
python -m tdx_data --limit 10
```

定向归档沪深300、中证500成分股，以及按最近交易日成交额排序的前 120 只
高流动性 ETF：

```powershell
tdx-full-archive --target-universe --etf-limit 120 --limit 0
```

指数成分清单来自中证指数公开接口，ETF 清单和成交额来自东方财富；清单确定后，
日线、基础资料、扩展字段和板块关系均由本机 TQ 接口采集。`asset_groups` 表保存每只
证券的集合归属和 ETF 流动性排名，任务可中断后使用同一命令增量续跑。

核心归档调用以下 TQ 接口：

- `get_stock_list`：股票列表；
- `get_market_data`：未复权日线；
- `get_stock_info`：股票基础资料和财务字段；
- `get_more_info`：扩展行情、估值、资金和事件字段；
- `get_relation`：行业、地域、概念和指数关系；
- `get_market_snapshot`：每日市场和盘口快照；
- `get_financial_data(report_type='announce_time')`：带报告期、公告日的历史财务记录；
- `get_gb_info_by_date`：历史每日股本；
- `get_divid_factors`：分红送配和除权记录；
- `get_gpjy_value`、`get_gp_one_data`：交易扩展序列和单点动态字段。

原始返回写入 `raw_api_records`，常用字典同时展开到 `stock_info_flat` 和 `more_info_flat`；日线和板块关系均使用复合主键保证增量运行幂等。首次启用扩展归档会回溯历史数据，耗时明显长于后续每日增量。

## 每日增量

完成一次 `--target-universe` 初始化后，每天直接复用数据库中的标的清单：

```powershell
tdx-daily-update
# 调试前 10 只，不采集扩展数据
tdx-daily-update --limit 10 --skip-extended-data
# 长任务中断后，从指定代码的下一只标的继续
tdx-daily-update --start-after 513350.SH
```

每日命令会为所有证券固定同一个快照日期。日线从最后交易日后一日续传；财务、股本和公司行为从各自最后业务日期向前回看 31 天，以吸收源端修订并依靠复合主键幂等更新。可使用 Windows 任务计划程序在收盘后调用该命令；项目不自动创建系统计划任务。

公司财务历史仅适用于股票。归入“高流动性ETF”的标的不调用 `get_financial_data`，但仍采集日线、基础/扩展快照、历史份额和分配记录，避免将基金数据错误解释为公司财报。

建议每月另行运行一次 `tdx-full-archive --target-universe --etf-limit 120 --limit 0`，刷新指数成分和 ETF 清单；每日任务只使用数据库中当前清单，不访问外部指数接口。

新增的结构化历史表：

| 表 | 用途 | 唯一键 |
|---|---|---|
| `financial_reports` | 财报原始字段、报告期和公告日 | 代码 + 报告期 + 公告日 |
| `financial_report_values` | 每版财报的结构化字段明细，支持未来增加 Fn 字段 | 财报版本 + 字段名 |
| `share_capital_history` | 每日流通股本、总股本 | 代码 + 生效日 |
| `corporate_actions` | 结构化分红、送股、配股、配股价及完整原文 | 代码 + 行为日 + 行为键 |
| `asset_group_history` | 指数/ETF 集合归属历史 | 代码 + 集合 + 观察日 |

财务数据同时保存两层：

- `financial_reports.payload_json` 保存接口完整原文，便于审计和重新解释字段；
- `financial_report_values` 把每个返回字段保存为数值或文本，新增 Fn 字段时无需修改表结构。

## 历史数据使用

`history_service.py` 负责把价格、财报和股本按真实可知时间连接起来。给定交易日时，只允许使用 `announce_date <= trade_date` 的财报，并从中选择报告期最新、同报告期公告版本最新的数据。

```python
from datetime import date
from pathlib import Path

from tdx_data import calculate_historical_pb, historical_metric_inputs
from tdx_data.repository import open_database

connection = open_database(Path("data/tdx_archive.sqlite3"))
try:
    inputs = historical_metric_inputs(
        connection,
        "600000.SH",
        date(2020, 1, 1),
        date(2020, 12, 31),
    )

    # 只有在 FN196 已经通过原始财报验证后才显式指定它。
    pb_series = calculate_historical_pb(
        connection,
        "600000.SH",
        date(2020, 1, 1),
        date(2020, 12, 31),
        book_value_per_share_field="FN196",
    )
finally:
    connection.close()
```

`historical_metric_inputs` 每个交易日返回：收盘价、报告期、公告日、该版财报的全部字段、股本生效日、流通股本和总股本。后续可以在这一统一输入上计算市值、PB、每股指标和其他财务比率。

## 量化日频宽表

完成归档后，可以将当前全部标的物化到 `quant_daily_wide`：

```powershell
# 当前 920 个标的的完整历史
tdx-build-quant-wide

# 指定股票/ETF和日期区间；先删除目标区间再重建
tdx-build-quant-wide --code 600000.SH 300750.SZ 510300.SH `
    --start 2020-01-01 --end 2026-08-24 --rebuild
```

每行由 `code + trade_date` 唯一标识，包含：

- OHLCV、成交额、复权因子、过去 1/5/20 日收益、日内收益、振幅和移动均值；
- 当日已经公告的最新财报版本、FN193–FN200 和公告时效；
- 当日有效股本、按收盘价计算的总/流通市值输入；
- 当日分红送配事件和距最近公司行为天数；
- 实际采集快照中的 PE、PB、股息率、换手率、Beta、市值、主要财务值、行业、ST/融资融券/互联互通资格和重要事件日期。

扩展快照按其内部 `HqDate` 对齐交易日，同时保留真实 `snapshot_date`。例如午夜后采集的 8 月 25 日快照若内部行情日为 8 月 24 日，只连接到 8 月 24 日，不会回填到更早日期。ETF 保留行情、份额和分配事件，财报字段为空。

宽表不包含未来收益标签，也不把当前指数成分关系回填到历史。因子研究应在宽表基础上单独构造预测标签和时间切分。

## 历史财务指标可行性

本机接口实测可以返回 2004 年以来的财务记录，每行同时包含 `tag_time`（报告期）和 `announce_time`（公告日）。这允许后续按公告日向后匹配交易日，避免用尚未公告的数据计算历史指标。股本和公司行为也可以回溯。

但 TQ 的 `get_market_data` 实测不能直接返回历史 `PB_MRQ`、PE、股息率或市值。理论上历史 PB 可按“当日未复权收盘价 ÷ 当时最新已公告的每股净资产”计算；当前插件文档虽将 `Fn196` 描述为每股净资产，实际样本却出现长期为 0 的异常值。因此 PB 接口要求调用方显式传入已经验证的每股净资产字段，程序不会默认信任 Fn196。应先用多只股票和原始财报交叉校验 Fn193-Fn200 的口径。

## 额外只读数据

`additional_data.py` 仍不写数据库，用来脱离归档流程单独查看接口说明、样例和真实返回：

| 数据集 | TQ 接口 | 额外数据 |
|---|---|---|
| `corporate_actions` | `get_divid_factors` | 分红、送股、配股、配股价和除权因子 |
| `market_snapshot` | `get_market_snapshot` | 单股实时或最近快照、盘口和可用完整字段 |
| `share_capital` | `get_gb_info` | 指定观察日的流通股本和总股本；归档主流程使用 `get_gb_info_by_date` |
| `financial_report_time` | `get_financial_data` | 按报告期组织的 Fn193–Fn200 财务字段 |
| `financial_announce_time` | `get_financial_data` | 按公告期组织的 Fn193–Fn200 财务字段 |
| `gp_trading` | `get_gpjy_value` | GP1–GP5 日期序列 |
| `gp_single` | `get_gp_one_data` | GO1–GO4、GO47 单点指标 |

```powershell
tdx-extra-data --sample-only
tdx-extra-data --code 600000.SH --dataset corporate_actions share_capital
```

`--sample-only` 输出接口说明和结构示意样例，不连接本机通达信。样例只展示典型返回形状，精确字段含义以本机 TQ 插件版本和交叉验证结果为准。
