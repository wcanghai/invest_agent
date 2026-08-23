"""通达信股票归档业务流程。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from tdx_data.client import TdxClient
from tdx_data.repository import (
    finish_run,
    insert_daily,
    latest_date,
    open_database,
    replace_relations,
    save_raw,
    start_run,
    upsert_asset,
    upsert_flat,
)


DEFAULT_USER_DIR = Path(r"D:\SoftWare\TDX\PYPlugins\user")
DEFAULT_DATABASE = Path("data/tdx_archive.sqlite3")


@dataclass(frozen=True)
class ArchiveResult:
    requested_codes: int
    inserted_bars: int
    failed_codes: int
    database_path: Path


class ArchiveClient(Protocol):
    """归档流程依赖的最小只读客户端边界。"""

    def connect(self) -> None: ...
    def close(self) -> None: ...
    def list_stocks(self, market: str) -> list[dict[str, Any]]: ...
    def daily(self, code: str, start: date, end: date) -> list[dict[str, Any]]: ...
    def stock_info(self, code: str) -> dict[str, Any]: ...
    def more_info(self, code: str) -> dict[str, Any]: ...
    def relations(self, code: str) -> list[dict[str, Any]]: ...


def archive_stocks(
    *,
    tdx_user_dir: Path,
    database_path: Path,
    market: str = "5",
    start_date: date = date(2004, 1, 1),
    end_date: date | None = None,
    limit: int = 10,
    client_factory: Callable[[Path, Path], ArchiveClient] = TdxClient,
) -> ArchiveResult:
    """采集股票日线和维度快照并幂等写入独立归档库。"""
    actual_end = end_date or date.today()
    if start_date > actual_end:
        raise ValueError("start_date 不能晚于 end_date")
    if not tdx_user_dir.is_dir():
        raise FileNotFoundError(f"未找到通达信插件目录：{tdx_user_dir}")
    con = open_database(database_path)
    client = client_factory(tdx_user_dir, Path(__file__).resolve())
    run_id = start_run(con, 0, now())
    inserted = failed = 0
    assets: list[dict[str, str]] = []
    try:
        client.connect()
        listed = client.list_stocks(market)
        assets = select_assets(listed, limit)
        con.execute(
            "UPDATE sync_runs SET requested_codes=? WHERE id=?", (len(assets), run_id)
        )
        con.commit()
        print(f"发现股票 {len(listed)} 只，本次处理 {len(assets)} 只")
        for index, asset in enumerate(assets, 1):
            code, name = asset["Code"], asset["Name"]
            try:
                upsert_asset(con, code, name, market, now())
                latest = latest_date(con, code)
                start = latest + timedelta(days=1) if latest else start_date
                observed = date.today()
                if start <= actual_end:
                    inserted += insert_daily(
                        con,
                        code,
                        client.daily(code, start, actual_end),
                        actual_end,
                        now(),
                    )
                info = client.stock_info(code)
                more = client.more_info(code)
                relations = client.relations(code)
                save_raw(con, code, "stock_info", observed, info, "snapshot", now())
                save_raw(con, code, "more_info", observed, more, "snapshot", now())
                save_raw(con, code, "relations", observed, relations, "snapshot", now())
                upsert_flat(con, "stock_info_flat", code, observed, info)
                upsert_flat(con, "more_info_flat", code, observed, more)
                replace_relations(con, code, observed, relations)
                con.commit()
                print(
                    f"[{index}/{len(assets)}] {code} {name}，累计新增日线 {inserted}",
                    flush=True,
                )
            except Exception as error:
                failed += 1
                con.rollback()
                print(
                    f"[{index}/{len(assets)}] {code} 失败：{type(error).__name__}: {error}",
                    flush=True,
                )
        finish_run(con, run_id, inserted, failed, now())
        con.commit()
        print(
            f"完成：股票 {len(assets)}，新增日线 {inserted}，失败 {failed}，"
            f"数据库 {database_path.resolve()}"
        )
        return ArchiveResult(len(assets), inserted, failed, database_path)
    finally:
        client.close()
        con.close()


def select_assets(rows: list[dict[str, Any]], limit: int) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        code = str(row.get("Code", "")).strip().upper()
        if not code or code in seen:
            continue
        seen.add(code)
        result.append({"Code": code, "Name": str(row.get("Name", code)).strip()})
        if limit > 0 and len(result) >= limit:
            break
    return result


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
