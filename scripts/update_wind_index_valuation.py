#!/usr/bin/env python3
"""Fetch Wind index PE_TTM series for local valuation charts.

Output:
  data/raw/index_pe_ttm_wind.csv

This script intentionally stores Wind data locally so later builds can reuse the
CSV without calling Wind again.
"""

from __future__ import annotations

import json
import subprocess
import sys
from calendar import monthrange
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from common import PROCESSED_DIR, RAW_DIR, VALUATION_START_DATE, ensure_dirs, write_metadata  # noqa: E402

WIND_SKILL_DIR = Path("/Users/jianfeng/.agents/skills/wind-mcp-skill")
CLI = WIND_SKILL_DIR / "scripts" / "cli.mjs"
OUT_CSV = RAW_DIR / "index_pe_ttm_wind.csv"
OUT_META = RAW_DIR / "index_pe_ttm_wind.metadata.json"

WIND_VALUATION_INDEXES = [
    {"windcode": "000300.SH", "index_name": "沪深300指数"},
    {"windcode": "000001.SH", "index_name": "上证指数"},
    {"windcode": "881001.WI", "index_name": "万得全A"},
    {"windcode": "881003.WI", "index_name": "万得全A（除金融、石油石化）"},
]


def parse_wind_payload(stdout: str) -> list[dict]:
    outer = json.loads(stdout)
    text = outer["content"][0]["text"]
    payload = json.loads(text)
    rows: list[dict] = []
    for block in payload.get("data", {}).get("data", []):
        columns = [col["name"] for col in block.get("columns", [])]
        for values in block.get("rows", []):
            row = dict(zip(columns, values))
            rows.append(row)
    return rows


def extract_rows(rows: list[dict], index_name: str) -> pd.DataFrame:
    records = []
    for row in rows:
        date_value = None
        pe_value = None
        for key, value in row.items():
            if "时间" in key or key == "日期":
                date_value = value
            if "市盈率" in key and "时间" not in key:
                pe_value = value
        if date_value is None or pe_value is None:
            continue
        records.append({"date": date_value, "index_name": index_name, "pe_ttm": pe_value})
    if not records:
        return pd.DataFrame(columns=["date", "index_name", "pe_ttm"])
    out = pd.DataFrame(records)
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.normalize()
    out["pe_ttm"] = pd.to_numeric(out["pe_ttm"], errors="coerce")
    return out.dropna(subset=["date", "pe_ttm"])


def fetch_range(windcode: str, index_name: str, begin: str, end: str) -> pd.DataFrame:
    question = f"{windcode}指数{begin}至{end}每日市盈率(TTM)"
    params = json.dumps({"question": question, "lang": "中文"}, ensure_ascii=False)
    proc = subprocess.run(
        ["node", str(CLI), "call", "index_data", "get_index_fundamentals", params],
        cwd=WIND_SKILL_DIR,
        text=True,
        capture_output=True,
        check=True,
    )
    return extract_rows(parse_wind_payload(proc.stdout), index_name)


def iter_month_ranges(start_date: pd.Timestamp, end_year: int) -> list[tuple[int, int, str, str]]:
    today = pd.Timestamp.today().normalize()
    ranges = []
    start_year = start_date.year
    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            begin = pd.Timestamp(year=year, month=month, day=1)
            if begin < pd.Timestamp(year=start_date.year, month=start_date.month, day=1):
                continue
            if begin > today:
                continue
            end = min(pd.Timestamp(year=year, month=month, day=monthrange(year, month)[1]), today)
            ranges.append((year, month, begin.strftime("%Y%m%d"), end.strftime("%Y%m%d")))
    return ranges


def existing_latest_dates() -> dict[str, pd.Timestamp]:
    frames = []
    if OUT_CSV.exists():
        frames.append(pd.read_csv(OUT_CSV, parse_dates=["date"]))
    processed_path = PROCESSED_DIR / "index_pe_ttm_valuation.csv"
    if processed_path.exists():
        frames.append(pd.read_csv(processed_path, parse_dates=["date"]))
    if not frames:
        return {}
    combined = pd.concat(frames, ignore_index=True)
    combined["date"] = pd.to_datetime(combined["date"], errors="coerce")
    latest = combined.dropna(subset=["date"]).groupby("index_name")["date"].max()
    return latest.to_dict()


def main() -> None:
    ensure_dirs()
    start_year = pd.Timestamp(VALUATION_START_DATE).year
    end_year = datetime.now().year
    frames = []
    notes = []
    latest_existing = existing_latest_dates()
    if OUT_CSV.exists():
        old = pd.read_csv(OUT_CSV, parse_dates=["date"])
        frames.append(old)
    for item in WIND_VALUATION_INDEXES:
        start_date = latest_existing.get(item["index_name"], pd.Timestamp(VALUATION_START_DATE))
        for year, month, begin, end in iter_month_ranges(pd.Timestamp(start_date), end_year):
            try:
                df = fetch_range(item["windcode"], item["index_name"], begin, end)
                if not df.empty:
                    frames.append(df)
                    print(f"{item['index_name']} {year}-{month:02d}: {len(df)} rows", flush=True)
            except Exception as exc:  # noqa: BLE001
                notes.append(f"{item['index_name']} {year}-{month:02d} failed: {type(exc).__name__}: {str(exc)[:180]}")
                print(notes[-1], flush=True)
    if not frames:
        raise RuntimeError("No Wind valuation rows fetched and no local CSV exists")
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.normalize()
    out["pe_ttm"] = pd.to_numeric(out["pe_ttm"], errors="coerce")
    out = out.dropna(subset=["date", "index_name", "pe_ttm"])
    out = out[out["date"].ge(pd.Timestamp(VALUATION_START_DATE))]
    out = out.drop_duplicates(["date", "index_name"], keep="last").sort_values(["index_name", "date"])
    out_to_write = out.copy()
    out_to_write["date"] = out_to_write["date"].dt.strftime("%Y-%m-%d")
    out_to_write.to_csv(OUT_CSV, index=False)
    latest = out.groupby("index_name")["date"].max().dt.strftime("%Y-%m-%d").to_dict()
    write_metadata(
        OUT_META,
        source="Wind AIFin Market CLI index_data.get_index_fundamentals",
        status="ok" if not notes else "partial",
        latest_date=max(latest.values()) if latest else "",
        notes=notes,
        extra={"latest_by_index": latest},
    )
    print(json.dumps({"rows": len(out), "latest_by_index": latest, "notes": notes}, ensure_ascii=False))


if __name__ == "__main__":
    main()
