from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from tdx_data.quant_wide_cli import parse_arguments
from tdx_data.quant_wide_service import build_quant_daily_wide
from tdx_data.repository import (
    insert_daily,
    open_database,
    replace_asset_groups,
    upsert_asset,
    upsert_corporate_actions,
    upsert_financial_reports,
    upsert_flat,
    upsert_share_capital_history,
)


def _database(path: Path) -> sqlite3.Connection:
    connection = open_database(path)
    captured = "2026-04-25T00:00:00+00:00"
    upsert_asset(connection, "600000.SH", "浦发银行", "5", captured)
    upsert_asset(connection, "510300.SH", "沪深300ETF", "5", captured)
    replace_asset_groups(connection, "600000.SH", ["沪深300"], captured)
    replace_asset_groups(connection, "510300.SH", ["高流动性ETF"], captured)
    start = date(2026, 4, 1)
    for code, base in (("600000.SH", 10.0), ("510300.SH", 4.0)):
        rows = []
        for offset in range(25):
            close = base + offset
            rows.append(
                {
                    "Date": (start + timedelta(days=offset)).isoformat(),
                    "Open": close - 0.5,
                    "High": close + 1,
                    "Low": close - 1,
                    "Close": close,
                    "Volume": 1000 + offset,
                    "Amount": 10000 + offset,
                    "ForwardFactor": 1,
                    "VolInStock": 2000,
                }
            )
        insert_daily(connection, code, rows, date(2026, 4, 25), captured)

    upsert_financial_reports(
        connection,
        "600000.SH",
        [
            {"tag_time": "20251231", "announce_time": "20260405", "FN193": 1, "FN196": 10},
            {"tag_time": "20260331", "announce_time": "20260415", "FN193": 2, "FN196": 12},
            {"tag_time": "20251231", "announce_time": "20260420", "FN193": 3, "FN196": 11},
        ],
        captured,
    )
    upsert_share_capital_history(
        connection,
        "600000.SH",
        [
            {"Date": "20260401", "Ltgb": 90, "Zgb": 100},
            {"Date": "20260410", "Ltgb": 99, "Zgb": 110},
        ],
        captured,
    )
    upsert_share_capital_history(
        connection,
        "510300.SH",
        [{"Date": "20260401", "Ltgb": 200, "Zgb": 200}],
        captured,
    )
    upsert_corporate_actions(
        connection,
        "600000.SH",
        [{"Date": "20260412", "Type": "1", "Bonus": 2.5, "ShareBonus": 1}],
        captured,
    )
    upsert_flat(
        connection,
        "more_info_flat",
        "600000.SH",
        date(2026, 4, 16),
        {
            "HqDate": "20260415",
            "DynaPE": "8.5",
            "PB_MRQ": "1.2",
            "NoticeDate_Recent": "20260414",
        },
    )
    upsert_flat(
        connection,
        "stock_info_flat",
        "600000.SH",
        date(2026, 4, 16),
        {
            "J_zzc": "1000",
            "J_jzc": "600",
            "J_jly": "50",
            "rs_hycode_sim": "480301",
            "rs_hyname": "银行",
            "IsSTGP": 0,
            "BelongRZRQ": 1,
        },
    )
    connection.commit()
    return connection


