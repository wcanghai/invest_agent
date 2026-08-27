from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from quant_value.config import Instrument
from quant_value.factors import build_factors
from quant_value.repository import (
    open_database,
    upsert_bars,
    upsert_etf_snapshot,
    upsert_financial_reports,
    upsert_instruments,
)


def test_factors_are_point_in_time_and_split_stock_from_etf(tmp_path: Path) -> None:
    captured = datetime.now(UTC).isoformat()
    instruments = [
        Instrument("600519.SH", "贵州茅台", "stock", "消费"),
        Instrument("510300.SH", "沪深300ETF", "etf", "宽基", "000300.SH", "沪深300"),
    ]
    with open_database(tmp_path / "value.sqlite3") as connection:
        upsert_instruments(connection, instruments, captured)
        start = date(2026, 1, 1)
        for code, base in (("600519.SH", 10), ("510300.SH", 4), ("000300.SH", 4000)):
            rows = [
                {"Date": (start + timedelta(days=offset)).isoformat(),
                 "Open": base + offset, "High": base + offset + 1,
                 "Low": base + offset - 1, "Close": base + offset,
                 "Volume": 1000, "Amount": 2000}
                for offset in range(80)
            ]
            upsert_bars(connection, code, rows, captured)
        upsert_financial_reports(connection, "600519.SH", [
            {"tag_time": "20251231", "announce_time": "20260110", "FN4": 10,
             "FN238": 1_000_000, "FN308": 100, "FN319": 1000,
             "FN281": 20, "FN329": 15, "FN202": 60, "FN210": 30},
            {"tag_time": "20251231", "announce_time": "20260210", "FN4": 20,
             "FN238": 1_000_000, "FN308": 120, "FN319": 1100,
             "FN281": 21, "FN329": 16, "FN202": 61, "FN210": 29},
        ], captured)
        upsert_etf_snapshot(
            connection, "510300.SH", date(2026, 3, 21), "000300.SH",
            {"NowPrice": 83, "IOPV": 82, "Zgb": 100, "Sz": 8.2}, captured,
        )
        connection.commit()

        first = build_factors(connection, rebuild=True)
        second = build_factors(connection)
        assert first.rows == 160
        assert second.rows == 16
        assert connection.execute("SELECT COUNT(*) FROM factor_daily").fetchone()[0] == 160

        before = connection.execute(
            "SELECT * FROM factor_daily WHERE code='600519.SH' AND trade_date='2026-01-09'"
        ).fetchone()
        announced = connection.execute(
            "SELECT * FROM factor_daily WHERE code='600519.SH' AND trade_date='2026-01-10'"
        ).fetchone()
        revised = connection.execute(
            "SELECT * FROM factor_daily WHERE code='600519.SH' AND trade_date='2026-02-10'"
        ).fetchone()
        assert before["pb"] is None
        assert announced["pb"] == pytest.approx(19 / 10)
        assert revised["pb"] == pytest.approx(50 / 20)
        assert announced["announce_date"] == "2026-01-10"
        assert revised["announce_date"] == "2026-02-10"

        etf = connection.execute(
            "SELECT * FROM factor_daily WHERE code='510300.SH' ORDER BY trade_date DESC LIMIT 1"
        ).fetchone()
        assert etf["pb"] is None
        assert etf["etf_iopv"] == 82
        assert etf["tracking_error_60d"] is not None
        assert etf["tracking_error_60d"] >= 0


def test_factor_build_commits_each_completed_instrument(tmp_path: Path) -> None:
    database = tmp_path / "resumable.sqlite3"
    captured = datetime.now(UTC).isoformat()
    instruments = [
        Instrument("600519.SH", "贵州茅台", "stock", "消费"),
        Instrument("000333.SZ", "美的集团", "stock", "制造"),
    ]
    with open_database(database) as connection:
        upsert_instruments(connection, instruments, captured)
        for code in ("600519.SH", "000333.SZ"):
            upsert_bars(connection, code, [{
                "Date": "2026-08-25", "Open": 10, "High": 11, "Low": 9,
                "Close": 10, "Volume": 100, "Amount": 1000,
            }], captured)
        connection.commit()

        observed: list[int] = []

        def inspect_commit(done: int, total: int, code: str, rows: int) -> None:
            if done == 1:
                with open_database(database) as observer:
                    observed.append(observer.execute(
                        "SELECT COUNT(*) FROM factor_daily WHERE code=?", (code,)
                    ).fetchone()[0])

        build_factors(connection, [item.code for item in instruments], progress=inspect_commit)
        assert observed == [1]
