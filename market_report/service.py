"""可复用的多市场日报生成服务。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from market_report.config import load_universe
from market_report.external import fetch_crypto_quotes, fetch_us_daily
from market_report.history import attach_price_positions, merge_latest_rows
from market_report.offerings import collect_offerings
from market_report.report import render
from market_report.tdx import fetch_a_share_data


@dataclass(frozen=True)
class MarketReportSnapshot:
    """一次成功采集产生的 Markdown 和可持久化结构化快照。"""

    source_date: date
    generated_at: datetime
    markdown: str
    data: dict[str, Any]

    def persisted_data(self) -> dict[str, Any]:
        return {
            "source_date": self.source_date.isoformat(),
            "generated_at": self.generated_at.isoformat(timespec="seconds"),
            "data": _json_safe(self.data),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.persisted_data(), "markdown": self.markdown}


def generate_market_report(
    config_path: Path,
    history_root: Path,
    caller_file: Path,
    generated_at: datetime | None = None,
) -> MarketReportSnapshot:
    """采集所有配置市场，计算指标并返回完整日报快照。"""
    generated_at = generated_at or datetime.now()
    universe = load_universe(config_path.resolve())
    history_root = history_root.resolve()

    stock_rows, etf_rows, index_rows, futures_rows, breadth = fetch_a_share_data(
        universe, caller_file
    )
    us_rows, us_warnings = fetch_us_daily(universe["us_stocks"])
    crypto_rows, crypto_warnings = fetch_crypto_quotes(universe["crypto_pairs"])
    offering_rows, offering_warnings = collect_offerings(caller_file, generated_at.date())
    fallback_date = generated_at.strftime("%Y-%m-%d")
    categorized_rows = [
        ("a_share_stocks", stock_rows),
        ("industry_etfs", etf_rows),
        ("a_share_indices", index_rows),
        ("commodity_futures", futures_rows),
        ("us_stocks", us_rows),
        ("crypto_pairs", crypto_rows),
    ]
    for category, rows in categorized_rows:
        merge_latest_rows(rows, history_root, category, fallback_date)
        attach_price_positions(rows, history_root, category)

    warnings = us_warnings + crypto_warnings + offering_warnings
    markdown = render(
        stock_rows,
        etf_rows,
        index_rows,
        breadth,
        futures_rows,
        us_rows,
        crypto_rows,
        offering_rows,
        warnings,
        generated_at,
    )
    dated_rows = [row for row in stock_rows + etf_rows + index_rows if "date" in row]
    source_date = (
        date.fromisoformat(max(row["date"] for row in dated_rows))
        if dated_rows
        else generated_at.date()
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
