# Implementation Plan: 通达信量化价值研究数据域

## Milestones

1. 建立独立包、代表性标的配置、字段字典和 SQLite schema。
2. 实现可注入 TDX 网关以及全量/增量采集。
3. 实现公告日一致的股票/ETF 日频因子。
4. 实现 CLI、覆盖率验证和中文文档。
5. 完成离线测试与本机真实 TDX 样本验证。

## Task List

### Task 1: 数据契约与存储

- Scope: `quant_value/config.py`、`fields.py`、`repository.py`、JSON 配置。
- Acceptance: schema 可重复初始化；所有事实表幂等；字段含官方中文定义。
- Verify: `tests/quant_value/test_repository.py`。

### Task 2: 数据采集

- Scope: `gateway.py`、`service.py`。
- Non-goals: 交易接口、外部数据源、写入其他数据库。
- Acceptance: 股票调用财报/股本/公司行动；ETF 调用行情、快照和跟踪 ETF；
  基准只调用行情；单标的失败隔离。
- Verify: `tests/quant_value/test_service.py`。

### Task 3: 因子构建

- Scope: `factors.py`。
- Acceptance: 财报公告日时点一致；股票和 ETF 使用不同因子；重复构建一致。
- Verify: `tests/quant_value/test_factors.py`。

### Task 4: CLI、文档与验证

- Scope: `cli.py`、`verify.py`、`README.md`、`pyproject.toml`。
- Acceptance: 四个子命令可运行，验证输出按标的解释覆盖与缺失。
- Verify: CLI 解析测试、全套 pytest、`git diff --check`、真实样本运行。

## Dependency Order

Task 1 -> Task 2 -> Task 3 -> Task 4。

## Human Decisions Needed

无。代表性标的作为可编辑 JSON 配置，不影响后续扩展。

## Pilot Completion: 三只通用股票

- [x] 固定贵州茅台、美的集团、宁德时代首批样本配置。
- [x] 增量获取至 2026-08-26，并构建完整日频因子。
- [x] 以行情、财报字段、股本、快照、关系和关键因子覆盖率作为严格质量门槛。
- [x] 因子构建按标的提交，支持长批次中断后续做。
- [x] 公司行动使用稳定内容指纹，消除查询窗口变化造成的重复分红。
- [x] 首批数据完善阶段全仓 48 项测试及 `git diff --check` 通过。

## Task 5: 可解释价值分析

- [x] 分离当日价格/TTM 估值与最近已公告年报口径。
- [x] 实现五维评分、历史估值分位、关键风险门槛和中文解释。
- [x] CLI 支持历史时点和 JSON 输出，拒绝将股票模型套用于 ETF。
- [x] 用贵州茅台、美的集团、宁德时代的真实数据验证。
- [x] 加入分析测试后全仓 50 项测试及 `git diff --check` 通过。
