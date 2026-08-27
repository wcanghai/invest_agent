"""从现有 TDX 归档库构建量化日频宽表。"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from typing import Sequence

from tdx_data.archive_service import DEFAULT_DATABASE
from tdx_data.quant_wide_service import build_quant_daily_wide
from tdx_data.repository import load_archived_assets, open_database


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """解析宽表构建参数。"""
    parser = argparse.ArgumentParser(description="从 TDX 归档库构建时点一致的量化日频宽表")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--code", nargs="+", help="只构建指定代码；默认构建当前全部标的")
    parser.add_argument("--start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--limit", type=int, default=0, help="最多处理 N 只，0 表示全部")
    parser.add_argument("--rebuild", action="store_true", help="先删除目标区间再重新构建")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """执行宽表构建。"""
    args = parse_arguments(argv)
    if not args.database.is_file():
        raise SystemExit(f"归档数据库不存在：{args.database.resolve()}")
    connection = open_database(args.database)
    try:
        codes = [code.strip().upper() for code in args.code] if args.code else [
            str(asset["Code"]) for asset in load_archived_assets(connection)
        ]
        if args.limit > 0:
            codes = codes[: args.limit]
        if not codes:
            raise SystemExit("没有可构建的标的")

        def report_progress(
            index: int, total: int, code: str, rows: int, failed: bool
        ) -> None:
            if failed or index == 1 or index % 25 == 0 or index == total:
                state = "失败" if failed else f"{rows} 行"
                print(f"[{index}/{total}] {code}：{state}", flush=True)

        result = build_quant_daily_wide(
            connection,
            codes,
            args.start,
            args.end,
            rebuild=args.rebuild,
            progress=report_progress,
        )
    finally:
        connection.close()
    print(
        f"完成：标的 {result.requested_codes}，写入/更新 {result.written_rows} 行，"
        f"失败 {len(result.failed_codes)}"
    )
    if result.failed_codes:
        print("失败代码：" + ", ".join(result.failed_codes))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
