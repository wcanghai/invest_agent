# ADR 0005: 保留独立业务包并增加统一 CLI

## Status

Accepted

## Context

项目已经按业务域拆包，但命令数量增加后缺少统一发现入口；股票全维度采集也需要在
`tdx_history` 内形成清晰子域。

## Decision

保留现有顶级业务包和全部旧 console scripts，新增轻量 `invest_tools` 路由包；将股票
全维度采集移动到 `tdx_history.stock_data` 子包。

## Consequences

- 用户获得统一帮助入口，旧自动化无需修改。
- 业务模块仍可独立测试和运行。
- 统一入口维护一份显式命令映射，新功能需要同步登记。
