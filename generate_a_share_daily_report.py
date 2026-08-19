"""生成包含个股、行业 ETF、主要指数与三市市场宽度的 Markdown 日报。"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from get_midea_daily_data import load_tq


STOCKS = {"000333.SZ": "美的集团"}
ETFS = {
    "512880.SH": "证券ETF",
    "512010.SH": "医药ETF",
    "512480.SH": "半导体ETF",
    "512660.SH": "军工ETF",
    "512690.SH": "酒ETF",
    "516160.SH": "新能源ETF",
}
INDICES = {
    "000001.SH": "上证综指",
    "399001.SZ": "深证成指",
    "000300.SH": "沪深300",
    "399006.SZ": "创业板指",
    "000016.SH": "上证50",
    "000688.SH": "科创50",
    "000905.SH": "中证500",
    "000852.SH": "中证1000",
    "932000.CSI": "中证2000",
}
MARKETS = {
    "000001.SH": "沪市",
    "399001.SZ": "深市",
    "899050.BJ": "北交所",
}
US_TECH_GIANTS = {
    "AAPL": "苹果",
    "MSFT": "微软",
    "GOOGL": "Alphabet（谷歌）",
    "AMZN": "亚马逊",
    "META": "Meta",
    "NVDA": "英伟达",
    "TSLA": "特斯拉",
}
CRYPTO_PAIRS = {
    "XBTUSD": "比特币 BTC",
    "ETHUSD": "以太坊 ETH",
    "SOLUSD": "Solana SOL",
    "XRPUSD": "瑞波币 XRP",
}
KLINE_FIELDS = ["Open", "High", "Low", "Close", "Volume", "Amount"]
SNAPSHOT_FIELDS = ["Amount", "UpHome", "DownHome", "ErrorId"]


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成每日行情 Markdown 日报")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("a_share_daily_report.md"),
        help="Markdown 报告保存路径（默认：a_share_daily_report.md）",
    )
    return parser.parse_args()


def latest_rows(data: dict[str, pd.DataFrame], names: dict[str, str]) -> list[dict[str, Any]]:
    """从两根日线中提取最新一根，并计算相对前收盘的涨跌幅。"""
    rows: list[dict[str, Any]] = []
    for code, name in names.items():
        close = data["Close"][code].dropna()
        if close.empty:
            rows.append({"名称": name, "代码": code, "状态": "无有效日线数据"})
            continue

        date = close.index[-1]
        previous_close = close.iloc[-2] if len(close) > 1 else None
        change_pct = None
        if previous_close and previous_close != 0:
            change_pct = (close.iloc[-1] / previous_close - 1) * 100
        rows.append(
            {
                "日期": date.strftime("%Y-%m-%d"),
                "名称": name,
                "代码": code,
                "开盘": data["Open"].at[date, code],
                "最高": data["High"].at[date, code],
                "最低": data["Low"].at[date, code],
                "收盘": close.iloc[-1],
                "涨跌幅(%)": change_pct,
                "成交量": data["Volume"].at[date, code],
                "成交额(万元)": data["Amount"].at[date, code],
            }
        )
    return rows


def fetch_kline_rows(tq: Any, names: dict[str, str]) -> list[dict[str, Any]]:
    data = tq.get_market_data(
        field_list=KLINE_FIELDS,
        stock_list=list(names),
        period="1d",
        count=2,
        dividend_type="none",
        fill_data=False,
    )
    if not data or "Close" not in data:
        raise RuntimeError("通达信未返回日线数据。")
    return latest_rows(data, names)


def fetch_market_breadth(tq: Any) -> dict[str, Any]:
    snapshots = {code: tq.get_market_snapshot(code, SNAPSHOT_FIELDS) for code in MARKETS}
    result: dict[str, Any] = {}
    for code, market_name in MARKETS.items():
        snapshot = snapshots[code]
        if snapshot.get("ErrorId") != "0":
            raise RuntimeError(f"未能获取{market_name}市场快照：{snapshot}")
        result[market_name] = {
            "amount": float(snapshot["Amount"]),
            "up": int(snapshot["UpHome"]),
            "down": int(snapshot["DownHome"]),
        }
    result["三市合计"] = {
        "amount": sum(item["amount"] for item in result.values()),
        "up": sum(item["up"] for item in result.values()),
        "down": sum(item["down"] for item in result.values()),
    }
    return result


def read_json(url: str) -> dict[str, Any]:
    """读取公开 JSON 接口响应。"""
    request = urllib.request.Request(url, headers={"User-Agent": "daily-market-report/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def fetch_us_tech_giants() -> tuple[list[dict[str, Any]], list[str]]:
    """获取美股七巨头最近一个交易日的日线；接口受限时不影响整份报告。"""
    api_key = os.getenv("ALPHAVANTAGE_API_KEY")
    if not api_key:
        return [], ["未读取到环境变量 ALPHAVANTAGE_API_KEY，未获取美股七巨头日线。"]

    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    symbols = list(US_TECH_GIANTS.items())
    for index, (symbol, name) in enumerate(symbols):
        params = urllib.parse.urlencode(
            {"function": "TIME_SERIES_DAILY", "symbol": symbol, "outputsize": "compact", "apikey": api_key}
        )
        try:
            payload = read_json(f"https://www.alphavantage.co/query?{params}")
            series = payload.get("Time Series (Daily)", {})
            if not series:
                message = payload.get("Note") or payload.get("Information") or payload.get("Error Message") or "接口未返回日线数据"
                warnings.append(f"{symbol}：{message}")
                continue

            dates = sorted(series, reverse=True)
            latest_date = dates[0]
            latest = series[latest_date]
            close = float(latest["4. close"])
            previous_close = float(series[dates[1]]["4. close"]) if len(dates) > 1 else None
            rows.append(
                {
                    "名称": name,
                    "代码": symbol,
                    "日期": latest_date,
                    "收盘": close,
                    "涨跌幅(%)": (close / previous_close - 1) * 100 if previous_close else None,
                    "开盘": float(latest["1. open"]),
                    "最高": float(latest["2. high"]),
                    "最低": float(latest["3. low"]),
                    "成交量": int(float(latest["5. volume"])),
                }
            )
        except Exception as exc:
            warnings.append(f"{symbol}：获取失败（{exc}）。")

        # Alpha Vantage 免费接口存在访问频率限制。
        if index < len(symbols) - 1:
            time.sleep(1.1)
    return rows, warnings


def fetch_crypto_prices() -> tuple[list[dict[str, Any]], list[str]]:
    """从 Kraken 公共行情接口获取主要虚拟货币的 USD 报价。"""
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    for pair, name in CRYPTO_PAIRS.items():
        try:
            url = f"https://api.kraken.com/0/public/Ticker?{urllib.parse.urlencode({'pair': pair})}"
            payload = read_json(url)
            errors = payload.get("error", [])
            result = payload.get("result", {})
            if errors or not result:
                warnings.append(f"{pair}：{'；'.join(errors) if errors else '接口未返回报价'}。")
                continue
            ticker = next(iter(result.values()))
            last_price = float(ticker["c"][0])
            open_price = float(ticker["o"])
            rows.append(
                {
                    "名称": name,
                    "代码": pair,
                    "收盘": last_price,
                    "涨跌幅(%)": (last_price / open_price - 1) * 100 if open_price else None,
                    "成交量": float(ticker["v"][1]),
                }
            )
        except Exception as exc:
            warnings.append(f"{pair}：获取失败（{exc}）。")
    return rows, warnings


def number(value: Any, decimals: int = 2) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{float(value):,.{decimals}f}"


def percent(value: Any) -> str:
    if value is None or pd.isna(value):
        return "—"
    marker = " ⚠️" if abs(float(value)) > 20 else ""
    return f"{float(value):+.2f}%{marker}"


def markdown_table(rows: list[dict[str, Any]]) -> str:
    headers = ["名称", "代码", "收盘", "涨跌幅", "开盘", "最高", "最低", "成交额（万元）"]
    body = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for row in rows:
        if "状态" in row:
            body.append(f"| {row['名称']} | {row['代码']} | {row['状态']} | — | — | — | — | — |")
            continue
        body.append(
            "| "
            + " | ".join(
                [
                    row["名称"],
                    row["代码"],
                    number(row["收盘"]),
                    percent(row["涨跌幅(%)"]),
                    number(row["开盘"]),
                    number(row["最高"]),
                    number(row["最低"]),
                    number(row["成交额(万元)"]),
                ]
            )
            + " |"
        )
    return "\n".join(body)


def us_stock_markdown_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "暂无可用的美股日线数据。"
    body = [
        "| 名称 | 代码 | 交易日 | 收盘（USD） | 涨跌幅 | 开盘 | 最高 | 最低 | 成交量 |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        body.append(
            f"| {row['名称']} | {row['代码']} | {row['日期']} | {number(row['收盘'])} | "
            f"{percent(row['涨跌幅(%)'])} | {number(row['开盘'])} | {number(row['最高'])} | "
            f"{number(row['最低'])} | {row['成交量']:,} |"
        )
    return "\n".join(body)


def crypto_markdown_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "暂无可用的虚拟货币报价。"
    body = [
        "| 资产 | 交易对 | 最新价（USD） | 24h 变动 | 24h 成交量（币） | 数据源 |",
        "|---|---|---:|---:|---:|---|",
    ]
    for row in rows:
        body.append(
            f"| {row['名称']} | {row['代码']} | {number(row['收盘'])} | "
            f"{percent(row['涨跌幅(%)'])} | {number(row['成交量'])} | Kraken |"
        )
    return "\n".join(body)


def render_report(
    stock_rows: list[dict[str, Any]],
    etf_rows: list[dict[str, Any]],
    index_rows: list[dict[str, Any]],
    breadth: dict[str, Any],
    us_stock_rows: list[dict[str, Any]],
    crypto_rows: list[dict[str, Any]],
    external_warnings: list[str],
    generated_at: datetime,
) -> str:
    report_date = max(
        row["日期"] for row in stock_rows + etf_rows + index_rows if "日期" in row
    )
    total = breadth["三市合计"]
    breadth_rows = []
    for market_name in ["沪市", "深市", "北交所", "三市合计"]:
        item = breadth[market_name]
        breadth_rows.append(
            f"| {market_name} | {number(item['amount'])} | {number(item['amount'] / 10_000)} | {item['up']:,} | {item['down']:,} |"
        )

    report = f"""# 每日行情报告（A 股 / 美股 / 虚拟货币）

