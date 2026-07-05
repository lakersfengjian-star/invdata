#!/usr/bin/env python3
"""Build all-market turnover series from the dashboard's all-A proxy."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = ROOT / "data" / "processed"
SOURCE_CSV = PROCESSED_DIR / "index_amount_share.csv"
OUT_CSV = PROCESSED_DIR / "market_turnover.csv"
METADATA_JSON = PROCESSED_DIR / "market_turnover.metadata.json"
START_DATE = "2024-09-24"


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    if not SOURCE_CSV.exists():
        raise RuntimeError("Missing index_amount_share.csv; run update_index_amount_share.py first.")
    df = pd.read_csv(SOURCE_CSV, parse_dates=["date"])
    out = df[df["date"].ge(pd.Timestamp(START_DATE))][["date", "wind_all_a_proxy_amount"]].copy()
    out = out.rename(columns={"wind_all_a_proxy_amount": "market_turnover_100mn"})
    out["market_turnover_100mn"] = pd.to_numeric(out["market_turnover_100mn"], errors="coerce")
    out = out.dropna(subset=["date", "market_turnover_100mn"]).sort_values("date")
    out["turnover_ma5_100mn"] = out["market_turnover_100mn"].rolling(5, min_periods=1).mean()
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    out.to_csv(OUT_CSV, index=False)
    metadata = {
        "source": "CSI All Share trading value from index_amount_share.csv",
        "status": "ok",
        "start_date": out["date"].min(),
        "latest_date": out["date"].max(),
        "unit": "100mn CNY",
        "notes": [
            "当前使用中证全指成交金额作为沪深京全市场成交额公开代理口径；若后续接入交易所逐日汇总或 Wind 全A 精确口径，可替换本序列。"
        ],
    }
    METADATA_JSON.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"rows": len(out), **metadata}, ensure_ascii=False))


if __name__ == "__main__":
    main()
