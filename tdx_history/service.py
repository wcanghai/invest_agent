"""十年回补与日常增量同步编排。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, Protocol

import pandas as pd

from tdx_history.config import Instrument
from tdx_history.repository import HistoryRepository


class DailySource(Protocol):
    def fetch_daily(
        self, code: str, start: date, end: date, dividend_type: str
    ) -> pd.DataFrame: ...


@dataclass(frozen=True)
class SyncResult:
    code: str
    status: str
    query_start: date | None
    query_end: date | None
    received_rows: int
    inserted_rows: int
    total_rows: int
    message: str = ""


class HistorySyncService:
    """对每只证券独立增量同步，单只失败不影响其他证券。"""

    def __init__(self, repository: HistoryRepository, source: DailySource, years: int = 10):
        if years <= 0:
            raise ValueError("years 必须大于 0。")
        self.repository = repository
        self.source = source
        self.years = years

    def sync(
        self,
        instruments: tuple[Instrument, ...],
        today: date | None = None,
        on_result: Callable[[int, int, SyncResult], None] | None = None,
    ) -> list[SyncResult]:
        effective_today = today or date.today()
        run_id = self.repository.start_run(len(instruments))
        results: list[SyncResult] = []
        for instrument in instruments:
            try:
                result = self._sync_one(instrument, effective_today)
            except Exception as error:  # 单只失败隔离，并由结果显式报告
                result = SyncResult(
                    code=instrument.code,
                    status="failed",
                    query_start=None,
                    query_end=None,
                    received_rows=0,
                    inserted_rows=0,
                    total_rows=self.repository.count_bars(instrument.code),
                    message=f"{type(error).__name__}: {error}",
                )
            results.append(result)
            if on_result:
                on_result(len(results), len(instruments), result)
        inserted = sum(result.inserted_rows for result in results)
        failed = sum(result.status == "failed" for result in results)
        self.repository.finish_run(
            run_id,
            inserted_rows=inserted,
            failed_codes=failed,
            message=f"成功/跳过 {len(results) - failed}，失败 {failed}",
        )
        return results

    def _sync_one(self, instrument: Instrument, today: date) -> SyncResult:
        self.repository.upsert_instrument(instrument)
        cutoff = _subtract_years(today, self.years)
        latest = self.repository.latest_date(instrument.code)
        start = max(cutoff, latest + timedelta(days=1)) if latest else cutoff
        if start > today:
            return SyncResult(
                instrument.code,
                "up_to_date",
                None,
                None,
                0,
                0,
                self.repository.count_bars(instrument.code),
                "数据已更新到当前日期。",
            )

        frame = self.source.fetch_daily(instrument.code, start, today, instrument.dividend_type)
        if frame.empty and latest is None:
            raise RuntimeError(
                f"{instrument.code} 首次回补未返回任何日线，请检查代码和客户端数据。"
            )
        if not frame.empty:
            dates = pd.to_datetime(frame["trade_date"], errors="coerce").dt.date
            frame = frame.loc[(dates >= start) & (dates <= today)].copy()
        inserted = self.repository.insert_new_bars(instrument.code, frame)
        return SyncResult(
            instrument.code,
            "updated" if inserted else "no_new_data",
            start,
            today,
            len(frame),
            inserted,
            self.repository.count_bars(instrument.code),
            "" if inserted else "查询区间内无新的交易日。",
        )


def _subtract_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year - years)
    except ValueError:  # 2 月 29 日
        return value.replace(year=value.year - years, day=28)
