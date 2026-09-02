#!/usr/bin/env python3
"""Update inventory cycle and M1-M2 macro datasets from Wind EDB."""

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

BEGIN_DATE = "19970101"
OUT_INVENTORY = PROCESSED_DIR / "macro_inventory_cycle.csv"
OUT_MONEY = PROCESSED_DIR / "macro_m1_m2.csv"
OUT_META = PROCESSED_DIR / "macro_credit_inventory.metadata.json"

EDB_CODES = {
    "inventory_yoy": "M0000561",
    "ppi_yoy": "M0001227",
    "m1_yoy": "M0001383",
    "m2_yoy": "M0001385",
}

EDB_NAMES = {
    "inventory_yoy": "中国:产成品存货:规模以上工业企业:同比",
    "ppi_yoy": "中国:PPI:当月同比",
    "m1_yoy": "中国:M1:同比",
    "m2_yoy": "中国:M2:同比",
}


def end_date() -> str:
    return pd.Timestamp.today().strftime("%Y%m%d")


def call_wind_edb() -> list[dict]:
    params = {
        "executionMode": "fetch",
        "question": ",".join(EDB_CODES.values()),
        "beginDate": BEGIN_DATE,
        "endDate": end_date(),
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
    text = outer["content"][0]["text"]
    payload = json.loads(text)
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
    series = pd.Series(values.to_numpy(), index=dates, name=key)
    return series.dropna().sort_index()


def call_ifind_edb() -> pd.DataFrame:
    requests = [
        ("中国规模以上工业企业产成品存货同比（199701-至今）", ("产成品存货", "同比"), "inventory_yoy"),
        ("中国PPI当月同比（199701-至今）", ("PPI", "同比"), "ppi_yoy"),
        ("中国M1同比（199701-至今）", ("M1", "同比"), "m1_yoy"),
        ("中国M2同比（199701-至今）", ("M2", "同比"), "m2_yoy"),
    ]

    def normalize(frame: pd.DataFrame, needles: tuple[str, ...], target: str) -> pd.DataFrame:
        date_col = find_column(frame.columns, "日期")
        value_col = find_column(frame.columns, *needles)
        out = frame.rename(columns={value_col: target})
        out["date"] = pd.to_datetime(out[date_col], errors="coerce")
        out[target] = pd.to_numeric(out[target], errors="coerce")
        return out.set_index("date")[[target]].dropna(how="all")

    parts = []
    for query, needles, target in requests:
        frame, _ = get_edb_table(query)
        parts.append(normalize(frame, needles, target))
    return pd.concat(parts, axis=1).sort_index()


def write_csv(df: pd.DataFrame, path: Path) -> str:
    out = df.copy().sort_values("date")
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    out.to_csv(path, index=False)
    return str(out["date"].dropna().max()) if not out.empty else ""


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    source = "Wind EDB economic_data.natural_language_get_edb_data"
    notes = []
    try:
        blocks = call_wind_edb()
        series_map = {series.name: series for series in (block_to_series(block) for block in blocks) if series.name}
        data = pd.DataFrame(series_map).sort_index()
        if data.empty:
            raise RuntimeError("Wind returned no macro rows")
    except Exception as wind_error:  # noqa: BLE001
        data = call_ifind_edb()
        source = "iFinD MCP edb.get_edb_data (Wind fallback)"
        notes.append(f"Wind failed; iFinD fallback used: {type(wind_error).__name__}")
    data.index.name = "date"

    inventory = data[["inventory_yoy", "ppi_yoy"]].dropna(subset=["inventory_yoy", "ppi_yoy"]).copy()
    inventory["real_inventory_yoy"] = inventory["inventory_yoy"] - inventory["ppi_yoy"]
    inventory = inventory.reset_index()

    money = data[["m1_yoy", "m2_yoy"]].dropna(subset=["m1_yoy", "m2_yoy"]).copy()
    money["m1_minus_m2"] = money["m1_yoy"] - money["m2_yoy"]
    money = money.reset_index()

    latest_inventory = write_csv(inventory, OUT_INVENTORY)
    latest_money = write_csv(money, OUT_MONEY)
    meta = {
        "source": source,
        "status": "ok",
        "latest_date": max(latest_inventory, latest_money),
        "latest_by_dataset": {"macro_inventory": latest_inventory, "macro_m1_m2": latest_money},
        "unit": "%",
        "edb_codes": EDB_CODES,
        "edb_names": EDB_NAMES,
        "notes": notes + [
            "实际库存同比 = 规模以上工业企业产成品存货同比 - PPI当月同比。",
            "M1-M2 = M1同比 - M2同比。",
        ],
        "built_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    OUT_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "latest": meta["latest_by_dataset"], "rows": {"inventory": len(inventory), "money": len(money)}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
