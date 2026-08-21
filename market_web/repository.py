"""每日市场报告的 SQLite 永久存储。"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DailyReportRecord:
    report_date: date
    generated_at: datetime
    markdown: str
    snapshot: dict[str, Any]
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_date": self.report_date.isoformat(),
            "generated_at": self.generated_at.isoformat(timespec="seconds"),
            "created_at": self.created_at.isoformat(timespec="seconds"),
            "markdown": self.markdown,
            "snapshot": self.snapshot,
        }


class DailyReportRepository:
    """使用短连接访问 SQLite，确保 Web 请求之间数据持久化。"""

    def __init__(self, path: Path):
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_reports (
                    report_date TEXT PRIMARY KEY,
                    generated_at TEXT NOT NULL,
                    markdown TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute("PRAGMA optimize")

    def get(self, report_date: date) -> DailyReportRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT report_date, generated_at, markdown, snapshot_json, created_at
                FROM daily_reports
                WHERE report_date = ?
                """,
                (report_date.isoformat(),),
            ).fetchone()
        return self._record(row) if row else None

    def save(
        self,
        report_date: date,
        generated_at: datetime,
        markdown: str,
        snapshot: dict[str, Any],
    ) -> DailyReportRecord:
        created_at = datetime.now(timezone.utc)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO daily_reports(
                    report_date, generated_at, markdown, snapshot_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    report_date.isoformat(),
                    generated_at.isoformat(timespec="seconds"),
                    markdown,
                    json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")),
                    created_at.isoformat(timespec="seconds"),
                ),
            )
        record = self.get(report_date)
        if record is None:  # pragma: no cover - 仅数据库异常时触发
            raise RuntimeError(f"日报写入后无法读取：{report_date}")
        return record

    def list_reports(self, limit: int = 366) -> list[DailyReportRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT report_date, generated_at, markdown, snapshot_json, created_at
                FROM daily_reports
                ORDER BY report_date DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._record(row) for row in rows]

    def count(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM daily_reports").fetchone()
        return int(row["count"])

    def check(self) -> None:
        with self._connect() as connection:
            connection.execute("SELECT 1").fetchone()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    @staticmethod
    def _record(row: sqlite3.Row) -> DailyReportRecord:
        return DailyReportRecord(
            report_date=date.fromisoformat(row["report_date"]),
            generated_at=datetime.fromisoformat(row["generated_at"]),
            markdown=row["markdown"],
            snapshot=json.loads(row["snapshot_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )
