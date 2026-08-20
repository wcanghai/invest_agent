"""通达信日线数据源适配器。"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd


FIELDS = ("Open", "High", "Low", "Close", "Volume", "Amount")


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
        if not payload or "Close" not in payload:
            raise RuntimeError(f"通达信未返回 {code} 的日线数据。")
        missing = [field for field in FIELDS if field not in payload]
        if missing:
            raise RuntimeError(f"通达信返回 {code} 时缺少字段：{missing}")

        close = _series(payload["Close"], code).dropna()
        if close.empty:
            return pd.DataFrame(columns=["trade_date", "open", "high", "low", "close", "volume", "amount"])
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


def _series(frame: pd.DataFrame, code: str) -> pd.Series:
    if code not in frame.columns:
        raise RuntimeError(f"通达信返回结果中缺少证券列：{code}")
    return frame[code]
