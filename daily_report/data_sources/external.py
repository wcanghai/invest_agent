"""美股和虚拟货币公开数据源。"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from typing import Any


def read_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "daily-market-report/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def fetch_us_daily(names: dict[str, str]) -> tuple[list[dict[str, Any]], list[str]]:
    """使用 Alpha Vantage 获取配置中的美股最近一个交易日日线。"""
    api_key = os.getenv("ALPHAVANTAGE_API_KEY")
    if not api_key:
        return [], ["未读取到环境变量 ALPHAVANTAGE_API_KEY，未获取美股日线。"]

    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    symbols = list(names.items())
    for index, (symbol, name) in enumerate(symbols):
        parameters = urllib.parse.urlencode(
            {"function": "TIME_SERIES_DAILY", "symbol": symbol, "outputsize": "compact", "apikey": api_key}
        )
        try:
            payload = read_json(f"https://www.alphavantage.co/query?{parameters}")
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
                    "name": name,
                    "code": symbol,
                    "date": latest_date,
                    "close": close,
                    "change_pct": (close / previous_close - 1) * 100 if previous_close else None,
                    "open": float(latest["1. open"]),
                    "high": float(latest["2. high"]),
                    "low": float(latest["3. low"]),
                    "volume": int(float(latest["5. volume"])),
                }
            )
        except Exception as error:  # 接口单标的失败不阻断日报。
            warnings.append(f"{symbol}：获取失败（{error}）。")
        if index < len(symbols) - 1:
            time.sleep(1.1)
    return rows, warnings


def fetch_crypto_quotes(names: dict[str, str]) -> tuple[list[dict[str, Any]], list[str]]:
    """使用 Kraken 无密钥公共接口获取配置中的 USD 加密资产报价。"""
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    for pair, name in names.items():
        try:
            parameters = urllib.parse.urlencode({"pair": pair})
            payload = read_json(f"https://api.kraken.com/0/public/Ticker?{parameters}")
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
                    "name": name,
                    "code": pair,
                    "close": last_price,
                    "change_pct": (last_price / open_price - 1) * 100 if open_price else None,
                    "volume": float(ticker["v"][1]),
                }
            )
        except Exception as error:  # 公共接口单标的失败不阻断日报。
            warnings.append(f"{pair}：获取失败（{error}）。")
    return rows, warnings
