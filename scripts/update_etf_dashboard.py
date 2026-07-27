#!/usr/bin/env python3
"""Build the ETF flow dashboard datasets (data only).

This script fetches ETF share changes, index prices, valuation series, and
A-share turnover concentration data. Chart generation and site building are
handled by build_site_from_processed.py.

Data priority:
1. Exchange/public source: SSE/SZSE ETF share endpoint; Tencent public quote kline.
2. AkShare wrappers for fund NAV and exchange datasets.
3. Tushare hook, enabled when TUSHARE_TOKEN is configured.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import date, datetime
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from io import StringIO
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from common import (
    RAW_DIR,
    PROCESSED_DIR,
    CHART_DIR,
    CACHE_DIR,
    START_DATE,
    VALUATION_START_DATE,
    TURNOVER_START_DATE,
    END_CAP,
    ETF_SELECTION,
    STAR50_ETF,
    INDEX_SELECTION,
    VALUATION_INDEXES,
    ensure_dirs,
    load_env_file,
    log_source,
    SourceLog,
    SOURCE_LOGS,
    previous_bday,
    dataset_fresh,
)

import numpy as np
import pandas as pd

try:
    import akshare as ak
except Exception as exc:
    ak = None
    AKSHARE_IMPORT_ERROR = repr(exc)
else:
    AKSHARE_IMPORT_ERROR = ""

try:
    import requests
except Exception as exc:
    raise SystemExit("requests is required. Run: python3 -m pip install --target .work/vendor requests") from exc


TURNOVER_CACHE_DIR = CACHE_DIR / "sina_a_share_daily_2026"


# ================================================================ helpers ====

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


# ============================================================ index data ====

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


# ============================================================ ETF ranking ====

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


# ================================================================ NAV ====

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


# ============================================================ SSE shares ====

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
    headers = {"Referer": "https://www.sse.com.cn/", "User-Agent": "Mozilla/5.0"}
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


# ============================================================ SZSE shares ====

def fetch_szse_shares_chunk(start: pd.Timestamp, end: pd.Timestamp, codes: list[str]) -> pd.DataFrame:
    cache = CACHE_DIR / f"szse_scale_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}.csv"
    if cache.exists():
        df = pd.read_csv(cache, dtype={"基金代码": str}, parse_dates=["日期"])
    else:
        if ak is None:
            raise RuntimeError(AKSHARE_IMPORT_ERROR)
        df = ak.fund_scale_daily_szse(
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
            symbol="ETF",
        )
        df.to_csv(cache, index=False)
    if df.empty:
        return pd.DataFrame(columns=["date", "code", "shares"])
    sub = df[df["基金代码"].astype(str).str.zfill(6).isin(codes)][["日期", "基金代码", "基金份额"]].copy()
    sub = sub.rename(columns={"日期": "date", "基金代码": "code", "基金份额": "shares"})
    sub["date"] = pd.to_datetime(sub["date"], errors="coerce").dt.normalize()
    sub["code"] = sub["code"].astype(str).str.zfill(6)
    sub["shares"] = pd.to_numeric(sub["shares"], errors="coerce")
    return sub.dropna(subset=["date", "code", "shares"])


def fetch_szse_shares(dates: list[pd.Timestamp], codes: list[str]) -> pd.DataFrame:
    if not dates or not codes:
        return pd.DataFrame(columns=["date", "code", "shares"])
    wanted_dates = pd.to_datetime(pd.Series(dates)).dt.normalize()
    start = wanted_dates.min()
    end = wanted_dates.max()
    rows = []
    failures = []
    chunk_start = start
    while chunk_start <= end:
        chunk_end = min(chunk_start + pd.DateOffset(months=2, days=25), end)
        try:
            rows.append(fetch_szse_shares_chunk(pd.Timestamp(chunk_start), pd.Timestamp(chunk_end), codes))
        except Exception as exc:
            failures.append(f"{pd.Timestamp(chunk_start).date()} to {pd.Timestamp(chunk_end).date()}: {repr(exc)[:160]}")
        chunk_start = pd.Timestamp(chunk_end) + pd.Timedelta(days=1)

    for err in failures[:12]:
        log_source("SZSE ETF scale", "failed", err)
    if len(failures) > 12:
        log_source("SZSE ETF scale", "failed", f"{len(failures) - 12} additional failed chunks omitted")
    if not rows:
        return pd.DataFrame(columns=["date", "code", "shares"])
    out = pd.concat(rows, ignore_index=True).drop_duplicates(["date", "code"], keep="last")
    out = out[out["date"].isin(set(wanted_dates))]
    missing_dates = sorted(set(wanted_dates) - set(out["date"]))
    day_rows = []
    for missing_date in missing_dates:
        try:
            day_rows.append(fetch_szse_shares_chunk(pd.Timestamp(missing_date), pd.Timestamp(missing_date), codes))
        except Exception as exc:
            failures.append(f"{pd.Timestamp(missing_date).date()}: {repr(exc)[:160]}")
    if day_rows:
        out = pd.concat([out, *day_rows], ignore_index=True).drop_duplicates(["date", "code"], keep="last")
        out = out[out["date"].isin(set(wanted_dates))]
    log_source("SZSE ETF scale", "ok", f"{out['date'].nunique()} trading days, {len(failures)} failed chunks")
    return out[["date", "code", "shares"]]


# ============================================================ Tushare ====

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


# ============================================================ ETF flow ====

def build_etf_flow(dates: list[pd.Timestamp], etfs: list[dict[str, str]], start: str, end: str) -> pd.DataFrame:
    sse_codes = [e["code"] for e in etfs if e["venue"] == "SSE"]
    share_frames = []
    if sse_codes:
        share_frames.append(fetch_sse_shares(dates, sse_codes))
    szse_codes = [e["code"] for e in etfs if e["venue"] == "SZSE"]
    if szse_codes:
        szse_shares = fetch_szse_shares(dates, szse_codes)
        if not szse_shares.empty:
            share_frames.append(szse_shares)
    for etf in etfs:
        if etf["venue"] == "SZSE" and (
            not share_frames
            or not any(
                not frame.empty and frame["code"].astype(str).str.zfill(6).eq(etf["code"]).any()
                for frame in share_frames
            )
        ):
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


# ============================================================ turnover ====

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


def build_turnover_concentration(indices: pd.DataFrame, force: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    start = TURNOVER_START_DATE
    idx = indices[indices["date"] >= pd.Timestamp(start)].dropna(subset=["上证指数"]).copy()
    latest = idx["date"].max()
    if pd.isna(latest):
        raise RuntimeError("No 2026 index dates available for turnover module.")
    end = pd.Timestamp(latest).strftime("%Y-%m-%d")

    # Freshness guard: skip full re-fetch if output already covers previous bday.
    expected = previous_bday()
    out_csv = PROCESSED_DIR / "a_share_turnover_concentration.csv"
    if not force and dataset_fresh(["a_share_turnover_concentration.csv"], expected):
        log_source("Turnover concentration", "fresh", f"data already up to date ({expected.date()})")
        summary = pd.read_csv(out_csv, parse_dates=["date"])
        detail_path = PROCESSED_DIR / "a_share_daily_turnover_rank_detail.csv"
        detail = pd.read_csv(detail_path, parse_dates=["date"], dtype={"code": str}) if detail_path.exists() else pd.DataFrame()
        return summary, detail

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


# ============================================================ valuation ====

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
        if not cached.empty and cached["date"].max() >= pd.Timestamp(date.today() - pd.Timedelta(days=10)):
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


def build_valuation_data() -> list[str]:
    """Fetch valuation series and output index_pe_ttm_valuation.csv. Returns notes."""
    notes: list[str] = []
    all_frames = []
    for cfg in VALUATION_INDEXES:
        df = fetch_valuation_series(cfg)
        if df.empty:
            notes.append(f"{cfg['name']} PE_TTM 暂无可用数据，需补充本地 CSV 或接入 Wind/Tushare。")
            continue
        all_frames.append(df)
    if all_frames:
        pd.concat(all_frames, ignore_index=True).to_csv(PROCESSED_DIR / "index_pe_ttm_valuation.csv", index=False)
    return notes


# ================================================================ main ====

def main() -> None:
    load_env_file()
    ensure_dirs()

    # 1. Fetch index closes.
    indices = fetch_indices(START_DATE, END_CAP)
    indices_full = indices.copy()
    trading_dates = indices.dropna(subset=["沪深300"])["date"].sort_values().tolist()
    if not trading_dates:
        raise RuntimeError("No trading dates fetched.")

    # 2. Determine latest common date for ETF flow (SSE scale is usually T+1).
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

    # 3. Build ETF flow.
    etfs_all = ETF_SELECTION + [STAR50_ETF]
    flow_detail = build_etf_flow(trading_dates, etfs_all, START_DATE, latest_common.strftime("%Y-%m-%d"))
    aggregate_flows(flow_detail, [e["code"] for e in ETF_SELECTION], "broad_etf_flow.csv")
    aggregate_flows(flow_detail, [STAR50_ETF["code"]], "star50_etf_flow.csv")

    # 4. Build turnover concentration (with freshness guard).
    build_turnover_concentration(indices_full)

    # 5. Build valuation data.
    valuation_notes = build_valuation_data()

    # 6. Metadata.
    szse_missing_mask = (
        flow_detail["venue"].eq("SZSE")
        & flow_detail["net_inflow_100mn"].isna()
        & ~(flow_detail["shares"].notna() & flow_detail["shares_prev"].isna())
    )
    missing_szse = flow_detail[szse_missing_mask]["code"].unique()
    notes = [
        "指数收盘价来自腾讯公开行情 K 线接口；ETF规模排序快照来自东方财富公开行情列表。",
        "ETF份额优先来自交易所公开数据：上交所历史ETF规模接口；深交所ETF份额来自深交所基金规模日频接口；ETF单位净值来自 AkShare 封装的东方财富基金净值接口，净值缺失时用ETF二级市场收盘价估算。",
        "净流入额 = 当日份额变化 × 估值价格 / 1亿元。首个交易日因缺少上一交易日份额，不计算净流入。",
    ]
    if len(missing_szse):
        notes.append(
            "深交所ETF份额优先使用深交所基金规模日频接口；当前仍有部分日期未取得完整份额、估值或前值，"
            f"{'、'.join(missing_szse)} 的净流入会在明细CSV保留缺失标记。"
        )
    notes.extend(valuation_notes)

    metadata = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "start_date": START_DATE,
        "latest_common_date": latest_common.strftime("%Y-%m-%d"),
        "etf_selection": ETF_SELECTION,
        "star50_etf": STAR50_ETF,
        "notes": notes,
        "source_logs": [log.__dict__ for log in SOURCE_LOGS],
    }
    (PROCESSED_DIR / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"latest_common_date": metadata["latest_common_date"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
