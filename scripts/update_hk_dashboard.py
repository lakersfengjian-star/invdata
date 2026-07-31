#!/usr/bin/env python3
"""Update Hong Kong market dashboard datasets from Wind AIFin CLI.

Excel files in the project are treated as methodology references only. This
script pulls fresh time series from Wind and stores small processed CSV files so
the static site can rebuild without re-parsing workbooks.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from common import PROCESSED_DIR, ensure_dirs, previous_bday, write_metadata  # noqa: E402

WIND_SKILL_DIR = Path(
    os.environ.get("WIND_SKILL_DIR", Path.home() / ".agents" / "skills" / "wind-mcp-skill")
).expanduser()
CLI = WIND_SKILL_DIR / "scripts" / "cli.mjs"
RAW_DIR = ROOT / "data" / "raw"

DAILY_START = "20240101"
VALUATION_START = "20130101"
SOUTHBOUND_START = DAILY_START

OUT_SENTIMENT = PROCESSED_DIR / "hk_sentiment.csv"
OUT_RATES = PROCESSED_DIR / "hk_rates.csv"
OUT_FX = PROCESSED_DIR / "hk_fx.csv"
OUT_AH = PROCESSED_DIR / "hk_ah_premium.csv"
OUT_VALUATION = PROCESSED_DIR / "hk_hsi_valuation.csv"
OUT_DIVIDEND = PROCESSED_DIR / "hk_dividend_yield.csv"
OUT_SOUTHBOUND = PROCESSED_DIR / "southbound_flow.csv"
OUT_META = PROCESSED_DIR / "hk_dashboard.metadata.json"


def ymd(value: str) -> str:
    return pd.Timestamp(value).strftime("%Y%m%d")


def human_date(value: str) -> str:
    ts = pd.Timestamp(value)
    return f"{ts.year}年{ts.month}月{ts.day}日"


def parse_local_date(value) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("Asia/Shanghai").tz_localize(None)
    return ts.normalize()


def iter_quarters(begin: str, end: str) -> list[tuple[str, str]]:
    start = pd.Timestamp(begin)
    finish = pd.Timestamp(end)
    ranges: list[tuple[str, str]] = []
    cursor = start
    while cursor <= finish:
        q_end = min(cursor + pd.offsets.QuarterEnd(startingMonth=3), finish)
        ranges.append((cursor.strftime("%Y%m%d"), q_end.strftime("%Y%m%d")))
        cursor = q_end + pd.Timedelta(days=1)
    return ranges


def iter_months(begin: str, end: str) -> list[tuple[str, str]]:
    start = pd.Timestamp(begin)
    finish = pd.Timestamp(end)
    ranges: list[tuple[str, str]] = []
    cursor = start
    while cursor <= finish:
        month_end = min(cursor + pd.offsets.MonthEnd(0), finish)
        ranges.append((cursor.strftime("%Y%m%d"), month_end.strftime("%Y%m%d")))
        cursor = month_end + pd.Timedelta(days=1)
    return ranges


def concat_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def call_wind(server: str, tool: str, params: dict) -> list[pd.DataFrame]:
    proc = subprocess.run(
        ["node", str(CLI), "call", server, tool, json.dumps(params, ensure_ascii=False)],
        cwd=WIND_SKILL_DIR,
        text=True,
        capture_output=True,
        timeout=90,
        check=True,
    )
    outer = json.loads(proc.stdout)
    text = outer["content"][0]["text"]
    payload = json.loads(text)
    data = payload.get("data", {})
    blocks = data.get("data", [data])
    frames: list[pd.DataFrame] = []
    for block in blocks:
        columns = [col["name"] for col in block.get("columns", [])]
        rows = block.get("rows", [])
        if columns and rows:
            frames.append(pd.DataFrame(rows, columns=columns))
    return frames


def clean_dates(df: pd.DataFrame, col: str = "date") -> pd.DataFrame:
    out = df.copy()
    out[col] = out[col].apply(lambda value: parse_local_date(value) if pd.notna(value) else pd.NaT)
    return out.dropna(subset=[col]).sort_values(col)


def first_col(df: pd.DataFrame, patterns: list[str], exclude: list[str] | None = None) -> str | None:
    exclude = exclude or []
    for col in df.columns:
        name = str(col)
        if all(word in name for word in patterns) and not any(word in name for word in exclude):
            return col
    return None


def extract_metric(frames: list[pd.DataFrame], value_patterns: list[str], date_patterns: list[str] | None = None) -> pd.DataFrame:
    date_patterns = date_patterns or ["日期"]
    for df in frames:
        date_idx = None
        for idx, col in enumerate(df.columns):
            name = str(col)
            if all(word in name for word in date_patterns) or "时间" in name:
                date_idx = idx
                break
        candidates = [
            (idx, col)
            for idx, col in enumerate(df.columns)
            if all(word in str(col) for word in value_patterns) and "时间" not in str(col) and idx != date_idx
        ]
        value_idx = None
        if candidates:
            value_idx, _ = max(candidates, key=lambda item: pd.to_numeric(df.iloc[:, item[0]], errors="coerce").notna().sum())
        if date_idx is not None and value_idx is not None and pd.to_numeric(df.iloc[:, value_idx], errors="coerce").notna().any():
            out = df.iloc[:, [date_idx, value_idx]].copy()
            out.columns = ["date", "value"]
            out["value"] = pd.to_numeric(out["value"], errors="coerce")
            return clean_dates(out).dropna(subset=["value"])
    return pd.DataFrame(columns=["date", "value"])


def extract_code_close(frames: list[pd.DataFrame], wind_code: str) -> pd.DataFrame:
    for df in frames:
        if "Wind代码" in df.columns and not df[df["Wind代码"].eq(wind_code)].empty:
            sub = df[df["Wind代码"].eq(wind_code)].copy()
            date_col = first_col(sub, ["收盘价", "时间"]) or first_col(sub, ["日期"])
            value_col = first_col(sub, ["收盘价"], exclude=["时间"])
            if date_col and value_col:
                out = sub[[date_col, value_col]].copy()
                out.columns = ["date", "value"]
                out["value"] = pd.to_numeric(out["value"], errors="coerce")
                return clean_dates(out).dropna(subset=["value"])
    return pd.DataFrame(columns=["date", "value"])


def kline(windcode: str, begin: str, end: str) -> pd.DataFrame:
    frames = call_wind(
        "index_data",
        "get_index_kline",
        {"windcode": windcode, "begin_date": begin, "end_date": end, "period": "10"},
    )
    if not frames:
        return pd.DataFrame(columns=["date", "close"])
    df = frames[0]
    out = df[["TIME", "MATCH"]].copy()
    out.columns = ["date", "close"]
    out["close"] = pd.to_numeric(out["close"], errors="coerce")
    return clean_dates(out).dropna(subset=["close"])


def incremental_start(path: Path, required_start: str, overlap_days: int = 10) -> str:
    """Return required_start for first backfill; later return latest-overlap."""
    if not path.exists():
        return required_start
    try:
        existing = pd.read_csv(path, usecols=["date"], parse_dates=["date"])
    except Exception:
        return required_start
    if existing.empty:
        return required_start
    min_date = existing["date"].min()
    latest_date = existing["date"].max()
    required = pd.Timestamp(required_start)
    if pd.isna(min_date) or min_date > required + pd.Timedelta(days=7):
        return required_start
    return max(required, latest_date - pd.Timedelta(days=overlap_days)).strftime("%Y%m%d")


def needs_column_backfill(path: Path, column: str, max_missing_ratio: float = 0.05) -> bool:
    if not path.exists():
        return True
    try:
        df = pd.read_csv(path)
    except Exception:
        return True
    if df.empty or column not in df.columns:
        return True
    return df[column].isna().mean() > max_missing_ratio


def merge_existing(df: pd.DataFrame, path: Path) -> pd.DataFrame:
    if not path.exists():
        return df.copy()
    try:
        old = pd.read_csv(path, parse_dates=["date"])
    except Exception:
        return df.copy()
    out = pd.concat([old, df], ignore_index=True)
    dedupe_cols = ["date"]
    if "wind_code" in out.columns:
        dedupe_cols.append("wind_code")
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out = out.dropna(subset=["date"])
    value_cols = [col for col in out.columns if col not in dedupe_cols]

    def last_valid(series: pd.Series):
        valid = series.dropna()
        return valid.iloc[-1] if not valid.empty else pd.NA

    merged = out.groupby(dedupe_cols, as_index=False, sort=True)[value_cols].agg(last_valid)
    return merged.sort_values(dedupe_cols)


def rolling_z(series: pd.Series, window: int = 750, min_periods: int = 60) -> pd.Series:
    mean = series.rolling(window, min_periods=min_periods).mean()
    std = series.rolling(window, min_periods=min_periods).std(ddof=0)
    return (series - mean) / std.replace(0, pd.NA)


def fetch_southbound(begin: str, end: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for q_begin, q_end in iter_quarters(begin, end):
        question = f"获取{human_date(q_begin)}至{human_date(q_end)}沪市港股通、深市港股通、南向资金每日净流入和港股通指数H50069.CSI收盘价"
        frames.extend(call_wind("analytics_data", "get_financial_data", {"question": question, "lang": "CNS"}))
    records = []
    h50069 = extract_code_close(frames, "H50069.CSI").rename(columns={"value": "h50069_close"})
    for df in frames:
        date_col = first_col(df, ["交易日期"]) or first_col(df, ["日期"])
        net_col = first_col(df, ["南向资金", "净买入", "合计"]) or first_col(df, ["南向资金", "净流入"])
        sh_col = first_col(df, ["沪市港股通", "净买入"]) or first_col(df, ["沪市港股通", "净流入"])
        sz_col = first_col(df, ["深市港股通", "净买入"]) or first_col(df, ["深市港股通", "净流入"])
        if date_col and net_col:
            for _, row in df.iterrows():
                records.append(
                    {
                        "date": row[date_col],
                        "southbound_net_buy_100mn": row.get(net_col),
                        "southbound_buy_100mn": pd.NA,
                        "southbound_sell_100mn": pd.NA,
                        "southbound_cumulative_net_buy_trillion": pd.NA,
                        "sh_connect_net_buy_100mn": row.get(sh_col) if sh_col else pd.NA,
                        "sz_connect_net_buy_100mn": row.get(sz_col) if sz_col else pd.NA,
                    }
                )
    out = pd.DataFrame(records)
    if out.empty:
        return pd.DataFrame(columns=["date", "southbound_net_buy_100mn"])
    out = clean_dates(out)
    for col in out.columns:
        if col != "date":
            out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["southbound_net_buy_100mn"])
    if not h50069.empty:
        out = out.merge(h50069, on="date", how="left")
    else:
        out["h50069_close"] = pd.NA
    out["rolling_15d_net_buy_100mn"] = out["southbound_net_buy_100mn"].rolling(15, min_periods=15).sum()
    return out


def fetch_hk_daily(start: str, end: str) -> dict[str, pd.DataFrame]:
    hsi = kline("HSI.HI", start, end).rename(columns={"close": "hsi_close"})
    hstech = kline("HSTECH.HI", start, end).rename(columns={"close": "hstech_close"})
    vhsi = kline("VHSI.HI", start, end).rename(columns={"close": "vhsi_close"})

    rates_parts = []
    fx_parts = []
    ah_parts = []
    width_parts = []
    short_parts = []
    for q_begin, q_end in iter_quarters(start, end):
        rates_frames = call_wind(
            "analytics_data",
            "get_financial_data",
            {"question": f"获取{human_date(q_begin)}至{human_date(q_end)}HIBOR隔夜、美国10年期国债收益率", "lang": "CNS"},
        )
        hibor_q = extract_metric(rates_frames, ["HIBOR"]).rename(columns={"value": "hibor_on"})
        us10y_q = extract_metric(rates_frames, ["美国", "国债收益率", "10年"]).rename(columns={"value": "us10y"})
        rates_parts.append(hibor_q.merge(us10y_q, on="date", how="outer"))

        ah_frames = call_wind(
            "analytics_data",
            "get_financial_data",
            {"question": f"获取{human_date(q_begin)}至{human_date(q_end)}恒生沪深港通AH股溢价指数HSAHP.HI和H50069.CSI每日收盘价", "lang": "CNS"},
        )
        ah_q = extract_code_close(ah_frames, "HSAHP.HI").rename(columns={"value": "ah_premium"})
        h50069_q = extract_code_close(ah_frames, "H50069.CSI").rename(columns={"value": "h50069_close"})
        ah_parts.append(ah_q.merge(h50069_q, on="date", how="outer"))

        width_frames = call_wind(
            "analytics_data",
            "get_financial_data",
            {"question": f"获取{human_date(q_begin)}至{human_date(q_end)}恒生指数HSI.HI每日上涨家数和下跌家数", "lang": "CNS"},
        )
        width_records = []
        for df in width_frames:
            date_col = first_col(df, ["日期"])
            up_col = first_col(df, ["上涨"])
            down_col = first_col(df, ["下跌"])
            if date_col and up_col and down_col:
                tmp = df[[date_col, up_col, down_col]].copy()
                tmp.columns = ["date", "up_count", "down_count"]
                width_records.append(tmp)
        if width_records:
            width_parts.append(pd.concat(width_records, ignore_index=True))

        short_frames = call_wind(
            "analytics_data",
            "get_financial_data",
            {"question": f"获取{human_date(q_begin)}至{human_date(q_end)}香港市场每日卖空成交额占市场成交额比例", "lang": "CNS"},
        )
        short_parts.append(extract_metric(short_frames, ["卖空", "比例"]).rename(columns={"value": "short_ratio"}))

    for m_begin, m_end in iter_months(start, end):
        dxy_frames = call_wind(
            "analytics_data",
            "get_financial_data",
            {"question": f"获取{human_date(m_begin)}至{human_date(m_end)}美元指数USDX.FX每日收盘价", "lang": "CNS"},
        )
        usdhkd_frames = call_wind(
            "analytics_data",
            "get_financial_data",
            {"question": f"获取{human_date(m_begin)}至{human_date(m_end)}美元兑港元USDHKD.FX每日收盘价", "lang": "CNS"},
        )
        dxy_q = extract_code_close(dxy_frames, "USDX.FX").rename(columns={"value": "usd_index"})
        if dxy_q.empty:
            dxy_q = extract_metric(dxy_frames, ["美元指数"]).rename(columns={"value": "usd_index"})
        usdhkd_q = extract_code_close(usdhkd_frames, "USDHKD.FX").rename(columns={"value": "usdhkd"})
        if usdhkd_q.empty:
            usdhkd_q = extract_metric(usdhkd_frames, ["美元兑港元"]).rename(columns={"value": "usdhkd"})
        fx_parts.append(dxy_q.merge(usdhkd_q, on="date", how="outer"))

    rates = clean_dates(concat_frames(rates_parts)).drop_duplicates("date", keep="last") if rates_parts else pd.DataFrame(columns=["date", "hibor_on", "us10y"])
    fx = clean_dates(concat_frames(fx_parts)).drop_duplicates("date", keep="last") if fx_parts else pd.DataFrame(columns=["date", "usd_index", "usdhkd"])
    if not fx.empty:
        fx = fx.sort_values("date")
        for col in ["usd_index", "usdhkd"]:
            if col in fx:
                fx[col] = pd.to_numeric(fx[col], errors="coerce").ffill(limit=3)
    ah = clean_dates(concat_frames(ah_parts)).drop_duplicates("date", keep="last") if ah_parts else pd.DataFrame(columns=["date", "ah_premium", "h50069_close"])
    width = clean_dates(concat_frames(width_parts)).drop_duplicates("date", keep="last") if width_parts else pd.DataFrame(columns=["date", "up_count", "down_count"])
    short = clean_dates(concat_frames(short_parts)).drop_duplicates("date", keep="last") if short_parts else pd.DataFrame(columns=["date", "short_ratio"])
    for col in ["up_count", "down_count"]:
        if col in width:
            width[col] = pd.to_numeric(width[col], errors="coerce")
    if not width.empty:
        width.loc[width[["up_count", "down_count"]].sum(axis=1).eq(0), ["up_count", "down_count"]] = pd.NA
    for df in [rates, fx, ah, short]:
        for col in df.columns:
            if col != "date":
                df[col] = pd.to_numeric(df[col], errors="coerce")

    return {
        "hsi": hsi,
        "hstech": hstech,
        "vhsi": vhsi,
        "hibor": rates[["date", "hibor_on"]] if "hibor_on" in rates else pd.DataFrame(columns=["date", "hibor_on"]),
        "us10y": rates[["date", "us10y"]] if "us10y" in rates else pd.DataFrame(columns=["date", "us10y"]),
        "dxy": fx[["date", "usd_index"]] if "usd_index" in fx else pd.DataFrame(columns=["date", "usd_index"]),
        "usdhkd": fx[["date", "usdhkd"]] if "usdhkd" in fx else pd.DataFrame(columns=["date", "usdhkd"]),
        "ah": ah[["date", "ah_premium"]] if "ah_premium" in ah else pd.DataFrame(columns=["date", "ah_premium"]),
        "h50069": ah[["date", "h50069_close"]] if "h50069_close" in ah else pd.DataFrame(columns=["date", "h50069_close"]),
        "width": width,
        "short": short,
    }


def fetch_hsi_valuation(begin: str, end: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    cn10y_frames: list[pd.DataFrame] = []
    for q_begin, q_end in iter_quarters(begin, end):
        frames.extend(
            call_wind(
                "index_data",
                "get_index_fundamentals",
                {"question": f"HSI.HI恒生指数{human_date(q_begin)}至{human_date(q_end)}每日市盈率PE(TTM)、股息率TTM", "lang": "中文"},
            )
        )
        frames.extend(
            call_wind(
                "index_data",
                "get_index_fundamentals",
                {"question": f"HSI.HI恒生指数{human_date(q_begin)}至{human_date(q_end)}每日ERP", "lang": "中文"},
            )
        )
        cn10y_frames.extend(
            call_wind(
                "analytics_data",
                "get_financial_data",
                {"question": f"获取{human_date(q_begin)}至{human_date(q_end)}中国:国债到期收益率:10年每日数据", "lang": "CNS"},
            )
        )
    pe_frames = []
    erp_frames = []
    for df in frames:
        date_col = first_col(df, ["日期"]) or first_col(df, ["时间"])
        pe_col = first_col(df, ["PE_TTM"]) or first_col(df, ["市盈率"])
        div_col = first_col(df, ["股息率"])
        erp_col = first_col(df, ["ERP"])
        if date_col and pe_col:
            cols = [date_col, pe_col] + ([div_col] if div_col else [])
            tmp = df[cols].copy()
            tmp.columns = ["date", "pe_ttm"] + (["dividend_yield_ttm"] if div_col else [])
            pe_frames.append(tmp)
        if erp_col:
            erp_date = first_col(df, ["ERP", "时间"]) or date_col
            if erp_date:
                tmp = df[[erp_date, erp_col]].copy()
                tmp.columns = ["date", "erp"]
                erp_frames.append(tmp)
    valuation = pd.concat(pe_frames, ignore_index=True) if pe_frames else pd.DataFrame(columns=["date", "pe_ttm"])
    valuation = clean_dates(valuation) if not valuation.empty else valuation
    if erp_frames:
        erp = clean_dates(pd.concat(erp_frames, ignore_index=True))
        valuation = valuation.merge(erp, on="date", how="outer")
    for col in ["pe_ttm", "dividend_yield_ttm", "erp"]:
        if col in valuation:
            valuation[col] = pd.to_numeric(valuation[col], errors="coerce")
    cn10y = extract_metric(cn10y_frames, ["国债到期收益率", "10年"]).rename(columns={"value": "cn10y"})
    if not cn10y.empty:
        cn10y = clean_dates(cn10y)
        cn10y["cn10y"] = pd.to_numeric(cn10y["cn10y"], errors="coerce")
        valuation = valuation.merge(cn10y, on="date", how="left")
    valuation = clean_dates(valuation).drop_duplicates("date", keep="last")
    return recompute_valuation_stats(valuation)


def recompute_valuation_stats(valuation: pd.DataFrame) -> pd.DataFrame:
    if valuation.empty:
        return valuation
    valuation = clean_dates(valuation).sort_values("date")
    for col in ["pe_ttm", "dividend_yield_ttm", "erp"]:
        if col in valuation:
            valuation[col] = pd.to_numeric(valuation[col], errors="coerce")
    if "cn10y" not in valuation:
        valuation["cn10y"] = pd.NA
    valuation["cn10y"] = pd.to_numeric(valuation["cn10y"], errors="coerce")
    local_yield_path = RAW_DIR / "sentiment_base.csv"
    if local_yield_path.exists():
        local_yield = pd.read_csv(local_yield_path, usecols=["date", "yield_10y"])
        local_yield = clean_dates(local_yield).rename(columns={"yield_10y": "local_cn10y"})
        local_yield["local_cn10y"] = pd.to_numeric(local_yield["local_cn10y"], errors="coerce")
        valuation = valuation.merge(local_yield, on="date", how="left")
        valuation["cn10y"] = valuation["cn10y"].fillna(valuation["local_cn10y"])
        valuation = valuation.drop(columns=["local_cn10y"])
    if "erp" not in valuation:
        valuation["erp"] = pd.NA
    missing_erp = valuation["erp"].isna()
    valid_fallback = missing_erp & valuation["pe_ttm"].notna() & valuation["cn10y"].notna()
    valuation.loc[valid_fallback, "erp"] = 100 / valuation.loc[valid_fallback, "pe_ttm"] - valuation.loc[valid_fallback, "cn10y"]
    for col in ["pe_ttm", "erp"]:
        if col in valuation:
            valuation[f"{col}_mean"] = valuation[col].expanding(min_periods=60).mean()
            valuation[f"{col}_std"] = valuation[col].expanding(min_periods=60).std(ddof=0)
            valuation[f"{col}_pctile"] = valuation[col].expanding(min_periods=60).apply(
                lambda values: pd.Series(values).rank(pct=True).iloc[-1] * 100,
                raw=False,
            )
    return valuation


def fetch_dividend_snapshot(begin: str, end: str) -> pd.DataFrame:
    question = "获取{}至{}港股主要指数股息率TTM：930915.CSI、000922.CSI、884059.WI、931233.CSI、HSI.HI、000001.SH".format(human_date(begin), human_date(end))
    frames = call_wind("analytics_data", "get_financial_data", {"question": question, "lang": "CNS"})
    records = []
    for df in frames:
        code_col = "Wind代码" if "Wind代码" in df.columns else None
        name_col = "证券简称" if "证券简称" in df.columns else None
        date_col = first_col(df, ["股息率", "时间"]) or first_col(df, ["日期"])
        value_col = first_col(df, ["股息率"], exclude=["时间"])
        if code_col and name_col and date_col and value_col:
            tmp = df[[date_col, code_col, name_col, value_col]].copy()
            tmp.columns = ["date", "wind_code", "index_name", "dividend_yield_ttm"]
            records.append(tmp)
    out = pd.concat(records, ignore_index=True) if records else pd.DataFrame(columns=["date", "wind_code", "index_name", "dividend_yield_ttm"])
    if out.empty:
        return out
    out = clean_dates(out)
    out["dividend_yield_ttm"] = pd.to_numeric(out["dividend_yield_ttm"], errors="coerce")
    return out.dropna(subset=["dividend_yield_ttm"])


def write_csv(df: pd.DataFrame, path: Path) -> str:
    out = df.copy()
    if path.exists() and "date" in out:
        out = merge_existing(out, path)
    if "date" in out:
        out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    out.to_csv(path, index=False)
    return str(out["date"].dropna().max()) if "date" in out and not out.empty else ""


def coverage_note(df: pd.DataFrame, label: str, column: str, start: str, end: str) -> str | None:
    if df.empty or column not in df:
        return f"{label}：字段 {column} 缺失，未参与相关图表计算。"
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    sub = df[(df["date"].ge(start_ts)) & (df["date"].le(end_ts))].copy()
    if sub.empty:
        return f"{label}：{start_ts:%Y-%m-%d} 至 {end_ts:%Y-%m-%d} 无可用记录。"
    valid = sub.dropna(subset=[column])
    missing_count = len(sub) - len(valid)
    if valid.empty:
        return f"{label}：{start_ts:%Y-%m-%d} 至 {end_ts:%Y-%m-%d} 字段 {column} 全部缺失。"
    missing_ratio = missing_count / len(sub)
    if missing_ratio > 0.05:
        return (
            f"{label}：{column} 覆盖 {len(valid)}/{len(sub)} 个交易日，"
            f"首个有效日 {valid['date'].min():%Y-%m-%d}，最后有效日 {valid['date'].max():%Y-%m-%d}。"
        )
    return None


def main() -> None:
    ensure_dirs()
    end = ymd(previous_bday())
    today = datetime.now().strftime("%Y-%m-%d")
    notes: list[str] = []

    daily_start = incremental_start(OUT_SENTIMENT, DAILY_START)
    if needs_column_backfill(OUT_FX, "usdhkd"):
        daily_start = DAILY_START
    valuation_start = incremental_start(OUT_VALUATION, VALUATION_START, overlap_days=20)
    southbound_start = SOUTHBOUND_START if needs_column_backfill(OUT_SOUTHBOUND, "southbound_net_buy_100mn") else incremental_start(OUT_SOUTHBOUND, SOUTHBOUND_START)

    daily = fetch_hk_daily(daily_start, end)
    southbound = fetch_southbound(southbound_start, end)

    southbound = merge_existing(southbound, OUT_SOUTHBOUND)
    southbound = clean_dates(southbound)
    southbound["southbound_net_buy_100mn"] = pd.to_numeric(southbound["southbound_net_buy_100mn"], errors="coerce")
    southbound["rolling_15d_net_buy_100mn"] = southbound["southbound_net_buy_100mn"].rolling(15, min_periods=15).sum()

    sentiment = daily["hsi"].merge(daily["hstech"], on="date", how="outer").merge(daily["vhsi"], on="date", how="outer")
    sentiment = sentiment.merge(daily["width"], on="date", how="outer").merge(southbound[["date", "southbound_net_buy_100mn"]], on="date", how="left")
    sentiment = sentiment.merge(daily["short"], on="date", how="left")
    sentiment = merge_existing(sentiment, OUT_SENTIMENT)
    if "southbound_net_buy_100mn" in southbound:
        southbound_for_sentiment = southbound[["date", "southbound_net_buy_100mn"]].dropna(subset=["southbound_net_buy_100mn"]).copy()
        sentiment = sentiment.drop(columns=["southbound_net_buy_100mn"], errors="ignore").merge(southbound_for_sentiment, on="date", how="left")
    sentiment = clean_dates(sentiment)
    for col in ["hsi_close", "hstech_close", "vhsi_close", "up_count", "down_count", "southbound_net_buy_100mn", "short_ratio"]:
        if col in sentiment:
            sentiment[col] = pd.to_numeric(sentiment[col], errors="coerce")
    sentiment["hstech_hsi_ratio"] = sentiment["hstech_close"] / sentiment["hsi_close"]
    sentiment["advance_line"] = sentiment["up_count"] - sentiment["down_count"]
    sentiment["advance_line_ma20"] = sentiment["advance_line"].rolling(20, min_periods=5).mean()
    sentiment["southbound_ma20"] = sentiment["southbound_net_buy_100mn"].rolling(20, min_periods=5).mean()
    sentiment["breadth_z"] = rolling_z(sentiment["advance_line_ma20"])
    sentiment["vhsi_z"] = rolling_z(sentiment["vhsi_close"])
    sentiment["relative_z"] = rolling_z(sentiment["hstech_hsi_ratio"])
    sentiment["southbound_z"] = rolling_z(sentiment["southbound_ma20"])
    sentiment["short_z"] = rolling_z(sentiment["short_ratio"])
    sentiment["hk_sentiment_z"] = sentiment[["breadth_z", "vhsi_z", "relative_z", "southbound_z", "short_z"]].mean(axis=1, skipna=True)
    for label, column in [
        ("港股情绪-宽度分项", "breadth_z"),
        ("港股情绪-波动率分项", "vhsi_z"),
        ("港股情绪-恒科/恒指分项", "relative_z"),
        ("港股情绪-南向资金分项", "southbound_z"),
        ("港股情绪-卖空占比分项", "short_z"),
    ]:
        note = coverage_note(sentiment, label, column, DAILY_START, end)
        if note:
            notes.append(note)
    note = coverage_note(southbound, "南向资金净流入", "southbound_net_buy_100mn", SOUTHBOUND_START, end)
    if note:
        notes.append(note)

    rates = daily["hibor"].merge(daily["us10y"], on="date", how="outer")
    fx = daily["dxy"].merge(daily["usdhkd"], on="date", how="outer")
    ah = daily["ah"].merge(daily["h50069"], on="date", how="outer")
    valuation = fetch_hsi_valuation(valuation_start, end)
    valuation = recompute_valuation_stats(merge_existing(valuation, OUT_VALUATION))
    dividend = fetch_dividend_snapshot((pd.Timestamp(end) - pd.Timedelta(days=14)).strftime("%Y%m%d"), end)

    latest = {
        "hk_sentiment": write_csv(sentiment, OUT_SENTIMENT),
        "hk_rates": write_csv(rates, OUT_RATES),
        "hk_fx": write_csv(fx, OUT_FX),
        "hk_ah_premium": write_csv(ah, OUT_AH),
        "hk_hsi_valuation": write_csv(valuation, OUT_VALUATION),
        "hk_dividend_yield": write_csv(dividend, OUT_DIVIDEND),
        "southbound": write_csv(southbound, OUT_SOUTHBOUND),
    }
    write_metadata(
        OUT_META,
        source="Wind AIFin Market CLI: index_data.get_index_kline, index_data.get_index_fundamentals, analytics_data.get_financial_data",
        status="ok" if not notes else "partial",
        latest_date=max(v for v in latest.values() if v),
        notes=notes,
        extra={"latest_by_dataset": latest, "built_at": today, "run_start": {"daily": daily_start, "valuation": valuation_start, "southbound": southbound_start}},
    )
    print(json.dumps({"status": "ok" if not notes else "partial", "latest": latest, "notes": notes}, ensure_ascii=False))


if __name__ == "__main__":
    main()
