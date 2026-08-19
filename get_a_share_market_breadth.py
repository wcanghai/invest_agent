"""获取并保存沪深北三市 A 股当日市场成交额与涨跌家数。

通过通达信的沪市、深市、北交所市场快照分别取得 Amount、UpHome、DownHome，
再汇总为三市 A 股口径。Amount 表示成交额，不表示资金净流入。
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd

from get_midea_daily_data import load_tq


MARKETS = {
    "000001.SH": "沪市",
    "399001.SZ": "深市",
    "899050.BJ": "北交所",
}
SNAPSHOT_FIELDS = ["Amount", "UpHome", "DownHome", "ErrorId"]


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="获取全 A 股当日成交额与涨跌家数")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("a_share_market_breadth.csv"),
        help="CSV 保存路径（默认：a_share_market_breadth.csv）",
    )
    return parser.parse_args()


def get_today_market_breadth() -> pd.DataFrame:
    """读取沪深北快照并返回一行三市 A 股汇总数据。"""
    tq = load_tq()
    tq.initialize(str(Path(__file__).resolve()))
    try:
        snapshots = {
            code: tq.get_market_snapshot(code, SNAPSHOT_FIELDS) for code in MARKETS
        }
    finally:
        tq.close()

    values: dict[str, float | int] = {}
    for code, market_name in MARKETS.items():
        snapshot = snapshots[code]
        if snapshot.get("ErrorId") != "0":
            raise RuntimeError(f"未能获取{market_name}快照：{snapshot}")
        try:
            values[f"{market_name}成交额(万元)"] = float(snapshot["Amount"])
            values[f"{market_name}上涨家数"] = int(snapshot["UpHome"])
            values[f"{market_name}下跌家数"] = int(snapshot["DownHome"])
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError(f"{market_name}快照字段不完整：{snapshot}") from error

    now = datetime.now()
    total_amount = sum(values[f"{market_name}成交额(万元)"] for market_name in MARKETS.values())
    return pd.DataFrame(
        [
            {
                "交易日期": now.strftime("%Y-%m-%d"),
                "获取时间": now.strftime("%Y-%m-%d %H:%M:%S"),
                "沪市成交额(万元)": values["沪市成交额(万元)"],
                "深市成交额(万元)": values["深市成交额(万元)"],
                "北交所成交额(万元)": values["北交所成交额(万元)"],
                "三市成交额(万元)": total_amount,
                "三市成交额(亿元)": total_amount / 10_000,
                "沪市上涨家数": values["沪市上涨家数"],
                "沪市下跌家数": values["沪市下跌家数"],
                "深市上涨家数": values["深市上涨家数"],
                "深市下跌家数": values["深市下跌家数"],
                "北交所上涨家数": values["北交所上涨家数"],
                "北交所下跌家数": values["北交所下跌家数"],
                "三市上涨家数": sum(values[f"{market_name}上涨家数"] for market_name in MARKETS.values()),
                "三市下跌家数": sum(values[f"{market_name}下跌家数"] for market_name in MARKETS.values()),
            }
        ]
    )


def merge_and_save(new_data: pd.DataFrame, output_path: Path) -> pd.DataFrame:
    """按交易日期去重；同一天再次运行时保留最新快照。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        existing_data = pd.read_csv(output_path, encoding="utf-8-sig")
        # 丢弃旧版“两市”字段，并为历史记录补齐当前三市字段。
        existing_data = existing_data.reindex(columns=new_data.columns)
        combined = pd.concat([existing_data, new_data], ignore_index=True)
    else:
        combined = new_data.copy()

    combined = combined.drop_duplicates(subset=["交易日期"], keep="last")
    combined = combined.sort_values("交易日期").reset_index(drop=True)
    combined.to_csv(output_path, index=False, encoding="utf-8-sig", float_format="%.2f")
    return combined


def main() -> None:
    args = parse_arguments()
    today_data = get_today_market_breadth()
    history = merge_and_save(today_data, args.output)
    print(today_data.to_string(index=False, float_format=lambda value: f"{value:.2f}"))
    print(f"\n已保存：{args.output.resolve()}（累计 {len(history)} 个交易日）")


if __name__ == "__main__":
    main()
