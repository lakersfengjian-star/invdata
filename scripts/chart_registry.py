"""Chart registry for the investment dashboard.

The registry is the single place for stable chart ids, categories and expected
update frequencies. Rendering code may still decide layout, but audit/status
logic should use these keys instead of scattered hard-coded lists.
"""

from __future__ import annotations

CHART_REGISTRY: list[dict[str, str]] = [
    {"key": "market_monitor", "id": "001", "title": "行情监控面板", "category": "行情", "frequency": "daily"},
    {"key": "market_turnover", "id": "002", "title": "全市场成交额变化", "category": "行情", "frequency": "daily"},
    {"key": "limit_up_longest", "id": "003", "title": "涨停观察：连续涨停天数前十", "category": "行情", "frequency": "daily"},
    {"key": "limit_up_amount_top", "id": "004", "title": "涨停观察：当日涨停成交额前十", "category": "行情", "frequency": "daily"},
    {"key": "macro", "id": "005", "title": "宏观经济数据概览", "category": "宏观", "frequency": "monthly"},
    {"key": "valuation_hs300", "id": "006A", "title": "沪深300指数历史滚动市盈率及标准差通道", "category": "估值", "frequency": "daily"},
    {"key": "valuation_sse", "id": "006B", "title": "上证指数历史滚动市盈率及标准差通道", "category": "估值", "frequency": "daily"},
    {"key": "valuation_wind_all_a", "id": "006C", "title": "万得全A历史滚动市盈率及标准差通道", "category": "估值", "frequency": "daily"},
    {"key": "valuation_wind_all_a_ex_fin_petchem", "id": "006D", "title": "万得全A（除金融、石油石化）历史滚动市盈率及标准差通道", "category": "估值", "frequency": "daily"},
    {"key": "pb_roe", "id": "008", "title": "中信一级行业 PB-ROE 对比", "category": "估值", "frequency": "weekly"},
    {"key": "industrial_profits", "id": "009", "title": "工业企业利润同比与全年外推", "category": "盈利", "frequency": "monthly"},
    {"key": "southbound", "id": "010", "title": "南向资金每日净流入", "category": "流动性", "frequency": "daily"},
    {"key": "broad_etf_flow", "id": "011", "title": "沪深300/上证指数 vs. 大宽基ETF资金流", "category": "流动性", "frequency": "daily"},
    {"key": "star50_etf_flow", "id": "012", "title": "科创50指数 vs. 科创50ETF资金流", "category": "流动性", "frequency": "daily"},
    {"key": "sentiment", "id": "013", "title": "上证等权情绪指数（3年分位）", "category": "情绪", "frequency": "daily"},
    {"key": "turnover_top10", "id": "014A", "title": "A股成交额前10大公司交易集中度", "category": "情绪", "frequency": "daily"},
    {"key": "turnover_top100", "id": "014B", "title": "A股成交额前100大公司交易集中度", "category": "情绪", "frequency": "daily"},
    {"key": "amount_share", "id": "015", "title": "主要宽基指数成交额占全A成交额比例", "category": "情绪", "frequency": "daily"},
    {"key": "theme_amount_share", "id": "016", "title": "TMT与红利低波成交额占全A成交额比例", "category": "情绪", "frequency": "daily"},
    {"key": "industry_crowding", "id": "017", "title": "中信一级行业估值与成交拥挤度", "category": "情绪", "frequency": "weekly"},
    {"key": "value_growth_spread", "id": "018", "title": "价值成长风格价差", "category": "情绪", "frequency": "daily"},
    {"key": "citic_pb_dispersion", "id": "019", "title": "中信一级行业估值离散度", "category": "情绪", "frequency": "daily"},
    {"key": "library", "id": "020", "title": "研究资料库", "category": "资料", "frequency": "manual"},
]

REGISTRY_BY_KEY = {item["key"]: item for item in CHART_REGISTRY}
