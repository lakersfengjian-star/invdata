#!/usr/bin/env python3
"""Update style index performance data from gjdata.

The output supports the sentiment panel style return heatmap. Data source is
fixed to gjdata AIndexEODPrices first; when gjdata is unavailable, the existing
local cache is retained so the site can still build.
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
OUT_CSV = PROCESSED_DIR / "style_index_performance.csv"
OUT_META = PROCESSED_DIR / "style_index_performance.metadata.json"
START_DATE = "20240101"

STYLE_INDEXES = {
    "000300.SH": "沪深300",
    "000905.SH": "中证500",
    "000852.SH": "中证1000",
    "932000.CSI": "中证2000",
    "000998.CSI": "中证TMT",
    "h30269.CSI": "红利低波",
    "000922.CSI": "中证红利",
    "000688.SH": "科创50",
}


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
        "AIndexEODPrices",
        "--code",
        ",".join(STYLE_INDEXES.keys()),
        "--start",
        START_DATE,
        "--end",
        datetime.now().strftime("%Y%m%d"),
        "--cols",
        "S_INFO_WINDCODE,TRADE_DT,S_DQ_CLOSE,S_DQ_PCTCHANGE",
        "--limit",
        "30000",
    ])
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["wind_code"] = df["S_INFO_WINDCODE"]
    df["date"] = pd.to_datetime(df["TRADE_DT"], errors="coerce")
    df["index_name"] = df["wind_code"].map(STYLE_INDEXES)
    df["close"] = pd.to_numeric(df["S_DQ_CLOSE"], errors="coerce")
    df["pct_change"] = pd.to_numeric(df["S_DQ_PCTCHANGE"], errors="coerce")
    return (
        df[["date", "wind_code", "index_name", "close", "pct_change"]]
        .dropna(subset=["date", "index_name", "close"])
        .sort_values(["wind_code", "date"])
    )


def main() -> None:
    source = "gjdata:AIndexEODPrices"
    status = "ok"
    notes: list[str] = []
    try:
        df = fetch_from_gjdata()
    except Exception as exc:  # noqa: BLE001
        notes.append(f"gjdata failed: {type(exc).__name__}: {str(exc)[:180]}")
        if OUT_CSV.exists():
            df = pd.read_csv(OUT_CSV, parse_dates=["date"])
            source = "local-cache:style_index_performance.csv"
            status = "cache-fallback"
        else:
            raise

    if df.empty:
        raise RuntimeError("style index performance has no available rows")
    df = df.drop_duplicates(["date", "wind_code"], keep="last").sort_values(["date", "wind_code"])
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
        unit="pct/point",
        notes=[
            "style return heatmap uses close prices from gjdata AIndexEODPrices",
            "returns are calculated during site build for 1D, 5D, 20D, 60D and YTD windows",
            *notes,
        ],
        extra={"rows": len(out)},
    )
    print(json.dumps({"latest_date": latest_date, "rows": len(out), "status": status}, ensure_ascii=False))


if __name__ == "__main__":
    main()
