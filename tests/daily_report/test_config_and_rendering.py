from datetime import date, datetime
from pathlib import Path

import pandas as pd

from daily_report.config import load_universe
from daily_report.rendering import a_share_table, eastmoney_quote_url, offering_table, render
from daily_report.storage.market_repository import MarketRepository


def test_default_config_includes_midea_and_moutai() -> None:
    root = Path(__file__).resolve().parents[2]
    universe = load_universe(root / "config" / "market_universe.json")
    assert universe["a_share_stocks"] == {"000333.SZ": "美的集团", "600519.SH": "贵州茅台"}


def test_render_includes_configurable_sections() -> None:
    a_share_row = {
        "name": "美的集团", "code": "000333.SZ", "date": "2026-08-19", "open": 80,
        "high": 82, "low": 79, "close": 81, "change_pct": 1.25, "volume": 10, "amount": 100,
    }
    breadth = {
        "沪市": {"amount": 10_000, "up": 1, "down": 2},
        "深市": {"amount": 20_000, "up": 3, "down": 4},
        "北交所": {"amount": 3_000, "up": 5, "down": 6},
        "三市合计": {"amount": 33_000, "up": 9, "down": 12},
    }
    offering = {
        "kind": "新债", "name": "测试转债", "security_code": "123999",
        "subscription_code": "371999", "subscription_date": "2026-08-20",
        "issue_price": 100, "max_subscription": 100, "issue_pe": None,
        "max_subscription_unit": "万元", "event_status": "今日申购",
        "winning_rate": 0.001234, "listing_date": "2026-09-01",
        "underlying_name": "测试股份", "underlying_code": "301999",
        "issue_size": 5.5, "rating": "AA", "sources": ["通达信", "东方财富"],
    }
    report = render(
        [a_share_row], [], [], breadth, [], [], [], [offering], [],
        datetime(2026, 8, 19, 9, 0),
    )
    assert "## 1. A 股股票" in report
    assert "美的集团" in report
    assert "## 5. 重要商品期货" in report
    assert "## 6. 配置的美股" in report
    assert "## 8. 新股新债日历" in report
    assert "测试转债" in report
    assert "0.001234%" in report
    assert "100.00 万元" in report
    assert "[查看](https://quote.eastmoney.com/sz000333.html)" in report
    assert "[查看](https://quote.eastmoney.com/zs000001.html)" in report
    assert "[查看](https://quote.eastmoney.com/q/0.899050.html)" in report


def test_eastmoney_quote_urls_cover_stocks_etfs_and_indices() -> None:
    assert eastmoney_quote_url("000333.SZ") == "https://quote.eastmoney.com/sz000333.html"
    assert eastmoney_quote_url("600519.SH") == "https://quote.eastmoney.com/sh600519.html"
    assert eastmoney_quote_url("512880.SH") == "https://quote.eastmoney.com/sh512880.html"
    assert eastmoney_quote_url("399006.SZ", index=True) == "https://quote.eastmoney.com/zs399006.html"
    assert eastmoney_quote_url("932000.CSI", index=True) == "https://quote.eastmoney.com/zz/2.932000.html"


def test_a_share_table_preserves_configured_row_order() -> None:
    rows = [
        {"name": "美的集团", "code": "000333.SZ", "status": "测试"},
        {"name": "贵州茅台", "code": "600519.SH", "status": "测试"},
    ]
    table = a_share_table(rows)
    assert table.index("美的集团") < table.index("贵州茅台")


def test_offering_table_has_explicit_empty_state() -> None:
    assert offering_table([]) == "观察窗口内暂无新股、新债申购或上市事件。"


def test_three_year_price_position_uses_cached_closes(tmp_path: Path) -> None:
    repository = MarketRepository(tmp_path / "daily_report.sqlite3")
    dates = pd.date_range(end="2026-08-19", periods=1_100, freq="D").strftime("%Y-%m-%d")
    repository.upsert_bars(
        "a_share_stocks",
        "000333.SZ",
        pd.DataFrame(
            {"date": dates, "close": [10] * len(dates)}
        ),
    )
    percentile, label = repository.price_position(
        "a_share_stocks", "000333.SZ", date(2026, 8, 19), 20
    )
    assert percentile == 100
    assert label == "价格偏高"
