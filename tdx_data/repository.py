"""通达信归档的 SQLite 表结构和持久化操作。"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from tdx_data.field_mapping import display_name, group_name


FLAT_TABLES = {"stock_info_flat", "more_info_flat"}
SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS assets (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    market TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS daily_bars (
    code TEXT NOT NULL REFERENCES assets(code),
    trade_date TEXT NOT NULL,
    time TEXT,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume REAL,
    amount REAL,
    forward_factor REAL,
    vol_in_stock REAL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY(code, trade_date)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS raw_api_records (
    code TEXT NOT NULL REFERENCES assets(code),
    dataset TEXT NOT NULL,
    observed_date TEXT NOT NULL,
    record_key TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    PRIMARY KEY(code, dataset, observed_date, record_key)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS stock_info_flat (
    code TEXT NOT NULL REFERENCES assets(code),
    observed_date TEXT NOT NULL,
    PRIMARY KEY(code, observed_date)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS more_info_flat (
    code TEXT NOT NULL REFERENCES assets(code),
    observed_date TEXT NOT NULL,
    PRIMARY KEY(code, observed_date)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS stock_relations (
    code TEXT NOT NULL REFERENCES assets(code),
    observed_date TEXT NOT NULL,
    relation_key TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY(code, observed_date, relation_key)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS field_dictionary (
    dataset TEXT NOT NULL,
    field_name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    field_group TEXT NOT NULL,
    value_type TEXT NOT NULL,
    PRIMARY KEY(dataset, field_name)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    requested_codes INTEGER NOT NULL,
    inserted_bars INTEGER NOT NULL DEFAULT 0,
    failed_codes INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    message TEXT
);
"""


def open_database(path: Path) -> sqlite3.Connection:
    """打开本地数据库并创建归档表。"""
    resolved = path.resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(resolved, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=30000")
    connection.executescript(SCHEMA)
    connection.commit()
    return connection


def upsert_asset(
    connection: sqlite3.Connection,
    code: str,
    name: str,
    market: str,
    captured_at: str,
) -> None:
    connection.execute(
        """
        INSERT INTO assets VALUES(?,?,?,?)
        ON CONFLICT(code) DO UPDATE SET
            name=excluded.name,market=excluded.market,updated_at=excluded.updated_at
        """,
        (code, name, market, captured_at),
    )


def latest_date(connection: sqlite3.Connection, code: str) -> date | None:
    row = connection.execute(
        "SELECT MAX(trade_date) AS value FROM daily_bars WHERE code=?", (code,)
    ).fetchone()
    return date.fromisoformat(row["value"]) if row and row["value"] else None


def insert_daily(
    connection: sqlite3.Connection,
    code: str,
    rows: Iterable[dict[str, Any]],
    observed: date,
    captured_at: str,
) -> int:
    """按代码和日期幂等插入日线，并保留每行原始记录。"""
    inserted = 0
    for row in rows:
        trade_date = date_text(row.get("Date"))
        if not trade_date or row.get("Close") is None:
            continue
        cursor = connection.execute(
            "INSERT OR IGNORE INTO daily_bars VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                code,
                trade_date,
                row.get("Time"),
                *numbers(
                    row,
                    (
                        "Open",
                        "High",
                        "Low",
                        "Close",
                        "Volume",
                        "Amount",
                        "ForwardFactor",
                        "VolInStock",
                    ),
                ),
                json.dumps(row, ensure_ascii=False, default=str),
            ),
        )
        inserted += max(cursor.rowcount, 0)
        save_raw(connection, code, "daily", observed, row, trade_date, captured_at)
    return inserted


def save_raw(
    connection: sqlite3.Connection,
    code: str,
    dataset: str,
    observed: date,
    value: Any,
    record_key: str,
    captured_at: str,
) -> None:
    """保存接口的完整原始返回，供后续重新加工。"""
    connection.execute(
        """
        INSERT INTO raw_api_records VALUES(?,?,?,?,?,?)
        ON CONFLICT(code,dataset,observed_date,record_key) DO UPDATE SET
            payload_json=excluded.payload_json,captured_at=excluded.captured_at
        """,
        (
            code,
            dataset,
            observed.isoformat(),
            record_key,
            json.dumps(value, ensure_ascii=False, default=str),
            captured_at,
        ),
    )


