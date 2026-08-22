# Implementation Plan: 通达信 A 股与 ETF 全标的十年日线归档

## Milestones

1. 完成可测试的证券集合配置和运行时发现。
2. 完成安全冒烟/全量 CLI 和长任务进度输出。
3. 通过离线测试和真实通达信每类 5 个标的验证。
4. 完成发布检查、Git 提交和 GitHub 推送。

## Task List

## Task 1: 证券集合配置与发现

### Background

当前只支持手工 `instruments`，无法跟随全市场标的变化。

### Scope

- 增加 `UniverseSpec` 和 `universes` JSON 解析。
- 在 `TdxDailySource` 中封装 `get_stock_list(market, list_type=1)`。
- 新增无外部依赖的合并、去重、限量和筛选逻辑。

### Non-Goals

- 不改变 SQLite schema。
- 不引入其他证券范围。

### Dependencies

- `docs/design/tdx-all-a-etf-history.md`

### Likely Files

- `tdx_history/config.py`
- `tdx_history/tdx_source.py`
- `tdx_history/universe.py`
- `config/tdx_history.json`

### Acceptance Criteria

- AC1、AC2。

### Verification Commands

```powershell
python -m pytest -q -p no:cacheprovider tests/test_tdx_history.py
```

## Task 2: CLI 安全模式与进度

### Background

全量十年任务耗时长，需要防止误启动并在每只完成后显示进度。

### Scope

- 新增 `--limit-per-kind`和 `--all`。
- `--symbols` 与自动发现兼容。
- 同步服务支持每只结果回调。
- CLI 先输出发现/选中数量，再持续输出同步进度。

### Non-Goals

- 不并发调用通达信 DLL。

### Likely Files

- `tdx_history/service.py`
- `tdx_history/cli.py`
- `tdx_history/__init__.py`

### Acceptance Criteria

- AC2、AC3。

### Verification Commands

```powershell
python -m tdx_history --help
python -m pytest -q -p no:cacheprovider tests/test_tdx_history.py
```

## Task 3: 离线测试和文档

### Scope

- 使用 fake TQ 响应验证列表转换和错误。
- 验证去重、限量、筛选和进度回调。
- 更新 README 和专题说明。

### Acceptance Criteria

- AC1、AC2、AC3、AC7、AC8。

### Verification Commands

```powershell
python -m pytest -q -p no:cacheprovider
git diff --check
```

## Task 4: 真实通达信冒烟验证

### Scope

- 使用独立的忽略 SQLite 库运行默认模式。
- 重运同一命令验证幂等。
- 查询类型/标的数、行数、日期范围、空值、重复键和库完整性。

### Acceptance Criteria

- AC4、AC5、AC6。

### Verification Commands

```powershell
python -m tdx_history --database .\data\tdx_all_smoke.sqlite3
python -m tdx_history --database .\data\tdx_all_smoke.sqlite3
```

### Cleanup Notes

- 冒烟库由 `.gitignore` 排除，不提交 Git。

## Task 5: 发布与 GitHub

### Scope

- 写入验证和发布文档。
- 确认 Git diff 只包含源码、测试、配置和文档。
- 提交并推送当前分支到 `origin`。

### Acceptance Criteria

- AC7、AC8，远程分支指向新提交。

### Verification Commands

```powershell
git status --short
git diff --check
git log -1 --oneline --decorate
git ls-remote --heads origin codex/reorganize-project
```

## Dependency Order

Task 1 → Task 2 → Task 3 → Task 4 → Task 5。

## Parallelizable Work

本变更的模块和验收相互依赖，不需要并行开发。

## Risky Tasks

- 真实通达信列表响应与长时间日线回补。
- 全量命令的误启动与磁盘占用。

## Human Decisions Needed

无。用户已明确要求编写程序、每类约 5 个标的验证并推送 GitHub。

## Recommended First Task

先实现 Task 1，因为 CLI、冒烟测试和全量运行都依赖可注入的证券发现。
