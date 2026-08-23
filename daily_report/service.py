"""多市场日报的采集、计算和渲染编排。"""

from __future__ import annotations

import math
from datetime import date, datetime
from pathlib import Path
from typing import Any

from daily_report.config import load_universe
from daily_report.data_sources.external import fetch_crypto_quotes, fetch_us_daily
from daily_report.data_sources.offerings import collect_offerings
from daily_report.data_sources.tdx import fetch_a_share_data
from daily_report.models import MarketReportSnapshot
from daily_report.rendering import render
from daily_report.storage.market_repository import MarketRepository


def generate_market_report(
    config_path: Path,
    database_path: Path,
    caller_file: Path,
    generated_at: datetime | None = None,
) -> MarketReportSnapshot:
    """采集所有配置市场、更新 SQLite 日线并返回完整日报快照。"""
    generated_at = generated_at or datetime.now()
    universe = load_universe(config_path.resolve())
    repository = MarketRepository(database_path)
    repository.sync_instruments(universe)

    stock_rows, etf_rows, index_rows, futures_rows, breadth = fetch_a_share_data(
        universe, caller_file
    )
    us_rows, us_warnings = fetch_us_daily(universe["us_stocks"])
    crypto_rows, crypto_warnings = fetch_crypto_quotes(universe["crypto_pairs"])
    offering_rows, offering_warnings = collect_offerings(caller_file, generated_at.date())
    fallback_date = generated_at.date()
    categorized_rows = [
        ("a_share_stocks", stock_rows),
        ("industry_etfs", etf_rows),
        ("a_share_indices", index_rows),
        ("commodity_futures", futures_rows),
        ("us_stocks", us_rows),
        ("crypto_pairs", crypto_rows),
    ]
    for category, rows in categorized_rows:
        _update_positions(repository, category, rows, fallback_date)

    warnings = us_warnings + crypto_warnings + offering_warnings
    markdown = render(
        stock_rows, etf_rows, index_rows, breadth, futures_rows,
        us_rows, crypto_rows, offering_rows, warnings, generated_at,
    )
    dated_rows = [row for row in stock_rows + etf_rows + index_rows if "date" in row]
    source_date = (
        date.fromisoformat(max(str(row["date"]) for row in dated_rows))
        if dated_rows else generated_at.date()
    )
    data = {
        "a_share_stocks": stock_rows,
        "industry_etfs": etf_rows,
        "a_share_indices": index_rows,
        "market_breadth": breadth,
        "commodity_futures": futures_rows,
        "us_stocks": us_rows,
        "crypto_pairs": crypto_rows,
        "ipo_calendar": offering_rows,
        "warnings": warnings,
    }
    return MarketReportSnapshot(source_date, generated_at, markdown, _json_safe(data))


def _update_positions(
    repository: MarketRepository,
    category: str,
    rows: list[dict[str, Any]],
    fallback_date: date,
) -> None:
    for row in rows:
        if "close" not in row:
            continue
        row_date = date.fromisoformat(str(row.get("date") or fallback_date.isoformat()))
        repository.upsert_bars(
            category,
            str(row["code"]),
            [
                {
                    "date": row_date.isoformat(),
                    "open": row.get("open"),
                    "high": row.get("high"),
                    "low": row.get("low"),
                    "close": row["close"],
                    "volume": row.get("volume"),
                    "amount": row.get("amount"),
                }
            ],
        )
        percentile, label = repository.price_position(
            category, str(row["code"]), row_date, float(row["close"])
        )
        row["three_year_percentile"] = percentile
        row["price_position"] = label


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if hasattr(value, "item"):
        return _json_safe(value.item())
    return value
