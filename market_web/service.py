"""按自然日生成一次并永久缓存日报。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from threading import Lock

from market_report.service import MarketReportSnapshot
from market_web.repository import DailyReportRecord, DailyReportRepository


ReportGenerator = Callable[[datetime], MarketReportSnapshot]


class DailyReportService:
    def __init__(self, repository: DailyReportRepository, generator: ReportGenerator):
        self.repository = repository
        self.generator = generator
        self._locks: dict[date, Lock] = {}
        self._locks_guard = Lock()

    def get(self, report_date: date) -> DailyReportRecord | None:
        return self.repository.get(report_date)

    def get_or_create_today(self, now: datetime | None = None) -> DailyReportRecord:
        requested_at = now or datetime.now()
        report_date = requested_at.date()
        existing = self.repository.get(report_date)
        if existing:
            return existing

        lock = self._lock_for(report_date)
        with lock:
            existing = self.repository.get(report_date)
            if existing:
                return existing
            snapshot = self.generator(requested_at)
            return self.repository.save(
                report_date,
                snapshot.generated_at,
                snapshot.markdown,
                snapshot.persisted_data(),
            )

    def list_reports(self, limit: int = 366) -> list[DailyReportRecord]:
        return self.repository.list_reports(limit)

    def _lock_for(self, report_date: date) -> Lock:
        with self._locks_guard:
            return self._locks.setdefault(report_date, Lock())
