from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from market_report.service import MarketReportSnapshot
from market_web.app import create_app
from market_web.repository import DailyReportRepository
from market_web.service import DailyReportService


def _snapshot(generated_at: datetime) -> MarketReportSnapshot:
    return MarketReportSnapshot(
        source_date=generated_at.date(),
        generated_at=generated_at,
        markdown=(
            "# 测试市场日报\n\n"
            "| 标的 | 涨跌幅 | 三年价格分位 |\n"
            "|---|---:|---:|\n"
            "| 美的集团 | +4.20% | 85.00% |\n"
            "| 贵州茅台 | -3.50% | 10.00% |\n\n"
            "[东方财富](https://quote.eastmoney.com/sz000333.html)"
            "<script>alert('unsafe')</script>"
        ),
        data={
            "market_breadth": {
                "三市合计": {"amount": 12_345_600, "up": 3210, "down": 1760}
            }
        },
    )


def test_daily_service_generates_once_and_survives_restart(tmp_path):
    repository = DailyReportRepository(tmp_path / "reports.sqlite3")
    calls: list[datetime] = []

    def generator(generated_at: datetime) -> MarketReportSnapshot:
        calls.append(generated_at)
        return _snapshot(generated_at)

    requested_at = datetime(2026, 8, 21, 9, 30)
    service = DailyReportService(repository, generator)
    first = service.get_or_create_today(requested_at)
    second = service.get_or_create_today(requested_at + timedelta(hours=2))

    assert len(calls) == 1
    assert first == second
    assert repository.count() == 1

    restarted = DailyReportService(
        DailyReportRepository(tmp_path / "reports.sqlite3"),
        lambda _: pytest.fail("数据库已有当日报告，不应重新生成"),
    )
    restored = restarted.get_or_create_today(requested_at + timedelta(hours=4))
    assert restored.markdown == first.markdown
    assert restored.snapshot["source_date"] == "2026-08-21"


def test_failed_generation_is_not_persisted(tmp_path):
    repository = DailyReportRepository(tmp_path / "reports.sqlite3")

    def generator(_: datetime) -> MarketReportSnapshot:
        raise RuntimeError("行情源暂时不可用")

    service = DailyReportService(repository, generator)
    with pytest.raises(RuntimeError, match="行情源暂时不可用"):
        service.get_or_create_today(datetime(2026, 8, 21, 9, 30))

    assert repository.get(date(2026, 8, 21)) is None
    assert repository.count() == 0


def test_web_pages_and_api_use_the_same_persisted_report(tmp_path):
    calls: list[datetime] = []

    def generator(generated_at: datetime) -> MarketReportSnapshot:
        calls.append(generated_at)
        return _snapshot(generated_at)

    app = create_app(database_path=tmp_path / "reports.sqlite3", generator=generator)
    today = date.today().isoformat()

    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok", "stored_reports": 0}

        page = client.get("/")
        assert page.status_code == 200
        assert "测试市场日报" in page.text
        assert "美的集团" in page.text
        assert "https://quote.eastmoney.com/sz000333.html" in page.text
        assert 'target="_blank"' in page.text
        assert 'rel="noopener noreferrer"' in page.text
        assert "<script>" not in page.text
        assert client.get("/static/site.css").status_code == 200
        script = client.get("/static/report-tables.js")
        assert script.status_code == 200
        assert 'className = "sort-toggle"' in script.text
        assert "icon:" not in script.text
        assert "涨幅优先" in script.text
        assert "跌幅优先" in script.text
        assert "change > 3" in script.text
        assert "percentile > 80" in script.text
        assert "signal-marker" not in script.text
        assert "强势" not in script.text
        assert "高位" not in script.text
        style = client.get("/static/site.css").text
        assert '.sort-toggle::before, .sort-toggle::after' in style
        assert "color: #781123" in style
        assert "font-weight: 800" in style

        today_api = client.get("/api/reports/today")
        assert today_api.status_code == 200
        assert today_api.json()["report_date"] == today
        assert len(calls) == 1

        index = client.get("/api/reports").json()
        assert index["count"] == 1
        assert index["reports"][0]["report_date"] == today
        assert client.get(f"/reports/{today}").status_code == 200
        assert client.get(f"/api/reports/{today}").status_code == 200
        assert client.get("/api/reports/2000-01-01").status_code == 404
