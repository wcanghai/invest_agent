"""指定股票、ETF 和基金的十年日线增量同步入口。"""

from __future__ import annotations

import argparse
import logging
from datetime import date, datetime, time, timedelta
from pathlib import Path

from tdx_history import HistoryRepository, HistorySyncService, load_config
from tdx_history.service import SyncResult
from tdx_history.tdx_source import TdxDailySource
from tdx_history.universe import count_by_kind, discover_instruments, select_instruments


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "tdx_history.json"
DEFAULT_DATABASE = PROJECT_ROOT / "data" / "tdx_history.sqlite3"


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="首次回补近十年通达信日线，后续只追加新交易日。"
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="证券配置 JSON")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE, help="SQLite 数据库路径")
    parser.add_argument("--years", type=int, default=10, help="首次回补年数（默认：10）")
    parser.add_argument(
        "--symbols",
        nargs="*",
        help="只同步配置或发现集合中的指定代码。",
    )
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument(
        "--limit-per-kind",
        type=int,
        help="每种证券类型最多同步 N 个（默认：5）。",
    )
    scope.add_argument(
        "--all",
        action="store_true",
        help="同步配置集合中的所有标的；可能需要数小时和数 GB 磁盘。",
    )
    parser.add_argument(
        "--include-today",
        action="store_true",
        help="包含当天日线；默认在工作日 16:30 前只同步到昨日。",
    )
    parser.add_argument("--verbose", action="store_true", help="输出调试日志")
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    config = load_config(args.config.resolve())
    database = args.database.resolve()
    now = datetime.now()
    completed_through = now.date() if args.include_today else _completed_through(now)
    with TdxDailySource(config.tdx_user_dir, Path(__file__).resolve()) as source:
        discovered = discover_instruments(config, source)
        configured_limit = 5 if args.limit_per_kind is None else args.limit_per_kind
        limit = None if args.all or args.symbols else configured_limit
        instruments = select_instruments(
            discovered,
            symbols=set(args.symbols) if args.symbols else None,
            limit_per_kind=limit,
        )
        if not instruments:
            raise ValueError("没有需要同步的证券。")
        print(f"发现标的：{len(discovered)}（{_format_counts(count_by_kind(discovered))}）")
        print(f"本次选中：{len(instruments)}（{_format_counts(count_by_kind(instruments))}）")
        print(f"数据库：{database}")
        print(f"本次同步截止日：{completed_through}")
        print("进度       代码          状态              接收    新增    库内总数  查询区间/说明")
        print("-" * 105)
        with HistoryRepository(database) as repository:
            results = HistorySyncService(repository, source, years=args.years).sync(
                instruments,
                today=completed_through,
                on_result=_print_progress,
            )

    inserted = sum(result.inserted_rows for result in results)
    print(f"\n同步完成：标的 {len(results)}，新增日线 {inserted}，失败 {sum(r.status == 'failed' for r in results)}。")

    failures = [result for result in results if result.status == "failed"]
    if failures:
        for result in failures:
            logging.error("%s 同步失败：%s", result.code, result.message)
        raise SystemExit(1)


def _format_counts(counts: dict[str, int]) -> str:
    return "，".join(f"{kind}={count}" for kind, count in counts.items())


def _completed_through(now: datetime) -> date:
    """返回已完成日 K 的最晚自然日；节假日由空区间幂等处理。"""
    candidate = now.date()
    if now.weekday() < 5 and now.time() < time(16, 30):
        candidate -= timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def _print_progress(index: int, total: int, result: SyncResult) -> None:
    query_range = (
        f"{result.query_start}..{result.query_end}"
        if result.query_start and result.query_end
        else result.message
    )
    print(
        f"[{index:>5}/{total:<5}] {result.code:<13} {result.status:<17} "
        f"{result.received_rows:>6} {result.inserted_rows:>7} {result.total_rows:>10}  {query_range}",
        flush=True,
    )


if __name__ == "__main__":
    main()
