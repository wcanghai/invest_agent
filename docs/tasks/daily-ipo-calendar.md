# Implementation Plan: 日报新股新债发行日历

## Milestones

1. 建立独立、可测试的发行事件采集与归一化模块。
2. 接入日报 Markdown 和结构化快照。
3. 完成离线验证、文档和发布说明。

## Task 1: 发行数据采集与归一化

### Background

通达信提供近期申购，AKShare提供更完整的发行和上市字段。

### Scope

- 新增 `market_report/offerings.py`。
- 实现三个来源、日期数字归一化、合并和窗口过滤。
- 所有实时调用均可注入。

### Non-Goals

- 自动交易和价值评分。

### Dependencies

- 现有 `market_report.tdx.load_tq` 与 AKShare 依赖。

### Likely Files

- `market_report/offerings.py`
- `tests/test_market_offerings.py`

### Acceptance Criteria

- 满足需求 AC1 至 AC4。

### Verification Commands

```powershell
python -m pytest -q -p no:cacheprovider tests/test_market_offerings.py
```

## Task 2: 日报与快照集成

### Scope

- 扩展 `market_report.service.generate_market_report`。
- 扩展 `market_report.report.render` 与渲染测试。
- 更新 README 数据口径。

### Non-Goals

- 修改网站路由、数据库模式或 CLI 参数。

### Dependencies

- Task 1。

### Likely Files

- `market_report/service.py`
- `market_report/report.py`
- `tests/test_config_and_report.py`
- `README.md`

### Acceptance Criteria

- 满足需求 AC5、AC6。

### Verification Commands

```powershell
python -m pytest -q -p no:cacheprovider
git diff --check
```

## Dependency Order

Task 1 → Task 2 → 完整验证 → 发布说明。

## Parallelizable Work

本次改动范围小且共享日报函数签名，不安排并行编辑。

## Risky Tasks

- 不同来源列名和日期缺失值归一化。
- 扩展 `render` 参数时需同步所有调用和测试。

## Human Decisions Needed

无。使用需求中记录的默认观察窗口。
