"""读取并校验市场标的配置。"""

from __future__ import annotations

import json
from pathlib import Path


REQUIRED_SECTIONS = (
    "a_share_stocks",
    "industry_etfs",
    "a_share_indices",
    "a_share_markets",
    "commodity_futures",
    "us_stocks",
    "crypto_pairs",
)


def load_universe(path: Path) -> dict[str, dict[str, str]]:
    """读取配置，确保每个分类都是“代码: 名称”的非空映射。"""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise FileNotFoundError(f"未找到标的配置文件：{path}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"标的配置不是有效 JSON：{path}（{error}）") from error

    if not isinstance(raw, dict):
        raise ValueError("标的配置的最外层必须是 JSON 对象。")
    result: dict[str, dict[str, str]] = {}
    for section in REQUIRED_SECTIONS:
        values = raw.get(section)
        if not isinstance(values, dict):
            raise ValueError(f"配置项 {section} 必须是“代码: 名称”的 JSON 对象。")
        if not all(isinstance(code, str) and isinstance(name, str) for code, name in values.items()):
            raise ValueError(f"配置项 {section} 的代码和名称都必须是字符串。")
        result[section] = values
    return result
