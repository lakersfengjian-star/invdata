#!/usr/bin/env python3
"""Update style index performance from Wind daily index K-lines."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from common import PROCESSED_DIR, write_metadata  # noqa: E402
from common.wind_cli import cached_call, parse_kline, year_chunks  # noqa: E402

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


def fetch_index(code: str, name: str) -> pd.DataFrame:
    records: list[dict] = []
    safe_code = code.replace(".", "_")
    for begin, end in year_chunks(START_DATE):
        payload = cached_call(
            f"style_kline_{safe_code}_{begin}_{end}",
            "index_data",
            "get_index_kline",
            {"windcode": code, "begin_date": begin, "end_date": end, "period": "10"},
        )
        records.extend(parse_kline(payload))
    frame = pd.DataFrame(records)
    if frame.empty:
        return frame
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce", utc=True).dt.tz_convert("Asia/Shanghai").dt.tz_localize(None).dt.normalize()
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.dropna().drop_duplicates("date", keep="last").sort_values("date")
    frame["pct_change"] = frame["close"].pct_change() * 100
    frame["wind_code"] = code
    frame["index_name"] = name
    return frame[["date", "wind_code", "index_name", "close", "pct_change"]]


def main() -> None:
    frames = [fetch_index(code, name) for code, name in STYLE_INDEXES.items()]
    df = pd.concat([frame for frame in frames if not frame.empty], ignore_index=True)
    if df.empty:
        raise RuntimeError("Wind returned no style index K-line rows")
    df = df.drop_duplicates(["date", "wind_code"], keep="last").sort_values(["date", "wind_code"])
    latest_date = df["date"].max().strftime("%Y-%m-%d")
    out = df.copy()
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    out.to_csv(OUT_CSV, index=False)
    write_metadata(
        OUT_META,
        source="wind:index_data.get_index_kline",
        status="ok",
        latest_date=latest_date,
        unit="pct/point",
        notes=[
            "style return heatmap uses Wind daily index K-line closes",
            "returns are calculated for 1D, 5D, 20D, 60D and YTD windows",
        ],
        extra={"rows": len(out)},
    )
    print(json.dumps({"latest_date": latest_date, "rows": len(out), "source": "Wind"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