def upsert_flat(
    connection: sqlite3.Connection,
    table: str,
    code: str,
    observed: date,
    value: Any,
) -> None:
    """将字典动态展开成平铺列，并登记英文到中文的字段映射。"""
    if table not in FLAT_TABLES:
        raise ValueError(f"不支持的平铺表：{table}")
    if not isinstance(value, dict) or not value:
        return
    values = {"code": code, "observed_date": observed.isoformat()}
    dataset = table.removesuffix("_flat")
    for key, item in value.items():
        name = str(key)
        values[flat_column(name)] = flat_value(item)
        connection.execute(
            """
            INSERT INTO field_dictionary VALUES(?,?,?,?,?)
            ON CONFLICT(dataset,field_name) DO UPDATE SET
                display_name=excluded.display_name,
                field_group=excluded.field_group,
                value_type=excluded.value_type
            """,
            (dataset, name, display_name(name), group_name(name), value_type(item)),
        )
    columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
    for column, item in values.items():
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type(item)}")
    names = list(values)
    placeholders = ",".join("?" for _ in names)
    quoted_names = ",".join(quote(name) for name in names)
    connection.execute(
        f"INSERT OR REPLACE INTO {table} ({quoted_names}) VALUES ({placeholders})",
        [values[name] for name in names],
    )


def replace_relations(
    connection: sqlite3.Connection, code: str, observed: date, values: Any
) -> None:
    connection.execute(
        "DELETE FROM stock_relations WHERE code=? AND observed_date=?",
        (code, observed.isoformat()),
    )
    for index, item in enumerate(values if isinstance(values, list) else []):
        connection.execute(
            "INSERT INTO stock_relations VALUES(?,?,?,?)",
            (
                code,
                observed.isoformat(),
                f"{index:06d}",
                json.dumps(item, ensure_ascii=False, default=str),
            ),
        )


def start_run(connection: sqlite3.Connection, count: int, started_at: str) -> int:
    cursor = connection.execute(
        "INSERT INTO sync_runs(started_at,requested_codes,status) VALUES(?,?,?)",
        (started_at, count, "running"),
    )
    return int(cursor.lastrowid)


def finish_run(
    connection: sqlite3.Connection,
    run_id: int,
    inserted: int,
    failed: int,
    finished_at: str,
) -> None:
    connection.execute(
        """
        UPDATE sync_runs
        SET finished_at=?,inserted_bars=?,failed_codes=?,status=?,message=?
        WHERE id=?
        """,
        (
            finished_at,
            inserted,
            failed,
            "success" if failed == 0 else "partial_failure",
            f"失败股票 {failed}",
            run_id,
        ),
    )


def date_text(value: Any) -> str | None:
    text = str(value) if value is not None else ""
    if len(text) >= 10 and text[4] == "-":
        return text[:10]
    digits = "".join(character for character in text if character.isdigit())
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}" if len(digits) >= 8 else None


def numbers(row: dict[str, Any], names: tuple[str, ...]) -> list[float | None]:
    result: list[float | None] = []
    for name in names:
        try:
            result.append(None if row.get(name) in (None, "", "--") else float(row[name]))
        except (TypeError, ValueError):
            result.append(None)
    return result


def flat_column(name: str) -> str:
    return "f_" + (re.sub(r"[^A-Za-z0-9_]", "_", name) or "unknown")


def flat_value(value: Any) -> Any:
    return (
        json.dumps(value, ensure_ascii=False, default=str)
        if isinstance(value, (dict, list, tuple))
        else value
    )


def quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def sql_type(value: Any) -> str:
    return "REAL" if isinstance(value, (int, float)) and not isinstance(value, bool) else "TEXT"


def value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, (list, tuple)):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "text"
