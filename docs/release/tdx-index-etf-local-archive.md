# Release: 沪深300、中证500与主流 ETF 十年本地归档

## Change Summary

- 新增配置构建器，从通达信固化沪深300、中证500和近期成交额前 120 只 ETF。
- 新增显式标的配置 `config/tdx_index_etf_history.json`，包含 920 个唯一代码。
- 新增 ETF 分批日均成交额读取和离线测试。
- 保持 SQLite schema、日线同步 CLI 和增量语义不变。

## User Impact

- 可使用 `tdx-history-config` 重建研究样本快照。
- 使用生成配置和 `tdx-history --all` 同步时，运行范围严格来自配置，不再动态漂移。
- 当前成分十年历史不是历史每期成分，研究时应考虑幸存者偏差。

## Operator Impact

- 通达信客户端必须启动并登录。
- 本地正式数据库为 `data/tdx_index_etf_history.sqlite3`，不提交、不上传。
- 日常重复运行同一同步命令即可增量追加。

## Verification Report

### Acceptance Criteria Coverage

| 验收项 | 结果 |
|---|---|
| 配置分组 | 沪深300=300，中证500=500，ETF=120 |
| 配置唯一性 | 总数 920，重复代码 0 |
| 小批量真实验证 | 股票/ETF 各 5，只首次新增 20,506，二次新增 0 |
| 完整真实归档 | 920/920 成功，失败 0 |
| 完整幂等重跑 | 新增 0，失败 0 |
| 数据库完整性 | `PRAGMA integrity_check=ok` |
| 全仓测试 | 25 passed，1 个既有弃用警告 |

### Local Database Result

- 文件：`data/tdx_index_etf_history.sqlite3`
- 大小：254,361,600 字节。
- 总日线：1,817,723。
- 股票：800 个标的，1,684,075 条。
- ETF：120 个标的，133,648 条。
- 日期范围：2016-08-22 至 2026-08-21。
- 有数据代码：920；零数据代码：0。
- 最新日不是 2026-08-21 的代码：0。
- 空收盘价：0；非法高低价/负成交量或成交额：0。
- 同步记录：首次成功新增 1,817,723；二次成功新增 0。

### Checks Run

- `python -m pytest -q -p no:cacheprovider tests/test_tdx_history.py`：14 passed。
- `python -m pytest -q -p no:cacheprovider`：21 passed，4 个 setup error；原因是系统 pytest 临时目录拒绝访问。
- 使用已忽略的仓库内 `--basetemp` 重跑：25 passed，1 个既有 FastAPI/httpx 弃用警告。
- `python -m compileall -q finance_news market_report market_web tdx_history`：通过。
- `git diff --check`：通过。

## Pre-Release Checklist

- [x] 需求、设计、ADR、任务和发布文档完整。
- [x] 配置构建单元测试和真实 TDX 验证通过。
- [x] 920 标的首次回补和幂等重跑通过。
- [x] 数据库质量与完整性检查通过。
- [x] SQLite、WAL、SHM、缓存和 pytest 临时目录均被 Git 忽略。

## Deployment Steps

1. 启动并登录通达信。
2. 需要更新样本时运行 `tdx-history-config --output config/tdx_index_etf_history.json`。
3. 审查配置差异和数量。
4. 运行 `tdx-history --config config/tdx_index_etf_history.json --all --database data/tdx_index_etf_history.sqlite3`。
5. 核对失败数和 `sync_runs`。

## Database And Config Changes

- SQLite schema 无迁移。
- 新配置是公开证券代码快照，可版本化。
- 行情数据库和伴随文件只留本地。

## Monitoring

- 配置构建时指数数量必须严格为 300/500。
- ETF 有效流动性候选数量和第 120 名成交额。
- 同步失败数、数据库 `MAX(trade_date)` 和剩余磁盘空间。

## Post-Release Verification

```sql
SELECT kind, COUNT(*) FROM instruments GROUP BY kind;
SELECT COUNT(*), MIN(trade_date), MAX(trade_date) FROM daily_bars;
SELECT COUNT(*) FROM daily_bars WHERE close IS NULL;
PRAGMA integrity_check;
```

## Rollback Plan

- 配置或代码可回退相应 Git 提交。
- 数据库与旧 schema 兼容，无需回滚。
- 如需废弃本地库，应先备份，再由操作者明确删除指定文件；程序不自动删除。

## Communication Draft

沪深300、中证500和近期成交额前 120 只 ETF 的显式配置及十年本地日线归档已完成。920 个标的全部成功，数据库约 254 MB，只保留在本机；后续重复运行同一命令只会增量追加。

## Open Risks

- 当前成分历史回补具有幸存者偏差。
- 新上市证券只有上市后的真实行情。
- 系统 pytest 临时目录权限异常仍存在，已通过仓库内忽略目录规避。

## Release Readiness

Ready to release.
