"""采集器配置读取与校验。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]+\.[A-Z]+$")
MARKET_PATTERN = re.compile(r"^[0-9]+$")
VALID_KINDS = {"stock", "etf", "fund"}
VALID_DIVIDEND_TYPES = {"none", "front", "back"}


@dataclass(frozen=True)
class Instrument:
    """一个需要同步的证券。"""

    code: str
    name: str
    kind: str
    dividend_type: str = "none"


@dataclass(frozen=True)
class UniverseSpec:
    """通达信证券集合。"""

    market: str
    kind: str
    dividend_type: str = "none"


@dataclass(frozen=True)
class SyncConfig:
    """采集运行配置。"""

    tdx_user_dir: Path
    instruments: tuple[Instrument, ...]
    universes: tuple[UniverseSpec, ...] = ()


def _require_text(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} 必须是非空字符串。")
    return value.strip()


def load_config(path: Path) -> SyncConfig:
    """读取 JSON 配置，并在连接通达信前完成校验。"""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise FileNotFoundError(f"未找到配置文件：{path}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"配置文件不是有效 JSON：{path}（{error}）") from error

    if not isinstance(raw, dict):
        raise ValueError("配置最外层必须是 JSON 对象。")
    user_dir_raw = raw.get("tdx_user_dir")
    if not isinstance(user_dir_raw, str) or not user_dir_raw.strip():
        raise ValueError("tdx_user_dir 必须是非空路径字符串。")

    universe_values = raw.get("universes", [])
    if not isinstance(universe_values, list):
        raise ValueError("universes 必须是数组。")
    universes: list[UniverseSpec] = []
    seen_markets: set[str] = set()
    for index, item in enumerate(universe_values):
        if not isinstance(item, dict):
            raise ValueError(f"universes[{index}] 必须是 JSON 对象。")
        market = _require_text(item.get("market"), f"universes[{index}].market")
        kind = _require_text(item.get("kind"), f"universes[{index}].kind").lower()
        dividend_type = str(item.get("dividend_type", "none")).strip().lower()
        if not MARKET_PATTERN.fullmatch(market):
            raise ValueError(f"通达信证券集合编号无效：{market}。")
        if kind not in VALID_KINDS:
            raise ValueError(f"集合 {market} 的 kind 必须是 {sorted(VALID_KINDS)} 之一。")
        if dividend_type not in VALID_DIVIDEND_TYPES:
            raise ValueError(
                f"集合 {market} 的 dividend_type 必须是 "
                f"{sorted(VALID_DIVIDEND_TYPES)} 之一。"
            )
        if market in seen_markets:
            raise ValueError(f"通达信证券集合重复：{market}。")
        seen_markets.add(market)
        universes.append(UniverseSpec(market, kind, dividend_type))

    values = raw.get("instruments", [])
    if not isinstance(values, list):
        raise ValueError("instruments 必须是数组。")

    instruments: list[Instrument] = []
    seen: set[str] = set()
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            raise ValueError(f"instruments[{index}] 必须是 JSON 对象。")
        code = _require_text(item.get("code"), f"instruments[{index}].code").upper()
        name = _require_text(item.get("name"), f"instruments[{index}].name")
        kind = _require_text(item.get("kind"), f"instruments[{index}].kind").lower()
        dividend_type = str(item.get("dividend_type", "none")).strip().lower()
        if not SYMBOL_PATTERN.fullmatch(code):
            raise ValueError(f"证券代码格式无效：{code}。示例：600519.SH、159725.SZ。")
        if kind not in VALID_KINDS:
            raise ValueError(f"{code} 的 kind 必须是 {sorted(VALID_KINDS)} 之一。")
        if dividend_type not in VALID_DIVIDEND_TYPES:
            raise ValueError(
                f"{code} 的 dividend_type 必须是 {sorted(VALID_DIVIDEND_TYPES)} 之一。"
            )
        if code in seen:
            raise ValueError(f"证券代码重复：{code}。")
        seen.add(code)
        instruments.append(Instrument(code, name, kind, dividend_type))

    if not universes and not instruments:
        raise ValueError("universes 和 instruments 至少需要配置一项。")
    return SyncConfig(
        tdx_user_dir=Path(user_dir_raw).expanduser(),
        instruments=tuple(instruments),
        universes=tuple(universes),
    )
