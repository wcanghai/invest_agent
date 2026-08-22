# Requirement: 通达信 A 股与 ETF 全标的十年日线归档

## Background

现有 `tdx_history` 只同步 JSON 中手工配置的证券。需要扩展为可从通达信自动发现所有 A 股和 ETF，首次回补近十年日线，后续幂等增量写入本地 SQLite。

## Goals

- 从通达信证券集合 `5`自动发现所有 A 股。
- 从通达信证券集合 `31`自动发现所有 ETF。
- 对首次出现的证券回补近 10 年 OHLC、成交量和成交额。
- 对已存在证券只请求最后交易日之后的数据。
- 先以每类约 5 个标的完成真实通达信冒烟验证，再提供显式全量模式。

## Users And Scenarios

- 本地投资数据使用者首次建立 A 股/ETF 十年数据库。
- 用户每日收盘后重新运行同一命令，只追加新交易日。
- 中途中断或单只证券失败后，用户可直接重运，无需清库。
- 开发者可在不连接通达信的情况下测试发现、限量、去重和持久化逻辑。

## Functional Requirements

1. 配置支持证券集合，每个集合包含 `market`、`kind`和 `dividend_type`。
2. 配置仍支持手工 `instruments`，自动发现与手工标的按代码去重。
3. 命令默认每类最多同步 5 个标的，用于安全冒烟验证。
4. `--limit-per-kind N` 可调整每类上限；`--all` 取消上限并同步全部标的。
5. `--symbols` 仍可指定自动发现或手工配置中的代码。
6. 证券列表需使用 `get_stock_list(market, list_type=1)` 获取 `Code` 和 `Name`。
7. 每只证券完成后立即事务提交，并输出进度。
8. 数据库以 `(code, trade_date)` 为日线唯一键，重运不得重复写入。
9. 数据源需使用 `fill_data=False`，不伪造停牌日数据。
10. 单只标的失败不影响其他标的；有失败时命令最终非零退出。

## Non-Functional Requirements

- Python 3.11+，公开函数使用类型标注。
- 数据获取、编排和持久化分层；通达信调用可注入，单元测试离线。
- SQLite 数据库、WAL、日志、缓存和字节码不进入 Git。
- 全量运行可中断恢复，不依赖内存中保存全市场日线。
- 对千万级日线行数保持主键查询和顺序增量写入能力。

## Out Of Scope

- 本次不自动启动、登录或操作通达信 GUI。
- 不包含港股、美股、LOF、债券、指数或期货的全量归档。
- 不提供远程服务、公网暴露、认证、交易或选股功能。
- 不将实际行情数据库推送到 GitHub。

## Acceptance Criteria

- AC1：离线测试证明 A 股与 ETF 集合可转换为类型正确的 `Instrument`。
- AC2：离线测试证明每类限量、代码去重和 `--symbols` 筛选正确。
- AC3：现有持久化唯一性、首次回补、增量和失败隔离测试继续通过。
- AC4：真实通达信冒烟运行每类约 5 个标的，两类均成功写入 SQLite。
- AC5：冒烟库无重复 `(code, trade_date)`、无空收盘价，`PRAGMA integrity_check` 返回 `ok`。
- AC6：第二次运行不重复写入已有交易日。
- AC7：`python -m pytest -q -p no:cacheprovider` 和 `git diff --check` 通过。
- AC8：发布文档明确全量命令、容量/时间风险、恢复方式和不提交数据库。

## Dependencies

- 已启动并登录的通达信客户端。
- 本地 `tqcenter.py` 及通达信 DLL。
- pandas 与 Python 标准库 SQLite。

## Risks

- 全量约数千标的、千万级行，可能运行数小时并占用数 GB 磁盘。
- 客户端本地盘后数据缺失、连接重置或单只超时可造成部分失败。
- 通达信证券集合可随客户端版本或市场变化，数量不应写死在程序中。
- 退市或长期停牌标的可能不返回完整十年数据。

## Open Questions

- 无阻塞性问题。本次采用不复权作为默认口径，全量运行必须显式传入 `--all`。

## Readiness

Ready for design.
