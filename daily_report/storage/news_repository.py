"""财经新闻的 SQLite 去重与查询。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from daily_report.storage.database import connect_database, initialize_database


class NewsRepository:
    def __init__(self, path: Path):
        self.path = path.resolve()
        initialize_database(self.path)

    def upsert(self, records: pd.DataFrame | Iterable[Mapping[str, Any]]) -> int:
        values = records.to_dict(orient="records") if isinstance(records, pd.DataFrame) else list(records)
        captured_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rows: list[tuple[str, ...]] = []
        for item in values:
            source = str(item.get("来源") or item.get("source") or "").strip()
            title = str(item.get("标题") or item.get("title") or "").strip()
            published = pd.to_datetime(item.get("发布时间") or item.get("published_at"), errors="coerce")
            if not source or not title or pd.isna(published):
                continue
            rows.append(
                (
                    source,
                    published.isoformat(),
                    title,
                    str(item.get("摘要") or item.get("summary") or ""),
                    str(item.get("正文") or item.get("content") or ""),
                    str(item.get("链接") or item.get("url") or ""),
                    captured_at,
                )
            )
        if not rows:
            return 0
        with connect_database(self.path) as connection:
            before = connection.total_changes
            connection.executemany(
                """
                INSERT INTO news_items(source,published_at,title,summary,content,url,captured_at)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(source,published_at,title) DO UPDATE SET
                    summary=excluded.summary, content=excluded.content,
                    url=excluded.url, captured_at=excluded.captured_at
                """,
                rows,
            )
            return connection.total_changes - before

    def for_date(self, target: date) -> list[dict[str, Any]]:
        with connect_database(self.path) as connection:
            rows = connection.execute(
                """
                SELECT source,published_at,title,summary,content,url
                FROM news_items
                WHERE substr(published_at,1,10)=?
                ORDER BY published_at DESC
                """,
                (target.isoformat(),),
            ).fetchall()
        return [dict(row) for row in rows]

    def count(self) -> int:
        with connect_database(self.path) as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM news_items").fetchone()
        return int(row["count"])
