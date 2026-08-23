# 双业务域重构发布说明

## 行为变化

- Python 包变为 `daily_report` 和 `tdx_data`；控制台命令保持原功能名称。
- 日报历史行情和财经新闻从 CSV 改为 `data/daily_report.sqlite3`。
- TDX 默认归档库改为 `data/tdx_archive.sqlite3`。
- `invest-tools`、`tdx_history` 及所有旧模块入口已删除。

## 本地迁移结果

- 29 个正式 CSV、37,552 条行情已完整迁移。
- 2 份历史日报已完整迁移。
- TDX 新库保留 51,727 条日线、51,757 条原始记录和 151 个字段定义。
- 新旧逐项计数一致，SQLite `integrity_check` 为 `ok` 后删除旧产物。

## 回滚

代码通过 Git 回滚；本地数据库不纳入版本控制。如需数据级回滚，应在发布前自行复制 `data/` 到工作区外。回滚旧代码后，旧 CSV 流程不会自动从 SQLite 反向生成。
