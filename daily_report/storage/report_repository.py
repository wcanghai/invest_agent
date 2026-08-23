"""每日完整报告的 SQLite 永久存储。"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from daily_report.models import DailyReportRecord
from daily_report.storage.database import connect_database, initialize_database


class DailyReportRepository:
    """每日自然日只保存第一份成功报告。"""

    def __init__(self, path: Path):
        self.path = path.resolve()
        initialize_database(self.path)

    def get(self, report_date: date) -> DailyReportRecord | None:
        with connect_database(self.path) as connection:
            row = connection.execute(
                """
                SELECT report_date,source_date,generated_at,markdown,snapshot_json,created_at
                FROM daily_reports WHERE report_date=?
                """,
                (report_date.isoformat(),),
            ).fetchone()
        return self._record(row) if row else None

    def save(
        self,
        report_date: date,
        source_date: date,
        generated_at: datetime,
        markdown: str,
        snapshot: dict[str, Any],
    ) -> DailyReportRecord:
        created_at = datetime.now(timezone.utc)
        with connect_database(self.path) as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO daily_reports(
                    report_date,source_date,generated_at,markdown,snapshot_json,created_at
                ) VALUES(?,?,?,?,?,?)
                """,
                (
                    report_date.isoformat(), source_date.isoformat(),
                    generated_at.isoformat(timespec="seconds"), markdown,
                    json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")),
                    created_at.isoformat(timespec="seconds"),
                ),
            )
        record = self.get(report_date)
        if record is None:  # pragma: no cover
            raise RuntimeError(f"日报写入后无法读取：{report_date}")
        return record

    def list_reports(self, limit: int = 366) -> list[DailyReportRecord]:
        with connect_database(self.path) as connection:
            rows = connection.execute(
                """
                SELECT report_date,source_date,generated_at,markdown,snapshot_json,created_at
                FROM daily_reports ORDER BY report_date DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._record(row) for row in rows]

    def count(self) -> int:
        with connect_database(self.path) as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM daily_reports").fetchone()
        return int(row["count"])

    def check(self) -> None:
        with connect_database(self.path) as connection:
            connection.execute("SELECT 1").fetchone()

    @staticmethod
    def _record(row: Any) -> DailyReportRecord:
        return DailyReportRecord(
            report_date=date.fromisoformat(row["report_date"]),
            source_date=date.fromisoformat(row["source_date"] or row["report_date"]),
            generated_at=datetime.fromisoformat(row["generated_at"]),
            markdown=row["markdown"],
            snapshot=json.loads(row["snapshot_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )
