#!/usr/bin/env python3
"""Update the SSE sentiment index (等权情绪指标, 3-year percentile edition).

Methodology (reverse-engineered from input/情绪指标.xlsx, all formulas
numerically verified against the workbook):

  1. 股债收益差      = yield_10y/100 - 1/PE_TTM            (上证指数 PE_TTM, 中债10年国债收益率)
  2. 换手率          = MA20(自由流通换手率)                  (增量用普通换手率 × 2.607 折算, 见下)
  3. 流动性冲击 LS   = MA60(ILLIQ) - MA20(ILLIQ), ILLIQ = |pct_chg%|/amt(亿) × 1e6
  4. 新发基金占比    = rolling30(偏股型份额) / rolling30(总份额)
  5. 乖离率 BIAS250  = (close/MA250(close) - 1) × 100
  6. RSI90           = Wilder RSI(90)
  每个指标取过去 750 个观测的分位数(mean(window <= value)),
  情绪指数 = 六个 3 年分位数的等权平均。

Data flow (token-free after initial setup):
  - history  : input/情绪指标.xlsx  →  data/raw/sentiment_base.csv  (extract_sentiment_base.py)
  - increments: Wind AIFin Market CLI (PE/收盘/换手率/成交额涨跌幅/基金份额 EDB)
                + akshare bond_china_yield (10Y yield, public)
                cached under data/raw/sentiment_cache/ for resume
  - output   : data/processed/sentiment_index.csv + sentiment_index.metadata.json

Run:  python scripts/update_sentiment_index.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / ".work" / "vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

SKILL_DIR = Path.home() / ".agents" / "skills" / "wind-mcp-skill"
CLI = SKILL_DIR / "scripts" / "cli.mjs"

BASE_CSV = ROOT / "data" / "raw" / "sentiment_base.csv"
CACHE_DIR = ROOT / "data" / "raw" / "sentiment_cache"
PROCESSED_DIR = ROOT / "data" / "processed"
OUT_CSV = PROCESSED_DIR / "sentiment_index.csv"
METADATA_JSON = PROCESSED_DIR / "sentiment_index.metadata.json"

# 上证指数普通换手率 → 自由流通换手率的折算系数。
# 2026-07-01..03 Excel free_turn_n / Wind 普通换手率 = 3.6149/1.3864 = 3.5383/1.3571
# = 3.2247/1.2369 ≈ 2.607(即 总股本/自由流通股本, 缓慢变化)。
FREE_TURN_RATIO = 2.607

PCTL_WINDOW = 750  # 3 年 ≈ 750 个交易日观测

CHUNK_MONTHS = 4  # Wind NL 单次约 100 行, 4 个月≈85 个交易日, 安全


def cli_call(server: str, tool: str, params: dict, timeout: int = 120) -> dict:
    cmd = ["node", str(CLI), "call", server, tool, json.dumps(params, ensure_ascii=False)]
    proc = subprocess.run(cmd, cwd=SKILL_DIR, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"CLI exit {proc.returncode}: {proc.stdout[:240]}")
    outer = json.loads(proc.stdout)
    if outer.get("isError"):
        raise RuntimeError(f"CLI isError: {proc.stdout[:240]}")
    inner = json.loads(outer["content"][0]["text"])
    if inner.get("error"):
        raise RuntimeError(f"Wind error: {json.dumps(inner['error'], ensure_ascii=False)[:240]}")
    return inner


def cache_call(kind: str, begin: str, end: str, fetch) -> dict:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{kind}_{begin}_{end}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    last_exc = None
    for attempt in range(1, 4):
        try:
            inner = fetch()
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(inner, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
            return inner
        except Exception as exc:  # noqa: BLE001
            if "没找到数据" in str(exc):
                # 周末/节假日等无交易数据区间: 写空缓存, 视为成功。
                inner = {"data": {"data": []}}
                path.write_text(json.dumps(inner, ensure_ascii=False), encoding="utf-8")
                return inner
            last_exc = exc
            time.sleep(2 * attempt)
    raise RuntimeError(f"{kind} {begin}-{end}: {last_exc}")


def nl_rows(inner: dict) -> tuple[list[str], list[list]]:
    blocks = inner.get("data", {}).get("data", [])
    if not blocks:
        return [], []
    cols = [c["name"] for c in blocks[0]["columns"]]
    return cols, blocks[0]["rows"]


def chunks(begin_d: date, end_d: date) -> list[tuple[str, str]]:
    out = []
    cur = begin_d
    while cur <= end_d:
        nxt = min(cur + pd.DateOffset(months=CHUNK_MONTHS).to_pytimedelta() if False else (pd.Timestamp(cur) + pd.DateOffset(months=CHUNK_MONTHS)).date(), end_d)
        out.append((cur.strftime("%Y%m%d"), nxt.strftime("%Y%m%d")))
        cur = nxt + timedelta(days=1)
    return out


def cn(yyyymmdd: str) -> str:
    return f"{yyyymmdd[:4]}年{int(yyyymmdd[4:6])}月{int(yyyymmdd[6:8])}日"


def fetch_increments(last: date, today: date) -> pd.DataFrame:
    """Fetch incremental rows after `last` up to `today`. Returns DataFrame indexed by date."""
    if last >= today:
        return pd.DataFrame()
    begin_d = last + timedelta(days=1)
    inc: dict[str, pd.Series] = {}

    def grab(kind: str, question_fn, col_map: dict[str, str], date_key: str = "日期"):
        series: dict[str, dict] = {new: {} for new in col_map.values()}
        for b, e in chunks(begin_d, today):
            inner = cache_call(f"{kind}_{kind}", b, e, lambda: cli_call(*question_fn(b, e)))
            cols, rows = nl_rows(inner)
            if not cols:
                continue
            di = cols.index(date_key)
            for old, new in col_map.items():
                ci = next((i for i, c in enumerate(cols) if old in c), None)
                if ci is None:
                    continue
                for r in rows:
                    if r[di] is None or r[ci] is None:
                        continue
                    series[new][str(r[di])[:10]] = r[ci]
        for new, kv in series.items():
            if kv:
                s = pd.Series(kv, name=new)
                s.index = pd.to_datetime(s.index)
                inc[new] = pd.to_numeric(s, errors="coerce")

    grab(
        "pe", lambda b, e: ("index_data", "get_index_fundamentals",
                            {"question": f"上证指数{cn(b)}至{cn(e)}每日市盈率(TTM)"}),
        {"市盈率": "pe_ttm"})
    grab(
        "close", lambda b, e: ("index_data", "get_index_technicals",
                               {"question": f"上证指数{cn(b)}至{cn(e)}每日收盘价"}),
        {"收盘价": "close"})
    grab(
        "turn", lambda b, e: ("index_data", "get_index_technicals",
                              {"question": f"上证指数{cn(b)}至{cn(e)}每日换手率"}),
        {"换手率": "turn_std"})
    grab(
        "amt", lambda b, e: ("index_data", "get_index_technicals",
                             {"question": f"上证指数{cn(b)}至{cn(e)}每日成交额(亿元)和涨跌幅"}),
        {"成交额": "amt", "涨跌幅": "pct_chg"})

    # 基金份额 EDB(日频, 亿份)
    def grab_edb():
        kv_eq, kv_all = {}, {}
        inner = cache_call(
            "fund_edb", begin_d.strftime("%Y%m%d"), today.strftime("%Y%m%d"),
            lambda: cli_call("economic_data", "natural_language_get_edb_data", {
                "executionMode": "fetch",
                "question": "M0060433,M8524625",
                "beginDate": begin_d.strftime("%Y%m%d"),
                "endDate": today.strftime("%Y%m%d"),
            }))
        for item in inner.get("data", {}).get("data", []):
            code = item.get("meta", {}).get("code")
            target = kv_eq if code == "M0060433" else kv_all if code == "M8524625" else None
            if target is None:
                continue
            for d, v in zip(item.get("date", []), item.get("value", [])):
                if v is not None:
                    target[f"{d[:4]}-{d[4:6]}-{d[6:8]}"] = v
        for name, kv in (("fund_eq", kv_eq), ("fund_all", kv_all)):
            if kv:
                s = pd.Series(kv, name=name)
                s.index = pd.to_datetime(s.index)
                inc[name] = pd.to_numeric(s, errors="coerce")
    grab_edb()

    # 10 年国债收益率(akshare 中债公开数据)
    try:
        import akshare as ak

        y = ak.bond_china_yield(start_date=begin_d.strftime("%Y%m%d"), end_date=today.strftime("%Y%m%d"))
        if not y.empty:
            y["日期"] = pd.to_datetime(y["日期"])
            s = y.set_index("日期")["10年"]
            inc["yield_10y"] = pd.to_numeric(s, errors="coerce")
    except Exception as exc:  # noqa: BLE001
        print(f"warn: akshare bond_china_yield failed: {type(exc).__name__}: {exc}", flush=True)

    if not inc:
        return pd.DataFrame()
    df = pd.DataFrame(inc).sort_index()
    if "turn_std" in df:
        df["free_turn"] = df["turn_std"] * FREE_TURN_RATIO
        df = df.drop(columns=["turn_std"])
    return df


def rolling_percentile(s: pd.Series, window: int = PCTL_WINDOW) -> pd.Series:
    """Percentile of each value within its trailing `window` observations."""
    arr = s.to_numpy(dtype=float)
    out = np.full(len(arr), np.nan)
    for i in range(len(arr)):
        lo = max(0, i - window + 1)
        win = arr[lo : i + 1]
        win = win[~np.isnan(win)]
        if len(win) >= 60 and not np.isnan(arr[i]):
            out[i] = (win <= arr[i]).mean()
    return pd.Series(out, index=s.index)


def compute(base: pd.DataFrame) -> pd.DataFrame:
    df = base.set_index("date").sort_index().copy()
    close = df["close"].dropna()

    # 1. 股债收益差
    pe_spread = df["yield_10y"] / 100 - 1 / df["pe_ttm"]
    # 2. 换手率 MA20
    turn_ma20 = df["free_turn"].rolling(20, min_periods=15).mean()
    # 3. 流动性冲击 LS
    illiq = (df["pct_chg"].abs() / df["amt"]) * 1e6
    ls = illiq.rolling(60, min_periods=45).mean() - illiq.rolling(20, min_periods=15).mean()
    # 4. 30 日新发基金占比
    fund30 = df["fund_eq"].rolling(30, min_periods=20).sum() / df["fund_all"].rolling(30, min_periods=20).sum()
    # 5. BIAS250
    bias = (close / close.rolling(250, min_periods=200).mean() - 1) * 100
    # 6. RSI90 (Wilder)
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / 90, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 90, adjust=False).mean()
    rsi = 100 - 100 / (1 + avg_gain / avg_loss)

    indicators = pd.DataFrame({
        "pe_spread": pe_spread,
        "turn_ma20": turn_ma20,
        "ls": ls,
        "fund30": fund30,
        "bias250": bias.reindex(df.index),
        "rsi90": rsi.reindex(df.index),
    })
    pct = pd.DataFrame({name: rolling_percentile(indicators[name]) for name in indicators.columns})
    pct.columns = [f"{n}_pct3" for n in indicators.columns]
    out = pd.concat([df[["close"]], indicators, pct], axis=1)
    pct_cols = list(pct.columns)
    out["sentiment_3y"] = out[pct_cols].mean(axis=1, skipna=False)
    return out


def main() -> None:
    if not BASE_CSV.exists():
        print(json.dumps({"status": "error", "error": "missing data/raw/sentiment_base.csv; run scripts/extract_sentiment_base.py first"}, ensure_ascii=False))
        sys.exit(1)
    base = pd.read_csv(BASE_CSV, parse_dates=["date"])
    last = base["date"].max().date()
    today = date.today()
    inc = fetch_increments(last, today)
    if not inc.empty:
        inc = inc.reset_index().rename(columns={"index": "date"})
        inc["date"] = pd.to_datetime(inc["date"])
        base = pd.concat([base, inc], ignore_index=True)
        base = base.drop_duplicates(subset="date", keep="last").sort_values("date")
        base.to_csv(BASE_CSV, index=False)
        print(f"incremental rows added: {len(inc)} ({inc['date'].min().date()} → {inc['date'].max().date()})", flush=True)
    else:
        print("no incremental data (already up to date or sources unavailable)", flush=True)

    full = compute(base)
    full = full.reset_index()
    full["date"] = pd.to_datetime(full["date"]).dt.strftime("%Y-%m-%d")
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    full.dropna(subset=["sentiment_3y"]).to_csv(OUT_CSV, index=False)

    valid = full.dropna(subset=["sentiment_3y"])
    latest = valid.iloc[-1]
    metadata = {
        "source": "Wind AIFin Market CLI + akshare 中债 + Excel 历史基座",
        "status": "ok",
        "latest_date": latest["date"],
        "sentiment_3y": round(float(latest["sentiment_3y"]), 4),
        "components": {
            "股债收益差": None if pd.isna(latest["pe_spread_pct3"]) else round(float(latest["pe_spread_pct3"]), 4),
            "换手率": None if pd.isna(latest["turn_ma20_pct3"]) else round(float(latest["turn_ma20_pct3"]), 4),
            "流动性冲击": None if pd.isna(latest["ls_pct3"]) else round(float(latest["ls_pct3"]), 4),
            "新发基金占比": None if pd.isna(latest["fund30_pct3"]) else round(float(latest["fund30_pct3"]), 4),
            "乖离率": None if pd.isna(latest["bias250_pct3"]) else round(float(latest["bias250_pct3"]), 4),
            "RSI": None if pd.isna(latest["rsi90_pct3"]) else round(float(latest["rsi90_pct3"]), 4),
        },
        "method": "6指标等权,750交易日(≈3年)分位数",
        "frequency": "daily",
    }
    METADATA_JSON.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False))


if __name__ == "__main__":
    main()
