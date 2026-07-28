"""Common configuration shared across update scripts."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# ------------------------------------------------------------------ dirs ---
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
CHART_DIR = ROOT / "output" / "charts"
SITE_DIR = ROOT / "site"
CACHE_DIR = ROOT / ".work" / "cache"

# ------------------------------------------------------------------ dates ---
START_DATE = "2025-01-01"
VALUATION_START_DATE = "2020-01-01"
TURNOVER_START_DATE = "2026-01-01"
SOUTHBOUND_START_DATE = "2026-01-01"
END_CAP = "2050-01-01"

# ------------------------------------------------------------------ ETFs ---
ETF_SELECTION = [
    {"code": "510300", "name": "沪深300ETF华泰柏瑞", "market": "sh", "index": "沪深300", "venue": "SSE"},
    {"code": "510310", "name": "沪深300ETF易方达", "market": "sh", "index": "沪深300", "venue": "SSE"},
    {"code": "510330", "name": "沪深300ETF华夏", "market": "sh", "index": "沪深300", "venue": "SSE"},
    {"code": "159919", "name": "沪深300ETF嘉实", "market": "sz", "index": "沪深300", "venue": "SZSE"},
    {"code": "510050", "name": "上证50ETF华夏", "market": "sh", "index": "上证50", "venue": "SSE"},
]

STAR50_ETF = {"code": "588000", "name": "科创50ETF华夏", "market": "sh", "index": "科创50", "venue": "SSE"}

# ---------------------------------------------------------------- indices ---
INDEX_SELECTION = {
    "沪深300": {"symbol": "sh000300", "label": "沪深300"},
    "上证指数": {"symbol": "sh000001", "label": "上证指数"},
    "科创50": {"symbol": "sh000688", "label": "科创50"},
}

VALUATION_INDEXES = [
    {"key": "hs300", "name": "沪深300指数", "source": "legulegu_index", "symbol": "沪深300"},
    {"key": "sse", "name": "上证指数", "source": "legulegu_market", "symbol": "上证"},
    {"key": "wind_all_a", "name": "万得全A", "source": "local_csv", "symbol": "万得全A"},
    {"key": "wind_all_a_ex_fin_petchem", "name": "万得全A（除金融、石油石化）", "source": "local_csv", "symbol": "万得全A（除金融、石油石化）"},
]

# --------------------------------------------------------- market monitor ---
EQUITY_ORDER = ["沪深300", "300收益", "上证指数", "万得全A", "恒生指数", "恒生科技指数", "中证红利"]
RATE_ORDER = ["7天逆回购利率", "DR007(FDR007定盘)", "10年期国债", "30年期国债", "5年期AAA企业债(中短票)", "银行二级资本债AAA-(5年)"]

# ----------------------------------------------------------- CITIC L1 ---
CITIC_LEVEL1 = {
    "CI005001.WI": "石油石化",
    "CI005002.WI": "煤炭",
    "CI005003.WI": "有色金属",
    "CI005004.WI": "电力及公用事业",
    "CI005005.WI": "钢铁",
    "CI005006.WI": "基础化工",
    "CI005007.WI": "建筑",
    "CI005008.WI": "建材",
    "CI005009.WI": "轻工制造",
    "CI005010.WI": "机械",
    "CI005011.WI": "电力设备及新能源",
    "CI005012.WI": "国防军工",
    "CI005013.WI": "汽车",
    "CI005014.WI": "商贸零售",
    "CI005015.WI": "消费者服务",
    "CI005016.WI": "家电",
    "CI005017.WI": "纺织服装",
    "CI005018.WI": "医药",
    "CI005019.WI": "食品饮料",
    "CI005020.WI": "农林牧渔",
    "CI005021.WI": "银行",
    "CI005022.WI": "非银行金融",
    "CI005023.WI": "房地产",
    "CI005024.WI": "交通运输",
    "CI005025.WI": "电子",
    "CI005026.WI": "通信",
    "CI005027.WI": "计算机",
    "CI005028.WI": "传媒",
    "CI005029.WI": "综合",
    "CI005030.WI": "综合金融",
}
