"""从现有 TDX 数据库标的执行每日增量归档。"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from typing import Sequence

from tdx_data.archive_service import DEFAULT_DATABASE, DEFAULT_USER_DIR, archive_stocks
from tdx_data.repository import load_archived_assets, open_database


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """解析每日增量命令参数。"""
    parser = argparse.ArgumentParser(
        description="从 TDX 归档库读取已有标的并获取当天增量数据"
    )
    parser.add_argument("--tdx-user-dir", type=Path, default=DEFAULT_USER_DIR)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--end-date", type=date.fromisoformat, default=date.today())
    parser.add_argument(
        "--initial-start-date",
        type=date.fromisoformat,
        default=date(2004, 1, 1),
        help="某类历史数据首次为空时的回溯起点",
    )
    parser.add_argument("--limit", type=int, default=0, help="调试时最多处理 N 只，0 表示全部")
    parser.add_argument("--history-overlap-days", type=int, default=31)
    parser.add_argument(
        "--start-after",
        help="断点续跑时只处理代码字典序晚于该值的标的，例如 513350.SH",
    )
    parser.add_argument(
        "--skip-extended-data", action="store_true", help="跳过历史财务等扩展数据"
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """执行适合每日计划任务调用的增量归档。"""
    args = parse_arguments(argv)
    if not args.database.is_file():
        raise SystemExit(
            f"归档数据库不存在：{args.database.resolve()}。请先运行 tdx-full-archive 初始化。"
        )
    connection = open_database(args.database)
    try:
        assets = load_archived_assets(connection)
    finally:
        connection.close()
    if not assets:
        raise SystemExit(
            "数据库中没有带集合归属的标的，请先使用 tdx-full-archive --target-universe 初始化。"
        )
    if args.start_after:
        start_after = args.start_after.strip().upper()
        assets = [asset for asset in assets if str(asset["Code"]) > start_after]
        if not assets:
            print(f"没有代码晚于 {start_after} 的标的，无需续跑")
            return 0
    print(f"从数据库读取每日增量标的 {len(assets)} 只")
    try:
        result = archive_stocks(
            tdx_user_dir=args.tdx_user_dir,
            database_path=args.database,
            start_date=args.initial_start_date,
            end_date=args.end_date,
            limit=args.limit,
            selected_assets=assets,
            include_extended_data=not args.skip_extended_data,
            history_overlap_days=args.history_overlap_days,
            snapshot_date=args.end_date,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        raise SystemExit(str(error)) from error
    return 0 if result.failed_codes == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
