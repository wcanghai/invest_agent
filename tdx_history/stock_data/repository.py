"""股票全维度 SQLite 仓储实现。"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from tdx_history.repository import HistoryRepository, _nullable_float


class StockDataRepository(HistoryRepository):
    """在日线 schema 上增加股票公司、财务、关系和快照数据。"""

    def __init__(self, path: Path):
        super().__init__(path)
        self._create_stock_schema()

    def _create_stock_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS stock_sample_tags (
                code TEXT PRIMARY KEY REFERENCES instruments(code),
                sample_type TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS corporate_actions (
                code TEXT NOT NULL REFERENCES instruments(code),
                event_date TEXT NOT NULL,
                event_type TEXT NOT NULL,
                bonus REAL,
                allot_price REAL,
                share_bonus REAL,
                allotment REAL,
                payload_json TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                PRIMARY KEY (code, event_date, event_type, payload_json)
            ) WITHOUT ROWID;

            CREATE TABLE IF NOT EXISTS share_capital (
                code TEXT NOT NULL REFERENCES instruments(code),
                effective_date TEXT NOT NULL,
                circulating_shares REAL,
                total_shares REAL,
                payload_json TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                PRIMARY KEY (code, effective_date)
            ) WITHOUT ROWID;

            CREATE TABLE IF NOT EXISTS financial_facts (
                code TEXT NOT NULL REFERENCES instruments(code),
                report_basis TEXT NOT NULL,
                fact_date TEXT NOT NULL,
                field_code TEXT NOT NULL,
                value_json TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                PRIMARY KEY (code, report_basis, fact_date, field_code)
            ) WITHOUT ROWID;

            CREATE TABLE IF NOT EXISTS stock_relations (
                code TEXT NOT NULL REFERENCES instruments(code),
                observed_date TEXT NOT NULL,
                relation_key TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                PRIMARY KEY (code, observed_date, relation_key)
            ) WITHOUT ROWID;

            CREATE TABLE IF NOT EXISTS stock_dataset_records (
                code TEXT NOT NULL REFERENCES instruments(code),
                dataset TEXT NOT NULL,
                observed_date TEXT NOT NULL,
                record_key TEXT NOT NULL,
                record_date TEXT,
                payload_json TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                PRIMARY KEY (code, dataset, observed_date, record_key)
            ) WITHOUT ROWID;

            CREATE INDEX IF NOT EXISTS idx_stock_dataset_records_dataset
                ON stock_dataset_records(dataset, observed_date);

            CREATE TABLE IF NOT EXISTS stock_dataset_fields (
                dataset TEXT NOT NULL,
                field_name TEXT NOT NULL,
                value_type TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                PRIMARY KEY (dataset, field_name)
            ) WITHOUT ROWID;

            CREATE TABLE IF NOT EXISTS stock_collection_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                requested_codes INTEGER NOT NULL,
                status TEXT NOT NULL,
                message TEXT
            );

            CREATE TABLE IF NOT EXISTS stock_collection_results (
                run_id INTEGER NOT NULL REFERENCES stock_collection_runs(id),
                code TEXT NOT NULL,
                dataset TEXT NOT NULL,
                status TEXT NOT NULL,
                record_count INTEGER NOT NULL,
                field_count INTEGER NOT NULL,
                message TEXT,
                PRIMARY KEY (run_id, code, dataset)
            ) WITHOUT ROWID;
            """
        )
        self.connection.commit()

    def upsert_sample_tag(self, code: str, sample_type: str) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO stock_sample_tags(code, sample_type) VALUES (?, ?)
                ON CONFLICT(code) DO UPDATE SET sample_type=excluded.sample_type
                """,
                (code, sample_type),
            )

    def insert_corporate_actions(self, code: str, records: Iterable[dict[str, Any]]) -> int:
        now = self._utc_now()
        rows = []
        for record in records:
            event_date = _date_text(_get(record, "Date", "date"))
            if not event_date:
                continue
            payload = _json(record)
            rows.append(
                (
                    code,
                    event_date,
                    str(_get(record, "Type", "type") or "unknown"),
                    _nullable_number(_get(record, "Bonus")),
                    _nullable_number(_get(record, "AllotPrice")),
                    _nullable_number(_get(record, "ShareBonus")),
                    _nullable_number(_get(record, "Allotment")),
                    payload,
                    now,
                )
            )
        return self._insert_ignore(
            """
            INSERT OR IGNORE INTO corporate_actions(
                code,event_date,event_type,bonus,allot_price,share_bonus,allotment,payload_json,observed_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            rows,
        )

    def upsert_share_capital(self, code: str, records: Iterable[dict[str, Any]]) -> int:
        now = self._utc_now()
        rows = []
        for record in records:
            effective_date = _date_text(_get(record, "Date", "date"))
            if not effective_date:
                continue
            rows.append(
                (
                    code,
                    effective_date,
                    _nullable_number(_get(record, "Ltgb")),
                    _nullable_number(_get(record, "Zgb")),
                    _json(record),
                    now,
                )
            )
        before = self.connection.total_changes
        with self.connection:
            self.connection.executemany(
                """
                INSERT INTO share_capital(
                    code,effective_date,circulating_shares,total_shares,payload_json,observed_at
                ) VALUES (?,?,?,?,?,?)
                ON CONFLICT(code,effective_date) DO UPDATE SET
                    circulating_shares=excluded.circulating_shares,
                    total_shares=excluded.total_shares,
                    payload_json=excluded.payload_json,
                    observed_at=excluded.observed_at
                """,
                rows,
            )
        return self.connection.total_changes - before

    def upsert_financial_facts(
        self, code: str, report_basis: str, records: Iterable[dict[str, Any]]
    ) -> int:
        now = self._utc_now()
        rows = []
        for index, record in enumerate(records):
            fact_date = _record_date(record) or f"row-{index:06d}"
            for field, value in record.items():
                if str(field).lower() in {"date", "_index", "reportdate", "announcedate"}:
                    continue
                rows.append((code, report_basis, fact_date, str(field), _json(value), now))
        before = self.connection.total_changes
        with self.connection:
            self.connection.executemany(
                """
                INSERT INTO financial_facts(
                    code,report_basis,fact_date,field_code,value_json,observed_at
                ) VALUES (?,?,?,?,?,?)
                ON CONFLICT(code,report_basis,fact_date,field_code) DO UPDATE SET
                    value_json=excluded.value_json,
                    observed_at=excluded.observed_at
                """,
                rows,
            )
        return self.connection.total_changes - before

    def replace_relations(
        self, code: str, observed_date: date, records: Iterable[dict[str, Any]]
    ) -> int:
        values = list(records)
        day = observed_date.isoformat()
        now = self._utc_now()
        rows = []
        seen: set[str] = set()
        for index, record in enumerate(values):
            relation_key = _hash_key(record, index)
            if relation_key in seen:
                continue
            seen.add(relation_key)
            rows.append((code, day, relation_key, _json(record), now))
        with self.connection:
            self.connection.execute(
                "DELETE FROM stock_relations WHERE code=? AND observed_date=?", (code, day)
            )
            self.connection.executemany(
                """
                INSERT INTO stock_relations(code,observed_date,relation_key,payload_json,observed_at)
                VALUES (?,?,?,?,?)
                """,
                rows,
            )
        return len(rows)

    def upsert_dataset_records(
        self,
        code: str,
        dataset: str,
        observed_date: date,
        records: Iterable[dict[str, Any]],
    ) -> int:
        values = list(records)
        day = observed_date.isoformat()
        now = self._utc_now()
        rows = []
        for index, record in enumerate(values):
            record_date = _record_date(record)
            record_key = record_date or ("snapshot" if len(values) == 1 else _hash_key(record, index))
            payload = _json(record)
            rows.append((code, dataset, day, record_key, record_date, payload, now))
            self._upsert_field_catalog(dataset, record, now)
        before = self.connection.total_changes
        with self.connection:
            self.connection.execute(
                "DELETE FROM stock_dataset_records WHERE code=? AND dataset=? AND observed_date=?",
                (code, dataset, day),
            )
            self.connection.executemany(
                """
                INSERT INTO stock_dataset_records(
                    code,dataset,observed_date,record_key,record_date,payload_json,observed_at
                ) VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(code,dataset,observed_date,record_key) DO UPDATE SET
                    record_date=excluded.record_date,
                    payload_json=excluded.payload_json,
                    observed_at=excluded.observed_at
                """,
                rows,
            )
        return self.connection.total_changes - before

    def start_collection_run(self, requested_codes: int) -> int:
        with self.connection:
            cursor = self.connection.execute(
                """
                INSERT INTO stock_collection_runs(started_at,requested_codes,status)
                VALUES (?,?,'running')
                """,
                (self._utc_now(), requested_codes),
            )
        return int(cursor.lastrowid)

    def add_collection_result(
        self,
        run_id: int,
        code: str,
        dataset: str,
        status: str,
        record_count: int,
        field_count: int,
        message: str = "",
    ) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO stock_collection_results(
                    run_id,code,dataset,status,record_count,field_count,message
                ) VALUES (?,?,?,?,?,?,?)
                """,
                (run_id, code, dataset, status, record_count, field_count, message),
            )

    def finish_collection_run(self, run_id: int, failed: int, message: str) -> None:
        with self.connection:
            self.connection.execute(
                """
                UPDATE stock_collection_runs
                SET finished_at=?,status=?,message=? WHERE id=?
                """,
                (self._utc_now(), "success" if failed == 0 else "partial_failure", message, run_id),
            )

    def fields_for_dataset(self, dataset: str) -> tuple[str, ...]:
        rows = self.connection.execute(
            "SELECT field_name FROM stock_dataset_fields WHERE dataset=? ORDER BY field_name",
            (dataset,),
        ).fetchall()
        return tuple(str(row["field_name"]) for row in rows)

    def _upsert_field_catalog(self, dataset: str, record: dict[str, Any], now: str) -> None:
        rows = [(dataset, str(key), _value_type(value), now, now) for key, value in record.items()]
        with self.connection:
            self.connection.executemany(
                """
                INSERT INTO stock_dataset_fields(
                    dataset,field_name,value_type,first_seen_at,last_seen_at
                ) VALUES (?,?,?,?,?)
                ON CONFLICT(dataset,field_name) DO UPDATE SET
                    value_type=excluded.value_type,last_seen_at=excluded.last_seen_at
                """,
                rows,
            )

    def _insert_ignore(self, sql: str, rows: list[tuple[Any, ...]]) -> int:
        before = self.connection.total_changes
        with self.connection:
            self.connection.executemany(sql, rows)
        return self.connection.total_changes - before


def _get(record: dict[str, Any], *names: str) -> Any:
    lowered = {str(key).lower(): value for key, value in record.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def _record_date(record: dict[str, Any]) -> str | None:
    return _date_text(_get(record, "Date", "ReportDate", "AnnounceDate", "_index"))


def _date_text(value: Any) -> str | None:
    if value is None or str(value).strip() in {"", "--", "None", "NaT"}:
        return None
    text = str(value).strip().replace("/", "-")
    if len(text) >= 10 and text[4] == "-":
        return text[:10]
    digits = "".join(character for character in text if character.isdigit())
    if len(digits) >= 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return text


def _nullable_number(value: Any) -> float | None:
    try:
        return _nullable_float(value)
    except (TypeError, ValueError):
        return None


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash_key(record: dict[str, Any], index: int) -> str:
    digest = hashlib.sha256(_json(record).encode("utf-8")).hexdigest()[:20]
    return f"{index:06d}-{digest}"


def _value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "text"
