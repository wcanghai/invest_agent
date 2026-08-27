"""构建无未来数据泄漏的股票/ETF 日频研究宽表。"""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Callable, Iterable


@dataclass(frozen=True)
class BuildResult:
    codes: int
    rows: int


FACTOR_COLUMNS = (
    "code", "trade_date", "name", "asset_type", "category", "benchmark_code",
    "open", "high", "low", "close", "volume", "amount",
    "return_1d", "return_20d", "momentum_252d", "volatility_20d", "volatility_60d",
    "max_drawdown_252d", "amount_ma20", "report_date", "announce_date",
    "report_age_days", "book_value_per_share", "ttm_profit_10k", "ttm_revenue_10k",
    "total_shares", "market_cap", "pb", "pe_ttm", "ps_ttm", "earnings_yield",
    "fcff_yield", "fcfe_yield", "dividend_yield", "roe", "roic", "gross_margin",
    "operating_margin", "net_margin", "cash_conversion", "asset_turnover",
    "debt_to_assets", "interest_bearing_debt_ratio", "current_ratio", "quick_ratio",
    "interest_coverage", "revenue_growth", "net_profit_growth", "equity_growth",
    "audit_opinion", "dividend_payout_ratio", "etf_iopv", "etf_premium_discount",
    "benchmark_return_20d", "tracking_difference_20d", "tracking_error_60d",
    "factor_flags", "built_at",
)


def build_factors(
    connection: sqlite3.Connection,
    codes: Iterable[str] | None = None,
    start: date | None = None,
    end: date | None = None,
    *,
    rebuild: bool = False,
    progress: Callable[[int, int, str, int], None] | None = None,
) -> BuildResult:
    """从规范化事实表构造研究宽表。"""
    selected = list(codes or [
        row[0] for row in connection.execute(
            "SELECT code FROM instruments WHERE asset_type IN ('stock','etf') ORDER BY code"
        )
    ])
    built_at = datetime.now(UTC).isoformat()
    written = 0
    for position, code in enumerate(selected, 1):
        instrument = connection.execute(
            "SELECT * FROM instruments WHERE code=?", (code,)
        ).fetchone()
        if instrument is None:
            continue
        # 每个标的是独立事务。长批次中断时，已经完成的标的仍可直接复用，
        # 当前标的发生异常则自动回滚其 rebuild 删除和写入。
        with connection:
            build_start = start
            if build_start is None and not rebuild:
                latest = connection.execute(
                    "SELECT MAX(trade_date) FROM factor_daily WHERE code=?", (code,)
                ).fetchone()[0]
                if latest:
                    build_start = date.fromisoformat(str(latest)) - timedelta(days=7)
            if rebuild:
                clauses = ["code=?"]
                parameters: list[Any] = [code]
                if start:
                    clauses.append("trade_date>=?")
                    parameters.append(start.isoformat())
                if end:
                    clauses.append("trade_date<=?")
                    parameters.append(end.isoformat())
                connection.execute(
                    f"DELETE FROM factor_daily WHERE {' AND '.join(clauses)}", parameters
                )
            rows = _factor_rows(connection, instrument, build_start, end, built_at)
            _upsert_factor_rows(connection, rows)
        written += len(rows)
        if progress is not None:
            progress(position, len(selected), code, len(rows))
    return BuildResult(len(selected), written)


