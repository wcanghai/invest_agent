"""通达信股票全维度只读数据源适配器。"""

from __future__ import annotations

from datetime import date
from typing import Any, Iterable

import pandas as pd

from tdx_history.tdx_source import TdxDailySource


FINANCIAL_FIELDS = (
    "Fn193",
    "Fn194",
    "Fn195",
    "Fn196",
    "Fn197",
    "Fn198",
    "Fn199",
    "Fn200",
)
GP_FIELDS = ("GP1", "GP2", "GP3", "GP4", "GP5")
GO_FIELDS = ("GO1", "GO2", "GO3", "GO4", "GO47")


class TdxStockDataSource(TdxDailySource):
    """在一个 TQ 会话中读取安全、只读的股票维度数据。"""

    def fetch_dividends(self, code: str, start: date, end: date) -> list[dict[str, Any]]:
        payload = self._require_tq().get_divid_factors(
            stock_code=code,
            start_time=start.strftime("%Y%m%d"),
            end_time=end.strftime("%Y%m%d"),
        )
        return records_from_payload(payload, code)

    def fetch_market_snapshot(self, code: str) -> dict[str, Any]:
        return mapping_from_payload(
            self._require_tq().get_market_snapshot(stock_code=code, field_list=[]), code
        )

    def fetch_stock_info(self, code: str) -> dict[str, Any]:
        return mapping_from_payload(
            self._require_tq().get_stock_info(stock_code=code, field_list=[]), code
        )

    def fetch_more_info(self, code: str) -> dict[str, Any]:
        return mapping_from_payload(
            self._require_tq().get_more_info(stock_code=code, field_list=[]), code
        )

    def fetch_share_capital(
        self, code: str, observation_dates: tuple[date, ...]
    ) -> list[dict[str, Any]]:
        values = [item.strftime("%Y%m%d") for item in sorted(set(observation_dates))]
        payload = self._require_tq().get_gb_info(
            stock_code=code,
            date_list=values,
            count=len(values),
        )
        return records_from_payload(payload, code)

    def fetch_financial_data(
        self,
        code: str,
        start: date,
        end: date,
        report_type: str,
    ) -> list[dict[str, Any]]:
        payload = self._require_tq().get_financial_data(
            stock_list=[code],
            field_list=list(FINANCIAL_FIELDS),
            start_time=start.strftime("%Y%m%d"),
            end_time=end.strftime("%Y%m%d"),
            report_type=report_type,
        )
        return records_from_payload(payload, code)

    def fetch_gp_trading(self, code: str, start: date, end: date) -> list[dict[str, Any]]:
        payload = self._require_tq().get_gpjy_value(
            stock_list=[code],
            field_list=list(GP_FIELDS),
            start_time=start.strftime("%Y%m%d"),
            end_time=end.strftime("%Y%m%d"),
        )
        return field_series_records(payload, code)

    def fetch_gp_single(self, code: str) -> dict[str, Any]:
        payload = self._require_tq().get_gp_one_data(
            stock_list=[code], field_list=list(GO_FIELDS)
        )
        return mapping_from_payload(payload, code)

    def fetch_relations(self, code: str) -> list[dict[str, Any]]:
        return records_from_payload(self._require_tq().get_relation(stock_code=code), code)

    def _require_tq(self) -> Any:
        if not self._connected or self.tq is None:
            raise RuntimeError("通达信数据源尚未连接。")
        return self.tq


def records_from_payload(payload: Any, code: str | None = None) -> list[dict[str, Any]]:
    """把 TQ 的 DataFrame、字典或列表统一为记录列表。"""
    payload = _unwrap_code(payload, code)
    if payload is None:
        return []
    if isinstance(payload, pd.DataFrame):
        frame = payload.copy()
        if not isinstance(frame.index, pd.RangeIndex):
            index_name = frame.index.name or "Date"
            if index_name in frame.columns:
                index_name = "_index"
            frame.insert(0, index_name, frame.index)
        return [_clean_mapping(item) for item in frame.to_dict(orient="records")]
    if isinstance(payload, list):
        return [
            _clean_mapping(item) if isinstance(item, dict) else {"Value": _json_value(item)}
            for item in payload
        ]
    if isinstance(payload, dict):
        _raise_for_error(payload)
        value = payload.get("Value") if set(payload).issubset({"ErrorId", "Error", "Value"}) else payload
        if value is not payload:
            return records_from_payload(value, code)
        if _is_columnar(payload):
            return [
                _clean_mapping(item)
                for item in pd.DataFrame(payload).to_dict(orient="records")
            ]
        return [_clean_mapping(payload)]
    return [{"Value": _json_value(payload)}]


def mapping_from_payload(payload: Any, code: str | None = None) -> dict[str, Any]:
    """把单股票快照规范化为一个字典。"""
    records = records_from_payload(payload, code)
    if not records:
        return {}
    if len(records) == 1:
        return records[0]
    return {"Records": records}


def field_series_records(payload: Any, code: str | None = None) -> list[dict[str, Any]]:
    """把 ``GP字段 -> [{Date, Value}]`` 结构合并为按日期记录。"""
    value = _unwrap_code(payload, code)
    if not isinstance(value, dict):
        return records_from_payload(value, code)
    _raise_for_error(value)
    by_date: dict[str, dict[str, Any]] = {}
    for field, observations in value.items():
        if not isinstance(observations, list):
            continue
        for observation in observations:
            if not isinstance(observation, dict) or not observation.get("Date"):
                continue
            record_date = str(observation["Date"])
            record = by_date.setdefault(record_date, {"Date": record_date})
            record[str(field)] = _json_value(observation.get("Value"))
    if by_date:
        return [by_date[key] for key in sorted(by_date)]
    return records_from_payload(value, code)


def _unwrap_code(payload: Any, code: str | None) -> Any:
    if code and isinstance(payload, dict):
        for candidate in (code, code.upper(), code.lower()):
            if candidate in payload:
                return payload[candidate]
    return payload


def _raise_for_error(payload: dict[str, Any]) -> None:
    error_id = payload.get("ErrorId")
    if error_id is not None and str(error_id) not in {"", "0"}:
        raise RuntimeError(f"通达信错误 {error_id}: {payload.get('Error', '')}")


def _is_columnar(payload: dict[str, Any]) -> bool:
    values = list(payload.values())
    if not values or not all(isinstance(value, (list, tuple, pd.Series)) for value in values):
        return False
    lengths = {len(value) for value in values}
    return len(lengths) == 1


def _clean_mapping(value: dict[str, Any]) -> dict[str, Any]:
    return {str(key): _json_value(item) for key, item in value.items()}


def _json_value(value: Any) -> Any:
    if isinstance(value, (date, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, dict):
        return _clean_mapping(value)
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if hasattr(value, "item"):
        try:
            value = value.item()
        except (TypeError, ValueError):
            pass
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def field_names(records: Iterable[dict[str, Any]]) -> tuple[str, ...]:
    """返回记录中的稳定排序字段集合。"""
    return tuple(sorted({str(key) for record in records for key in record}))
