# Release: 通达信 A 股与 ETF 全标的十年日线归档

## Change Summary

- `tdx_history` 可从通达信集合 `5` 和 `31` 自动发现所有 A 股与 ETF。
- 默认运行是每类 5 个标的的安全冒烟模式；`--all` 显式启用全量。
- 保留手工标的、`--symbols`、十年首次回补、日常增量、单标的失败隔离和 SQLite 幂等写入。
- 新增长任务逐标的进度输出，并正确处理周末与无交易日的空增量区间。

## User Impact

- `tdx-history` 默认行为由“配置中的全部手工标的”变为“自动发现后每类前 5 个”。
- 全量用户必须使用 `tdx-history --all`。
- `--symbols` 仍然可用，且可指定自动发现集合中的代码。

## Operator Impact

- 首次全量回补可能运行数小时，SQLite 可能占用数 GB。
- 必须保持通达信客户端启动且已登录。
- 中断后直接重运 `--all`，无需删库。
- 数据库受 `.gitignore` 保护，不应上传 GitHub。

## Verification Report

### Acceptance Criteria Coverage

| 验收项 | 检查 | 结果 |
|---|---|---|
| AC1 发现与类型 | fake TQ 列表转换测试 + 真实发现 | 通过 |
| AC2 限量/去重/筛选 | `select_instruments` 离线测试 | 通过 |
| AC3 持久化和增量回归 | `tests/test_tdx_history.py` | 12 项通过 |
| AC4 每类 5 个真实标的 | 通达信冒烟库 | stock=5，etf=5 |
| AC5 库质量 | 重复键/空收盘/`integrity_check` | 0 / 0 / `ok` |
| AC6 重运幂等 | 同一命令连续两次 | 第二次新增 0 |
| AC7 仓库检查 | pytest / compileall / diff check | 通过 |
| AC8 运维文档 | README、专题文档、本发布说明 | 通过 |

### Checks Run

- `python -m pytest -q -p no:cacheprovider tests/test_tdx_history.py`：12 passed。
- `python -m pytest -q -p no:cacheprovider --basetemp .pytest-tmp/tdx-all-final-20260822`：23 passed，1 个已存在的 FastAPI/httpx 弃用警告。
- 按 `AGENTS.md` 原命令首次全仓运行时，系统 pytest 临时目录无访问权限，19 项通过、4 项 setup error；改用仓库内已忽略 `--basetemp` 后 23 项全部通过。
- `python -m compileall -q finance_news market_report market_web tdx_history`：通过。
- `git diff --check`：通过。

### Real TDX Smoke Result

- 时点：2026-08-22（截止交易日 2026-08-21）。
- 发现：7,240 个标的，其中 A 股 5,558、ETF 1,682。
- 选中：A 股 5、ETF 5。
- 第一次：新增 11,739 条，失败 0。
- 第二次：新增 0 条，失败 0。
- 范围：2016-08-22 至 2026-08-21；新上市 ETF 只有上市后数据。
- 最终库：`data/tdx_all_smoke_final_20260822.sqlite3`（1,683,456 字节，已忽略）。

### Issues Found And Fixed

- 无交易日的空增量区间被误判为数据源失败；已改为标准空 DataFrame，由服务层区分首次空数据与增量无新数据。
- 周末截止日会产生无意义空查询；已回退到最近工作日。
- `--limit-per-kind 0` 会被误当为默认 5；已改为显式校验失败。
- `SyncConfig` 新字段曾改变位置参数语义；已调整为尾部默认字段，保留旧两参数构造方式。

## Pre-Release Checklist

- [x] 需求、设计、ADR 和任务文档完整。
- [x] 离线测试与全仓回归通过。
- [x] 真实通达信每类 5 个冒烟通过。
- [x] 数据库与临时测试目录已被 Git 忽略。
- [x] 无 schema 迁移、无新依赖、无凭证变更。

## Deployment Steps

1. 启动并登录通达信客户端。
2. 先运行默认冒烟：`tdx-history`。
3. 检查输出的发现数、失败数和数据库路径。
4. 确认磁盘空间充足后运行：`tdx-history --all`。
5. 任务中断时重复第 4 步即可续传。

## Database And Config Changes

- 无 SQLite schema 迁移。
- `config/tdx_history.json` 新增 `universes`，默认配置 A 股集合 `5` 和 ETF 集合 `31`。
- 已有手工 `instruments` 配置格式仍受支持。

## Monitoring

- CLI 发现数量是否突然为 0 或显著下降。
- 逐标的进度、`failed` 数量和 `sync_runs` 的最终状态。
- 数据库体积、剩余磁盘和 WAL 体积。
- 抽查 `MAX(trade_date)` 是否跟随最新交易日。

## Post-Release Verification

```sql
SELECT kind, COUNT(*) FROM instruments GROUP BY kind;
SELECT COUNT(*) FROM daily_bars WHERE close IS NULL;
SELECT code, trade_date, COUNT(*)
FROM daily_bars GROUP BY code, trade_date HAVING COUNT(*) > 1;
PRAGMA integrity_check;
```

## Rollback Plan

- 代码回滚：回退本变更提交，原手工配置模式可恢复。
- 配置回滚：删除 `universes`，在 `instruments` 中恢复手工代码。
- 数据库不需回滚：新数据与旧 schema 兼容，保留可避免重新回补。
- 如操作者需要完全废弃本地数据，应手动备份后删除指定 SQLite；发布过程不自动删库。

## Communication Draft

`tdx-history` 现可自动发现所有 A 股和 ETF。默认每类只同步 5 个用于验证；使用 `--all` 启动全量十年归档。任务可中断重运，日线按代码和交易日幂等写入本地 SQLite。

## Open Risks

- 未在本次会话中真正跑完 7,240 个标的的全量十年任务；该任务可能持续数小时，应由操作者在确认磁盘和客户端稳定后执行。
- FastAPI 测试存在与本变更无关的 httpx 弃用警告。

## Release Readiness

Ready to release.
