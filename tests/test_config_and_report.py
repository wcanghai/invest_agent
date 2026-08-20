from datetime import datetime
from pathlib import Path

import pandas as pd

from market_report.config import load_universe
from market_report.history import attach_price_positions, save_history
from market_report.report import render


def test_default_config_includes_midea_and_moutai() -> None:
    root = Path(__file__).resolve().parents[1]
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
    report = render([a_share_row], [], [], breadth, [], [], [], [], datetime(2026, 8, 19, 9, 0))
    assert "## 1. A 股股票" in report
    assert "美的集团" in report
    assert "## 5. 重要商品期货" in report
    assert "## 6. 配置的美股" in report


def test_three_year_price_position_uses_cached_closes(tmp_path: Path) -> None:
    history_root = tmp_path / "history"
    path = history_root / "a_share_stocks" / "000333.SZ.csv"
    dates = pd.date_range(end="2026-08-19", periods=1_100, freq="D").strftime("%Y-%m-%d")
    save_history(
        pd.DataFrame(
            {"date": dates, "close": [10] * len(dates)}
        ),
        path,
    )
    rows = [{"code": "000333.SZ", "close": 20, "date": "2026-08-19"}]
    attach_price_positions(rows, history_root, "a_share_stocks")
    assert rows[0]["three_year_percentile"] == 100
    assert rows[0]["price_position"] == "价格偏高"
