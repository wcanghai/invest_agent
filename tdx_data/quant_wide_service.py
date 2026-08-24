"""把 TDX 归档数据物化为时点一致的日频量化宽表。"""

from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Sequence


FINANCIAL_FIELDS = tuple(f"FN{number}" for number in range(193, 201))

WIDE_COLUMNS = (
    "code", "trade_date", "name", "market", "asset_type",
    "open", "high", "low", "close", "volume", "amount",
    "forward_factor", "vol_in_stock", "prev_close", "return_1d",
    "return_5d", "return_20d", "log_return_1d", "intraday_return",
    "amplitude", "close_ma5", "close_ma20", "volume_ma20", "amount_ma20",
    "report_date", "announce_date", "report_age_days",
    "fn193", "fn194", "fn195", "fn196", "fn197", "fn198", "fn199", "fn200",
    "share_capital_date", "float_shares", "total_shares", "market_cap",
    "float_market_cap", "action_count", "action_types", "cash_dividend",
    "bonus_shares", "allotment_shares", "allotment_price", "days_since_action",
    "snapshot_date", "snapshot_hq_date", "snapshot_dynamic_pe",
    "snapshot_static_pe_ttm", "snapshot_pb_mrq", "snapshot_dividend_yield",
    "snapshot_turnover_rate", "snapshot_beta", "snapshot_total_market_cap",
    "snapshot_float_market_cap", "snapshot_total_assets",
    "snapshot_current_assets", "snapshot_current_liabilities",
    "snapshot_long_term_liabilities", "snapshot_equity", "snapshot_revenue",
    "snapshot_operating_profit", "snapshot_net_profit",
    "snapshot_operating_cash_flow", "snapshot_inventory", "snapshot_receivables",
    "snapshot_eps", "snapshot_bps", "snapshot_shareholders",
    "snapshot_industry_code", "snapshot_industry_name",
    "snapshot_tdx_industry_code", "snapshot_tdx_industry_name",
    "snapshot_is_st", "snapshot_hs300_member", "snapshot_margin_eligible",
    "snapshot_hk_connect",
    "recent_notice_date", "recent_repurchase_date", "recent_insider_trade_date",
    "recent_incentive_date", "recent_unlock_date", "recent_block_trade_date",
    "recent_halt_date", "built_at",
)

MORE_INFO_COLUMNS = {
    "snapshot_hq_date": "f_HqDate",
    "snapshot_dynamic_pe": "f_DynaPE",
    "snapshot_static_pe_ttm": "f_StaticPE_TTM",
    "snapshot_pb_mrq": "f_PB_MRQ",
    "snapshot_dividend_yield": "f_DYRatio",
    "snapshot_turnover_rate": "f_fHSL",
    "snapshot_beta": "f_BetaValue",
    "snapshot_total_market_cap": "f_Zsz",
    "snapshot_float_market_cap": "f_Ltsz",
    "recent_notice_date": "f_NoticeDate_Recent",
    "recent_repurchase_date": "f_RecentHGDate",
    "recent_insider_trade_date": "f_RecentGGJYDate",
    "recent_incentive_date": "f_RecentIncentDate",
    "recent_unlock_date": "f_RecentReleaseDate",
    "recent_block_trade_date": "f_RecentDZDate",
    "recent_halt_date": "f_StopJYDate_Recent",
}

STOCK_INFO_COLUMNS = {
    "snapshot_total_assets": "f_J_zzc",
    "snapshot_current_assets": "f_J_ldzc",
    "snapshot_current_liabilities": "f_J_ldfz",
    "snapshot_long_term_liabilities": "f_J_cqfz",
    "snapshot_equity": "f_J_jzc",
    "snapshot_revenue": "f_J_yysy",
    "snapshot_operating_profit": "f_J_yyly",
    "snapshot_net_profit": "f_J_jly",
    "snapshot_operating_cash_flow": "f_J_jyxjl",
    "snapshot_inventory": "f_J_ch",
    "snapshot_receivables": "f_J_yszk",
    "snapshot_eps": "f_J_mgsy",
    "snapshot_bps": "f_J_mgjzc",
    "snapshot_shareholders": "f_J_gdrs",
    "snapshot_industry_code": "f_rs_hycode_sim",
    "snapshot_industry_name": "f_rs_hyname",
    "snapshot_tdx_industry_code": "f_tdx_dycode",
    "snapshot_tdx_industry_name": "f_tdx_dyname",
    "snapshot_is_st": "f_IsSTGP",
    "snapshot_hs300_member": "f_BelongHS300",
    "snapshot_margin_eligible": "f_BelongRZRQ",
    "snapshot_hk_connect": "f_BelongHSGT",
}

