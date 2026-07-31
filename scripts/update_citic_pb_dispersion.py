#!/usr/bin/env python3
"""Build weekly CITIC PB dispersion from Wind-cached industry inputs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from common import PROCESSED_DIR, RAW_DIR, write_metadata  # noqa: E402
from common.wind_cli import cached_call, parse_kline, year_chunks  # noqa: E402

INPUT_CSV = RAW_DIR / "citic_industry_crowding_weekly.csv"
OUT_CSV = PROCESSED_DIR / "citic_pb_dispersion.csv"
OUT_META = PROCESSED_DIR / "citic_pb_dispersion.metadata.json"
START_DATE = "20160101"
WINDOW_WEEKS = 520
MIN_WEEKS = 260


def week_ending_sunday(values: pd.Series) -> pd.Series:
    dates = pd.to_datetime(values, errors="coerce").dt.normalize()
    return dates + pd.to_timedelta((6 - dates.dt.weekday) % 7, unit="D")


def fetch_wind_all_a_weekly() -> pd.DataFrame:
    records: list[dict] = []
    for begin, end in year_chunks(START_DATE):
        payload = cached_call(
            f"citic_dispersion_wind_all_a_{begin}_{end}",
            "index_data",
            "get_index_kline",
            {"windcode": "881001.WI", "begin_date": begin, "end_date": end, "period": "10"},
        )
        records.extend(parse_kline(payload))
    frame = pd.DataFrame(records)
    if frame.empty:
        return frame
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce", utc=True).dt.tz_convert("Asia/Shanghai").dt.tz_localize(None).dt.normalize()
    frame["wind_all_a_close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.dropna(subset=["date", "wind_all_a_close"]).sort_values("date")
    frame["week"] = week_ending_sunday(frame["date"])
    return frame.groupby("week", as_index=False).tail(1)[["week", "wind_all_a_close"]].rename(columns={"week": "date"})


def percentile_last(values: pd.Series) -> float:
    return float(values.rank(pct=True).iloc[-1])


def main() -> None:
    if not INPUT_CSV.exists():
        raise FileNotFoundError(f"Wind CITIC weekly input not found: {INPUT_CSV}")
    pb = pd.read_csv(INPUT_CSV)
    pb["date"] = week_ending_sunday(pb["date"])
    pb["pb_lf"] = pd.to_numeric(pb["pb_lf"], errors="coerce")
    pb = pb.dropna(subset=["date", "wind_code", "pb_lf"]).drop_duplicates(["date", "wind_code"], keep="last")

    frames: list[pd.DataFrame] = []
    for _, part in pb.sort_values("date").groupby("wind_code"):
        tmp = part.copy()
        tmp["pb_percentile_10y"] = tmp["pb_lf"].rolling(WINDOW_WEEKS, min_periods=MIN_WEEKS).apply(percentile_last, raw=False)
        frames.append(tmp)
    pct = pd.concat(frames, ignore_index=True)
    dispersion = (
        pct.groupby("date")["pb_percentile_10y"]
        .agg(lambda values: values.dropna().std(ddof=1) if values.dropna().size >= 10 else pd.NA)
        .reset_index(name="pb_dispersion_raw")
    )
    dispersion["pb_dispersion_raw"] = pd.to_numeric(dispersion["pb_dispersion_raw"], errors="coerce")
    dispersion = dispersion.dropna(subset=["pb_dispersion_raw"]).sort_values("date")
    dispersion["pb_dispersion_ma5"] = dispersion["pb_dispersion_raw"].rolling(5, min_periods=3).mean()

    close = fetch_wind_all_a_weekly()
    out = dispersion.merge(close, on="date", how="left")
    if out.empty:
        raise RuntimeError("Wind CITIC PB dispersion has no available rows")
    latest_date = out["date"].max().strftime("%Y-%m-%d")
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    out.to_csv(OUT_CSV, index=False)
    write_metadata(
        OUT_META,
        source="wind:citic-weekly-pb+index_data.get_index_kline",
        status="ok",
        latest_date=latest_date,
        unit="index/pctile-std",
        notes=[
            "CITIC PB(LF) comes from the Wind weekly crowding cache for 30 level-1 industries.",
            "PB percentile uses a trailing 10-year weekly window (520 weeks, minimum 260).",
            "PB dispersion MA5 is the 5-week moving average of cross-industry PB percentile standard deviation.",
            "left axis uses Wind All A weekly close from Wind index K-lines, code 881001.WI.",
        ],
    )
    print(json.dumps({"latest_date": latest_date, "rows": len(out), "source": "Wind"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
