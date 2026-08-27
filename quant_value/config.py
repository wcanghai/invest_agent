"""代表性研究标的配置。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


DEFAULT_UNIVERSE = Path(__file__).with_name("representative_universe.json")


@dataclass(frozen=True)
class Instrument:
    code: str
    name: str
    asset_type: str
    category: str
    benchmark_code: str | None = None
    benchmark_name: str | None = None


def load_universe(path: Path = DEFAULT_UNIVERSE) -> list[Instrument]:
    """读取并校验研究标的；证券代码必须唯一。"""
    payload = json.loads(path.read_text(encoding="utf-8"))
    instruments = [Instrument(**item) for item in payload["instruments"]]
    codes = [item.code for item in instruments]
    if len(codes) != len(set(codes)):
        raise ValueError("研究标的代码不能重复。")
    invalid = [item.code for item in instruments if item.asset_type not in {"stock", "etf"}]
    if invalid:
        raise ValueError(f"不支持的资产类型：{invalid}")
    return instruments

