"""获取并保存主要国内大盘指数的每日行情。

运行前请启动并登录通达信客户端，并确保下载了盘后日线数据。
输出数据是各指数自身的日线交易数据，不等同于沪深全市场汇总成交额。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from get_midea_daily_data import load_tq


INDICES = {
    "000001.SH": "上证综指",
    "399001.SZ": "深证成指",
    "000300.SH": "沪深300",
    "399006.SZ": "创业板指",
    "000016.SH": "上证50",
    "000688.SH": "科创50",
    "000905.SH": "中证500",
    "000852.SH": "中证1000",
    "932000.CSI": "中证2000",
}
FIELDS = ["Open", "High", "Low", "Close", "Volume", "Amount"]


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="获取主要国内大盘指数的日线行情")
    parser.add_argument("--count", type=int, default=20, help="获取最近 N 个交易日（默认：20）")
    parser.add_argument("--start", help="起始日期，格式 YYYYMMDD；指定后进行区间查询")
    parser.add_argument("--end", help="结束日期，格式 YYYYMMDD；区间查询时必填")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("market_daily_data.csv"),
        help="CSV 保存路径（默认：market_daily_data.csv）",
    )
    args = parser.parse_args()
    if args.start and not args.end:
        parser.error("指定 --start 时也必须指定 --end")
    if args.count <= 0 and not args.start:
        parser.error("--count 必须大于 0；如需区间查询，请提供 --start 和 --end")
    return args


def fetch_market_daily_data(args: argparse.Namespace) -> pd.DataFrame:
    """从通达信获取指数日线并计算收盘涨跌幅。"""
    tq = load_tq()
    tq.initialize(str(Path(__file__).resolve()))
    try:
        query = {
            "field_list": FIELDS,
            "stock_list": list(INDICES),
            "period": "1d",
            "dividend_type": "none",
            "fill_data": False,
        }
        if args.start:
            query.update(start_time=args.start, end_time=args.end, count=-1)
        else:
            # 多取一根日线，用于计算输出首日相对前一交易日的涨跌幅。
            query.update(count=args.count + 1)
        data = tq.get_market_data(**query)
    finally:
        tq.close()

    if not data or "Close" not in data:
        raise RuntimeError("接口未返回指数日线数据，请检查通达信客户端和盘后数据。")

    rows: list[dict[str, object]] = []
    for code, name in INDICES.items():
        close = data["Close"][code].dropna()
        for date, price in close.items():
            rows.append(
                {
                    "日期": date.strftime("%Y-%m-%d"),
                    "指数": name,
                    "代码": code,
                    "开盘": data["Open"].at[date, code],
                    "最高": data["High"].at[date, code],
                    "最低": data["Low"].at[date, code],
                    "收盘": price,
                    "涨跌幅(%)": close.pct_change().at[date] * 100,
                    "成交量": data["Volume"].at[date, code],
                    "成交额(万元)": data["Amount"].at[date, code],
                }
            )

    result = pd.DataFrame(rows)
    if result.empty:
        raise RuntimeError("接口没有返回有效的指数日线记录。")
    if not args.start:
        result = result.groupby("代码", group_keys=False).tail(args.count)
    return result.sort_values(["日期", "代码"]).reset_index(drop=True)


def merge_and_save(new_data: pd.DataFrame, output_path: Path) -> pd.DataFrame:
    """与既有 CSV 合并，以日期和代码去重，保留本次获取的记录。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        existing_data = pd.read_csv(output_path, encoding="utf-8-sig")
        combined = pd.concat([existing_data, new_data], ignore_index=True)
    else:
        combined = new_data.copy()

    combined = combined.drop_duplicates(subset=["日期", "代码"], keep="last")
    combined = combined.sort_values(["日期", "代码"]).reset_index(drop=True)
    combined.to_csv(output_path, index=False, encoding="utf-8-sig", float_format="%.6f")
    return combined


def main() -> None:
    args = parse_arguments()
    new_data = fetch_market_daily_data(args)
    all_data = merge_and_save(new_data, args.output)

    print("本次获取：")
    print(new_data.to_string(index=False, float_format=lambda value: f"{value:.2f}"))
    print(f"\n已保存：{args.output.resolve()}（累计 {len(all_data)} 条记录）")


if __name__ == "__main__":
    main()
