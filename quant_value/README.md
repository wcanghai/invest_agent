# 通达信量化价值研究

`quant_value` 是仓库第三个独立业务域。它直接从通达信 TQ 获取一个可控研究池的
行情、专业财务、股本、公司行动、基础资料、板块关系和 ETF 快照，并生成
`factor_daily` 日频宽表。它不依赖 `tdx_data` 的 3GB 全量归档库。

## 数据接口

| 数据 | TDX 接口 | 用途 |
|---|---|---|
| 股票/ETF/指数日线 | `get_market_data` | 收益、动量、波动、回撤、流动性 |
| 历史专业财务 | `get_financial_data` | 估值、盈利质量、成长、偿债和现金流 |
| 历史股本 | `get_gb_info_by_date` | 历史市值和每股口径校验 |
| 分红送配 | `get_divid_factors` | 股息率、公司行动和复权研究 |
| 基础/更多/行情快照 | `get_stock_info`、`get_more_info`、`get_market_snapshot` | 当日状态与原始证据 |
| 股票板块 | `get_relation` | 行业、地域、概念暴露 |
| 指数跟踪 ETF | `get_trackzs_etf_info` | 当日 IOPV、份额、规模和折溢价 |

财报必须先在通达信客户端下载专业财务数据。程序请求 `FN1` 至 `FN337` 中与价值
研究直接相关的 78 个字段；完整中文名和单位见 `fields.py`。

## 时点一致

每个交易日只使用 `announce_date <= trade_date` 且报告期最新的财报。修订财报从
修订公告日起生效；每日快照和 IOPV 只用于采集当天，不会回填历史。因此历史 PB、
PE、PS、ROE 等可用于回测，不会把今天才知道的数据放进过去。

## 股票与 ETF 因子

- 股票：PB、PE TTM、PS TTM、盈利收益率、FCFF/FCFE 收益率、股息率、ROE、
  ROIC、毛利率、净利率、现金转化、周转率、杠杆、偿债和成长率。
- ETF：收益、动量、波动、回撤、成交额、当日 IOPV 折溢价、相对基准收益、
  跟踪差和跟踪误差。

债券、商品和跨境 ETF 在已验证 TDX 接口中没有稳定的基准映射；程序仍可计算
价格风险和流动性，但会将跟踪指标留空并解释原因。ETF 历史 IOPV、费率和完整
持仓也不会伪造，需以后接入交易所或基金公司数据。

## 命令

```powershell
quant-value init
quant-value sync --start 2016-01-01 --end 2026-08-25
quant-value build --rebuild
quant-value verify
```

默认数据库是 `data/quant_value.sqlite3`，已被 Git 忽略。日常任务只需执行
`quant-value sync`（自动从最后交易日重叠 7 天增量获取），随后执行
`quant-value build` 和 `quant-value verify`。

## 价值分析

在完成 `build` 后，可对股票运行时点一致的价值初筛：

```powershell
quant-value --database data/quant_value_hs300_csi500_etf.sqlite3 analyze --as-of 2026-08-26 --code 600519.SH --code 000333.SZ --code 300750.SZ
```

`analyze` 输出估值、盈利质量、成长、安全性、股东回报五维分数、综合结论和风险。
估值结合股票自身近五年历史分位；质量、成长和资产负债使用截至价格日已经公告的
最近年报，从而避免未来数据泄漏和季度/年度口径混比。添加 `--format json` 可获得
含原始证据的机器可读结果；`--history-years` 可调整历史估值窗口。

该评分用于缩小需要人工研究的范围，不包含行业相对估值、管理层和护城河定性、
盈利预测或 DCF 假设，不构成投资建议。ETF 不适用股票模型，应独立分析基准暴露、
费率、跟踪误差、流动性和折溢价。

## 代表性验证池

- 股票：贵州茅台、招商银行、美的集团、宁德时代、中国平安，覆盖消费、银行、
  制造、成长新能源和保险。
- ETF：沪深300、中证500、创业板、证券、国债、黄金、纳指 ETF，覆盖宽基、行业、
  债券、商品和跨境类型。

## 首批三只股票样本

`pilot_stock_universe.json` 固定贵州茅台、美的集团、宁德时代，分别代表稳定高盈利、
成熟制造现金流和成长制造。它用于先验证通用股票因子，不包含需要银行/保险专用
指标体系的金融股。

```powershell
quant-value --database data/quant_value_hs300_csi500_etf.sqlite3 --universe quant_value/pilot_stock_universe.json build --rebuild
quant-value --database data/quant_value_hs300_csi500_etf.sqlite3 --universe quant_value/pilot_stock_universe.json verify --code 600519.SH --code 000333.SZ --code 300750.SZ
```

股票只有同时具备行情、历史财报、财务字段、历史股本、当日快照、关系数据，因子行数
与行情一致，且 12 个关键估值/质量/成长因子的完整行覆盖率不低于 90%，才会被
`verify` 判定为“通过”。公司行动允许为零，因为未分红本身是合法事实。