TEXT_SNAPSHOT_FIELDS = {
    "snapshot_hq_date",
    "snapshot_industry_code",
    "snapshot_industry_name",
    "snapshot_tdx_industry_code",
    "snapshot_tdx_industry_name",
    "recent_notice_date",
    "recent_repurchase_date",
    "recent_insider_trade_date",
    "recent_incentive_date",
    "recent_unlock_date",
    "recent_block_trade_date",
    "recent_halt_date",
}
NUMERIC_SNAPSHOT_FIELDS = set((*MORE_INFO_COLUMNS, *STOCK_INFO_COLUMNS)) - TEXT_SNAPSHOT_FIELDS


@dataclass(frozen=True)
class QuantWideBuildResult:
    """一次宽表构建结果。"""

    requested_codes: int
    written_rows: int
    failed_codes: tuple[str, ...]
    run_id: int


ProgressCallback = Callable[[int, int, str, int, bool], None]


def build_quant_daily_wide(
    connection: sqlite3.Connection,
    codes: Sequence[str],
    start: date | None = None,
    end: date | None = None,
    *,
    rebuild: bool = False,
    progress: ProgressCallback | None = None,
) -> QuantWideBuildResult:
    """按标的物化日频宽表；各类特征都只使用交易日当时可知的数据。"""
    if start is not None and end is not None and start > end:
        raise ValueError("start 不能晚于 end")
    normalized_codes = tuple(dict.fromkeys(code.strip().upper() for code in codes if code.strip()))
    started_at = _utc_now()
    cursor = connection.execute(
        """
        INSERT INTO quant_wide_build_runs(started_at,requested_codes,status)
        VALUES(?,?,?)
        """,
        (started_at, len(normalized_codes), "running"),
    )
    run_id = int(cursor.lastrowid)
    connection.commit()

    written_rows = 0
    failures: list[str] = []
    for index, code in enumerate(normalized_codes, start=1):
        row_count = 0
        failed = False
        try:
            if rebuild:
                _delete_range(connection, code, start, end)
            rows = _build_code_rows(connection, code, start, end, started_at)
            _upsert_rows(connection, rows)
            connection.commit()
            row_count = len(rows)
            written_rows += row_count
        except Exception:  # noqa: BLE001 - 单标的失败必须隔离并继续其他标的
            connection.rollback()
            failures.append(code)
            failed = True
        if progress is not None:
            progress(index, len(normalized_codes), code, row_count, failed)

    finished_at = _utc_now()
    connection.execute(
        """
        UPDATE quant_wide_build_runs
        SET finished_at=?,written_rows=?,failed_codes=?,status=?,message=?
        WHERE id=?
        """,
        (
            finished_at,
            written_rows,
            len(failures),
            "success" if not failures else "partial_failure",
            "失败标的：" + (",".join(failures) if failures else "无"),
            run_id,
        ),
    )
    connection.commit()
    return QuantWideBuildResult(
        requested_codes=len(normalized_codes),
        written_rows=written_rows,
        failed_codes=tuple(failures),
        run_id=run_id,
    )


