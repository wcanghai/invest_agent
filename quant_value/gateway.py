"""只读通达信 TQ 网关；所有网络/DLL 访问集中在此模块。"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Protocol

import pandas as pd

from quant_value.fields import FINANCIAL_CODES


DEFAULT_TDX_USER_DIR = Path(r"D:\SoftWare\TDX\PYPlugins\user")
MARKET_FIELDS = ("Open", "High", "Low", "Close", "Volume", "Amount", "ForwardFactor")


class ResearchGateway(Protocol):
    def connect(self) -> None: ...
    def close(self) -> None: ...
    def market_bars(self, code: str, start: date, end: date) -> list[dict[str, Any]]: ...
    def financial_reports(self, code: str, start: date, end: date) -> list[dict[str, Any]]: ...
    def share_capital(self, code: str, start: date, end: date) -> list[dict[str, Any]]: ...
    def corporate_actions(self, code: str, start: date, end: date) -> list[dict[str, Any]]: ...
    def snapshot(self, code: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]: ...
    def relations(self, code: str) -> list[dict[str, Any]]: ...
    def etfs_for_benchmark(self, benchmark_code: str) -> list[dict[str, Any]]: ...


class TdxGateway:
    """TQCenter 的研究型只读封装。"""

    def __init__(self, user_dir: Path | None = None, caller_file: Path | None = None):
        self.user_dir = user_dir or Path(os.getenv("TDX_USER_DIR", str(DEFAULT_TDX_USER_DIR)))
        self.caller_file = caller_file or Path(__file__)
        self.tq: Any = None

    def connect(self) -> None:
        if not self.user_dir.is_dir():
            raise FileNotFoundError(f"未找到通达信 TQ 插件目录：{self.user_dir}")
        text = str(self.user_dir.resolve())
        if text not in sys.path:
            sys.path.insert(0, text)
        from tqcenter import tq  # type: ignore  # pylint: disable=import-outside-toplevel

        tq.initialize(str(self.caller_file.resolve()))
        self.tq = tq

    def close(self) -> None:
        if self.tq is not None:
            self.tq.close()
            self.tq = None

    def market_bars(self, code: str, start: date, end: date) -> list[dict[str, Any]]:
        payload = self._api().get_market_data(
            field_list=list(MARKET_FIELDS), stock_list=[code], period="1d",
            start_time=start.strftime("%Y%m%d"), end_time=end.strftime("%Y%m%d"),
            count=-1, dividend_type="none", fill_data=False,
        ) or {}
        if not isinstance(payload, Mapping):
            return []
        frames = {
            field: value[code]
            for field, value in payload.items()
            if isinstance(value, pd.DataFrame) and code in value.columns
        }
        if not frames:
            return []
        frame = pd.DataFrame(frames)
        frame.insert(0, "Date", frame.index)
        return _records(frame)

    def financial_reports(self, code: str, start: date, end: date) -> list[dict[str, Any]]:
        payload = self._api().get_financial_data(
            stock_list=[code], field_list=list(FINANCIAL_CODES),
            start_time=start.strftime("%Y%m%d"), end_time=end.strftime("%Y%m%d"),
            report_type="announce_time",
        ) or {}
        if isinstance(payload, Mapping) and code in payload:
            return _records(payload[code])
        return _records(payload)

    def share_capital(self, code: str, start: date, end: date) -> list[dict[str, Any]]:
        return _records(self._api().get_gb_info_by_date(
            stock_code=code, start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
        ) or {})

    def corporate_actions(self, code: str, start: date, end: date) -> list[dict[str, Any]]:
        return _records(self._api().get_divid_factors(
            stock_code=code, start_time=start.strftime("%Y%m%d"),
            end_time=end.strftime("%Y%m%d"),
        ))

    def snapshot(self, code: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        return (
            _mapping(self._api().get_stock_info(stock_code=code, field_list=[]) or {}),
            _mapping(self._api().get_more_info(stock_code=code, field_list=[]) or {}),
            _mapping(self._api().get_market_snapshot(stock_code=code, field_list=[]) or {}),
        )

    def relations(self, code: str) -> list[dict[str, Any]]:
        return _records(self._api().get_relation(stock_code=code) or [])

    def etfs_for_benchmark(self, benchmark_code: str) -> list[dict[str, Any]]:
        return _records(self._api().get_trackzs_etf_info(zs_code=benchmark_code) or [])

    def _api(self) -> Any:
        if self.tq is None:
            raise RuntimeError("通达信 TQ 会话尚未连接。")
        return self.tq


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    return {}


def _records(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, pd.DataFrame):
        frame = value.copy()
        if not isinstance(frame.index, pd.RangeIndex):
            index_name = str(frame.index.name or "Date")
            if index_name in frame.columns:
                index_name = "IndexDate"
            frame.insert(0, index_name, frame.index)
        return [
            {str(key): _plain(item) for key, item in row.items()}
            for row in frame.reset_index(drop=True).to_dict(orient="records")
        ]
    if isinstance(value, list):
        return [_mapping(item) for item in value if isinstance(item, Mapping)]
    if isinstance(value, Mapping):
        if "Value" in value and isinstance(value["Value"], (list, Mapping, pd.DataFrame)):
            return _records(value["Value"])
        list_values = [item for item in value.values() if isinstance(item, list)]
        if list_values and len(list_values) == len(value) and len({len(item) for item in list_values}) == 1:
            return _records(pd.DataFrame(value))
        return [_mapping(value)]
    return []


def _plain(value: Any) -> Any:
    if isinstance(value, (date, pd.Timestamp)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    try:
        return None if pd.isna(value) else value
    except (TypeError, ValueError):
        return value

