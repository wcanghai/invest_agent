# 多市场投资数据工具

一个模块化的 Python 项目，提供多市场行情日报、历史行情缓存、通达信日线增量同步和财经新闻采集。

## 功能模块

```text
.
├─ config/                 # 标的和同步配置
├─ docs/                   # 专题文档
├─ finance_news/           # 新浪/东方财富新闻采集与标准化
├─ market_report/          # 行情数据源、历史缓存、报告渲染及命令入口
├─ market_web/             # 每日首次生成、SQLite 归档和浏览器页面/API
├─ tdx_history/            # 通达信历史数据配置、存储、同步服务及命令入口
├─ tests/                  # 核心业务单元测试
├─ .gitignore              # 缓存、运行结果和本地配置忽略规则
└─ pyproject.toml          # 项目元数据、依赖和命令入口
```

运行时生成的 `data/history/`、`data/news/`、`data/*.sqlite3` 和 `reports/` 不纳入版本控制。

## 环境安装

需要 Python 3.11 或更高版本：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

使用 A 股相关功能前，需要启动并登录通达信客户端。通达信 Python 插件默认从
`D:\SoftWare\TDX\PYPlugins\user` 加载，也可以通过环境变量覆盖：

```powershell
$env:TDX_USER_DIR = "D:\path\to\TDX\PYPlugins\user"
```

美股当日报价需要 Alpha Vantage 密钥：

```powershell
$env:ALPHAVANTAGE_API_KEY = "your-key"
```

## 使用方法

### 1. 建立历史缓存

```powershell
market-cache
# 或：python -m market_report.cache_cli
```

默认缓存 `config/market_universe.json` 中标的的近五年日线。使用
`--overwrite` 强制刷新，使用 `--help` 查看全部参数。

### 2. 生成多市场日报

```powershell
market-report
# 或：python -m market_report
```

默认写入 `reports/market_report_YYYY-MM-DD.md`。标的统一在
`config/market_universe.json` 中维护。

### 3. 同步通达信 A 股/ETF 十年日线

```powershell
tdx-history
# 或：python -m tdx_history
```

默认每类同步 5 个标的作为冒烟验证；使用 `tdx-history --all`
才同步通达信中的所有 A 股和 ETF。首次回补、后续增量追加到 SQLite。配置和数据结构详见
[通达信历史同步说明](docs/tdx-history.md)。

### 4. 启动日报网站

```powershell
market-web
# 或：python -m market_web
```

浏览器打开 <http://127.0.0.1:8000>。网站按本机自然日工作：当天第一次访问
首页或 `/api/reports/today` 时采集行情并计算报告，成功后写入
`data/market_reports.sqlite3`；同一天后续访问直接读取该记录。服务重启后记录仍然
存在，历史报告可从页面左侧归档或 `/api/reports` 查看。

标的表默认保持 `config/market_universe.json` 中的配置顺序；点击涨跌幅列名旁的
箭头，可在配置顺序、涨幅优先和跌幅优先之间循环切换。涨跌幅超过 ±3%，或三年
价格分位高于 80% / 低于 20% 时，网页会用颜色和底纹高亮，其中高分位使用深红
粗体强调；东方财富行情链接在新页签打开。

常用接口：

- `/`：今日报告网页；
- `/reports/YYYY-MM-DD`：已归档的历史报告；
- `/api/reports/today`：今日完整 JSON；
- `/api/reports`：归档索引；
- `/health`：服务及数据库健康状态。

使用 `python -m market_web --help` 可调整监听地址、端口、数据库和行情配置路径。
默认只监听 `127.0.0.1`，且保持单进程运行，以保证本地通达信插件访问与每日首次
生成逻辑一致。

### 5. 获取财经新闻

```powershell
finance-news
# 或：python -m finance_news
```

默认采集当天新浪财经和东方财富快讯，保存到 `data/news/`。

## 测试

```powershell
python -m pytest
```

测试只覆盖无需外部网络和通达信客户端的核心逻辑；真实数据源应在本机环境单独验证。

## 数据口径

- A 股、ETF、指数和商品期货来自通达信。
- 美股历史数据来自 Yahoo Finance，当日报价来自 Alpha Vantage。
- 加密资产历史数据来自 Coinbase，当日报价来自 Kraken。
- “三年价格分位”反映历史价格位置，不等同于 PE、PB 等估值指标。
- 商品期货使用具体合约代码，临近到期时需在配置中切换主力合约。
