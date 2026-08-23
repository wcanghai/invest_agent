from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from daily_report.storage.news_repository import NewsRepository
from daily_report.storage.report_repository import DailyReportRepository


def test_news_repository_deduplicates_same_source_time_and_title(tmp_path: Path) -> None:
    repository = NewsRepository(tmp_path / "daily_report.sqlite3")
    item = {
        "来源": "新浪财经",
        "发布时间": "2026-08-23T09:30:00",
        "标题": "测试新闻",
        "摘要": "初始摘要",
    }
    repository.upsert([item, item])
    repository.upsert([{**item, "摘要": "更新摘要"}])

    assert repository.count() == 1
    assert repository.for_date(date(2026, 8, 23))[0]["summary"] == "更新摘要"


def test_daily_report_repository_keeps_first_success_of_the_day(tmp_path: Path) -> None:
    repository = DailyReportRepository(tmp_path / "daily_report.sqlite3")
    target = date(2026, 8, 23)
    repository.save(target, target, datetime(2026, 8, 23, 9), "first", {"data": {}})
    repository.save(target, target, datetime(2026, 8, 23, 10), "second", {"data": {}})

    record = repository.get(target)
    assert record is not None
    assert record.markdown == "first"
    assert repository.count() == 1
