"""Markdown 日报渲染。"""

from __future__ import annotations

from datetime import datetime
from typing import Any


MARKET_INDEX_CODES = {
    "沪市": "000001.SH",
    "深市": "399001.SZ",
    "北交所": "899050.BJ",
}


def eastmoney_quote_url(code: str, *, index: bool = False) -> str:
    """根据证券代码生成东方财富行情页地址。"""
    symbol, _, exchange = code.upper().partition(".")
    if index:
        if code.upper() == "932000.CSI":
            return "https://quote.eastmoney.com/zz/2.932000.html"
        if code.upper() == "899050.BJ":
            return "https://quote.eastmoney.com/q/0.899050.html"
        return f"https://quote.eastmoney.com/zs{symbol}.html"

    prefixes = {"SH": "sh", "SZ": "sz", "BJ": "bj"}
    if exchange not in prefixes:
        raise ValueError(f"不支持生成东方财富链接的证券代码：{code}")
    return f"https://quote.eastmoney.com/{prefixes[exchange]}{symbol}.html"


def eastmoney_link(code: str, *, index: bool = False) -> str:
    return f"[查看]({eastmoney_quote_url(code, index=index)})"


def number(value: Any, decimals: int = 2) -> str:
    if value is None:
        return "—"
    return f"{float(value):,.{decimals}f}"


def percent(value: Any) -> str:
    if value is None:
        return "—"
    marker = " ⚠️" if abs(float(value)) > 20 else ""
    return f"{float(value):+.2f}%{marker}"


def percentile(value: Any) -> str:
    """历史价格分位不是涨跌幅，不附加异常涨跌标记。"""
    if value is None:
        return "—"
    return f"{float(value):.2f}%"


def a_share_table(rows: list[dict[str, Any]], *, index: bool = False) -> str:
    body = ["| 名称 | 代码 | 收盘 | 涨跌幅 | 三年价格分位 | 价格位置 | 开盘 | 最高 | 最低 | 成交额（万元） | 东方财富 |", "|---|---|---:|---:|---:|---|---:|---:|---:|---:|---|"]
    for row in rows:
        quote_link = eastmoney_link(row["code"], index=index)
        if "status" in row:
            body.append(f"| {row['name']} | {row['code']} | {row['status']} | — | — | — | — | — | — | — | {quote_link} |")
            continue
        body.append(
            f"| {row['name']} | {row['code']} | {number(row['close'])} | {percent(row['change_pct'])} | "
            f"{percentile(row.get('three_year_percentile'))} | {row.get('price_position', '—')} | {number(row['open'])} | "
            f"{number(row['high'])} | {number(row['low'])} | {number(row['amount'])} | {quote_link} |"
        )
    return "\n".join(body)


def us_stock_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "暂无可用的美股日线数据。"
    body = ["| 名称 | 代码 | 交易日 | 收盘（USD） | 涨跌幅 | 三年价格分位 | 价格位置 | 开盘 | 最高 | 最低 | 成交量 |", "|---|---|---|---:|---:|---:|---|---:|---:|---:|---:|"]
    for row in rows:
        body.append(
            f"| {row['name']} | {row['code']} | {row['date']} | {number(row['close'])} | {percent(row['change_pct'])} | "
            f"{percentile(row.get('three_year_percentile'))} | {row.get('price_position', '—')} | {number(row['open'])} | "
            f"{number(row['high'])} | {number(row['low'])} | {row['volume']:,} |"
        )
    return "\n".join(body)


def crypto_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "暂无可用的虚拟货币报价。"
    body = ["| 资产 | 交易对 | 最新价（USD） | 24h 变动 | 三年价格分位 | 价格位置 | 24h 成交量（币） | 数据源 |", "|---|---|---:|---:|---:|---|---:|---|"]
    for row in rows:
        body.append(
            f"| {row['name']} | {row['code']} | {number(row['close'])} | {percent(row['change_pct'])} | "
            f"{percentile(row.get('three_year_percentile'))} | {row.get('price_position', '—')} | {number(row['volume'])} | Kraken |"
        )
    return "\n".join(body)


def futures_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "暂无可用的商品期货日线数据。"
    body = ["| 合约 | 代码 | 收盘（合约报价） | 涨跌幅 | 三年价格分位 | 价格位置 | 开盘 | 最高 | 最低 | 成交额（万元） |", "|---|---|---:|---:|---:|---|---:|---:|---:|---:|"]
    for row in rows:
        if "status" in row:
            body.append(f"| {row['name']} | {row['code']} | {row['status']} | — | — | — | — | — | — | — |")
            continue
        body.append(
            f"| {row['name']} | {row['code']} | {number(row['close'])} | {percent(row['change_pct'])} | "
            f"{percentile(row.get('three_year_percentile'))} | {row.get('price_position', '—')} | {number(row['open'])} | "
            f"{number(row['high'])} | {number(row['low'])} | {number(row['amount'])} |"
        )
    return "\n".join(body)


