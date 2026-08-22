# Implementation Plan: 指数与主流 ETF 十年本地归档

## Milestones

1. 实现并测试配置快照构建器。
2. 生成 300+500+120 的真实配置。
3. 小批量验证后执行 920 标的十年归档。
4. 完整性、幂等性与发布检查。

## Task List

## Task: 配置构建器

### Scope

- 分批读取 ETF 近期成交额。
- 校验指数成分数量。
- 选择 120 只 ETF 并输出显式配置。
- 增加离线测试和使用文档。

### Non-Goals

- 修改 SQLite schema。
- 自动更新指数成分。

### Likely Files

- `tdx_history/tdx_source.py`
- `tdx_history/config_builder.py`
- `pyproject.toml`
- `tests/test_tdx_history.py`
- `docs/tdx-history.md`

### Acceptance Criteria

- 假数据可稳定生成预期排序和元数据。
- 输出能由现有 `load_config` 加载。

### Verification Commands

- `python -m pytest -q -p no:cacheprovider tests/test_tdx_history.py`
- `python -m compileall -q tdx_history`

## Task: 真实配置与本地同步

### Scope

- 生成 `config/tdx_index_etf_history.json`。
- 先按每类少量标的验证，再以 `--all` 完整回补。
- 核对数据库质量并二次幂等运行。

### Non-Goals

- 上传或提交 SQLite 数据库。
- 补齐指数历史成分变化。

### Acceptance Criteria

- 配置为 920 个唯一标的。
- 本地库包含所有成功标的，失败清单为 0 或已重跑补齐。
- 第二次运行新增 0。

### Verification Commands

- `python -m tdx_history.config_builder --output config/tdx_index_etf_history.json`
- `tdx-history --config config/tdx_index_etf_history.json --all --database data/tdx_index_etf_history.sqlite3`
- `python -m pytest -q -p no:cacheprovider`
- `git diff --check`

## Dependency Order

配置构建器 → 离线测试 → 真实配置 → 小批量 → 全量 → 数据校验 → Git 检查。

## Risky Tasks

- 长任务中通达信客户端断连；保留逐标的进度和重跑能力。
- 当前成分历史回补的研究偏差；配置与发布说明明确标注。

## Human Decisions Needed

无；ETF 数量取 120，流动性窗口取 60 个自然日。