def _build_code_rows(
    connection: sqlite3.Connection,
    code: str,
    start: date | None,
    end: date | None,
    built_at: str,
) -> list[dict[str, Any]]:
    asset = connection.execute(
        """
        SELECT a.name,a.market,
               CASE WHEN EXISTS(
                   SELECT 1 FROM asset_groups g
                   WHERE g.code=a.code AND g.group_name LIKE '%ETF%'
               ) THEN 'ETF' ELSE 'stock' END AS asset_type
        FROM assets a WHERE a.code=?
        """,
        (code,),
    ).fetchone()
    if asset is None:
        raise ValueError(f"标的不存在：{code}")
    end_text = end.isoformat() if end else "9999-12-31"
    snapshot_end_text = (end + timedelta(days=7)).isoformat() if end else end_text
    start_text = start.isoformat() if start else "0001-01-01"
    bars = connection.execute(
        """
        SELECT trade_date,open,high,low,close,volume,amount,forward_factor,vol_in_stock
        FROM daily_bars WHERE code=? AND trade_date<=? ORDER BY trade_date
        """,
        (code, end_text),
    ).fetchall()
    reports = connection.execute(
        """
        SELECT report_date,announce_date FROM financial_reports
        WHERE code=? AND announce_date<=? ORDER BY announce_date,report_date
        """,
        (code, end_text),
    ).fetchall()
    report_values = _load_report_values(connection, code)
    capitals = connection.execute(
        """
        SELECT effective_date,float_shares,total_shares FROM share_capital_history
        WHERE code=? AND effective_date<=? ORDER BY effective_date
        """,
        (code, end_text),
    ).fetchall()
    actions = connection.execute(
        """
        SELECT action_date,action_type,cash_dividend,bonus_shares,
               allotment_shares,allotment_price
        FROM corporate_actions WHERE code=? AND action_date<=?
        ORDER BY action_date,record_key
        """,
        (code, end_text),
    ).fetchall()
    action_map = _aggregate_actions(actions)
    more_snapshots = _load_snapshots(
        connection,
        "more_info_flat",
        code,
        start_text,
        snapshot_end_text,
        MORE_INFO_COLUMNS,
        effective_date_field="snapshot_hq_date",
    )
    stock_snapshots = _load_snapshots(
        connection,
        "stock_info_flat",
        code,
        start_text,
        snapshot_end_text,
        STOCK_INFO_COLUMNS,
    )
    more_observed_dates = {
        str(snapshot["snapshot_date"])
        for snapshot in more_snapshots.values()
        if snapshot.get("snapshot_date")
    }

    report_index = capital_index = action_index = 0
    active_reports: dict[str, tuple[str, dict[str, float | str | None]]] = {}
    active_capital: sqlite3.Row | None = None
    action_dates = sorted(action_map)
    last_action_date: str | None = None
    closes: list[float] = []
    volumes: list[float | None] = []
    amounts: list[float | None] = []
    result: list[dict[str, Any]] = []

    for bar in bars:
        trade_date = str(bar["trade_date"])
        close = float(bar["close"])
        while report_index < len(reports) and str(reports[report_index]["announce_date"]) <= trade_date:
            report = reports[report_index]
            report_date = str(report["report_date"])
            if report_date <= trade_date:
                announce_date = str(report["announce_date"])
                active_reports[report_date] = (
                    announce_date,
                    report_values.get((report_date, announce_date), {}),
                )
            report_index += 1
        while capital_index < len(capitals) and str(capitals[capital_index]["effective_date"]) <= trade_date:
            active_capital = capitals[capital_index]
            capital_index += 1
        while action_index < len(action_dates) and action_dates[action_index] <= trade_date:
            last_action_date = action_dates[action_index]
            action_index += 1

        prev_close = closes[-1] if closes else None
        return_1d = _return(close, prev_close)
        return_5d = _return(close, closes[-5] if len(closes) >= 5 else None)
        return_20d = _return(close, closes[-20] if len(closes) >= 20 else None)
        closes.append(close)
        volumes.append(_optional_float(bar["volume"]))
        amounts.append(_optional_float(bar["amount"]))

        if trade_date < start_text:
            continue
        selected_report_date = max(active_reports) if active_reports else None
        selected_report = active_reports.get(selected_report_date) if selected_report_date else None
        financial_values = selected_report[1] if selected_report else {}
        action = action_map.get(trade_date, {})
        more_snapshot = more_snapshots.get(trade_date, {})
        snapshot_observed_date = more_snapshot.get("snapshot_date")
        if snapshot_observed_date:
            stock_snapshot = stock_snapshots.get(str(snapshot_observed_date), {})
        elif trade_date not in more_observed_dates:
            stock_snapshot = stock_snapshots.get(trade_date, {})
        else:
            stock_snapshot = {}
        snapshot = {**stock_snapshot, **more_snapshot}
        snapshot_date = str(snapshot_observed_date or trade_date) if snapshot else None
        float_shares = _optional_float(active_capital["float_shares"]) if active_capital else None
        total_shares = _optional_float(active_capital["total_shares"]) if active_capital else None
        open_value = _optional_float(bar["open"])
        high_value = _optional_float(bar["high"])
        low_value = _optional_float(bar["low"])

        row: dict[str, Any] = {
            "code": code,
            "trade_date": trade_date,
            "name": str(asset["name"]),
            "market": str(asset["market"]),
            "asset_type": str(asset["asset_type"]),
            "open": open_value,
            "high": high_value,
            "low": low_value,
            "close": close,
            "volume": _optional_float(bar["volume"]),
            "amount": _optional_float(bar["amount"]),
            "forward_factor": _optional_float(bar["forward_factor"]),
            "vol_in_stock": _optional_float(bar["vol_in_stock"]),
            "prev_close": prev_close,
            "return_1d": return_1d,
            "return_5d": return_5d,
            "return_20d": return_20d,
            "log_return_1d": math.log(close / prev_close) if prev_close and close > 0 else None,
            "intraday_return": _return(close, open_value),
            "amplitude": ((high_value - low_value) / prev_close if high_value is not None and low_value is not None and prev_close else None),
            "close_ma5": _window_mean(closes, 5),
            "close_ma20": _window_mean(closes, 20),
            "volume_ma20": _window_mean(volumes, 20),
            "amount_ma20": _window_mean(amounts, 20),
            "report_date": selected_report_date,
            "announce_date": selected_report[0] if selected_report else None,
            "report_age_days": _days_between(selected_report[0], trade_date) if selected_report else None,
            "share_capital_date": str(active_capital["effective_date"]) if active_capital else None,
            "float_shares": float_shares,
            "total_shares": total_shares,
            "market_cap": close * total_shares if total_shares is not None else None,
            "float_market_cap": close * float_shares if float_shares is not None else None,
            "action_count": int(action.get("action_count", 0)),
            "action_types": action.get("action_types"),
            "cash_dividend": action.get("cash_dividend"),
            "bonus_shares": action.get("bonus_shares"),
            "allotment_shares": action.get("allotment_shares"),
            "allotment_price": action.get("allotment_price"),
            "days_since_action": _days_between(last_action_date, trade_date) if last_action_date else None,
            "snapshot_date": snapshot_date,
            "built_at": built_at,
        }
        for field in FINANCIAL_FIELDS:
            row[field.lower()] = _optional_float(financial_values.get(field))
        row.update(snapshot)
        result.append(row)
    return result