def test_quant_wide_is_point_in_time_idempotent_and_supports_etf(tmp_path: Path) -> None:
    with _database(tmp_path / "quant.sqlite3") as connection:
        first = build_quant_daily_wide(connection, ["600000.SH", "510300.SH"])
        second = build_quant_daily_wide(connection, ["600000.SH", "510300.SH"])

        assert first.written_rows == second.written_rows == 50
        assert not first.failed_codes
        assert connection.execute("SELECT COUNT(*) FROM quant_daily_wide").fetchone()[0] == 50

        before = connection.execute(
            "SELECT * FROM quant_daily_wide WHERE code=? AND trade_date=?",
            ("600000.SH", "2026-04-04"),
        ).fetchone()
        first_report = connection.execute(
            "SELECT * FROM quant_daily_wide WHERE code=? AND trade_date=?",
            ("600000.SH", "2026-04-05"),
        ).fetchone()
        latest_report = connection.execute(
            "SELECT * FROM quant_daily_wide WHERE code=? AND trade_date=?",
            ("600000.SH", "2026-04-20"),
        ).fetchone()
        assert before["report_date"] is None
        assert first_report["fn196"] == 10
        assert latest_report["report_date"] == "2026-03-31"
        assert latest_report["fn196"] == 12

        action = connection.execute(
            "SELECT * FROM quant_daily_wide WHERE code=? AND trade_date=?",
            ("600000.SH", "2026-04-12"),
        ).fetchone()
        after_action = connection.execute(
            "SELECT days_since_action FROM quant_daily_wide WHERE code=? AND trade_date=?",
            ("600000.SH", "2026-04-14"),
        ).fetchone()
        assert action["action_count"] == 1
        assert action["cash_dividend"] == 2.5
        assert after_action[0] == 2

        snapshot = connection.execute(
            "SELECT * FROM quant_daily_wide WHERE code=? AND trade_date=?",
            ("600000.SH", "2026-04-15"),
        ).fetchone()
        no_backfill = connection.execute(
            "SELECT snapshot_date FROM quant_daily_wide WHERE code=? AND trade_date=?",
            ("600000.SH", "2026-04-16"),
        ).fetchone()
        assert snapshot["snapshot_dynamic_pe"] == 8.5
        assert snapshot["snapshot_date"] == "2026-04-16"
        assert snapshot["snapshot_total_assets"] == 1000
        assert snapshot["snapshot_industry_name"] == "银行"
        assert snapshot["snapshot_margin_eligible"] == 1
        assert snapshot["recent_notice_date"] == "2026-04-14"
        assert no_backfill[0] is None

        # 指定结束日重建时，也要读取次日采集但 HqDate 属于结束日的快照。
        narrow = build_quant_daily_wide(
            connection,
            ["600000.SH"],
            date(2026, 4, 15),
            date(2026, 4, 15),
            rebuild=True,
        )
        assert narrow.written_rows == 1
        rebuilt_snapshot = connection.execute(
            "SELECT snapshot_date,snapshot_hq_date FROM quant_daily_wide WHERE code=? AND trade_date=?",
            ("600000.SH", "2026-04-15"),
        ).fetchone()
        assert tuple(rebuilt_snapshot) == ("2026-04-16", "2026-04-15")

        last = connection.execute(
            "SELECT * FROM quant_daily_wide WHERE code=? AND trade_date=?",
            ("600000.SH", "2026-04-25"),
        ).fetchone()
        assert last["return_1d"] == pytest.approx(34 / 33 - 1)
        assert last["return_20d"] == pytest.approx(34 / 14 - 1)
        assert last["close_ma20"] == pytest.approx(sum(range(15, 35)) / 20)
        assert last["total_shares"] == 110
        assert last["market_cap"] == 34 * 110

        etf = connection.execute(
            "SELECT * FROM quant_daily_wide WHERE code=? ORDER BY trade_date DESC LIMIT 1",
            ("510300.SH",),
        ).fetchone()
        assert etf["asset_type"] == "ETF"
        assert etf["report_date"] is None
        assert etf["fn196"] is None
        assert etf["total_shares"] == 200


def test_quant_wide_rebuilds_range_and_isolates_missing_code(tmp_path: Path) -> None:
    with _database(tmp_path / "quant.sqlite3") as connection:
        result = build_quant_daily_wide(
            connection,
            ["600000.SH", "999999.SH"],
            date(2026, 4, 10),
            date(2026, 4, 12),
            rebuild=True,
        )

        assert result.written_rows == 3
        assert result.failed_codes == ("999999.SH",)
        assert connection.execute("SELECT COUNT(*) FROM quant_daily_wide").fetchone()[0] == 3
        run = connection.execute(
            "SELECT status,failed_codes FROM quant_wide_build_runs WHERE id=?",
            (result.run_id,),
        ).fetchone()
        assert tuple(run) == ("partial_failure", 1)


def test_quant_wide_cli_arguments() -> None:
    args = parse_arguments(
        [
            "--code", "600000.SH", "510300.SH",
            "--start", "2020-01-01",
            "--end", "2020-12-31",
            "--rebuild",
        ]
    )
    assert args.code == ["600000.SH", "510300.SH"]
    assert args.start == date(2020, 1, 1)
    assert args.end == date(2020, 12, 31)
    assert args.rebuild is True
