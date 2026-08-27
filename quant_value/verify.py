"""研究数据覆盖率与可计算性验证。"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Iterable


STOCK_REQUIRED_FACTORS = (
    "pb", "pe_ttm", "ps_ttm", "roe", "roic", "gross_margin", "net_margin",
    "cash_conversion", "debt_to_assets", "current_ratio", "revenue_growth",
    "net_profit_growth",
)
MIN_FACTOR_COVERAGE = 0.90


@dataclass(frozen=True)
class Coverage:
    code: str
    name: str
    asset_type: str
    bars: int
    first_date: str | None
    last_date: str | None
    reports: int
    financial_fields: int
    capitals: int
    actions: int
    snapshots: int
    relations: int
    factors: int
    required_factor_coverage: float
    latest_pb: float | None
    latest_pe_ttm: float | None
    latest_roe: float | None
    latest_iopv: float | None
    latest_tracking_error: float | None
    status: str
    notes: str


def verify_coverage(
    connection: sqlite3.Connection, codes: Iterable[str] | None = None
) -> list[Coverage]:
    selected = list(codes or [
        row[0] for row in connection.execute(
            "SELECT code FROM instruments WHERE asset_type IN ('stock','etf') ORDER BY code"
        )
    ])
    result: list[Coverage] = []
    for code in selected:
        instrument = connection.execute("SELECT * FROM instruments WHERE code=?", (code,)).fetchone()
        if instrument is None:
            continue
        bars = connection.execute(
            "SELECT COUNT(*),MIN(trade_date),MAX(trade_date) FROM market_bars WHERE code=?", (code,)
        ).fetchone()
        reports = connection.execute(
            "SELECT COUNT(*) FROM financial_reports WHERE code=?", (code,)
        ).fetchone()[0]
        financial_fields = connection.execute(
            "SELECT COUNT(DISTINCT field_code) FROM financial_values WHERE code=?", (code,)
        ).fetchone()[0]
        capitals = connection.execute(
            "SELECT COUNT(*) FROM share_capital WHERE code=?", (code,)
        ).fetchone()[0]
        actions = connection.execute(
            "SELECT COUNT(*) FROM corporate_actions WHERE code=?", (code,)
        ).fetchone()[0]
        snapshots = connection.execute(
            "SELECT COUNT(*) FROM daily_snapshots WHERE code=?", (code,)
        ).fetchone()[0]
        relations = connection.execute(
            "SELECT COUNT(*) FROM relations WHERE code=?", (code,)
        ).fetchone()[0]
        factors = connection.execute(
            "SELECT COUNT(*) FROM factor_daily WHERE code=?", (code,)
        ).fetchone()[0]
        latest = connection.execute(
            "SELECT * FROM factor_daily WHERE code=? ORDER BY trade_date DESC LIMIT 1", (code,)
        ).fetchone()
        notes: list[str] = []
        if bars[0] == 0:
            notes.append("无行情")
        if instrument["asset_type"] == "stock" and reports == 0:
            notes.append("无专业财务；请先在通达信下载专业财务数据")
        if instrument["asset_type"] == "stock" and capitals == 0:
            notes.append("无历史股本")
        if snapshots == 0:
            notes.append("无当日证券快照")
        if relations == 0:
            notes.append("无行业/概念关系")
        if instrument["asset_type"] == "etf" and instrument["benchmark_code"] is None:
            notes.append("TDX 未验证该类 ETF 基准映射，仅计算价格/流动性因子")
        if latest is None:
            notes.append("尚未构建因子")
        elif latest["factor_flags"]:
            notes.append(str(latest["factor_flags"]))
        required_coverage = _required_factor_coverage(
            connection, code, str(instrument["asset_type"]), int(factors)
        )
        if instrument["asset_type"] == "stock" and required_coverage < MIN_FACTOR_COVERAGE:
            notes.append(f"关键股票因子覆盖率仅 {required_coverage:.1%}")
        stock_ready = (
            reports > 0 and financial_fields > 0 and capitals > 0
            and required_coverage >= MIN_FACTOR_COVERAGE
        ) if instrument["asset_type"] == "stock" else True
        status = "通过" if (
            bars[0] > 0 and factors == bars[0] and snapshots > 0 and relations > 0 and stock_ready
        ) else "不通过"
        result.append(Coverage(
            code=code, name=str(instrument["name"]), asset_type=str(instrument["asset_type"]),
            bars=int(bars[0]), first_date=bars[1], last_date=bars[2], reports=int(reports),
            financial_fields=int(financial_fields), capitals=int(capitals), actions=int(actions),
            snapshots=int(snapshots), relations=int(relations), factors=int(factors),
            required_factor_coverage=required_coverage, latest_pb=_value(latest, "pb"),
            latest_pe_ttm=_value(latest, "pe_ttm"), latest_roe=_value(latest, "roe"),
            latest_iopv=_value(latest, "etf_iopv"),
            latest_tracking_error=_value(latest, "tracking_error_60d"),
            status=status, notes="；".join(notes) or "核心数据可用",
        ))
    return result


def _required_factor_coverage(
    connection: sqlite3.Connection, code: str, asset_type: str, factors: int
) -> float:
    if factors == 0:
        return 0.0
    if asset_type != "stock":
        return 1.0
    complete = connection.execute(
        "SELECT COUNT(*) FROM factor_daily WHERE code=? AND "
        + " AND ".join(f"{field} IS NOT NULL" for field in STOCK_REQUIRED_FACTORS),
        (code,),
    ).fetchone()[0]
    return int(complete) / factors


def _value(row: sqlite3.Row | None, name: str) -> float | None:
    return None if row is None or row[name] is None else float(row[name])
