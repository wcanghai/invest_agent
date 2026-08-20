"""指定股票、ETF 和基金的十年日线增量同步入口。"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, time, timedelta
from pathlib import Path

from tdx_history import HistoryRepository, HistorySyncService, load_config
from tdx_history.tdx_source import TdxDailySource


PROJECT_ROOT = Path(__file__).resolve().parent
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
        help="只同步配置中的指定代码；默认同步全部。",
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
    instruments = config.instruments
    if args.symbols:
        requested = {code.upper() for code in args.symbols}
        instruments = tuple(item for item in instruments if item.code in requested)
        missing = sorted(requested - {item.code for item in instruments})
        if missing:
            raise ValueError(f"以下代码未在配置中：{', '.join(missing)}")
    if not instruments:
        raise ValueError("没有需要同步的证券。")

    database = args.database.resolve()
    now = datetime.now()
    completed_through = now.date()
    if not args.include_today and now.weekday() < 5 and now.time() < time(16, 30):
        completed_through -= timedelta(days=1)
    with HistoryRepository(database) as repository:
        with TdxDailySource(config.tdx_user_dir, Path(__file__).resolve()) as source:
            results = HistorySyncService(repository, source, years=args.years).sync(
                instruments, today=completed_through
            )

        print(f"\n数据库：{database}")
        print(f"本次同步截止日：{completed_through}")
        print("代码          状态              接收    新增    库内总数  查询区间/说明")
        print("-" * 92)
        for result in results:
            query_range = (
                f"{result.query_start}..{result.query_end}"
                if result.query_start and result.query_end
                else result.message
            )
            print(
                f"{result.code:<13} {result.status:<17} "
                f"{result.received_rows:>6} {result.inserted_rows:>7} {result.total_rows:>10}  {query_range}"
            )

    failures = [result for result in results if result.status == "failed"]
    if failures:
        for result in failures:
            logging.error("%s 同步失败：%s", result.code, result.message)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
