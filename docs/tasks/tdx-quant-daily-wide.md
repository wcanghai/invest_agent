# 实施计划：TDX 量化日频宽表

## 里程碑

1. 增加可向前迁移的宽表和构建审计结构。
2. 实现单标的线性 point-in-time 合并和批量幂等写入。
3. 增加命令行、文档和离线测试。
4. 在真实库构建股票/ETF样例，再构建当前全标的并验证。

## 任务

### 任务一：存储结构

- 修改：`tdx_data/repository.py`
- 验收：旧库打开后自动创建新表和索引，不修改旧数据。
- 验证：临时 SQLite 表结构测试。

### 任务二：构建服务

- 新增：`tdx_data/quant_wide_service.py`
- 范围：行情历史特征、财报公告时点、股本、公司行为、精确日快照。
- 非目标：未来标签、外部网络采集。
- 验收：重复构建幂等，公告前后切换正确，ETF 财务为空。

### 任务三：命令行与文档

- 新增：`tdx_data/quant_wide_cli.py`
- 修改：`pyproject.toml`、`tdx_data/README.md`
- 验收：支持全部当前标的、指定代码、日期范围、数量限制和重建。

### 任务四：验证

- 新增：`tests/tdx_data/test_quant_wide_service.py`、CLI 测试。
- 命令：`python -m pytest -q -p no:cacheprovider --basetemp .test-tmp`。
- 真实库：至少三只股票、两只 ETF；检查主键唯一、财报公告约束、ETF 空财报、日期覆盖。
- 最终：`PRAGMA quick_check` 和 `git diff --check`。

## 依赖顺序

存储结构 → 构建服务 → CLI/文档 → 真实构建与验证。

## 人工决策

无。未来标签和额外事件源不阻塞当前基础宽表。
