from __future__ import annotations

import pandas as pd

from tdx_data.universe import fetch_target_universe, group_counts


def _index_frame(symbol: str) -> pd.DataFrame:
    rows = []
    count = 3 if symbol == "000300" else 4
    for index in range(count):
        code = f"{index + 1:06d}"
        rows.append(["date", symbol, "index", "index_en", code, f"股票{code}", "", "", "Shenzhen Stock Exchange"])
    return pd.DataFrame(rows)


def _etf_frame() -> pd.DataFrame:
    rows = []
    for index in range(105):
        code = f"51{index:04d}"
        rows.append([code, f"ETF{index}", None, None, None, None, None, None, index + 1])
    return pd.DataFrame(rows)


def test_target_universe_merges_indices_and_ranks_etfs() -> None:
    assets = fetch_target_universe(
        101, index_fetcher=_index_frame, etf_fetcher=_etf_frame
    )

    assert group_counts(assets) == {"沪深300": 3, "中证500": 4, "高流动性ETF": 101}
    assert len(assets) == 105  # 两个指数有三只重合股票。
    top_etf = next(asset for asset in assets if asset.liquidity_rank == 1)
    assert top_etf.code == "510104.SH"
    assert top_etf.latest_amount == 105


def test_target_universe_requires_more_than_one_hundred_etfs() -> None:
    try:
        fetch_target_universe(100, index_fetcher=_index_frame, etf_fetcher=_etf_frame)
    except ValueError as error:
        assert "大于 100" in str(error)
    else:
        raise AssertionError("ETF 数量下限应被拒绝")
