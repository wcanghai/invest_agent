"""市场报告网站启动命令。"""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from daily_report.web.app import DEFAULT_CONFIG, DEFAULT_DATABASE, create_app


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="启动每日市场报告网站")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认：127.0.0.1）")
    parser.add_argument("--port", default=8000, type=int, help="监听端口（默认：8000）")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE, help="日报 SQLite 路径")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="市场标的配置路径")
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    app = create_app(args.database, args.config)
    uvicorn.run(app, host=args.host, port=args.port, workers=1)