def _factor_rows(
    connection: sqlite3.Connection,
    instrument: sqlite3.Row,
    start: date | None,
    end: date | None,
    built_at: str,
) -> list[dict[str, Any]]:
    code = str(instrument["code"])
    # 为滚动窗口预读 370 个自然日，输出时再裁切。
    read_start = start - timedelta(days=370) if start else None
    clauses = ["code=?"]
    parameters: list[Any] = [code]
    if read_start:
        clauses.append("trade_date>=?")
        parameters.append(read_start.isoformat())
    if end:
        clauses.append("trade_date<=?")
        parameters.append(end.isoformat())
    bars = connection.execute(
        f"SELECT * FROM market_bars WHERE {' AND '.join(clauses)} ORDER BY trade_date",
        parameters,
    ).fetchall()
    reports = _reports(connection, code)
    capitals = connection.execute(
        "SELECT * FROM share_capital WHERE code=? ORDER BY effective_date", (code,)
    ).fetchall()
    actions = connection.execute(
        "SELECT action_date,cash_dividend_per_10 FROM corporate_actions WHERE code=? ORDER BY action_date",
        (code,),
    ).fetchall()
    etf_snapshots = {
        str(row["observed_date"]): row
        for row in connection.execute("SELECT * FROM etf_snapshots WHERE code=?", (code,))
    }
    benchmark_returns = _benchmark_returns(connection, instrument["benchmark_code"])

    active_reports: dict[str, dict[str, Any]] = {}
    report_position = capital_position = 0
    active_capital: sqlite3.Row | None = None
    closes: list[float] = []
    returns: list[float | None] = []
    asset_return_by_date: dict[str, float | None] = {}
    amounts: list[float | None] = []
    result: list[dict[str, Any]] = []
    for bar in bars:
        trade_text = str(bar["trade_date"])
        trade_date = date.fromisoformat(trade_text)
        close = _float(bar["close"])
        if close is None or close <= 0:
            continue
        while report_position < len(reports) and reports[report_position]["announce_date"] <= trade_text:
            report = reports[report_position]
            active_reports[report["report_date"]] = report
            report_position += 1
        while capital_position < len(capitals) and str(capitals[capital_position]["effective_date"]) <= trade_text:
            active_capital = capitals[capital_position]
            capital_position += 1

        prior_close = closes[-1] if closes else None
        return_1d = close / prior_close - 1 if prior_close and prior_close > 0 else None
        closes.append(close)
        returns.append(return_1d)
        asset_return_by_date[trade_text] = return_1d
        amounts.append(_float(bar["amount"]))
        selected_report = _latest_report(active_reports, trade_text)
        values = selected_report["values"] if selected_report else {}
        flags: list[str] = []

        row: dict[str, Any] = {
            "code": code,
            "trade_date": trade_text,
            "name": str(instrument["name"]),
            "asset_type": str(instrument["asset_type"]),
            "category": str(instrument["category"]),
            "benchmark_code": instrument["benchmark_code"],
            "open": bar["open"], "high": bar["high"], "low": bar["low"],
            "close": close, "volume": bar["volume"], "amount": bar["amount"],
            "return_1d": return_1d,
            "return_20d": _period_return(closes, 20),
            "momentum_252d": _period_return(closes, 252),
            "volatility_20d": _volatility(returns, 20),
            "volatility_60d": _volatility(returns, 60),
            "max_drawdown_252d": _max_drawdown(closes[-252:]),
            "amount_ma20": _mean(amounts[-20:]),
            "report_date": selected_report["report_date"] if selected_report else None,
            "announce_date": selected_report["announce_date"] if selected_report else None,
            "report_age_days": (
                (trade_date - date.fromisoformat(selected_report["report_date"])).days
                if selected_report else None
            ),
            "book_value_per_share": None, "ttm_profit_10k": None,
            "ttm_revenue_10k": None, "total_shares": None, "market_cap": None,
            "pb": None, "pe_ttm": None, "ps_ttm": None, "earnings_yield": None,
            "fcff_yield": None, "fcfe_yield": None, "dividend_yield": None,
            "roe": None, "roic": None, "gross_margin": None, "operating_margin": None,
            "net_margin": None, "cash_conversion": None, "asset_turnover": None,
            "debt_to_assets": None, "interest_bearing_debt_ratio": None,
            "current_ratio": None, "quick_ratio": None, "interest_coverage": None,
            "revenue_growth": None, "net_profit_growth": None, "equity_growth": None,
            "audit_opinion": None, "dividend_payout_ratio": None,
            "etf_iopv": None, "etf_premium_discount": None,
            "benchmark_return_20d": None, "tracking_difference_20d": None,
            "tracking_error_60d": None, "factor_flags": "", "built_at": built_at,
        }
        if instrument["asset_type"] == "stock":
            _stock_factors(row, values, active_capital, actions, trade_date, close, flags)
        else:
            _etf_factors(
                row, etf_snapshots.get(trade_text), benchmark_returns,
                asset_return_by_date, flags,
            )
        row["factor_flags"] = ",".join(flags)
        if start is None or trade_date >= start:
            result.append(row)
    return result


