"""SQLite 日线数据库。"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from tdx_history.config import Instrument


BAR_COLUMNS = ("trade_date", "open", "high", "low", "close", "volume", "amount")


class HistoryRepository:
    """封装 schema、幂等日线写入和同步状态。"""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.execute("PRAGMA busy_timeout = 5000")
        self._create_schema()

    def __enter__(self) -> "HistoryRepository":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self.connection.close()

    def _create_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS instruments (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                kind TEXT NOT NULL CHECK (kind IN ('stock', 'etf', 'fund')),
                dividend_type TEXT NOT NULL CHECK (dividend_type IN ('none', 'front', 'back')),
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS daily_bars (
                code TEXT NOT NULL REFERENCES instruments(code),
                trade_date TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL NOT NULL,
                volume REAL,
                amount REAL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (code, trade_date),
                CHECK (high IS NULL OR low IS NULL OR high >= low),
                CHECK (volume IS NULL OR volume >= 0),
                CHECK (amount IS NULL OR amount >= 0)
            ) WITHOUT ROWID;

            CREATE INDEX IF NOT EXISTS idx_daily_bars_date
                ON daily_bars(trade_date);

            CREATE TABLE IF NOT EXISTS sync_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                requested_codes INTEGER NOT NULL,
                inserted_rows INTEGER NOT NULL DEFAULT 0,
                failed_codes INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                message TEXT
            );
            """
        )
        self.connection.commit()

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def upsert_instrument(self, instrument: Instrument) -> None:
        existing = self.connection.execute(
            "SELECT dividend_type FROM instruments WHERE code = ?", (instrument.code,)
        ).fetchone()
        if existing and existing["dividend_type"] != instrument.dividend_type:
            bar_count = self.count_bars(instrument.code)
            if bar_count:
                raise ValueError(
                    f"{instrument.code} 已有 {bar_count} 条 {existing['dividend_type']} 数据，"
                    f"不能增量混入 {instrument.dividend_type} 数据。"
                )
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO instruments(code, name, kind, dividend_type, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    name=excluded.name,
                    kind=excluded.kind,
                    dividend_type=excluded.dividend_type,
                    updated_at=excluded.updated_at
                """,
                (
                    instrument.code,
                    instrument.name,
                    instrument.kind,
                    instrument.dividend_type,
                    self._utc_now(),
                ),
            )

    def latest_date(self, code: str) -> date | None:
        row = self.connection.execute(
            "SELECT MAX(trade_date) AS latest FROM daily_bars WHERE code = ?", (code,)
        ).fetchone()
        return date.fromisoformat(row["latest"]) if row and row["latest"] else None

    def insert_new_bars(self, code: str, frame: pd.DataFrame) -> int:
        """仅插入尚不存在的交易日，并在单个事务中完成。"""
        if frame.empty:
            return 0
        missing = [column for column in BAR_COLUMNS if column not in frame.columns]
        if missing:
            raise ValueError(f"日线数据缺少字段：{missing}")

        clean = frame.loc[:, BAR_COLUMNS].copy()
        clean["trade_date"] = pd.to_datetime(clean["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
        for column in BAR_COLUMNS[1:]:
            clean[column] = pd.to_numeric(clean[column], errors="coerce")
        clean = clean.dropna(subset=["trade_date", "close"])
        clean = clean.drop_duplicates(subset=["trade_date"], keep="last").sort_values("trade_date")
        if clean.empty:
            return 0
        if ((clean["high"].notna()) & (clean["low"].notna()) & (clean["high"] < clean["low"])).any():
            raise ValueError(f"{code} 存在 high < low 的日线。")
        if (clean["volume"].dropna() < 0).any() or (clean["amount"].dropna() < 0).any():
            raise ValueError(f"{code} 存在负的成交量或成交额。")

        before = self.connection.total_changes
        created_at = self._utc_now()
        rows = [
            (
                code,
                row.trade_date,
                _nullable_float(row.open),
                _nullable_float(row.high),
                _nullable_float(row.low),
                float(row.close),
                _nullable_float(row.volume),
                _nullable_float(row.amount),
                created_at,
            )
            for row in clean.itertuples(index=False)
        ]
        with self.connection:
            self.connection.executemany(
                """
                INSERT OR IGNORE INTO daily_bars(
                    code, trade_date, open, high, low, close, volume, amount, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return self.connection.total_changes - before

    def start_run(self, requested_codes: int) -> int:
        with self.connection:
            cursor = self.connection.execute(
                """
                INSERT INTO sync_runs(started_at, requested_codes, status)
                VALUES (?, ?, 'running')
                """,
                (self._utc_now(), requested_codes),
            )
        return int(cursor.lastrowid)

    def finish_run(self, run_id: int, inserted_rows: int, failed_codes: int, message: str) -> None:
        status = "success" if failed_codes == 0 else "partial_failure"
        with self.connection:
            self.connection.execute(
                """
                UPDATE sync_runs
                SET finished_at=?, inserted_rows=?, failed_codes=?, status=?, message=?
                WHERE id=?
                """,
                (self._utc_now(), inserted_rows, failed_codes, status, message, run_id),
            )

    def count_bars(self, code: str) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) AS count FROM daily_bars WHERE code = ?", (code,)
        ).fetchone()
        return int(row["count"])

    def date_range(self, code: str) -> tuple[str | None, str | None]:
        row = self.connection.execute(
            "SELECT MIN(trade_date) AS first, MAX(trade_date) AS last FROM daily_bars WHERE code = ?",
            (code,),
        ).fetchone()
        return row["first"], row["last"]


def _nullable_float(value: object) -> float | None:
    return None if pd.isna(value) else float(value)
