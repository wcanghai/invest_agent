"""日报领域中的稳定数据模型。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True)
class MarketReportSnapshot:
    """一次成功采集产生的 Markdown 和结构化快照。"""

    source_date: date
    generated_at: datetime
    markdown: str
    data: dict[str, Any]

    def persisted_data(self) -> dict[str, Any]:
        return {
            "source_date": self.source_date.isoformat(),
            "generated_at": self.generated_at.isoformat(timespec="seconds"),
            "data": self.data,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.persisted_data(), "markdown": self.markdown}


@dataclass(frozen=True)
class DailyReportRecord:
    """SQLite 中一条不可变的每日完整报告。"""

    report_date: date
    source_date: date
    generated_at: datetime
    markdown: str
    snapshot: dict[str, Any]
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_date": self.report_date.isoformat(),
            "source_date": self.source_date.isoformat(),
            "generated_at": self.generated_at.isoformat(timespec="seconds"),
            "created_at": self.created_at.isoformat(timespec="seconds"),
            "markdown": self.markdown,
            "snapshot": self.snapshot,
        }
