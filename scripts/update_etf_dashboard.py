#!/usr/bin/env python3
"""Build the ETF flow dashboard.

Data priority:
1. Exchange/public source: SSE ETF share endpoint; Tencent public quote kline.
2. AkShare wrappers for fund NAV and exchange datasets.
3. Tushare hook, enabled when TUSHARE_TOKEN is configured.

ETF net inflow is calculated as daily ETF share change multiplied by daily NAV,
then converted to CNY 100mn. For SZSE ETF historical shares, the script keeps a
Tushare fallback hook because the public SZSE list endpoint only exposes the
latest snapshot.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from io import StringIO
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / ".work" / "vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

import numpy as np
import pandas as pd

try:
    import akshare as ak
except Exception as exc:  # pragma: no cover - handled at runtime
    ak = None
    AKSHARE_IMPORT_ERROR = repr(exc)
else:
    AKSHARE_IMPORT_ERROR = ""

try:
    import requests
except Exception as exc:  # pragma: no cover - handled at runtime
    raise SystemExit("requests is required. Run: python3 -m pip install --target .work/vendor requests") from exc

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter


START_DATE = "2025-01-01"
TURNOVER_START_DATE = "2026-01-01"
VALUATION_START_DATE = "2020-01-01"
END_CAP = "2050-01-01"

RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
CHART_DIR = ROOT / "output" / "charts"
SITE_DIR = ROOT / "site"
CACHE_DIR = ROOT / ".work" / "cache"

ETF_SELECTION = [
    {"code": "510300", "name": "沪深300ETF华泰柏瑞", "market": "sh", "index": "沪深300", "venue": "SSE"},
    {"code": "510310", "name": "沪深300ETF易方达", "market": "sh", "index": "沪深300", "venue": "SSE"},
    {"code": "510330", "name": "沪深300ETF华夏", "market": "sh", "index": "沪深300", "venue": "SSE"},
    {"code": "159919", "name": "沪深300ETF嘉实", "market": "sz", "index": "沪深300", "venue": "SZSE"},
    {"code": "510050", "name": "上证50ETF华夏", "market": "sh", "index": "上证50", "venue": "SSE"},
]

STAR50_ETF = {"code": "588000", "name": "科创50ETF华夏", "market": "sh", "index": "科创50", "venue": "SSE"}

INDEX_SELECTION = {
    "沪深300": {"symbol": "sh000300", "label": "沪深300"},
    "上证指数": {"symbol": "sh000001", "label": "上证指数"},
    "科创50": {"symbol": "sh000688", "label": "科创50"},
}

TURNOVER_CACHE_DIR = CACHE_DIR / "sina_a_share_daily_2026"

VALUATION_INDEXES = [
    {"key": "hs300", "name": "沪深300指数", "source": "legulegu_index", "symbol": "沪深300"},
    {"key": "sse", "name": "上证指数", "source": "legulegu_market", "symbol": "上证"},
    {"key": "wind_all_a", "name": "万得全A", "source": "local_csv", "symbol": "万得全A"},
    {"key": "wind_all_a_ex_fin_petchem", "name": "万得全A（除金融、石油石化）", "source": "local_csv", "symbol": "万得全A（除金融、石油石化）"},
]


@dataclass
class SourceLog:
    source: str
    status: str
    detail: str


SOURCE_LOGS: list[SourceLog] = []


def log_source(source: str, status: str, detail: str) -> None:
    SOURCE_LOGS.append(SourceLog(source, status, detail))


def ensure_dirs() -> None:
    for path in [RAW_DIR, PROCESSED_DIR, CHART_DIR, SITE_DIR, CACHE_DIR, TURNOVER_CACHE_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def load_env_file() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def setup_fonts() -> None:
    preferred = [
        "Noto Sans CJK SC",
        "Noto Sans CJK JP",
        "Microsoft YaHei",
        "SimHei",
        "PingFang SC",
        "Heiti SC",
        "Arial Unicode MS",
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    for name in preferred:
        if name in available:
            plt.rcParams["font.family"] = "sans-serif"
            plt.rcParams["font.sans-serif"] = [name]
            break
    plt.rcParams["axes.unicode_minus"] = False


def request_json(url: str, params: dict[str, Any] | None = None, timeout: int = 25) -> dict[str, Any]:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://quote.eastmoney.com/",
    }
    resp = requests.get(url, params=params, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def fetch_tencent_kline(symbol: str, start: str, end: str) -> pd.DataFrame:
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    params = {"param": f"{symbol},day,{start},{end},900,qfq"}
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"}
    resp = requests.get(url, params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    node = payload["data"][symbol]
    rows = node.get("day") or node.get("qfqday") or node.get("hfqday")
    if not rows:
        raise ValueError(f"No kline rows for {symbol}")
    df = pd.DataFrame(rows, columns=["date", "open", "close", "high", "low", "volume"])
    df["date"] = pd.to_datetime(df["date"])
    for col in ["open", "close", "high", "low", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df[["date", "close"]].sort_values("date")


def fetch_indices(start: str, end: str) -> pd.DataFrame:
    frames = []
    for label, cfg in INDEX_SELECTION.items():
        df = fetch_tencent_kline(cfg["symbol"], start, end)
        df = df.rename(columns={"close": label})
        frames.append(df)
        log_source("Tencent public kline", "ok", f"{label} close: {len(df)} rows")
    out = frames[0]
    for frame in frames[1:]:
        out = out.merge(frame, on="date", how="outer")
    out = out.sort_values("date")
    out.to_csv(PROCESSED_DIR / "index_close.csv", index=False)
    return out


def fetch_current_etf_ranking() -> pd.DataFrame:
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": 1,
        "pz": 5000,
        "po": 1,
        "np": 1,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": 2,
        "invt": 2,
        "fid": "f20",
        "fs": "b:MK0021,b:MK0022,b:MK0023,b:MK0024",
        "fields": "f12,f14,f2,f20,f21,f6",
    }
    try:
        data = request_json(url, params=params)
        df = pd.DataFrame(data["data"]["diff"])
        df = df.rename(
            columns={
                "f12": "code",
                "f14": "name",
                "f2": "price",
                "f20": "market_cap",
                "f21": "float_cap",
                "f6": "amount",
            }
        )
        df["market_cap_100mn"] = pd.to_numeric(df["market_cap"], errors="coerce") / 1e8
        log_source("Eastmoney ETF quote list", "ok", f"ranking snapshot: {len(df)} ETFs")
        df.to_csv(RAW_DIR / "current_etf_ranking.csv", index=False)
        return df
    except Exception as exc:
        log_source("Eastmoney ETF quote list", "failed", repr(exc))
        return pd.DataFrame()


def fetch_nav(code: str, start: str, end: str) -> pd.DataFrame:
    if ak is None:
        log_source("AkShare fund_etf_fund_info_em", "failed", AKSHARE_IMPORT_ERROR)
        return pd.DataFrame(columns=["date", "nav"])
    cache = CACHE_DIR / f"nav_{code}_{start}_{end}.csv"
    if cache.exists():
        df = pd.read_csv(cache, parse_dates=["date"])
        log_source("AkShare fund_etf_fund_info_em", "cache", f"{code}: {len(df)} rows")
        return df
    try:
        df = ak.fund_etf_fund_info_em(fund=code, start_date=start, end_date=end)
        df = df.rename(columns={"净值日期": "date", "单位净值": "nav"})
        df = df[["date", "nav"]].copy()
        df["date"] = pd.to_datetime(df["date"])
        df["nav"] = pd.to_numeric(df["nav"], errors="coerce")
        df = df.dropna(subset=["date"]).sort_values("date")
        df.to_csv(cache, index=False)
        log_source("AkShare fund_etf_fund_info_em", "ok", f"{code}: {len(df)} NAV rows")
        return df
    except Exception as exc:
        log_source("AkShare fund_etf_fund_info_em", "failed", f"{code}: {repr(exc)}")
        return pd.DataFrame(columns=["date", "nav"])


def fetch_etf_close_prices(etfs: list[dict[str, str]], start: str, end: str) -> pd.DataFrame:
    frames = []
    for etf in etfs:
        symbol = f"{etf['market']}{etf['code']}"
        try:
            df = fetch_tencent_kline(symbol, start, end)
            df = df.rename(columns={"close": "close_price"})
            df["code"] = etf["code"]
            frames.append(df[["date", "code", "close_price"]])
            log_source("Tencent public kline", "ok", f"{etf['code']} ETF close: {len(df)} rows")
        except Exception as exc:
            log_source("Tencent public kline", "failed", f"{etf['code']} ETF close: {repr(exc)}")
    if not frames:
        return pd.DataFrame(columns=["date", "code", "close_price"])
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    return out


def fetch_sse_scale_one_day(day: pd.Timestamp) -> pd.DataFrame:
    day_str = day.strftime("%Y%m%d")
    cache = CACHE_DIR / f"sse_scale_{day_str}.csv"
    if cache.exists():
        return pd.read_csv(cache, dtype={"基金代码": str}, parse_dates=["统计日期"])
    data_str = day.strftime("%Y-%m-%d")
    url = "https://query.sse.com.cn/commonQuery.do"
    params = {
        "isPagination": "true",
        "pageHelp.pageSize": "10000",
        "pageHelp.pageNo": "1",
        "pageHelp.beginPage": "1",
        "pageHelp.cacheSize": "1",
        "pageHelp.endPage": "1",
        "sqlId": "COMMON_SSE_ZQPZ_ETFZL_XXPL_ETFGM_SEARCH_L",
        "STAT_DATE": data_str,
    }
    headers = {
        "Referer": "https://www.sse.com.cn/",
        "User-Agent": "Mozilla/5.0",
    }
    resp = requests.get(url, params=params, headers=headers, timeout=12)
    resp.raise_for_status()
    payload = resp.json()
    rows = payload.get("result") or []
    if not rows:
        raise ValueError("empty SSE scale result")
    df = pd.DataFrame(rows)
    df = df.rename(
        columns={
            "NUM": "序号",
            "SEC_CODE": "基金代码",
            "SEC_NAME": "基金简称",
            "ETF_TYPE": "ETF类型",
            "STAT_DATE": "统计日期",
            "TOT_VOL": "基金份额",
        }
    )
    df = df[["序号", "基金代码", "基金简称", "ETF类型", "统计日期", "基金份额"]]
    df["序号"] = pd.to_numeric(df["序号"], errors="coerce")
    df["统计日期"] = pd.to_datetime(df["统计日期"], errors="coerce")
    df["基金份额"] = pd.to_numeric(df["基金份额"], errors="coerce") * 10000
    df.to_csv(cache, index=False)
    return df


def fetch_sse_shares(dates: list[pd.Timestamp], codes: list[str]) -> pd.DataFrame:
    rows = []
    failures = []

    def load(day: pd.Timestamp) -> tuple[pd.Timestamp, pd.DataFrame | None, str | None]:
        try:
            df = fetch_sse_scale_one_day(day)
            sub = df[df["基金代码"].astype(str).isin(codes)][["统计日期", "基金代码", "基金份额"]].copy()
            return day, sub, None
        except Exception as exc:
            return day, None, repr(exc)[:140]

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(load, day) for day in dates]
        for future in as_completed(futures):
            day, sub, err = future.result()
            if err:
                failures.append((day, err))
            elif sub is not None and not sub.empty:
                rows.append(sub)

    for day, err in failures[:30]:
        log_source("SSE ETF scale", "failed", f"{day.date()}: {err}")
    if len(failures) > 30:
        log_source("SSE ETF scale", "failed", f"{len(failures) - 30} additional failed dates omitted")
    if not rows:
        return pd.DataFrame(columns=["date", "code", "shares"])
    out = pd.concat(rows, ignore_index=True)
    out = out.rename(columns={"统计日期": "date", "基金代码": "code", "基金份额": "shares"})
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    out["code"] = out["code"].astype(str)
    out["shares"] = pd.to_numeric(out["shares"], errors="coerce")
    ok_days = out["date"].nunique()
    log_source("SSE ETF scale", "ok", f"{ok_days} trading days, {len(failures)} failed days")
    return out


def fetch_tushare_fund_share(code: str, dates: list[pd.Timestamp]) -> pd.DataFrame:
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        log_source("Tushare fund_share", "skipped", f"{code}: TUSHARE_TOKEN not configured")
        return pd.DataFrame(columns=["date", "code", "shares"])
    try:
        import tushare as ts

        ts.set_token(token)
        pro = ts.pro_api()
        start = min(dates).strftime("%Y%m%d")
        end = max(dates).strftime("%Y%m%d")
        # ETF ts_code conventions vary by endpoint; try both common forms.
        suffix = "SZ" if code.startswith("15") else "SH"
        df = pro.fund_share(ts_code=f"{code}.{suffix}", start_date=start, end_date=end)
        if df.empty:
            raise ValueError("empty fund_share result")
        date_col = "trade_date" if "trade_date" in df.columns else "ann_date"
        share_col = "fd_share" if "fd_share" in df.columns else "fund_share"
        out = df[[date_col, share_col]].copy()
        out = out.rename(columns={date_col: "date", share_col: "shares"})
        out["date"] = pd.to_datetime(out["date"])
        out["date"] = out["date"].dt.normalize()
        out["shares"] = pd.to_numeric(out["shares"], errors="coerce")
        out["code"] = code
        log_source("Tushare fund_share", "ok", f"{code}: {len(out)} rows")
        return out[["date", "code", "shares"]]
    except Exception as exc:
        log_source("Tushare fund_share", "failed", f"{code}: {repr(exc)}")
        return pd.DataFrame(columns=["date", "code", "shares"])


def build_etf_flow(dates: list[pd.Timestamp], etfs: list[dict[str, str]], start: str, end: str) -> pd.DataFrame:
    sse_codes = [e["code"] for e in etfs if e["venue"] == "SSE"]
    share_frames = []
    if sse_codes:
        share_frames.append(fetch_sse_shares(dates, sse_codes))
    for etf in etfs:
        if etf["venue"] == "SZSE":
            share_frames.append(fetch_tushare_fund_share(etf["code"], dates))
    shares = pd.concat(share_frames, ignore_index=True) if share_frames else pd.DataFrame()
    if shares.empty:
        raise RuntimeError("No ETF share data was fetched.")

    nav_frames = []
    for etf in etfs:
        nav = fetch_nav(etf["code"], start, end)
        nav["code"] = etf["code"]
        nav_frames.append(nav)
    navs = pd.concat(nav_frames, ignore_index=True)
    prices = fetch_etf_close_prices(etfs, start, end)

    grid = pd.MultiIndex.from_product(
        [pd.to_datetime(dates), [e["code"] for e in etfs]], names=["date", "code"]
    ).to_frame(index=False)
    grid["date"] = pd.to_datetime(grid["date"]).dt.normalize()
    shares["date"] = pd.to_datetime(shares["date"]).dt.normalize()
    navs["date"] = pd.to_datetime(navs["date"]).dt.normalize()
    prices["date"] = pd.to_datetime(prices["date"]).dt.normalize()
    df = (
        grid.merge(shares, on=["date", "code"], how="left")
        .merge(navs, on=["date", "code"], how="left")
        .merge(prices, on=["date", "code"], how="left")
    )
    df = df.sort_values(["code", "date"])
    df["shares_prev"] = df.groupby("code")["shares"].shift(1)
    df["share_change"] = df["shares"] - df["shares_prev"]
    df["valuation_price"] = df["nav"].combine_first(df["close_price"])
    df["valuation_source"] = np.where(df["nav"].notna(), "NAV", np.where(df["close_price"].notna(), "ETF close", None))
    df["net_inflow_100mn"] = df["share_change"] * df["valuation_price"] / 1e8
    df.loc[df["shares"].isna() | df["shares_prev"].isna() | df["valuation_price"].isna(), "net_inflow_100mn"] = np.nan
    name_map = {e["code"]: e["name"] for e in etfs}
    venue_map = {e["code"]: e["venue"] for e in etfs}
    df["name"] = df["code"].map(name_map)
    df["venue"] = df["code"].map(venue_map)
    df.to_csv(PROCESSED_DIR / "etf_daily_flow_detail.csv", index=False)
    return df


def aggregate_flows(flow_detail: pd.DataFrame, codes: list[str], output_name: str) -> pd.DataFrame:
    sub = flow_detail[flow_detail["code"].isin(codes)].copy()
    out = sub.groupby("date", as_index=False)["net_inflow_100mn"].sum(min_count=1)
    out = out.rename(columns={"net_inflow_100mn": "daily_net_inflow_100mn"})
    out["rolling_7d_net_inflow_100mn"] = out["daily_net_inflow_100mn"].rolling(7, min_periods=7).sum()
    missing_codes = (
        sub[sub["net_inflow_100mn"].isna()]
        .groupby("date")["code"]
        .apply(lambda s: ",".join(sorted(set(s))))
        .reset_index(name="missing_flow_codes")
    )
    out = out.merge(missing_codes, on="date", how="left")
    out.to_csv(PROCESSED_DIR / output_name, index=False)
    return out


def fmt_num(value: float, digits: int = 2) -> str:
    if pd.isna(value):
        return "NA"
    return f"{value:,.{digits}f}"


def y_100mn(x: float, _pos: int) -> str:
    if abs(x) >= 1000:
        return f"{x/1000:.1f}k"
    return f"{x:.0f}"


def pct_formatter(x: float, _pos: int) -> str:
    return f"{x:.0f}%"


def last_valid_row(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    mask = df[cols].notna().any(axis=1)
    return df[mask].iloc[-1]


def draw_combo_chart(
    df: pd.DataFrame,
    line_cols: list[tuple[str, str, str]],
    bar_col: str,
    area_col: str,
    title: str,
    out_path: Path,
) -> dict[str, Any]:
    setup_fonts()
    plot_df = df.copy()
    numeric_cols = [bar_col, area_col] + [col for col, _label, _color in line_cols]
    for col in numeric_cols:
        plot_df[col] = pd.to_numeric(plot_df[col], errors="coerce")
    x = plot_df["date"]
    fig, ax1 = plt.subplots(figsize=(16, 8), dpi=180)
    fig.patch.set_facecolor("#fbfbf8")
    ax1.set_facecolor("#fbfbf8")
    ax2 = ax1.twinx()

    width = 0.82
    ax2.bar(x, plot_df[bar_col].astype(float).to_numpy(), width=width, color="#a9c4d8", alpha=0.55, label="当日净流入")
    ax2.fill_between(
        x,
        plot_df[area_col].astype(float).to_numpy(),
        0,
        color="#d28b72",
        alpha=0.24,
        label="7日滚动合计净流入",
        linewidth=0,
    )
    ax2.plot(x, plot_df[area_col], color="#b8664f", linewidth=1.6, alpha=0.9)

    for col, label, color in line_cols:
        ax1.plot(x, plot_df[col], label=label, color=color, linewidth=2.2)

    ax1.set_title(title, loc="left", fontsize=19, fontweight="bold", pad=16)
    ax1.set_ylabel("收盘价（点）", fontsize=12)
    ax2.set_ylabel("净流入额（亿元）", fontsize=12)
    ax2.yaxis.set_major_formatter(FuncFormatter(y_100mn))
    ax1.grid(axis="y", color="#d8d8d8", linewidth=0.8, alpha=0.65)
    ax1.grid(axis="x", color="#eeeeee", linewidth=0.5, alpha=0.45)
    ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax1.set_xlim(plot_df["date"].min(), plot_df["date"].max() + pd.Timedelta(days=12))

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", ncol=4, frameon=False, fontsize=10)

    latest = last_valid_row(plot_df, [c for c, _, _ in line_cols] + [bar_col, area_col])
    text_lines = [latest["date"].strftime("%Y-%m-%d")]
    for col, label, _color in line_cols:
        text_lines.append(f"{label}: {fmt_num(latest[col], 2)}")
    text_lines.append(f"当日净流入: {fmt_num(latest[bar_col], 2)} 亿元")
    text_lines.append(f"7日滚动: {fmt_num(latest[area_col], 2)} 亿元")
    ax1.text(
        0.985,
        0.965,
        "\n".join(text_lines),
        transform=ax1.transAxes,
        ha="right",
        va="top",
        fontsize=10.5,
        bbox={"boxstyle": "round,pad=0.45", "facecolor": "#ffffff", "edgecolor": "#d0d0d0", "alpha": 0.9},
    )

    ax1.spines[["top", "right"]].set_visible(False)
    ax2.spines[["top", "left"]].set_visible(False)
    fig.autofmt_xdate(rotation=0)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return {
        "path": str(out_path.relative_to(ROOT)),
        "last_date": latest["date"].strftime("%Y-%m-%d"),
        "last_values": {col: None if pd.isna(latest[col]) else float(latest[col]) for col, _, _ in line_cols}
        | {
            bar_col: None if pd.isna(latest[bar_col]) else float(latest[bar_col]),
            area_col: None if pd.isna(latest[area_col]) else float(latest[area_col]),
        },
    }


def stock_code_to_sina_symbol(code: str) -> str:
    code = str(code).zfill(6)
    if code.startswith(("920", "8", "4")):
        return f"bj{code}"
    if code.startswith(("6", "5", "9")):
        return f"sh{code}"
    if code.startswith(("0", "1", "2", "3")):
        return f"sz{code}"
    return f"bj{code}"


def fetch_a_share_stock_list() -> pd.DataFrame:
    cache = RAW_DIR / "a_share_stock_list.csv"
    if ak is None:
        log_source("AkShare stock_zh_a_spot_em", "failed", AKSHARE_IMPORT_ERROR)
        if cache.exists():
            return pd.read_csv(cache, dtype={"code": str})
        return pd.DataFrame(columns=["code", "name", "symbol"])
    try:
        df = ak.stock_info_a_code_name()
        out = df[["code", "name"]].copy()
        out["code"] = out["code"].astype(str).str.zfill(6)
        out = out[~out["name"].astype(str).str.contains("退", na=False)]
        out["symbol"] = out["code"].map(stock_code_to_sina_symbol)
        out = out.drop_duplicates("code").sort_values("code")
        out.to_csv(cache, index=False)
        log_source("AkShare stock_info_a_code_name", "ok", f"A-share stock list: {len(out)} names")
        return out
    except Exception as exc:
        log_source("AkShare stock_info_a_code_name", "failed", repr(exc))
        if cache.exists():
            log_source("A-share stock list", "cache", str(cache))
            return pd.read_csv(cache, dtype={"code": str})
        return pd.DataFrame(columns=["code", "name", "symbol"])


def fetch_sina_stock_daily(row: pd.Series | dict[str, str], start: str, end: str) -> pd.DataFrame:
    code = str(row["code"]).zfill(6)
    symbol = row["symbol"]
    cache = TURNOVER_CACHE_DIR / f"{symbol}_{start}.csv"
    legacy_matches = sorted(TURNOVER_CACHE_DIR.glob(f"{symbol}_{start}_*.csv"))
    source_cache = cache if cache.exists() else (legacy_matches[-1] if legacy_matches else None)
    if source_cache and source_cache.exists():
        cached = pd.read_csv(source_cache, parse_dates=["date"], dtype={"code": str})
        cached["date"] = pd.to_datetime(cached["date"]).dt.normalize()
        if not cached.empty and cached["date"].max() >= pd.Timestamp(end):
            return cached
        missing_start = (cached["date"].max() + pd.Timedelta(days=1)).strftime("%Y%m%d") if not cached.empty else start.replace("-", "")
        missing = ak.stock_zh_a_daily(symbol=symbol, start_date=missing_start, end_date=end.replace("-", ""), adjust="")
        if not missing.empty:
            extra = missing[["date", "amount"]].copy()
            extra["date"] = pd.to_datetime(extra["date"]).dt.normalize()
            extra["amount_100mn"] = pd.to_numeric(extra["amount"], errors="coerce") / 1e8
            extra["code"] = code
            extra["name"] = row["name"]
            extra = extra[["date", "code", "name", "amount_100mn"]].dropna(subset=["date", "amount_100mn"])
            cached = pd.concat([cached, extra], ignore_index=True)
            cached = cached.drop_duplicates(["date", "code"], keep="last").sort_values("date")
            cached.to_csv(cache, index=False)
            return cached
        cached.to_csv(cache, index=False)
        return cached
    if ak is None:
        raise RuntimeError(AKSHARE_IMPORT_ERROR)
    df = ak.stock_zh_a_daily(symbol=symbol, start_date=start.replace("-", ""), end_date=end.replace("-", ""), adjust="")
    if df.empty:
        raise ValueError("empty daily history")
    out = df[["date", "amount"]].copy()
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    out["amount_100mn"] = pd.to_numeric(out["amount"], errors="coerce") / 1e8
    out["code"] = code
    out["name"] = row["name"]
    out = out[["date", "code", "name", "amount_100mn"]].dropna(subset=["date", "amount_100mn"])
    out.to_csv(cache, index=False)
    return out


def fetch_sina_stock_daily_worker(row_dict: dict[str, str], start: str, end: str) -> tuple[str, str | None, str | None]:
    try:
        df = fetch_sina_stock_daily(row_dict, start, end)
        if df.empty:
            return row_dict["symbol"], None, "empty"
        return row_dict["symbol"], df.to_csv(index=False), None
    except Exception as exc:
        return row_dict["symbol"], None, repr(exc)[:180]


def build_turnover_concentration(indices: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    start = TURNOVER_START_DATE
    idx = indices[indices["date"] >= pd.Timestamp(start)].dropna(subset=["上证指数"]).copy()
    latest = idx["date"].max()
    if pd.isna(latest):
        raise RuntimeError("No 2026 index dates available for turnover module.")
    end = pd.Timestamp(latest).strftime("%Y-%m-%d")
    stocks = fetch_a_share_stock_list()
    if stocks.empty:
        raise RuntimeError("No A-share stock list available.")

    rows = []
    failures = []

    stock_rows = stocks[["code", "name", "symbol"]].to_dict("records")
    with ProcessPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(fetch_sina_stock_daily_worker, row, start, end) for row in stock_rows]
        for n, future in enumerate(as_completed(futures), 1):
            symbol, csv_text, err = future.result()
            if csv_text:
                df = pd.read_csv(StringIO(csv_text), parse_dates=["date"], dtype={"code": str})
                rows.append(df)
            else:
                failures.append((symbol, err or "empty"))
            if n % 500 == 0:
                print(f"stock daily fetched: {n}/{len(stocks)}", flush=True)

    for symbol, err in failures[:40]:
        log_source("Sina A-share daily", "failed", f"{symbol}: {err}")
    if len(failures) > 40:
        log_source("Sina A-share daily", "failed", f"{len(failures) - 40} additional failed symbols omitted")
    if not rows:
        raise RuntimeError("No stock daily turnover data fetched.")

    detail = pd.concat(rows, ignore_index=True)
    detail = detail[detail["date"] >= pd.Timestamp(start)].copy()
    detail = detail.sort_values(["date", "amount_100mn"], ascending=[True, False])
    detail["rank"] = detail.groupby("date")["amount_100mn"].rank(method="first", ascending=False).astype(int)

    total = detail.groupby("date", as_index=False)["amount_100mn"].sum().rename(columns={"amount_100mn": "market_amount_100mn"})
    top10 = detail[detail["rank"] <= 10].groupby("date", as_index=False)["amount_100mn"].sum().rename(columns={"amount_100mn": "top10_amount_100mn"})
    top100 = detail[detail["rank"] <= 100].groupby("date", as_index=False)["amount_100mn"].sum().rename(columns={"amount_100mn": "top100_amount_100mn"})
    top1000 = detail[detail["rank"] <= 1000].groupby("date", as_index=False)["amount_100mn"].sum().rename(columns={"amount_100mn": "top1000_amount_100mn"})
    top_names = (
        detail[detail["rank"] <= 10]
        .sort_values(["date", "rank"])
        .groupby("date")
        .apply(lambda g: "、".join(g["name"].astype(str).tolist()), include_groups=False)
        .reset_index(name="top10_names")
    )
    summary = total.merge(top10, on="date", how="left").merge(top100, on="date", how="left").merge(top1000, on="date", how="left").merge(top_names, on="date", how="left")
    for n in [10, 100, 1000]:
        summary[f"top{n}_share_pct"] = summary[f"top{n}_amount_100mn"] / summary["market_amount_100mn"] * 100
    summary = summary.merge(idx[["date", "上证指数"]], on="date", how="left")

    detail.to_csv(PROCESSED_DIR / "a_share_daily_turnover_rank_detail.csv", index=False)
    summary.to_csv(PROCESSED_DIR / "a_share_turnover_concentration.csv", index=False)
    log_source("Sina A-share daily", "ok", f"{len(rows)} symbols ok, {len(failures)} symbols failed")
    return summary, detail


def draw_turnover_concentration_chart(df: pd.DataFrame, out_path: Path) -> dict[str, Any]:
    setup_fonts()
    plot_df = df.copy()
    for col in ["top10_share_pct", "top100_share_pct", "top1000_share_pct", "上证指数"]:
        plot_df[col] = pd.to_numeric(plot_df[col], errors="coerce")
    plot_df = plot_df.sort_values("date")
    x = plot_df["date"]

    fig, ax1 = plt.subplots(figsize=(16, 8), dpi=180)
    fig.patch.set_facecolor("#fbfbf8")
    ax1.set_facecolor("#fbfbf8")
    ax2 = ax1.twinx()

    latest = plot_df.dropna(subset=["top10_share_pct"]).iloc[-1]
    latest_date = latest["date"].strftime("%Y-%m-%d")

    ax1.plot(x, plot_df["top10_share_pct"], color="#c5513c", linewidth=2.4, label="前10大占比")
    ax1.plot(x, plot_df["top100_share_pct"], color="#2f7cb8", linewidth=2.1, label="前100大占比")
    ax2.plot(x, plot_df["上证指数"], color="#7a6f64", linewidth=1.8, alpha=0.75, label="上证指数")

    ax1.set_title(f"A股成交额前10大公司交易集中度变化（截至{latest_date}）", loc="left", fontsize=18, fontweight="bold", pad=16)
    ax1.set_xlabel("日期", fontsize=12)
    ax1.set_ylabel("占全市场成交额比例（%）", fontsize=12)
    ax2.set_ylabel("上证指数收盘价（点）", fontsize=12)
    ax1.yaxis.set_major_formatter(FuncFormatter(pct_formatter))
    ax1.grid(axis="y", color="#d8d8d8", linewidth=0.8, alpha=0.65)
    ax1.grid(axis="x", color="#eeeeee", linewidth=0.5, alpha=0.45)
    ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax1.set_xlim(plot_df["date"].min(), plot_df["date"].max() + pd.Timedelta(days=8))

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", ncol=4, frameon=False, fontsize=10)

    ax1.annotate(
        f"{latest['top10_share_pct']:.2f}%",
        xy=(latest["date"], latest["top10_share_pct"]),
        xytext=(12, 0),
        textcoords="offset points",
        va="center",
        fontsize=11,
        color="#c5513c",
        bbox={"boxstyle": "round,pad=0.25", "facecolor": "#ffffff", "edgecolor": "#e2c1b9", "alpha": 0.9},
    )
    label = (
        f"{latest['date'].strftime('%Y-%m-%d')}\n"
        f"前10: {latest['top10_share_pct']:.2f}%\n"
        f"前100: {latest['top100_share_pct']:.2f}%\n"
        f"全市场成交额: {latest['market_amount_100mn']:,.0f} 亿元"
    )
    ax1.text(
        0.985,
        0.965,
        label,
        transform=ax1.transAxes,
        ha="right",
        va="top",
        fontsize=10.5,
        bbox={"boxstyle": "round,pad=0.45", "facecolor": "#ffffff", "edgecolor": "#d0d0d0", "alpha": 0.9},
    )
    ax1.spines[["top", "right"]].set_visible(False)
    ax2.spines[["top", "left"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return {
        "path": str(out_path.relative_to(ROOT)),
        "last_date": latest["date"].strftime("%Y-%m-%d"),
        "last_values": {
            "top10_share_pct": float(latest["top10_share_pct"]),
            "top100_share_pct": float(latest["top100_share_pct"]),
            "market_amount_100mn": float(latest["market_amount_100mn"]),
        },
    }


def normalize_valuation_df(df: pd.DataFrame, name: str, pe_col: str) -> pd.DataFrame:
    out = df.copy()
    if "日期" in out.columns:
        out = out.rename(columns={"日期": "date"})
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    out["pe_ttm"] = pd.to_numeric(out[pe_col], errors="coerce")
    out["index_name"] = name
    out = out[["date", "index_name", "pe_ttm"]].dropna(subset=["date", "pe_ttm"])
    out = out[out["date"] >= pd.Timestamp(VALUATION_START_DATE)].sort_values("date")
    return out


def fetch_local_wind_valuation(index_name: str) -> pd.DataFrame:
    path = RAW_DIR / "index_pe_ttm_wind.csv"
    if not path.exists():
        log_source("Local Wind PE_TTM CSV", "missing", str(path))
        return pd.DataFrame(columns=["date", "index_name", "pe_ttm"])
    df = pd.read_csv(path)
    needed = {"date", "index_name", "pe_ttm"}
    if not needed.issubset(df.columns):
        raise ValueError(f"{path} must contain columns: date,index_name,pe_ttm")
    out = df[df["index_name"].astype(str).eq(index_name)].copy()
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    out["pe_ttm"] = pd.to_numeric(out["pe_ttm"], errors="coerce")
    out = out[["date", "index_name", "pe_ttm"]].dropna(subset=["date", "pe_ttm"])
    out = out[out["date"] >= pd.Timestamp(VALUATION_START_DATE)].sort_values("date")
    log_source("Local Wind PE_TTM CSV", "ok", f"{index_name}: {len(out)} rows")
    return out


def fetch_valuation_series(cfg: dict[str, str]) -> pd.DataFrame:
    cache = PROCESSED_DIR / f"valuation_{cfg['key']}.csv"
    if cache.exists():
        cached = pd.read_csv(cache, parse_dates=["date"])
        if not cached.empty and cached["date"].max() >= pd.Timestamp(datetime.now().date() - timedelta(days=10)):
            log_source("Index PE_TTM", "cache", f"{cfg['name']}: {len(cached)} rows")
            return cached
    frames = []
    if ak is None:
        log_source("Index PE_TTM", "failed", AKSHARE_IMPORT_ERROR)
    else:
        for attempt in range(3):
            try:
                if cfg["source"] == "legulegu_index":
                    raw = ak.stock_index_pe_lg(symbol=cfg["symbol"])
                    frames.append(normalize_valuation_df(raw, cfg["name"], "滚动市盈率"))
                    log_source("Legulegu index PE", "ok", f"{cfg['name']}: {len(frames[-1])} rows")
                    break
                if cfg["source"] == "legulegu_market":
                    raw = ak.stock_market_pe_lg(symbol=cfg["symbol"])
                    frames.append(normalize_valuation_df(raw, cfg["name"], "平均市盈率"))
                    log_source("Legulegu market PE", "ok", f"{cfg['name']}: {len(frames[-1])} rows")
                    break
            except Exception as exc:
                log_source("Index PE_TTM", "failed", f"{cfg['name']} attempt {attempt + 1}: {repr(exc)[:160]}")
                time.sleep(1.2 * (attempt + 1))
    if cfg["source"] == "local_csv":
        frames.append(fetch_local_wind_valuation(cfg["name"]))
    if frames:
        out = pd.concat(frames, ignore_index=True).drop_duplicates(["date", "index_name"], keep="last").sort_values("date")
    else:
        out = pd.DataFrame(columns=["date", "index_name", "pe_ttm"])
    if out.empty and cache.exists():
        log_source("Index PE_TTM", "cache-fallback", f"{cfg['name']}: using stale cache")
        return pd.read_csv(cache, parse_dates=["date"])
    out.to_csv(cache, index=False)
    return out


def draw_valuation_channel_chart(df: pd.DataFrame, index_name: str, out_path: Path) -> dict[str, Any]:
    setup_fonts()
    plot_df = df.copy().sort_values("date")
    plot_df["pe_ttm"] = pd.to_numeric(plot_df["pe_ttm"], errors="coerce")
    plot_df = plot_df.dropna(subset=["pe_ttm"])
    if plot_df.empty:
        raise ValueError(f"No PE_TTM data for {index_name}")
    mu = plot_df["pe_ttm"].mean()
    sigma = plot_df["pe_ttm"].std(ddof=0)
    levels = [
        ("均值", mu, "#34495e", 1.8),
        ("μ + 1σ", mu + sigma, "#2f7cb8", 1.3),
        ("μ - 1σ", mu - sigma, "#2f7cb8", 1.3),
        ("μ + 2σ", mu + 2 * sigma, "#c5513c", 1.2),
        ("μ - 2σ", mu - 2 * sigma, "#c5513c", 1.2),
    ]
    fig, ax = plt.subplots(figsize=(16, 7.2), dpi=180)
    fig.patch.set_facecolor("#fbfbf8")
    ax.set_facecolor("#fbfbf8")
    ax.plot(plot_df["date"], plot_df["pe_ttm"], color="#1f77b4", linewidth=2.2, label="PE_TTM")
    for label, value, color, width in levels:
        ax.axhline(value, linestyle="--", color=color, linewidth=width, alpha=0.9, label=f"{label}: {value:.2f}")
    latest = plot_df.iloc[-1]
    latest_date = latest["date"].strftime("%Y-%m-%d")
    ax.annotate(
        f"{latest['pe_ttm']:.2f}x",
        xy=(latest["date"], latest["pe_ttm"]),
        xytext=(12, 0),
        textcoords="offset points",
        va="center",
        fontsize=11,
        color="#1f77b4",
        bbox={"boxstyle": "round,pad=0.25", "facecolor": "#ffffff", "edgecolor": "#bdd4e8", "alpha": 0.9},
    )
    ax.set_title(f"{index_name}历史滚动市盈率及标准差通道（截至{latest_date}）", loc="left", fontsize=18, fontweight="bold", pad=16)
    ax.set_xlabel("日期", fontsize=12)
    ax.set_ylabel("滚动市盈率（倍）", fontsize=12)
    ax.grid(axis="y", color="#d8d8d8", linewidth=0.8, alpha=0.65)
    ax.grid(axis="x", color="#eeeeee", linewidth=0.5, alpha=0.45)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.legend(loc="upper left", ncol=3, frameon=False, fontsize=9.5)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return {
        "path": str(out_path.relative_to(ROOT)),
        "last_date": latest["date"].strftime("%Y-%m-%d"),
        "last_values": {
            "pe_ttm": float(latest["pe_ttm"]),
            "mean": float(mu),
            "std": float(sigma),
            "mean_plus_1std": float(mu + sigma),
            "mean_minus_1std": float(mu - sigma),
            "mean_plus_2std": float(mu + 2 * sigma),
            "mean_minus_2std": float(mu - 2 * sigma),
        },
    }


def build_valuation_charts() -> tuple[list[dict[str, Any]], list[str]]:
    chart_infos = []
    notes = []
    all_frames = []
    for i, cfg in enumerate(VALUATION_INDEXES, 1):
        df = fetch_valuation_series(cfg)
        if df.empty:
            notes.append(f"{cfg['name']} PE_TTM 暂无可用数据，需补充本地 CSV 或接入 Wind/Tushare。")
            continue
        all_frames.append(df)
        out_path = CHART_DIR / f"fig_004{chr(96+i)}_{cfg['key']}_pe_ttm_channel.png"
        info = draw_valuation_channel_chart(df, cfg["name"], out_path)
        info["title"] = f"图四：{cfg['name']}历史滚动市盈率及标准差通道（截至{info['last_date']}）"
        chart_infos.append(info)
    if all_frames:
        pd.concat(all_frames, ignore_index=True).to_csv(PROCESSED_DIR / "index_pe_ttm_valuation.csv", index=False)
    return chart_infos, notes


def build_page(metadata: dict[str, Any]) -> None:
    assets_dir = SITE_DIR / "assets" / "charts"
    assets_dir.mkdir(parents=True, exist_ok=True)
    for chart_file in CHART_DIR.glob("*.png"):
        shutil.copy2(chart_file, assets_dir / chart_file.name)

    chart1 = "assets/charts/fig_001_broad_etf_flow.png"
    chart2 = "assets/charts/fig_002_star50_etf_flow.png"
    chart3 = "assets/charts/fig_003_a_share_turnover_concentration.png"
    chart5 = "assets/charts/fig_005_index_amount_share.png"
    updated_at = metadata["updated_at"]
    latest = metadata["latest_common_date"]
    asset_version = latest.replace("-", "")
    source_notes = "<br>".join(metadata["notes"])
    chart3_info = metadata.get("chart_files", [{}, {}, {}])[2] if len(metadata.get("chart_files", [])) >= 3 else {}
    chart3_date = chart3_info.get("last_date", "最新")
    amount_share_meta_path = PROCESSED_DIR / "index_amount_share.metadata.json"
    amount_share_date = "最新"
    if amount_share_meta_path.exists():
        try:
            amount_share_date = json.loads(amount_share_meta_path.read_text(encoding="utf-8")).get("latest_date", "最新")
        except Exception:
            amount_share_date = "最新"
    amount_share_html = ""
    if (CHART_DIR / "fig_005_index_amount_share.png").exists():
        amount_share_version = str(amount_share_date).replace("-", "")
        amount_share_html = f"""      <section class="chart-section">
        <h2>图五：主要宽基指数成交额占全A成交额比例（截至{amount_share_date}）</h2>
        <img src="{chart5}?v={amount_share_version}" alt="主要宽基指数成交额占全A成交额比例">
        <p class="note">数据来自中证指数官网指数行情接口。分子为沪深300、中证500、中证1000、中证2000指数成交金额；分母优先使用 Wind 全A成交额，当前公开数据用中证全指成交金额作为代理口径。</p>
      </section>"""
    valuation_sections = []
    for chart in metadata.get("valuation_chart_files", []):
        rel = "assets/charts/" + Path(chart["path"]).name
        title = chart.get("title", "指数历史滚动市盈率及标准差通道")
        valuation_sections.append(
            f"""      <section class="chart-section">
      <h2>{title}</h2>
      <img src="{rel}?v={asset_version}" alt="{title}">
      <p class="note">统计区间自 {VALUATION_START_DATE} 起；水平虚线分别为均值、均值±1倍标准差、均值±2倍标准差。</p>
    </section>"""
        )
    valuation_html = "\n\n".join(valuation_sections)
    if not valuation_html:
        valuation_html = """      <section class="chart-section">
      <h2>图四：指数估值通道</h2>
      <p class="note">当前未取得可绘制的 PE_TTM 序列。Wind 指数可通过 data/raw/index_pe_ttm_wind.csv 接入。</p>
    </section>"""
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>投研数据页</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <main>
    <header class="page-head">
      <div>
        <p class="eyebrow">Investment Data Monitor</p>
        <h1>投研数据页</h1>
      </div>
      <div class="meta">
        <div>更新：{updated_at}</div>
        <div>区间：2025-01-01 至 {latest}</div>
      </div>
    </header>

    <nav class="category-tabs" aria-label="投研数据分类">
      <button class="category-tab active" type="button" data-target="market" aria-selected="true">行情</button>
      <button class="category-tab" type="button" data-target="macro" aria-selected="false">宏观</button>
      <button class="category-tab" type="button" data-target="valuation" aria-selected="false">估值</button>
      <button class="category-tab" type="button" data-target="earnings" aria-selected="false">盈利</button>
      <button class="category-tab" type="button" data-target="liquidity" aria-selected="false">流动性</button>
      <button class="category-tab" type="button" data-target="sentiment" aria-selected="false">情绪</button>
    </nav>

    <section class="category-panel active" id="panel-market" data-category="market">
      <div class="category-head"><h2>行情</h2></div>
      <section class="chart-section">
        <h2>图一：沪深300/上证指数 vs. 大宽基ETF资金流</h2>
        <img src="{chart1}?v={asset_version}" alt="沪深300与上证指数走势及大宽基ETF资金流">
        <p class="note">样本：510300、510310、510330、159919、510050。净流入口径为份额变化乘以单位净值；7日滚动合计按交易日滚动计算。</p>
      </section>

      <section class="chart-section">
        <h2>图二：科创50指数 vs. 科创50ETF资金流</h2>
        <img src="{chart2}?v={asset_version}" alt="科创50指数走势及科创50ETF资金流">
        <p class="note">样本：588000 华夏科创50ETF。净流入口径为份额变化乘以单位净值；7日滚动合计按交易日滚动计算。</p>
      </section>
{amount_share_html}
    </section>

    <section class="category-panel" id="panel-macro" data-category="macro" hidden>
      <div class="category-head"><h2>宏观</h2></div>
      <p class="empty-note">暂无图表。</p>
    </section>

    <section class="category-panel" id="panel-valuation" data-category="valuation" hidden>
      <div class="category-head"><h2>估值</h2></div>
{valuation_html}
    </section>

    <section class="category-panel" id="panel-earnings" data-category="earnings" hidden>
      <div class="category-head"><h2>盈利</h2></div>
      <p class="empty-note">暂无图表。</p>
    </section>

    <section class="category-panel" id="panel-liquidity" data-category="liquidity" hidden>
      <div class="category-head"><h2>流动性</h2></div>
      <section class="chart-section">
        <h2>图三：A股成交额前10大公司交易集中度变化（截至{chart3_date}）</h2>
        <img src="{chart3}?v={asset_version}" alt="A股成交额前10大公司交易集中度变化">
        <p class="note">样本覆盖当前沪深京A股清单；逐股获取2026年以来日成交额，按交易日排序计算前10、前100成交额占比。右轴为上证指数收盘价。</p>
      </section>
    </section>

    <section class="category-panel" id="panel-sentiment" data-category="sentiment" hidden>
      <div class="category-head"><h2>情绪</h2></div>
      <p class="empty-note">暂无图表。</p>
    </section>

    <section class="data-note">
      <h2>数据说明与风险提示</h2>
      <p>{source_notes}</p>
      <p>当日净流入为 0 或长时间缺失时，可能代表 ETF 份额未更新、接口未披露或数据源暂不可用，不应机械解读为真实无申赎。</p>
    </section>
  </main>
  <script src="app.js"></script>
</body>
</html>
"""
    css = """body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif;
  color: #1f2933;
  background: #f6f5f1;
}
main {
  max-width: 1180px;
  margin: 0 auto;
  padding: 36px 22px 56px;
}
.page-head {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  align-items: end;
  border-bottom: 1px solid #d8d4ca;
  padding-bottom: 20px;
}
.eyebrow {
  margin: 0 0 8px;
  color: #607080;
  font-size: 13px;
  letter-spacing: .08em;
  text-transform: uppercase;
}
h1 {
  margin: 0;
  font-size: 34px;
  font-weight: 760;
}
h2 {
  margin: 0 0 14px;
  font-size: 21px;
}
.meta {
  text-align: right;
  color: #59636e;
  font-size: 14px;
  line-height: 1.8;
}
.category-tabs {
  position: sticky;
  top: 0;
  z-index: 5;
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 1px;
  margin: 22px 0 10px;
  background: #d8d4ca;
  border: 1px solid #d8d4ca;
}
.category-tab {
  appearance: none;
  border: 0;
  border-radius: 0;
  min-height: 44px;
  padding: 0 12px;
  background: #f8f7f3;
  color: #53606b;
  font: inherit;
  font-size: 15px;
  cursor: pointer;
}
.category-tab:hover,
.category-tab:focus-visible {
  background: #ffffff;
  color: #1f2933;
  outline: none;
}
.category-tab.active {
  background: #203040;
  color: #ffffff;
  font-weight: 700;
}
.category-panel {
  padding-top: 20px;
}
.category-head {
  padding: 8px 0 12px;
  border-bottom: 1px solid #dedbd3;
}
.category-head h2 {
  font-size: 26px;
}
.chart-section {
  padding: 30px 0 18px;
  border-bottom: 1px solid #dedbd3;
}
.chart-section img {
  display: block;
  width: 100%;
  height: auto;
  background: #fbfbf8;
  border: 1px solid #dedbd3;
}
.note, .data-note p, .empty-note {
  color: #4f5c66;
  font-size: 14px;
  line-height: 1.75;
}
.empty-note {
  margin: 22px 0 36px;
}
.data-note {
  padding-top: 30px;
}
@media (max-width: 720px) {
  main {
    padding: 28px 16px 44px;
  }
  .page-head {
    display: block;
  }
  .meta {
    text-align: left;
    margin-top: 14px;
  }
  h1 {
    font-size: 28px;
  }
  .category-tabs {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .category-tab {
    min-height: 42px;
    font-size: 14px;
  }
}
"""
    js = """const tabs = Array.from(document.querySelectorAll(".category-tab"));
const panels = Array.from(document.querySelectorAll(".category-panel"));

function activateCategory(target) {
  tabs.forEach((tab) => {
    const active = tab.dataset.target === target;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", active ? "true" : "false");
  });
  panels.forEach((panel) => {
    const active = panel.dataset.category === target;
    panel.classList.toggle("active", active);
    panel.hidden = !active;
  });
}

tabs.forEach((tab) => {
  tab.addEventListener("click", () => activateCategory(tab.dataset.target));
});
"""
    (SITE_DIR / "index.html").write_text(html, encoding="utf-8")
    (SITE_DIR / "styles.css").write_text(css, encoding="utf-8")
    (SITE_DIR / "app.js").write_text(js, encoding="utf-8")


