"""标的、历史行情和同步审计的 SQLite repository。"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from daily_report.storage.database import connect_database, initialize_database


SOURCE_BY_CATEGORY = {
    "a_share_stocks": "tdx",
    "industry_etfs": "tdx",
    "a_share_indices": "tdx",
    "commodity_futures": "tdx",
    "us_stocks": "yahoo",
    "crypto_pairs": "coinbase",
}


class MarketRepository:
    """使用幂等 UPSERT 管理日报所需的历史行情。"""

    def __init__(self, path: Path):
        self.path = path.resolve()
        initialize_database(self.path)

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def sync_instruments(self, universe: Mapping[str, Mapping[str, str]]) -> None:
        now = self._utc_now()
        rows: list[tuple[Any, ...]] = []
        for category, source in SOURCE_BY_CATEGORY.items():
            for sort_order, (code, name) in enumerate(universe.get(category, {}).items()):
                rows.append((category, code, name, source, sort_order, 1, now))
        with connect_database(self.path) as connection:
            connection.execute("UPDATE instruments SET active=0")
            connection.executemany(
                """
                INSERT INTO instruments(category,code,name,source,sort_order,active,updated_at)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(category,code) DO UPDATE SET
                    name=excluded.name, source=excluded.source,
                    sort_order=excluded.sort_order, active=1, updated_at=excluded.updated_at
                """,
                rows,
            )

    def upsert_bars(
        self,
        category: str,
        code: str,
        records: pd.DataFrame | Iterable[Mapping[str, Any]],
        *,
        source: str | None = None,
    ) -> int:
        normalized = _normalise_records(records)
        if not normalized:
            return 0
        now = self._utc_now()
        resolved_source = source or SOURCE_BY_CATEGORY.get(category, "unknown")
        rows = [
            (
                category,
                code,
                row["date"],
                _number(row.get("open")),
                _number(row.get("high")),
                _number(row.get("low")),
                float(row["close"]),
                _number(row.get("volume")),
                _number(row.get("amount")),
                resolved_source,
                now,
            )
            for row in normalized
        ]
        with connect_database(self.path) as connection:
            before = connection.total_changes
            connection.executemany(
                """
                INSERT INTO market_bars(
                    category,code,trade_date,open,high,low,close,volume,amount,source,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(category,code,trade_date) DO UPDATE SET
                    open=excluded.open, high=excluded.high, low=excluded.low,
                    close=excluded.close, volume=excluded.volume, amount=excluded.amount,
                    source=excluded.source, updated_at=excluded.updated_at
                """,
                rows,
            )
            return connection.total_changes - before

    def delete_bars(self, category: str, code: str) -> None:
        with connect_database(self.path) as connection:
            connection.execute(
                "DELETE FROM market_bars WHERE category=? AND code=?", (category, code)
            )

    def latest_date(self, category: str, code: str) -> date | None:
        with connect_database(self.path) as connection:
            row = connection.execute(
                "SELECT MAX(trade_date) AS value FROM market_bars WHERE category=? AND code=?",
                (category, code),
            ).fetchone()
        return date.fromisoformat(row["value"]) if row and row["value"] else None

    def count_bars(self, category: str | None = None, code: str | None = None) -> int:
        sql = "SELECT COUNT(*) AS count FROM market_bars WHERE 1=1"
        parameters: list[str] = []
        if category is not None:
            sql += " AND category=?"
            parameters.append(category)
        if code is not None:
            sql += " AND code=?"
            parameters.append(code)
        with connect_database(self.path) as connection:
            row = connection.execute(sql, parameters).fetchone()
        return int(row["count"])

    def date_range(self, category: str, code: str) -> tuple[str | None, str | None]:
        with connect_database(self.path) as connection:
            row = connection.execute(
                """
                SELECT MIN(trade_date) AS first_date, MAX(trade_date) AS last_date
                FROM market_bars WHERE category=? AND code=?
                """,
                (category, code),
            ).fetchone()
        return row["first_date"], row["last_date"]

    def price_position(
        self,
        category: str,
        code: str,
        reference_date: date,
        current_close: float,
    ) -> tuple[float | None, str]:
        try:
            cutoff = reference_date.replace(year=reference_date.year - 3)
        except ValueError:  # 2 月 29 日向前推三年时落到 2 月 28 日。
            cutoff = reference_date.replace(year=reference_date.year - 3, day=28)
        with connect_database(self.path) as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS sample_count, MIN(trade_date) AS first_date,
                       SUM(CASE WHEN close <= ? THEN 1 ELSE 0 END) AS below_count
                FROM market_bars
                WHERE category=? AND code=? AND trade_date>=?
                """,
                (float(current_close), category, code, cutoff.isoformat()),
            ).fetchone()
        count = int(row["sample_count"])
        first_date = date.fromisoformat(row["first_date"]) if row["first_date"] else None
        if not count:
            return None, "历史缓存缺失"
        if count < 500 or first_date is None or (first_date - cutoff).days > 45:
            return None, "历史样本不足"
        percentile = float(row["below_count"] or 0) / count * 100
        label = "价格偏低" if percentile <= 20 else "价格偏高" if percentile >= 80 else "价格中性"
        return percentile, label

    def rows(self, category: str, code: str) -> list[dict[str, Any]]:
        with connect_database(self.path) as connection:
            values = connection.execute(
                """
                SELECT trade_date AS date,open,high,low,close,volume,amount
                FROM market_bars WHERE category=? AND code=? ORDER BY trade_date
                """,
                (category, code),
            ).fetchall()
        return [dict(row) for row in values]


def _normalise_records(
    records: pd.DataFrame | Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    values = records.to_dict(orient="records") if isinstance(records, pd.DataFrame) else list(records)
    by_date: dict[str, dict[str, Any]] = {}
    for item in values:
        value = dict(item)
        parsed = pd.to_datetime(value.get("date"), errors="coerce")
        close = pd.to_numeric(value.get("close"), errors="coerce")
        if pd.isna(parsed) or pd.isna(close):
            continue
        value["date"] = parsed.strftime("%Y-%m-%d")
        value["close"] = float(close)
        by_date[value["date"]] = value
    return [by_date[key] for key in sorted(by_date)]


def _number(value: Any) -> float | None:
    parsed = pd.to_numeric(value, errors="coerce")
    return None if pd.isna(parsed) else float(parsed)
