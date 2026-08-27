from datetime import date

from quant_value.cli import parse_arguments


def test_cli_parses_sync_and_build() -> None:
    sync = parse_arguments(["sync", "--start", "2020-01-01", "--code", "600519.SH"])
    assert sync.start == date(2020, 1, 1)
    assert sync.code == ["600519.SH"]
    build = parse_arguments(["build", "--rebuild"])
    assert build.rebuild is True

    target = parse_arguments(["sync", "--target-universe", "--etf-limit", "150"])
    assert target.target_universe is True
    assert target.etf_limit == 150
    database = parse_arguments(["sync", "--database-universe", "--code", "600519.SH"])
    assert database.database_universe is True

    analyze = parse_arguments([
        "analyze", "--as-of", "2026-08-26", "--history-years", "3", "--format", "json",
    ])
    assert analyze.as_of == date(2026, 8, 26)
    assert analyze.history_years == 3
    assert analyze.format == "json"
