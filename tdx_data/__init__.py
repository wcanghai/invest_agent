"""通达信股票数据只读采集与本地归档工具。"""

from tdx_data.client import TdxClient
from tdx_data.history_service import (
    calculate_historical_pb,
    financial_report_as_of,
    historical_metric_inputs,
    share_capital_as_of,
)
from tdx_data.quant_wide_service import QuantWideBuildResult, build_quant_daily_wide

__all__ = [
    "TdxClient",
    "QuantWideBuildResult",
    "build_quant_daily_wide",
    "calculate_historical_pb",
    "financial_report_as_of",
    "historical_metric_inputs",
    "share_capital_as_of",
]
