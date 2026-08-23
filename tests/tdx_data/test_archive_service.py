from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

from tdx_data.archive_service import archive_stocks


class FakeTdxClient:
    instances: list["FakeTdxClient"] = []

    def __init__(self, user_dir: Path, caller_file: Path):
        self.user_dir = user_dir
        self.caller_file = caller_file
        self.closed = False
        self.__class__.instances.append(self)

    def connect(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    def list_stocks(self, market: str) -> list[dict[str, Any]]:
        assert market == "5"
        return [{"Code": "600000.SH", "Name": "浦发银行"}]

    def daily(self, code: str, start: date, end: date) -> list[dict[str, Any]]:
        return [{"Date": "2026-08-22", "Close": 10.5, "Volume": 1000}]

    def stock_info(self, code: str) -> dict[str, Any]:
        return {"Code": code, "J_zgb": 1_000_000}

    def more_info(self, code: str) -> dict[str, Any]:
        return {"Code": code, "DynaPE": 8.5}

    def relations(self, code: str) -> list[dict[str, Any]]:
        return [{"Code": code, "Type": "行业", "Name": "银行"}]


def test_archive_service_is_offline_injectable_and_idempotent(tmp_path: Path) -> None:
    user_dir = tmp_path / "tdx-user"
    user_dir.mkdir()
    database = tmp_path / "tdx.sqlite3"

    for _ in range(2):
        result = archive_stocks(
            tdx_user_dir=user_dir,
            database_path=database,
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 23),
            client_factory=FakeTdxClient,
        )
        assert result.failed_codes == 0

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM assets").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM daily_bars").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM stock_relations").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM sync_runs").fetchone()[0] == 2
    assert all(instance.closed for instance in FakeTdxClient.instances)
