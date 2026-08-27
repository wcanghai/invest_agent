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
        self.history_calls: list[tuple[str, date, date]] = []
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

    def financial_history(self, code: str, start: date, end: date) -> Any:
        self.history_calls.append(("financial", start, end))
        return {
            code: [
                {
                    "FN196": "12.5",
                    "announce_time": "20260822",
                    "tag_time": "20260630",
                }
            ]
        }

    def share_capital_history(self, code: str, start: date, end: date) -> Any:
        self.history_calls.append(("share_capital", start, end))
        return [{"Date": 20260821, "Ltgb": 900.0, "Zgb": 1000.0}]

    def corporate_actions(self, code: str, start: date, end: date) -> Any:
        self.history_calls.append(("corporate_actions", start, end))
        return [{"Date": "2026-08-20", "Type": "1", "Bonus": 1.0}]

    def market_snapshot(self, code: str) -> Any:
        return {"Code": code, "Now": 10.5}

    def gp_trading(self, code: str, start: date, end: date) -> Any:
        return {code: [{"Date": end.isoformat(), "GP1": 100.0}]}

    def gp_single(self, code: str) -> Any:
        return {code: {"GO1": 5.0}}


class PartiallyFailingTdxClient(FakeTdxClient):
    def market_snapshot(self, code: str) -> Any:
        raise RuntimeError("snapshot unavailable")


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
        assert connection.execute("SELECT COUNT(*) FROM financial_reports").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM share_capital_history").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM corporate_actions").fetchone()[0] == 1
        assert connection.execute(
            "SELECT MIN(observed_date), MAX(observed_date) FROM stock_info_flat"
        ).fetchone() == ("2026-08-23", "2026-08-23")
        assert connection.execute("SELECT COUNT(*) FROM sync_runs").fetchone()[0] == 2
    assert all(instance.closed for instance in FakeTdxClient.instances)
    assert FakeTdxClient.instances[-1].history_calls == [
        ("financial", date(2026, 8, 1), date(2026, 8, 23)),
        ("share_capital", date(2026, 8, 1), date(2026, 8, 23)),
        ("corporate_actions", date(2026, 8, 1), date(2026, 8, 23)),
    ]


def test_selected_assets_persist_group_membership(tmp_path: Path) -> None:
    user_dir = tmp_path / "tdx-user"
    user_dir.mkdir()
    database = tmp_path / "tdx.sqlite3"
    selected = [
        {
            "Code": "600000.SH",
            "Name": "浦发银行",
            "Groups": ["沪深300"],
            "LiquidityRank": None,
            "LatestAmount": None,
        }
    ]

    archive_stocks(
        tdx_user_dir=user_dir,
        database_path=database,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 23),
        selected_assets=selected,
        client_factory=FakeTdxClient,
    )

    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT group_name FROM asset_groups WHERE code='600000.SH'"
        ).fetchone()[0] == "沪深300"
        assert connection.execute(
            "SELECT observed_date FROM asset_group_history WHERE code='600000.SH'"
        ).fetchone()[0] == "2026-08-23"


def test_one_extended_interface_failure_keeps_other_datasets(tmp_path: Path) -> None:
    user_dir = tmp_path / "tdx-user"
    user_dir.mkdir()
    database = tmp_path / "tdx.sqlite3"

    result = archive_stocks(
        tdx_user_dir=user_dir,
        database_path=database,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 23),
        client_factory=PartiallyFailingTdxClient,
    )

    assert result.failed_codes == 1
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM daily_bars").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM financial_reports").fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM raw_api_records WHERE dataset='gp_single'"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM raw_api_records WHERE dataset='market_snapshot'"
        ).fetchone()[0] == 0


def test_etf_skips_company_financial_history(tmp_path: Path) -> None:
    user_dir = tmp_path / "tdx-user"
    user_dir.mkdir()
    selected = [
        {
            "Code": "159001.SZ",
            "Name": "货币ETF",
            "Groups": ["高流动性ETF"],
        }
    ]

    archive_stocks(
        tdx_user_dir=user_dir,
        database_path=tmp_path / "tdx.sqlite3",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 24),
        selected_assets=selected,
        client_factory=FakeTdxClient,
    )

    calls = [name for name, _, _ in FakeTdxClient.instances[-1].history_calls]
    assert calls == ["share_capital", "corporate_actions"]
