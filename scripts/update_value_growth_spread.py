#!/usr/bin/env python3
"""Update value-growth style spread.

Metric:
  中证红利指数股息率 - 双创50盈利收益率(100 / PE_TTM)

Primary source: gjdata AIndexValuation.
Fallback: existing processed CSV if gjdata is unavailable.
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
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from common import PROCESSED_DIR, write_metadata  # noqa: E402

GJ_INDEX = Path(
    os.environ.get("GJDATA_SCRIPT", Path.home() / ".codex" / "skills" / "gjdata" / "scripts" / "index.py")
).expanduser()
OUT_CSV = PROCESSED_DIR / "value_growth_spread.csv"
OUT_META = PROCESSED_DIR / "value_growth_spread.metadata.json"
START_DATE = "20210101"
DIVIDEND_CODE = "000922.CSI"
GROWTH_CODE = "931643.CSI"


def run_gjdata_json(args: list[str]) -> list[dict]:
    if not GJ_INDEX.exists():
        raise FileNotFoundError(f"gjdata script not found: {GJ_INDEX}")
    cmd = [sys.executable, str(GJ_INDEX), *args, "--format", "json"]
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=True)
    text = proc.stdout.strip()
    if not text or text == "无数据":
        return []
    return json.loads(text)


def fetch_from_gjdata() -> pd.DataFrame:
    rows = run_gjdata_json([
        "get",
        "--table",
        "AIndexValuation",
        "--code",
        f"{DIVIDEND_CODE},{GROWTH_CODE}",
        "--start",
        START_DATE,
        "--end",
        datetime.now().strftime("%Y%m%d"),
        "--cols",
        "S_INFO_WINDCODE,TRADE_DT,DIVIDEND_YIELD,PE_TTM",
        "--limit",
        "20000",
    ])
    if not rows:
        return pd.DataFrame()
    raw = pd.DataFrame(rows)
    raw["date"] = pd.to_datetime(raw["TRADE_DT"])
    raw["DIVIDEND_YIELD"] = pd.to_numeric(raw["DIVIDEND_YIELD"], errors="coerce")
    raw["PE_TTM"] = pd.to_numeric(raw["PE_TTM"], errors="coerce")

    dividend = (
        raw[raw["S_INFO_WINDCODE"].eq(DIVIDEND_CODE)][["date", "DIVIDEND_YIELD"]]
        .rename(columns={"DIVIDEND_YIELD": "dividend_yield"})
        .dropna()
    )
    growth = (
        raw[raw["S_INFO_WINDCODE"].eq(GROWTH_CODE)][["date", "PE_TTM"]]
        .rename(columns={"PE_TTM": "growth_pe_ttm"})
        .dropna()
    )
    df = dividend.merge(growth, on="date", how="inner").sort_values("date")
    df["growth_earnings_yield"] = 100 / df["growth_pe_ttm"]
    df["spread"] = df["dividend_yield"] - df["growth_earnings_yield"]
    return df[["date", "dividend_yield", "growth_pe_ttm", "growth_earnings_yield", "spread"]]


def main() -> None:
    source = "gjdata:AIndexValuation"
    status = "ok"
    notes: list[str] = []
    try:
        df = fetch_from_gjdata()
    except Exception as exc:  # noqa: BLE001
        notes.append(f"gjdata failed: {type(exc).__name__}: {str(exc)[:180]}")
        if OUT_CSV.exists():
            df = pd.read_csv(OUT_CSV, parse_dates=["date"])
            source = "local-cache:value_growth_spread.csv"
            status = "cache-fallback"
        else:
            raise
    if df.empty:
        raise RuntimeError("value-growth spread has no available rows")
    df = df.dropna(subset=["spread"]).drop_duplicates("date").sort_values("date")
    latest_date = df["date"].max().strftime("%Y-%m-%d")
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    out.to_csv(OUT_CSV, index=False)
    write_metadata(
        OUT_META,
        source=source,
        status=status,
        latest_date=latest_date,
        unit="pct",
        notes=[
            "spread = 中证红利指数股息率 - 双创50盈利收益率(100/PE_TTM)",
            "primary source: gjdata AIndexValuation, codes 000922.CSI and 931643.CSI",
            *notes,
        ],
    )
    print(json.dumps({"latest_date": latest_date, "rows": len(out), "status": status}, ensure_ascii=False))


if __name__ == "__main__":
    main()
