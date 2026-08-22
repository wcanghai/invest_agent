"""通达信日线数据源适配器。"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from tdx_history.config import Instrument, UniverseSpec


FIELDS = ("Open", "High", "Low", "Close", "Volume", "Amount")
BAR_COLUMNS = ("trade_date", "open", "high", "low", "close", "volume", "amount")


class TdxDailySource:
    """在单个 TQ 会话中逐只读取日线。"""

    def __init__(self, user_dir: Path, caller_file: Path, tq: Any | None = None):
        self.user_dir = user_dir
        self.caller_file = caller_file
        self.tq = tq
        self._connected = False

    def __enter__(self) -> "TdxDailySource":
        if self.tq is None:
            if not self.user_dir.is_dir():
                raise FileNotFoundError(f"未找到通达信 Python 插件目录：{self.user_dir}")
            user_dir_text = str(self.user_dir)
            if user_dir_text not in sys.path:
                sys.path.insert(0, user_dir_text)
            from tqcenter import tq  # pylint: disable=import-outside-toplevel

            self.tq = tq
        self.tq.initialize(str(self.caller_file))
        self._connected = True
        return self

    def __exit__(self, *_: object) -> None:
        if self._connected:
            self.tq.close()
            self._connected = False

    def list_instruments(self, universe: UniverseSpec) -> tuple[Instrument, ...]:
        """读取一个通达信证券集合的代码和名称。"""
        if not self._connected:
            raise RuntimeError("通达信数据源尚未连接。")
        payload = self.tq.get_stock_list(universe.market, list_type=1)
        if not isinstance(payload, list) or not payload:
            raise RuntimeError(f"通达信证券集合 {universe.market} 返回空列表或非列表。")

        instruments: list[Instrument] = []
        seen: set[str] = set()
        for index, item in enumerate(payload):
            if not isinstance(item, dict):
                raise RuntimeError(f"证券集合 {universe.market} 第 {index + 1} 项不是对象。")
            code = item.get("Code")
            name = item.get("Name")
            if not isinstance(code, str) or not code.strip():
                raise RuntimeError(f"证券集合 {universe.market} 第 {index + 1} 项缺少 Code。")
            if not isinstance(name, str) or not name.strip():
                raise RuntimeError(f"证券集合 {universe.market} 中 {code} 缺少 Name。")
            normalized_code = code.strip().upper()
            if normalized_code in seen:
                continue
            seen.add(normalized_code)
            instruments.append(
                Instrument(
                    normalized_code,
                    name.strip(),
                    universe.kind,
                    universe.dividend_type,
                )
            )
        return tuple(instruments)

    def fetch_daily(
        self,
        code: str,
        start: date,
        end: date,
        dividend_type: str,
    ) -> pd.DataFrame:
        """获取闭区间内的真实日线，不填充停牌缺口。"""
        if not self._connected:
            raise RuntimeError("通达信数据源尚未连接。")
        payload = self.tq.get_market_data(
            field_list=list(FIELDS),
            stock_list=[code],
            start_time=start.strftime("%Y%m%d"),
            end_time=end.strftime("%Y%m%d"),
            count=-1,
            dividend_type=dividend_type,
            period="1d",
            fill_data=False,
        )
        if not payload:
            return pd.DataFrame(columns=BAR_COLUMNS)
        if "Close" not in payload:
            raise RuntimeError(f"通达信未返回 {code} 的收盘价字段。")
        missing = [field for field in FIELDS if field not in payload]
        if missing:
            raise RuntimeError(f"通达信返回 {code} 时缺少字段：{missing}")

        close = _series(payload["Close"], code).dropna()
        if close.empty:
            return pd.DataFrame(columns=BAR_COLUMNS)
        result = pd.DataFrame(index=close.index)
        result["trade_date"] = close.index.strftime("%Y-%m-%d")
        for source_name, target_name in (
            ("Open", "open"),
            ("High", "high"),
            ("Low", "low"),
            ("Close", "close"),
            ("Volume", "volume"),
            ("Amount", "amount"),
        ):
            result[target_name] = pd.to_numeric(
                _series(payload[source_name], code).reindex(close.index), errors="coerce"
            ).to_numpy()
        return result.reset_index(drop=True)

    def average_amounts(
        self,
        codes: Sequence[str],
        start: date,
        end: date,
        chunk_size: int = 100,
    ) -> dict[str, float]:
        """分批计算指定区间内有成交 ETF 的日均成交额。"""
        if not self._connected:
            raise RuntimeError("通达信数据源尚未连接。")
        if chunk_size <= 0:
            raise ValueError("chunk_size 必须大于 0。")

        averages: dict[str, float] = {}
        normalized = tuple(dict.fromkeys(code.strip().upper() for code in codes if code.strip()))
        for offset in range(0, len(normalized), chunk_size):
            chunk = normalized[offset : offset + chunk_size]
            payload = self.tq.get_market_data(
                field_list=["Amount"],
                stock_list=list(chunk),
                start_time=start.strftime("%Y%m%d"),
                end_time=end.strftime("%Y%m%d"),
                count=-1,
                dividend_type="none",
                period="1d",
                fill_data=False,
            )
            if not payload:
                continue
            if "Amount" not in payload or not isinstance(payload["Amount"], pd.DataFrame):
                raise RuntimeError("通达信未返回可识别的 ETF 成交额数据。")
            amount_frame = payload["Amount"]
            for code in chunk:
                if code not in amount_frame.columns:
                    continue
                values = pd.to_numeric(amount_frame[code], errors="coerce")
                positive = values[values > 0].dropna()
                if not positive.empty:
                    averages[code] = float(positive.mean())
        return averages


def _series(frame: pd.DataFrame, code: str) -> pd.Series:
    if code not in frame.columns:
        raise RuntimeError(f"通达信返回结果中缺少证券列：{code}")
    return frame[code]
