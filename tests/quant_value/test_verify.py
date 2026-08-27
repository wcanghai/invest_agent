from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from quant_value.config import Instrument
from quant_value.factors import build_factors
from quant_value.repository import (
    open_database,
    upsert_bars,
    upsert_financial_reports,
    upsert_instruments,
    upsert_relations,
    upsert_share_capital,
    upsert_snapshot,
)
from quant_value.verify import verify_coverage


def test_stock_requires_research_sources_and_factor_coverage(tmp_path: Path) -> None:
    captured = datetime.now(UTC).isoformat()
    code = "600519.SH"
    with open_database(tmp_path / "coverage.sqlite3") as connection:
        upsert_instruments(connection, [Instrument(code, "贵州茅台", "stock", "消费")], captured)
        upsert_bars(connection, code, [{
            "Date": "2026-08-25", "Open": 10, "High": 11, "Low": 9,
            "Close": 10, "Volume": 100, "Amount": 1000,
        }], captured)
        upsert_financial_reports(connection, code, [{
            "tag_time": "20260630", "announce_time": "20260801",
            "FN4": 5, "FN238": 1_000_000, "FN308": 100, "FN319": 200,
            "FN281": 20, "FN329": 15, "FN202": 60, "FN199": 30,
            "FN228": 90, "FN210": 30, "FN159": 2, "FN183": 10,
            "FN184": 8,
        }], captured)
        upsert_share_capital(
            connection, code, [{"Date": "2026-01-01", "Zgb": 1000}], captured
        )
        upsert_snapshot(connection, code, date(2026, 8, 26), {}, {}, {}, captured)
        upsert_relations(
            connection, code, date(2026, 8, 26),
            [{"BlockCode": "food", "BlockType": "行业"}], captured,
        )
        connection.commit()
        build_factors(connection, [code], rebuild=True)

        coverage = verify_coverage(connection, [code])[0]
        assert coverage.status == "通过"
        assert coverage.required_factor_coverage == 1.0
        assert coverage.capitals == 1
        assert coverage.snapshots == 1
        assert coverage.relations == 1

        connection.execute("DELETE FROM daily_snapshots WHERE code=?", (code,))
        connection.commit()
        missing = verify_coverage(connection, [code])[0]
        assert missing.status == "不通过"
        assert "无当日证券快照" in missing.notes
