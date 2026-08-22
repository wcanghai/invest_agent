"""FastAPI 每日市场报告网站。"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import bleach
import markdown
from bleach.linkifier import Linker
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from market_report.service import MarketReportSnapshot, generate_market_report
from market_web.repository import DailyReportRecord, DailyReportRepository
from market_web.service import DailyReportService, ReportGenerator


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = Path(__file__).resolve().parent
DEFAULT_DATABASE = PROJECT_ROOT / "data" / "market_reports.sqlite3"
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "market_universe.json"
DEFAULT_HISTORY = PROJECT_ROOT / "data" / "history"

ALLOWED_TAGS = {
    "a", "blockquote", "br", "code", "em", "h1", "h2", "h3", "h4",
    "hr", "li", "ol", "p", "pre", "strong", "table", "tbody", "td",
    "th", "thead", "tr", "ul",
}


def _external_quote_link(
    attributes: dict[Any, str], new: bool = False
) -> dict[Any, str]:
    """东方财富链接在新页签打开，并阻断新页签反向控制原页面。"""
    del new
    href = attributes.get((None, "href"), "")
    if href.startswith("https://quote.eastmoney.com/"):
        attributes[(None, "target")] = "_blank"
        attributes[(None, "rel")] = "noopener noreferrer"
    return attributes


EASTMONEY_LINKER = Linker(callbacks=[_external_quote_link])


def create_app(
    database_path: Path = DEFAULT_DATABASE,
    config_path: Path = DEFAULT_CONFIG,
    history_root: Path = DEFAULT_HISTORY,
    generator: ReportGenerator | None = None,
) -> FastAPI:
    repository = DailyReportRepository(database_path)
    if generator is None:
        generator = lambda generated_at: generate_market_report(
            config_path,
            history_root,
            Path(__file__).resolve(),
            generated_at,
        )
    report_service = DailyReportService(repository, generator)
    templates = Jinja2Templates(directory=WEB_ROOT / "templates")

    app = FastAPI(title="多市场行情日报", version="1.0.0")
    app.mount("/static", StaticFiles(directory=WEB_ROOT / "static"), name="static")
    app.state.report_service = report_service
    app.state.repository = repository

    @app.get("/", response_class=HTMLResponse)
    def today_page(request: Request) -> HTMLResponse:
        try:
            record = report_service.get_or_create_today()
        except Exception as error:  # 数据源错误需展示为网页，且不得写入数据库
            return templates.TemplateResponse(
                request,
                "error.html",
                {
                    "message": str(error),
                    "history": report_service.list_reports(),
                },
                status_code=503,
            )
        return _report_response(templates, request, record, report_service.list_reports())

    @app.get("/reports/{report_date}", response_class=HTMLResponse)
    def historical_page(request: Request, report_date: date) -> HTMLResponse:
        record = report_service.get(report_date)
        if record is None:
            raise HTTPException(status_code=404, detail="该日期没有已保存的日报。")
        return _report_response(templates, request, record, report_service.list_reports())

    @app.get("/api/reports")
    def report_index() -> dict[str, Any]:
        records = report_service.list_reports()
        return {
            "count": len(records),
            "reports": [
                {
                    "report_date": record.report_date.isoformat(),
                    "generated_at": record.generated_at.isoformat(timespec="seconds"),
                    "source_date": record.snapshot.get("source_date"),
                }
                for record in records
            ],
        }

    @app.get("/api/reports/today")
    def today_api() -> dict[str, Any]:
        try:
            return report_service.get_or_create_today().to_dict()
        except Exception as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @app.get("/api/reports/{report_date}")
    def report_api(report_date: date) -> dict[str, Any]:
        record = report_service.get(report_date)
        if record is None:
            raise HTTPException(status_code=404, detail="该日期没有已保存的日报。")
        return record.to_dict()

    @app.get("/api/offerings/today")
    def today_offerings_api() -> dict[str, Any]:
        """从今日已持久化日报读取新股、新债事件。"""
        try:
            return _offering_payload(report_service.get_or_create_today())
        except Exception as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @app.get("/api/offerings/{report_date}")
    def historical_offerings_api(report_date: date) -> dict[str, Any]:
        """读取指定历史日报中的新股、新债事件，不触发补采。"""
        record = report_service.get(report_date)
        if record is None:
            raise HTTPException(status_code=404, detail="该日期没有已保存的日报。")
        return _offering_payload(record)

    @app.get("/health")
    def health() -> dict[str, Any]:
        repository.check()
        return {"status": "ok", "stored_reports": repository.count()}

    return app


def _report_response(
    templates: Jinja2Templates,
    request: Request,
    record: DailyReportRecord,
    history: list[DailyReportRecord],
) -> HTMLResponse:
    breadth = record.snapshot.get("data", {}).get("market_breadth", {})
    total = breadth.get("三市合计", {})
    offerings = _offering_items(record)
    return templates.TemplateResponse(
        request,
        "report.html",
        {
            "record": record,
            "history": history,
            "report_html": _markdown_html(record.markdown),
            "source_date": record.snapshot.get("source_date", "—"),
            "total_amount": _format_amount(total.get("amount")),
            "up_count": total.get("up", "—"),
            "down_count": total.get("down", "—"),
            "offering_count": len(offerings),
            "today_subscription_count": sum(
                "今日申购" in str(item.get("event_status", "")) for item in offerings
            ),
        },
    )


def _offering_payload(record: DailyReportRecord) -> dict[str, Any]:
    items = _offering_items(record)
    return {
        "report_date": record.report_date.isoformat(),
        "generated_at": record.generated_at.isoformat(timespec="seconds"),
        "count": len(items),
        "items": items,
    }


def _offering_items(record: DailyReportRecord) -> list[dict[str, Any]]:
    value = record.snapshot.get("data", {}).get("ipo_calendar", [])
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _markdown_html(value: str) -> Markup:
    rendered = markdown.markdown(value, extensions=["tables", "sane_lists"])
    clean = bleach.clean(
        rendered,
        tags=ALLOWED_TAGS,
        attributes={"a": ["href", "title"]},
        protocols={"https"},
        strip=True,
    )
    return Markup(EASTMONEY_LINKER.linkify(clean))


def _format_amount(value: Any) -> str:
    if value is None:
        return "—"
    return f"{float(value) / 10_000:,.2f} 亿元"
