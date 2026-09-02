#!/usr/bin/env python3
"""Update fiscal revenue and expenditure datasets from Wind EDB."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from common.ifind_client import find_column, get_edb_table  # noqa: E402
PROCESSED_DIR = ROOT / "data" / "processed"
WIND_SKILL_DIR = Path(
    os.environ.get("WIND_SKILL_DIR", Path.home() / ".agents" / "skills" / "wind-mcp-skill")
).expanduser()
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


def call_ifind_edb() -> pd.DataFrame:
    requests = [
        ("中国一般公共预算支出累计同比（202405-至今）", ("一般公共预算支出", "累计同比"), "budget_expenditure_ytd_yoy"),
        ("中国一般公共预算收入累计同比（202405-至今）", ("一般公共预算收入", "累计同比"), "budget_revenue_ytd_yoy"),
        ("中国中央一般公共预算收入累计同比（202405-至今）", ("中央", "一般公共预算收入", "累计同比"), "central_revenue_ytd_yoy"),
        ("中国地方一般公共预算本级收入累计同比（202405-至今）", ("地方", "一般公共预算", "收入", "累计同比"), "local_revenue_ytd_yoy"),
    ]
    parts = []
    for query, needles, target in requests:
        frame, _ = get_edb_table(query)
        date_col = find_column(frame.columns, "日期")
        value_col = find_column(frame.columns, *needles)
        out = frame.rename(columns={value_col: target})
        out["date"] = pd.to_datetime(out[date_col], errors="coerce")
        out[target] = pd.to_numeric(out[target], errors="coerce")
        parts.append(out.set_index("date")[[target]].dropna(how="all"))
    return pd.concat(parts, axis=1).sort_index()


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    source = "Wind EDB economic_data.natural_language_get_edb_data"
    notes = []
    try:
        blocks = call_wind_edb()
        series_map = {series.name: series for series in (block_to_series(block) for block in blocks) if series.name}
        data = pd.DataFrame(series_map).sort_index()
        if data.empty:
            raise RuntimeError("Wind returned no fiscal rows")
    except Exception as wind_error:  # noqa: BLE001
        data = call_ifind_edb()
        source = "iFinD MCP edb.get_edb_data (Wind fallback)"
        notes.append(f"Wind failed; iFinD fallback used: {type(wind_error).__name__}")
    data.index.name = "date"
    out = data.reset_index()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    out.to_csv(OUT_CSV, index=False)

    latest = str(out["date"].dropna().max()) if not out.empty else ""
    meta = {
        "source": source,
        "status": "ok",
        "latest_date": latest,
        "unit": "%",
        "edb_codes": EDB_CODES,
        "edb_names": EDB_NAMES,
        "notes": notes + ["财政收支指标均为累计同比。"],
        "built_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    OUT_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "latest_date": latest, "rows": len(out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
