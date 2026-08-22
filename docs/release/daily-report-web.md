# Verification Report: 每日行情报告网站

## Scope

验证 Markdown 日报网站、SQLite 永久归档、每日首次生成缓存、历史页面和 JSON API。

## Acceptance Criteria Coverage

- 空数据库访问首页：真实行情验证由 0 条变为 1 条。
- 同日重复访问：两次 `generated_at` 均为 `2026-08-21T23:11:28`，数据库仍为 1 条。
- 服务重启：重启后读取相同 `generated_at`，数据库仍为 1 条。
- 失败不入库：自动化测试覆盖生成器异常后的空数据库状态。
- 页面与 API：自动化测试覆盖首页、历史页、JSON API、健康检查和静态资源。
- 内容安全：自动化测试验证 Markdown 中的 `script` 标签被移除，HTTPS 东方财富链接保留。
- 表格交互：验证配置顺序不变、涨跌幅表头三态箭头可用、阈值纯视觉高亮规则存在。
- 外部链接：东方财富链接包含新页签和 `noopener noreferrer` 安全属性。

## Checks Run

- `python -m pytest -q -p no:cacheprovider --basetemp=.pytest-tmp`
- `python -m market_web --help`
- 现有命令行入口 `--help` 检查
- `git diff --check`
- 本地服务首次访问、重复访问及重启后的真实数据检查

## Results

- 17 项测试通过。
- 真实网页返回 HTTP 200，响应正文 14,027 字节。
- SQLite 唯一日期记录、同日缓存和进程重启持久化均通过。
- `git diff --check` 通过。

## Remaining Risks

- 首次生成仍依赖本机已登录的通达信客户端和外部行情网络。
- 当前并发互斥为单进程锁，服务必须按文档保持单 worker。
- FastAPI 测试依赖栈输出一条上游 `TestClient/httpx` 弃用警告，不影响运行结果。

## Merge Readiness

Ready with noted risk.
