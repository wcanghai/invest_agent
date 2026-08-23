# TDX 数据归档

该目录是独立的通达信只读采集模块，不依赖日报模块。默认数据库是 `data/tdx_archive.sqlite3`。

## 核心归档

```powershell
tdx-full-archive --limit 10
# 或
python -m tdx_data --limit 10
```

核心归档调用以下 TQ 接口：

- `get_stock_list`：股票列表；
- `get_market_data`：未复权日线；
- `get_stock_info`：股票基础资料和财务字段；
- `get_more_info`：扩展行情、估值、资金和事件字段；
- `get_relation`：行业、地域、概念和指数关系。

原始返回写入 `raw_api_records`，常用字典同时展开到 `stock_info_flat` 和 `more_info_flat`；日线和板块关系均使用复合主键保证增量运行幂等。

## 额外只读数据

`additional_data.py` 不写数据库，用来说明和调用核心归档尚未包含的接口：

| 数据集 | TQ 接口 | 额外数据 |
|---|---|---|
| `corporate_actions` | `get_divid_factors` | 分红、送股、配股、配股价和除权因子 |
| `market_snapshot` | `get_market_snapshot` | 单股实时或最近快照、盘口和可用完整字段 |
| `share_capital` | `get_gb_info` | 多观察日流通股本和总股本 |
| `financial_report_time` | `get_financial_data` | 按报告期组织的 Fn193–Fn200 财务字段 |
| `financial_announce_time` | `get_financial_data` | 按公告期组织的 Fn193–Fn200 财务字段 |
| `gp_trading` | `get_gpjy_value` | GP1–GP5 日期序列 |
| `gp_single` | `get_gp_one_data` | GO1–GO4、GO47 单点指标 |

```powershell
tdx-extra-data --sample-only
tdx-extra-data --code 600000.SH --dataset corporate_actions share_capital
```

`--sample-only` 输出接口说明和结构示意样例，不连接本机通达信。样例只展示典型返回形状，精确字段含义以本机 TQ 插件版本为准。
