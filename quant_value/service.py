"""全量与每日增量采集编排。"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Callable, Iterable

from quant_value.config import Instrument
from quant_value.gateway import ResearchGateway
from quant_value.repository import (
    latest_action_date,
    latest_bar_date,
    latest_financial_announce_date,
    latest_share_capital_date,
    upsert_actions,
    upsert_bars,
    upsert_etf_snapshot,
    upsert_financial_reports,
    upsert_instruments,
    upsert_relations,
    upsert_share_capital,
    upsert_snapshot,
)


@dataclass(frozen=True)
class SyncResult:
    run_id: int
    status: str
    bar_rows: int
    financial_rows: int
    errors: dict[str, str]


def sync_research_data(
    connection: sqlite3.Connection,
    gateway: ResearchGateway,
    instruments: Iterable[Instrument],
    start: date,
    end: date,
    *,
    incremental: bool = True,
    overlap_days: int = 7,
    progress: Callable[[int, int, str, str | None], None] | None = None,
) -> SyncResult:
    """采集研究数据；每个代码独立事务，失败不会回滚其他代码。"""
    if start > end:
        raise ValueError("start 不能晚于 end")
    selected = list(instruments)
    now = datetime.now(UTC).isoformat()
    upsert_instruments(connection, selected, now)
    run_id = connection.execute(
        "INSERT INTO sync_runs(operation,started_at,status,requested_codes) VALUES (?,?,?,?)",
        ("incremental" if incremental else "full", now, "running", len(selected)),
    ).lastrowid
    connection.commit()

    bar_rows = financial_rows = 0
    errors: dict[str, str] = {}
    benchmark_codes = {
        item.benchmark_code for item in selected if item.benchmark_code
    }
    gateway.connect()
    try:
        for position, item in enumerate(selected, 1):
            item_start = _effective_start(connection, item.code, start, incremental, overlap_days)
            try:
                bars = gateway.market_bars(item.code, item_start, end)
                bar_rows += upsert_bars(connection, item.code, bars, now)
                stock_info, more_info, market_snapshot = gateway.snapshot(item.code)
                upsert_snapshot(connection, item.code, end, stock_info, more_info, market_snapshot, now)
                action_start = _history_start(
                    latest_action_date(connection, item.code), start, incremental, overlap_days
                )
                actions = gateway.corporate_actions(item.code, action_start, end)
                upsert_actions(connection, item.code, actions, now)

                if item.asset_type == "stock":
                    financial_start = _history_start(
                        latest_financial_announce_date(connection, item.code),
                        start, incremental, overlap_days,
                    )
                    reports = gateway.financial_reports(item.code, financial_start, end)
                    financial_rows += upsert_financial_reports(connection, item.code, reports, now)
                    capital_start = _history_start(
                        latest_share_capital_date(connection, item.code),
                        start, incremental, overlap_days,
                    )
                    upsert_share_capital(
                        connection, item.code,
                        gateway.share_capital(item.code, capital_start, end), now,
                    )
                    upsert_relations(connection, item.code, end, gateway.relations(item.code), now)
                else:
                    etf_row = _etf_row(gateway, item, more_info, market_snapshot)
                    upsert_etf_snapshot(
                        connection, item.code, end, item.benchmark_code, etf_row, now
                    )
                connection.commit()
            except Exception as exc:  # 单标的容错是采集服务的契约
                connection.rollback()
                errors[item.code] = f"{type(exc).__name__}: {exc}"
            if progress is not None:
                progress(position, len(selected), item.code, errors.get(item.code))

        for benchmark_code in sorted(code for code in benchmark_codes if code):
            benchmark_start = _effective_start(
                connection, benchmark_code, start, incremental, overlap_days
            )
            try:
                bar_rows += upsert_bars(
                    connection, benchmark_code,
                    gateway.market_bars(benchmark_code, benchmark_start, end), now,
                )
                connection.commit()
            except Exception as exc:
                connection.rollback()
                errors[benchmark_code] = f"{type(exc).__name__}: {exc}"
    finally:
        gateway.close()

    status = "success" if not errors else ("failed" if len(errors) >= len(selected) else "partial_failure")
    finished = datetime.now(UTC).isoformat()
    connection.execute(
        """UPDATE sync_runs SET finished_at=?,status=?,bar_rows=?,financial_rows=?,
        failed_codes=?,errors_json=? WHERE id=?""",
        (finished, status, bar_rows, financial_rows, len(errors),
         json.dumps(errors, ensure_ascii=False, sort_keys=True), run_id),
    )
    connection.commit()
    return SyncResult(int(run_id), status, bar_rows, financial_rows, errors)


def _effective_start(
    connection: sqlite3.Connection, code: str, requested: date,
    incremental: bool, overlap_days: int,
) -> date:
    latest = latest_bar_date(connection, code) if incremental else None
    if latest is None:
        return requested
    return max(requested, latest - timedelta(days=max(0, overlap_days)))


def _history_start(
    latest: date | None, requested: date, incremental: bool, overlap_days: int
) -> date:
    if not incremental or latest is None:
        return requested
    return max(requested, latest - timedelta(days=max(0, overlap_days)))


def _etf_row(
    gateway: ResearchGateway,
    instrument: Instrument,
    more_info: dict[str, object],
    market_snapshot: dict[str, object],
) -> dict[str, object]:
    if instrument.benchmark_code:
        rows = gateway.etfs_for_benchmark(instrument.benchmark_code)
        for row in rows:
            if str(row.get("Code", "")).upper() == instrument.code.upper():
                return row
    merged = dict(market_snapshot)
    merged.update(more_info)
    # 某些 ETF 基准接口不可用；保留动态行情中的净值/折溢价相关原始字段。
    return merged
