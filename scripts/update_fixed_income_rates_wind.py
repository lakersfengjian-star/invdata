#!/usr/bin/env python3
"""Update the fixed-income yield snapshot with Wind MCP daily indicators."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from common.wind_cli import call

ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = ROOT / "data" / "processed"
OUTPUT_PATH = PROCESSED_DIR / "fixed_income_rates_wind.csv"
METADATA_PATH = PROCESSED_DIR / "fixed_income_rates_wind.metadata.json"

INDICATORS = {
    "M1001654": "10年国债",
    "M1001657": "30年国债",
    "M1002843": "5年AAA信用债",
    "M1015589": "5年AA银行二级资本债",
}


def fetch_indicator(code: str, begin: str, end: str) -> tuple[list[dict], dict]:
    payload = call(
        "economic_data",
        "query_economic_indicator_data",
        {"question": code, "beginDate": begin, "endDate": end},
        timeout=240,
    )
    metrics = payload.get("metrics", [])
    if not metrics:
        raise RuntimeError(f"Wind returned no metric for {code}")
    metric = next((item for item in metrics if item.get("meta", {}).get("code") == code), metrics[0])
    meta = metric.get("meta", {})
    dates = metric.get("date", [])
    values = metric.get("value", [])
    if len(dates) != len(values):
        raise RuntimeError(f"Wind date/value length mismatch for {code}")
    rows = [
        {
            "date": pd.to_datetime(raw_date, format="%Y%m%d").strftime("%Y-%m-%d"),
            "code": code,
            "name": INDICATORS[code],
            "value": value,
            "unit": meta.get("unit", "%"),
            "source": "Wind MCP",
        }
        for raw_date, value in zip(dates, values)
        if value is not None
    ]
    return rows, meta


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    current_year = date.today().year
    begin = f"{current_year}-01-01"
    end = date.today().strftime("%Y-%m-%d")
    rows: list[dict] = []
    source_meta: dict[str, dict] = {}
    errors: list[str] = []

    for code in INDICATORS:
        try:
            part, meta = fetch_indicator(code, begin, end)
            rows.extend(part)
            source_meta[code] = meta
        except Exception as exc:  # noqa: BLE001 - preserve other successful indicators
            errors.append(f"{code}: {type(exc).__name__}: {str(exc)[:180]}")

    if not rows:
        raise RuntimeError("Wind returned no fixed-income yield data: " + "; ".join(errors))

    fresh = pd.DataFrame(rows)
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
        "latest_date": min(latest_by_code.values()) if len(latest_by_code) == len(INDICATORS) else "",
        "latest_by_code": latest_by_code,
        "indicators": source_meta,
        "errors": errors,
        "notes": [
            "数据通过 Wind MCP economic_data 接口按指标代码逐项获取。",
            "银行二级资本债采用5年AA口径；5年AAA-指标M1010708受当前Wind账号权限限制，未与其他来源混用。",
        ],
    }
    METADATA_PATH.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"rows": len(data), "latest_by_code": latest_by_code, "errors": errors}, ensure_ascii=False))


if __name__ == "__main__":
    main()
