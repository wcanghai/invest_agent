"""通达信字段字典：原始字段名、中文名称和数据分组。"""

from __future__ import annotations


BASE_INFO = {"Code": "代码", "Name": "名称"}
KLINE = {
    "Date": "日期", "Time": "时间", "Open": "开盘价", "High": "最高价",
    "Low": "最低价", "Close": "收盘价", "Volume": "成交量", "Amount": "成交额",
    "ForwardFactor": "前复权因子", "VolInStock": "持仓量", "Ltgb": "流通股本",
    "Zgb": "总股本",
}
STOCK_INFO = {
    "BelongHS300": "是否属于沪深300", "IsSTGP": "是否是ST股票", "IsQuitGP": "是否是退市整理板股票",
    "HSStockKind": "沪深京品种类型", "ActiveCapital": "流通股本(万股)", "J_zgb": "总股本(万股)",
    "J_zzc": "总资产(万元)", "J_ldzc": "流动资产(万元)", "J_gdzc": "固定资产(万元)",
    "J_wxzc": "无形资产(万元)", "J_ldfz": "流动负债(万元)", "J_cqfz": "少数股东权益(万元)",
    "J_zbgjj": "资本公积金(万元)", "J_jzc": "股东权益/净资产(万元)", "J_yysy": "营业收入(万元)",
    "J_yycb": "营业成本(万元)", "J_yszk": "应收账款(万元)", "J_yyly": "营业利润(万元)",
    "J_tzsy": "投资收益(万元)", "J_jyxjl": "经营现金净流量(万元)", "J_zxjl": "总现金净流量(万元)",
    "J_ch": "存货(万元)", "J_lyze": "利润总额(万元)", "J_shly": "税后利润(万元)",
    "J_jly": "净利润(万元)", "J_wfply": "未分配利润(万元)", "J_jyl": "净资产收益率",
    "J_mgwfp": "每股未分配利润", "J_mgsy": "每股收益（折算为全年）",
    "J_mgsy2": "季报每股收益（财报）", "J_mggjj": "每股公积金", "J_mgjzc": "每股净资产",
    "J_mgjzc2": "季报每股净资产（财报）", "J_gdqyb": "股东权益比", "J_gdrs": "股东人数",
    "J_HalfYearFlag": "报告期月份(3/6/9/12)", "J_start": "上市日期", "tdx_dycode": "通达信地域代码",
    "tdx_dyname": "通达信地域", "rs_hycode_sim": "通达信行业代码", "rs_hyname": "通达信行业",
    "blockzscode": "所属行业板块指数代码",
}
MORE_INFO = {
    "MainBusiness": "主营构成", "TPFlag": "停牌标识", "ZTPrice": "涨停价", "DTPrice": "跌停价",
    "HqDate": "行情日期", "fHSL": "换手率", "fLianB": "量比", "Wtb": "委比", "Zsz": "总市值(亿)",
    "Ltsz": "流通市值(亿)", "vzangsu": "量涨速", "Fzhsl": "分钟换手率", "FzAmo": "2分钟金额(万元)",
    "VOpenZAF": "抢筹涨幅", "ZAF": "涨幅", "ZAFYesterday": "昨日涨幅", "ZAFPre2D": "前天涨幅",
    "ZAFPre5": "5日涨幅", "ZAFPre10": "10日涨幅", "ZAFPre20": "20日涨幅", "ZAFPre30": "30日涨幅",
    "ZAFPre60": "60日涨幅", "ZAFYear": "年初至今涨幅", "ZAFPreMyMonth": "本月涨幅",
    "ZAFPreOneYear": "一年涨幅", "Zjl": "主买净额(万元)", "Zjl_HB": "主力净流入(万元)",
    "TotalBVol": "总买量", "TotalSVol": "总卖量", "BCancel": "总撤买量", "SCancel": "总撤卖量",
    "OpenAmo": "开盘金额(万元)", "OpenZTBuy": "竞价涨停买入金额(万元)", "OpenAmoPre1": "昨日开盘金额(万元)",
    "OpenVolPre1": "昨日开盘量", "CJJEPre1": "昨日成交额(万元)", "CJJEPre3": "3日成交额(万元)",
    "ZTGPNum": "板块涨停家数", "LastStartZT": "最近涨停持续天数", "LastZTHzNum": "最近连板数",
    "EverZTCount": "历史连板天数", "ConZAFDateNum": "连续上涨天数", "YearZTDay": "年涨停天数",
    "MA5Value": "5日均价", "HisHigh": "52周最高", "HisLow": "52周最低", "IPO_Price": "发行价",
    "More_YJL": "ETF/LOF溢价率", "BetaValue": "贝塔系数", "DynaPE": "动态市盈率",
    "MorePE": "市盈率(扩展)", "StaticPE_TTM": "市盈率(TTM)", "DYRatio": "股息率", "PB_MRQ": "市净率(MRQ)",
    "FreeLtgb": "自由流通股本(万)", "Yield": "应计利息/占款天数", "KfEarnMoney": "扣非净利润(万元)",
    "RDInputFee": "研发费用(万元)", "CashZJ": "货币资金(万元)", "PreReceiveZJ": "合同负债(万元)",
    "OtherQYJzc": "其它权益工具(万元)", "StaffNum": "员工人数",
}

FIELD_MAP = BASE_INFO | KLINE | STOCK_INFO | MORE_INFO
FIELD_GROUP = {**{k: "base_info" for k in BASE_INFO}, **{k: "kline" for k in KLINE}, **{k: "stock_info" for k in STOCK_INFO}, **{k: "more_info" for k in MORE_INFO}}


def display_name(field_name: str) -> str:
    """未知字段保留原名，避免丢失新版本通达信字段。"""
    return FIELD_MAP.get(field_name, field_name)


def group_name(field_name: str) -> str:
    return FIELD_GROUP.get(field_name, "dynamic")
