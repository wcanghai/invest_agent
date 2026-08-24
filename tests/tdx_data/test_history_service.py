from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from tdx_data.history_service import (
    calculate_historical_pb,
    corporate_actions_between,
    financial_report_as_of,
    historical_metric_inputs,
    share_capital_as_of,
)
from tdx_data.repository import (
    insert_daily,
    open_database,
    upsert_asset,
    upsert_corporate_actions,
    upsert_financial_reports,
    upsert_share_capital_history,
)


def _database(path: Path) -> sqlite3.Connection:
    connection = open_database(path)
    upsert_asset(connection, "600000.SH", "浦发银行", "5", "2026-08-24T00:00:00Z")
    insert_daily(
        connection,
        "600000.SH",
        [
            {"Date": "2026-04-01", "Close": 18.0},
            {"Date": "2026-04-20", "Close": 20.0},
            {"Date": "2026-05-01", "Close": 22.0},
            {"Date": "2026-05-15", "Close": 24.0},
        ],
        date(2026, 5, 15),
        "2026-05-15T00:00:00Z",
    )
    upsert_financial_reports(
        connection,
        "600000.SH",
        [
            {"tag_time": "20250930", "announce_time": "20251031", "FN196": "9"},
            {"tag_time": "20251231", "announce_time": "20260418", "FN196": "10"},
            {"tag_time": "20260331", "announce_time": "20260430", "FN196": "11"},
            # 较旧报告期的更正公告不能覆盖已经发布的更新报告期。
            {"tag_time": "20251231", "announce_time": "20260510", "FN196": "10.5"},
        ],
        "2026-05-15T00:00:00Z",
    )
    upsert_share_capital_history(
        connection,
        "600000.SH",
        [
            {"Date": "20260101", "Ltgb": 90, "Zgb": 100},
            {"Date": "20260425", "Ltgb": 99, "Zgb": 110},
        ],
        "2026-05-15T00:00:00Z",
    )
    upsert_corporate_actions(
        connection,
        "600000.SH",
        [
            {
                "Date": "2026-05-08",
                "Type": "1",
                "Bonus": 2.5,
                "ShareBonus": 1.0,
                "Allotment": 0.5,
                "AllotPrice": 8.0,
            }
        ],
        "2026-05-15T00:00:00Z",
    )
    connection.commit()
    return connection


def test_point_in_time_inputs_use_only_announced_latest_report(tmp_path: Path) -> None:
    with _database(tmp_path / "tdx.sqlite3") as connection:
        inputs = historical_metric_inputs(
            connection, "600000.SH", date(2026, 4, 1), date(2026, 5, 15)
        )

        assert [item.financial_values["FN196"] for item in inputs] == [9.0, 10.0, 11.0, 11.0]
        assert inputs[0].report_date == date(2025, 9, 30)
        assert inputs[1].announce_date == date(2026, 4, 18)
        assert inputs[2].total_shares == 110.0
        assert inputs[3].report_date == date(2026, 3, 31)


def test_as_of_queries_and_explicit_pb_calculation(tmp_path: Path) -> None:
    with _database(tmp_path / "tdx.sqlite3") as connection:
        report = financial_report_as_of(connection, "600000.SH", date(2026, 4, 20))
        capital = share_capital_as_of(connection, "600000.SH", date(2026, 5, 1))
        pb = calculate_historical_pb(
            connection,
            "600000.SH",
            date(2026, 4, 1),
            date(2026, 5, 15),
            book_value_per_share_field="fn196",
        )

        assert report is not None and report.values["FN196"] == 10.0
        assert capital is not None and capital.total_shares == 110.0
        assert [item.pb for item in pb] == pytest.approx([2.0, 2.0, 2.0, 24 / 11])
        with pytest.raises(ValueError, match="不能为空"):
            calculate_historical_pb(
                connection,
                "600000.SH",
                date(2026, 4, 1),
                date(2026, 5, 15),
                book_value_per_share_field=" ",
            )


def test_financial_values_and_corporate_actions_are_structured(tmp_path: Path) -> None:
    with _database(tmp_path / "tdx.sqlite3") as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM financial_report_values WHERE field_name='FN196'"
        ).fetchone()[0] == 4
        action = corporate_actions_between(
            connection, "600000.SH", date(2026, 5, 1), date(2026, 5, 31)
        )[0]

        assert action.cash_dividend == 2.5
        assert action.bonus_shares == 1.0
        assert action.allotment_shares == 0.5
        assert action.allotment_price == 8.0

        upsert_corporate_actions(
            connection,
            "600000.SH",
            [{"Date": "2026-05-08", "Type": "1", "Bonus": 3.0}],
            "2026-05-16T00:00:00Z",
        )
        connection.commit()
        assert connection.execute(
            "SELECT COUNT(*) FROM corporate_actions WHERE action_date='2026-05-08'"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT cash_dividend FROM corporate_actions WHERE action_date='2026-05-08'"
        ).fetchone()[0] == 3.0


def test_open_database_adds_columns_to_older_corporate_action_table(tmp_path: Path) -> None:
    path = tmp_path / "old.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE corporate_actions(
                code TEXT NOT NULL,
                action_date TEXT NOT NULL,
                record_key TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                PRIMARY KEY(code,action_date,record_key)
            ) WITHOUT ROWID
            """
        )

    with open_database(path) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(corporate_actions)")
        }
        assert {
            "action_type",
            "cash_dividend",
            "bonus_shares",
            "allotment_shares",
            "allotment_price",
        } <= columns


def test_open_database_backfills_structured_values_from_existing_json(tmp_path: Path) -> None:
    path = tmp_path / "backfill.sqlite3"
    with open_database(path) as connection:
        upsert_asset(connection, "600000.SH", "浦发银行", "5", "captured")
        connection.execute(
            """
            INSERT INTO financial_reports VALUES(?,?,?,?,?)
            """,
            (
                "600000.SH",
                "2025-12-31",
                "2026-04-18",
                '{"tag_time":"20251231","announce_time":"20260418","FN196":"10"}',
                "captured",
            ),
        )
        connection.commit()

    with open_database(path) as connection:
        row = connection.execute(
            """
            SELECT numeric_value FROM financial_report_values
            WHERE code='600000.SH' AND field_name='FN196'
            """
        ).fetchone()
        assert row[0] == 10.0
