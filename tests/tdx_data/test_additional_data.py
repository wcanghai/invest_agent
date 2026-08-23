"""额外 TDX 只读接口示例的离线测试。"""

from __future__ import annotations

from datetime import date

import pandas as pd

from tdx_data.additional_data import (
    AdditionalTdxDataSource,
    DATASET_DESCRIPTIONS,
    FINANCIAL_FIELDS,
    GO_FIELDS,
    GP_FIELDS,
    json_ready,
    main,
    quarter_observation_dates,
)


class FakeTq:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def _return(self, name: str, values: dict[str, object], result: object) -> object:
        self.calls.append((name, values))
        return result

    def get_divid_factors(self, **values: object) -> object:
        return self._return("get_divid_factors", values, [{"Date": "20250620"}])

    def get_market_snapshot(self, **values: object) -> object:
        return self._return("get_market_snapshot", values, {"Now": 10.5})

    def get_gb_info(self, **values: object) -> object:
        return self._return("get_gb_info", values, [{"Date": "20250630"}])

    def get_financial_data(self, **values: object) -> object:
        return self._return("get_financial_data", values, {"Fn193": [1.2]})

    def get_gpjy_value(self, **values: object) -> object:
        return self._return("get_gpjy_value", values, {"GP1": [{"Date": "20260820"}]})

    def get_gp_one_data(self, **values: object) -> object:
        return self._return("get_gp_one_data", values, {"GO1": 5.0})


def test_all_additional_interfaces_use_expected_tq_arguments() -> None:
    tq = FakeTq()
    source = AdditionalTdxDataSource(tq)
    start = date(2025, 1, 1)
    end = date(2026, 8, 20)
    observations = (date(2025, 6, 30), date(2025, 3, 31), date(2025, 6, 30))

    for dataset in DATASET_DESCRIPTIONS:
        source.fetch_dataset(dataset, "600000.SH", start, end, observations)

    calls = {name: values for name, values in tq.calls}
    assert calls["get_divid_factors"] == {
        "stock_code": "600000.SH",
        "start_time": "20250101",
        "end_time": "20260820",
    }
    assert calls["get_market_snapshot"]["field_list"] == []
    assert calls["get_gb_info"]["date_list"] == ["20250331", "20250630"]
    assert calls["get_gb_info"]["count"] == 2
    financial_calls = [values for name, values in tq.calls if name == "get_financial_data"]
    assert [values["report_type"] for values in financial_calls] == [
        "report_time",
        "announce_time",
    ]
    assert all(values["field_list"] == list(FINANCIAL_FIELDS) for values in financial_calls)
    assert calls["get_gpjy_value"]["field_list"] == list(GP_FIELDS)
    assert calls["get_gp_one_data"]["field_list"] == list(GO_FIELDS)


def test_json_ready_preserves_dataframe_index_as_date() -> None:
    frame = pd.DataFrame(
        {"Fn193": [1.2]}, index=pd.to_datetime(["2025-12-31"])
    )
    assert json_ready(frame) == [{"Date": "2025-12-31T00:00:00", "Fn193": 1.2}]


def test_quarter_dates_and_sample_only_cli(capsys) -> None:
    assert quarter_observation_dates(date(2026, 1, 1), date(2026, 8, 20)) == (
        date(2026, 3, 31),
        date(2026, 6, 30),
    )
    assert main(["--sample-only", "--dataset", "share_capital"]) == 0
    output = capsys.readouterr().out
    assert "get_gb_info" in output
    assert "结构示意样例" in output
