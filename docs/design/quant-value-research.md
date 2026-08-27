# Design: 通达信量化价值研究数据域

## Requirement Link

`docs/requirements/quant-value-research.md`

## Current System

- `daily_report`：日报采集、存储、渲染和 Web。
- `tdx_data`：大范围原始归档和通用量化宽表。
- 新域不读取上述两个数据库，避免研究口径与归档/展示口径隐式耦合。

## Proposed Architecture

```text
TDX TQ -> gateway.py -> service.py -> repository.py -> quant_value.sqlite3
                                |                         |
                                +-> 原始/规范化数据       +-> factors.py -> factor_daily
config.py -> representative_universe.json                +-> verify.py
                                                          +-> analysis.py
cli.py ---------------------------------------------------------------^
```

- `gateway.py`：只读 TQ 适配器，返回 Python 记录，不持久化。
- `repository.py`：schema、幂等 upsert、查询和运行审计。
- `service.py`：全量/增量采集编排，按资产类型选择接口。
- `factors.py`：仅从数据库构造时点一致股票/ETF 因子。
- `verify.py`：覆盖率和可计算性检查。
- `analysis.py`：只读因子与财报事实，生成可解释的价值分析快照，不保存投资结论。

## Data Model

- `instruments`：证券主数据及 ETF 基准映射。
- `market_bars`：证券和基准指数日线，主键 `(code, trade_date)`。
- `financial_reports` / `financial_values`：按报告期和公告日保存财报原始记录与
  FN 长表，允许同一报告期后续修订。
- `share_capital`：按生效日保存流通/总股本。
- `corporate_actions`：分红送配和除权事件。
- `daily_snapshots`：基础资料、更多资料和行情快照的按日原始数据。
- `relations`：股票行业、地域、概念和指数关系的按日快照。
- `etf_snapshots`：IOPV、份额、规模和当时折溢价。
- `factor_daily`：研究宽表；主键 `(code, trade_date)`。
- `sync_runs`：运行状态、数量和错误摘要。

## Point-in-time Rules

1. 财报：最大 `announce_date <= trade_date`，再按最新 `report_date` 取一份。
2. 股本：最大 `effective_date <= trade_date`。
3. 公司行动：只在事件日及向后天数窗口中使用。
4. 快照/IOPV：只落在 `observed_date`，绝不回填更早日期。
5. ETF 基准收益仅在 ETF 与基准都有同日收盘价时计算。

## Factor Contracts

股票公共价格因子包括收益率、均线、波动率、回撤和成交额均值。股票财务因子包括：

- 估值：`PB = close/FN4`、`PE_TTM = 市值/FN308`、`PS_TTM = 市值/FN319`、
  `FCF_yield = FN322/close`、股息率（滚动现金分红/市值）。
- 质量：ROE、ROIC、毛利率、净利率、经营现金/净利润、资产周转率。
- 安全：资产负债率、流动/速动比率、利息保障倍数、有息负债率。
- 成长：营业收入、净利润、净资产同比增长率。

ETF 因子包括价格风险、成交额、IOPV 折溢价、相对基准 20 日收益和 60 日年化
跟踪误差；股票财务列保持 `NULL`。

## Value Analysis Contract

股票价值分析分为五个维度，综合权重依次为估值 30%、盈利质量 25%、成长 15%、
安全性 20%、股东回报 10%。各维度只在实际可用指标间重新归一权重，缺失数据不会
被当作零分，但会在结果中保留数据提示。

- 估值：当前 PE/PB/PS 在自身近五年日频历史中的分位，以及盈利收益率、股息率。
- 盈利质量：最近已公告年报的 ROE、ROIC、净利率、现金转化率和近五年 ROE 正值率。
- 成长：最近已公告年报的营收、净利润和净资产同比增长。
- 安全性：年报资产负债率、流动比率、审计意见以及 60 日波动和 252 日回撤。
- 股东回报：滚动现金股息率和最近年报股利支付率。

价格、TTM 估值取不晚于分析日的最新 `factor_daily`；质量、成长和资产负债指标
使用 `announce_date <= price_date` 的最近年报。采用年报是为了避免把季度 ROE/ROIC
与全年指标直接比较。缺失年报及严重/无法确认的审计意见属于关键风险门槛。结论只
用于研究初筛，不是买卖建议；跨行业比较、管理层/护城河定性、DCF 假设和预测数据
不在当前自动评分范围内。

FN336 按[通达信官方枚举](https://help.tdx.com.cn/quant/docs/markdown/TdxQuant.md/mindoc-1h10m001ic888.html)
解释：0 未审计、1 无保留、2 带强调事项段的无保留、3 保留、4 无法表示、5 否定及
其他。代码 2 降低安全性并提示人工核查；0、3、4、5 触发关键审计风险门槛。

金额字段按官方字段单位定义进行换算。估值计算同时保存来源报告日期、公告日期和
`factor_flags`，分母非正或单位不可靠时返回 `NULL`。

## Interfaces

```powershell
quant-value init
quant-value sync --start 2016-01-01 --end 2026-08-25
quant-value build
quant-value verify
quant-value analyze --as-of 2026-08-26 --code 600519.SH
```

所有命令支持 `--database`、`--universe`；`sync` 支持 `--code` 与 `--incremental`。

## Failure Modes

- TDX DLL/客户端下载缺失：运行标记失败并给出准备说明。
- 单标的接口失败：保存其他数据，运行标记 `partial_failure`。
- 专业财务为空：行情仍可用，验证报告明确财务因子不可计算。
- ETF 无基准或 IOPV：保留价格风险/流动性因子，相关列为空并记录原因。

## Alternatives Considered

- 复用 `tdx_archive.sqlite3`：能减少重复数据，但形成跨域、跨 schema 的隐式耦合，
  且 3GB 归档不利于研究样本快速重建，故不采用。
- CSV：缺少事务、唯一约束和时点关联查询，故使用 SQLite。
- 全部 FN 字段：体量和空值过多；选择可解释的原始科目、官方派生指标和 TTM 字段，
  同时以字段字典保留来源定义。

## Verification Strategy

- Fake gateway 离线验证接口选择、幂等和失败隔离。
- 人工构造两次公告的财报，验证公告日前不可见、修订不覆盖过去。
- 股票/ETF 因子数值单元测试。
- 本机 TDX 对代表性标的运行同步、构建和覆盖率报告。