> **数据日期：{report_date}**  
> 生成时间：{generated_at:%Y-%m-%d %H:%M:%S}（通达信客户端快照）

## 市场概览

| 指标 | 数值 |
|---|---:|
| 沪深北三市成交额 | **{number(total['amount'] / 10_000)} 亿元** |
| 上涨家数 | **{total['up']:,}** |
| 下跌家数 | **{total['down']:,}** |

## 1. 个股：美的集团

{markdown_table(stock_rows)}

## 2. 代表性行业 ETF

{markdown_table(etf_rows)}

## 3. 主要大盘指数

{markdown_table(index_rows)}

## 4. 沪深北三市市场宽度

| 市场 | 成交额（万元） | 成交额（亿元） | 上涨家数 | 下跌家数 |
|---|---:|---:|---:|---:|
{chr(10).join(breadth_rows)}

## 5. 美股七巨头（最近一个美股交易日）

{us_stock_markdown_table(us_stock_rows)}

## 6. 主要虚拟货币（实时交易所报价）

{crypto_markdown_table(crypto_rows)}

## 数据口径与提示

- “三市成交额”是沪市、深市和北交所快照的成交金额汇总，**不等于资金净流入**。
- 上涨/下跌家数来自各市场快照，报告生成后盘中数值会继续变化；日终运行更适合作为当日记录。
- 个股、ETF 与指数的价格数据为日线；成交额单位为万元。
- 涨跌幅以最新日线收盘价相对于前一交易日收盘价计算。带 ⚠️ 的数值表示绝对涨跌幅超过 20%，应先核验本地历史缓存再据此分析。
- 美股七巨头为 Alpha Vantage 最近一个美股交易日的日线，币种为美元；美股交易日可能与 A 股报告日期不同。
- 虚拟货币为 Kraken 交易所的 USD 报价；24h 变动按其返回的开盘价计算，价格会持续变化。
"""
    if external_warnings:
        report += "\n## 外部接口状态\n\n" + "\n".join(f"- {warning}" for warning in external_warnings) + "\n"
    return report


def main() -> None:
    args = parse_arguments()
    tq = load_tq()
    tq.initialize(str(Path(__file__).resolve()))
    try:
        stock_rows = fetch_kline_rows(tq, STOCKS)
        etf_rows = fetch_kline_rows(tq, ETFS)
        index_rows = fetch_kline_rows(tq, INDICES)
        breadth = fetch_market_breadth(tq)
    finally:
        tq.close()

    us_stock_rows, us_warnings = fetch_us_tech_giants()
    crypto_rows, crypto_warnings = fetch_crypto_prices()
    report = render_report(
        stock_rows,
        etf_rows,
        index_rows,
        breadth,
        us_stock_rows,
        crypto_rows,
        us_warnings + crypto_warnings,
        datetime.now(),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(f"报告已生成：{args.output.resolve()}")


if __name__ == "__main__":
    main()
