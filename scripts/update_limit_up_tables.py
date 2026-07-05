#!/usr/bin/env python3
"""Update latest A-share limit-up leader tables from Eastmoney/AkShare."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / ".work" / "vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

import akshare as ak
import pandas as pd


PROCESSED_DIR = ROOT / "data" / "processed"
CACHE_DIR = ROOT / ".work" / "cache" / "company_profiles"
LONGEST_CSV = PROCESSED_DIR / "limit_up_longest.csv"
AMOUNT_CSV = PROCESSED_DIR / "limit_up_amount_top.csv"
METADATA_JSON = PROCESSED_DIR / "limit_up_tables.metadata.json"


def latest_market_date() -> str:
    candidates = [
        PROCESSED_DIR / "index_amount_share.metadata.json",
        PROCESSED_DIR / "metadata.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        value = data.get("latest_date") or data.get("latest_common_date")
        if value:
            return str(value).replace("-", "")
    return pd.Timestamp.today().strftime("%Y%m%d")


def short_text(value: object, max_len: int = 54) -> str:
    text = "" if pd.isna(value) else str(value).strip()
    text = " ".join(text.split())
    if len(text) > max_len:
        return text[: max_len - 1] + "..."
    return text


def fetch_business(code: str) -> str:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{code}.json"
    if cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        return cached.get("main_business", "")
    try:
        profile = ak.stock_profile_cninfo(symbol=code)
        business = ""
        if not profile.empty and "主营业务" in profile.columns:
            business = short_text(profile.iloc[0]["主营业务"], 70)
        cache_path.write_text(json.dumps({"main_business": business}, ensure_ascii=False), encoding="utf-8")
        return business
    except Exception as exc:
        cache_path.write_text(
            json.dumps({"main_business": "", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False),
            encoding="utf-8",
        )
        return ""


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["流通市值"] = pd.to_numeric(out["流通市值"], errors="coerce") / 100_000_000
    out["成交额"] = pd.to_numeric(out["成交额"], errors="coerce") / 100_000_000
    out["现价"] = pd.to_numeric(out["最新价"], errors="coerce")
    out["连续涨停天数"] = pd.to_numeric(out["连板数"], errors="coerce").fillna(0).astype(int)
    out["主营业务"] = out["代码"].astype(str).str.zfill(6).map(fetch_business).replace("", "主营业务待补充")
    out["涨停原因"] = out.apply(
        lambda row: (
            f"公开涨停池未披露具体原因；按行情特征归纳为{row.get('所属行业', '相关')}板块，"
            f"{int(row['连续涨停天数'])}连板，涨停统计{row.get('涨停统计', '')}。"
        ),
        axis=1,
    )
    keep = ["代码", "名称", "连续涨停天数", "流通市值", "现价", "成交额", "主营业务", "涨停原因"]
    return out[keep]


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    date = latest_market_date()
    notes: list[str] = []
    try:
        pool = ak.stock_zt_pool_em(date=date)
    except Exception as exc:
        metadata = {
            "source": "Eastmoney limit-up pool via AkShare",
            "status": "failed",
            "latest_date": date,
            "notes": [f"涨停股池获取失败：{type(exc).__name__}: {exc}"],
        }
        METADATA_JSON.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(metadata, ensure_ascii=False))
        return

    if pool.empty:
        metadata = {
            "source": "Eastmoney limit-up pool via AkShare",
            "status": "empty",
            "latest_date": date,
            "notes": ["涨停股池为空，可能为非交易日或数据源未更新。"],
        }
        METADATA_JSON.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(metadata, ensure_ascii=False))
        return

    normalized = normalize(pool)
    longest = normalized.sort_values(["连续涨停天数", "成交额"], ascending=[False, False]).head(10)
    amount_top = normalized.sort_values("成交额", ascending=False).head(10)
    longest.to_csv(LONGEST_CSV, index=False)
    amount_top.to_csv(AMOUNT_CSV, index=False)
    metadata = {
        "source": "Eastmoney limit-up pool via AkShare; company profile from CNINFO via AkShare",
        "status": "ok",
        "latest_date": f"{date[:4]}-{date[4:6]}-{date[6:]}",
        "pool_size": int(len(pool)),
        "notes": notes
        + [
            "东方财富涨停股池不含ST股票及科创板股票，且未披露逐股涨停原因；原因字段为行业与连板特征归纳，后续可替换为同花顺/财联社原因源。"
        ],
    }
    METADATA_JSON.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False))


if __name__ == "__main__":
    main()
