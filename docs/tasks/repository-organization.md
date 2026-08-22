# Implementation Plan: 仓库结构与统一功能入口整理

## Milestones

1. 建立仓库整理的需求、设计和 ADR。
2. 移动股票全维度模块并修正导入。
3. 新增统一 CLI、配置索引和文档索引。
4. 完整验证后提交并推送。

## Task List

### Task: 股票采集子包化

- 将 CLI、repository、service、source 移到 `tdx_history/stock_data/`。
- 更新 console script、测试和文档引用。
- 保持命令行为和 SQLite schema 不变。

### Task: 统一入口

- 新增 `invest_tools` 包和 `invest-tools` console script。
- 采用延迟导入和参数透传。
- 添加离线路由测试。

### Task: 导航和配置整理

- 增加 `config/README.md` 与 `docs/README.md`。
- 更新根 README 的目录图和命令示例。
- 使用明确的 A 股配置文件名。

### Task: 验证与发布

- 运行 pytest、compileall、各入口 `--help`、`git diff --check`。
- 检查 staged diff 和忽略文件。
- 提交并推送当前 feature branch。

## Verification Commands

```powershell
python -m pytest -q -p no:cacheprovider
python -m compileall -q finance_news invest_tools market_report market_web tdx_history
python -m invest_tools --help
git diff --check
```

## Human Decisions Needed

无。用户已明确要求整理、测试、提交 GitHub。
