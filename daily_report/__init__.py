"""可配置的多市场日报工具。"""

from daily_report.models import MarketReportSnapshot
from daily_report.service import generate_market_report

__all__ = ["MarketReportSnapshot", "generate_market_report"]
