"""通达信 TQ 数据源。"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd

KLINE_FIELDS = ["Open", "High", "Low", "Close", "Volume", "Amount"]
SNAPSHOT_FIELDS = ["Amount", "UpHome", "DownHome", "ErrorId"]
DEFAULT_TDX_USER_DIR = Path(r"D:\SoftWare\TDX\PYPlugins\user")


def load_tq():
    """加载通达信 TQ 插件；可用 ``TDX_USER_DIR`` 覆盖默认目录。"""
    user_dir = Path(os.getenv("TDX_USER_DIR", str(DEFAULT_TDX_USER_DIR))).expanduser()
    if not user_dir.is_dir():
        raise FileNotFoundError(
            f"未找到通达信 Python 插件目录：{user_dir}。"
            "请设置环境变量 TDX_USER_DIR。"
        )
    user_dir_text = str(user_dir)
    if user_dir_text not in sys.path:
        sys.path.insert(0, user_dir_text)
    from tqcenter import tq  # pylint: disable=import-outside-toplevel

    return tq


def latest_daily_rows(tq: Any, names: dict[str, str]) -> list[dict[str, Any]]:
    """读取两根日线，返回最新收盘、OHLC、成交量和成交额。"""
    if not names:
        return []
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

    rows: list[dict[str, Any]] = []
    for code, name in names.items():
        close = data["Close"][code].dropna()
        if close.empty:
            rows.append({"name": name, "code": code, "status": "无有效日线数据"})
            continue
        date = close.index[-1]
        previous_close = close.iloc[-2] if len(close) > 1 else None
        latest_close = close.iloc[-1]
        rows.append(
            {
                "name": name,
                "code": code,
                "date": date.strftime("%Y-%m-%d"),
                "open": data["Open"].at[date, code],
                "high": data["High"].at[date, code],
                "low": data["Low"].at[date, code],
                "close": latest_close,
                "change_pct": (latest_close / previous_close - 1) * 100 if previous_close else None,
                "volume": data["Volume"].at[date, code],
                "amount": data["Amount"].at[date, code],
            }
        )
    return rows


def market_breadth(tq: Any, markets: dict[str, str]) -> dict[str, dict[str, float | int]]:
    """获取沪深北等市场快照的成交额和上涨/下跌家数，并计算合计。"""
    result: dict[str, dict[str, float | int]] = {}
    for code, name in markets.items():
        snapshot = tq.get_market_snapshot(code, SNAPSHOT_FIELDS)
        if snapshot.get("ErrorId") != "0":
            raise RuntimeError(f"未能获取{name}市场快照：{snapshot}")
        result[name] = {
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


def fetch_a_share_data(universe: dict[str, dict[str, str]], caller_file: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, float | int]]]:
    """在一个通达信会话中获取 A 股及配置商品期货数据。"""
    tq = load_tq()
    tq.initialize(str(caller_file))
    try:
        return (
            latest_daily_rows(tq, universe["a_share_stocks"]),
            latest_daily_rows(tq, universe["industry_etfs"]),
            latest_daily_rows(tq, universe["a_share_indices"]),
            latest_daily_rows(tq, universe["commodity_futures"]),
            market_breadth(tq, universe["a_share_markets"]),
        )
    finally:
        tq.close()
