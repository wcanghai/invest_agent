"""十只股票全维度通达信数据试采集命令。"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

from tdx_history.config import Instrument, load_config
from tdx_history.cli import _completed_through
from tdx_history.stock_data.repository import StockDataRepository
from tdx_history.stock_data.service import DatasetResult, StockDataSyncService
from tdx_history.stock_data.source import TdxStockDataSource


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "tdx_stock_samples.json"
DEFAULT_DATABASE = PROJECT_ROOT / "data" / "tdx_stock_data.sqlite3"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "history" / "tdx_stock_data_summary.json"


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="采集十只不同类型 A 股的通达信全维度数据。")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--years", type=int, default=10)
    parser.add_argument("--as-of", type=date.fromisoformat, help="采集截止日 YYYY-MM-DD")
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    config_path = args.config.resolve()
    config = load_config(config_path)
    instruments = config.instruments
    if config.universes:
        raise ValueError("全维度试采集只接受显式 instruments，不接受动态 universes。")
    if len(instruments) != 10 or any(item.kind != "stock" for item in instruments):
        raise ValueError("试采集配置必须恰好包含 10 只 kind=stock 的股票。")
    sample_types = _load_sample_types(config_path, instruments)
    observed_date = args.as_of or date.today()
    history_end = _previous_weekday(observed_date) if args.as_of else _completed_through(datetime.now())
    database = args.database.resolve()
    output = args.output.resolve()

    print(f"股票数：{len(instruments)}；截止日：{observed_date}")
    print(f"已完成日线截止日：{history_end}")
    print(f"数据库：{database}")
    print("进度       代码          数据集                       状态      记录  字段  说明")
    print("-" * 118)
    with TdxStockDataSource(config.tdx_user_dir, Path(__file__).resolve()) as source:
        with StockDataRepository(database) as repository:
            results = StockDataSyncService(repository, source, years=args.years).sync(
                instruments,
                sample_types,
                today=observed_date,
                history_end=history_end,
                on_result=_print_progress,
            )

    summary = build_summary(instruments, sample_types, observed_date, database, results)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    _print_summary(summary)
    print(f"\n字段汇总：{output}")


def build_summary(
    instruments: tuple[Instrument, ...],
    sample_types: dict[str, str],
    observed_date: date,
    database: Path,
    results: list[DatasetResult],
) -> dict[str, Any]:
    by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
    fields_by_dataset: dict[str, set[str]] = defaultdict(set)
    for result in results:
        by_code[result.code].append(result.to_dict())
        fields_by_dataset[result.dataset].update(result.fields)
    return {
        "observed_date": observed_date.isoformat(),
        "database": str(database),
        "instrument_count": len(instruments),
        "dataset_result_count": len(results),
        "success_count": sum(item.status == "success" for item in results),
        "empty_count": sum(item.status == "empty" for item in results),
        "failed_count": sum(item.status == "failed" for item in results),
        "fields_by_dataset": {
            dataset: sorted(fields) for dataset, fields in sorted(fields_by_dataset.items())
        },
        "instruments": [
            {
                "code": item.code,
                "name": item.name,
                "sample_type": sample_types[item.code],
                "datasets": by_code[item.code],
            }
            for item in instruments
        ],
    }


def _load_sample_types(path: Path, instruments: tuple[Instrument, ...]) -> dict[str, str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    values = raw.get("instruments", [])
    tags = {
        str(item.get("code", "")).strip().upper(): str(item.get("sample_type", "")).strip()
        for item in values
        if isinstance(item, dict)
    }
    missing = [item.code for item in instruments if not tags.get(item.code)]
    if missing:
        raise ValueError(f"以下股票缺少 sample_type：{missing}")
    return tags


def _print_progress(index: int, total: int, result: DatasetResult) -> None:
    print(
        f"[{index:>3}/{total:<3}] {result.code:<13} {result.dataset:<28} "
        f"{result.status:<9} {result.record_count:>5} {result.field_count:>5}  {result.message}",
        flush=True,
    )


def _print_summary(summary: dict[str, Any]) -> None:
    print(
        "\n采集结果："
        f"成功 {summary['success_count']}，空数据 {summary['empty_count']}，"
        f"失败 {summary['failed_count']}。"
    )
    print("可获取字段：")
    for dataset, fields in summary["fields_by_dataset"].items():
        preview = "、".join(fields[:12])
        suffix = f" 等共 {len(fields)} 个" if len(fields) > 12 else ""
        print(f"- {dataset}: {preview}{suffix}")


def _previous_weekday(value: date) -> date:
    while value.weekday() >= 5:
        value = value.fromordinal(value.toordinal() - 1)
    return value


if __name__ == "__main__":
    main()
