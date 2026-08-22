# 配置目录

该目录只保存可复现、可审阅的输入配置，不保存数据库、缓存或凭据。

| 文件 | 用途 | 维护方式 |
|---|---|---|
| `market_universe.json` | 日报、网站和历史缓存的多市场标的 | 手工维护 |
| `tdx_history.json` | 全部 A 股和 ETF 的动态发现入口 | 手工维护集合编号 |
| `tdx_a_share_history.json` | 仅全部 A 股的动态发现入口 | 手工维护集合编号 |
| `tdx_index_etf_history.json` | 沪深300、中证500及主流 ETF 明确快照 | `tdx-history-config` 生成后审阅 |
| `tdx_stock_samples.json` | 十只跨板块股票的全维度试采集 | 手工维护 |

配置可以提交 Git，但 `data/` 中生成的 SQLite、JSON 汇总、WAL/SHM 和行情缓存不得提交。
密钥使用环境变量，不写入配置文件。
