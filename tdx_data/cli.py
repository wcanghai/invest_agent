"""通达信完整归档命令行入口。"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from tdx_data.archive_service import DEFAULT_DATABASE, DEFAULT_USER_DIR, archive_stocks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="获取通达信股票日线和股票维度数据并保存到 SQLite")
    parser.add_argument("--tdx-user-dir", type=Path, default=DEFAULT_USER_DIR)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--market", default="5", help="通达信证券集合编号，默认 5")
    parser.add_argument("--start-date", type=date.fromisoformat, default=date(2004, 1, 1), help="首次日线起始日期")
    parser.add_argument("--end-date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--limit", type=int, default=10, help="最多处理 N 只股票，0 表示全部")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        archive_stocks(
            tdx_user_dir=args.tdx_user_dir,
            database_path=args.database,
            market=args.market,
            start_date=args.start_date,
            end_date=args.end_date,
            limit=args.limit,
        )
    except (FileNotFoundError, ValueError) as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
