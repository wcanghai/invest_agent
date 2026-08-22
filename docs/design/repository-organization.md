# Design: 仓库结构与统一功能入口整理

## Requirement Link

`docs/requirements/repository-organization.md`

## Current System

仓库按 `market_report`、`market_web`、`finance_news`、`tdx_history` 划分业务包，结构总体合理。
问题集中在股票全维度模块平铺、多个入口缺少统一发现方式，以及配置/文档缺少索引。

## Proposed Architecture

```text
invest_tools/                 # 统一命令路由，不承载业务逻辑
finance_news/                 # 财经新闻
market_report/                # 数据采集、报告生成、新股新债日历
market_web/                   # 本地 HTTP 和页面
tdx_history/                  # 通达信历史数据域
  stock_data/                 # 股票全维度采集子域
config/                       # 可提交的输入配置与快照配置
docs/guides/                  # 面向使用者的功能指南
docs/{requirements,design,adr,tasks,release}/  # 生命周期材料
tests/                        # 离线测试
data/, reports/               # 本地生成，Git 忽略
```

## Interfaces

统一命令映射：

- `invest-tools report` → `market_report.cli`
- `invest-tools cache` → `market_report.cache_cli`
- `invest-tools web` → `market_web.cli`
- `invest-tools news` → `finance_news.cli`
- `invest-tools history` → `tdx_history.cli`
- `invest-tools history-config` → `tdx_history.config_builder`
- `invest-tools stock-data` → `tdx_history.stock_data.cli`

原有 console scripts 全部保留。统一入口用延迟导入转发剩余参数，避免导入一个命令时初始化
其他数据源。

## Configuration And Data

配置继续位于根级 `config/`，避免破坏默认路径。新增索引说明各文件用途。全 A 股专用配置
命名为 `tdx_a_share_history.json`，区别于同时包含 A 股和 ETF 的 `tdx_history.json`。

## Security And Permissions

不改变服务监听地址和权限；生成数据库、汇总 JSON、缓存与报告继续由 `.gitignore` 排除。

## Alternatives Considered

- 大规模移动所有业务包：收益有限且会产生大量兼容风险，不采用。
- 删除旧入口只保留统一入口：会破坏用户脚本，不采用。
- 保持现状只改 README：无法解决新增模块平铺和入口发现问题，不采用。

## Verification Strategy

- 单元测试统一入口路由和未知命令。
- 对统一入口及所有 console modules 执行 `--help` 冒烟测试。
- 运行全仓库 pytest、编译检查和 `git diff --check`。
