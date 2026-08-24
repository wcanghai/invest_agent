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
CREATE TABLE IF NOT EXISTS asset_groups (
    code TEXT NOT NULL REFERENCES assets(code),
    group_name TEXT NOT NULL,
    selected_at TEXT NOT NULL,
    liquidity_rank INTEGER,
    latest_amount REAL,
    PRIMARY KEY(code, group_name)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS asset_group_history (
    code TEXT NOT NULL REFERENCES assets(code),
    group_name TEXT NOT NULL,
    observed_date TEXT NOT NULL,
    liquidity_rank INTEGER,
    latest_amount REAL,
    captured_at TEXT NOT NULL,
    PRIMARY KEY(code, group_name, observed_date)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS financial_reports (
    code TEXT NOT NULL REFERENCES assets(code),
    report_date TEXT NOT NULL,
    announce_date TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    PRIMARY KEY(code, report_date, announce_date)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS ix_financial_reports_announce
    ON financial_reports(code, announce_date);
CREATE TABLE IF NOT EXISTS financial_report_values (
    code TEXT NOT NULL,
    report_date TEXT NOT NULL,
    announce_date TEXT NOT NULL,
    field_name TEXT NOT NULL,
    numeric_value REAL,
    text_value TEXT,
    PRIMARY KEY(code, report_date, announce_date, field_name),
    FOREIGN KEY(code, report_date, announce_date)
        REFERENCES financial_reports(code, report_date, announce_date)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS share_capital_history (
    code TEXT NOT NULL REFERENCES assets(code),
    effective_date TEXT NOT NULL,
    float_shares REAL,
    total_shares REAL,
    payload_json TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    PRIMARY KEY(code, effective_date)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS corporate_actions (
    code TEXT NOT NULL REFERENCES assets(code),
    action_date TEXT NOT NULL,
    record_key TEXT NOT NULL,
    action_type TEXT,
    cash_dividend REAL,
    bonus_shares REAL,
    allotment_shares REAL,
    allotment_price REAL,
    payload_json TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    PRIMARY KEY(code, action_date, record_key)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS quant_daily_wide (
    code TEXT NOT NULL REFERENCES assets(code),
    trade_date TEXT NOT NULL,
    name TEXT NOT NULL,
    market TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL NOT NULL,
    volume REAL,
    amount REAL,
    forward_factor REAL,
    vol_in_stock REAL,
    prev_close REAL,
    return_1d REAL,
    return_5d REAL,
    return_20d REAL,
    log_return_1d REAL,
    intraday_return REAL,
    amplitude REAL,
    close_ma5 REAL,
    close_ma20 REAL,
    volume_ma20 REAL,
    amount_ma20 REAL,
    report_date TEXT,
    announce_date TEXT,
    report_age_days INTEGER,
    fn193 REAL,
    fn194 REAL,
    fn195 REAL,
    fn196 REAL,
    fn197 REAL,
    fn198 REAL,
    fn199 REAL,
    fn200 REAL,
    share_capital_date TEXT,
    float_shares REAL,
    total_shares REAL,
    market_cap REAL,
    float_market_cap REAL,
    action_count INTEGER NOT NULL DEFAULT 0,
    action_types TEXT,
    cash_dividend REAL,
    bonus_shares REAL,
    allotment_shares REAL,
    allotment_price REAL,
    days_since_action INTEGER,
    snapshot_date TEXT,
    snapshot_hq_date TEXT,
    snapshot_dynamic_pe REAL,
    snapshot_static_pe_ttm REAL,
    snapshot_pb_mrq REAL,
    snapshot_dividend_yield REAL,
    snapshot_turnover_rate REAL,
    snapshot_beta REAL,
    snapshot_total_market_cap REAL,
    snapshot_float_market_cap REAL,
    snapshot_total_assets REAL,
    snapshot_current_assets REAL,
    snapshot_current_liabilities REAL,
    snapshot_long_term_liabilities REAL,
    snapshot_equity REAL,
    snapshot_revenue REAL,
    snapshot_operating_profit REAL,
    snapshot_net_profit REAL,
    snapshot_operating_cash_flow REAL,
    snapshot_inventory REAL,
    snapshot_receivables REAL,
    snapshot_eps REAL,
    snapshot_bps REAL,
    snapshot_shareholders REAL,
    snapshot_industry_code TEXT,
    snapshot_industry_name TEXT,
    snapshot_tdx_industry_code TEXT,
    snapshot_tdx_industry_name TEXT,
    snapshot_is_st INTEGER,
    snapshot_hs300_member INTEGER,
    snapshot_margin_eligible INTEGER,
    snapshot_hk_connect INTEGER,
    recent_notice_date TEXT,
    recent_repurchase_date TEXT,
    recent_insider_trade_date TEXT,
    recent_incentive_date TEXT,
    recent_unlock_date TEXT,
    recent_block_trade_date TEXT,
    recent_halt_date TEXT,
    built_at TEXT NOT NULL,
    PRIMARY KEY(code, trade_date)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS ix_quant_daily_wide_date
    ON quant_daily_wide(trade_date, code);
CREATE INDEX IF NOT EXISTS ix_quant_daily_wide_report
    ON quant_daily_wide(code, report_date, announce_date);
CREATE TABLE IF NOT EXISTS quant_wide_build_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    requested_codes INTEGER NOT NULL,
    written_rows INTEGER NOT NULL DEFAULT 0,
    failed_codes INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    message TEXT
);
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
    migrate_schema(connection)
    connection.commit()
    return connection


def migrate_schema(connection: sqlite3.Connection) -> None:
    """只做向前兼容加列，使已创建的归档库可继续使用。"""
    ensure_columns(
        connection,
        "corporate_actions",
        {
            "action_type": "TEXT",
            "cash_dividend": "REAL",
            "bonus_shares": "REAL",
            "allotment_shares": "REAL",
            "allotment_price": "REAL",
        },
    )
    ensure_columns(
        connection,
        "quant_daily_wide",
        {
            "snapshot_industry_code": "TEXT",
            "snapshot_industry_name": "TEXT",
            "snapshot_tdx_industry_code": "TEXT",
            "snapshot_tdx_industry_name": "TEXT",
            "snapshot_is_st": "INTEGER",
            "snapshot_hs300_member": "INTEGER",
            "snapshot_margin_eligible": "INTEGER",
            "snapshot_hk_connect": "INTEGER",
        },
    )
    backfill_financial_report_values(connection)


def ensure_columns(
    connection: sqlite3.Connection, table: str, columns: dict[str, str]
) -> None:
    """为受控表补充缺失列，不删除或重写现有数据。"""
    existing = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}
    for name, definition in columns.items():
        if name not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {quote(name)} {definition}")


def backfill_financial_report_values(connection: sqlite3.Connection) -> None:
    """把旧版只存 JSON 的财报记录补充到字段明细表。"""
    rows = connection.execute(
        """
        SELECT report.code, report.report_date, report.announce_date,
               report.payload_json, report.captured_at
        FROM financial_reports AS report
        WHERE NOT EXISTS (
            SELECT 1 FROM financial_report_values AS value
            WHERE value.code=report.code
              AND value.report_date=report.report_date
              AND value.announce_date=report.announce_date
        )
        """
    ).fetchall()
    for row in rows:
        try:
            payload = json.loads(str(row["payload_json"]))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        payload.setdefault("tag_time", str(row["report_date"]).replace("-", ""))
        payload.setdefault("announce_time", str(row["announce_date"]).replace("-", ""))
        upsert_financial_reports(
            connection,
            str(row["code"]),
            [payload],
            str(row["captured_at"]),
        )


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


def replace_asset_groups(
    connection: sqlite3.Connection,
    code: str,
    groups: Iterable[str],
    selected_at: str,
    liquidity_rank: int | None = None,
    latest_amount: float | None = None,
    observed: date | None = None,
) -> None:
    """保存本次定向清单中的指数或 ETF 集合归属。"""
    connection.execute("DELETE FROM asset_groups WHERE code=?", (code,))
    connection.executemany(
        "INSERT INTO asset_groups VALUES(?,?,?,?,?)",
        [
            (code, group, selected_at, liquidity_rank, latest_amount)
            for group in dict.fromkeys(groups)
        ],
    )
    observed_text = (observed or date.fromisoformat(selected_at[:10])).isoformat()
    connection.executemany(
        """
        INSERT INTO asset_group_history VALUES(?,?,?,?,?,?)
        ON CONFLICT(code,group_name,observed_date) DO UPDATE SET
            liquidity_rank=excluded.liquidity_rank,
            latest_amount=excluded.latest_amount,
            captured_at=excluded.captured_at
        """,
        [
            (
                code,
                group,
                observed_text,
                liquidity_rank,
                latest_amount,
                selected_at,
            )
            for group in dict.fromkeys(groups)
        ],
    )


def latest_history_date(
    connection: sqlite3.Connection, table: str, column: str, code: str
) -> date | None:
    """读取受支持历史表的最后业务日期。"""
    allowed = {
        ("financial_reports", "announce_date"),
        ("share_capital_history", "effective_date"),
        ("corporate_actions", "action_date"),
    }
    if (table, column) not in allowed:
        raise ValueError(f"不支持的历史日期列：{table}.{column}")
    row = connection.execute(
        f"SELECT MAX({column}) AS value FROM {table} WHERE code=?", (code,)
    ).fetchone()
    return date.fromisoformat(row["value"]) if row and row["value"] else None


def upsert_financial_reports(
    connection: sqlite3.Connection,
    code: str,
    rows: Iterable[dict[str, Any]],
    captured_at: str,
) -> int:
    """保存财报原文，并把所有返回字段拆到可查询的明细表。"""
    count = 0
    for row in rows:
        report_date = date_text(row.get("tag_time") or row.get("report_date"))
        announce_date = date_text(row.get("announce_time") or row.get("announce_date"))
        if not report_date or not announce_date:
            continue
        connection.execute(
            """
            INSERT INTO financial_reports(
                code,report_date,announce_date,payload_json,captured_at
            ) VALUES(?,?,?,?,?)
            ON CONFLICT(code,report_date,announce_date) DO UPDATE SET
                payload_json=excluded.payload_json,captured_at=excluded.captured_at
            """,
            (
                code,
                report_date,
                announce_date,
                json.dumps(row, ensure_ascii=False, default=str),
                captured_at,
            ),
        )
        connection.execute(
            """
            DELETE FROM financial_report_values
            WHERE code=? AND report_date=? AND announce_date=?
            """,
            (code, report_date, announce_date),
        )
        for raw_name, raw_value in row.items():
            field_name = str(raw_name).strip().upper()
            if not field_name or field_name.lower() in {
                "tag_time",
                "announce_time",
                "report_date",
                "announce_date",
            }:
                continue
            numeric_value, text_value = numeric_and_text(raw_value)
            connection.execute(
                """
                INSERT INTO financial_report_values VALUES(?,?,?,?,?,?)
                """,
                (
                    code,
                    report_date,
                    announce_date,
                    field_name,
                    numeric_value,
                    text_value,
                ),
            )
            connection.execute(
                """
                INSERT INTO field_dictionary VALUES(?,?,?,?,?)
                ON CONFLICT(dataset,field_name) DO UPDATE SET
                    display_name=excluded.display_name,
                    field_group=excluded.field_group,
                    value_type=excluded.value_type
                """,
                (
                    "financial_history",
                    field_name,
                    display_name(field_name),
                    group_name(field_name),
                    "number" if numeric_value is not None else "text",
                ),
            )
        count += 1
    return count


def upsert_share_capital_history(
    connection: sqlite3.Connection,
    code: str,
    rows: Iterable[dict[str, Any]],
    captured_at: str,
) -> int:
    """按生效日幂等保存流通股本和总股本。"""
    count = 0
    for row in rows:
        effective_date = date_text(row.get("Date") or row.get("date"))
        if not effective_date:
            continue
        float_shares, total_shares = numbers(row, ("Ltgb", "Zgb"))
        connection.execute(
            """
            INSERT INTO share_capital_history VALUES(?,?,?,?,?,?)
            ON CONFLICT(code,effective_date) DO UPDATE SET
                float_shares=excluded.float_shares,total_shares=excluded.total_shares,
                payload_json=excluded.payload_json,captured_at=excluded.captured_at
            """,
            (
                code,
                effective_date,
                float_shares,
                total_shares,
                json.dumps(row, ensure_ascii=False, default=str),
                captured_at,
            ),
        )
        count += 1
    return count


def upsert_corporate_actions(
    connection: sqlite3.Connection,
    code: str,
    rows: Iterable[dict[str, Any]],
    captured_at: str,
) -> int:
    """按行为日和稳定行键保存分红送配记录。"""
    count = 0
    for index, row in enumerate(rows):
        action_date = date_text(row.get("Date") or row.get("date"))
        if not action_date:
            continue
        record_key = f"{row.get('Type', '')}|{index:06d}"
        cash_dividend, bonus_shares, allotment_shares, allotment_price = numbers(
            row, ("Bonus", "ShareBonus", "Allotment", "AllotPrice")
        )
        connection.execute(
            """
            INSERT INTO corporate_actions(
                code,action_date,record_key,action_type,cash_dividend,
                bonus_shares,allotment_shares,allotment_price,payload_json,captured_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(code,action_date,record_key) DO UPDATE SET
                action_type=excluded.action_type,
                cash_dividend=excluded.cash_dividend,
                bonus_shares=excluded.bonus_shares,
                allotment_shares=excluded.allotment_shares,
                allotment_price=excluded.allotment_price,
                payload_json=excluded.payload_json,
                captured_at=excluded.captured_at
            """,
            (
                code,
                action_date,
                record_key,
                str(row.get("Type", "")) or None,
                cash_dividend,
                bonus_shares,
                allotment_shares,
                allotment_price,
                json.dumps(row, ensure_ascii=False, default=str),
                captured_at,
            ),
        )
        count += 1
    return count


def load_archived_assets(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    """读取当前有集合归属的归档标的，供每日任务复用。"""
    rows = connection.execute(
        """
        SELECT a.code, a.name, group_concat(g.group_name, char(31)) AS groups,
               MAX(g.liquidity_rank) AS liquidity_rank,
               MAX(g.latest_amount) AS latest_amount
        FROM assets AS a
        JOIN asset_groups AS g ON g.code=a.code
        GROUP BY a.code, a.name
        ORDER BY a.code
        """
    ).fetchall()
    return [
        {
            "Code": row["code"],
            "Name": row["name"],
            "Groups": str(row["groups"]).split(chr(31)),
            "LiquidityRank": row["liquidity_rank"],
            "LatestAmount": row["latest_amount"],
        }
        for row in rows
    ]


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


def numeric_and_text(value: Any) -> tuple[float | None, str | None]:
    """财务字段优先保存数值；不可转数值时保留原始文本。"""
    if value in (None, "", "--"):
        return None, None
    try:
        return float(value), None
    except (TypeError, ValueError):
        return None, str(value)
