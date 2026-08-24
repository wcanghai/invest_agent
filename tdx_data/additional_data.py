"""独立演示和检查通达信扩展只读数据接口。

本文件不写数据库，只负责：

1. 说明每个额外接口可以获取什么数据；
2. 使用可注入的 TQ 对象调用接口，便于离线测试；
3. 将 pandas/通达信返回值转换为可打印的 JSON；
4. 提供结构示意样例，或连接本机通达信打印真实返回。

结构示意样例只用于展示典型返回形状，不代表真实股票、真实数值或所有 TQ 版本的
完整字段。尤其 Fn、GP、GO 字段的精确定义应以本机通达信 TQ 插件文档为准。

只查看接口说明和样例，不连接通达信：

    python -m tdx_data.additional_data --sample-only

获取一只股票的全部额外数据并打印 JSON：

    python -m tdx_data.additional_data --code 600000.SH

只获取公司行为和股本历史：

    python -m tdx_data.additional_data --code 600000.SH `
        --dataset corporate_actions share_capital
"""

from __future__ import annotations

import argparse
import calendar
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Sequence

import pandas as pd

from tdx_data.client import FINANCIAL_FIELDS, GO_FIELDS, GP_FIELDS, TdxClient


DEFAULT_USER_DIR = Path(r"D:\SoftWare\TDX\PYPlugins\user")
@dataclass(frozen=True)
class DatasetDescription:
    """一个额外数据集的接口说明和结构示意样例。"""

    interface: str
    description: str
    sample: Any


DATASET_DESCRIPTIONS: dict[str, DatasetDescription] = {
    "corporate_actions": DatasetDescription(
        "get_divid_factors",
        "获取指定日期范围内的分红、送股、配股、配股价等公司行为/除权因子记录。",
        [
            {
                "Date": "20250620",
                "Type": 1,
                "Bonus": 2.0,
                "ShareBonus": 1.0,
                "Allotment": 0.0,
                "AllotPrice": 0.0,
            }
        ],
    ),
    "market_snapshot": DatasetDescription(
        "get_market_snapshot",
        "获取单只股票的实时/最近市场快照；空 field_list 请求插件提供的全部字段。",
        {
            "Now": 10.52,
            "Open": 10.35,
            "High": 10.66,
            "Low": 10.21,
            "Volume": 123456.0,
            "Amount": 129876543.0,
            "Buyp": [10.51, 10.50],
            "Sellp": [10.52, 10.53],
            "ErrorId": "0",
        },
    ),
    "share_capital": DatasetDescription(
        "get_gb_info",
        "按一组观察日期获取流通股本、总股本等股本结构，可用于观察季度变化。",
        [{"Date": "20250630", "Ltgb": 1_000_000_000, "Zgb": 1_200_000_000}],
    ),
    "financial_report_time": DatasetDescription(
        "get_financial_data(report_type='report_time')",
        "按报告期读取 Fn193-Fn200 财务字段，适合按财报所属期间组织数据。",
        [{"Date": "20251231", "Fn193": 1.2, "Fn196": 8.8}],
    ),
    "financial_announce_time": DatasetDescription(
        "get_financial_data(report_type='announce_time')",
        "按公告期读取 Fn193-Fn200 财务字段，适合按市场实际可知时间组织数据。",
        [{"Date": "20260420", "Fn193": 1.2, "Fn196": 8.8}],
    ),
    "gp_trading": DatasetDescription(
        "get_gpjy_value",
        "获取指定日期范围内的 GP1-GP5 交易序列；返回通常按字段包含日期和值。",
        [{"Date": "20260820", "GP1": ["100", "0"], "GP2": ["1000", "0"]}],
    ),
    "gp_single": DatasetDescription(
        "get_gp_one_data",
        "获取 GO1-GO4、GO47 等单股票单点指标。",
        {"GO1": 5.0, "GO2": 10.0, "GO47": "20000101"},
    ),
}


class AdditionalTdxDataSource:
    """调用 TDX 归档使用的扩展只读 TQ 接口。"""

    def __init__(self, tq: Any):
        self.tq = tq

    def fetch_corporate_actions(self, code: str, start: date, end: date) -> Any:
        """调用 ``get_divid_factors`` 获取公司行为。"""
        return json_ready(
            self.tq.get_divid_factors(
                stock_code=code,
                start_time=_date_argument(start),
                end_time=_date_argument(end),
            )
        )

    def fetch_market_snapshot(self, code: str) -> Any:
        """调用 ``get_market_snapshot`` 获取全部可用的单股票快照字段。"""
        return json_ready(self.tq.get_market_snapshot(stock_code=code, field_list=[]))

    def fetch_share_capital(self, code: str, observation_dates: Sequence[date]) -> Any:
        """调用 ``get_gb_info`` 获取多个观察日的股本结构。"""
        dates = sorted(set(observation_dates))
        if not dates:
            raise ValueError("observation_dates 不能为空。")
        return json_ready(
            self.tq.get_gb_info(
                stock_code=code,
                date_list=[_date_argument(item) for item in dates],
                count=len(dates),
            )
        )

    def fetch_financial_data(
        self,
        code: str,
        start: date,
        end: date,
        report_type: str,
    ) -> Any:
        """调用 ``get_financial_data`` 获取报告期或公告期财务字段。"""
        if report_type not in {"report_time", "announce_time"}:
            raise ValueError("report_type 必须是 report_time 或 announce_time。")
        return json_ready(
            self.tq.get_financial_data(
                stock_list=[code],
                field_list=list(FINANCIAL_FIELDS),
                start_time=_date_argument(start),
                end_time=_date_argument(end),
                report_type=report_type,
            )
        )

    def fetch_gp_trading(self, code: str, start: date, end: date) -> Any:
        """调用 ``get_gpjy_value`` 获取 GP1-GP5 日期序列。"""
        return json_ready(
            self.tq.get_gpjy_value(
                stock_list=[code],
                field_list=list(GP_FIELDS),
                start_time=_date_argument(start),
                end_time=_date_argument(end),
            )
        )

    def fetch_gp_single(self, code: str) -> Any:
        """调用 ``get_gp_one_data`` 获取 GO1-GO4、GO47 单点指标。"""
        return json_ready(
            self.tq.get_gp_one_data(stock_list=[code], field_list=list(GO_FIELDS))
        )

    def fetch_dataset(
        self,
        dataset: str,
        code: str,
        start: date,
        end: date,
        observation_dates: Sequence[date],
    ) -> Any:
        """按数据集名称调用对应接口，供 CLI 和调用方统一使用。"""
        fetchers: dict[str, Callable[[], Any]] = {
            "corporate_actions": lambda: self.fetch_corporate_actions(code, start, end),
            "market_snapshot": lambda: self.fetch_market_snapshot(code),
            "share_capital": lambda: self.fetch_share_capital(code, observation_dates),
            "financial_report_time": lambda: self.fetch_financial_data(
                code, start, end, "report_time"
            ),
            "financial_announce_time": lambda: self.fetch_financial_data(
                code, start, end, "announce_time"
            ),
            "gp_trading": lambda: self.fetch_gp_trading(code, start, end),
            "gp_single": lambda: self.fetch_gp_single(code),
        }
        try:
            fetch = fetchers[dataset]
        except KeyError as error:
            raise ValueError(f"未知数据集：{dataset}") from error
        return fetch()


