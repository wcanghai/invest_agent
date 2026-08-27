"""通达信完整归档命令行入口。"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from tdx_data.archive_service import DEFAULT_DATABASE, DEFAULT_USER_DIR, archive_stocks
from tdx_data.universe import fetch_target_universe, group_counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="获取通达信股票日线和股票维度数据并保存到 SQLite")
    parser.add_argument("--tdx-user-dir", type=Path, default=DEFAULT_USER_DIR)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--market", default="5", help="通达信证券集合编号，默认 5")
    parser.add_argument("--start-date", type=date.fromisoformat, default=date(2004, 1, 1), help="首次日线起始日期")
    parser.add_argument("--end-date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--limit", type=int, default=10, help="最多处理 N 只股票，0 表示全部")
    parser.add_argument(
        "--target-universe",
        action="store_true",
        help="归档沪深300、中证500和高流动性 ETF，而不是默认股票列表",
    )
    parser.add_argument(
        "--etf-limit",
        type=int,
        default=120,
        help="定向归档时按最近成交额选择的 ETF 数量，必须大于100（默认：120）",
    )
    parser.add_argument(
        "--history-overlap-days",
        type=int,
        default=31,
        help="历史财务、股本和公司行为增量回看天数（默认：31）",
    )
    parser.add_argument(
        "--skip-extended-data",
        action="store_true",
        help="仅归档原有日线和基础快照，跳过历史财务等扩展数据",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        selected_assets = None
        if args.target_universe:
            universe = fetch_target_universe(args.etf_limit)
            selected_assets = [asset.to_archive_row() for asset in universe]
            print(f"定向清单：{group_counts(universe)}，去重后 {len(universe)} 只")
        archive_stocks(
            tdx_user_dir=args.tdx_user_dir,
            database_path=args.database,
            market=args.market,
            start_date=args.start_date,
            end_date=args.end_date,
            limit=args.limit,
            selected_assets=selected_assets,
            include_extended_data=not args.skip_extended_data,
            history_overlap_days=args.history_overlap_days,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
