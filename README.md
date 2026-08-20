# 多市场行情日报

一个使用通达信本地 `tqcenter`、Alpha Vantage 和 Kraken 的可配置行情日报工具。

## 目录

- `config/market_universe.json`：所有跟踪标的的唯一配置文件。
- `market_report/tdx.py`：A 股日线与沪深北市场宽度。
- `market_report/external.py`：美股日线、虚拟货币报价。
- `market_report/report.py`：Markdown 报告渲染。
- `run_market_report.py`：每日运行入口。
- `build_history_cache.py`：首次建立五年日线缓存。
- `reports/`：生成的日报，按日期保存。

## 配置标的

直接编辑 `config/market_universe.json` 中相应的代码和名称即可。例如，A 股股票默认已配置：

```json
"a_share_stocks": {
  "000333.SZ": "美的集团",
  "600519.SH": "贵州茅台"
}
```

可按同样方式增删 ETF、A 股指数、美股和 Kraken 的 USD 交易对。A 股代码使用通达信格式（如 `600519.SH`、`000001.SZ`）；美股使用交易代码（如 `NVDA`）；加密资产使用 Kraken 交易对（如 `XBTUSD`）。

`commodity_futures` 默认包含黄金、白银、沪铜、原油。它们是具体期货合约代码，临近到期时需更新为新的主力合约；单一合约通常没有完整三年历史，因此报告会显示“历史样本不足”，而不会错误地给出三年分位。

## 运行

先启动并登录通达信客户端，并确保进程环境能读取 `ALPHAVANTAGE_API_KEY`。随后在项目目录运行：

```powershell
python .\build_history_cache.py
python .\run_market_report.py
```

默认输出为 `reports/market_report_YYYY-MM-DD.md`。可指定配置或输出位置：

```powershell
python .\run_market_report.py --config .\config\market_universe.json --output .\reports\custom_report.md
```

首次运行请先执行 `build_history_cache.py`，它会将配置中 A 股、ETF、指数、美股和加密资产的近五年日线保存到 `data/history/`。日报随后使用近三年的本地收盘价计算“价格分位”：≤20% 为价格偏低，≥80% 为价格偏高，否则为价格中性。该指标是价格历史位置，不能代替 PE、PB 等估值分析。

建库脚本可重复执行，默认会跳过已存在的标的缓存，便于中断后继续；如需强制全量重新下载，使用 `python .\build_history_cache.py --overwrite`。

历史缓存来源为：A 股/ETF/指数使用通达信，配置美股使用 Yahoo Finance 日线，配置加密资产使用 Coinbase UTC 日 K。当日美股和加密资产报价仍分别来自 Alpha Vantage 与 Kraken，因此不同交易所/数据源在同一时刻可能存在轻微价格差异。

若美股 API 密钥未配置、额度不足或个别外部标的失败，A 股报告仍会生成，失败原因写在“外部接口状态”部分。
