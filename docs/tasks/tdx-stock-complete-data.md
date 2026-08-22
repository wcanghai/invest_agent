# Implementation Plan: 通达信股票全维度数据试采集

## Milestones

1. 定义十股配置和混合 SQLite schema。
2. 实现只读 TQ 适配、编排和 CLI。
3. 完成离线测试和真实十股试运行。
4. 输出字段可用性汇总和发布说明。

## Task List

### Task: 数据模型与幂等仓储

- 新增股票全维度 repository。
- 固定表使用自然键，快照一天一个版本。
- 验证重复写入不重复。

### Task: 只读接口适配

- 封装十类安全接口。
- 关闭日线填充，财务同时请求报告期和公告期。
- 不暴露账户和交易接口。

### Task: 同步编排与结果报告

- 逐股票、逐数据集捕获异常。
- 写入运行状态、字段数、记录数和错误。
- 输出本地 JSON 汇总。

### Task: 十股真实验证

- 在已登录通达信环境运行。
- 检查 SQLite 表计数、日期范围和 JSON 可解析性。
- 记录环境相关的空数据或权限限制。

## Dependency Order

数据模型 → 数据源 → 编排/CLI → 离线测试 → 真实验证。

## Risky Tasks

真实财务和专业字段返回结构不稳定，必须采用保守的通用规范化逻辑。

## Human Decisions Needed

无。全市场扩容需在本次结果通过后另行决定。

## Verification Commands

```powershell
python -m pytest -q -p no:cacheprovider
python -m tdx_history.stock_data --config config/tdx_stock_samples.json
git diff --check
```
