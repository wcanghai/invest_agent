"""多市场历史日线的只读获取。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from daily_report.data_sources.external import read_json
from daily_report.data_sources.tdx import KLINE_FIELDS


def fetch_tdx_history(
    tq: Any, names: dict[str, str], years: int = 5
) -> dict[str, pd.DataFrame]:
    if not names:
        return {}
    data = tq.get_market_data(
        field_list=KLINE_FIELDS,
        stock_list=list(names),
        period="1d",
        count=years * 260 + 40,
        dividend_type="none",
        fill_data=False,
    )
    if not data or "Close" not in data:
        raise RuntimeError("通达信未返回历史日线数据。")
    result: dict[str, pd.DataFrame] = {}
    for code in names:
        close = data["Close"][code].dropna()
        if close.empty:
            continue
        result[code] = pd.DataFrame(
            {
                "date": close.index.strftime("%Y-%m-%d"),
                "open": data["Open"].loc[close.index, code].values,
                "high": data["High"].loc[close.index, code].values,
                "low": data["Low"].loc[close.index, code].values,
                "close": close.values,
                "volume": data["Volume"].loc[close.index, code].values,
                "amount": data["Amount"].loc[close.index, code].values,
            }
        )
    return result


def fetch_yahoo_history(code: str, years: int = 5) -> pd.DataFrame:
    now = datetime.now(timezone.utc)
    start = int((now - timedelta(days=years * 366)).timestamp())
    payload = read_json(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{code}"
        f"?period1={start}&period2={int(now.timestamp())}&interval=1d"
    )
    chart = payload.get("chart", {})
    result = chart.get("result") or []
    if not result:
        raise RuntimeError(chart.get("error", {}).get("description", "Yahoo Finance 未返回历史日线"))
    series = result[0]
    quote = series["indicators"]["quote"][0]
    timestamps = series.get("timestamp", [])
    return pd.DataFrame(
        {
            "date": [datetime.fromtimestamp(item, tz=timezone.utc).strftime("%Y-%m-%d") for item in timestamps],
            "open": quote.get("open", []), "high": quote.get("high", []),
            "low": quote.get("low", []), "close": quote.get("close", []),
            "volume": quote.get("volume", []), "amount": None,
        }
    )


def fetch_coinbase_history(pair: str, years: int = 5) -> pd.DataFrame:
    product = pair.replace("XBT", "BTC")[:-3] + "-USD"
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=years * 366)
    step = timedelta(days=290)
    candles: list[list[float]] = []
    cursor = start
    while cursor < end:
        next_cursor = min(cursor + step, end)
        data = read_json(
            f"https://api.exchange.coinbase.com/products/{product}/candles"
            f"?start={cursor.strftime('%Y-%m-%dT%H:%M:%SZ')}"
            f"&end={next_cursor.strftime('%Y-%m-%dT%H:%M:%SZ')}&granularity=86400"
        )
        if not isinstance(data, list):
            raise RuntimeError(f"Coinbase 未返回 {product} 的历史日线")
        candles.extend(data)
        cursor = next_cursor
    return pd.DataFrame(
        [
            {
                "date": datetime.fromtimestamp(item[0], tz=timezone.utc).strftime("%Y-%m-%d"),
                "low": item[1], "high": item[2], "open": item[3],
                "close": item[4], "volume": item[5], "amount": None,
            }
            for item in candles
        ]
    )
