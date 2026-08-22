# Release: 日报新股新债发行日历

## Change Summary

- 新增通达信新股、新债申购采集，分别调用 `get_ipo_info` 的新股和新债类型。
- 新增 AKShare 新股及可转债公开数据补全，并按类型和申购代码去重。
- 新股申购上限统一为万股，新债申购上限保留万元。
- 日报新增近期发行日历，展示事件状态、申购信息、中签率、上市日、正股、规模、评级及来源。
- B/S 首页摘要增加发行事件数和今日可申购数，并提供今日及历史发行日历 API。
- 结构化日报快照新增 `ipo_calendar`。
- 单个补充来源失败只产生警告，不阻断日报生成。

## User Impact

每天生成的 Markdown 和网站日报增加“新股新债日历”，覆盖今天至未来十四天的申购事件，以及最近三天至未来十四天的上市事件。

## Operator Impact

- 继续要求本机通达信客户端已启动并登录。
- 需要可访问 AKShare 所使用的东方财富公开数据源。
- 不新增环境变量、密钥、数据库迁移或 CLI 参数。

## Pre-Release Checklist

- [x] 需求、设计和任务文档完成。
- [x] 数据源调用支持注入，离线测试不连接通达信或公网。
- [x] 单位差异经真实公开数据核对。
- [x] 全量测试通过。
- [x] 真实通达信与公开接口冒烟通过。
- [x] `git diff --check` 通过。

## Deployment Steps

1. 保持现有 Python 依赖安装，无需升级数据库。
2. 启动并登录通达信客户端。
3. 按原方式运行 `market-report` 或 `market-web`。
4. 检查报告中的“新股新债日历”和“外部接口状态”。
5. 检查 `/api/offerings/today` 与页面事件数量一致。

## Database And Config Changes

- 无数据库结构迁移；`ipo_calendar` 随现有 JSON 快照写入 SQLite。
- 无配置或密钥变化。

## Monitoring

- 观察 `warnings` 中的“通达信新股新债日历”“公开新股发行数据”“公开可转债发行数据”。
- 定期与交易所或发行人公告抽样核对发行价格和上市日期。

## Post-Release Verification

```powershell
market-report
```

确认报告包含：

- `## 8. 新股新债日历`
- 新股申购上限单位为“万股”
- 新债申购上限单位为“万元”
- 数据源失败时主报告仍生成

## Verification Report

| 检查 | 结果 |
|---|---|
| 定向测试 | 11 passed |
| 仓库要求的原始 pytest 命令 | 26 passed、5 errors；均因系统临时目录 `pytest-of-Julia` 无访问权限，未进入测试逻辑 |
| 指定仓库内 `--basetemp` 的全量测试 | 32 passed，1 个既有 Starlette/httpx 弃用警告 |
| Python 编译 | 通过 |
| 差异空白检查 | 通过，仅有 Git 的 LF/CRLF 提示 |
| 真实数据冒烟（2026-08-22） | 合并得到 13 条窗口内事件，0 条数据源警告 |

## Rollback Plan

回退 `market_report.offerings` 及 `service`、`report` 中对应集成即可。没有独立表或迁移需要清理；已持久化日报仍是可读取的 JSON/Markdown 快照。

## Open Risks

- 东方财富上游字段或访问策略可能变化；发生时报告会保留通达信结果并显示警告。
- 通达信不提供历史申购记录和完整上市日期，因此公开补充源不可用时字段会减少。
- 本功能展示公开事实，不构成申购建议；最终安排仍以交易所和发行人公告为准。

Ready to release.
