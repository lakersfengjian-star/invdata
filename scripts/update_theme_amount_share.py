#!/usr/bin/env python3
"""Update TMT and dividend-low-volatility turnover share series."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / ".work" / "vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

import pandas as pd
import requests


PROCESSED_DIR = ROOT / "data" / "processed"
OUT_CSV = PROCESSED_DIR / "theme_amount_share.csv"
METADATA_JSON = PROCESSED_DIR / "theme_amount_share.metadata.json"
START_DATE = "20240101"
END_DATE = "20260704"

INDEX_SOURCES = {
    "tmt": {"name": "中证TMT", "symbol": "000998"},
    "dividend_low_vol": {"name": "红利低波", "symbol": "H30269"},
}


def fetch_csindex_amount(symbol: str) -> pd.DataFrame:
    resp = requests.get(
        "https://www.csindex.com.cn/csindex-home/perf/index-perf",
        params={"indexCode": symbol, "startDate": START_DATE, "endDate": END_DATE},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json().get("data") or []
    if not data:
        return pd.DataFrame(columns=["date", "amount"])
    df = pd.DataFrame(data)
    date_col = "tradeDate" if "tradeDate" in df.columns else "date"
    amount_col = "tradingValue" if "tradingValue" in df.columns else "amount"
    out = df[[date_col, amount_col]].copy()
    out.columns = ["date", "amount"]
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["amount"] = pd.to_numeric(out["amount"], errors="coerce")
    return out.dropna(subset=["date", "amount"])


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    denominator_path = PROCESSED_DIR / "index_amount_share.csv"
    if not denominator_path.exists():
        raise RuntimeError("Missing index_amount_share.csv; run update_index_amount_share.py first.")
    denominator = pd.read_csv(denominator_path, parse_dates=["date"])[["date", "wind_all_a_proxy_amount"]]
    frames: dict[str, pd.DataFrame] = {}
    notes: list[str] = []
    for key, config in INDEX_SOURCES.items():
        try:
            data = fetch_csindex_amount(config["symbol"])
            if data.empty:
                notes.append(f"{config['name']}：中证官网暂未返回成交金额。")
            else:
                frames[key] = data.rename(columns={"amount": f"{key}_amount"})
        except Exception as exc:
            notes.append(f"{config['name']}：获取失败：{type(exc).__name__}: {exc}")
    summary = denominator.copy()
    for key in INDEX_SOURCES:
        if key in frames:
            summary = summary.merge(frames[key], on="date", how="left")
        else:
            summary[f"{key}_amount"] = pd.NA
        summary[f"{key}_share_pct"] = (
            pd.to_numeric(summary[f"{key}_amount"], errors="coerce")
            / pd.to_numeric(summary["wind_all_a_proxy_amount"], errors="coerce")
            * 100
        )
    summary = summary.sort_values("date")
    summary["date"] = summary["date"].dt.strftime("%Y-%m-%d")
    summary.to_csv(OUT_CSV, index=False)
    metadata = {
        "source": "CSI official index performance API",
        "start_date": summary["date"].min(),
        "latest_date": summary.dropna(subset=["tmt_share_pct", "dividend_low_vol_share_pct"], how="all")["date"].max(),
        "denominator": "中证全指成交金额，作为 Wind 全A 成交额公开代理口径",
        "notes": notes,
    }
    METADATA_JSON.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"rows": len(summary), **metadata}, ensure_ascii=False))


if __name__ == "__main__":
    main()
