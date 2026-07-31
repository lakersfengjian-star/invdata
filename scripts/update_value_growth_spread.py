#!/usr/bin/env python3
"""Update value-growth spread from Wind index fundamentals."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from common import PROCESSED_DIR, write_metadata  # noqa: E402
from common.wind_cli import cached_call, cn_date, date_chunks, parse_nl_series  # noqa: E402

OUT_CSV = PROCESSED_DIR / "value_growth_spread.csv"
OUT_META = PROCESSED_DIR / "value_growth_spread.metadata.json"
START_DATE = "20210101"
DIVIDEND_CODE = "000922.CSI"
GROWTH_CODE = "931643.CSI"


def fetch_series(code: str, field_label: str, cache_label: str) -> pd.DataFrame:
    records: list[dict] = []
    for begin, end in date_chunks(START_DATE, days=120):
        payload = cached_call(
            f"value_growth_{cache_label}_{begin}_{end}",
            "index_data",
            "get_index_fundamentals",
            {"question": f"{code}{cn_date(begin)}至{cn_date(end)}每日{field_label}", "lang": "CNS"},
        )
        records.extend(parse_nl_series(payload, field_label.split("(")[0]))
    frame = pd.DataFrame(records)
    if frame.empty:
        return frame
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.tz_localize(None)
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    return frame.dropna().drop_duplicates("date", keep="last").sort_values("date")


def main() -> None:
    dividend = fetch_series(DIVIDEND_CODE, "股息率", "dividend").rename(columns={"value": "dividend_yield"})
    growth = fetch_series(GROWTH_CODE, "市盈率(TTM)", "pe_ttm").rename(columns={"value": "growth_pe_ttm"})
    df = dividend.merge(growth, on="date", how="inner").sort_values("date")
    if df.empty:
        raise RuntimeError("Wind returned no value-growth spread rows")
    df["growth_earnings_yield"] = 100 / df["growth_pe_ttm"]
    df["spread"] = df["dividend_yield"] - df["growth_earnings_yield"]
    df = df.dropna(subset=["spread"]).drop_duplicates("date")
    latest_date = df["date"].max().strftime("%Y-%m-%d")
    out = df.copy()
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    out.to_csv(OUT_CSV, index=False)
    write_metadata(
        OUT_META,
        source="wind:index_data.get_index_fundamentals",
        status="ok",
        latest_date=latest_date,
        unit="pct",
        notes=[
            "spread = 中证红利指数股息率 - 双创50盈利收益率(100/PE_TTM)",
            "Wind codes: 000922.CSI dividend yield and 931643.CSI PE(TTM)",
            f"updated via cached 120-day chunks through {date.today():%Y-%m-%d}",
        ],
    )
    print(json.dumps({"latest_date": latest_date, "rows": len(out), "source": "Wind"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
