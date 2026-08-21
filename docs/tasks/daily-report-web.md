# Implementation Plan: 每日行情报告网站

## Milestones

1. 抽取日报生成服务并保持 CLI 行为。
2. 实现 SQLite 仓库和每日首次生成服务。
3. 实现 HTML 页面、历史导航和 JSON API。
4. 完成测试、真实启动检查和使用文档。

## Dependency Order

生成服务 -> 数据仓库 -> 每日缓存服务 -> HTTP 层 -> 验证。

## Acceptance And Verification

- `python -m pytest -q -p no:cacheprovider`
- `python -m market_web --help`
- 启动本地服务后请求 `/health`、`/`、`/api/reports/today` 两次。
- 检查 SQLite 同一天只有一行，第二次请求的 `generated_at` 不变。

## Non-Goals

本任务不加入登录、公网部署、定时任务或覆盖历史报告功能。
