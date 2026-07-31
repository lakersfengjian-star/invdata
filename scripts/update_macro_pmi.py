#!/usr/bin/env python3
"""Update China PMI headline, component and industry series from Wind EDB."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from common import PROCESSED_DIR, write_metadata  # noqa: E402
from common.wind_cli import cached_call  # noqa: E402

OUT_CSV = PROCESSED_DIR / "macro_pmi.csv"
OUT_META = PROCESSED_DIR / "macro_pmi.metadata.json"
START_DATE = "20150101"

INDICATORS = {
    "M0017126": ("制造业PMI", "headline"),
    "M5207838": ("服务业PMI", "headline"),
    "M5207831": ("建筑业PMI", "headline"),
    "M0017127": ("生产", "component"),
    "M0017128": ("新订单", "component"),
    "M0017129": ("新出口订单", "component"),
    "M0017130": ("在手订单", "component"),
    "M0017131": ("产成品库存", "component"),
    "M0017132": ("采购量", "component"),
    "M0017133": ("进口", "component"),
    "M0017134": ("主要原材料购进价格", "component"),
    "M0017135": ("原材料库存", "component"),
    "M0017136": ("从业人员", "component"),
    "M0017137": ("供应商配送时间", "component"),
    "M6642296": ("消费品制造业", "industry"),
    "M6642294": ("高技术制造业", "industry"),
    "M6642297": ("基础原材料行业", "industry"),
    "M6642295": ("装备制造业", "industry"),
}


def main() -> None:
    end_date = date.today().strftime("%Y%m%d")
    codes = ",".join(INDICATORS)
    payload = cached_call(
        f"macro_pmi_{START_DATE}_{end_date}",
        "economic_data",
        "natural_language_get_edb_data",
        {
            "executionMode": "fetch",
            "question": codes,
            "beginDate": START_DATE,
            "endDate": end_date,
        },
    )
    series = payload.get("data", {}).get("data", [])
    records: list[dict] = []
    for item in series:
        meta = item.get("meta", {})
        code = meta.get("code")
        if code not in INDICATORS:
            continue
        label, group = INDICATORS[code]
        for raw_date, value in zip(item.get("date", []), item.get("value", [])):
            records.append(
                {
                    "date": pd.to_datetime(raw_date, format="%Y%m%d", errors="coerce"),
                    "indicator_key": code,
                    "indicator": label,
                    "group": group,
                    "value": pd.to_numeric(value, errors="coerce"),
                }
            )
    frame = pd.DataFrame(records).dropna(subset=["date", "value"])
    if frame.empty:
        raise RuntimeError("Wind returned no PMI series")

    enriched: list[pd.DataFrame] = []
    for _, sub in frame.groupby("indicator_key", sort=False):
        sub = sub.sort_values("date").drop_duplicates("date", keep="last").set_index("date")
        monthly = sub.reindex(pd.date_range(sub.index.min(), sub.index.max(), freq="ME"))
        monthly.index.name = "date"
        for col in ["indicator_key", "indicator", "group"]:
            monthly[col] = monthly[col].ffill().bfill()
        monthly["mom_diff"] = monthly["value"].diff(1)
        monthly["yoy_diff"] = monthly["value"].diff(12)
        enriched.append(monthly.reset_index())
    out = pd.concat(enriched, ignore_index=True).dropna(subset=["value"])
    out = out.sort_values(["date", "group", "indicator_key"])
    latest_date = out["date"].max().strftime("%Y-%m-%d")
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    out.to_csv(OUT_CSV, index=False)
    write_metadata(
        OUT_META,
        source="wind:economic_data.natural_language_get_edb_data",
        status="ok",
        latest_date=latest_date,
        unit="index/percentage-point",
        notes=[
            "PMI is a diffusion index; mom_diff and yoy_diff are index-point differences, not growth rates",
            "Headline series: manufacturing, services and construction",
            "Manufacturing components and four industry-group PMI series are included",
        ],
        extra={"indicator_codes": INDICATORS, "rows": len(out)},
    )
    print(json.dumps({"latest_date": latest_date, "rows": len(out), "indicators": out["indicator_key"].nunique()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
