# ADR 0001: 本地 FastAPI 与 SQLite

## Status

Accepted

## Context

报告生成依赖本机通达信客户端和 Python 插件。云端运行时无法直接访问该本地数据源。

## Decision

网站采用本地 FastAPI B/S 服务，SQLite 永久保存每日快照和 Markdown。默认单进程、仅监听 `127.0.0.1`。

## Consequences

- 浏览器与服务端职责清晰，进程重启不会丢失报告。
- 需要运行本机服务且通达信仅在每日首次生成时可用。
- 未来若改用云端行情源，可保持 HTTP 和存储接口后替换采集层。
