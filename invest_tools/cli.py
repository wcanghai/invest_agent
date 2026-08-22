"""将统一命令延迟路由到各独立业务入口。"""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from types import ModuleType
from typing import Callable, Sequence


@dataclass(frozen=True)
class Command:
    """一个可发现但保持独立实现的业务命令。"""

    module: str
    description: str


COMMANDS: dict[str, Command] = {
    "report": Command("market_report.cli", "生成多市场投资日报"),
    "cache": Command("market_report.cache_cli", "建立行情历史缓存"),
    "web": Command("market_web.cli", "启动本地日报网站"),
    "news": Command("finance_news.cli", "采集财经新闻"),
    "history": Command("tdx_history.cli", "同步通达信 A 股和 ETF 日线"),
    "history-config": Command("tdx_history.config_builder", "生成指数成分和主流 ETF 配置"),
    "stock-data": Command("tdx_history.stock_data.cli", "采集十只股票的全维度数据"),
}


def main(argv: Sequence[str] | None = None) -> None:
    """解析一级命令，并把剩余参数原样交给原业务 CLI。"""
    values = list(sys.argv[1:] if argv is None else argv)
    if not values or values[0] in {"-h", "--help", "help"}:
        print(help_text())
        return
    dispatch(values)


def dispatch(
    argv: Sequence[str],
    *,
    loader: Callable[[str], ModuleType] = importlib.import_module,
) -> None:
    """延迟加载并执行一个业务命令，便于隔离可选数据源依赖。"""
    if not argv:
        raise ValueError("argv 不能为空。")
    command_name, *remaining = argv
    command = COMMANDS.get(command_name)
    if command is None:
        available = "、".join(COMMANDS)
        raise SystemExit(f"未知命令：{command_name}。可用命令：{available}")
    module = loader(command.module)
    entry = getattr(module, "main", None)
    if not callable(entry):
        raise RuntimeError(f"模块 {command.module} 缺少可调用的 main()。")
    original_argv = sys.argv
    sys.argv = [f"invest-tools {command_name}", *remaining]
    try:
        entry()
    finally:
        sys.argv = original_argv


def help_text() -> str:
    """返回统一入口帮助文本。"""
    width = max(len(name) for name in COMMANDS)
    rows = ["多市场投资数据工具", "", "用法：invest-tools <命令> [参数]", "", "命令："]
    rows.extend(
        f"  {name:<{width}}  {command.description}" for name, command in COMMANDS.items()
    )
    rows.extend(
        [
            "",
            "使用 invest-tools <命令> --help 查看具体参数。",
            "原有的 market-report、market-web、tdx-history 等命令继续可用。",
        ]
    )
    return "\n".join(rows)
