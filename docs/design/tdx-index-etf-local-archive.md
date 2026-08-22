# Design: 配置快照驱动的指数与 ETF 本地归档

## Requirement Link

- `docs/requirements/tdx-index-etf-local-archive.md`

## Current System

- `TdxDailySource` 负责集合发现和单只日线。
- `SyncConfig` 支持动态 `universes` 与显式 `instruments`。
- `HistorySyncService` 对每只证券独立回补和增量同步。
- `HistoryRepository` 通过 SQLite 主键保证幂等。

## Proposed Architecture

新增独立配置构建器，不改变日线同步主流程：

1. 从集合 23、24、31读取候选标的。
2. 分批获取 ETF 近期成交额，计算每只日均成交额。
3. 取前 120 只并与两个指数集合组成 920 只目标快照。
4. 输出只有显式 `instruments` 的 JSON；`selection` 仅保存审计元数据。
5. 使用 `tdx-history --config <快照配置> --all --database <本地库>` 完成归档。

## Module Boundaries

- `tdx_history/tdx_source.py`：增加分批近期日均成交额读取。
- `tdx_history/config_builder.py`：选择、校验、序列化和命令行入口。
- `tdx_history/config.py`：继续只解析运行所需的显式标的，允许审计元数据共存。
- `tdx_history/service.py` / `repository.py`：保持现有增量和存储职责。

## Data Model

SQLite schema 不变。配置新增非运行必需的 `selection`：

- `as_of`
- `index_groups.hs300` / `index_groups.csi500`
- `etf_ranking.metric` / `window_start` / `window_end` / `selected_count`
- `instruments[]`

## Interfaces

- `TdxDailySource.average_amounts(codes, start, end, chunk_size) -> dict[str, float]`
- `build_target_payload(source, tdx_user_dir, as_of, etf_count) -> dict`
- CLI：`tdx-history-config --output ... --etf-count 120`

## Security And Permissions

- 不读取账户、持仓或交易信息。
- 不上传 SQLite；数据库路径继续由 `.gitignore` 保护。
- 配置只含公开证券代码和名称，可与源码一同版本化。

## Failure Modes

- 指数数量不是 300/500：立即失败，避免生成残缺配置。
- ETF 某批查询失败：明确抛错，不输出部分配置。
- ETF 有效流动性数量不足：立即失败。
- 写配置：先写同目录临时文件，再原子替换，避免中断留下半文件。
- 日线单标的失败：沿用现有隔离与重跑机制。

## Alternatives Considered

- 手工维护 920 个代码：易错且无法审计来源，不采用。
- 每次同步动态发现：样本会静默漂移，不满足配置快照要求。
- 获取全部 1,682 只 ETF：不符合“主流”范围且增加无效数据。
- 按基金规模：通达信列表未稳定提供完整规模字段；近期成交额更直接、可复现。

## Risks

- 当前成分回补十年存在幸存者偏差，配置元数据和文档必须明确。
- 日均成交额可能受极端交易日影响；60 日自然窗口降低单日噪声。

## Verification Strategy

- 假数据测试排序、无效值、数量校验、去重和配置可加载性。
- 真实生成后核对 300/500/120/920。
- 真实同步后核对覆盖数、日期范围、失败、重复键和 SQLite 完整性。

## Implementation Notes

- ETF 成交额按正数观测的算术平均值排名，金额单位沿用通达信。
- 同分按代码升序，保证结果稳定。
- 配置生成不触碰数据库；同步命令只读生成后的配置。
