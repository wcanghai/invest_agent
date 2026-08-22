# Release: 通达信十股全维度数据试采集

## Change Summary

新增配置驱动的十只 A 股全维度采集命令，使用混合固定表与 JSON 的 SQLite schema，
并输出逐股票、逐数据集可用性和字段汇总。

## User Impact

用户可以先验证十只跨板块样本，再决定是否扩到全市场。现有 `tdx-history` 日线命令和
数据库契约保持不变。

## Operator Impact

- 新配置：`config/tdx_stock_samples.json`。
- 新命令：`tdx-stock-data` 或 `python -m tdx_history.stock_data`。
- 新本地数据库：`data/tdx_stock_data.sqlite3`。
- 新本地汇总：`data/history/tdx_stock_data_summary.json`。

## Database And Config Changes

新数据库首次运行自动建表，没有对既有数据库执行破坏性迁移。生成数据仍由
`.gitignore` 排除。

## Verification

- 新增测试：8 passed。
- 全仓库测试：40 passed，1 个第三方弃用警告。
- `git diff --check`：通过。
- 真实十股结果：109 success、1 empty、0 failed。

## Monitoring

查看 `stock_collection_runs` 和 `stock_collection_results` 中的失败、空结果和字段数变化。

## Rollback Plan

停止使用新命令即可；代码回滚不会影响现有日线功能。本地新数据库若不再需要，可由用户
明确确认后删除。

## Open Risks

- 当前快照和成分关系必须持续归档才能形成历史。
- 未文档化的 Fn/GP 字段未猜测性批量请求。
- 通达信版本或权限变化可能使字段集合改变。

## Release Readiness

Ready with noted risk。
