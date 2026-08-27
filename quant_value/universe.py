"""构建沪深300、中证500与高流动性 ETF 研究池。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Callable

import akshare as ak
import pandas as pd

from quant_value.config import Instrument


IndexFetcher = Callable[[str], pd.DataFrame]
EtfFetcher = Callable[[], pd.DataFrame]


@dataclass(frozen=True)
class Membership:
    code: str
    group_name: str
    selected_date: date
    liquidity_rank: int | None = None
    latest_amount: float | None = None


@dataclass(frozen=True)
class UniverseSelection:
    instruments: tuple[Instrument, ...]
    memberships: tuple[Membership, ...]


def fetch_target_universe(
    etf_limit: int = 120,
    *,
    selected_date: date | None = None,
    index_fetcher: IndexFetcher = ak.index_stock_cons_csindex,
    etf_fetcher: EtfFetcher = ak.fund_etf_spot_em,
) -> UniverseSelection:
    """获取当前指数成分与按最近成交额排序的 ETF，行情仍由 TDX 获取。"""
    if etf_limit <= 100:
        raise ValueError("etf_limit 必须大于 100。")
    observed = selected_date or date.today()
    instruments: dict[str, Instrument] = {}
    memberships: list[Membership] = []
    for symbol, group in (("000300", "沪深300"), ("000905", "中证500")):
        frame = index_fetcher(symbol)
        if frame.empty or len(frame.columns) < 9:
            raise RuntimeError(f"{group} 成分接口没有返回有效数据。")
        for row in frame.itertuples(index=False, name=None):
            code = _stock_code(row[4], row[8])
            name = str(row[5]).strip() or code
            existing = instruments.get(code)
            category = f"{existing.category},{group}" if existing else group
            instruments[code] = Instrument(code, name, "stock", category)
            memberships.append(Membership(code, group, observed))

    frame = etf_fetcher()
    if frame.empty or len(frame.columns) < 9:
        raise RuntimeError("ETF 行情接口没有返回有效数据。")
    ranked = frame.iloc[:, [0, 1, 8]].copy()
    ranked.columns = ["code", "name", "amount"]
    ranked["amount"] = pd.to_numeric(ranked["amount"], errors="coerce")
    ranked = ranked.dropna(subset=["amount"]).sort_values("amount", ascending=False)
    if len(ranked) < etf_limit:
        raise RuntimeError(f"有效 ETF 只有 {len(ranked)} 只，少于要求的 {etf_limit} 只。")
    for rank, row in enumerate(ranked.head(etf_limit).itertuples(index=False), 1):
        code = _fund_code(row.code)
        instruments[code] = Instrument(
            code, str(row.name).strip() or code, "etf", "高流动性ETF"
        )
        memberships.append(
            Membership(code, "高流动性ETF", observed, rank, float(row.amount))
        )
    return UniverseSelection(
        tuple(sorted(instruments.values(), key=lambda item: (item.asset_type, item.code))),
        tuple(sorted(memberships, key=lambda item: (item.group_name, item.code))),
    )


def save_selection(selection: UniverseSelection, path: Path) -> None:
    """保存本次动态选池快照，便于复现实验。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "instruments": [asdict(item) for item in selection.instruments],
        "memberships": [
            {**asdict(item), "selected_date": item.selected_date.isoformat()}
            for item in selection.memberships
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def group_counts(selection: UniverseSelection) -> dict[str, int]:
    return {
        group: sum(item.group_name == group for item in selection.memberships)
        for group in ("沪深300", "中证500", "高流动性ETF")
    }


def _stock_code(value: object, exchange: object) -> str:
    code = str(value).strip().zfill(6)
    exchange_text = str(exchange).lower()
    if "shanghai" in exchange_text or "上海" in exchange_text:
        return f"{code}.SH"
    if "shenzhen" in exchange_text or "深圳" in exchange_text:
        return f"{code}.SZ"
    return f"{code}.SH" if code.startswith(("5", "6")) else f"{code}.SZ"


def _fund_code(value: object) -> str:
    code = str(value).strip().zfill(6)
    return f"{code}.SH" if code.startswith("5") else f"{code}.SZ"
