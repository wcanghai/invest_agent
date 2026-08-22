# 指南：通达信 A 股与 ETF 十年日线增量采集器

该程序可从通达信自动发现所有 A 股和 ETF：首次运行回补最近十年日线，后续运行从数据库中该证券的最后交易日的下一天开始查询，只插入新交易日。

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
  "universes": [
    {"market": "5", "kind": "stock", "dividend_type": "none"},
    {"market": "31", "kind": "etf", "dividend_type": "none"}
  ],
  "instruments": []
}
```

`market=5` 表示所有 A 股，`market=31` 表示 ETF。`instruments` 可继续补充手工标的。`dividend_type` 可选 `none`（不复权）、`front`（前复权）或 `back`（后复权）。一个数据库中的同一代码不应中途更换复权方式。

## 运行

先启动并登录通达信，然后在项目根目录执行：

```powershell
tdx-history
# 或：python -m tdx_history
```

默认是安全冒烟模式，每种证券类型只同步前 5 个标的。可调整上限：

```powershell
tdx-history --limit-per-kind 10
```

全量同步所有 A 股和 ETF 必须显式执行：

```powershell
tdx-history --all
```

> 全量首次回补可能需要数小时和数 GB 磁盘。中断后直接重运同一命令，程序会通过每只证券的最新交易日续传。

只更新发现集合或手工配置中的指定代码：

```powershell
tdx-history --symbols 600519.SH 510300.SH
```

工作日 16:30 前运行时，程序默认不写入尚未收盘的当日日线，并会跳过周末。交易所节假日由通达信的空区间结果幂等处理。如确实需要包含当天，可显式执行：

```powershell
tdx-history --include-today
```

指定其他配置或数据库：

```powershell
tdx-history --config .\config\tdx_history.json --database .\data\my_history.sqlite3
```

## 沪深300、中证500与主流 ETF 快照

生成当前指数成分和按最近 60 个自然日日均成交额排名的前 120 只 ETF：

```powershell
tdx-history-config --output .\config\tdx_index_etf_history.json
# 或：python -m tdx_history.config_builder --output .\config\tdx_index_etf_history.json
```

生成文件包含 300 只沪深300成分、500 只中证500成分和 120 只 ETF 的显式代码。同步时不会再次动态改变样本：

```powershell
tdx-history --config .\config\tdx_index_etf_history.json --all `
  --database .\data\tdx_index_etf_history.sqlite3
```

指数成分是配置生成日的当前快照；把当前成分回补十年不等于历史每期真实成分，研究时需注意幸存者偏差。SQLite、WAL 和 SHM 文件只保留本地，不应提交或上传。

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
- 数据库、WAL 和运行日志均已被 `.gitignore` 排除，不应推送到 GitHub。
