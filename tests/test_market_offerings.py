from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd

from market_report.offerings import collect_offerings, normalize_tdx_offerings
from market_report.service import generate_market_report


def test_normalize_tdx_offerings_uses_subscription_code_and_ignores_zero_values() -> None:
    rows = normalize_tdx_offerings(
        [
            {
                "SetCode": "1",
                "Code": "603999",
                "Name": "测试股份",
                "SGDate": "20260824",
                "SGPrice": "0.00",
                "SGCode": "732999",
                "MaxSG": "2.95",
                "PE_Issue": "13.81",
            }
        ],
        "新股",
    )

    assert rows == [
        {
            "kind": "新股",
            "name": "测试股份",
            "subscription_code": "732999",
            "security_code": "603999",
            "subscription_date": "2026-08-24",
            "issue_price": None,
            "max_subscription": 2.95,
            "max_subscription_unit": "万股",
            "issue_pe": 13.81,
            "winning_rate": None,
            "listing_date": None,
            "underlying_code": None,
            "underlying_name": None,
            "issue_size": None,
            "rating": None,
            "sources": ["通达信"],
            "event_status": None,
        }
    ]


def test_collect_offerings_merges_sources_and_filters_event_window() -> None:
    tdx_rows = normalize_tdx_offerings(
        [
            {
                "Code": "603999", "Name": "测试股份", "SGCode": "732999",
                "SGDate": "20260824", "SGPrice": "10", "MaxSG": "2",
                "PE_Issue": "15",
            }
        ],
        "新股",
    )
    stock_frame = pd.DataFrame(
        [
            {
                "股票代码": "603999", "股票简称": "测试股份", "申购代码": "732999",
                "发行价格": 10, "申购上限": 20_000, "发行市盈率": 15,
                "申购日期": "2026-08-24", "中签率": 0.0123,
                "上市日期": "2026-09-01",
            },
            {
                "股票代码": "600001", "股票简称": "历史股票", "申购代码": "730001",
                "申购日期": "2020-01-01", "上市日期": "2020-02-01",
            },
        ]
    )
    bond_frame = pd.DataFrame(
        [
            {
                "债券代码": "123999", "债券简称": "测试转债", "申购代码": "371999",
                "申购日期": "2026-07-01", "申购上限": 100,
                "正股代码": "301999", "正股简称": "测试科技", "发行规模": 5.5,
                "中签率": 0.001, "上市时间": "2026-08-21", "信用评级": "AA-",
            }
        ]
    )

    rows, warnings = collect_offerings(
        Path("caller.py"),
        date(2026, 8, 22),
        tdx_fetcher=lambda: tdx_rows,
        stock_fetcher=lambda: stock_frame,
        bond_fetcher=lambda: bond_frame,
    )

    assert warnings == []
    assert len(rows) == 2
    stock = next(row for row in rows if row["kind"] == "新股")
    assert stock["winning_rate"] == 0.0123
    assert stock["max_subscription"] == 2
    assert stock["max_subscription_unit"] == "万股"
    assert stock["listing_date"] == "2026-09-01"
    assert stock["event_status"] == "待申购、待上市"
    assert stock["sources"] == ["通达信", "东方财富"]
    bond = next(row for row in rows if row["kind"] == "新债")
    assert bond["underlying_name"] == "测试科技"
    assert bond["rating"] == "AA-"
    assert bond["event_status"] == "近期上市"


def test_collect_offerings_degrades_when_live_sources_fail() -> None:
    def fail() -> pd.DataFrame:
        raise RuntimeError("模拟网络错误")

    rows, warnings = collect_offerings(
        Path("caller.py"),
        date(2026, 8, 22),
        tdx_fetcher=lambda: [],
        stock_fetcher=fail,
        bond_fetcher=lambda: pd.DataFrame(),
    )

    assert rows == []
    assert warnings == ["公开新股发行数据：获取失败（模拟网络错误）。"]


def test_collect_offerings_rejects_negative_window() -> None:
    try:
        collect_offerings(
            Path("caller.py"),
            date(2026, 8, 22),
            tdx_fetcher=lambda: [],
            stock_fetcher=pd.DataFrame,
            bond_fetcher=pd.DataFrame,
            forward_days=-1,
        )
    except ValueError as error:
        assert str(error) == "发行日历观察窗口不能为负数。"
    else:
        raise AssertionError("负数观察窗口应被拒绝")


def test_generate_report_persists_offering_calendar(monkeypatch, tmp_path: Path) -> None:
    breadth = {
        "沪市": {"amount": 10_000, "up": 1, "down": 2},
        "深市": {"amount": 20_000, "up": 3, "down": 4},
        "北交所": {"amount": 3_000, "up": 5, "down": 6},
        "三市合计": {"amount": 33_000, "up": 9, "down": 12},
    }
    offering = {
        "kind": "新股", "name": "测试股份", "subscription_code": "732999",
        "security_code": "603999", "subscription_date": "2026-08-24",
        "issue_price": 10.0, "max_subscription": 2.0,
        "max_subscription_unit": "万股", "issue_pe": 15.0,
        "winning_rate": None, "listing_date": None, "underlying_code": None,
        "underlying_name": None, "issue_size": None, "rating": None,
        "sources": ["通达信"], "event_status": "待申购",
    }
    monkeypatch.setattr(
        "market_report.service.fetch_a_share_data",
        lambda _universe, _caller: ([], [], [], [], breadth),
    )
    monkeypatch.setattr("market_report.service.fetch_us_daily", lambda _names: ([], []))
    monkeypatch.setattr("market_report.service.fetch_crypto_quotes", lambda _names: ([], []))
    monkeypatch.setattr(
        "market_report.service.collect_offerings",
        lambda _caller, _as_of: ([offering], ["发行数据测试警告"]),
    )

    root = Path(__file__).resolve().parents[1]
    snapshot = generate_market_report(
        root / "config" / "market_universe.json",
        tmp_path / "history",
        Path(__file__),
        datetime(2026, 8, 22, 9, 0),
    )

    assert snapshot.data["ipo_calendar"] == [offering]
    assert snapshot.data["warnings"] == ["发行数据测试警告"]
    assert "## 8. 新股新债日历" in snapshot.markdown
    assert "测试股份" in snapshot.markdown
