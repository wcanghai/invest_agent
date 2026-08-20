"""本地五年日线缓存与三年价格分位计算。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from market_report.external import read_json
from market_report.tdx import KLINE_FIELDS


HISTORY_COLUMNS = ["date", "open", "high", "low", "close", "volume", "amount"]
THREE_YEARS_DAYS = 365 * 3 + 1


def cache_path(history_root: Path, category: str, code: str) -> Path:
    """返回某个标的的本地 CSV 缓存路径。"""
    safe_code = code.replace("/", "_").replace("\\", "_")
    return history_root / category / f"{safe_code}.csv"


def normalise_history(frame: pd.DataFrame) -> pd.DataFrame:
    """清理、按日期去重并统一日线缓存字段。"""
    result = frame.copy()
    for column in HISTORY_COLUMNS:
        if column not in result:
            result[column] = None
    result = result[HISTORY_COLUMNS]
    result["date"] = pd.to_datetime(result["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    result["close"] = pd.to_numeric(result["close"], errors="coerce")
    result = result.dropna(subset=["date", "close"])
    result = result.drop_duplicates(subset=["date"], keep="last").sort_values("date").reset_index(drop=True)
    return result


def save_history(frame: pd.DataFrame, path: Path, merge: bool = False) -> None:
    """保存全量历史，或把新日线合并进已有缓存。"""
    result = normalise_history(frame)
    if merge and path.exists():
        old = pd.read_csv(path)
        result = normalise_history(pd.concat([old, result], ignore_index=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(path, index=False, encoding="utf-8")


def fetch_tdx_history(tq: Any, names: dict[str, str], years: int = 5) -> dict[str, pd.DataFrame]:
    """从通达信读取指定标的近若干年的日线。"""
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
    """从 Yahoo Finance 公开图表端点获取美股日线。"""
    now = datetime.now(timezone.utc)
    start = int((now - timedelta(days=years * 366)).timestamp())
    end = int(now.timestamp())
    payload = read_json(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{code}?period1={start}&period2={end}&interval=1d"
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
            "open": quote.get("open", []),
            "high": quote.get("high", []),
            "low": quote.get("low", []),
            "close": quote.get("close", []),
            "volume": quote.get("volume", []),
            "amount": None,
        }
    )


def fetch_coinbase_history(pair: str, years: int = 5) -> pd.DataFrame:
    """从 Coinbase 公共接口分段获取加密资产 UTC 日 K（单次最多约 300 根）。"""
    product = pair.replace("XBT", "BTC")[:-3] + "-USD"
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=years * 366)
    step = timedelta(days=290)
    candles: list[list[float]] = []
    cursor = start
    while cursor < end:
        next_cursor = min(cursor + step, end)
        url = (
            f"https://api.exchange.coinbase.com/products/{product}/candles"
            f"?start={cursor.strftime('%Y-%m-%dT%H:%M:%SZ')}&end={next_cursor.strftime('%Y-%m-%dT%H:%M:%SZ')}&granularity=86400"
        )
        data = read_json(url)
        if not isinstance(data, list):
            raise RuntimeError(f"Coinbase 未返回 {product} 的历史日线")
        candles.extend(data)
        cursor = next_cursor
    return pd.DataFrame(
        [
            {
                "date": datetime.fromtimestamp(item[0], tz=timezone.utc).strftime("%Y-%m-%d"),
                "low": item[1], "high": item[2], "open": item[3], "close": item[4], "volume": item[5], "amount": None,
            }
            for item in candles
        ]
    )


def attach_price_positions(rows: list[dict[str, Any]], history_root: Path, category: str) -> None:
    """原地增加三年收盘价分位与价格位置；缺缓存时保留清晰状态。"""
    for row in rows:
        if "close" not in row:
            continue
        path = cache_path(history_root, category, row["code"])
        if not path.exists():
            row["price_position"] = "历史缓存缺失"
            row["three_year_percentile"] = None
            continue
        history = normalise_history(pd.read_csv(path))
        reference_date = pd.Timestamp(row.get("date") or datetime.now().date())
        cutoff = reference_date - pd.Timedelta(days=THREE_YEARS_DAYS)
        closes = history.loc[pd.to_datetime(history["date"]) >= cutoff, "close"]
        first_date = pd.to_datetime(history["date"]).min()
        # 三年交易日线通常至少约 700 条；用 500 条下限排除期货换月、停牌等不连续合约记录。
        if len(closes) < 500 or first_date > cutoff + pd.Timedelta(days=45):
            row["price_position"] = "历史样本不足"
            row["three_year_percentile"] = None
            continue
        percentile = float((closes <= float(row["close"])).mean() * 100)
        row["three_year_percentile"] = percentile
        row["price_position"] = "价格偏低" if percentile <= 20 else "价格偏高" if percentile >= 80 else "价格中性"


def merge_latest_rows(rows: list[dict[str, Any]], history_root: Path, category: str, fallback_date: str) -> None:
    """将日报中的最新价格按日期写入缓存；同日重复运行时覆盖该日记录。"""
    for row in rows:
        if "close" not in row:
            continue
        frame = pd.DataFrame(
            [{
                "date": row.get("date", fallback_date), "open": row.get("open"), "high": row.get("high"),
                "low": row.get("low"), "close": row["close"], "volume": row.get("volume"), "amount": row.get("amount"),
            }]
        )
        save_history(frame, cache_path(history_root, category, row["code"]), merge=True)
