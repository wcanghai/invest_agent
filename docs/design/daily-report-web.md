# Design: 每日行情报告网站

## Requirement Link

[`docs/requirements/daily-report-web.md`](../requirements/daily-report-web.md)

## Current System

`market_report.cli` 直接采集数据、计算指标、渲染 Markdown 并写文件。生成逻辑不能被 Web 层复用，历史结果只存在文件中。

## Proposed Architecture

```text
Browser -> FastAPI routes -> DailyReportService -> SQLite repository
                              | cache miss
                              v
                      market_report.service
                              |
                 TDX / Alpha Vantage / Kraken
```

- `market_report.service` 负责采集、计算和生成可序列化快照。
- `market_web.repository` 独占 SQLite 读写和建表。
- `market_web.service` 实现按日期读取、首次生成和并发保护。
- `market_web.app` 提供 HTML 页面、JSON API、健康检查和依赖装配。
- Jinja2 模板负责页面结构，Markdown 的 `tables` 扩展负责报告正文。

## Data Model

`daily_reports`：

- `report_date TEXT PRIMARY KEY`
- `generated_at TEXT NOT NULL`
- `markdown TEXT NOT NULL`
- `snapshot_json TEXT NOT NULL`
- `created_at TEXT NOT NULL`

主键直接支持按日期读取，无需重复索引。初始化后执行 `PRAGMA optimize`。

## Interfaces

- `GET /`：当天报告，缓存未命中时生成。
- `GET /reports/{YYYY-MM-DD}`：只读历史报告。
- `GET /api/reports`：日期和生成时间列表。
- `GET /api/reports/{YYYY-MM-DD|today}`：完整 JSON。
- `GET /health`：`{"status": "ok"}`。

## Security And Permissions

- 默认仅本机监听，不内置认证。
- 数据库查询全部参数化。
- Markdown 禁止原始 HTML，仅开启表格扩展；模板自动转义外围数据。
- API 不返回环境变量或密钥。

## Failure Modes

- 数据源失败：不入库，返回 HTTP 503 和错误页。
- 历史日期不存在：返回 404，不触发历史行情采集。
- 并发首次访问：同一进程内按日期加锁并二次查询数据库。
- 数据库损坏或不可写：健康检查和请求返回明确错误。

## Alternatives Considered

- 纯静态网站无法在首次访问时运行本机通达信采集，也无法可靠持久化。
- 云端 Sites/D1 无法访问本机 TDX 插件，因此首版采用本地 FastAPI/SQLite。
- 每次请求重新生成实现简单，但违背每日一次和永久保存要求。

## Verification Strategy

- 使用伪生成器验证首次调用、缓存命中、进程重建和失败不入库。
- 使用 FastAPI TestClient 验证 HTML、API、404 和健康检查。
- 用现有真实数据源启动本地服务，检查首页响应。

Ready for implementation.
