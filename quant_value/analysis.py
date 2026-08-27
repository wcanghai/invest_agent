"""基于时点一致因子进行可解释的股票价值分析。"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Any, Iterable


ANNUAL_FIELDS = {
    "roe": "FN281",
    "roic": "FN329",
    "gross_margin": "FN202",
    "net_margin": "FN199",
    "cash_conversion": "FN228",
    "debt_to_assets": "FN210",
    "current_ratio": "FN159",
    "revenue_growth": "FN183",
    "net_profit_growth": "FN184",
    "equity_growth": "FN185",
    "audit_opinion": "FN336",
    "dividend_payout_ratio": "FN337",
}

AUDIT_OPINIONS = {
    0: "未审计",
    1: "无保留意见",
    2: "带强调事项段的无保留意见",
    3: "保留意见",
    4: "无法表示意见",
    5: "否定意见及其他",
}


@dataclass(frozen=True)
class DimensionScore:
    """单个价值分析维度的分数和证据。"""

    score: float | None
    evidence: dict[str, float | str | None]
    note: str


@dataclass(frozen=True)
class StockAnalysis:
    """某只股票在指定交易日的价值分析快照。"""

    code: str
    name: str
    as_of: str
    price_date: str
    report_date: str | None
    announce_date: str | None
    annual_report_date: str | None
    annual_announce_date: str | None
    valuation: DimensionScore
    quality: DimensionScore
    growth: DimensionScore
    safety: DimensionScore
    shareholder_return: DimensionScore
    overall_score: float | None
    conclusion: str
    strengths: tuple[str, ...]
    risks: tuple[str, ...]
    data_warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """返回适合 JSON 序列化的分析结果。"""
        return asdict(self)


def analyze_stocks(
    connection: sqlite3.Connection,
    codes: Iterable[str] | None = None,
    as_of: date | None = None,
    *,
    history_years: int = 5,
) -> list[StockAnalysis]:
    """分析指定股票；所有数据的可见日期均不晚于 ``as_of``。"""
    if history_years < 1:
        raise ValueError("history_years 必须大于等于 1")
    analysis_date = as_of or date.today()
    selected = list(codes or [
        row[0] for row in connection.execute(
            "SELECT code FROM instruments WHERE asset_type='stock' ORDER BY code"
        )
    ])
    results: list[StockAnalysis] = []
    for code in selected:
        instrument = connection.execute(
            "SELECT code,name,asset_type FROM instruments WHERE code=?", (code,)
        ).fetchone()
        if instrument is None:
            raise ValueError(f"数据库中不存在代码：{code}")
        if instrument["asset_type"] != "stock":
            raise ValueError(f"{code} 不是股票；ETF 应使用跟踪质量与折溢价分析")
        latest = connection.execute(
            "SELECT * FROM factor_daily WHERE code=? AND trade_date<=? "
            "ORDER BY trade_date DESC LIMIT 1",
            (code, analysis_date.isoformat()),
        ).fetchone()
        if latest is None:
            raise ValueError(f"{code} 在 {analysis_date.isoformat()} 前没有已构建因子")
        annual = _annual_reports(connection, code, str(latest["trade_date"]), limit=5)
        current_annual = annual[0] if annual else None
        results.append(_analyze_one(
            connection, instrument, latest, current_annual, annual,
            analysis_date, history_years,
        ))
    return results


def _analyze_one(
    connection: sqlite3.Connection,
    instrument: sqlite3.Row,
    latest: sqlite3.Row,
    annual: dict[str, Any] | None,
    annual_history: list[dict[str, Any]],
    as_of: date,
    history_years: int,
) -> StockAnalysis:
    code = str(instrument["code"])
    history_start = date.fromisoformat(str(latest["trade_date"])) - timedelta(
        days=366 * history_years
    )
    history = connection.execute(
        "SELECT pb,pe_ttm,ps_ttm FROM factor_daily "
        "WHERE code=? AND trade_date BETWEEN ? AND ? ORDER BY trade_date",
        (code, history_start.isoformat(), str(latest["trade_date"])),
    ).fetchall()
    annual_values = annual["values"] if annual else {}
    percentiles = {
        field: _percentile(_number(latest[field]), [_number(row[field]) for row in history])
        for field in ("pe_ttm", "pb", "ps_ttm")
    }
    valuation = _dimension(
        [
            (_inverse_percentile(percentiles["pe_ttm"]), 0.35),
            (_inverse_percentile(percentiles["pb"]), 0.30),
            (_inverse_percentile(percentiles["ps_ttm"]), 0.15),
            (_scale(_number(latest["earnings_yield"]), 0.02, 0.08), 0.10),
            (_scale(_number(latest["dividend_yield"]), 0.00, 0.05), 0.10),
        ],
        {
            "pe_ttm": _number(latest["pe_ttm"]), "pb": _number(latest["pb"]),
            "ps_ttm": _number(latest["ps_ttm"]),
            "pe_history_percentile": percentiles["pe_ttm"],
            "pb_history_percentile": percentiles["pb"],
            "ps_history_percentile": percentiles["ps_ttm"],
            "earnings_yield": _number(latest["earnings_yield"]),
            "dividend_yield": _number(latest["dividend_yield"]),
        },
        "估值越处于自身近年低分位、盈利与股息收益率越高，分数越高。",
    )
    roe_history = [_number(item["values"].get("roe")) for item in annual_history]
    quality = _dimension(
        [
            (_scale(_number(annual_values.get("roe")), 8, 25), 0.30),
            (_scale(_number(annual_values.get("roic")), 6, 20), 0.30),
            (_scale(_number(annual_values.get("net_margin")), 3, 25), 0.15),
            (_scale(_number(annual_values.get("cash_conversion")), 60, 130), 0.15),
            (_positive_ratio(roe_history), 0.10),
        ],
        {
            "annual_roe": _number(annual_values.get("roe")),
            "annual_roic": _number(annual_values.get("roic")),
            "annual_gross_margin": _number(annual_values.get("gross_margin")),
            "annual_net_margin": _number(annual_values.get("net_margin")),
            "annual_cash_conversion": _number(annual_values.get("cash_conversion")),
            "positive_roe_year_ratio": _ratio01(roe_history),
        },
        "盈利质量使用最近已公告年报，避免季度指标与全年指标直接混比。",
    )
    growth = _dimension(
        [
            (_scale(_number(annual_values.get("revenue_growth")), -5, 20), 0.35),
            (_scale(_number(annual_values.get("net_profit_growth")), -5, 25), 0.45),
            (_scale(_number(annual_values.get("equity_growth")), -5, 20), 0.20),
        ],
        {
            "annual_revenue_growth": _number(annual_values.get("revenue_growth")),
            "annual_net_profit_growth": _number(annual_values.get("net_profit_growth")),
            "annual_equity_growth": _number(annual_values.get("equity_growth")),
        },
        "成长维度关注营收、利润和净资产的年报同比变化，不外推未来增速。",
    )
    audit = _number(annual_values.get("audit_opinion"))
    safety = _dimension(
        [
            (_inverse_scale(_number(annual_values.get("debt_to_assets")), 30, 75), 0.35),
            (_scale(_number(annual_values.get("current_ratio")), 0.8, 2.0), 0.15),
            (_inverse_scale(_number(latest["volatility_60d"]), 0.18, 0.55), 0.20),
            (_inverse_scale(_absolute(_number(latest["max_drawdown_252d"])), 0.10, 0.50), 0.20),
            (_audit_score(audit), 0.10),
        ],
        {
            "annual_debt_to_assets": _number(annual_values.get("debt_to_assets")),
            "annual_current_ratio": _number(annual_values.get("current_ratio")),
            "audit_opinion_code": audit,
            "audit_opinion": _audit_label(audit),
            "volatility_60d": _number(latest["volatility_60d"]),
            "max_drawdown_252d": _number(latest["max_drawdown_252d"]),
        },
        "安全性同时考虑年报资产负债、审计意见及近期价格风险。",
    )
    payout = _number(annual_values.get("dividend_payout_ratio"))
    shareholder = _dimension(
        [
            (_scale(_number(latest["dividend_yield"]), 0.0, 0.05), 0.60),
            (_payout_score(payout), 0.40),
        ],
        {
            "trailing_dividend_yield": _number(latest["dividend_yield"]),
            "annual_dividend_payout_ratio": payout,
        },
        "股东回报关注近一年现金股息率及年报分红支付比例。",
    )
    dimensions = [valuation, quality, growth, safety, shareholder]
    overall = _weighted_average(
        [(item.score, weight) for item, weight in zip(
            dimensions, (0.30, 0.25, 0.15, 0.20, 0.10), strict=True
        )]
    )
    risks, warnings = _risks(latest, annual_values, percentiles, annual)
    strengths = _strengths(valuation, quality, growth, safety, shareholder)
    return StockAnalysis(
        code=code, name=str(instrument["name"]), as_of=as_of.isoformat(),
        price_date=str(latest["trade_date"]), report_date=latest["report_date"],
        announce_date=latest["announce_date"],
        annual_report_date=annual["report_date"] if annual else None,
        annual_announce_date=annual["announce_date"] if annual else None,
        valuation=valuation, quality=quality, growth=growth, safety=safety,
        shareholder_return=shareholder, overall_score=overall,
        conclusion=_conclusion(overall, risks), strengths=tuple(strengths),
        risks=tuple(risks), data_warnings=tuple(warnings),
    )


def _annual_reports(
    connection: sqlite3.Connection, code: str, visible_date: str, limit: int
) -> list[dict[str, Any]]:
    reports = connection.execute(
        "SELECT report_date,MAX(announce_date) AS announce_date FROM financial_reports "
        "WHERE code=? AND report_date LIKE '%-12-31' AND announce_date<=? "
        "GROUP BY report_date ORDER BY report_date DESC LIMIT ?",
        (code, visible_date, limit),
    ).fetchall()
    result: list[dict[str, Any]] = []
    for report in reports:
        raw = dict(connection.execute(
            "SELECT field_code,numeric_value FROM financial_values "
            "WHERE code=? AND report_date=? AND announce_date=?",
            (code, report["report_date"], report["announce_date"]),
        ).fetchall())
        result.append({
            "report_date": str(report["report_date"]),
            "announce_date": str(report["announce_date"]),
            "values": {name: _number(raw.get(field)) for name, field in ANNUAL_FIELDS.items()},
        })
    return result


def _dimension(
    components: list[tuple[float | None, float]],
    evidence: dict[str, float | str | None],
    note: str,
) -> DimensionScore:
    return DimensionScore(_weighted_average(components), evidence, note)


def _weighted_average(values: list[tuple[float | None, float]]) -> float | None:
    available = [(value, weight) for value, weight in values if value is not None]
    if not available:
        return None
    total_weight = sum(weight for _, weight in available)
    return round(sum(value * weight for value, weight in available) / total_weight, 1)


def _scale(value: float | None, low: float, high: float) -> float | None:
    if value is None:
        return None
    return 100 * min(1.0, max(0.0, (value - low) / (high - low)))


def _inverse_scale(value: float | None, low: float, high: float) -> float | None:
    score = _scale(value, low, high)
    return None if score is None else 100 - score


def _percentile(current: float | None, values: list[float | None]) -> float | None:
    sample = sorted(value for value in values if value is not None and value > 0)
    if current is None or len(sample) < 60:
        return None
    below = sum(value < current for value in sample)
    equal = sum(value == current for value in sample)
    return (below + equal / 2) / len(sample)


def _inverse_percentile(value: float | None) -> float | None:
    return None if value is None else 100 * (1 - value)


def _positive_ratio(values: list[float | None]) -> float | None:
    sample = [value for value in values if value is not None]
    return None if not sample else 100 * sum(value > 0 for value in sample) / len(sample)


def _ratio01(values: list[float | None]) -> float | None:
    score = _positive_ratio(values)
    return None if score is None else score / 100


def _payout_score(value: float | None) -> float | None:
    if value is None or value < 0:
        return None
    if 20 <= value <= 70:
        return 100.0
    if value < 20:
        return _scale(value, 0, 20)
    return _inverse_scale(value, 70, 120)


def _audit_score(value: float | None) -> float | None:
    if value is None:
        return None
    return {0: 0.0, 1: 100.0, 2: 60.0, 3: 20.0, 4: 0.0, 5: 0.0}.get(
        int(value), 0.0
    )


def _audit_label(value: float | None) -> str | None:
    if value is None:
        return None
    return AUDIT_OPINIONS.get(int(value), f"未知枚举 {value:g}")


def _risks(
    latest: sqlite3.Row,
    annual: dict[str, float | None],
    percentiles: dict[str, float | None],
    annual_report: dict[str, Any] | None,
) -> tuple[list[str], list[str]]:
    risks: list[str] = []
    warnings: list[str] = []
    if annual_report is None:
        risks.append("缺少截至分析日已公告的年报，质量判断不足")
    audit = _number(annual.get("audit_opinion"))
    if audit is not None and audit != 1:
        risks.append(f"审计意见为{_audit_label(audit)}（代码 {audit:g}）")
    debt = _number(annual.get("debt_to_assets"))
    if debt is not None and debt > 75:
        risks.append(f"资产负债率较高（{debt:.1f}%）")
    cash = _number(annual.get("cash_conversion"))
    if cash is not None and cash < 50:
        risks.append(f"经营现金对利润支撑偏弱（{cash:.1f}%）")
    if _number(latest["pe_ttm"]) is None:
        risks.append("TTM PE 不可计算，可能存在亏损或数据缺口")
    for label, key in (("PE", "pe_ttm"), ("PB", "pb")):
        percentile = percentiles[key]
        if percentile is not None and percentile >= 0.80:
            risks.append(f"{label} 位于自身近年较高分位（{percentile:.0%}）")
    for label, key in (("营收", "revenue_growth"), ("净利润", "net_profit_growth")):
        value = _number(annual.get(key))
        if value is not None and value < 0:
            risks.append(f"最近年报{label}同比下降（{value:.1f}%）")
    drawdown = _number(latest["max_drawdown_252d"])
    if drawdown is not None and drawdown < -0.40:
        risks.append(f"近 252 日最大回撤较大（{drawdown:.1%}）")
    if latest["factor_flags"]:
        warnings.append(f"因子标记：{latest['factor_flags']}")
    if annual_report and date.fromisoformat(str(latest["trade_date"])) - date.fromisoformat(
        annual_report["report_date"]
    ) > timedelta(days=550):
        warnings.append("最近可用年报距价格日超过 550 天")
    if annual.get("audit_opinion") is None:
        warnings.append("缺少审计意见代码")
    return risks, warnings


def _strengths(*dimensions: DimensionScore) -> list[str]:
    labels = ("估值", "盈利质量", "成长", "安全性", "股东回报")
    return [
        f"{label}维度较强（{dimension.score:.1f}）"
        for label, dimension in zip(labels, dimensions, strict=True)
        if dimension.score is not None and dimension.score >= 75
    ]


def _conclusion(score: float | None, risks: list[str]) -> str:
    if score is None:
        return "数据不足"
    if any(
        risk.startswith("缺少截至分析日已公告的年报")
        or risk.startswith("审计意见为未审计")
        or any(risk.startswith(f"审计意见为{AUDIT_OPINIONS[code]}") for code in (3, 4, 5))
        for risk in risks
    ):
        return "需先排除关键风险"
    if score >= 75:
        return "重点研究"
    if score >= 60:
        return "可关注"
    if score >= 45:
        return "观察"
    return "暂不优先"


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _absolute(value: float | None) -> float | None:
    return None if value is None else abs(value)
