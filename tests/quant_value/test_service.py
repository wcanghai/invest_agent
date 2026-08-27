from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from quant_value.config import Instrument
from quant_value.repository import open_database
from quant_value.service import sync_research_data


class FakeGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.starts: list[tuple[str, str, date]] = []

    def connect(self) -> None:
        self.calls.append(("connect", ""))

    def close(self) -> None:
        self.calls.append(("close", ""))

    def market_bars(self, code: str, start: date, end: date) -> list[dict[str, Any]]:
        self.calls.append(("bars", code))
        self.starts.append(("bars", code, start))
        return [{"Date": end.isoformat(), "Close": 10, "Amount": 100}]

    def financial_reports(self, code: str, start: date, end: date) -> list[dict[str, Any]]:
        self.calls.append(("financial", code))
        self.starts.append(("financial", code, start))
        return [{"tag_time": "20251231", "announce_time": "20260401", "FN4": 5}]

    def share_capital(self, code: str, start: date, end: date) -> list[dict[str, Any]]:
        self.calls.append(("capital", code))
        return [{"Date": "20260101", "Zgb": 1000, "Ltgb": 900}]

    def corporate_actions(self, code: str, start: date, end: date) -> list[dict[str, Any]]:
        self.calls.append(("actions", code))
        return []

    def snapshot(self, code: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        self.calls.append(("snapshot", code))
        return ({"Name": code}, {"IOPV": 9.9}, {"Now": 10})

    def relations(self, code: str) -> list[dict[str, Any]]:
        self.calls.append(("relations", code))
        return [{"BlockCode": "A", "BlockType": "行业"}]

    def etfs_for_benchmark(self, benchmark_code: str) -> list[dict[str, Any]]:
        self.calls.append(("etfs", benchmark_code))
        return [{"Code": "510300.SH", "NowPrice": 10, "IOPV": 9.9, "Zgb": 1, "Sz": 2}]


def test_service_uses_stock_etf_and_benchmark_interfaces(tmp_path: Path) -> None:
    gateway = FakeGateway()
    universe = [
        Instrument("600519.SH", "贵州茅台", "stock", "消费"),
        Instrument("510300.SH", "沪深300ETF", "etf", "宽基", "000300.SH", "沪深300"),
    ]
    with open_database(tmp_path / "value.sqlite3") as connection:
        result = sync_research_data(
            connection, gateway, universe, date(2026, 1, 1), date(2026, 8, 25),
            incremental=False,
        )
        assert result.status == "success"
        assert connection.execute("SELECT COUNT(*) FROM market_bars").fetchone()[0] == 3
        assert connection.execute("SELECT COUNT(*) FROM financial_reports").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM etf_snapshots").fetchone()[0] == 1
        assert ("financial", "600519.SH") in gateway.calls
        assert ("financial", "510300.SH") not in gateway.calls
        assert ("bars", "000300.SH") in gateway.calls

        sync_research_data(
            connection, gateway, universe, date(2026, 1, 1), date(2026, 8, 25),
            incremental=True,
        )
        assert ("bars", "600519.SH", date(2026, 8, 18)) in gateway.starts
        assert ("financial", "600519.SH", date(2026, 3, 25)) in gateway.starts
