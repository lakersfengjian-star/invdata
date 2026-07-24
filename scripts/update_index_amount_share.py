#!/usr/bin/env python3
"""Update index turnover share data from CSI official index daily bars."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / ".work" / "vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

import pandas as pd
import requests


PROCESSED_DIR = ROOT / "data" / "processed"
START_DATE = "20240101"
END_DATE = date.today().strftime("%Y%m%d")

INDEX_SOURCES = {
    "hs300": {"name": "沪深300", "symbol": "000300"},
    "csi500": {"name": "中证500", "symbol": "000905"},
    "csi1000": {"name": "中证1000", "symbol": "000852"},
    "csi2000": {"name": "中证2000", "symbol": "932000"},
    "wind_all_a_proxy": {"name": "中证全指（Wind全A成交额公开代理）", "symbol": "000985"},
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
    df.columns = [
        "date",
        "index_code",
        "cn_full_name",
        "cn_short_name",
        "en_full_name",
        "en_short_name",
        "open",
        "high",
        "low",
        "close",
        "change",
        "change_pct",
        "volume",
        "amount",
        "constituents",
        "pe_ttm",
    ]
    out = df[["date", "amount"]].copy()
    out["date"] = pd.to_datetime(out["date"])
    out["amount"] = pd.to_numeric(out["amount"], errors="coerce")
    return out.dropna(subset=["date", "amount"])


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    frames: dict[str, pd.DataFrame] = {}
    notes: list[str] = []
    for key, config in INDEX_SOURCES.items():
        try:
            df = fetch_csindex_amount(config["symbol"])
            if df.empty:
                notes.append(f"{config['name']}：中证指数官网暂未返回成交金额。")
            else:
                frames[key] = df.rename(columns={"amount": f"{key}_amount"})
        except Exception as exc:
            notes.append(f"{config['name']}：中证指数官网成交金额获取失败：{type(exc).__name__}。")

    if "wind_all_a_proxy" not in frames:
        raise RuntimeError("No denominator data. Need Wind All A or CSI All Share amount series.")

    summary = frames["wind_all_a_proxy"].copy()
    for key in ["hs300", "csi500", "csi1000", "csi2000"]:
        if key in frames:
            summary = summary.merge(frames[key], on="date", how="left")
        else:
            summary[f"{key}_amount"] = pd.NA

    denominator = summary["wind_all_a_proxy_amount"]
    for key in ["hs300", "csi500", "csi1000", "csi2000"]:
        summary[f"{key}_share_pct"] = pd.to_numeric(summary[f"{key}_amount"], errors="coerce") / denominator * 100

    summary = summary.sort_values("date")
    summary["date"] = summary["date"].dt.strftime("%Y-%m-%d")
    summary.to_csv(PROCESSED_DIR / "index_amount_share.csv", index=False)

    metadata = {
        "source": "CSI official index performance API",
        "start_date": summary["date"].min(),
        "latest_date": summary["date"].max(),
        "denominator": "中证全指成交金额，作为 Wind 全A 成交额公开代理口径",
        "notes": notes,
    }
    (PROCESSED_DIR / "index_amount_share.metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"rows": len(summary), **metadata}, ensure_ascii=False))


if __name__ == "__main__":
    main()
