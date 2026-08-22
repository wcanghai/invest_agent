"""财经新闻采集与标准化。"""

from finance_news.service import fetch_sources, select_news_for_date

__all__ = ["fetch_sources", "select_news_for_date"]
