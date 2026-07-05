#!/usr/bin/env python3
"""Update southbound trading net-buy series."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / ".work" / "vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

import akshare as ak
import pandas as pd


PROCESSED_DIR = ROOT / "data" / "processed"
OUT_CSV = PROCESSED_DIR / "southbound_flow.csv"
METADATA_JSON = PROCESSED_DIR / "southbound_flow.metadata.json"
START_DATE = "2026-01-01"


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    raw = ak.stock_hsgt_hist_em(symbol="南向资金")
    if raw.empty:
        raise RuntimeError("东方财富沪深港通历史接口未返回南向资金数据。")

    out = raw.rename(
        columns={
            "日期": "date",
            "当日成交净买额": "southbound_net_buy_100mn",
            "买入成交额": "southbound_buy_100mn",
            "卖出成交额": "southbound_sell_100mn",
            "历史累计净买额": "southbound_cumulative_net_buy_trillion",
        }
    )[
        [
            "date",
            "southbound_net_buy_100mn",
            "southbound_buy_100mn",
            "southbound_sell_100mn",
            "southbound_cumulative_net_buy_trillion",
        ]
    ].copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    numeric_cols = [col for col in out.columns if col != "date"]
    for col in numeric_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out[out["date"].ge(pd.Timestamp(START_DATE))]
    out = out.dropna(subset=["date", "southbound_net_buy_100mn"]).sort_values("date")
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    out.to_csv(OUT_CSV, index=False)

    metadata = {
        "source": "Eastmoney HSGT history API via AkShare stock_hsgt_hist_em(symbol='南向资金')",
        "status": "ok",
        "start_date": out["date"].min(),
        "latest_date": out["date"].max(),
        "unit": "亿元",
        "notes": [
            "每日南向资金净流入采用东方财富沪深港通历史数据中的“当日成交净买额”字段。",
            "若最新交易日数值长时间为0或缺失，可能代表接口尚未更新，而非真实无交易净买入。",
        ],
    }
    METADATA_JSON.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"rows": len(out), **metadata}, ensure_ascii=False))


if __name__ == "__main__":
    main()