def json_ready(value: Any) -> Any:
    """递归转换 TQ/pandas 返回值，使其可由 ``json.dumps`` 输出。"""
    if isinstance(value, pd.DataFrame):
        frame = value.copy()
        if not isinstance(frame.index, pd.RangeIndex):
            index_name = frame.index.name or "Date"
            if index_name in frame.columns:
                index_name = "_index"
            frame.insert(0, index_name, frame.index)
        return [json_ready(row) for row in frame.to_dict(orient="records")]
    if isinstance(value, pd.Series):
        return [json_ready(item) for item in value.tolist()]
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    if isinstance(value, (date, pd.Timestamp)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            value = value.item()
        except (TypeError, ValueError):
            pass
    try:
        return None if pd.isna(value) else value
    except (TypeError, ValueError):
        return value


def quarter_observation_dates(start: date, end: date) -> tuple[date, ...]:
    """返回区间内季度末；没有季度末时使用结束日，供 ``get_gb_info`` 调用。"""
    if start > end:
        raise ValueError("start 不能晚于 end。")
    dates: list[date] = []
    for year in range(start.year, end.year + 1):
        for month in (3, 6, 9, 12):
            item = date(year, month, calendar.monthrange(year, month)[1])
            if start <= item <= end:
                dates.append(item)
    return tuple(dates) or (end,)


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """解析样例程序参数。"""
    today = date.today()
    default_start = _subtract_year(today)
    parser = argparse.ArgumentParser(
        description="查看或单独调用 TDX 归档使用的扩展只读接口"
    )
    parser.add_argument("--code", default="600000.SH", help="股票代码")
    parser.add_argument("--start-date", type=date.fromisoformat, default=default_start)
    parser.add_argument("--end-date", type=date.fromisoformat, default=today)
    parser.add_argument("--tdx-user-dir", type=Path, default=DEFAULT_USER_DIR)
    parser.add_argument(
        "--dataset",
        nargs="+",
        choices=tuple(DATASET_DESCRIPTIONS),
        default=list(DATASET_DESCRIPTIONS),
        help="要获取的数据集；默认全部",
    )
    parser.add_argument(
        "--sample-only",
        action="store_true",
        help="只打印接口说明和结构示意样例，不连接通达信",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """打印接口说明；可选连接 TDX 获取并打印真实数据，不进行持久化。"""
    args = parse_arguments(argv)
    if args.start_date > args.end_date:
        raise SystemExit("start-date 不能晚于 end-date。")

    catalog = {
        name: {
            "interface": DATASET_DESCRIPTIONS[name].interface,
            "description": DATASET_DESCRIPTIONS[name].description,
            "illustrative_sample": DATASET_DESCRIPTIONS[name].sample,
        }
        for name in args.dataset
    }
    print("接口说明与结构示意样例：")
    print(json.dumps(catalog, ensure_ascii=False, indent=2))
    if args.sample_only:
        return 0

    client = TdxClient(args.tdx_user_dir, Path(__file__).resolve())
    client.connect()
    try:
        if client.tq is None:
            raise RuntimeError("通达信会话初始化后没有可用的 TQ 对象。")
        source = AdditionalTdxDataSource(client.tq)
        observation_dates = quarter_observation_dates(args.start_date, args.end_date)
        live: dict[str, Any] = {}
        for dataset in args.dataset:
            try:
                live[dataset] = {
                    "status": "success",
                    "data": source.fetch_dataset(
                        dataset,
                        args.code,
                        args.start_date,
                        args.end_date,
                        observation_dates,
                    ),
                }
            except Exception as error:  # 单接口失败不阻断其他示例接口。
                live[dataset] = {
                    "status": "failed",
                    "error": f"{type(error).__name__}: {error}",
                }
        print("真实接口返回（未写入数据库）：")
        print(json.dumps(live, ensure_ascii=False, indent=2, default=str))
    finally:
        client.close()
    return 0


def _date_argument(value: date) -> str:
    return value.strftime("%Y%m%d")


def _subtract_year(value: date) -> date:
    try:
        return value.replace(year=value.year - 1)
    except ValueError:
        return value.replace(year=value.year - 1, day=28)


if __name__ == "__main__":
    raise SystemExit(main())
