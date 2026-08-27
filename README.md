# 多市场投资数据工具

项目包含三个独立业务域：`daily_report` 构建和展示每日投资日报，`tdx_data` 归档通达信完整数据，`quant_value` 获取研究子集并构建时点一致的股票/ETF 量化价值因子。各域使用独立 SQLite，不再使用 CSV 缓存。

## 最终目录

```text
invest_202608/
├─ daily_report/                 # 日报业务域
│  ├─ data_sources/              # 通达信、公开市场、新闻和发行数据采集
│  ├─ storage/                   # 日报统一 SQLite 的表结构与 Repository
│  ├─ web/                       # FastAPI、HTML 模板和静态资源
│  ├─ cache_cli.py               # 同步近年历史行情
│  ├─ cli.py                     # 生成 Markdown 日报
│  ├─ config.py                  # 读取并校验标的配置
│  ├─ models.py                  # 报告快照和持久化记录模型
│  ├─ news_cli.py                # 采集并保存财经新闻
│  ├─ rendering.py               # Markdown 渲染
│  └─ service.py                 # 日报采集、指标计算和渲染编排
├─ tdx_data/                     # 独立的通达信完整归档业务域
│  ├─ additional_data.py         # 核心归档之外的只读接口、说明和样例
│  ├─ archive_service.py         # 股票遍历与增量归档流程
│  ├─ cli.py                     # 完整归档命令入口
│  ├─ incremental_cli.py         # 从现有标的执行每日增量
│  ├─ client.py                  # TQ 连接和只读接口适配
│  ├─ field_mapping.py           # 通达信字段中文映射
│  ├─ history_service.py         # 历史财报、股本和指标时点一致读取
│  ├─ quant_wide_service.py      # 时点一致的量化日频宽表构建
│  ├─ quant_wide_cli.py          # 宽表全量/区间重建命令
│  └─ repository.py              # TDX 专用 SQLite 表和写入操作
├─ quant_value/                  # 独立量化价值研究业务域
│  ├─ gateway.py                 # 通达信只读接口适配
│  ├─ repository.py              # 研究专用 SQLite 与时点事实表
│  ├─ service.py                 # 全量/增量采集编排
│  ├─ factors.py                 # 股票/ETF 日频因子宽表
│  ├─ verify.py                  # 数据覆盖和可计算性验证
│  └─ representative_universe.json # 多行业股票和多类 ETF 样本
├─ config/market_universe.json   # 日报关注标的
├─ data/                         # 本地 SQLite 数据（Git 忽略）
├─ docs/                         # 当前架构的生命周期文档
├─ reports/                      # 命令行生成的 Markdown（Git 忽略）
├─ tests/                        # 按两个业务域划分的离线测试
├─ AGENTS.md                     # 仓库协作约定
└─ pyproject.toml                # 依赖、包发现和命令入口
```

## 数据库

`data/daily_report.sqlite3` 是日报唯一数据库：

- `instruments`：配置标的和顺序；
- `market_bars`：多市场历史日线，按“分类、代码、日期”去重；
- `news_items`：新浪财经、东方财富新闻，按“来源、时间、标题”去重；
- `daily_reports`：每天第一份成功生成的 Markdown 和结构化快照；
- `sync_runs`：数据同步审计记录。

`data/tdx_archive.sqlite3` 只属于 `tdx_data`，保存股票日线、完整原始接口记录、平铺字段、板块关系、字段字典和归档运行记录。两个数据库分离，避免日报读写与大体量 TDX 归档互相影响。

`data/quant_value.sqlite3` 只属于 `quant_value`，保存代表性研究池的行情、公告日历史财务、股本、公司行动、ETF IOPV 快照及股票/ETF 日频因子。它不读取前两个数据库，便于独立重建和避免研究口径隐式耦合。

## 安装与命令

```powershell
python -m pip install -e ".[dev]"

market-cache --years 5
market-report
finance-news
market-web --host 127.0.0.1 --port 8000

tdx-full-archive --limit 10
tdx-full-archive --target-universe --etf-limit 120 --limit 0
tdx-daily-update
tdx-build-quant-wide
tdx-extra-data --sample-only
quant-value sync --start 2016-01-01
quant-value build --rebuild
quant-value verify
```

对应模块入口也可直接运行：`python -m daily_report`、`python -m daily_report.cache_cli`、`python -m daily_report.news_cli`、`python -m daily_report.web`、`python -m tdx_data`、`python -m tdx_data.incremental_cli`、`python -m tdx_data.quant_wide_cli` 和 `python -m tdx_data.additional_data`。

本地通达信插件默认读取 `D:\SoftWare\TDX\PYPlugins\user`；也可设置 `TDX_USER_DIR`，完整归档命令还支持 `--tdx-user-dir`。

## 日报处理逻辑

1. `market-cache` 从 TDX、Yahoo Chart 和 Coinbase 同步历史行情到 SQLite。
2. `market-report` 获取最新行情和发行事件，将最新行情幂等写入同一数据库，并直接用 SQL 计算三年价格分位。
3. `finance-news` 采集新闻并写入 `news_items`，为后续日报新闻章节准备数据；当前渲染暂未展示新闻。
4. `market-web` 在当天第一次请求时生成并永久保存日报；同日后续请求和服务重启均读取已有记录。

## 验证

```powershell
python -m pytest -q -p no:cacheprovider --basetemp .test-tmp
git diff --check
```

数据库、WAL/SHM、报告、缓存、凭据和 Python 字节码均不得提交。
