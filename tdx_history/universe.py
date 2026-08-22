"""证券集合发现、去重与运行范围选择。"""

from __future__ import annotations

from collections import Counter
from typing import Protocol

from tdx_history.config import Instrument, SyncConfig, UniverseSpec


class InstrumentLister(Protocol):
    def list_instruments(self, universe: UniverseSpec) -> tuple[Instrument, ...]: ...


def discover_instruments(
    config: SyncConfig,
    source: InstrumentLister,
) -> tuple[Instrument, ...]:
    """合并手工与运行时发现的标的，按代码保留首个定义。"""
    result: list[Instrument] = []
    seen: set[str] = set()

    def append_new(values: tuple[Instrument, ...]) -> None:
        for instrument in values:
            if instrument.code not in seen:
                seen.add(instrument.code)
                result.append(instrument)

    append_new(config.instruments)
    for universe in config.universes:
        append_new(source.list_instruments(universe))
    return tuple(result)


def select_instruments(
    instruments: tuple[Instrument, ...],
    symbols: set[str] | None = None,
    limit_per_kind: int | None = 5,
) -> tuple[Instrument, ...]:
    """按代码精确筛选，或对每种类型应用安全上限。"""
    if symbols:
        requested = {code.upper() for code in symbols}
        selected = tuple(item for item in instruments if item.code in requested)
        missing = sorted(requested - {item.code for item in selected})
        if missing:
            raise ValueError(f"以下代码未在配置或发现集合中：{', '.join(missing)}")
        return selected

    if limit_per_kind is None:
        return instruments
    if limit_per_kind <= 0:
        raise ValueError("limit_per_kind 必须大于 0。")
    counts: Counter[str] = Counter()
    selected: list[Instrument] = []
    for instrument in instruments:
        if counts[instrument.kind] >= limit_per_kind:
            continue
        counts[instrument.kind] += 1
        selected.append(instrument)
    return tuple(selected)


def count_by_kind(instruments: tuple[Instrument, ...]) -> dict[str, int]:
    """返回稳定的按类型计数。"""
    counts = Counter(item.kind for item in instruments)
    return {kind: counts[kind] for kind in sorted(counts)}
