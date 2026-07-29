#!/usr/bin/env python3
"""Update fiscal revenue and expenditure datasets from Wind EDB."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = ROOT / "data" / "processed"
WIND_SKILL_DIR = Path("/Users/jianfeng/.agents/skills/wind-mcp-skill")
CLI = WIND_SKILL_DIR / "scripts" / "cli.mjs"

BEGIN_DATE = "20240501"
OUT_CSV = PROCESSED_DIR / "macro_fiscal.csv"
OUT_META = PROCESSED_DIR / "macro_fiscal.metadata.json"

EDB_CODES = {
    "budget_expenditure_ytd_yoy": "M0046167",
    "budget_revenue_ytd_yoy": "M0046169",
    "central_revenue_ytd_yoy": "M0089129",
    "local_revenue_ytd_yoy": "M0089130",
}

EDB_NAMES = {
    "budget_expenditure_ytd_yoy": "中国:一般公共预算支出:累计同比",
    "budget_revenue_ytd_yoy": "中国:一般公共预算收入:累计同比",
    "central_revenue_ytd_yoy": "中国:中央一般公共预算收入:累计同比",
    "local_revenue_ytd_yoy": "中国:地方一般公共预算本级收入:累计同比",
}


def call_wind_edb() -> list[dict]:
    params = {
        "executionMode": "fetch",
        "question": ",".join(EDB_CODES.values()),
        "beginDate": BEGIN_DATE,
        "endDate": pd.Timestamp.today().strftime("%Y%m%d"),
    }
    proc = subprocess.run(
        ["node", str(CLI), "call", "economic_data", "natural_language_get_edb_data", json.dumps(params, ensure_ascii=False)],
        cwd=WIND_SKILL_DIR,
        text=True,
        capture_output=True,
        timeout=120,
        check=True,
    )
    outer = json.loads(proc.stdout)
    payload = json.loads(outer["content"][0]["text"])
    data = payload.get("data", {})
    if data.get("code") != 0:
        raise RuntimeError(f"Wind EDB error: {data}")
    return data.get("data", [])


def block_to_series(block: dict) -> pd.Series:
    code = block.get("meta", {}).get("code")
    key = next((name for name, edb_code in EDB_CODES.items() if edb_code == code), None)
    if not key:
        return pd.Series(dtype="float64")
    dates = pd.to_datetime(block.get("date", []), format="%Y%m%d", errors="coerce")
    values = pd.to_numeric(pd.Series(block.get("value", [])), errors="coerce")
    return pd.Series(values.to_numpy(), index=dates, name=key).dropna().sort_index()


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    blocks = call_wind_edb()
    series_map = {series.name: series for series in (block_to_series(block) for block in blocks) if series.name}
    data = pd.DataFrame(series_map).sort_index()
    data.index.name = "date"
    out = data.reset_index()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    out.to_csv(OUT_CSV, index=False)

    latest = str(out["date"].dropna().max()) if not out.empty else ""
    meta = {
        "source": "Wind EDB economic_data.natural_language_get_edb_data",
        "status": "ok",
        "latest_date": latest,
        "unit": "%",
        "edb_codes": EDB_CODES,
        "edb_names": EDB_NAMES,
        "notes": ["财政收支指标均为累计同比。"],
        "built_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    OUT_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "latest_date": latest, "rows": len(out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
