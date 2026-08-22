"""生成沪深300、中证500和高流动性 ETF 的显式同步配置。"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Protocol, Sequence

from tdx_history.cli import PROJECT_ROOT, _completed_through
from tdx_history.config import Instrument, UniverseSpec
from tdx_history.tdx_source import TdxDailySource


DEFAULT_OUTPUT = PROJECT_ROOT / "config" / "tdx_index_etf_history.json"
DEFAULT_TDX_USER_DIR = Path(r"D:\SoftWare\TDX\PYPlugins\user")


@dataclass(frozen=True)
class IndexSpec:
    """需要固化的指数成分集合。"""

    name: str
    market: str
    expected_count: int


INDEX_SPECS = (
    IndexSpec("hs300", "23", 300),
    IndexSpec("csi500", "24", 500),
)


class TargetSource(Protocol):
    def list_instruments(self, universe: UniverseSpec) -> tuple[Instrument, ...]: ...

    def average_amounts(
        self,
        codes: Sequence[str],
        start: date,
        end: date,
        chunk_size: int = 100,
    ) -> dict[str, float]: ...


def build_target_payload(
    source: TargetSource,
    tdx_user_dir: Path,
    as_of: date,
    etf_count: int = 120,
    lookback_days: int = 60,
    chunk_size: int = 100,
    index_specs: tuple[IndexSpec, ...] = INDEX_SPECS,
) -> dict[str, object]:
    """构建可审计、可由 ``load_config`` 直接读取的显式标的配置。"""
    if etf_count < 100:
        raise ValueError("etf_count 必须至少为 100。")
    if lookback_days <= 0:
        raise ValueError("lookback_days 必须大于 0。")

    grouped: dict[str, tuple[Instrument, ...]] = {}
    for spec in index_specs:
        values = source.list_instruments(UniverseSpec(spec.market, "stock"))
        if len(values) != spec.expected_count:
            raise RuntimeError(
                f"{spec.name} 成分数量异常：期望 {spec.expected_count}，实际 {len(values)}。"
            )
        grouped[spec.name] = values

    etf_candidates = source.list_instruments(UniverseSpec("31", "etf"))
    window_start = as_of - timedelta(days=lookback_days - 1)
    averages = source.average_amounts(
        [instrument.code for instrument in etf_candidates],
        window_start,
        as_of,
        chunk_size,
    )
    ranked_etfs = sorted(
        (instrument for instrument in etf_candidates if averages.get(instrument.code, 0) > 0),
        key=lambda instrument: (-averages[instrument.code], instrument.code),
    )
    if len(ranked_etfs) < etf_count:
        raise RuntimeError(
            f"有效 ETF 流动性数据只有 {len(ranked_etfs)} 只，少于要求的 {etf_count} 只。"
        )
    grouped["mainstream_etf"] = tuple(ranked_etfs[:etf_count])

    instruments: list[dict[str, object]] = []
    seen: set[str] = set()
    memberships: dict[str, list[str]] = {}
    for group_name, values in grouped.items():
        for instrument in values:
            memberships.setdefault(instrument.code, []).append(group_name)
            if instrument.code in seen:
                continue
            seen.add(instrument.code)
            item: dict[str, object] = {
                "code": instrument.code,
                "name": instrument.name,
                "kind": instrument.kind,
                "dividend_type": instrument.dividend_type,
                "groups": memberships[instrument.code],
            }
            if instrument.kind == "etf":
                item["average_amount"] = round(averages[instrument.code], 6)
            instruments.append(item)

    return {
        "tdx_user_dir": str(tdx_user_dir),
        "universes": [],
        "selection": {
            "as_of": as_of.isoformat(),
            "source": "通达信 TQ",
            "index_groups": {
                spec.name: {
                    "market": spec.market,
                    "count": len(grouped[spec.name]),
                    "codes": [item.code for item in grouped[spec.name]],
                }
                for spec in index_specs
            },
            "etf_ranking": {
                "market": "31",
                "metric": "positive_daily_amount_mean",
                "window_start": window_start.isoformat(),
                "window_end": as_of.isoformat(),
                "candidate_count": len(etf_candidates),
                "valid_count": len(ranked_etfs),
                "selected_count": etf_count,
                "codes": [item.code for item in grouped["mainstream_etf"]],
            },
        },
        "instruments": instruments,
    }


def write_target_config(path: Path, payload: dict[str, object]) -> None:
    """用同目录临时文件原子写入 UTF-8 JSON 配置。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成指数成分和主流 ETF 显式同步配置。")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="输出 JSON 路径。")
    parser.add_argument(
        "--tdx-user-dir",
        type=Path,
        default=DEFAULT_TDX_USER_DIR,
        help="通达信 Python 插件 user 目录。",
    )
    parser.add_argument("--as-of", type=date.fromisoformat, help="筛选截止日，格式 YYYY-MM-DD。")
    parser.add_argument("--etf-count", type=int, default=120, help="ETF 数量，至少 100。")
    parser.add_argument("--lookback-days", type=int, default=60, help="流动性自然日窗口。")
    parser.add_argument("--chunk-size", type=int, default=100, help="ETF 成交额分批大小。")
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    as_of = args.as_of or _completed_through(datetime.now())
    with TdxDailySource(args.tdx_user_dir.resolve(), Path(__file__).resolve()) as source:
        payload = build_target_payload(
            source,
            args.tdx_user_dir.resolve(),
            as_of,
            etf_count=args.etf_count,
            lookback_days=args.lookback_days,
            chunk_size=args.chunk_size,
        )
    output = args.output.resolve()
    write_target_config(output, payload)
    selection = payload["selection"]
    assert isinstance(selection, dict)
    ranking = selection["etf_ranking"]
    assert isinstance(ranking, dict)
    print(f"配置已生成：{output}")
    print(f"显式标的：{len(payload['instruments'])}")
    print(f"ETF：{ranking['selected_count']} / 候选 {ranking['candidate_count']}")


if __name__ == "__main__":
    main()
