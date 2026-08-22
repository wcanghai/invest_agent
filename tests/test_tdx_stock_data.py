from datetime import date
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from tdx_history.config import Instrument
from tdx_history.stock_data.cli import DEFAULT_CONFIG, PROJECT_ROOT, build_summary
from tdx_history.stock_data.repository import StockDataRepository
from tdx_history.stock_data.service import StockDataSyncService
from tdx_history.stock_data.source import field_series_records, records_from_payload


class FakeStockSource:
    def fetch_daily(
        self, code: str, start: date, end: date, dividend_type: str
    ) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "trade_date": ["2026-08-20"],
                "open": [10.0],
                "high": [11.0],
                "low": [9.0],
                "close": [10.5],
                "volume": [100.0],
                "amount": [1000.0],
            }
        )

    def fetch_dividends(self, code: str, start: date, end: date) -> list[dict[str, object]]:
        return [{"Date": "20250620", "Type": 1, "Bonus": 2.0}]

    def fetch_market_snapshot(self, code: str) -> dict[str, object]:
        return {"Now": 10.5, "Buyp": [10.4, 10.3], "ErrorId": 0}

    def fetch_stock_info(self, code: str) -> dict[str, object]:
        return {"Name": "样本", "Unit": 100, "IsSTGP": 0}

    def fetch_more_info(self, code: str) -> dict[str, object]:
        return {"DynaPE": 12.3, "PB_MRQ": 1.5}

    def fetch_share_capital(
        self, code: str, observation_dates: tuple[date, ...]
    ) -> list[dict[str, object]]:
        return [{"Date": "20260820", "Ltgb": 1000, "Zgb": 1200}]

    def fetch_financial_data(
        self, code: str, start: date, end: date, report_type: str
    ) -> list[dict[str, object]]:
        return [{"Date": "2025-12-31", "Fn193": 1.2, "Fn196": 8.8}]

    def fetch_gp_trading(
        self, code: str, start: date, end: date
    ) -> list[dict[str, object]]:
        return [{"Date": "20260820", "GP1": 100, "GP2": 1000}]

    def fetch_gp_single(self, code: str) -> dict[str, object]:
        return {"GO1": 5.0, "GO47": "20000101"}

    def fetch_relations(self, code: str) -> list[dict[str, object]]:
        return [{"Code": "BK001", "Name": "测试行业", "Type": "industry"}]


class TdxStockDataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.instrument = Instrument("600000.SH", "浦发银行", "stock")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_stock_data_cli_defaults_to_repository_config(self) -> None:
        self.assertEqual(PROJECT_ROOT, Path(__file__).resolve().parents[1])
        self.assertEqual(DEFAULT_CONFIG, PROJECT_ROOT / "config" / "tdx_stock_samples.json")

    def test_records_from_payload_handles_code_dataframe_and_columnar_dict(self) -> None:
        frame = pd.DataFrame({"Fn193": [1.0]}, index=pd.to_datetime(["2025-12-31"]))
        records = records_from_payload({"600000.SH": frame}, "600000.SH")
        self.assertEqual(records[0]["Fn193"], 1.0)
        self.assertIn("Date", records[0])
        self.assertEqual(
            records_from_payload({"Date": ["20260101"], "GP1": [100]}),
            [{"Date": "20260101", "GP1": 100}],
        )

    def test_field_series_records_merges_gp_values_by_date(self) -> None:
        payload = {
            "600000.SH": {
                "GP1": [{"Date": "20260101", "Value": ["100", "0"]}],
                "GP2": [{"Date": "20260101", "Value": ["200", "0"]}],
            }
        }
        self.assertEqual(
            field_series_records(payload, "600000.SH"),
            [{"Date": "20260101", "GP1": ["100", "0"], "GP2": ["200", "0"]}],
        )

    def test_repository_core_tables_are_idempotent(self) -> None:
        path = self.root / "stock.sqlite3"
        with StockDataRepository(path) as repository:
            repository.upsert_instrument(self.instrument)
            action = [{"Date": "20250620", "Type": 1, "Bonus": 2.0}]
            self.assertEqual(repository.insert_corporate_actions(self.instrument.code, action), 1)
            self.assertEqual(repository.insert_corporate_actions(self.instrument.code, action), 0)

            capital = [{"Date": "20260820", "Ltgb": 1000, "Zgb": 1200}]
            repository.upsert_share_capital(self.instrument.code, capital)
            repository.upsert_share_capital(self.instrument.code, capital)
            count = repository.connection.execute("SELECT COUNT(*) FROM share_capital").fetchone()[0]
            self.assertEqual(count, 1)

            repository.upsert_dataset_records(
                self.instrument.code,
                "stock_info",
                date(2026, 8, 20),
                [{"Name": "浦发银行", "Unit": 100}],
            )
            repository.upsert_dataset_records(
                self.instrument.code,
                "stock_info",
                date(2026, 8, 20),
                [{"Name": "浦发银行", "Unit": 100}],
            )
            count = repository.connection.execute(
                "SELECT COUNT(*) FROM stock_dataset_records"
            ).fetchone()[0]
            self.assertEqual(count, 1)
            self.assertEqual(repository.fields_for_dataset("stock_info"), ("Name", "Unit"))

    def test_relations_allow_same_block_code_with_different_relation_records(self) -> None:
        with StockDataRepository(self.root / "stock.sqlite3") as repository:
            repository.upsert_instrument(self.instrument)
            count = repository.replace_relations(
                self.instrument.code,
                date(2026, 8, 20),
                [
                    {"BlockCode": "880001", "BlockName": "行业A", "BlockType": 1},
                    {"BlockCode": "880001", "BlockName": "概念B", "BlockType": 2},
                ],
            )
            self.assertEqual(count, 2)
            self.assertEqual(
                repository.connection.execute("SELECT COUNT(*) FROM stock_relations").fetchone()[0],
                2,
            )

    def test_service_collects_all_datasets_and_persists_results(self) -> None:
        path = self.root / "stock.sqlite3"
        with StockDataRepository(path) as repository:
            service = StockDataSyncService(repository, FakeStockSource(), years=10)
            first = service.sync(
                (self.instrument,),
                {self.instrument.code: "沪市主板-银行"},
                today=date(2026, 8, 20),
            )
            second = service.sync(
                (self.instrument,),
                {self.instrument.code: "沪市主板-银行"},
                today=date(2026, 8, 20),
            )
            self.assertEqual(len(first), 11)
            self.assertTrue(all(item.status == "success" for item in first))
            self.assertEqual(len(second), 11)
            self.assertEqual(repository.count_bars(self.instrument.code), 1)
            self.assertEqual(
                repository.connection.execute("SELECT COUNT(*) FROM corporate_actions").fetchone()[0],
                1,
            )
            self.assertEqual(
                repository.connection.execute("SELECT COUNT(*) FROM financial_facts").fetchone()[0],
                4,
            )
            self.assertEqual(
                repository.connection.execute("SELECT COUNT(*) FROM stock_relations").fetchone()[0],
                1,
            )

    def test_one_dataset_failure_is_reported_without_stopping_others(self) -> None:
        class PartlyFailingSource(FakeStockSource):
            def fetch_more_info(self, code: str) -> dict[str, object]:
                raise RuntimeError("模拟扩展信息失败")

        with StockDataRepository(self.root / "stock.sqlite3") as repository:
            results = StockDataSyncService(repository, PartlyFailingSource()).sync(
                (self.instrument,),
                {self.instrument.code: "样本"},
                today=date(2026, 8, 20),
            )
        statuses = {item.dataset: item.status for item in results}
        self.assertEqual(statuses["more_info"], "failed")
        self.assertEqual(statuses["stock_info"], "success")
        self.assertEqual(statuses["daily_bars"], "success")

    def test_summary_contains_dataset_fields(self) -> None:
        with StockDataRepository(self.root / "stock.sqlite3") as repository:
            results = StockDataSyncService(repository, FakeStockSource()).sync(
                (self.instrument,), {self.instrument.code: "样本"}, today=date(2026, 8, 20)
            )
        summary = build_summary(
            (self.instrument,),
            {self.instrument.code: "样本"},
            date(2026, 8, 20),
            self.root / "stock.sqlite3",
            results,
        )
        self.assertEqual(summary["instrument_count"], 1)
        self.assertIn("DynaPE", summary["fields_by_dataset"]["more_info"])
        json.dumps(summary, ensure_ascii=False)

    def test_history_end_cannot_be_after_observation_date(self) -> None:
        with StockDataRepository(self.root / "stock.sqlite3") as repository:
            with self.assertRaisesRegex(ValueError, "不能晚于"):
                StockDataSyncService(repository, FakeStockSource()).sync(
                    (self.instrument,),
                    {self.instrument.code: "样本"},
                    today=date(2026, 8, 20),
                    history_end=date(2026, 8, 21),
                )


if __name__ == "__main__":
    unittest.main()
