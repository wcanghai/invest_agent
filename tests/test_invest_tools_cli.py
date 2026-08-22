from types import ModuleType
import sys

import pytest

from invest_tools.cli import COMMANDS, dispatch, help_text


def test_help_lists_all_commands_and_compatibility_note() -> None:
    text = help_text()
    assert set(COMMANDS).issubset(text.split())
    assert "原有的 market-report" in text


def test_dispatch_forwards_arguments_and_restores_sys_argv() -> None:
    received: list[list[str]] = []
    module = ModuleType("fake_command")
    module.main = lambda: received.append(sys.argv.copy())  # type: ignore[attr-defined]
    original = sys.argv

    dispatch(["history", "--years", "3"], loader=lambda _name: module)

    assert received == [["invest-tools history", "--years", "3"]]
    assert sys.argv is original


def test_dispatch_rejects_unknown_command() -> None:
    with pytest.raises(SystemExit, match="未知命令"):
        dispatch(["missing"])
