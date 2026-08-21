# 通达信十年日线增量采集器

该程序面向配置中指定的 A 股、ETF 和场内基金：首次运行回补最近十年日线，后续运行从数据库中该证券的最后交易日的下一天开始查询，只插入新交易日。

## 存储设计

- SQLite 默认位于 `data/tdx_history.sqlite3`。
- `instruments`：证券代码、名称、类型和复权方式。
- `daily_bars`：OHLC、成交量和成交额；`(code, trade_date)` 是主键。
- `sync_runs`：每次运行的时间、新增行数和失败数。
- 每只证券的日线在单独事务中写入；中断后重新运行不会制造重复数据。

## 配置

编辑 `config/tdx_history.json`：

```json
{
  "tdx_user_dir": "D:\\SoftWare\\TDX\\PYPlugins\\user",
  "instruments": [
    {"code": "600519.SH", "name": "贵州茅台", "kind": "stock", "dividend_type": "none"},
    {"code": "510300.SH", "name": "沪深300ETF", "kind": "etf", "dividend_type": "none"},
    {"code": "161725.SZ", "name": "招商中证白酒LOF", "kind": "fund", "dividend_type": "none"}
  ]
}
```

`dividend_type` 可选 `none`（不复权）、`front`（前复权）或 `back`（后复权）。一个数据库中的同一代码不应中途更换复权方式，否则新旧价格口径会不一致。

## 运行

先启动并登录通达信，然后在项目根目录执行：

```powershell
tdx-history
# 或：python -m tdx_history
```

只更新指定代码：

```powershell
tdx-history --symbols 600519.SH 510300.SH
```

工作日 16:30 前运行时，程序默认不写入尚未收盘的当日日线。如确实需要包含当天，可显式执行：

```powershell
tdx-history --include-today
```

指定其他配置或数据库：

```powershell
tdx-history --config .\config\tdx_history.json --database .\data\my_history.sqlite3
```

## 查询示例

```sql
SELECT trade_date, open, high, low, close, volume, amount
FROM daily_bars
WHERE code = '510300.SH'
ORDER BY trade_date;
```

## 运行特性

- 用 `count=-1` 和明确起止日期读取区间数据。
- 使用 `fill_data=False`，不伪造停牌日的 OHLC/成交量。
- 一只证券失败不会阻止其他证券，但程序最终会以非零状态退出。
- 上市不满十年的证券只保存实际上市后的数据。
