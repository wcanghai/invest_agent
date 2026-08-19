# 多市场行情日报

一个使用通达信本地 `tqcenter`、Alpha Vantage 和 Kraken 的可配置行情日报工具。

## 目录

- `config/market_universe.json`：所有跟踪标的的唯一配置文件。
- `market_report/tdx.py`：A 股日线与沪深北市场宽度。
- `market_report/external.py`：美股日线、虚拟货币报价。
- `market_report/report.py`：Markdown 报告渲染。
- `run_market_report.py`：每日运行入口。
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

## 运行

先启动并登录通达信客户端，并确保进程环境能读取 `ALPHAVANTAGE_API_KEY`。随后在项目目录运行：

```powershell
python .\run_market_report.py
```

默认输出为 `reports/market_report_YYYY-MM-DD.md`。可指定配置或输出位置：

```powershell
python .\run_market_report.py --config .\config\market_universe.json --output .\reports\custom_report.md
```

若美股 API 密钥未配置、额度不足或个别外部标的失败，A 股报告仍会生成，失败原因写在“外部接口状态”部分。
