"""数据同步运行的审计记录。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from daily_report.storage.database import connect_database, initialize_database


class SyncRunRepository:
    def __init__(self, path: Path):
        self.path = path.resolve()
        initialize_database(self.path)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def start(self, job_type: str) -> int:
        with connect_database(self.path) as connection:
            cursor = connection.execute(
                "INSERT INTO sync_runs(job_type,started_at,status) VALUES(?,?,?)",
                (job_type, self._now(), "running"),
            )
            return int(cursor.lastrowid)

    def finish(self, run_id: int, written_rows: int) -> None:
        with connect_database(self.path) as connection:
            connection.execute(
                """
                UPDATE sync_runs SET finished_at=?,status='success',inserted_rows=?
                WHERE id=?
                """,
                (self._now(), written_rows, run_id),
            )

    def fail(self, run_id: int, error: Exception) -> None:
        with connect_database(self.path) as connection:
            connection.execute(
                """
                UPDATE sync_runs SET finished_at=?,status='failed',message=? WHERE id=?
                """,
                (self._now(), f"{type(error).__name__}: {error}", run_id),
            )
