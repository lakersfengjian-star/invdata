#!/usr/bin/env python3
"""Update macro overview indicators for the dashboard."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / ".work" / "vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

import akshare as ak
import pandas as pd


PROCESSED_DIR = ROOT / "data" / "processed"
RAW_FALLBACK = ROOT / "data" / "raw" / "macro_overview_extra.csv"
RAW_PBOC = ROOT / "data" / "raw" / "pbc_macro_credit.csv"
OUT_CSV = PROCESSED_DIR / "macro_overview.csv"
METADATA_JSON = PROCESSED_DIR / "macro_overview.metadata.json"

INDICATOR_ORDER = [
    ("industrial", "工增"),
    ("service", "服务业"),
    ("retail", "社零"),
    ("fai", "固投"),
    ("fai_real_estate", "固投/房地产"),
    ("fai_infra", "固投/基建"),
    ("fai_manufacturing", "固投/制造业"),
    ("export", "出口"),
    ("import", "进口"),
    ("cpi", "CPI"),
    ("ppi", "PPI"),
    ("social_financing", "社融"),
    ("enterprise_long_loan", "企业中长期贷款"),
    ("m1", "M1"),
    ("gdp", "GDP"),
]


def parse_month(value: object) -> pd.Timestamp | pd.NaT:
    text = str(value)
    match = re.search(r"(\d{4})年(\d{1,2})月", text)
    if match:
        return pd.Timestamp(int(match.group(1)), int(match.group(2)), 1)
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return pd.NaT
    return pd.Timestamp(parsed.year, parsed.month, 1)


def parse_quarter(value: object) -> pd.Timestamp | pd.NaT:
    text = str(value)
    year_match = re.search(r"(\d{4})年", text)
    quarter_matches = re.findall(r"(\d)", text.split("年", 1)[-1])
    if year_match and quarter_matches:
        quarter = int(quarter_matches[-1])
        month = quarter * 3
        return pd.Timestamp(int(year_match.group(1)), month, 1)
    return pd.NaT


def keep_latest_six(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    out.loc[out["value"].eq(0), "value"] = pd.NA
    out = out.dropna(subset=["date", "value"]).sort_values("date")
    return out.tail(6)


def monthly_yoy_from_cumulative(df: pd.DataFrame, date_col: str, value_col: str) -> pd.DataFrame:
    out = df[[date_col, value_col]].copy()
    out.columns = ["date", "cum_value"]
    out["date"] = out["date"].map(parse_month)
    out["cum_value"] = pd.to_numeric(out["cum_value"], errors="coerce")
    out = out.dropna(subset=["date", "cum_value"]).sort_values("date")
    out["year"] = out["date"].dt.year
    out["month"] = out["date"].dt.month
    out["prev_cum"] = out.groupby("year")["cum_value"].shift(1)
    out["monthly_value"] = out["cum_value"] - out["prev_cum"]
    out.loc[out["month"].le(2), "monthly_value"] = out["cum_value"]
    lookup = out.set_index("date")["monthly_value"]
    out["last_year_monthly"] = out["date"].map(lambda value: lookup.get(value - pd.DateOffset(years=1)))
    out["value"] = (out["monthly_value"] / out["last_year_monthly"] - 1) * 100
    return out[["date", "value"]]


def stock_yoy(df: pd.DataFrame, date_col: str, stock_col: str) -> pd.DataFrame:
    out = df[[date_col, stock_col]].copy()
    out.columns = ["date", "stock"]
    out["date"] = out["date"].map(parse_month)
    out["stock"] = pd.to_numeric(out["stock"], errors="coerce")
    out = out.dropna(subset=["date", "stock"]).sort_values("date")
    lookup = out.set_index("date")["stock"]
    out["last_year_stock"] = out["date"].map(lambda value: lookup.get(value - pd.DateOffset(years=1)))
    out["value"] = (out["stock"] / out["last_year_stock"] - 1) * 100
    return out[["date", "value"]]


def series_from_func(key: str, label: str, func_name: str, date_col: str, value_col: str, parser=parse_month) -> tuple[pd.DataFrame, str | None]:
    try:
        raw = getattr(ak, func_name)()
        if raw.empty or date_col not in raw or value_col not in raw:
            return pd.DataFrame(), f"{label}：接口返回为空或缺少字段 {date_col}/{value_col}。"
        out = raw[[date_col, value_col]].copy()
        out.columns = ["date", "value"]
        out["date"] = out["date"].map(parser)
        out["indicator_key"] = key
        out["indicator"] = label
        out["source"] = f"AkShare {func_name}"
        return keep_latest_six(out), None
    except Exception as exc:
        return pd.DataFrame(), f"{label}：获取失败：{type(exc).__name__}: {exc}"


def series_from_nbs_monthly(key: str, label: str, path_candidates: list[str], source_note: str, mode: str = "direct") -> tuple[pd.DataFrame, str | None]:
    notes = []
    for path in path_candidates:
        try:
            raw = ak.macro_china_nbs_nation(kind="月度数据", path=path, period="2024-")
            if raw.empty:
                notes.append(f"{path}: empty")
                continue
            if mode == "cumulative_to_monthly_yoy":
                value_col = raw.columns[-1]
                out = monthly_yoy_from_cumulative(raw.reset_index(), raw.reset_index().columns[0], value_col)
            else:
                frame = raw.reset_index()
                out = frame[[frame.columns[0], frame.columns[-1]]].copy()
                out.columns = ["date", "value"]
                out["date"] = out["date"].map(parse_month)
            out["indicator_key"] = key
            out["indicator"] = label
            out["source"] = source_note
            result = keep_latest_six(out)
            if not result.empty:
                return result, None
            notes.append(f"{path}: no valid values")
        except Exception as exc:
            notes.append(f"{path}: {type(exc).__name__}: {exc}")
    return pd.DataFrame(), f"{label}：国家统计局自动获取失败；{' | '.join(notes[:3])}"


def series_from_pbc_local(key: str, label: str, value_mode: str) -> tuple[pd.DataFrame, str | None]:
    if not RAW_PBOC.exists():
        return pd.DataFrame(), f"{label}：未提供人民银行原始数据文件 {RAW_PBOC.relative_to(ROOT)}。"
    try:
        raw = pd.read_csv(RAW_PBOC)
        required = {"indicator_key", "date"}
        missing = sorted(required - set(raw.columns))
        if missing:
            return pd.DataFrame(), f"{label}：人民银行原始数据文件缺少字段：{', '.join(missing)}。"
        subset = raw[raw["indicator_key"].eq(key)].copy()
        if subset.empty:
            return pd.DataFrame(), f"{label}：人民银行原始数据文件未找到 {key}。"
        if "value" in subset.columns and subset["value"].notna().any():
            out = subset[["date", "value"]].copy()
            out["date"] = out["date"].map(parse_month)
        elif value_mode == "stock_yoy" and "stock" in subset.columns:
            out = stock_yoy(subset, "date", "stock")
        else:
            return pd.DataFrame(), f"{label}：人民银行原始数据文件需提供 value 或 stock 字段。"
        out["indicator_key"] = key
        out["indicator"] = label
        out["source"] = subset.get("source", pd.Series(["PBOC local"] * len(subset))).iloc[0]
        return keep_latest_six(out), None
    except Exception as exc:
        return pd.DataFrame(), f"{label}：人民银行原始数据读取失败：{type(exc).__name__}: {exc}"


def load_fallback() -> tuple[pd.DataFrame, list[str]]:
    if not RAW_FALLBACK.exists():
        return pd.DataFrame(), [f"未提供本地补充文件：{RAW_FALLBACK.relative_to(ROOT)}。"]
    raw = pd.read_csv(RAW_FALLBACK)
    required = {"indicator_key", "indicator", "date", "value"}
    missing = sorted(required - set(raw.columns))
    if missing:
        return pd.DataFrame(), [f"本地补充文件缺少字段：{', '.join(missing)}。"]
    out = raw.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    out["source"] = out.get("source", "local fallback")
    return out.dropna(subset=["date", "value"]), []


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    DATA_SOURCES = [
        ("industrial", "工增", "macro_china_gyzjz", "月份", "同比增长", parse_month),
        ("retail", "社零", "macro_china_consumer_goods_retail", "月份", "同比增长", parse_month),
        ("fai", "固投", "macro_china_gdzctz", "月份", "同比增长", parse_month),
        ("export", "出口", "macro_china_hgjck", "月份", "当月出口额-同比增长", parse_month),
        ("import", "进口", "macro_china_hgjck", "月份", "当月进口额-同比增长", parse_month),
        ("cpi", "CPI", "macro_china_cpi", "月份", "全国-同比增长", parse_month),
        ("ppi", "PPI", "macro_china_ppi", "月份", "当月同比增长", parse_month),
        ("m1", "M1", "macro_china_money_supply", "月份", "货币(M1)-同比增长", parse_month),
        ("gdp", "GDP", "macro_china_gdp", "季度", "国内生产总值-同比增长", parse_quarter),
    ]
    frames: list[pd.DataFrame] = []
    notes: list[str] = []
    for item in DATA_SOURCES:
        frame, note = series_from_func(*item)
        if not frame.empty:
            frames.append(frame)
        if note:
            notes.append(note)

    EXTRA_SOURCES = [
        (
            series_from_nbs_monthly,
            (
                "service",
                "服务业",
                [
                    "服务业 > 服务业生产指数 > 服务业生产指数_当月同比增长",
                    "服务业 > 服务业生产指数 > 服务业生产指数同比增长",
                    "第三产业 > 服务业生产指数 > 服务业生产指数同比增长",
                ],
                "国家统计局 服务业生产指数（当月同比）",
                "direct",
            ),
        ),
        (
            series_from_nbs_monthly,
            (
                "fai_real_estate",
                "固投/房地产",
                [
                    "房地产 > 房地产开发投资完成额 > 房地产开发投资完成额_累计值",
                    "固定资产投资 > 房地产开发投资完成额 > 房地产开发投资完成额_累计值",
                    "房地产开发投资 > 房地产开发投资完成额 > 房地产开发投资完成额_累计值",
                ],
                "国家统计局 房地产开发投资完成额累计值倒算当月同比",
                "cumulative_to_monthly_yoy",
            ),
        ),
        (
            series_from_nbs_monthly,
            (
                "fai_infra",
                "固投/基建",
                [
                    "固定资产投资 > 固定资产投资完成额 > 基础设施建设投资_累计值",
                    "固定资产投资（不含农户） > 固定资产投资完成额 > 基础设施建设投资_累计值",
                    "固定资产投资 > 按行业分固定资产投资 > 基础设施建设投资_累计值",
                ],
                "国家统计局 基础设施建设固定资产投资完成额累计值倒算当月同比",
                "cumulative_to_monthly_yoy",
            ),
        ),
        (
            series_from_nbs_monthly,
            (
                "fai_manufacturing",
                "固投/制造业",
                [
                    "固定资产投资 > 固定资产投资完成额 > 制造业投资_累计值",
                    "固定资产投资（不含农户） > 固定资产投资完成额 > 制造业投资_累计值",
                    "固定资产投资 > 按行业分固定资产投资 > 制造业投资_累计值",
                ],
                "国家统计局 制造业固定资产投资完成额累计值倒算当月同比",
                "cumulative_to_monthly_yoy",
            ),
        ),
        (series_from_pbc_local, ("social_financing", "社融", "direct")),
        (series_from_pbc_local, ("enterprise_long_loan", "企业中长期贷款", "stock_yoy")),
    ]
    for func, args in EXTRA_SOURCES:
        frame, note = func(*args)
        if not frame.empty:
            frames.append(frame)
        if note:
            notes.append(note)

    fallback, fallback_notes = load_fallback()
    notes.extend(fallback_notes)
    if not fallback.empty:
        for key, label in INDICATOR_ORDER:
            existing = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
            if key in set(existing.get("indicator_key", [])):
                continue
            subset = fallback[fallback["indicator_key"].eq(key)].copy()
            if subset.empty:
                continue
            subset["indicator"] = subset["indicator"].fillna(label)
            subset["source"] = subset["source"].fillna("local fallback")
            frames.append(keep_latest_six(subset))

    present_keys = set()
    if frames:
        present_keys = set(pd.concat(frames, ignore_index=True)["indicator_key"].unique())
    for key, label in INDICATOR_ORDER:
        if key not in present_keys:
            notes.append(f"{label}：暂无可用自动数据，图中保留面板占位。")

    data = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["date", "value", "indicator_key", "indicator", "source"])
    order_map = {key: i for i, (key, _label) in enumerate(INDICATOR_ORDER)}
    data["order"] = data["indicator_key"].map(order_map)
    data = data.sort_values(["order", "date"])
    data["date"] = pd.to_datetime(data["date"]).dt.strftime("%Y-%m-%d")
    data[["indicator_key", "indicator", "date", "value", "source"]].to_csv(OUT_CSV, index=False)

    latest_by_key = data.groupby("indicator_key")["date"].max().to_dict() if not data.empty else {}
    metadata = {
        "source": "AkShare Eastmoney macro interfaces; NBS macro interface; optional PBOC/local fallback files",
        "status": "partial" if notes else "ok",
        "latest_date": max(latest_by_key.values()) if latest_by_key else "",
        "latest_by_indicator": latest_by_key,
        "unit": "%",
        "notes": notes,
        "indicator_order": [{"indicator_key": key, "indicator": label} for key, label in INDICATOR_ORDER],
    }
    METADATA_JSON.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"rows": len(data), **metadata}, ensure_ascii=False))


if __name__ == "__main__":
    main()
