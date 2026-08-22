"""股票全维度数据采集编排。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Callable, Protocol

from tdx_history.config import Instrument
from tdx_history.service import HistorySyncService, _subtract_years
from tdx_history.stock_data.repository import StockDataRepository
from tdx_history.stock_data.source import field_names


class StockDataSource(Protocol):
    def fetch_daily(self, code: str, start: date, end: date, dividend_type: str) -> Any: ...
    def fetch_dividends(self, code: str, start: date, end: date) -> list[dict[str, Any]]: ...
    def fetch_market_snapshot(self, code: str) -> dict[str, Any]: ...
    def fetch_stock_info(self, code: str) -> dict[str, Any]: ...
    def fetch_more_info(self, code: str) -> dict[str, Any]: ...
    def fetch_share_capital(
        self, code: str, observation_dates: tuple[date, ...]
    ) -> list[dict[str, Any]]: ...
    def fetch_financial_data(
        self, code: str, start: date, end: date, report_type: str
    ) -> list[dict[str, Any]]: ...
    def fetch_gp_trading(self, code: str, start: date, end: date) -> list[dict[str, Any]]: ...
    def fetch_gp_single(self, code: str) -> dict[str, Any]: ...
    def fetch_relations(self, code: str) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class DatasetResult:
    code: str
    dataset: str
    status: str
    record_count: int
    field_count: int
    fields: tuple[str, ...]
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["fields"] = list(self.fields)
        return value


class StockDataSyncService:
    """逐股票、逐数据集采集，任一失败不会中断其余接口。"""

    def __init__(
        self,
        repository: StockDataRepository,
        source: StockDataSource,
        years: int = 10,
    ):
        if years <= 0:
            raise ValueError("years 必须大于 0。")
        self.repository = repository
        self.source = source
        self.years = years

    def sync(
        self,
        instruments: tuple[Instrument, ...],
        sample_types: dict[str, str],
        today: date | None = None,
        history_end: date | None = None,
        on_result: Callable[[int, int, DatasetResult], None] | None = None,
    ) -> list[DatasetResult]:
        effective_today = today or date.today()
        effective_history_end = history_end or effective_today
        if effective_history_end > effective_today:
            raise ValueError("history_end 不能晚于采集日期。")
        start = _subtract_years(effective_history_end, self.years)
        run_id = self.repository.start_collection_run(len(instruments))
        results: list[DatasetResult] = []

        for instrument in instruments:
            self.repository.upsert_instrument(instrument)
            self.repository.upsert_sample_tag(
                instrument.code, sample_types.get(instrument.code, "未分类样本")
            )

        daily_results = HistorySyncService(
            self.repository, self.source, years=self.years
        ).sync(instruments, today=effective_history_end)
        for daily in daily_results:
            result = DatasetResult(
                daily.code,
                "daily_bars",
                "failed" if daily.status == "failed" else ("empty" if daily.total_rows == 0 else "success"),
                daily.total_rows,
                7 if daily.total_rows else 0,
                ("trade_date", "open", "high", "low", "close", "volume", "amount")
                if daily.total_rows
                else (),
                daily.message,
            )
            self._record_result(run_id, result, results, len(instruments), on_result)

        capital_dates = _quarter_observation_dates(start, effective_history_end)
        jobs = (
            ("corporate_actions", lambda code: self.source.fetch_dividends(code, start, effective_history_end)),
            ("market_snapshot", lambda code: _one(self.source.fetch_market_snapshot(code))),
            ("stock_info", lambda code: _one(self.source.fetch_stock_info(code))),
            ("more_info", lambda code: _one(self.source.fetch_more_info(code))),
            ("share_capital", lambda code: self.source.fetch_share_capital(code, capital_dates)),
            (
                "financial_report_time",
                lambda code: self.source.fetch_financial_data(code, start, effective_history_end, "report_time"),
            ),
            (
                "financial_announce_time",
                lambda code: self.source.fetch_financial_data(code, start, effective_history_end, "announce_time"),
            ),
            ("gp_trading", lambda code: self.source.fetch_gp_trading(code, start, effective_history_end)),
            ("gp_single", lambda code: _one(self.source.fetch_gp_single(code))),
            ("relations", lambda code: self.source.fetch_relations(code)),
        )

        for instrument in instruments:
            for dataset, fetch in jobs:
                try:
                    records = fetch(instrument.code)
                    fields = field_names(records)
                    self._persist(instrument.code, dataset, records, effective_today)
                    result = DatasetResult(
                        instrument.code,
                        dataset,
                        "success" if records else "empty",
                        len(records),
                        len(fields),
                        fields,
                        "" if records else "接口未返回数据。",
                    )
                except Exception as error:  # 单接口故障隔离
                    result = DatasetResult(
                        instrument.code,
                        dataset,
                        "failed",
                        0,
                        0,
                        (),
                        f"{type(error).__name__}: {error}",
                    )
                self._record_result(run_id, result, results, len(instruments), on_result)

        failed = sum(item.status == "failed" for item in results)
        self.repository.finish_collection_run(
            run_id,
            failed,
            f"数据集结果 {len(results)}，失败 {failed}，空数据 {sum(r.status == 'empty' for r in results)}",
        )
        return results

    def _persist(
        self, code: str, dataset: str, records: list[dict[str, Any]], observed_date: date
    ) -> None:
        if dataset == "corporate_actions":
            self.repository.insert_corporate_actions(code, records)
        elif dataset == "share_capital":
            self.repository.upsert_share_capital(code, records)
        elif dataset.startswith("financial_"):
            self.repository.upsert_financial_facts(code, dataset.removeprefix("financial_"), records)
        elif dataset == "relations":
            self.repository.replace_relations(code, observed_date, records)
        else:
            self.repository.upsert_dataset_records(code, dataset, observed_date, records)

    def _record_result(
        self,
        run_id: int,
        result: DatasetResult,
        results: list[DatasetResult],
        instrument_count: int,
        on_result: Callable[[int, int, DatasetResult], None] | None,
    ) -> None:
        self.repository.add_collection_result(
            run_id,
            result.code,
            result.dataset,
            result.status,
            result.record_count,
            result.field_count,
            result.message,
        )
        results.append(result)
        if on_result:
            on_result(len(results), instrument_count * 11, result)


def _one(value: dict[str, Any]) -> list[dict[str, Any]]:
    return [value] if value else []


def _quarter_observation_dates(start: date, end: date) -> tuple[date, ...]:
    values: set[date] = {start, end}
    for year in range(start.year, end.year + 1):
        for month, day in ((3, 31), (6, 30), (9, 30), (12, 31)):
            candidate = date(year, month, day)
            if start <= candidate <= end:
                values.add(candidate)
    return tuple(sorted(values))
