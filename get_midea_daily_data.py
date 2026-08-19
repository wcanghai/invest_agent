"""通过通达信 TQ 接口获取美的集团（000333.SZ）的日线交易数据。

运行前：启动并登录通达信客户端，且客户端下载了对应的盘后日线数据。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


TDX_USER_DIR = Path(r"D:\SoftWare\TDX\PYPlugins\user")
STOCK_CODE = "000333.SZ"
FIELDS = ["Open", "High", "Low", "Close", "Volume", "Amount"]


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="获取美的集团日线交易数据")
    parser.add_argument("--count", type=int, default=20, help="获取最近 N 个交易日（默认：20）")
    parser.add_argument("--start", help="起始日期，格式 YYYYMMDD；指定后改为区间查询")
    parser.add_argument("--end", help="结束日期，格式 YYYYMMDD；区间查询时建议指定")
    parser.add_argument(
        "--dividend-type",
        choices=["none", "front", "back"],
        default="none",
        help="复权类型：none（不复权，默认）、front（前复权）、back（后复权）",
    )
    parser.add_argument("--output", type=Path, help="可选：将结果保存为 CSV 文件")
    args = parser.parse_args()
    if args.start and not args.end:
        parser.error("指定 --start 时也必须指定 --end")
    if args.count <= 0 and not args.start:
        parser.error("--count 必须大于 0；如需区间查询，请提供 --start 和 --end")
    return args


def load_tq():
    """从通达信插件目录加载 tqcenter。"""
    if not TDX_USER_DIR.is_dir():
        raise FileNotFoundError(f"未找到通达信插件目录：{TDX_USER_DIR}")
    sys.path.insert(0, str(TDX_USER_DIR))
    from tqcenter import tq  # pylint: disable=import-outside-toplevel

    return tq


def get_daily_data(args: argparse.Namespace) -> pd.DataFrame:
    tq = load_tq()
    tq.initialize(str(Path(__file__).resolve()))
    try:
        query = {
            "field_list": FIELDS,
            "stock_list": [STOCK_CODE],
            "period": "1d",
            "dividend_type": args.dividend_type,
            "fill_data": False,
        }
        if args.start:
            query.update(start_time=args.start, end_time=args.end, count=-1)
        else:
            query.update(count=args.count)

        data = tq.get_market_data(**query)
        if not data:
            raise RuntimeError("接口未返回日线数据，请检查通达信客户端和盘后数据是否可用。")

        return pd.concat({field: frame[STOCK_CODE] for field, frame in data.items()}, axis=1)
    finally:
        tq.close()


def main() -> None:
    args = parse_arguments()
    daily_data = get_daily_data(args)
    print(daily_data.to_string())

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        daily_data.to_csv(args.output, encoding="utf-8-sig")
        print(f"\n已保存到：{args.output.resolve()}")


if __name__ == "__main__":
    main()
