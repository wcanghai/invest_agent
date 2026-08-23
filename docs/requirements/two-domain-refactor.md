# 双业务域重构需求

## 目标

- 日报相关采集、新闻、存储、渲染和 Web 全部归入 `daily_report`。
- 通达信完整归档独立为 `tdx_data`。
- 删除 `tdx_history`、`invest_tools`、旧包和所有过渡兼容关系。
- 日报历史行情、新闻和报告统一保存到 `data/daily_report.sqlite3`，不再使用 CSV。
- 保留既有六个功能命令，并允许离线测试替代真实 TDX/网络访问。

## 验收

- 只有 `daily_report` 与 `tdx_data` 两个业务包。
- CSV 历史及旧数据库成功迁移并逐项校验后删除。
- 每日报告只生成并持久化一次，新闻和行情复合键去重。
- Web 页面、API、CLI 和额外 TDX 样例入口可用。
- 全部测试、命令帮助、SQLite 完整性及 `git diff --check` 通过。