def main() -> None:
    load_env_file()
    ensure_dirs()
    ranking = fetch_current_etf_ranking()

    indices = fetch_indices(START_DATE, END_CAP)
    indices_full = indices.copy()
    trading_dates = indices.dropna(subset=["沪深300"])["date"].sort_values().tolist()
    if not trading_dates:
        raise RuntimeError("No trading dates fetched.")

    # SSE ETF scale is usually T+1. Pick the latest date where the primary SSE
    # share source works, so both charts share one strict time window.
    latest_common = None
    for day in reversed(trading_dates):
        try:
            sample = fetch_sse_scale_one_day(day)
            if not sample.empty:
                latest_common = pd.Timestamp(day).normalize()
                break
        except Exception:
            continue
    if latest_common is None:
        raise RuntimeError("Could not determine latest common ETF flow date.")

    trading_dates = [pd.Timestamp(d).normalize() for d in trading_dates if pd.Timestamp(d).normalize() <= latest_common]
    indices = indices[indices["date"].isin(trading_dates)].copy()

    etfs_all = ETF_SELECTION + [STAR50_ETF]
    flow_detail = build_etf_flow(trading_dates, etfs_all, START_DATE, latest_common.strftime("%Y-%m-%d"))
    broad = aggregate_flows(flow_detail, [e["code"] for e in ETF_SELECTION], "broad_etf_flow.csv")
    star = aggregate_flows(flow_detail, [STAR50_ETF["code"]], "star50_etf_flow.csv")

    chart1_df = indices[["date", "沪深300", "上证指数"]].merge(broad, on="date", how="left")
    chart2_df = indices[["date", "科创50"]].merge(star, on="date", how="left")

    chart1_info = draw_combo_chart(
        chart1_df,
        [("沪深300", "沪深300", "#1f77b4"), ("上证指数", "上证指数", "#2a9d55")],
        "daily_net_inflow_100mn",
        "rolling_7d_net_inflow_100mn",
        "沪深300与上证指数走势及大宽基ETF资金流",
        CHART_DIR / "fig_001_broad_etf_flow.png",
    )
    chart2_info = draw_combo_chart(
        chart2_df,
        [("科创50", "科创50", "#7b4ab8")],
        "daily_net_inflow_100mn",
        "rolling_7d_net_inflow_100mn",
        "科创50指数走势及科创50ETF资金流",
        CHART_DIR / "fig_002_star50_etf_flow.png",
    )
    turnover, turnover_detail = build_turnover_concentration(indices_full)
    chart3_info = draw_turnover_concentration_chart(
        turnover,
        CHART_DIR / "fig_003_a_share_turnover_concentration.png",
    )
    valuation_chart_infos, valuation_notes = build_valuation_charts()

    missing_szse = flow_detail[(flow_detail["venue"] == "SZSE") & (flow_detail["net_inflow_100mn"].isna())]["code"].unique()
    notes = [
        "指数收盘价来自腾讯公开行情 K 线接口；ETF规模排序快照来自东方财富公开行情列表。",
        "ETF份额优先来自交易所公开数据：上交所历史ETF规模接口；ETF单位净值来自 AkShare 封装的东方财富基金净值接口，净值缺失时用ETF二级市场收盘价估算。",
        "净流入额 = 当日份额变化 × 估值价格 / 1亿元。首个交易日因缺少上一交易日份额，不计算净流入。",
    ]
    if len(missing_szse):
        notes.append(
            "深交所ETF历史份额公开接口当前未返回可按日期查询的数据，且本机未配置可用 Tushare token；"
            f"{'、'.join(missing_szse)} 的历史申赎口径净流入暂缺，图一合计会按已取得ETF求和并在明细CSV保留缺失标记。"
        )
    zero_warning_dates = broad.loc[broad["daily_net_inflow_100mn"].fillna(0).eq(0), "date"].dt.strftime("%Y-%m-%d").tail(3).tolist()
    if zero_warning_dates:
        notes.append(f"最近出现合计净流入为0的日期：{', '.join(zero_warning_dates)}；需留意份额数据可能未更新。")
    notes.append(
        "成交集中度使用新浪财经A股日行情逐股抓取成交额，并以抓取到的沪深京A股个股成交额合计作为全市场成交额；"
        "新上市、退市或接口缺失个股可能造成轻微口径差异。"
    )
    notes.extend(valuation_notes)

    metadata = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "start_date": START_DATE,
        "latest_common_date": latest_common.strftime("%Y-%m-%d"),
        "etf_selection": ETF_SELECTION,
        "star50_etf": STAR50_ETF,
        "chart_files": [chart1_info, chart2_info, chart3_info],
        "valuation_chart_files": valuation_chart_infos,
        "notes": notes,
        "source_logs": [log.__dict__ for log in SOURCE_LOGS],
    }
    (PROCESSED_DIR / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    build_page(metadata)
    print(json.dumps({"latest_common_date": metadata["latest_common_date"], "charts": metadata["chart_files"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
