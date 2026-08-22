# Requirement: 仓库结构与统一功能入口整理

## Background

仓库已包含日报、日报网站、财经新闻、通达信日线和股票全维度采集等功能。独立命令可用，
但新增股票采集模块仍平铺在 `tdx_history` 根目录，配置和生命周期文档也缺少统一导航。

## Goals

- 让目录边界与业务功能一致。
- 提供一个可发现全部功能的统一命令，同时保留现有命令兼容性。
- 为配置、文档和运行产物建立清晰说明。
- 将当前已完成的新股新债日历和股票全维度采集作为一个可测试版本提交 GitHub。

## Functional Requirements

1. 股票全维度采集代码归入独立子包。
2. 新增 `invest-tools` 总入口，支持报告、缓存、网站、新闻、日线、配置生成和股票全维度采集。
3. 旧的 console scripts 和 `python -m <package>` 入口继续工作。
4. 配置目录和文档目录提供索引，明确源配置、生成配置和本地运行产物。
5. SQLite、缓存、报告、凭据和字节码不得进入 Git 提交。

## Non-Functional Requirements

- 不改变既有业务 API 和数据库 schema。
- 统一入口只负责路由，不耦合具体业务实现。
- 测试保持离线，不访问真实 TDX 或外部网络。

## Out Of Scope

- 将多个业务包合并成单体模块。
- 删除旧命令。
- 上传本地 SQLite 或真实采集结果。
- 发布到 PyPI 或部署公开服务。

## Acceptance Criteria

1. `invest-tools --help` 能列出全部主要功能。
2. `invest-tools <command> --help` 能转发到原命令。
3. `tdx-stock-data --help` 仍可用。
4. 全仓库测试与 `git diff --check` 通过。
5. 提交只包含代码、测试、文档和可维护配置。

## Risks

- 模块移动可能破坏导入路径或 console script。
- 当前分支领先远程的既有提交也会随 push 一并发布。

## Readiness

Ready for design。
