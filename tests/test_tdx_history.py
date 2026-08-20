from datetime import date
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from tdx_history.config import Instrument, load_config
from tdx_history.repository import HistoryRepository
from tdx_history.service import HistorySyncService


def bars(*dates: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_date": dates,
            "open": [10.0] * len(dates),
            "high": [11.0] * len(dates),
            "low": [9.0] * len(dates),
            "close": [10.5] * len(dates),
            "volume": [100.0] * len(dates),
            "amount": [1_000.0] * len(dates),
        }
    )


class FakeSource:
    def __init__(self, available: pd.DataFrame):
        self.available = available
        self.calls: list[tuple[str, date, date, str]] = []

    def fetch_daily(self, code: str, start: date, end: date, dividend_type: str) -> pd.DataFrame:
        self.calls.append((code, start, end, dividend_type))
        values = pd.to_datetime(self.available["trade_date"]).dt.date
        return self.available.loc[(values >= start) & (values <= end)].copy()


class TdxHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_load_config_rejects_duplicate_symbols(self) -> None:
        config = self.root / "config.json"
        config.write_text(
            json.dumps(
                {
                    "tdx_user_dir": "D:/tdx",
                    "instruments": [
                        {"code": "510300.SH", "name": "a", "kind": "etf"},
                        {"code": "510300.SH", "name": "b", "kind": "etf"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "重复"):
            load_config(config)

    def test_repository_inserts_each_trading_day_only_once(self) -> None:
        instrument = Instrument("510300.SH", "沪深300ETF", "etf")
        with HistoryRepository(self.root / "history.sqlite3") as repository:
            repository.upsert_instrument(instrument)
            self.assertEqual(
                repository.insert_new_bars(instrument.code, bars("2026-08-18", "2026-08-19")), 2
            )
            self.assertEqual(
                repository.insert_new_bars(instrument.code, bars("2026-08-19", "2026-08-20")), 1
            )
            self.assertEqual(repository.count_bars(instrument.code), 3)
            self.assertEqual(repository.latest_date(instrument.code), date(2026, 8, 20))
            self.assertEqual(repository.date_range(instrument.code), ("2026-08-18", "2026-08-20"))

    def test_service_bootstraps_then_queries_only_after_latest_date(self) -> None:
        instrument = Instrument("000333.SZ", "美的集团", "stock")
        source = FakeSource(bars("2016-08-20", "2026-08-18", "2026-08-19", "2026-08-20"))
        with HistoryRepository(self.root / "history.sqlite3") as repository:
            service = HistorySyncService(repository, source, years=10)
            first = service.sync((instrument,), today=date(2026, 8, 19))[0]
            self.assertEqual(first.status, "updated")
            self.assertEqual(first.inserted_rows, 3)
            self.assertEqual(source.calls[0][1], date(2016, 8, 19))

            second = service.sync((instrument,), today=date(2026, 8, 20))[0]
            self.assertEqual(second.status, "updated")
            self.assertEqual(second.inserted_rows, 1)
            self.assertEqual(source.calls[1][1], date(2026, 8, 20))
            self.assertEqual(repository.count_bars(instrument.code), 4)

            third = service.sync((instrument,), today=date(2026, 8, 20))[0]
            self.assertEqual(third.status, "up_to_date")
            self.assertEqual(len(source.calls), 2)

    def test_existing_history_rejects_dividend_type_change(self) -> None:
        instrument = Instrument("000333.SZ", "美的集团", "stock", "none")
        with HistoryRepository(self.root / "history.sqlite3") as repository:
            repository.upsert_instrument(instrument)
            repository.insert_new_bars(instrument.code, bars("2026-08-20"))
            with self.assertRaisesRegex(ValueError, "不能增量混入"):
                repository.upsert_instrument(
                    Instrument("000333.SZ", "美的集团", "stock", "front")
                )

    def test_empty_first_fetch_is_reported_as_failure(self) -> None:
        instrument = Instrument("000333.SZ", "美的集团", "stock")
        source = FakeSource(bars())
        with HistoryRepository(self.root / "history.sqlite3") as repository:
            result = HistorySyncService(repository, source).sync(
                (instrument,), today=date(2026, 8, 20)
            )[0]
            self.assertEqual(result.status, "failed")
            self.assertIn("首次回补未返回", result.message)

    def test_one_symbol_failure_does_not_rollback_other_symbols(self) -> None:
        good = Instrument("000333.SZ", "美的集团", "stock")
        bad = Instrument("510300.SH", "沪深300ETF", "etf")

        class PartlyFailingSource(FakeSource):
            def fetch_daily(self, code: str, start: date, end: date, dividend_type: str) -> pd.DataFrame:
                if code == bad.code:
                    raise RuntimeError("模拟数据源失败")
                return super().fetch_daily(code, start, end, dividend_type)

        with HistoryRepository(self.root / "history.sqlite3") as repository:
            results = HistorySyncService(
                repository,
                PartlyFailingSource(bars("2026-08-20")),
            ).sync((good, bad), today=date(2026, 8, 20))
            self.assertEqual([result.status for result in results], ["updated", "failed"])
            self.assertEqual(repository.count_bars(good.code), 1)
            self.assertEqual(repository.count_bars(bad.code), 0)


if __name__ == "__main__":
    unittest.main()