def offering_table(rows: list[dict[str, Any]]) -> str:
    """渲染近期新股、新债申购与上市事件。"""
    if not rows:
        return "观察窗口内暂无新股、新债申购或上市事件。"
    body = [
        "| 状态 | 类型 | 名称（证券代码） | 申购代码 | 申购日 | 发行价 | 申购上限 | 发行 PE / 评级 | 中签率 | 上市日 | 正股 / 发行规模 | 来源 |",
        "|---|---|---|---|---|---:|---:|---:|---:|---|---|---|",
    ]
    for row in rows:
        name = row.get("name") or "—"
        security = row.get("security_code") or "—"
        pe_or_rating = row.get("rating") or number(row.get("issue_pe"))
        underlying_parts = [
            part
            for part in (row.get("underlying_name"), row.get("underlying_code"))
            if part
        ]
        if row.get("issue_size") is not None:
            underlying_parts.append(f"{number(row['issue_size'])} 亿元")
        underlying = " / ".join(underlying_parts) or "—"
        winning_rate = (
            f"{float(row['winning_rate']):.6f}%"
            if row.get("winning_rate") is not None
            else "—"
        )
        sources = "、".join(row.get("sources") or []) or "—"
        max_subscription = number(row.get("max_subscription"))
        if row.get("max_subscription_unit") and max_subscription != "—":
            max_subscription = f"{max_subscription} {row['max_subscription_unit']}"
        body.append(
            f"| {row.get('event_status', '—')} | {row.get('kind', '—')} | {name}（{security}） | {row.get('subscription_code') or '—'} | "
            f"{row.get('subscription_date') or '—'} | {number(row.get('issue_price'))} | "
            f"{max_subscription} | {pe_or_rating} | {winning_rate} | "
            f"{row.get('listing_date') or '—'} | {underlying} | {sources} |"
        )
    return "\n".join(body)


def render(
    stock_rows: list[dict[str, Any]], etf_rows: list[dict[str, Any]], index_rows: list[dict[str, Any]],
    breadth: dict[str, dict[str, float | int]], futures_rows: list[dict[str, Any]], us_rows: list[dict[str, Any]], crypto_rows: list[dict[str, Any]],
    offering_rows: list[dict[str, Any]], warnings: list[str], generated_at: datetime,
) -> str:
    dated_rows = [row for row in stock_rows + etf_rows + index_rows if "date" in row]
    report_date = max(row["date"] for row in dated_rows) if dated_rows else generated_at.strftime("%Y-%m-%d")
    total = breadth["三市合计"]
    breadth_rows = "\n".join(
        f"| {name} | {number(breadth[name]['amount'])} | {number(breadth[name]['amount'] / 10_000)} | "
        f"{breadth[name]['up']:,} | {breadth[name]['down']:,} | "
        f"{eastmoney_link(MARKET_INDEX_CODES[name], index=True) if name in MARKET_INDEX_CODES else '—'} |"
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

{a_share_table(index_rows, index=True)}

## 4. 沪深北三市市场宽度

| 市场 | 成交额（万元） | 成交额（亿元） | 上涨家数 | 下跌家数 | 东方财富 |
|---|---:|---:|---:|---:|---|
{breadth_rows}

## 5. 重要商品期货

{futures_table(futures_rows)}

## 6. 配置的美股（最近一个美股交易日）

{us_stock_table(us_rows)}

## 7. 配置的虚拟货币（实时交易所报价）

{crypto_table(crypto_rows)}

## 8. 新股新债日历

> 展示今天至未来 14 天的申购事件，以及最近 3 天至未来 14 天的上市事件。

{offering_table(offering_rows)}

## 数据口径与提示

- A 股价格、ETF、指数与市场宽度均来自通达信本地 `tqcenter` 接口；成交额单位为万元。
- A 股股票、ETF、指数与市场宽度表中的“东方财富”链接指向对应的公开行情页面。
- 三市成交额为市场快照的成交金额汇总，**不等于资金净流入**；上涨/下跌家数在盘中会继续变化。
- 美股日线来自 Alpha Vantage，币种为美元，交易日可能与 A 股日期不同。
- 虚拟货币来自 Kraken USD 交易对；24h 变动按该交易所返回的开盘价计算，价格会持续变化。
- 三年价格分位 = 最近三年缓存日线中，收盘价不高于当前价的比例；≤20% 标为“价格偏低”，≥80% 标为“价格偏高”，其余为“价格中性”。它反映价格历史位置，**不等同于 PE/PB 等基本面估值**。
- 商品期货采用配置中的具体合约，合约到期换月后需在配置中更新代码；若单一合约历史不足三年，不计算三年价格分位。
- 新股、新债当期申购信息来自通达信，东方财富公开数据用于补充中签率、正股、评级和上市日期；最终发行安排应以交易所及发行人公告为准。
"""
    if warnings:
        report += "\n## 外部接口状态\n\n" + "\n".join(f"- {warning}" for warning in warnings) + "\n"
    return report
