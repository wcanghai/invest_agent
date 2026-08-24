"""第一部分：通达信接口层。只负责 TDX 连接、只读接口和字段注释。"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_TDX_USER_DIR = Path(r"D:\SoftWare\TDX\PYPlugins\user")


# TQ 日线仅接受行情字段；交易日期由返回 DataFrame 索引补齐。
DAILY_FIELDS = (
    "Open", "High", "Low", "Close", "Volume", "Amount",
)
FINANCIAL_FIELDS = tuple(f"Fn{number}" for number in range(193, 201))
GP_FIELDS = ("GP1", "GP2", "GP3", "GP4", "GP5")
GO_FIELDS = ("GO1", "GO2", "GO3", "GO4", "GO47")
API_FIELD_COMMENTS = {
    "Code": "证券代码", "Name": "证券名称", "Date": "交易日期", "Time": "交易时间",
    "Open": "开盘价", "High": "最高价", "Low": "最低价", "Close": "收盘价",
    "Volume": "成交量", "Amount": "成交额", "ForwardFactor": "前复权因子",
    "VolInStock": "持仓量", "BelongHS300": "是否属于沪深300", "IsSTGP": "是否为ST股票",
    "HSStockKind": "沪深京品种类型", "J_zgb": "总股本", "J_zzc": "总资产",
    "J_jly": "净利润", "J_jyl": "净资产收益率", "tdx_dyname": "通达信地域",
    "rs_hyname": "通达信行业", "MainBusiness": "主营构成", "TPFlag": "停牌标识",
    "ZAF": "涨幅", "DynaPE": "动态市盈率", "StaticPE_TTM": "市盈率(TTM)",
    "PB_MRQ": "市净率(MRQ)", "DYRatio": "股息率", "Zsz": "总市值(亿)",
    "Ltsz": "流通市值(亿)", "StaffNum": "员工人数",
}


class TdxClient:
    """tqcenter.py 的只读接口封装，不包含交易或客户端写操作。"""

    def __init__(self, user_dir: Path, caller_file: Path):
        self.user_dir, self.caller_file, self.tq = user_dir, caller_file, None

    def connect(self) -> None:
        """加载 user 目录中的 tqcenter 并初始化 DLL。"""
        self.tq = load_tq(self.user_dir)
        self.tq.initialize(str(self.caller_file))

    def close(self) -> None:
        """关闭 DLL 会话。"""
        if self.tq is not None:
            self.tq.close()
            self.tq = None

    def list_stocks(self, market: str) -> list[dict[str, Any]]:
        """获取证券列表，list_type=1 表示可交易标的。"""
        return self._api().get_stock_list(market, list_type=1) or []

    def daily(self, code: str, start: date, end: date) -> list[dict[str, Any]]:
        """获取指定代码的 1 日线，fill_data=False 不填充停牌日。"""
        payload = self._api().get_market_data(
            field_list=list(DAILY_FIELDS), stock_list=[code], period="1d",
            start_time=start.strftime("%Y%m%d"), end_time=end.strftime("%Y%m%d"),
            count=-1, dividend_type="none", fill_data=False,
        ) or {}
        return daily_rows(payload, code)

    def stock_info(self, code: str) -> dict[str, Any]:
        """获取基础资料；空 field_list 保留全部接口字段。"""
        return self._api().get_stock_info(stock_code=code, field_list=[]) or {}

    def more_info(self, code: str) -> dict[str, Any]:
        """获取扩展行情、估值、资金和事件字段。"""
        return self._api().get_more_info(stock_code=code, field_list=[]) or {}

    def relations(self, code: str) -> list[dict[str, Any]]:
        """获取行业、地域、概念和指数板块关系。"""
        value = self._api().get_relation(stock_code=code)
        return value if isinstance(value, list) else []

    def financial_history(self, code: str, start: date, end: date) -> Any:
        """按公告日获取历史财务记录，同时保留返回中的报告期。"""
        return self._api().get_financial_data(
            stock_list=[code],
            field_list=list(FINANCIAL_FIELDS),
            start_time=start.strftime("%Y%m%d"),
            end_time=end.strftime("%Y%m%d"),
            report_type="announce_time",
        ) or {}

    def share_capital_history(self, code: str, start: date, end: date) -> Any:
        """按日期区间获取流通股本和总股本历史。"""
        return self._api().get_gb_info_by_date(
            stock_code=code,
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
        ) or {}

    def corporate_actions(self, code: str, start: date, end: date) -> Any:
        """获取日期区间内的分红送配和除权记录。"""
        return self._api().get_divid_factors(
            stock_code=code,
            start_time=start.strftime("%Y%m%d"),
            end_time=end.strftime("%Y%m%d"),
        )

    def market_snapshot(self, code: str) -> Any:
        """获取当前或最近市场快照的全部可用字段。"""
        return self._api().get_market_snapshot(stock_code=code, field_list=[]) or {}

    def gp_trading(self, code: str, start: date, end: date) -> Any:
        """获取 GP1-GP5 交易扩展序列。"""
        return self._api().get_gpjy_value(
            stock_list=[code],
            field_list=list(GP_FIELDS),
            start_time=start.strftime("%Y%m%d"),
            end_time=end.strftime("%Y%m%d"),
        ) or {}

    def gp_single(self, code: str) -> Any:
        """获取 GO1-GO4、GO47 单点动态信息。"""
        return self._api().get_gp_one_data(
            stock_list=[code], field_list=list(GO_FIELDS)
        ) or {}

    def _api(self) -> Any:
        if self.tq is None:
            raise RuntimeError("通达信会话尚未连接。")
        return self.tq


def load_tq(user_dir: Path | None = None) -> Any:
    """加载 TQ 插件；未显式传入路径时读取 ``TDX_USER_DIR``。"""
    resolved = (user_dir or Path(os.getenv("TDX_USER_DIR", str(DEFAULT_TDX_USER_DIR)))).expanduser()
    if not resolved.is_dir():
        raise FileNotFoundError(
            f"未找到通达信 Python 插件目录：{resolved}。请设置 TDX_USER_DIR 或传入路径。"
        )
    text = str(resolved)
    if text not in sys.path:
        sys.path.insert(0, text)
    from tqcenter import tq  # type: ignore  # pylint: disable=import-outside-toplevel

    return tq


@contextmanager
def tdx_session(caller_file: Path, user_dir: Path | None = None):
    """初始化一个只读 TQ 会话并确保关闭。"""
    tq = load_tq(user_dir)
    tq.initialize(str(caller_file.resolve()))
    try:
        yield tq
    finally:
        tq.close()


def daily_rows(payload: Any, code: str) -> list[dict[str, Any]]:
    """把字段->DataFrame 返回转换为按日期排列的字典记录。"""
    if not isinstance(payload, dict):
        return []
    frames = {name: value[code] for name, value in payload.items() if isinstance(value, pd.DataFrame) and code in value.columns}
    if not frames:
        return []
    frame = pd.DataFrame(frames)
    frame.insert(0, "Date", frame.index)
    return [{str(k): json_value(v) for k, v in row.items()} for row in frame.reset_index(drop=True).to_dict(orient="records")]


def json_value(value: Any) -> Any:
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
