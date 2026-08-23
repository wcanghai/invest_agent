"""将配置标的的近五年日线同步到日报 SQLite。"""

from __future__ import annotations

import argparse
from pathlib import Path

from daily_report.config import load_universe
from daily_report.data_sources.history import (
    fetch_coinbase_history,
    fetch_tdx_history,
    fetch_yahoo_history,
)
from daily_report.storage.market_repository import MarketRepository
from daily_report.storage.sync_repository import SyncRunRepository
from tdx_data.client import tdx_session


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = PROJECT_ROOT / "data" / "daily_report.sqlite3"


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="同步配置标的近五年日线到 SQLite")
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "config" / "market_universe.json")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--years", type=int, default=5, help="缓存年数（默认：5）")
    parser.add_argument("--overwrite", action="store_true", help="写入前删除对应标的已有日线")
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    if args.years < 3:
        raise ValueError("缓存年数必须不少于 3 年，才能计算三年价格分位。")
    universe = load_universe(args.config.resolve())
    repository = MarketRepository(args.database)
    run_repository = SyncRunRepository(args.database)
    run_id = run_repository.start("market_cache")
    written_rows = 0
    repository.sync_instruments(universe)
    tdx_groups = {
        category: universe[category]
        for category in (
            "a_share_stocks", "industry_etfs", "a_share_indices", "commodity_futures"
        )
    }
    try:
        with tdx_session(Path(__file__).resolve()) as tq:
            for category, names in tdx_groups.items():
                for code, frame in fetch_tdx_history(tq, names, args.years).items():
                    if args.overwrite:
                        repository.delete_bars(category, code)
                    written_rows += repository.upsert_bars(category, code, frame)
                    print(f"已同步 {category}/{code}：{len(frame)} 个交易日")

        for category, fetcher in (
            ("us_stocks", fetch_yahoo_history),
            ("crypto_pairs", fetch_coinbase_history),
        ):
            for code in universe[category]:
                frame = fetcher(code, args.years)
                if args.overwrite:
                    repository.delete_bars(category, code)
                written_rows += repository.upsert_bars(category, code, frame)
                print(f"已同步 {category}/{code}：{len(frame)} 个交易日")
    except Exception as error:
        run_repository.fail(run_id, error)
        raise
    run_repository.finish(run_id, written_rows)
    print(f"历史行情数据库：{args.database.resolve()}")


if __name__ == "__main__":
    main()
