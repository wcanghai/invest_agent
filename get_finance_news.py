"""获取新浪财经和东方财富的当日财经快讯。

数据通过 AKShare 的公开资讯接口获取。默认保存到：
data/news/finance_news_YYYY-MM-DD.csv
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

import pandas as pd


OUTPUT_COLUMNS = ["来源", "发布时间", "标题", "摘要", "正文", "链接"]
SOURCE_NAMES = {
    "sina": "新浪财经",
    "eastmoney": "东方财富",
}


def parse_date(value: str) -> date:
    """解析 YYYY-MM-DD 日期参数。"""
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("日期格式必须是 YYYY-MM-DD") from exc


def title_from_sina_content(content: object) -> str:
    """从新浪快讯正文中提取标题；无显式标题时生成短标题。"""
    text = str(content).strip()
    match = re.match(r"^[〖【](.*?)[〗】]", text)
    if match:
        return match.group(1).strip()
    return text if len(text) <= 60 else f"{text[:60].rstrip()}…"


def normalize_sina(frame: pd.DataFrame) -> pd.DataFrame:
    """将 AKShare 新浪快讯结果转换为统一字段。"""
    required = {"时间", "内容"}
    if not required.issubset(frame.columns):
        raise ValueError(f"新浪财经返回字段异常：{list(frame.columns)}")

    result = pd.DataFrame()
    result["来源"] = pd.Series([SOURCE_NAMES["sina"]] * len(frame), index=frame.index)
    result["发布时间"] = pd.to_datetime(frame["时间"], errors="coerce")
    result["标题"] = frame["内容"].map(title_from_sina_content)
    result["摘要"] = frame["内容"].astype(str).str.strip()
    result["正文"] = result["摘要"]
    result["链接"] = "https://finance.sina.com.cn/7x24/"
    return result[OUTPUT_COLUMNS]


def normalize_eastmoney(frame: pd.DataFrame) -> pd.DataFrame:
    """将 AKShare 东方财富快讯结果转换为统一字段。"""
    required = {"标题", "摘要", "发布时间", "链接"}
    if not required.issubset(frame.columns):
        raise ValueError(f"东方财富返回字段异常：{list(frame.columns)}")

    result = pd.DataFrame()
    result["来源"] = pd.Series(
        [SOURCE_NAMES["eastmoney"]] * len(frame), index=frame.index
    )
    result["发布时间"] = pd.to_datetime(frame["发布时间"], errors="coerce")
    result["标题"] = frame["标题"].fillna("").astype(str).str.strip()
    result["摘要"] = frame["摘要"].fillna("").astype(str).str.strip()
    result["正文"] = result["摘要"]
    result["链接"] = frame["链接"].fillna("").astype(str).str.strip()
    return result[OUTPUT_COLUMNS]


def fetch_sources(
    sources: list[str],
    fetchers: dict[str, Callable[[], pd.DataFrame]] | None = None,
) -> tuple[pd.DataFrame, dict[str, str]]:
    """抓取多个来源；单个来源失败时继续返回其他来源的数据。"""
    if fetchers is None:
        try:
            import akshare as ak
        except ImportError as exc:
            raise RuntimeError(
                "缺少 AKShare，请先运行：python -m pip install akshare"
            ) from exc
        fetchers = {
            "sina": ak.stock_info_global_sina,
            "eastmoney": ak.stock_info_global_em,
        }

    normalizers = {
        "sina": normalize_sina,
        "eastmoney": normalize_eastmoney,
    }
    frames: list[pd.DataFrame] = []
    errors: dict[str, str] = {}

    for source in sources:
        try:
            frames.append(normalizers[source](fetchers[source]()))
        except Exception as exc:  # 网络和上游字段错误都按来源隔离
            errors[SOURCE_NAMES[source]] = str(exc)

    if not frames:
        detail = "；".join(f"{name}: {message}" for name, message in errors.items())
        raise RuntimeError(f"所有新闻来源均获取失败。{detail}")
    return pd.concat(frames, ignore_index=True), errors


def select_news_for_date(frame: pd.DataFrame, target_date: date) -> pd.DataFrame:
    """筛选目标日期、清理空记录并去重。"""
    result = frame.copy()
    result = result[result["发布时间"].notna()]
    result = result[result["发布时间"].dt.date == target_date]
    result = result[result["标题"].astype(str).str.strip().ne("")]
    result = result.drop_duplicates(subset=["来源", "发布时间", "标题"])
    return result.sort_values("发布时间", ascending=False).reset_index(drop=True)


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
        "--output",
        type=Path,
        help="CSV 输出路径；默认保存到 data/news/finance_news_YYYY-MM-DD.csv",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    output = args.output or Path(
        f"data/news/finance_news_{args.date:%Y-%m-%d}.csv"
    )

    try:
        raw_news, errors = fetch_sources(args.sources)
        news = select_news_for_date(raw_news, args.date)
    except RuntimeError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    output.parent.mkdir(parents=True, exist_ok=True)
    news.to_csv(output, index=False, encoding="utf-8-sig", date_format="%Y-%m-%d %H:%M:%S")

    print(f"已保存 {len(news)} 条 {args.date:%Y-%m-%d} 财经新闻：{output.resolve()}")
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


if __name__ == "__main__":
    raise SystemExit(main())
