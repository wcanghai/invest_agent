"""首次建立所有配置标的的五年本地日线缓存。"""

from __future__ import annotations

import argparse
from pathlib import Path

from market_report.config import load_universe
from market_report.history import cache_path, fetch_coinbase_history, fetch_tdx_history, fetch_yahoo_history, save_history
from market_report.tdx import load_tq


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="建立配置标的近五年日线缓存")
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "config" / "market_universe.json")
    parser.add_argument("--history-dir", type=Path, default=PROJECT_ROOT / "data" / "history")
    parser.add_argument("--years", type=int, default=5, help="缓存年数（默认：5）")
    parser.add_argument("--overwrite", action="store_true", help="重新下载并覆盖已有标的缓存")
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    if args.years < 3:
        raise ValueError("缓存年数必须不少于 3 年，才能计算三年价格分位。")
    universe = load_universe(args.config.resolve())
    history_root = args.history_dir.resolve()
    tdx_groups = {
        "a_share_stocks": universe["a_share_stocks"],
        "industry_etfs": universe["industry_etfs"],
        "a_share_indices": universe["a_share_indices"],
        "commodity_futures": universe["commodity_futures"],
    }
    pending_tdx_groups: dict[str, dict[str, str]] = {}
    for category, names in tdx_groups.items():
        pending = {code: name for code, name in names.items() if args.overwrite or not cache_path(history_root, category, code).exists()}
        for code in names:
            if code not in pending:
                print(f"跳过已有缓存 {category}/{code}")
        if pending:
            pending_tdx_groups[category] = pending
    if pending_tdx_groups:
        tq = load_tq()
        tq.initialize(str(Path(__file__).resolve()))
        try:
            for category, names in pending_tdx_groups.items():
                for code, frame in fetch_tdx_history(tq, names, args.years).items():
                    save_history(frame, cache_path(history_root, category, code))
                    print(f"已缓存 {category}/{code}：{len(frame)} 个交易日")
        finally:
            tq.close()

    for code in universe["us_stocks"]:
        path = cache_path(history_root, "us_stocks", code)
        if path.exists() and not args.overwrite:
            print(f"跳过已有缓存 us_stocks/{code}")
            continue
        frame = fetch_yahoo_history(code, args.years)
        save_history(frame, path)
        print(f"已缓存 us_stocks/{code}：{len(frame)} 个交易日")
    for code in universe["crypto_pairs"]:
        path = cache_path(history_root, "crypto_pairs", code)
        if path.exists() and not args.overwrite:
            print(f"跳过已有缓存 crypto_pairs/{code}")
            continue
        frame = fetch_coinbase_history(code, args.years)
        save_history(frame, path)
        print(f"已缓存 crypto_pairs/{code}：{len(frame)} 个交易日")


if __name__ == "__main__":
    main()
