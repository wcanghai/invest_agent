from datetime import date

import pandas as pd

from finance_news.service import (
    fetch_sources,
    normalize_eastmoney,
    normalize_sina,
    select_news_for_date,
    title_from_sina_content,
)


def test_title_from_sina_content() -> None:
    assert title_from_sina_content("〖央行发布公告〗公告正文") == "央行发布公告"
    assert title_from_sina_content("普通短讯") == "普通短讯"


def test_normalize_and_select_news_for_date() -> None:
    sina = pd.DataFrame(
        {
            "时间": ["2026-08-20 09:00:00", "2026-08-19 23:59:59"],
            "内容": ["〖新浪标题〗新浪正文", "旧新闻"],
        }
    )
    eastmoney = pd.DataFrame(
        {
            "标题": ["东财标题"],
            "摘要": ["东财摘要"],
            "发布时间": ["2026-08-20 10:00:00"],
            "链接": ["https://example.com/news"],
        }
    )

    combined = pd.concat(
        [normalize_sina(sina), normalize_eastmoney(eastmoney)], ignore_index=True
    )
    selected = select_news_for_date(combined, date(2026, 8, 20))

    assert selected["来源"].tolist() == ["东方财富", "新浪财经"]
    assert selected["标题"].tolist() == ["东财标题", "新浪标题"]


def test_fetch_sources_keeps_success_when_one_source_fails() -> None:
    def fail() -> pd.DataFrame:
        raise ConnectionError("temporary failure")

    fetchers = {
        "sina": lambda: pd.DataFrame(
            {"时间": ["2026-08-20 09:00:00"], "内容": ["一条新闻"]}
        ),
        "eastmoney": fail,
    }

    news, errors = fetch_sources(["sina", "eastmoney"], fetchers)

    assert len(news) == 1
    assert errors == {"东方财富": "temporary failure"}
