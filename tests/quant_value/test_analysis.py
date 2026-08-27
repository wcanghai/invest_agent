from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from quant_value.analysis import analyze_stocks
from quant_value.config import Instrument
from quant_value.factors import build_factors
from quant_value.repository import (
    open_database,
    upsert_bars,
    upsert_financial_reports,
    upsert_instruments,
)


def test_analysis_uses_only_visible_annual_report_and_explains_scores(tmp_path: Path) -> None:
    captured = datetime.now(UTC).isoformat()
    with open_database(tmp_path / "analysis.sqlite3") as connection:
        upsert_instruments(
            connection, [Instrument("600519.SH", "样本股票", "stock", "消费")], captured
        )
        start = date(2024, 1, 1)
        upsert_bars(connection, "600519.SH", [
            {
                "Date": (start + timedelta(days=offset)).isoformat(),
                "Open": 10 + offset / 100, "High": 11 + offset / 100,
                "Low": 9 + offset / 100, "Close": 10 + offset / 100,
                "Volume": 1000, "Amount": 10000,
            }
            for offset in range(900)
        ], captured)
        upsert_financial_reports(connection, "600519.SH", [
            {
                "tag_time": "20241231", "announce_time": "20250401",
                "FN4": 8, "FN238": 1_000_000, "FN308": 100, "FN319": 1000,
                "FN281": 18, "FN329": 14, "FN202": 55, "FN199": 20,
                "FN228": 105, "FN210": 35, "FN159": 2.0, "FN183": 10,
                "FN184": 12, "FN185": 8, "FN336": 1, "FN337": 40,
            },
            {
                "tag_time": "20251231", "announce_time": "20260401",
                "FN4": 9, "FN238": 1_000_000, "FN308": 110, "FN319": 1100,
                "FN281": 20, "FN329": 16, "FN202": 56, "FN199": 21,
                "FN228": 110, "FN210": 32, "FN159": 2.2, "FN183": 11,
                "FN184": 14, "FN185": 9, "FN336": 3, "FN337": 45,
            },
        ], captured)
        connection.commit()
        build_factors(connection, rebuild=True)

        before = analyze_stocks(connection, ["600519.SH"], date(2025, 12, 31))[0]
        after = analyze_stocks(connection, ["600519.SH"], date(2026, 4, 2))[0]

        assert before.annual_report_date == "2024-12-31"
        assert before.quality.evidence["annual_roe"] == 18
        assert before.conclusion != "需先排除关键风险"
        assert after.annual_report_date == "2025-12-31"
        assert after.quality.evidence["annual_roe"] == 20
        assert after.overall_score is not None
        assert after.valuation.score is not None
        assert after.conclusion == "需先排除关键风险"
        assert any("审计意见" in risk for risk in after.risks)
        assert after.to_dict()["quality"]["score"] == after.quality.score


def test_analysis_rejects_etf_method_mismatch(tmp_path: Path) -> None:
    captured = datetime.now(UTC).isoformat()
    with open_database(tmp_path / "analysis.sqlite3") as connection:
        upsert_instruments(
            connection, [Instrument("510300.SH", "ETF", "etf", "宽基")], captured
        )
        upsert_bars(connection, "510300.SH", [{
            "Date": "2026-01-01", "Open": 4, "High": 4, "Low": 4,
            "Close": 4, "Volume": 1000, "Amount": 4000,
        }], captured)
        connection.commit()
        build_factors(connection, rebuild=True)

        try:
            analyze_stocks(connection, ["510300.SH"], date(2026, 1, 1))
        except ValueError as error:
            assert "不是股票" in str(error)
        else:
            raise AssertionError("ETF 不应套用股票价值评分")
