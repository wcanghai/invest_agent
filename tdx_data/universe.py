"""构建指数成分股与高流动性 ETF 的定向归档清单。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import akshare as ak
import pandas as pd


IndexFetcher = Callable[[str], pd.DataFrame]
EtfFetcher = Callable[[], pd.DataFrame]


@dataclass(frozen=True)
class TargetAsset:
    code: str
    name: str
    groups: tuple[str, ...]
    liquidity_rank: int | None = None
    latest_amount: float | None = None

    def to_archive_row(self) -> dict[str, object]:
        return {
            "Code": self.code,
            "Name": self.name,
            "Groups": list(self.groups),
            "LiquidityRank": self.liquidity_rank,
            "LatestAmount": self.latest_amount,
        }


def fetch_target_universe(
    etf_limit: int = 120,
    *,
    index_fetcher: IndexFetcher = ak.index_stock_cons_csindex,
    etf_fetcher: EtfFetcher = ak.fund_etf_spot_em,
) -> list[TargetAsset]:
    """获取沪深300、中证500和按最近成交额排序的 ETF 清单。"""
    if etf_limit <= 100:
        raise ValueError("etf_limit 必须大于 100。")
    assets: dict[str, TargetAsset] = {}
    for symbol, group in (("000300", "沪深300"), ("000905", "中证500")):
        frame = index_fetcher(symbol)
        if frame.empty or len(frame.columns) < 9:
            raise RuntimeError(f"{group} 成分接口没有返回有效数据。")
        for row in frame.itertuples(index=False, name=None):
            code = _stock_code(row[4], row[8])
            _merge_asset(assets, code, str(row[5]).strip() or code, group)

    etf_frame = etf_fetcher()
    if etf_frame.empty or len(etf_frame.columns) < 9:
        raise RuntimeError("ETF 行情接口没有返回有效数据。")
    ranked = etf_frame.iloc[:, [0, 1, 8]].copy()
    ranked.columns = ["code", "name", "amount"]
    ranked["amount"] = pd.to_numeric(ranked["amount"], errors="coerce")
    ranked = ranked.dropna(subset=["amount"]).sort_values("amount", ascending=False)
    if len(ranked) < etf_limit:
        raise RuntimeError(f"有效 ETF 只有 {len(ranked)} 只，少于要求的 {etf_limit} 只。")
    for rank, row in enumerate(ranked.head(etf_limit).itertuples(index=False), 1):
        code = _fund_code(row.code)
        assets[code] = TargetAsset(
            code=code,
            name=str(row.name).strip() or code,
            groups=("高流动性ETF",),
            liquidity_rank=rank,
            latest_amount=float(row.amount),
        )
    return sorted(assets.values(), key=lambda item: (item.groups[-1], item.code))


def group_counts(assets: list[TargetAsset]) -> dict[str, int]:
    return {
        group: sum(group in asset.groups for asset in assets)
        for group in ("沪深300", "中证500", "高流动性ETF")
    }


def _merge_asset(
    assets: dict[str, TargetAsset], code: str, name: str, group: str
) -> None:
    existing = assets.get(code)
    groups = tuple(dict.fromkeys((*existing.groups, group))) if existing else (group,)
    assets[code] = TargetAsset(code=code, name=name, groups=groups)


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