def _load_report_values(
    connection: sqlite3.Connection, code: str
) -> dict[tuple[str, str], dict[str, float | str | None]]:
    result: dict[tuple[str, str], dict[str, float | str | None]] = defaultdict(dict)
    rows = connection.execute(
        """
        SELECT report_date,announce_date,field_name,numeric_value,text_value
        FROM financial_report_values WHERE code=? ORDER BY report_date,announce_date
        """,
        (code,),
    ).fetchall()
    for row in rows:
        result[(str(row["report_date"]), str(row["announce_date"]))][str(row["field_name"])] = (
            float(row["numeric_value"]) if row["numeric_value"] is not None else row["text_value"]
        )
    return dict(result)


def _aggregate_actions(rows: Iterable[sqlite3.Row]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        grouped[str(row["action_date"])].append(row)
    result: dict[str, dict[str, Any]] = {}
    for action_date, items in grouped.items():
        types = sorted({str(item["action_type"]) for item in items if item["action_type"]})
        result[action_date] = {
            "action_count": len(items),
            "action_types": ",".join(types) or None,
            "cash_dividend": _sum_present(item["cash_dividend"] for item in items),
            "bonus_shares": _sum_present(item["bonus_shares"] for item in items),
            "allotment_shares": _sum_present(item["allotment_shares"] for item in items),
            "allotment_price": _max_present(item["allotment_price"] for item in items),
        }
    return result


def _load_snapshots(
    connection: sqlite3.Connection,
    table: str,
    code: str,
    start_text: str,
    end_text: str,
    mapping: dict[str, str],
    *,
    effective_date_field: str | None = None,
) -> dict[str, dict[str, Any]]:
    existing = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}
    selected = {name: column for name, column in mapping.items() if column in existing}
    if not selected:
        return {}
    expressions = ",".join(f'"{column}" AS "{name}"' for name, column in selected.items())
    rows = connection.execute(
        f"SELECT observed_date,{expressions} FROM {table} "
        "WHERE code=? AND observed_date BETWEEN ? AND ? ORDER BY observed_date",
        (code, start_text, end_text),
    ).fetchall()
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        values: dict[str, Any] = {}
        for name in selected:
            value = row[name]
            values[name] = _optional_float(value) if name in NUMERIC_SNAPSHOT_FIELDS else _date_value(value)
        observed_date = str(row["observed_date"])
        effective_date = (
            str(values.get(effective_date_field) or observed_date)
            if effective_date_field
            else observed_date
        )
        if effective_date_field:
            values["snapshot_date"] = observed_date
        # 同一行情日可能在次日再次刷新，保留最后观察版本并记录真实观察日。
        if effective_date not in result or observed_date >= str(
            result[effective_date].get("snapshot_date", "")
        ):
            result[effective_date] = values
    return result


