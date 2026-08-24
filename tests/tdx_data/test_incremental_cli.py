from __future__ import annotations

from pathlib import Path

import pytest

from tdx_data.incremental_cli import main


def test_daily_update_requires_initialized_database(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="请先运行 tdx-full-archive 初始化"):
        main(["--database", str(tmp_path / "missing.sqlite3")])
