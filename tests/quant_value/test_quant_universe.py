from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from quant_value.universe import fetch_target_universe, group_counts, save_selection


def _index_frame(symbol: str) -> pd.DataFrame:
    count = 3 if symbol == "000300" else 4
    return pd.DataFrame([
        ["date", symbol, "index", "index_en", f"{index + 1:06d}",
         f"股票{index + 1}", "", "", "Shenzhen Stock Exchange"]
        for index in range(count)
    ])


def _etf_frame() -> pd.DataFrame:
    return pd.DataFrame([
        [f"51{index:04d}", f"ETF{index}", None, None, None, None, None, None, index + 1]
        for index in range(105)
    ])


def test_target_universe_is_ranked_traceable_and_serializable(tmp_path: Path) -> None:
    selection = fetch_target_universe(
        101, selected_date=date(2026, 8, 26),
        index_fetcher=_index_frame, etf_fetcher=_etf_frame,
    )
    assert group_counts(selection) == {"沪深300": 3, "中证500": 4, "高流动性ETF": 101}
    assert len(selection.instruments) == 105
    top = next(item for item in selection.memberships if item.liquidity_rank == 1)
    assert top.code == "510104.SH"
    assert top.latest_amount == 105

    output = tmp_path / "selection.json"
    save_selection(selection, output)
    assert '"selected_date": "2026-08-26"' in output.read_text(encoding="utf-8")


def test_target_universe_requires_more_than_100_etfs() -> None:
    try:
        fetch_target_universe(100, index_fetcher=_index_frame, etf_fetcher=_etf_frame)
    except ValueError as error:
        assert "大于 100" in str(error)
    else:
        raise AssertionError("ETF 数量下限应被拒绝")