def _stock_factors(
    row: dict[str, Any], values: dict[str, float | None], capital: sqlite3.Row | None,
    actions: list[sqlite3.Row], trade_date: date, close: float, flags: list[str],
) -> None:
    if not values:
        flags.append("missing_financial_report")
        return
    bps = _positive(values.get("FN4"))
    shares = _positive(values.get("FN238"))
    if shares is None and capital is not None:
        shares = _positive(_float(capital["total_shares"]))
    profit_10k = _float(values.get("FN308"))
    revenue_10k = _float(values.get("FN319"))
    market_cap = close * shares if shares else None
    profit_yuan = profit_10k * 10_000 if profit_10k is not None else _float(values.get("FN276"))
    revenue_yuan = revenue_10k * 10_000 if revenue_10k is not None else None
    pe = market_cap / profit_yuan if market_cap and profit_yuan and profit_yuan > 0 else None
    ps = market_cap / revenue_yuan if market_cap and revenue_yuan and revenue_yuan > 0 else None
    dividends = sum(
        (_float(item["cash_dividend_per_10"]) or 0) / 10
        for item in actions
        if trade_date - timedelta(days=365) < date.fromisoformat(item["action_date"]) <= trade_date
    )
    row.update({
        "book_value_per_share": bps,
        "ttm_profit_10k": profit_10k,
        "ttm_revenue_10k": revenue_10k,
        "total_shares": shares,
        "market_cap": market_cap,
        "pb": close / bps if bps else None,
        "pe_ttm": pe,
        "ps_ttm": ps,
        "earnings_yield": 1 / pe if pe and pe > 0 else None,
        "fcff_yield": _ratio(values.get("FN321"), close),
        "fcfe_yield": _ratio(values.get("FN322"), close),
        "dividend_yield": dividends / close if dividends > 0 else None,
        "roe": _first(values, "FN281", "FN197", "FN6"),
        "roic": _float(values.get("FN329")),
        "gross_margin": _float(values.get("FN202")),
        "operating_margin": _float(values.get("FN194")),
        "net_margin": _float(values.get("FN199")),
        "cash_conversion": _float(values.get("FN228")),
        "asset_turnover": _float(values.get("FN175")),
        "debt_to_assets": _float(values.get("FN210")),
        "interest_bearing_debt_ratio": _float(values.get("FN327")),
        "current_ratio": _float(values.get("FN159")),
        "quick_ratio": _float(values.get("FN160")),
        "interest_coverage": _float(values.get("FN162")),
        "revenue_growth": _float(values.get("FN183")),
        "net_profit_growth": _float(values.get("FN184")),
        "equity_growth": _float(values.get("FN185")),
        "audit_opinion": _float(values.get("FN336")),
        "dividend_payout_ratio": _float(values.get("FN337")),
    })
    if bps is None:
        flags.append("missing_bps")
    if shares is None:
        flags.append("missing_total_shares")
    if pe is None:
        flags.append("pe_not_computable")
    if revenue_yuan is None:
        flags.append("ps_not_computable")


def _etf_factors(
    row: dict[str, Any], snapshot: sqlite3.Row | None,
    benchmark_returns: dict[str, float | None],
    asset_returns: dict[str, float | None], flags: list[str],
) -> None:
    if snapshot is not None:
        row["etf_iopv"] = snapshot["iopv"]
        row["etf_premium_discount"] = snapshot["premium_discount"]
    else:
        flags.append("missing_daily_iopv")
    benchmark_code = row["benchmark_code"]
    if not benchmark_code:
        flags.append("benchmark_not_configured")
        return
    trade_date = str(row["trade_date"])
    benchmark_20d = _benchmark_period_return(benchmark_returns, trade_date, 20)
    row["benchmark_return_20d"] = benchmark_20d
    if row["return_20d"] is not None and benchmark_20d is not None:
        row["tracking_difference_20d"] = row["return_20d"] - benchmark_20d
    paired = _paired_active_returns(benchmark_returns, asset_returns, trade_date, 60)
    if len(paired) >= 20:
        row["tracking_error_60d"] = _sample_stdev(paired) * math.sqrt(252)
    else:
        flags.append("insufficient_benchmark_history")


