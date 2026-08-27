"""通达信专业财务字段的研究子集与官方含义。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FinancialField:
    code: str
    name: str
    display_name: str
    unit: str = ""


_DEFINITIONS = (
    (1, "basic_eps", "基本每股收益", "元/股"),
    (2, "deducted_eps", "扣非每股收益", "元/股"),
    (4, "book_value_per_share", "每股净资产", "元/股"),
    (6, "roe_reported", "净资产收益率", "%"),
    (7, "operating_cash_flow_per_share", "每股经营现金流", "元/股"),
    (8, "cash", "货币资金", "万元"),
    (11, "accounts_receivable", "应收账款", "万元"),
    (17, "inventory", "存货", "万元"),
    (21, "current_assets", "流动资产合计", "万元"),
    (35, "goodwill", "商誉", "万元"),
    (40, "total_assets", "资产总计", "万元"),
    (41, "short_term_borrowings", "短期借款", "万元"),
    (52, "current_noncurrent_liabilities", "一年内到期的非流动负债", "万元"),
    (54, "current_liabilities", "流动负债合计", "万元"),
    (55, "long_term_borrowings", "长期借款", "万元"),
    (56, "bonds_payable", "应付债券", "万元"),
    (62, "noncurrent_liabilities", "非流动负债合计", "万元"),
    (63, "total_liabilities", "负债合计", "万元"),
    (72, "total_equity", "股东权益合计", "万元"),
    (98, "cash_received_from_sales", "销售商品提供劳务收到的现金", "万元"),
    (107, "operating_cash_flow", "经营活动现金流量净额", "万元"),
    (114, "capital_expenditure_cash", "购建长期资产支付的现金", "万元"),
    (119, "investing_cash_flow", "投资活动现金流量净额", "万元"),
    (125, "dividend_interest_cash", "分配股利利润或偿付利息支付的现金", "万元"),
    (128, "financing_cash_flow", "筹资活动现金流量净额", "万元"),
    (134, "net_profit", "净利润", "万元"),
    (159, "current_ratio", "流动比率", "倍"),
    (160, "quick_ratio", "速动比率", "倍"),
    (162, "interest_coverage", "利息保障倍数", "倍"),
    (167, "equity_multiplier", "权益乘数", "%"),
    (172, "receivable_turnover", "应收账款周转率", "次"),
    (173, "inventory_turnover", "存货周转率", "次"),
    (175, "asset_turnover", "总资产周转率", "次"),
    (183, "revenue_growth", "营业收入增长率", "%"),
    (184, "net_profit_growth", "净利润增长率", "%"),
    (185, "equity_growth", "净资产增长率", "%"),
    (190, "deducted_eps_growth", "扣非每股收益同比", "%"),
    (191, "deducted_profit_growth", "扣非净利润同比", "%"),
    (194, "operating_margin", "营业利润率", "%"),
    (197, "roe", "净资产收益率", "%"),
    (199, "net_margin", "销售净利率", "%"),
    (202, "gross_margin", "销售毛利率", "%"),
    (206, "deducted_net_profit", "扣非净利润", "万元"),
    (207, "ebit", "息税前利润", "万元"),
    (208, "ebitda", "息税折旧摊销前利润", "万元"),
    (210, "debt_to_assets", "资产负债率", "%"),
    (219, "operating_cash_flow_per_share_2", "每股经营性现金流", "元/股"),
    (220, "revenue_cash_content", "营业收入现金含量", "%"),
    (223, "operating_cash_flow_to_revenue", "经营现金流/营业收入", "%"),
    (228, "cash_conversion", "经营现金流/净利润", "%"),
    (229, "cash_return_on_assets", "全部资产现金回收率", "%"),
    (230, "revenue", "营业收入", "万元"),
    (231, "operating_profit", "营业利润", "万元"),
    (232, "attributable_net_profit", "归母净利润", "万元"),
    (233, "attributable_deducted_profit", "归母扣非净利润", "万元"),
    (234, "operating_cash_flow_2", "经营活动现金流量净额", "万元"),
    (238, "total_shares", "总股本", "股"),
    (242, "shareholder_count", "股东人数", "户"),
    (246, "institution_count", "机构数量", "家"),
    (247, "institution_holding", "机构持股量", "股"),
    (266, "free_float_shares", "自由流通股", "股"),
    (271, "parent_equity", "归母股东权益", "万元"),
    (276, "ttm_net_profit", "近一年净利润", "元"),
    (281, "weighted_roe", "加权净资产收益率", "%"),
    (283, "latest_year_revenue", "最近一年营业收入", "万元"),
    (304, "research_and_development", "研发费用", "万元"),
    (307, "ttm_operating_cash_flow", "近一年经营现金流净额", "万元"),
    (308, "ttm_attributable_profit", "近一年归母净利润", "万元"),
    (309, "ttm_deducted_profit", "近一年扣非净利润", "万元"),
    (310, "ttm_net_cash_flow", "近一年现金净流量", "万元"),
    (319, "ttm_revenue", "营业总收入TTM", "万元"),
    (320, "employee_count", "员工总数", "人"),
    (321, "fcff_per_share", "每股企业自由现金流", "元/股"),
    (322, "fcfe_per_share", "每股股东自由现金流", "元/股"),
    (327, "interest_bearing_debt_ratio", "有息负债率", "%"),
    (329, "roic", "投入资本回报率", "%"),
    (336, "audit_opinion", "审计意见", "枚举"),
    (337, "dividend_payout_ratio", "股利支付率", "%"),
)

FINANCIAL_FIELDS = tuple(
    FinancialField(f"FN{number}", name, display_name, unit)
    for number, name, display_name, unit in _DEFINITIONS
)
FINANCIAL_CODES = tuple(field.code for field in FINANCIAL_FIELDS)
FIELD_BY_CODE = {field.code: field for field in FINANCIAL_FIELDS}

