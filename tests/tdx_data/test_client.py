from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from tdx_data.client import DAILY_FIELDS, TdxClient


class FakeTq:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _record(self, name: str, kwargs: dict[str, Any], result: Any) -> Any:
        self.calls.append((name, kwargs))
        return result

    def get_market_data(self, **kwargs: Any) -> dict[str, pd.DataFrame]:
        assert kwargs["field_list"] == list(DAILY_FIELDS)
        assert "Date" not in kwargs["field_list"]
        index = pd.to_datetime(["2026-08-21"])
        return {
            "Close": pd.DataFrame({"000009.SZ": [7.33]}, index=index),
            "Amount": pd.DataFrame({"000009.SZ": [12345]}, index=index),
        }

    def get_financial_data(self, **kwargs: Any) -> Any:
        return self._record("financial", kwargs, {"600000.SH": []})

    def get_gb_info_by_date(self, **kwargs: Any) -> Any:
        return self._record("capital", kwargs, [{"Date": 20260821}])

    def get_divid_factors(self, **kwargs: Any) -> Any:
        return self._record("actions", kwargs, [])

    def get_market_snapshot(self, **kwargs: Any) -> Any:
        return self._record("snapshot", kwargs, {"Now": 10.5})

    def get_gpjy_value(self, **kwargs: Any) -> Any:
        return self._record("gp_trading", kwargs, {})

    def get_gp_one_data(self, **kwargs: Any) -> Any:
        return self._record("gp_single", kwargs, {})


def test_daily_uses_supported_fields_and_recovers_date_from_index() -> None:
    client = TdxClient(Path("tdx-user"), Path("caller.py"))
    client.tq = FakeTq()

    rows = client.daily("000009.SZ", date(2026, 1, 1), date(2026, 8, 23))

    assert rows == [{"Date": "2026-08-21T00:00:00", "Close": 7.33, "Amount": 12345}]


def test_extended_client_uses_incremental_history_interfaces() -> None:
    client = TdxClient(Path("tdx-user"), Path("caller.py"))
    tq = FakeTq()
    client.tq = tq
    start, end = date(2026, 8, 1), date(2026, 8, 24)

    client.financial_history("600000.SH", start, end)
    client.share_capital_history("600000.SH", start, end)
    client.corporate_actions("600000.SH", start, end)
    client.market_snapshot("600000.SH")
    client.gp_trading("600000.SH", start, end)
    client.gp_single("600000.SH")

    calls = {name: kwargs for name, kwargs in tq.calls}
    assert calls["financial"]["report_type"] == "announce_time"
    assert calls["financial"]["start_time"] == "20260801"
    assert calls["capital"] == {
        "stock_code": "600000.SH",
        "start_date": "20260801",
        "end_date": "20260824",
    }
    assert calls["actions"]["end_time"] == "20260824"
    assert calls["snapshot"]["field_list"] == []
    assert calls["gp_trading"]["start_time"] == "20260801"
    assert calls["gp_single"]["stock_list"] == ["600000.SH"]
