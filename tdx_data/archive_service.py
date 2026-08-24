"""通达信股票归档业务流程。"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from tdx_data.additional_data import json_ready
from tdx_data.client import TdxClient
from tdx_data.repository import (
    finish_run,
    insert_daily,
    latest_date,
    latest_history_date,
    open_database,
    replace_asset_groups,
    replace_relations,
    save_raw,
    start_run,
    upsert_corporate_actions,
    upsert_asset,
    upsert_financial_reports,
    upsert_flat,
    upsert_share_capital_history,
)


DEFAULT_USER_DIR = Path(r"D:\SoftWare\TDX\PYPlugins\user")
DEFAULT_DATABASE = Path("data/tdx_archive.sqlite3")


@dataclass(frozen=True)
class ArchiveResult:
    requested_codes: int
    inserted_bars: int
    failed_codes: int
    database_path: Path
    archived_history_records: int = 0


class ArchiveClient(Protocol):
    """归档流程依赖的最小只读客户端边界。"""

    def connect(self) -> None: ...
    def close(self) -> None: ...
    def list_stocks(self, market: str) -> list[dict[str, Any]]: ...
    def daily(self, code: str, start: date, end: date) -> list[dict[str, Any]]: ...
    def stock_info(self, code: str) -> dict[str, Any]: ...
    def more_info(self, code: str) -> dict[str, Any]: ...
    def relations(self, code: str) -> list[dict[str, Any]]: ...
    def financial_history(self, code: str, start: date, end: date) -> Any: ...
    def share_capital_history(self, code: str, start: date, end: date) -> Any: ...
    def corporate_actions(self, code: str, start: date, end: date) -> Any: ...
    def market_snapshot(self, code: str) -> Any: ...
    def gp_trading(self, code: str, start: date, end: date) -> Any: ...
    def gp_single(self, code: str) -> Any: ...


def archive_stocks(
    *,
    tdx_user_dir: Path,
    database_path: Path,
    market: str = "5",
    start_date: date = date(2004, 1, 1),
    end_date: date | None = None,
    limit: int = 10,
    selected_assets: list[dict[str, Any]] | None = None,
    include_extended_data: bool = True,
    history_overlap_days: int = 31,
    snapshot_date: date | None = None,
    client_factory: Callable[[Path, Path], ArchiveClient] = TdxClient,
) -> ArchiveResult:
    """采集日线、每日快照和历史基本面并幂等写入独立归档库。"""
    actual_end = end_date or date.today()
    observed = snapshot_date or actual_end
    if start_date > actual_end:
        raise ValueError("start_date 不能晚于 end_date")
    if history_overlap_days < 0:
        raise ValueError("history_overlap_days 不能小于 0")
    if not tdx_user_dir.is_dir():
        raise FileNotFoundError(f"未找到通达信插件目录：{tdx_user_dir}")
    con = open_database(database_path)
    client = client_factory(tdx_user_dir, Path(__file__).resolve())
    run_id = start_run(con, 0, now())
    inserted = failed = history_records = 0
    assets: list[dict[str, Any]] = []
    try:
        client.connect()
        listed = selected_assets if selected_assets is not None else client.list_stocks(market)
        assets = select_assets(listed, limit)
        con.execute(
            "UPDATE sync_runs SET requested_codes=? WHERE id=?", (len(assets), run_id)
        )
        con.commit()
        print(f"发现股票 {len(listed)} 只，本次处理 {len(assets)} 只")
        for index, asset in enumerate(assets, 1):
            code, name = asset["Code"], asset["Name"]
            try:
                captured_at = now()
                groups = [str(value) for value in asset.get("Groups", [])]
                upsert_asset(con, code, name, "targeted" if groups else market, captured_at)
                if "Groups" in asset:
                    replace_asset_groups(
                        con,
                        code,
                        groups,
                        captured_at,
                        _optional_int(asset.get("LiquidityRank")),
                        _optional_float(asset.get("LatestAmount")),
                        observed,
                    )
                latest = latest_date(con, code)
                start = latest + timedelta(days=1) if latest else start_date
                if start <= actual_end:
                    inserted += insert_daily(
                        con,
                        code,
                        client.daily(code, start, actual_end),
                        actual_end,
                        captured_at,
                    )
                info = client.stock_info(code)
                more = client.more_info(code)
                relations = client.relations(code)
                save_raw(con, code, "stock_info", observed, info, "snapshot", captured_at)
                save_raw(con, code, "more_info", observed, more, "snapshot", captured_at)
                save_raw(con, code, "relations", observed, relations, "snapshot", captured_at)
                upsert_flat(con, "stock_info_flat", code, observed, info)
                upsert_flat(con, "more_info_flat", code, observed, more)
                replace_relations(con, code, observed, relations)
                extended_errors: list[str] = []
                if include_extended_data:
                    added, extended_errors = archive_extended_data(
                        con,
                        client,
                        code,
                        start_date,
                        actual_end,
                        observed,
                        history_overlap_days,
                        captured_at,
                        include_financial_history="高流动性ETF" not in groups,
                    )
                    history_records += added
                con.commit()
                if extended_errors:
                    failed += 1
                print(
                    f"[{index}/{len(assets)}] {code} {name}，累计新增日线 {inserted}，"
                    f"历史记录处理 {history_records}"
                    + (f"；附加接口失败：{'; '.join(extended_errors)}" if extended_errors else ""),
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
            f"历史记录处理 {history_records}，"
            f"数据库 {database_path.resolve()}"
        )
        return ArchiveResult(len(assets), inserted, failed, database_path, history_records)
    finally:
        client.close()
        con.close()


def select_assets(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        code = str(row.get("Code", "")).strip().upper()
        if not code or code in seen:
            continue
        seen.add(code)
        result.append(
            {
                "Code": code,
                "Name": str(row.get("Name", code)).strip(),
                **{key: row[key] for key in ("Groups", "LiquidityRank", "LatestAmount") if key in row},
            }
        )
        if limit > 0 and len(result) >= limit:
            break
    return result


def archive_extended_data(
    connection: sqlite3.Connection,
    client: ArchiveClient,
    code: str,
    initial_start: date,
    end: date,
    observed: date,
    overlap_days: int,
    captured_at: str,
    include_financial_history: bool = True,
) -> tuple[int, list[str]]:
    """归档历史基本面和每日动态数据；单接口失败时保留其他成功结果。"""
    total = 0
    errors: list[str] = []

    def capture(dataset: str, operation: Callable[[], int]) -> None:
        nonlocal total
        connection.execute("SAVEPOINT extended_dataset")
        try:
            total += operation()
        except Exception as error:  # 单接口故障不丢弃同股票的其他成功数据。
            connection.execute("ROLLBACK TO SAVEPOINT extended_dataset")
            errors.append(f"{dataset}={type(error).__name__}: {error}")
        finally:
            connection.execute("RELEASE SAVEPOINT extended_dataset")

    if include_financial_history:
        financial_start = incremental_start(
            latest_history_date(connection, "financial_reports", "announce_date", code),
            initial_start,
            overlap_days,
        )
        capture(
            "financial_history",
            lambda: _archive_financial(
                connection, client, code, financial_start, end, observed, captured_at
            ),
        )

    capital_start = incremental_start(
        latest_history_date(connection, "share_capital_history", "effective_date", code),
        initial_start,
        overlap_days,
    )
    capture(
        "share_capital_history",
        lambda: _archive_share_capital(
            connection, client, code, capital_start, end, observed, captured_at
        ),
    )

    action_start = incremental_start(
        latest_history_date(connection, "corporate_actions", "action_date", code),
        initial_start,
        overlap_days,
    )
    capture(
        "corporate_actions",
        lambda: _archive_corporate_actions(
            connection, client, code, action_start, end, observed, captured_at
        ),
    )
    capture(
        "market_snapshot",
        lambda: _archive_snapshot(
            connection, code, "market_snapshot", observed, client.market_snapshot(code), captured_at
        ),
    )
    capture(
        "gp_single",
        lambda: _archive_snapshot(
            connection, code, "gp_single", observed, client.gp_single(code), captured_at
        ),
    )
    capture(
        "gp_trading",
        lambda: _archive_snapshot(
            connection,
            code,
            "gp_trading",
            observed,
            client.gp_trading(code, end, end),
            captured_at,
        ),
    )
    return total, errors


def incremental_start(latest: date | None, initial: date, overlap_days: int) -> date:
    """历史接口使用重叠窗口吸收源端修订，同时不早于首次起点。"""
    return max(initial, latest - timedelta(days=overlap_days)) if latest else initial


def _archive_financial(
    connection: sqlite3.Connection,
    client: ArchiveClient,
    code: str,
    start: date,
    end: date,
    observed: date,
    captured_at: str,
) -> int:
    value = json_ready(client.financial_history(code, start, end))
    save_raw(connection, code, "financial_history", observed, value, _range_key(start, end), captured_at)
    return upsert_financial_reports(connection, code, rows_for_code(value, code), captured_at)


def _archive_share_capital(
    connection: sqlite3.Connection,
    client: ArchiveClient,
    code: str,
    start: date,
    end: date,
    observed: date,
    captured_at: str,
) -> int:
    value = json_ready(client.share_capital_history(code, start, end))
    save_raw(connection, code, "share_capital_history", observed, value, _range_key(start, end), captured_at)
    return upsert_share_capital_history(connection, code, rows_for_code(value, code), captured_at)


def _archive_corporate_actions(
    connection: sqlite3.Connection,
    client: ArchiveClient,
    code: str,
    start: date,
    end: date,
    observed: date,
    captured_at: str,
) -> int:
    value = json_ready(client.corporate_actions(code, start, end))
    save_raw(connection, code, "corporate_actions", observed, value, _range_key(start, end), captured_at)
    return upsert_corporate_actions(connection, code, rows_for_code(value, code), captured_at)


def _archive_snapshot(
    connection: sqlite3.Connection,
    code: str,
    dataset: str,
    observed: date,
    value: Any,
    captured_at: str,
) -> int:
    save_raw(connection, code, dataset, observed, json_ready(value), "snapshot", captured_at)
    return 1


def rows_for_code(value: Any, code: str) -> list[dict[str, Any]]:
    """从 TQ 的代码包裹结构中提取记录列表。"""
    if isinstance(value, dict) and code in value:
        return rows_for_code(value[code], code)
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict) and any(key in value for key in ("Date", "date", "tag_time")):
        return [value]
    return []


def _range_key(start: date, end: date) -> str:
    return f"{start.isoformat()}:{end.isoformat()}"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)
