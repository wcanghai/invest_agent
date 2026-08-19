"""通过通达信 TQ 接口展示代表性行业 ETF 的最新日线数据。"""

from __future__ import annotations

import pandas as pd

from get_midea_daily_data import load_tq


# 行业覆盖：金融、医药、半导体、军工、消费、新能源。
ETFS = {
    "512880.SH": {"name": "证券ETF", "industry": "证券"},
    "512010.SH": {"name": "医药ETF", "industry": "医药卫生"},
    "512480.SH": {"name": "半导体ETF", "industry": "半导体"},
    "512660.SH": {"name": "军工ETF", "industry": "国防军工"},
    "512690.SH": {"name": "酒ETF", "industry": "食品饮料"},
    "516160.SH": {"name": "新能源ETF", "industry": "新能源"},
}
FIELDS = ["Open", "High", "Low", "Close", "Volume", "Amount"]


def get_latest_industry_etfs() -> pd.DataFrame:
    tq = load_tq()
    tq.initialize(__file__)
    try:
        data = tq.get_market_data(
            field_list=FIELDS,
            stock_list=list(ETFS),
            period="1d",
            count=2,
            dividend_type="none",
            fill_data=False,
        )
    finally:
        tq.close()

    if not data or "Close" not in data:
        raise RuntimeError("接口未返回 ETF 日线数据，请检查通达信客户端和盘后数据。")

    rows = []
    for code, metadata in ETFS.items():
        close = data["Close"][code].dropna()
        if close.empty:
            continue

        latest_date = close.index[-1]
        previous_close = close.iloc[-2] if len(close) >= 2 else None
        latest_close = close.iloc[-1]
        change_pct = (
            (latest_close / previous_close - 1) * 100 if previous_close and previous_close != 0 else None
        )
        rows.append(
            {
                "日期": latest_date.strftime("%Y-%m-%d"),
                "行业": metadata["industry"],
                "ETF": metadata["name"],
                "代码": code,
                "开盘": data["Open"].at[latest_date, code],
                "最高": data["High"].at[latest_date, code],
                "最低": data["Low"].at[latest_date, code],
                "收盘": latest_close,
                "涨跌幅(%)": change_pct,
                "成交量": data["Volume"].at[latest_date, code],
                "成交额(万元)": data["Amount"].at[latest_date, code],
            }
        )

    if not rows:
        raise RuntimeError("未获得任何 ETF 数据。")
    return pd.DataFrame(rows).sort_values("行业").reset_index(drop=True)


def main() -> None:
    result = get_latest_industry_etfs()
    print(result.to_string(index=False, float_format=lambda value: f"{value:.2f}"))


if __name__ == "__main__":
    main()
