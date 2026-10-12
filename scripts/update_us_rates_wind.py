#!/usr/bin/env python3
"""Update US policy, funding and Treasury yields through Wind MCP."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from common.wind_cli import call

ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = ROOT / "data" / "processed"
OUTPUT_PATH = PROCESSED_DIR / "us_rates_wind.csv"
METADATA_PATH = PROCESSED_DIR / "us_rates_wind.metadata.json"

INDICATORS = {
    "G0001699": "EFFR",
    "M0000162": "Fed Funds Target",
    "M0341926": "SOFR",
    "K8012859": "3M Term SOFR",
    "M1001787": "2Y Treasury",
    "M1001791": "10Y Treasury",
    "G0000893": "30Y Treasury",
    "G0005428": "10Y TIPS Real Yield",
}


def fetch_all(begin: str, end: str) -> tuple[list[dict], dict[str, dict]]:
    payload = call(
        "economic_data",
        "natural_language_get_edb_data",
        {
            "executionMode": "fetch",
            "question": ",".join(INDICATORS),
            "beginDate": begin.replace("-", ""),
            "endDate": end.replace("-", ""),
        },
        timeout=240,
    )
    metrics = payload.get("data", {}).get("data", [])
    if not metrics:
        raise RuntimeError("Wind returned no US-rate metrics")
    rows: list[dict] = []
    source_meta: dict[str, dict] = {}
    for metric in metrics:
        meta = metric.get("meta", {})
        code = meta.get("code")
        if code not in INDICATORS:
            continue
        source_meta[code] = meta
        dates, values = metric.get("date", []), metric.get("value", [])
        if not dates or len(dates) != len(values):
            continue
        rows.extend({
            "date": pd.to_datetime(raw_date, format="%Y%m%d").strftime("%Y-%m-%d"),
            "code": code, "name": INDICATORS[code], "value": value,
            "unit": meta.get("unit", "%"), "source": "Wind MCP",
        } for raw_date, value in zip(dates, values) if value is not None)
    return rows, source_meta


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    begin_date = date(date.today().year, 1, 1)
    if OUTPUT_PATH.exists():
        cached = pd.read_csv(OUTPUT_PATH)
        cached_dates = pd.to_datetime(cached.get("date"), errors="coerce").dropna()
        if not cached_dates.empty:
            begin_date = max(begin_date, cached_dates.max().date() - timedelta(days=10))
    begin = begin_date.strftime("%Y-%m-%d")
    end = date.today().strftime("%Y-%m-%d")
    rows: list[dict] = []
    source_meta: dict[str, dict] = {}
    errors: list[str] = []
    try:
        rows, source_meta = fetch_all(begin, end)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"{type(exc).__name__}: {str(exc)[:180]}")

    if not rows:
        raise RuntimeError("Wind returned no US rate data: " + "; ".join(errors))
    fresh = pd.DataFrame(rows)
    pivot = fresh[fresh["code"].isin(["M1001787", "M1001791"])].pivot_table(
        index="date", columns="code", values="value", aggfunc="last"
    ).dropna()
    spread = pd.DataFrame(
        {
            "date": pivot.index,
            "code": "CALC_2Y10Y",
            "name": "2Y-10Y Spread",
            "value": pivot["M1001791"] - pivot["M1001787"],
            "unit": "%",
            "source": "Wind MCP计算",
        }
    )
    fresh = pd.concat([fresh, spread], ignore_index=True)
    existing = pd.read_csv(OUTPUT_PATH) if OUTPUT_PATH.exists() else pd.DataFrame()
    data = pd.concat([existing, fresh], ignore_index=True)
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data["value"] = pd.to_numeric(data["value"], errors="coerce")
    data = data.dropna(subset=["date", "code", "value"])
    data = data.drop_duplicates(["date", "code"], keep="last").sort_values(["code", "date"])
    data["date"] = data["date"].dt.strftime("%Y-%m-%d")
    data.to_csv(OUTPUT_PATH, index=False, encoding="utf-8")

    latest_by_code = data.groupby("code")["date"].max().to_dict()
    metadata = {
        "updated_at": pd.Timestamp.now(tz="Asia/Shanghai").strftime("%Y-%m-%d %H:%M:%S %Z"),
        "latest_date": max(latest_by_code.values()),
        "latest_by_code": latest_by_code,
        "indicators": source_meta,
        "errors": errors,
        "notes": [
            "2Y-10Y Spread按同日10Y Treasury减2Y Treasury计算。",
            "3M Term SOFR用于观察SOFR远期政策定价；不等同于某一指定到期日的SOFR期货合约。",
            "Fed Funds Target在Wind中2026年暂无观测值，页面不以EFFR替代。",
        ],
    }
    METADATA_PATH.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"rows": len(data), "latest_by_code": latest_by_code, "errors": errors}, ensure_ascii=False))


if __name__ == "__main__":
    main()
