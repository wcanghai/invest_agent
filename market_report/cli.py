"""可配置的多市场行情日报入口。"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from market_report.service import generate_market_report


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成可配置的 A 股、美股与虚拟货币行情日报")
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "config" / "market_universe.json",
        help="标的配置 JSON 路径",
    )
    parser.add_argument(
        "--history-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "history",
        help="本地历史日线缓存目录（默认：data/history）",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="报告输出路径；默认写入 reports/market_report_YYYY-MM-DD.md",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    generated_at = datetime.now()
    default_output = PROJECT_ROOT / "reports" / f"market_report_{generated_at:%Y-%m-%d}.md"
    output = (args.output or default_output).resolve()
    snapshot = generate_market_report(
        args.config,
        args.history_dir,
        Path(__file__).resolve(),
        generated_at,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(snapshot.markdown, encoding="utf-8")
    print(f"报告已生成：{output}")


if __name__ == "__main__":
    main()
