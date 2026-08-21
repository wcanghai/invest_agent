"""可配置的多市场行情日报入口。"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from market_report.config import load_universe
from market_report.external import fetch_crypto_quotes, fetch_us_daily
from market_report.history import attach_price_positions, merge_latest_rows
from market_report.report import render
from market_report.tdx import fetch_a_share_data


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成可配置的 A 股、美股与虚拟货币行情日报")
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "config" / "market_universe.json",
        help="标的配置 JSON 路径",
    )
    parser.add_argument(
        "--history-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "history",
        help="本地历史日线缓存目录（默认：data/history）",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="报告输出路径；默认写入 reports/market_report_YYYY-MM-DD.md",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    universe = load_universe(args.config.resolve())
    generated_at = datetime.now()
    default_output = PROJECT_ROOT / "reports" / f"market_report_{generated_at:%Y-%m-%d}.md"
    output = (args.output or default_output).resolve()
    history_root = args.history_dir.resolve()

    stock_rows, etf_rows, index_rows, futures_rows, breadth = fetch_a_share_data(universe, Path(__file__).resolve())
    us_rows, us_warnings = fetch_us_daily(universe["us_stocks"])
    crypto_rows, crypto_warnings = fetch_crypto_quotes(universe["crypto_pairs"])
    fallback_date = generated_at.strftime("%Y-%m-%d")
    for category, rows in [
        ("a_share_stocks", stock_rows),
        ("industry_etfs", etf_rows),
        ("a_share_indices", index_rows),
        ("commodity_futures", futures_rows),
        ("us_stocks", us_rows),
        ("crypto_pairs", crypto_rows),
    ]:
        merge_latest_rows(rows, history_root, category, fallback_date)
        attach_price_positions(rows, history_root, category)
    report = render(
        stock_rows, etf_rows, index_rows, breadth, futures_rows, us_rows, crypto_rows,
        us_warnings + crypto_warnings, generated_at,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(f"报告已生成：{output}")


if __name__ == "__main__":
    main()
