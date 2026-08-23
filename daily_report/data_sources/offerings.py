"""新股、新债申购与上市事件采集。"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from tdx_data.client import tdx_session


Offering = dict[str, Any]
TdxFetcher = Callable[[], list[Offering]]
FrameFetcher = Callable[[], pd.DataFrame]


def fetch_tdx_offerings(caller_file: Path) -> list[Offering]:
    """从通达信读取今天及未来的新股、新债申购信息。"""
    with tdx_session(caller_file) as tq:
        stocks = normalize_tdx_offerings(tq.get_ipo_info(ipo_type=0, ipo_date=1), "新股")
        bonds = normalize_tdx_offerings(tq.get_ipo_info(ipo_type=1, ipo_date=1), "新债")
        return stocks + bonds


def fetch_public_stock_offerings() -> pd.DataFrame:
    """从公开聚合接口读取新股申购、中签和上市信息。"""
    import akshare as ak  # pylint: disable=import-outside-toplevel

    return ak.stock_xgsglb_em(symbol="全部股票")


def fetch_public_bond_offerings() -> pd.DataFrame:
    """从公开聚合接口读取可转债申购和上市信息。"""
    import akshare as ak  # pylint: disable=import-outside-toplevel

    return ak.bond_zh_cov()


def collect_offerings(
    caller_file: Path,
    as_of: date,
    *,
    tdx_fetcher: TdxFetcher | None = None,
    stock_fetcher: FrameFetcher | None = None,
    bond_fetcher: FrameFetcher | None = None,
    forward_days: int = 14,
    listing_lookback_days: int = 3,
) -> tuple[list[Offering], list[str]]:
    """聚合多来源发行事件；单一来源失败不阻断日报。"""
    if forward_days < 0 or listing_lookback_days < 0:
        raise ValueError("发行日历观察窗口不能为负数。")

    tdx_fetcher = tdx_fetcher or (lambda: fetch_tdx_offerings(caller_file))
    stock_fetcher = stock_fetcher or fetch_public_stock_offerings
    bond_fetcher = bond_fetcher or fetch_public_bond_offerings

    collected: list[Offering] = []
    warnings: list[str] = []
    try:
        collected.extend(tdx_fetcher())
    except Exception as error:  # 实时发行数据属于补充信息，失败不阻断主报告。
        warnings.append(f"通达信新股新债日历：获取失败（{error}）。")

    try:
        collected.extend(normalize_public_stock_offerings(stock_fetcher()))
    except Exception as error:
        warnings.append(f"公开新股发行数据：获取失败（{error}）。")

    try:
        collected.extend(normalize_public_bond_offerings(bond_fetcher()))
    except Exception as error:
        warnings.append(f"公开可转债发行数据：获取失败（{error}）。")

    merged = merge_offerings(collected)
    window_end = as_of + timedelta(days=forward_days)
    listing_start = as_of - timedelta(days=listing_lookback_days)
    relevant = [
        item
        for item in merged
        if _in_window(item.get("subscription_date"), as_of, window_end)
        or _in_window(item.get("listing_date"), listing_start, window_end)
    ]
    for item in relevant:
        item["event_status"] = _event_status(item, as_of, listing_start, window_end)
    return sorted(relevant, key=lambda item: _sort_key(item, as_of, window_end)), warnings


def normalize_tdx_offerings(records: Iterable[Mapping[str, Any]], kind: str) -> list[Offering]:
    """将通达信申购字段归一化。"""
    if kind not in {"新股", "新债"}:
        raise ValueError(f"不支持的发行类型：{kind}")
    result: list[Offering] = []
    for record in records:
        subscription_code = _text(record.get("SGCode")) or _text(record.get("Code"))
        if not subscription_code:
            continue
        result.append(
            _offering(
                kind=kind,
                name=_text(record.get("Name")),
                subscription_code=subscription_code,
                security_code=_text(record.get("Code")),
                subscription_date=_date_text(record.get("SGDate")),
                issue_price=_positive_number(record.get("SGPrice")),
                max_subscription=_positive_number(record.get("MaxSG")),
                max_subscription_unit="万股" if kind == "新股" else "万元",
                issue_pe=_positive_number(record.get("PE_Issue")) if kind == "新股" else None,
                sources=["通达信"],
            )
        )
    return result


def normalize_public_stock_offerings(frame: pd.DataFrame) -> list[Offering]:
    """将公开新股申购表归一化。"""
    result: list[Offering] = []
    for record in frame.to_dict(orient="records"):
        subscription_code = _text(record.get("申购代码")) or _text(record.get("股票代码"))
        if not subscription_code:
            continue
        result.append(
            _offering(
                kind="新股",
                name=_text(record.get("股票简称")),
                subscription_code=subscription_code,
                security_code=_text(record.get("股票代码")),
                subscription_date=_date_text(record.get("申购日期")),
                issue_price=_positive_number(record.get("发行价格")),
                max_subscription=_scaled_positive_number(record.get("申购上限"), 10_000),
                max_subscription_unit="万股",
                issue_pe=_positive_number(record.get("发行市盈率")),
                winning_rate=_nonnegative_number(record.get("中签率")),
                listing_date=_date_text(record.get("上市日期")),
                sources=["东方财富"],
            )
        )
    return result


def normalize_public_bond_offerings(frame: pd.DataFrame) -> list[Offering]:
    """将公开可转债发行表归一化。"""
    result: list[Offering] = []
    for record in frame.to_dict(orient="records"):
        subscription_code = _text(record.get("申购代码")) or _text(record.get("债券代码"))
        if not subscription_code:
            continue
        result.append(
            _offering(
                kind="新债",
                name=_text(record.get("债券简称")),
                subscription_code=subscription_code,
                security_code=_text(record.get("债券代码")),
                subscription_date=_date_text(record.get("申购日期")),
                max_subscription=_positive_number(record.get("申购上限")),
                max_subscription_unit="万元",
                winning_rate=_nonnegative_number(record.get("中签率")),
                listing_date=_date_text(record.get("上市时间")),
                underlying_code=_text(record.get("正股代码")),
                underlying_name=_text(record.get("正股简称")),
                issue_size=_positive_number(record.get("发行规模")),
                rating=_text(record.get("信用评级")),
                sources=["东方财富"],
            )
        )
    return result


def merge_offerings(records: Iterable[Offering]) -> list[Offering]:
    """按发行类型和申购代码去重，并用后续来源补全空字段。"""
    merged: dict[tuple[str, str], Offering] = {}
    for record in records:
        kind = _text(record.get("kind"))
        subscription_code = _text(record.get("subscription_code"))
        if not kind or not subscription_code:
            continue
        key = (kind, subscription_code)
        current = merged.get(key)
        if current is None:
            merged[key] = {**record, "sources": list(record.get("sources", []))}
            continue
        for field, value in record.items():
            if field == "sources":
                current["sources"] = list(
                    dict.fromkeys([*current.get("sources", []), *record.get("sources", [])])
                )
            elif _missing(current.get(field)) and not _missing(value):
                current[field] = value
    return list(merged.values())


def _offering(**values: Any) -> Offering:
    fields = (
        "kind",
        "name",
        "subscription_code",
        "security_code",
        "subscription_date",
        "issue_price",
        "max_subscription",
        "max_subscription_unit",
        "issue_pe",
        "winning_rate",
        "listing_date",
        "underlying_code",
        "underlying_name",
        "issue_size",
        "rating",
        "sources",
        "event_status",
    )
    return {field: values.get(field) for field in fields}


def _date_text(value: Any) -> str | None:
    text = _text(value)
    if not text:
        return None
    try:
        parsed = pd.to_datetime(text, errors="raise")
    except (TypeError, ValueError):
        return None
    return parsed.date().isoformat()


def _text(value: Any) -> str | None:
    if _missing(value):
        return None
    text = str(value).strip()
    if text.lower() in {"", "-", "--", "nan", "nat", "none"}:
        return None
    return text


def _positive_number(value: Any) -> float | None:
    number = _number(value)
    return number if number is not None and number > 0 else None


def _scaled_positive_number(value: Any, divisor: float) -> float | None:
    number = _positive_number(value)
    return number / divisor if number is not None else None


def _nonnegative_number(value: Any) -> float | None:
    number = _number(value)
    return number if number is not None and number >= 0 else None


def _number(value: Any) -> float | None:
    if _missing(value):
        return None
    try:
        number = float(str(value).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _in_window(value: Any, start: date, end: date) -> bool:
    text = _text(value)
    if not text:
        return False
    try:
        event_date = date.fromisoformat(text)
    except ValueError:
        return False
    return start <= event_date <= end


def _event_status(item: Offering, as_of: date, listing_start: date, window_end: date) -> str:
    labels: list[str] = []
    subscription_date = _iso_date(item.get("subscription_date"))
    listing_date = _iso_date(item.get("listing_date"))
    if subscription_date == as_of:
        labels.append("今日申购")
    elif subscription_date is not None and as_of < subscription_date <= window_end:
        labels.append("待申购")
    if listing_date == as_of:
        labels.append("今日上市")
    elif listing_date is not None and listing_start <= listing_date < as_of:
        labels.append("近期上市")
    elif listing_date is not None and as_of < listing_date <= window_end:
        labels.append("待上市")
    return "、".join(labels) or "窗口内事件"


def _sort_key(item: Offering, as_of: date, window_end: date) -> tuple[str, str, str]:
    subscription_date = _iso_date(item.get("subscription_date"))
    if subscription_date is not None and as_of <= subscription_date <= window_end:
        event_date = subscription_date.isoformat()
    else:
        event_date = item.get("listing_date") or "9999-12-31"
    return str(event_date), str(item.get("kind") or ""), str(item.get("subscription_code") or "")


def _iso_date(value: Any) -> date | None:
    text = _text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None
