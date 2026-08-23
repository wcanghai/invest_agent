"""财经新闻采集命令入口。"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

from daily_report.data_sources.news import SOURCE_NAMES, fetch_sources, select_news_for_date
from daily_report.storage.news_repository import NewsRepository
from daily_report.storage.sync_repository import SyncRunRepository


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_date(value: str) -> date:
    """解析 YYYY-MM-DD 日期参数。"""
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("日期格式必须是 YYYY-MM-DD") from exc


def parse_arguments() -> argparse.Namespace:
    today = date.today()
    parser = argparse.ArgumentParser(description="获取新浪财经和东方财富当日财经快讯")
    parser.add_argument(
        "--date",
        type=parse_date,
        default=today,
        help=f"目标日期，格式 YYYY-MM-DD（默认：{today:%Y-%m-%d}）",
    )
    parser.add_argument(
        "--sources",
        nargs="+",
        choices=sorted(SOURCE_NAMES),
        default=list(SOURCE_NAMES),
        help="新闻来源（默认：sina eastmoney）",
    )
    parser.add_argument(
        "--database", type=Path,
        default=PROJECT_ROOT / "data" / "daily_report.sqlite3",
        help="日报 SQLite 路径",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    try:
        raw_news, errors = fetch_sources(args.sources)
        news = select_news_for_date(raw_news, args.date)
    except RuntimeError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    repository = NewsRepository(args.database)
    run_repository = SyncRunRepository(args.database)
    run_id = run_repository.start("finance_news")
    try:
        written_rows = repository.upsert(news)
    except Exception as error:
        run_repository.fail(run_id, error)
        raise
    run_repository.finish(run_id, written_rows)
    print(f"已保存 {len(news)} 条 {args.date:%Y-%m-%d} 财经新闻：{args.database.resolve()}")
    if not news.empty:
        counts = news.groupby("来源").size()
        print("来源统计：" + "，".join(f"{name} {count} 条" for name, count in counts.items()))
        print("\n最新新闻：")
        for row in news.head(10).itertuples(index=False):
            print(f"- {row.发布时间:%H:%M:%S} [{row.来源}] {row.标题}")
    else:
        print("目标日期没有匹配的新闻；免费接口只提供有限数量的最近快讯。")

    for source, message in errors.items():
        print(f"警告：{source} 获取失败：{message}", file=sys.stderr)
    return 0
