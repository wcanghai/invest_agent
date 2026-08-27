"""量化价值研究库的 SQLite schema 与幂等读写。"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping

from quant_value.config import Instrument
from quant_value.fields import FINANCIAL_FIELDS


DEFAULT_DATABASE = Path("data/quant_value.sqlite3")
SCHEMA = """
PRAGMA foreign_keys=ON;
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS instruments (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    asset_type TEXT NOT NULL CHECK(asset_type IN ('stock','etf','index')),
    category TEXT NOT NULL,
    benchmark_code TEXT,
    benchmark_name TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS field_dictionary (
    field_code TEXT PRIMARY KEY,
    field_name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    unit TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS universe_memberships (
    code TEXT NOT NULL REFERENCES instruments(code),
    group_name TEXT NOT NULL,
    selected_date TEXT NOT NULL,
    liquidity_rank INTEGER,
    latest_amount REAL,
    PRIMARY KEY(code, group_name, selected_date)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS market_bars (
    code TEXT NOT NULL REFERENCES instruments(code),
    trade_date TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL,
    volume REAL, amount REAL, forward_factor REAL,
    payload_json TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    PRIMARY KEY(code, trade_date)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS financial_reports (
    code TEXT NOT NULL REFERENCES instruments(code),
    report_date TEXT NOT NULL,
    announce_date TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    PRIMARY KEY(code, report_date, announce_date)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS ix_qv_financial_announce
    ON financial_reports(code, announce_date, report_date);
CREATE TABLE IF NOT EXISTS financial_values (
    code TEXT NOT NULL,
    report_date TEXT NOT NULL,
    announce_date TEXT NOT NULL,
    field_code TEXT NOT NULL REFERENCES field_dictionary(field_code),
    numeric_value REAL,
    text_value TEXT,
    PRIMARY KEY(code, report_date, announce_date, field_code),
    FOREIGN KEY(code, report_date, announce_date)
      REFERENCES financial_reports(code, report_date, announce_date)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS share_capital (
    code TEXT NOT NULL REFERENCES instruments(code),
    effective_date TEXT NOT NULL,
    float_shares REAL,
    total_shares REAL,
    payload_json TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    PRIMARY KEY(code, effective_date)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS corporate_actions (
    code TEXT NOT NULL REFERENCES instruments(code),
    action_date TEXT NOT NULL,
    record_key TEXT NOT NULL,
    action_type TEXT,
    cash_dividend_per_10 REAL,
    bonus_shares_per_10 REAL,
    allotment_shares_per_10 REAL,
    allotment_price REAL,
    payload_json TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    PRIMARY KEY(code, action_date, record_key)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS daily_snapshots (
    code TEXT NOT NULL REFERENCES instruments(code),
    observed_date TEXT NOT NULL,
    stock_info_json TEXT NOT NULL,
    more_info_json TEXT NOT NULL,
    market_snapshot_json TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    PRIMARY KEY(code, observed_date)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS relations (
    code TEXT NOT NULL REFERENCES instruments(code),
    observed_date TEXT NOT NULL,
    relation_key TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    PRIMARY KEY(code, observed_date, relation_key)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS etf_snapshots (
    code TEXT NOT NULL REFERENCES instruments(code),
    observed_date TEXT NOT NULL,
    benchmark_code TEXT,
    price REAL,
    previous_close REAL,
    iopv REAL,
    units_10k REAL,
    fund_size_100m REAL,
    premium_discount REAL,
    payload_json TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    PRIMARY KEY(code, observed_date)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS factor_daily (
    code TEXT NOT NULL REFERENCES instruments(code),
    trade_date TEXT NOT NULL,
    name TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    category TEXT NOT NULL,
    benchmark_code TEXT,
    open REAL, high REAL, low REAL, close REAL,
    volume REAL, amount REAL,
    return_1d REAL, return_20d REAL, momentum_252d REAL,
    volatility_20d REAL, volatility_60d REAL, max_drawdown_252d REAL,
    amount_ma20 REAL,
    report_date TEXT, announce_date TEXT, report_age_days INTEGER,
    book_value_per_share REAL, ttm_profit_10k REAL, ttm_revenue_10k REAL,
    total_shares REAL, market_cap REAL,
    pb REAL, pe_ttm REAL, ps_ttm REAL, earnings_yield REAL,
    fcff_yield REAL, fcfe_yield REAL, dividend_yield REAL,
    roe REAL, roic REAL, gross_margin REAL, operating_margin REAL,
    net_margin REAL, cash_conversion REAL, asset_turnover REAL,
    debt_to_assets REAL, interest_bearing_debt_ratio REAL,
    current_ratio REAL, quick_ratio REAL, interest_coverage REAL,
    revenue_growth REAL, net_profit_growth REAL, equity_growth REAL,
    audit_opinion REAL, dividend_payout_ratio REAL,
    etf_iopv REAL, etf_premium_discount REAL,
    benchmark_return_20d REAL, tracking_difference_20d REAL,
    tracking_error_60d REAL,
    factor_flags TEXT NOT NULL,
    built_at TEXT NOT NULL,
    PRIMARY KEY(code, trade_date)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    requested_codes INTEGER NOT NULL DEFAULT 0,
    bar_rows INTEGER NOT NULL DEFAULT 0,
    financial_rows INTEGER NOT NULL DEFAULT 0,
    failed_codes INTEGER NOT NULL DEFAULT 0,
    errors_json TEXT NOT NULL DEFAULT '{}'
);
"""


def open_database(path: Path = DEFAULT_DATABASE) -> sqlite3.Connection:
    """打开并初始化独立研究数据库。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    connection.executemany(
        """INSERT INTO field_dictionary VALUES (?,?,?,?)
        ON CONFLICT(field_code) DO UPDATE SET field_name=excluded.field_name,
        display_name=excluded.display_name,unit=excluded.unit""",
        [(f.code, f.name, f.display_name, f.unit) for f in FINANCIAL_FIELDS],
    )
    connection.commit()
    return connection


def upsert_instruments(
    connection: sqlite3.Connection, instruments: Iterable[Instrument], captured_at: str
) -> None:
    rows: list[tuple[Any, ...]] = []
    for item in instruments:
        rows.append((item.code, item.name, item.asset_type, item.category,
                     item.benchmark_code, item.benchmark_name, captured_at))
        if item.benchmark_code:
            rows.append((item.benchmark_code, item.benchmark_name or item.benchmark_code,
                         "index", "ETF基准", None, None, captured_at))
    connection.executemany(
        """INSERT INTO instruments VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(code) DO UPDATE SET name=excluded.name, asset_type=excluded.asset_type,
        category=excluded.category, benchmark_code=excluded.benchmark_code,
        benchmark_name=excluded.benchmark_name, updated_at=excluded.updated_at""",
        {row[0]: row for row in rows}.values(),
    )


def load_instruments(
    connection: sqlite3.Connection, codes: Iterable[str] | None = None
) -> list[Instrument]:
    """从研究库读取股票/ETF 标的，供每日增量与失败补采复用。"""
    requested = [code.upper() for code in codes or []]
    if requested:
        placeholders = ",".join("?" for _ in requested)
        rows = connection.execute(
            f"""SELECT code,name,asset_type,category,benchmark_code,benchmark_name
            FROM instruments WHERE asset_type IN ('stock','etf')
            AND UPPER(code) IN ({placeholders}) ORDER BY code""",
            requested,
        ).fetchall()
    else:
        rows = connection.execute(
            """SELECT code,name,asset_type,category,benchmark_code,benchmark_name
            FROM instruments WHERE asset_type IN ('stock','etf') ORDER BY code"""
        ).fetchall()
    if requested and len(rows) != len(set(requested)):
        found = {str(row["code"]).upper() for row in rows}
        raise ValueError(f"数据库中不存在代码：{', '.join(sorted(set(requested) - found))}")
    return [
        Instrument(
            code=str(row["code"]), name=str(row["name"]),
            asset_type=str(row["asset_type"]), category=str(row["category"]),
            benchmark_code=row["benchmark_code"], benchmark_name=row["benchmark_name"],
        )
        for row in rows
    ]


def upsert_memberships(connection: sqlite3.Connection, memberships: Iterable[Any]) -> None:
    """保存动态目标池入选证据；接收包含同名属性的不可变记录。"""
    connection.executemany(
        """INSERT INTO universe_memberships VALUES (?,?,?,?,?)
        ON CONFLICT(code,group_name,selected_date) DO UPDATE SET
        liquidity_rank=excluded.liquidity_rank,latest_amount=excluded.latest_amount""",
        [
            (item.code, item.group_name, item.selected_date.isoformat(),
             item.liquidity_rank, item.latest_amount)
            for item in memberships
        ],
    )


def upsert_bars(
    connection: sqlite3.Connection, code: str, rows: Iterable[Mapping[str, Any]], captured_at: str
) -> int:
    values = []
    for row in rows:
        trade_date = iso_date(_pick(row, "Date", "date", "trade_date"))
        if not trade_date:
            continue
        values.append((code, trade_date, number(_pick(row, "Open", "open")),
                       number(_pick(row, "High", "high")), number(_pick(row, "Low", "low")),
                       number(_pick(row, "Close", "close")), number(_pick(row, "Volume", "volume")),
                       number(_pick(row, "Amount", "amount")),
                       number(_pick(row, "ForwardFactor", "forward_factor")),
                       json_text(row), captured_at))
    connection.executemany(
        """INSERT INTO market_bars VALUES (?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(code,trade_date) DO UPDATE SET open=excluded.open,high=excluded.high,
        low=excluded.low,close=excluded.close,volume=excluded.volume,amount=excluded.amount,
        forward_factor=excluded.forward_factor,payload_json=excluded.payload_json,
        captured_at=excluded.captured_at""", values)
    return len(values)


def upsert_financial_reports(
    connection: sqlite3.Connection, code: str, rows: Iterable[Mapping[str, Any]], captured_at: str
) -> int:
    count = 0
    for row in rows:
        report_date = iso_date(_pick(row, "tag_time", "report_date"))
        announce_date = iso_date(_pick(row, "announce_time", "announce_date"))
        if not report_date or not announce_date:
            continue
        connection.execute(
            """INSERT INTO financial_reports VALUES (?,?,?,?,?)
            ON CONFLICT(code,report_date,announce_date) DO UPDATE SET
            payload_json=excluded.payload_json,captured_at=excluded.captured_at""",
            (code, report_date, announce_date, json_text(row), captured_at),
        )
        for field in FINANCIAL_FIELDS:
            value = _pick(row, field.code, field.code.lower())
            if value is None:
                continue
            numeric = number(value)
            connection.execute(
                """INSERT INTO financial_values VALUES (?,?,?,?,?,?)
                ON CONFLICT(code,report_date,announce_date,field_code) DO UPDATE SET
                numeric_value=excluded.numeric_value,text_value=excluded.text_value""",
                (code, report_date, announce_date, field.code, numeric,
                 None if numeric is not None else str(value)),
            )
        count += 1
    return count


def upsert_share_capital(
    connection: sqlite3.Connection, code: str, rows: Iterable[Mapping[str, Any]], captured_at: str
) -> int:
    values = []
    for row in rows:
        effective = iso_date(_pick(row, "Date", "date", "EffectiveDate"))
        if effective:
            values.append((code, effective, number(_pick(row, "Ltgb", "Ltg", "FloatShares")),
                           number(_pick(row, "Zgb", "TotalShares")), json_text(row), captured_at))
    connection.executemany(
        """INSERT INTO share_capital VALUES (?,?,?,?,?,?)
        ON CONFLICT(code,effective_date) DO UPDATE SET float_shares=excluded.float_shares,
        total_shares=excluded.total_shares,payload_json=excluded.payload_json,
        captured_at=excluded.captured_at""", values)
    return len(values)


def upsert_actions(
    connection: sqlite3.Connection, code: str, rows: Iterable[Mapping[str, Any]], captured_at: str
) -> int:
    values = []
    for row in rows:
        action_date = iso_date(_pick(row, "Date", "date"))
        if not action_date:
            continue
        action_type = str(_pick(row, "Type", "type") or "")
        payload = json_text(row)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        record_key = f"{action_type}:{digest}"
        # 兼容旧版包含响应序号的键：同一事件在不同查询窗口中的位置会变化，
        # 先清除内容完全相同的旧键，避免重复累计现金分红。
        connection.execute(
            "DELETE FROM corporate_actions "
            "WHERE code=? AND action_date=? AND payload_json=? AND record_key<>?",
            (code, action_date, payload, record_key),
        )
        values.append((code, action_date, record_key, action_type,
                       number(_pick(row, "Bonus", "cash_dividend")),
                       number(_pick(row, "ShareBonus", "bonus_shares")),
                       number(_pick(row, "Allotment", "allotment_shares")),
                       number(_pick(row, "AllotPrice", "allotment_price")),
                       payload, captured_at))
    connection.executemany(
        """INSERT INTO corporate_actions VALUES (?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(code,action_date,record_key) DO UPDATE SET
        payload_json=excluded.payload_json,captured_at=excluded.captured_at""", values)
    return len(values)


def upsert_snapshot(
    connection: sqlite3.Connection, code: str, observed_date: date,
    stock_info: Mapping[str, Any], more_info: Mapping[str, Any],
    market_snapshot: Mapping[str, Any], captured_at: str,
) -> None:
    connection.execute(
        """INSERT INTO daily_snapshots VALUES (?,?,?,?,?,?)
        ON CONFLICT(code,observed_date) DO UPDATE SET stock_info_json=excluded.stock_info_json,
        more_info_json=excluded.more_info_json,market_snapshot_json=excluded.market_snapshot_json,
        captured_at=excluded.captured_at""",
        (code, observed_date.isoformat(), json_text(stock_info), json_text(more_info),
         json_text(market_snapshot), captured_at),
    )


def upsert_relations(
    connection: sqlite3.Connection, code: str, observed_date: date,
    rows: Iterable[Mapping[str, Any]], captured_at: str,
) -> int:
    values = []
    for position, row in enumerate(rows):
        key = str(_pick(row, "BlockCode", "Code") or f"row-{position}")
        key = f"{_pick(row, 'BlockType', 'Type') or ''}:{key}"
        values.append((code, observed_date.isoformat(), key, json_text(row), captured_at))
    connection.executemany(
        """INSERT INTO relations VALUES (?,?,?,?,?)
        ON CONFLICT(code,observed_date,relation_key) DO UPDATE SET
        payload_json=excluded.payload_json,captured_at=excluded.captured_at""", values)
    return len(values)


def upsert_etf_snapshot(
    connection: sqlite3.Connection, code: str, observed_date: date,
    benchmark_code: str | None, row: Mapping[str, Any], captured_at: str,
) -> None:
    price = number(_pick(row, "NowPrice", "Now", "price"))
    iopv = number(_pick(row, "IOPV", "iopv"))
    premium = (price / iopv - 1) if price is not None and iopv and iopv > 0 else None
    connection.execute(
        """INSERT INTO etf_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(code,observed_date) DO UPDATE SET benchmark_code=excluded.benchmark_code,
        price=excluded.price,previous_close=excluded.previous_close,iopv=excluded.iopv,
        units_10k=excluded.units_10k,fund_size_100m=excluded.fund_size_100m,
        premium_discount=excluded.premium_discount,payload_json=excluded.payload_json,
        captured_at=excluded.captured_at""",
        (code, observed_date.isoformat(), benchmark_code, price,
         number(_pick(row, "PreClose", "previous_close")), iopv,
         number(_pick(row, "Zgb", "units_10k")), number(_pick(row, "Sz", "fund_size_100m")),
         premium, json_text(row), captured_at),
    )


def latest_bar_date(connection: sqlite3.Connection, code: str) -> date | None:
    row = connection.execute("SELECT MAX(trade_date) FROM market_bars WHERE code=?", (code,)).fetchone()
    return date.fromisoformat(row[0]) if row and row[0] else None


def latest_financial_announce_date(
    connection: sqlite3.Connection, code: str
) -> date | None:
    return _latest_date(connection, "financial_reports", "announce_date", code)


def latest_share_capital_date(connection: sqlite3.Connection, code: str) -> date | None:
    return _latest_date(connection, "share_capital", "effective_date", code)


def latest_action_date(connection: sqlite3.Connection, code: str) -> date | None:
    return _latest_date(connection, "corporate_actions", "action_date", code)


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, allow_nan=False)


def number(value: Any) -> float | None:
    if value in (None, "", "--", "None"):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def iso_date(value: Any) -> str | None:
    if value is None or value == "":
        return None
    text = str(value).split("T", maxsplit=1)[0].replace("-", "").replace("/", "")
    text = text.split(".", maxsplit=1)[0]
    if len(text) >= 8 and text[:8].isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return None


def _pick(row: Mapping[str, Any], *names: str) -> Any:
    lower = {str(key).lower(): value for key, value in row.items()}
    for name in names:
        if name.lower() in lower:
            return lower[name.lower()]
    return None


def _latest_date(
    connection: sqlite3.Connection, table: str, column: str, code: str
) -> date | None:
    allowed = {
        ("financial_reports", "announce_date"),
        ("share_capital", "effective_date"),
        ("corporate_actions", "action_date"),
    }
    if (table, column) not in allowed:
        raise ValueError("不允许的日期查询")
    row = connection.execute(
        f"SELECT MAX({column}) FROM {table} WHERE code=?", (code,)
    ).fetchone()
    return date.fromisoformat(row[0]) if row and row[0] else None