def _reports(connection: sqlite3.Connection, code: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    reports = connection.execute(
        "SELECT report_date,announce_date FROM financial_reports WHERE code=? ORDER BY announce_date,report_date",
        (code,),
    ).fetchall()
    for report in reports:
        values = {
            str(row["field_code"]): _float(row["numeric_value"])
            for row in connection.execute(
                """SELECT field_code,numeric_value FROM financial_values
                WHERE code=? AND report_date=? AND announce_date=?""",
                (code, report["report_date"], report["announce_date"]),
            )
        }
        result.append({"report_date": str(report["report_date"]),
                       "announce_date": str(report["announce_date"]), "values": values})
    return result


def _latest_report(active: dict[str, dict[str, Any]], trade_date: str) -> dict[str, Any] | None:
    eligible = [key for key in active if key <= trade_date]
    return active[max(eligible)] if eligible else None


def _benchmark_returns(connection: sqlite3.Connection, code: Any) -> dict[str, float | None]:
    if not code:
        return {}
    rows = connection.execute(
        "SELECT trade_date,close FROM market_bars WHERE code=? ORDER BY trade_date", (code,)
    ).fetchall()
    result: dict[str, float | None] = {}
    previous: float | None = None
    for row in rows:
        close = _positive(_float(row["close"]))
        result[str(row["trade_date"])] = close / previous - 1 if close and previous else None
        previous = close
    return result


def _benchmark_period_return(
    daily_returns: dict[str, float | None], end_date: str, periods: int
) -> float | None:
    dates = [key for key in daily_returns if key <= end_date and daily_returns[key] is not None]
    selected = dates[-periods:]
    if len(selected) < periods:
        return None
    return math.prod(1 + float(daily_returns[key]) for key in selected) - 1


def _paired_active_returns(
    benchmark: dict[str, float | None], asset_returns: dict[str, float | None],
    end_date: str, periods: int,
) -> list[float]:
    dates = [
        key for key in asset_returns
        if key <= end_date and asset_returns[key] is not None and benchmark.get(key) is not None
    ][-periods:]
    return [float(asset_returns[key]) - float(benchmark[key]) for key in dates]


def _upsert_factor_rows(connection: sqlite3.Connection, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    columns = ",".join(FACTOR_COLUMNS)
    placeholders = ",".join("?" for _ in FACTOR_COLUMNS)
    updates = ",".join(f"{column}=excluded.{column}" for column in FACTOR_COLUMNS[2:])
    connection.executemany(
        f"INSERT INTO factor_daily({columns}) VALUES ({placeholders}) "
        f"ON CONFLICT(code,trade_date) DO UPDATE SET {updates}",
        [[row.get(column) for column in FACTOR_COLUMNS] for row in rows],
    )


def _period_return(values: list[float], periods: int) -> float | None:
    return values[-1] / values[-periods - 1] - 1 if len(values) > periods else None


def _volatility(values: list[float | None], periods: int) -> float | None:
    sample = [value for value in values[-periods:] if value is not None]
    return _sample_stdev(sample) * math.sqrt(252) if len(sample) >= periods else None


def _sample_stdev(values: list[float]) -> float:
    """使用浮点两遍算法，避免 statistics 在 Python 3.14 中构造 Fraction。"""
    count = len(values)
    if count < 2:
        return 0.0
    mean = math.fsum(values) / count
    variance = math.fsum((value - mean) ** 2 for value in values) / (count - 1)
    return math.sqrt(max(0.0, variance))


def _max_drawdown(values: list[float]) -> float | None:
    if not values:
        return None
    peak = values[0]
    drawdown = 0.0
    for value in values:
        peak = max(peak, value)
        drawdown = min(drawdown, value / peak - 1)
    return drawdown


def _mean(values: list[float | None]) -> float | None:
    sample = [value for value in values if value is not None]
    return sum(sample) / len(sample) if sample else None


def _float(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _positive(value: Any) -> float | None:
    result = _float(value)
    return result if result is not None and result > 0 else None


def _ratio(value: Any, denominator: float) -> float | None:
    numerator = _float(value)
    return numerator / denominator if numerator is not None and denominator > 0 else None


def _first(values: dict[str, float | None], *keys: str) -> float | None:
    for key in keys:
        value = _float(values.get(key))
        if value is not None:
            return value
    return None
