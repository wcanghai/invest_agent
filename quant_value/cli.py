"""量化价值研究数据域命令行入口。"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Sequence

from quant_value.config import DEFAULT_UNIVERSE, Instrument, load_universe
from quant_value.analysis import StockAnalysis, analyze_stocks
from quant_value.factors import build_factors
from quant_value.gateway import TdxGateway
from quant_value.repository import DEFAULT_DATABASE, open_database
from quant_value.service import sync_research_data
from quant_value.verify import verify_coverage


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="通达信量化价值研究数据")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init", help="初始化数据库和标的")

    sync = subparsers.add_parser("sync", help="同步通达信研究数据")
    sync.add_argument("--start", type=date.fromisoformat, default=date(2016, 1, 1))
    sync.add_argument("--end", type=date.fromisoformat, default=date.today())
    sync.add_argument("--code", action="append", default=[])
    sync.add_argument("--full", action="store_true", help="关闭增量模式，严格按 start 重取")
    sync.add_argument("--tdx-user-dir", type=Path)
    sync.add_argument("--target-universe", action="store_true",
                      help="动态获取沪深300、中证500和高流动性ETF")
    sync.add_argument("--database-universe", action="store_true",
                      help="使用数据库已有标的，适合每日更新和失败补采")
    sync.add_argument("--etf-limit", type=int, default=120)
    sync.add_argument("--selection-output", type=Path,
                      default=Path("data/quant_value_universe.json"))

    build = subparsers.add_parser("build", help="构建日频因子宽表")
    build.add_argument("--start", type=date.fromisoformat)
    build.add_argument("--end", type=date.fromisoformat)
    build.add_argument("--code", action="append", default=[])
    build.add_argument("--rebuild", action="store_true")

    verify = subparsers.add_parser("verify", help="检查代表性标的数据覆盖")
    verify.add_argument("--code", action="append", default=[])

    analyze = subparsers.add_parser("analyze", help="按价值投资维度分析股票")
    analyze.add_argument("--code", action="append", default=[])
    analyze.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    analyze.add_argument("--history-years", type=int, default=5)
    analyze.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_arguments(argv)
    universe = load_universe(args.universe)
    with open_database(args.database) as connection:
        if args.command == "init":
            from datetime import UTC, datetime
            from quant_value.repository import upsert_instruments

            upsert_instruments(connection, universe, datetime.now(UTC).isoformat())
            connection.commit()
            print(f"已初始化 {args.database}，研究标的 {len(universe)} 个。")
            return 0
        if args.command == "sync":
            if args.target_universe and args.database_universe:
                raise SystemExit("--target-universe 与 --database-universe 不能同时使用")
            if args.target_universe:
                from quant_value.repository import upsert_instruments, upsert_memberships
                from quant_value.universe import fetch_target_universe, group_counts, save_selection

                selection = fetch_target_universe(args.etf_limit, selected_date=args.end)
                selected = list(selection.instruments)
                from datetime import UTC, datetime
                upsert_instruments(connection, selected, datetime.now(UTC).isoformat())
                upsert_memberships(connection, selection.memberships)
                connection.commit()
                save_selection(selection, args.selection_output)
                print(f"目标池：{group_counts(selection)}，去重后 {len(selected)} 个标的。")
            elif args.database_universe:
                from quant_value.repository import load_instruments

                try:
                    selected = load_instruments(connection, args.code or None)
                except ValueError as error:
                    raise SystemExit(str(error)) from error
            else:
                selected = _select(universe, args.code)
            result = sync_research_data(
                connection, TdxGateway(args.tdx_user_dir), selected,
                args.start, args.end, incremental=not args.full,
                progress=_print_progress,
            )
            print(
                f"同步 {result.status}：行情 {result.bar_rows} 行，财报 {result.financial_rows} 行，"
                f"失败 {len(result.errors)} 个。"
            )
            for code, error in result.errors.items():
                print(f"- {code}: {error}")
            return 0 if result.status == "success" else 2
        if args.command == "build":
            codes = args.code or None
            result = build_factors(
                connection, codes, args.start, args.end,
                rebuild=args.rebuild,
                progress=_print_build_progress,
            )
            print(f"已为 {result.codes} 个标的构建 {result.rows} 行因子。")
            return 0
        if args.command == "analyze":
            try:
                analyses = analyze_stocks(
                    connection, args.code or None, args.as_of,
                    history_years=args.history_years,
                )
            except ValueError as error:
                raise SystemExit(str(error)) from error
            if args.format == "json":
                print(json.dumps(
                    [item.to_dict() for item in analyses], ensure_ascii=False, indent=2
                ))
            else:
                _print_analyses(analyses)
            return 0 if analyses else 2
        coverages = verify_coverage(connection, args.code or None)
        print("代码       类型   行情  财报/字段  股本  事件  因子  关键覆盖  结果  说明")
        for item in coverages:
            print(
                f"{item.code:<10} {item.asset_type:<6} {item.bars:<5} "
                f"{item.reports}/{item.financial_fields:<7} {item.capitals:<5} "
                f"{item.actions:<5} {item.factors:<5} {item.required_factor_coverage:>7.1%} "
                f"{item.status:<4} {item.notes}"
            )
        return 0 if coverages and all(item.status == "通过" for item in coverages) else 2


def _select(universe: list[Instrument], codes: list[str]) -> list[Instrument]:
    if not codes:
        return universe
    requested = {code.upper() for code in codes}
    selected = [item for item in universe if item.code.upper() in requested]
    missing = requested - {item.code.upper() for item in selected}
    if missing:
        raise SystemExit(f"代码不在研究配置中：{', '.join(sorted(missing))}")
    return selected


def _print_progress(done: int, total: int, code: str, error: str | None) -> None:
    if error or done == total or done % 25 == 0:
        suffix = f"，失败：{error}" if error else ""
        print(f"采集进度 {done}/{total}：{code}{suffix}", flush=True)


def _print_build_progress(done: int, total: int, code: str, rows: int) -> None:
    if done == total or done % 25 == 0:
        print(f"因子进度 {done}/{total}：{code}，本标的 {rows} 行", flush=True)


def _print_analyses(analyses: list[StockAnalysis]) -> None:
    print("代码       名称       日期        综合  估值  质量  成长  安全  回报  结论")
    for item in analyses:
        scores = (
            item.overall_score, item.valuation.score, item.quality.score,
            item.growth.score, item.safety.score, item.shareholder_return.score,
        )
        print(
            f"{item.code:<10} {item.name:<10} {item.price_date} "
            f"{' '.join(_score(value) for value in scores)}  {item.conclusion}"
        )
        print(
            f"  最新财报 {item.report_date or '-'}（公告 {item.announce_date or '-'}）；"
            f"评分年报 {item.annual_report_date or '-'}（公告 {item.annual_announce_date or '-'}）"
        )
        if item.strengths:
            print(f"  优势：{'；'.join(item.strengths)}")
        if item.risks:
            print(f"  风险：{'；'.join(item.risks)}")
        if item.data_warnings:
            print(f"  数据提示：{'；'.join(item.data_warnings)}")
    print("说明：分数用于同一套规则下的研究初筛，不构成投资建议。")


def _score(value: float | None) -> str:
    return "  -  " if value is None else f"{value:5.1f}"
