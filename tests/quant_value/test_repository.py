from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from quant_value.config import Instrument
from quant_value.repository import (
    load_instruments,
    open_database,
    upsert_bars,
    upsert_actions,
    upsert_financial_reports,
    upsert_instruments,
)
from quant_value.repository import upsert_memberships
from quant_value.universe import Membership


def test_schema_and_market_bars_are_idempotent(tmp_path: Path) -> None:
    captured = datetime.now(UTC).isoformat()
    with open_database(tmp_path / "value.sqlite3") as connection:
        upsert_instruments(
            connection,
            [Instrument("600519.SH", "贵州茅台", "stock", "消费")],
            captured,
        )
        rows = [{"Date": "20260825", "Open": 10, "High": 11, "Low": 9,
                 "Close": 10.5, "Volume": 100, "Amount": 200}]
        assert upsert_bars(connection, "600519.SH", rows, captured) == 1
        assert upsert_bars(connection, "600519.SH", rows, captured) == 1
        connection.commit()

        assert connection.execute("SELECT COUNT(*) FROM market_bars").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM field_dictionary").fetchone()[0] >= 70
        upsert_memberships(connection, [Membership("600519.SH", "沪深300", date(2026, 8, 26))])
        upsert_memberships(connection, [Membership("600519.SH", "沪深300", date(2026, 8, 26))])
        assert connection.execute("SELECT COUNT(*) FROM universe_memberships").fetchone()[0] == 1
        assert load_instruments(connection, ["600519.SH"])[0].name == "贵州茅台"

        actions = [
            {"Date": "20260825", "Type": "dividend", "Bonus": 10},
            {"Date": "20260826", "Type": "dividend", "Bonus": 12},
        ]
        upsert_actions(connection, "600519.SH", actions, captured)
        upsert_actions(connection, "600519.SH", list(reversed(actions)), captured)
        connection.commit()
        assert connection.execute("SELECT COUNT(*) FROM corporate_actions").fetchone()[0] == 2

    # 重新初始化字段字典必须使用原位 UPSERT，不能删除被财务值外键引用的记录。
    with open_database(tmp_path / "value.sqlite3") as connection:
        upsert_financial_reports(
            connection, "600519.SH",
            [{"tag_time": "20251231", "announce_time": "20260401", "FN4": 10}],
            captured,
        )
        connection.commit()
    with open_database(tmp_path / "value.sqlite3") as connection:
        assert connection.execute("SELECT numeric_value FROM financial_values").fetchone()[0] == 10
