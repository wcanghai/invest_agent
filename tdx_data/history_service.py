"""历史公司数据的 point-in-time 读取和财务指标输入构建。"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date


FinancialValue = float | str | None


@dataclass(frozen=True)
class FinancialReportSnapshot:
    """在指定日期前已经公开、且报告期最新的一版财报。"""

    code: str
    report_date: date
    announce_date: date
    values: dict[str, FinancialValue]


@dataclass(frozen=True)
class ShareCapitalSnapshot:
    """指定日期有效的股本结构。"""

    code: str
    effective_date: date
    float_shares: float | None
    total_shares: float | None


@dataclass(frozen=True)
class CorporateAction:
    code: str
    action_date: date
    action_type: str | None
    cash_dividend: float | None
    bonus_shares: float | None
    allotment_shares: float | None
    allotment_price: float | None


@dataclass(frozen=True)
class HistoricalMetricInput:
    """一个交易日计算财务指标所需的时点一致输入。"""

    code: str
    trade_date: date
    close: float
    report_date: date | None
    announce_date: date | None
    financial_values: dict[str, FinancialValue]
    share_capital_date: date | None
    float_shares: float | None
    total_shares: float | None


@dataclass(frozen=True)
class HistoricalPb:
    code: str
    trade_date: date
    close: float
    report_date: date
    announce_date: date
    book_value_per_share: float
    pb: float


def financial_report_as_of(
    connection: sqlite3.Connection, code: str, as_of: date
) -> FinancialReportSnapshot | None:
    """返回当日已经公告且报告期最新的财报，避免未来函数。"""
    row = connection.execute(
        """
        SELECT code, report_date, announce_date
        FROM financial_reports
        WHERE code=? AND announce_date<=? AND report_date<=?
        ORDER BY report_date DESC, announce_date DESC
        LIMIT 1
        """,
        (code, as_of.isoformat(), as_of.isoformat()),
    ).fetchone()
    if row is None:
        return None
    key = (str(row["code"]), str(row["report_date"]), str(row["announce_date"]))
    return FinancialReportSnapshot(
        code=key[0],
        report_date=date.fromisoformat(key[1]),
        announce_date=date.fromisoformat(key[2]),
        values=financial_values(connection, *key),
    )


def financial_values(
    connection: sqlite3.Connection,
    code: str,
    report_date: str,
    announce_date: str,
) -> dict[str, FinancialValue]:
    """读取一版财报的全部结构化字段。"""
    rows = connection.execute(
        """
        SELECT field_name, numeric_value, text_value
        FROM financial_report_values
        WHERE code=? AND report_date=? AND announce_date=?
        ORDER BY field_name
        """,
        (code, report_date, announce_date),
    ).fetchall()
    return {
        str(row["field_name"]): (
            float(row["numeric_value"])
            if row["numeric_value"] is not None
            else row["text_value"]
        )
        for row in rows
    }


def share_capital_as_of(
    connection: sqlite3.Connection, code: str, as_of: date
) -> ShareCapitalSnapshot | None:
    """返回指定日期最近一条已经生效的股本记录。"""
    row = connection.execute(
        """
        SELECT code, effective_date, float_shares, total_shares
        FROM share_capital_history
        WHERE code=? AND effective_date<=?
        ORDER BY effective_date DESC
        LIMIT 1
        """,
        (code, as_of.isoformat()),
    ).fetchone()
    if row is None:
        return None
    return ShareCapitalSnapshot(
        code=str(row["code"]),
        effective_date=date.fromisoformat(str(row["effective_date"])),
        float_shares=_optional_float(row["float_shares"]),
        total_shares=_optional_float(row["total_shares"]),
    )


def corporate_actions_between(
    connection: sqlite3.Connection, code: str, start: date, end: date
) -> list[CorporateAction]:
    """读取区间内结构化公司行为。"""
    if start > end:
        raise ValueError("start 不能晚于 end")
    rows = connection.execute(
        """
        SELECT code, action_date, action_type, cash_dividend, bonus_shares,
               allotment_shares, allotment_price
        FROM corporate_actions
        WHERE code=? AND action_date BETWEEN ? AND ?
        ORDER BY action_date, record_key
        """,
        (code, start.isoformat(), end.isoformat()),
    ).fetchall()
    return [
        CorporateAction(
            code=str(row["code"]),
            action_date=date.fromisoformat(str(row["action_date"])),
            action_type=row["action_type"],
            cash_dividend=_optional_float(row["cash_dividend"]),
            bonus_shares=_optional_float(row["bonus_shares"]),
            allotment_shares=_optional_float(row["allotment_shares"]),
            allotment_price=_optional_float(row["allotment_price"]),
        )
        for row in rows
    ]


def historical_metric_inputs(
    connection: sqlite3.Connection, code: str, start: date, end: date
) -> list[HistoricalMetricInput]:
    """把日线、当时已公告财报和当时股本合并为每日指标输入。"""
    if start > end:
        raise ValueError("start 不能晚于 end")
    bars = connection.execute(
        """
        SELECT trade_date, close FROM daily_bars
        WHERE code=? AND trade_date BETWEEN ? AND ?
        ORDER BY trade_date
        """,
        (code, start.isoformat(), end.isoformat()),
    ).fetchall()
    reports = connection.execute(
        """
        SELECT code, report_date, announce_date
        FROM financial_reports
        WHERE code=? AND announce_date<=? AND report_date<=?
        ORDER BY announce_date, report_date
        """,
        (code, end.isoformat(), end.isoformat()),
    ).fetchall()
    capitals = connection.execute(
        """
        SELECT effective_date, float_shares, total_shares
        FROM share_capital_history
        WHERE code=? AND effective_date<=?
        ORDER BY effective_date
        """,
        (code, end.isoformat()),
    ).fetchall()

    value_map = _financial_value_map(connection, code, reports)
    report_index = capital_index = 0
    active_reports: dict[str, tuple[str, dict[str, FinancialValue]]] = {}
    active_capital: sqlite3.Row | None = None
    result: list[HistoricalMetricInput] = []
    for bar in bars:
        trade_date_text = str(bar["trade_date"])
        while report_index < len(reports):
            report = reports[report_index]
            if str(report["announce_date"]) > trade_date_text:
                break
            report_date_text = str(report["report_date"])
            active_reports[report_date_text] = (
                str(report["announce_date"]),
                value_map.get((report_date_text, str(report["announce_date"])), {}),
            )
            report_index += 1
        while capital_index < len(capitals):
            capital = capitals[capital_index]
            if str(capital["effective_date"]) > trade_date_text:
                break
            active_capital = capital
            capital_index += 1

        eligible_reports = [
            report_date for report_date in active_reports if report_date <= trade_date_text
        ]
        selected_date = max(eligible_reports) if eligible_reports else None
        selected = active_reports.get(selected_date) if selected_date else None
        result.append(
            HistoricalMetricInput(
                code=code,
                trade_date=date.fromisoformat(trade_date_text),
                close=float(bar["close"]),
                report_date=date.fromisoformat(selected_date) if selected_date else None,
                announce_date=date.fromisoformat(selected[0]) if selected else None,
                financial_values=dict(selected[1]) if selected else {},
                share_capital_date=(
                    date.fromisoformat(str(active_capital["effective_date"]))
                    if active_capital is not None
                    else None
                ),
                float_shares=(
                    _optional_float(active_capital["float_shares"])
                    if active_capital is not None
                    else None
                ),
                total_shares=(
                    _optional_float(active_capital["total_shares"])
                    if active_capital is not None
                    else None
                ),
            )
        )
    return result


def calculate_historical_pb(
    connection: sqlite3.Connection,
    code: str,
    start: date,
    end: date,
    *,
    book_value_per_share_field: str,
) -> list[HistoricalPb]:
    """用调用方已验证的每股净资产字段计算历史 PB。"""
    field_name = book_value_per_share_field.strip().upper()
    if not field_name:
        raise ValueError("book_value_per_share_field 不能为空")
    result: list[HistoricalPb] = []
    for item in historical_metric_inputs(connection, code, start, end):
        book_value = _positive_float(item.financial_values.get(field_name))
        if book_value is None or item.report_date is None or item.announce_date is None:
            continue
        result.append(
            HistoricalPb(
                code=code,
                trade_date=item.trade_date,
                close=item.close,
                report_date=item.report_date,
                announce_date=item.announce_date,
                book_value_per_share=book_value,
                pb=item.close / book_value,
            )
        )
    return result


def _financial_value_map(
    connection: sqlite3.Connection,
    code: str,
    reports: list[sqlite3.Row],
) -> dict[tuple[str, str], dict[str, FinancialValue]]:
    keys = {(str(row["report_date"]), str(row["announce_date"])) for row in reports}
    result: dict[tuple[str, str], dict[str, FinancialValue]] = {key: {} for key in keys}
    rows = connection.execute(
        """
        SELECT report_date, announce_date, field_name, numeric_value, text_value
        FROM financial_report_values
        WHERE code=?
        ORDER BY report_date, announce_date, field_name
        """,
        (code,),
    ).fetchall()
    for row in rows:
        key = (str(row["report_date"]), str(row["announce_date"]))
        if key not in result:
            continue
        result[key][str(row["field_name"])] = (
            float(row["numeric_value"])
            if row["numeric_value"] is not None
            else row["text_value"]
        )
    return result


def _optional_float(value: object) -> float | None:
    return None if value is None else float(value)


def _positive_float(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None
