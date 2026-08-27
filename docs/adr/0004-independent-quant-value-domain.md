# ADR 0004: 独立量化价值研究数据域

- 状态：Accepted
- 日期：2026-08-25

## Decision

新增 `quant_value` 第三业务域及独立 `data/quant_value.sqlite3`。该域直接通过可注入
TDX 网关采集研究所需子集，不依赖 `daily_report` 或 `tdx_data` 数据库。历史财务以
公告日作为可见性边界；股票与 ETF 使用不同的因子模型。

## Consequences

- 好处：无未来数据泄漏、研究库体量可控、可独立重建和测试。
- 代价：与完整归档存在少量行情重复；新增字段需要显式维护字典。
- 限制：ETF 历史 IOPV、费率、持仓等 TDX 未验证数据不做伪造填充。
