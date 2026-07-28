#!/usr/bin/env python3
"""Update CITIC level-1 industry PB percentile dispersion.

Metric:
  right axis = stddev of CITIC level-1 industry PB historical percentiles,
  smoothed by 5 trading days (MA5). Historical percentile uses a trailing
  10-year trading-day window.

Primary source:
  - gjdata AIndexValuation for CITIC industry PB_LF
  - gjdata AIndexWindIndustriesEOD for Wind All A close (881001.WI)
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from common import CITIC_LEVEL1, PROCESSED_DIR, write_metadata  # noqa: E402

GJ_INDEX = Path("/Users/jianfeng/.codex/skills/gjdata/scripts/index.py")
OUT_CSV = PROCESSED_DIR / "citic_pb_dispersion.csv"
OUT_META = PROCESSED_DIR / "citic_pb_dispersion.metadata.json"
START_DATE = "20050101"
WINDOW_DAYS = 2520
MIN_PERIODS = 1260


def run_gjdata_json(args: list[str]) -> list[dict]:
    if not GJ_INDEX.exists():
        raise FileNotFoundError(f"gjdata script not found: {GJ_INDEX}")
    cmd = ["python3", str(GJ_INDEX), *args, "--format", "json"]
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=True)
    text = proc.stdout.strip()
    if not text or text == "无数据":
        return []
    return json.loads(text)


def fetch_citic_pb() -> pd.DataFrame:
    codes = ",".join(CITIC_LEVEL1.keys())
    rows = run_gjdata_json([
        "get",
        "--table",
        "AIndexValuation",
        "--code",
        codes,
        "--start",
        START_DATE,
        "--end",
        datetime.now().strftime("%Y%m%d"),
        "--cols",
        "S_INFO_WINDCODE,TRADE_DT,PB_LF",
        "--limit",
        "400000",
    ])
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["TRADE_DT"])
    df["wind_code"] = df["S_INFO_WINDCODE"]
    df["industry"] = df["wind_code"].map(CITIC_LEVEL1)
    df["pb_lf"] = pd.to_numeric(df["PB_LF"], errors="coerce")
    return df[["date", "wind_code", "industry", "pb_lf"]].dropna(subset=["industry", "pb_lf"])


def fetch_wind_all_a_close() -> pd.DataFrame:
    rows = run_gjdata_json([
        "get",
        "--table",
        "AIndexWindIndustriesEOD",
        "--code",
        "881001.WI",
        "--start",
        START_DATE,
        "--end",
        datetime.now().strftime("%Y%m%d"),
        "--cols",
        "S_INFO_WINDCODE,TRADE_DT,S_DQ_CLOSE",
        "--limit",
        "20000",
    ])
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["TRADE_DT"])
    df["wind_all_a_close"] = pd.to_numeric(df["S_DQ_CLOSE"], errors="coerce")
    return df[["date", "wind_all_a_close"]].dropna()


def percentile_last(values: pd.Series) -> float:
    last = values.iloc[-1]
    return float(values.rank(pct=True).iloc[-1]) if pd.notna(last) else float("nan")


def build_dispersion(pb: pd.DataFrame, close: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for _, part in pb.sort_values("date").groupby("wind_code"):
        tmp = part.copy()
        tmp["pb_percentile_10y"] = tmp["pb_lf"].rolling(WINDOW_DAYS, min_periods=MIN_PERIODS).apply(percentile_last, raw=False)
        frames.append(tmp)
    pct = pd.concat(frames, ignore_index=True)
    dispersion = (
        pct.groupby("date")["pb_percentile_10y"]
        .agg(lambda s: s.dropna().std(ddof=1) if s.dropna().size >= 10 else pd.NA)
        .reset_index(name="pb_dispersion_raw")
    )
    dispersion["pb_dispersion_raw"] = pd.to_numeric(dispersion["pb_dispersion_raw"], errors="coerce")
    dispersion = dispersion.dropna(subset=["pb_dispersion_raw"]).sort_values("date")
    dispersion["pb_dispersion_ma5"] = dispersion["pb_dispersion_raw"].rolling(5, min_periods=3).mean()
    out = dispersion.merge(close, on="date", how="left")
    return out[["date", "wind_all_a_close", "pb_dispersion_raw", "pb_dispersion_ma5"]]


def main() -> None:
    source = "gjdata:AIndexValuation+AIndexWindIndustriesEOD"
    status = "ok"
    notes: list[str] = []
    try:
        pb = fetch_citic_pb()
        close = fetch_wind_all_a_close()
        if pb.empty:
            raise RuntimeError("empty CITIC PB data")
        if close.empty:
            notes.append("Wind All A close unavailable; chart will show PB dispersion only")
        df = build_dispersion(pb, close)
    except Exception as exc:  # noqa: BLE001
        notes.append(f"gjdata failed: {type(exc).__name__}: {str(exc)[:180]}")
        if OUT_CSV.exists():
            df = pd.read_csv(OUT_CSV, parse_dates=["date"])
            source = "local-cache:citic_pb_dispersion.csv"
            status = "cache-fallback"
        else:
            raise
    if df.empty:
        raise RuntimeError("CITIC PB dispersion has no available rows")
    df = df.drop_duplicates("date").sort_values("date")
    latest_date = df["date"].max().strftime("%Y-%m-%d")
    out = df.copy()
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    out.to_csv(OUT_CSV, index=False)
    write_metadata(
        OUT_META,
        source=source,
        status=status,
        latest_date=latest_date,
        unit="index/pctile-std",
        notes=[
            "PB percentile uses trailing 10-year trading-day window (2520 days, min 1260 observations).",
            "PB dispersion MA5 is the 5-trading-day moving average of cross-industry PB percentile standard deviation.",
            "left axis uses Wind All A close, code 881001.WI, table AIndexWindIndustriesEOD.",
            *notes,
        ],
    )
    print(json.dumps({"latest_date": latest_date, "rows": len(out), "status": status}, ensure_ascii=False))


if __name__ == "__main__":
    main()