def _upsert_rows(connection: sqlite3.Connection, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    columns = ",".join(WIDE_COLUMNS)
    placeholders = ",".join("?" for _ in WIDE_COLUMNS)
    updates = ",".join(f"{column}=excluded.{column}" for column in WIDE_COLUMNS if column not in {"code", "trade_date"})
    connection.executemany(
        f"INSERT INTO quant_daily_wide({columns}) VALUES({placeholders}) "
        f"ON CONFLICT(code,trade_date) DO UPDATE SET {updates}",
        [tuple(row.get(column) for column in WIDE_COLUMNS) for row in rows],
    )


def _delete_range(
    connection: sqlite3.Connection, code: str, start: date | None, end: date | None
) -> None:
    conditions = ["code=?"]
    values: list[Any] = [code]
    if start is not None:
        conditions.append("trade_date>=?")
        values.append(start.isoformat())
    if end is not None:
        conditions.append("trade_date<=?")
        values.append(end.isoformat())
    connection.execute(
        "DELETE FROM quant_daily_wide WHERE " + " AND ".join(conditions), values
    )


def _return(current: float, base: float | None) -> float | None:
    return current / base - 1.0 if base not in (None, 0) else None


def _window_mean(values: Sequence[float | None], size: int) -> float | None:
    if len(values) < size or any(value is None for value in values[-size:]):
        return None
    return sum(float(value) for value in values[-size:]) / size


def _optional_float(value: object) -> float | None:
    if value in (None, "", "--"):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _sum_present(values: Iterable[object]) -> float | None:
    numbers = [_optional_float(value) for value in values]
    present = [value for value in numbers if value is not None]
    return sum(present) if present else None


def _max_present(values: Iterable[object]) -> float | None:
    numbers = [_optional_float(value) for value in values]
    present = [value for value in numbers if value is not None]
    return max(present) if present else None


def _date_value(value: object) -> str | None:
    if value in (None, "", "0", 0):
        return None
    text = str(value)
    digits = "".join(character for character in text if character.isdigit())
    if len(digits) >= 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return text


def _days_between(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
