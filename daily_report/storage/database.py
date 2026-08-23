"""日报统一 SQLite 的连接、建表和轻量迁移。"""

from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS instruments (
    category TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    source TEXT NOT NULL,
    sort_order INTEGER NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (category, code)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS market_bars (
    category TEXT NOT NULL,
    code TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL NOT NULL,
    volume REAL,
    amount REAL,
    source TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (category, code, trade_date)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_market_bars_range
    ON market_bars(category, code, trade_date);

CREATE TABLE IF NOT EXISTS news_items (
    source TEXT NOT NULL,
    published_at TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT,
    content TEXT,
    url TEXT,
    captured_at TEXT NOT NULL,
    PRIMARY KEY (source, published_at, title)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_news_items_date ON news_items(published_at);

CREATE TABLE IF NOT EXISTS daily_reports (
    report_date TEXT PRIMARY KEY,
    source_date TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    markdown TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_type TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    inserted_rows INTEGER NOT NULL DEFAULT 0,
    updated_rows INTEGER NOT NULL DEFAULT 0,
    message TEXT
);
"""


def connect_database(path: Path) -> sqlite3.Connection:
    """打开配置了本地并发参数的短连接。"""
    resolved = path.resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(resolved, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA busy_timeout = 30000")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(path: Path) -> None:
    """创建统一 schema，并升级早期只有 daily_reports 的数据库。"""
    with connect_database(path) as connection:
        existing = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='daily_reports'"
        ).fetchone()
        if existing:
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(daily_reports)")
            }
            if "source_date" not in columns:
                connection.execute("ALTER TABLE daily_reports ADD COLUMN source_date TEXT")
                connection.execute(
                    "UPDATE daily_reports SET source_date=report_date WHERE source_date IS NULL"
                )
        connection.executescript(SCHEMA)
        connection.execute("PRAGMA optimize")
