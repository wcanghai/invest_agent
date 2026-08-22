# Design: 日报新股新债发行日历

## Requirement Link

- [日报新股新债发行日历](../requirements/daily-ipo-calendar.md)

## Current System

- `market_report.tdx` 负责本地通达信行情和市场宽度。
- `market_report.external` 负责公开网络接口。
- `market_report.service` 编排行情采集、历史位置计算和快照生成。
- `market_report.report` 只负责 Markdown 渲染。

## Proposed Architecture

新增 `market_report.offerings`，独立承担发行事件采集、字段归一化、合并和窗口过滤：

1. `fetch_tdx_offerings` 连接 TQ 并读取当期申购信息。
2. `fetch_public_stock_offerings` 和 `fetch_public_bond_offerings` 读取 AKShare DataFrame。
3. `collect_offerings` 对三个来源分别容错，归一化后合并。
4. `market_report.service` 调用聚合函数，并把结果交给渲染和持久化快照。
5. `market_report.report` 增加发行日历表格，不承担数据判断。
6. `market_web.app` 从已持久化快照提供摘要计数及今日/历史发行日历 API，不重复调用数据源。

## Data Model

归一化事件使用字典，字段如下：

- `kind`：`新股` 或 `新债`
- `name`
- `subscription_code`
- `security_code`
- `subscription_date`
- `issue_price`
- `max_subscription`
- `max_subscription_unit`：新股为万股，新债为万元
- `issue_pe`
- `winning_rate`
- `listing_date`
- `underlying_code`
- `underlying_name`
- `issue_size`
- `rating`
- `sources`
- `event_status`：今日申购、待申购、今日上市、近期上市或待上市

合并键为 `(kind, subscription_code)`。同一字段有冲突时保留通达信已给出的当期值；公开源仅补空值。来源集合按固定顺序输出。

## Interfaces

```python
def collect_offerings(
    caller_file: Path,
    as_of: date,
    *,
    tdx_fetcher: Callable[[], list[dict[str, Any]]] | None = None,
    stock_fetcher: Callable[[], pd.DataFrame] | None = None,
    bond_fetcher: Callable[[], pd.DataFrame] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    ...
```

可注入参数仅用于隔离实时数据源和测试；生产调用使用模块默认实现。

## Security And Permissions

- 不处理账户、持仓或下单权限。
- 不增加凭据。
- 延续本地服务仅监听 `127.0.0.1` 的既有行为。

## Failure Modes

- 通达信失败：保留公开源数据并添加警告。
- 单个 AKShare 接口失败：保留通达信及另一个公开源数据并添加警告。
- 字段缺失或不可解析：对应字段为空，不丢弃仍可识别的事件。
- 全部来源无数据：渲染空状态，日报其余部分正常生成。

## Alternatives Considered

- 只使用通达信：实现简单，但没有历史和上市日期，不能满足上市事件需求。
- 只使用 AKShare：字段更全，但失去本机通达信当期日历的独立来源。
- 直接修改 `fetch_a_share_data` 返回值：可复用同一 TQ 会话，但把发行事件耦合进行情接口且扩大既有公共返回契约，因此不采用。

## Risks

- AKShare 上游列名变化会触发空字段或警告；测试覆盖当前字段映射。
- 多开一次短生命周期 TQ 会话有少量开销，但避免改变既有行情契约。

## Verification Strategy

- 单元测试覆盖通达信归一化、公开字段映射、跨源合并、时间窗口和失败降级。
- 渲染测试覆盖有数据及无数据状态。
- 全量运行 pytest 和 `git diff --check`。

## Implementation Notes

- 不将发行事件写入独立数据库；它随每日快照一起由网站现有仓库持久化。
- 发行信息用于事实展示，不生成申购建议或收益预测。
