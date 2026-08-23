# 多市场投资数据工具

项目只保留两个业务域：`daily_report` 构建和展示每日投资日报，`tdx_data` 独立归档通达信股票数据。行情、新闻、报告快照统一由 SQLite 管理，不再使用 CSV 缓存。

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
│  ├─ client.py                  # TQ 连接和只读接口适配
│  ├─ field_mapping.py           # 通达信字段中文映射
│  └─ repository.py              # TDX 专用 SQLite 表和写入操作
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

## 安装与命令

```powershell
python -m pip install -e ".[dev]"

market-cache --years 5
market-report
finance-news
market-web --host 127.0.0.1 --port 8000

tdx-full-archive --limit 10
tdx-extra-data --sample-only
```

对应模块入口也可直接运行：`python -m daily_report`、`python -m daily_report.cache_cli`、`python -m daily_report.news_cli`、`python -m daily_report.web`、`python -m tdx_data` 和 `python -m tdx_data.additional_data`。

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
