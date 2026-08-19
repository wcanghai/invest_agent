"""Markdown 日报渲染。"""

from __future__ import annotations

from datetime import datetime
from typing import Any


def number(value: Any, decimals: int = 2) -> str:
    if value is None:
        return "—"
    return f"{float(value):,.{decimals}f}"


def percent(value: Any) -> str:
    if value is None:
        return "—"
    marker = " ⚠️" if abs(float(value)) > 20 else ""
    return f"{float(value):+.2f}%{marker}"


def a_share_table(rows: list[dict[str, Any]]) -> str:
    body = ["| 名称 | 代码 | 收盘 | 涨跌幅 | 开盘 | 最高 | 最低 | 成交额（万元） |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    for row in rows:
        if "status" in row:
            body.append(f"| {row['name']} | {row['code']} | {row['status']} | — | — | — | — | — |")
            continue
        body.append(
            f"| {row['name']} | {row['code']} | {number(row['close'])} | {percent(row['change_pct'])} | "
            f"{number(row['open'])} | {number(row['high'])} | {number(row['low'])} | {number(row['amount'])} |"
        )
    return "\n".join(body)


def us_stock_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "暂无可用的美股日线数据。"
    body = ["| 名称 | 代码 | 交易日 | 收盘（USD） | 涨跌幅 | 开盘 | 最高 | 最低 | 成交量 |", "|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for row in rows:
        body.append(
            f"| {row['name']} | {row['code']} | {row['date']} | {number(row['close'])} | {percent(row['change_pct'])} | "
            f"{number(row['open'])} | {number(row['high'])} | {number(row['low'])} | {row['volume']:,} |"
        )
    return "\n".join(body)


def crypto_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "暂无可用的虚拟货币报价。"
    body = ["| 资产 | 交易对 | 最新价（USD） | 24h 变动 | 24h 成交量（币） | 数据源 |", "|---|---|---:|---:|---:|---|"]
    for row in rows:
        body.append(f"| {row['name']} | {row['code']} | {number(row['close'])} | {percent(row['change_pct'])} | {number(row['volume'])} | Kraken |")
    return "\n".join(body)


def render(
    stock_rows: list[dict[str, Any]], etf_rows: list[dict[str, Any]], index_rows: list[dict[str, Any]],
    breadth: dict[str, dict[str, float | int]], us_rows: list[dict[str, Any]], crypto_rows: list[dict[str, Any]],
    warnings: list[str], generated_at: datetime,
) -> str:
    dated_rows = [row for row in stock_rows + etf_rows + index_rows if "date" in row]
    report_date = max(row["date"] for row in dated_rows) if dated_rows else generated_at.strftime("%Y-%m-%d")
    total = breadth["三市合计"]
    breadth_rows = "\n".join(
        f"| {name} | {number(breadth[name]['amount'])} | {number(breadth[name]['amount'] / 10_000)} | {breadth[name]['up']:,} | {breadth[name]['down']:,} |"
        for name in [*list(breadth.keys())[:-1], "三市合计"]
    )
    report = f"""# 每日行情报告（A 股 / 美股 / 虚拟货币）

> **A 股数据日期：{report_date}**  
> 生成时间：{generated_at:%Y-%m-%d %H:%M:%S}（Asia/Shanghai）

## 市场概览

| 指标 | 数值 |
|---|---:|
| 沪深北三市成交额 | **{number(total['amount'] / 10_000)} 亿元** |
| 上涨家数 | **{total['up']:,}** |
| 下跌家数 | **{total['down']:,}** |

## 1. A 股股票

{a_share_table(stock_rows)}

## 2. 代表性行业 ETF

{a_share_table(etf_rows)}

## 3. 主要 A 股指数

{a_share_table(index_rows)}

## 4. 沪深北三市市场宽度

| 市场 | 成交额（万元） | 成交额（亿元） | 上涨家数 | 下跌家数 |
|---|---:|---:|---:|---:|
{breadth_rows}

## 5. 配置的美股（最近一个美股交易日）

{us_stock_table(us_rows)}

## 6. 配置的虚拟货币（实时交易所报价）

{crypto_table(crypto_rows)}

## 数据口径与提示

- A 股价格、ETF、指数与市场宽度均来自通达信本地 `tqcenter` 接口；成交额单位为万元。
- 三市成交额为市场快照的成交金额汇总，**不等于资金净流入**；上涨/下跌家数在盘中会继续变化。
- 美股日线来自 Alpha Vantage，币种为美元，交易日可能与 A 股日期不同。
- 虚拟货币来自 Kraken USD 交易对；24h 变动按该交易所返回的开盘价计算，价格会持续变化。
"""
    if warnings:
        report += "\n## 外部接口状态\n\n" + "\n".join(f"- {warning}" for warning in warnings) + "\n"
    return report
