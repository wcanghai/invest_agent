# Release: 1.1.0 仓库结构与统一功能入口

## Change Summary

- 新增 `invest-tools` 统一入口，同时保留所有独立命令。
- 将股票全维度采集整理为 `tdx_history.stock_data` 子包。
- 增加配置和文档导航，并将使用指南集中到 `docs/guides/`。
- 纳入新股新债日历及其本地网站 API。
- 纳入十只股票全维度 SQLite 采集、字段目录和运行状态。

## User Impact

旧命令和既有数据库保持兼容。用户可以从 `invest-tools --help` 发现功能，也可以继续使用
`market-report`、`market-web`、`tdx-history` 等命令。

## Operator Impact

- 新 console script：`invest-tools`、`tdx-stock-data`。
- 新可提交配置：A 股专用动态集合和十股试采集配置。
- 本地生成的数据库、缓存和汇总仍不进入 Git。

## Database And Config Changes

既有日报和日线 schema 无破坏性迁移。股票全维度采集使用独立 SQLite，并在首次运行时自动
建表。

## Pre-Release Checklist

- 全仓库离线测试通过。
- 所有统一子命令 `--help` 通过。
- 配置解析通过。
- 编译和 `git diff --check` 通过。
- staged diff 不包含数据库、缓存、凭据或字节码。

## Rollback Plan

回退本次 Git 提交即可恢复旧目录和入口；本地 SQLite 无需回滚，也不会随 Git 操作删除。

## Open Risks

真实 TDX 和外部行情仍依赖本机客户端、下载状态、网络和数据权限；离线测试仅验证适配和
业务逻辑。

## Release Readiness

Ready to release。
