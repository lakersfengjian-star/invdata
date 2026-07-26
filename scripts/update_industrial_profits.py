#!/usr/bin/env python3
"""Update NBS industrial enterprise profits (monthly cumulative) for the earnings panel.

指标: 规模以上工业企业利润总额 累计值(亿元) / 累计同比(%), 国家统计局月度发布
(通常每月 27 日左右发布上月数据)。

取数策略(最小 API 消耗, 遵循 T+1 宏观规则):
  - 历史底座: data/raw/industrial_profits_wind.csv(一次性用本地 Wind EDB
    M0000556/M0000557 铺底, 已入库随仓库分发)。
  - 增量: AkShare 国家统计局接口(GitHub Actions 可用)只拉取本地最大日期前一年起
    的窗口, 合并更新月份; 已覆盖到预期最新月份时完全不发请求。
  - NBS 接口失败时保留 Wind 底座数据, 元数据记录失败原因(status=partial)。

输出:
  - data/processed/industrial_profits.csv(date 为月末日期, cum_value 亿元, cum_yoy %)
  - data/processed/industrial_profits.metadata.json
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / ".work" / "vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

import pandas as pd

PROCESSED_DIR = ROOT / "data" / "processed"
RAW_WIND = ROOT / "data" / "raw" / "industrial_profits_wind.csv"
OUT_CSV = PROCESSED_DIR / "industrial_profits.csv"
METADATA_JSON = PROCESSED_DIR / "industrial_profits.metadata.json"

NBS_CUM_PATHS = [
    "工业 > 工业企业主要经济指标 > 利润总额_累计值",
    "工业 > 规模以上工业企业主要经济指标 > 利润总额_累计值",
    "工业 > 工业企业主要经济指标 > 利润总额(累计值)",
]
NBS_YOY_PATHS = [
    "工业 > 工业企业主要经济指标 > 利润总额_累计增长",
    "工业 > 规模以上工业企业主要经济指标 > 利润总额_累计增长",
    "工业 > 工业企业主要经济指标 > 利润总额(累计增长)",
]


def parse_month(value: object) -> pd.Timestamp | pd.NaT:
    text = str(value)
    match = re.search(r"(\d{4})年(\d{1,2})月", text)
    if match:
        return pd.Timestamp(int(match.group(1)), int(match.group(2)), 1) + pd.offsets.MonthEnd(0)
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return pd.NaT
    return pd.Timestamp(parsed.year, parsed.month, 1) + pd.offsets.MonthEnd(0)


def expected_latest_month(today: pd.Timestamp | None = None) -> pd.Timestamp:
    """统计局通常每月 27 日左右发布上月数据: 27 日及以后预期到上个月, 否则预期到上上个月。"""
    today = today or pd.Timestamp.now()
    first = today.normalize().replace(day=1)
    return (first - pd.DateOffset(months=1)) if today.day >= 27 else (first - pd.DateOffset(months=2))


def load_base() -> pd.DataFrame:
    if not RAW_WIND.exists():
        return pd.DataFrame(columns=["date", "cum_value", "cum_yoy", "source"])
    df = pd.read_csv(RAW_WIND, parse_dates=["date"])
    return df.dropna(subset=["date", "cum_value"]).sort_values("date")


def fetch_nbs_series(path_candidates: list[str], period: str) -> tuple[pd.DataFrame, str | None]:
    """返回 (date, value) 数据框; 全部候选失败时返回空框与错误摘要。"""
    import akshare as ak

    notes: list[str] = []
    for path in path_candidates:
        try:
            raw = ak.macro_china_nbs_nation(kind="月度数据", path=path, period=period)
            if raw.empty:
                notes.append(f"{path}: empty")
                continue
            frame = raw.reset_index()
            out = frame[[frame.columns[0], frame.columns[-1]]].copy()
            out.columns = ["date", "value"]
            out["date"] = out["date"].map(parse_month)
            out["value"] = pd.to_numeric(out["value"], errors="coerce")
            out = out.dropna(subset=["date", "value"])
            if not out.empty:
                return out, None
            notes.append(f"{path}: no valid values")
        except Exception as exc:  # noqa: BLE001
            notes.append(f"{path}: {type(exc).__name__}: {exc}")
    return pd.DataFrame(columns=["date", "value"]), " | ".join(notes[:3])


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    notes: list[str] = []
    base = load_base()
    if base.empty:
        notes.append(f"未找到 Wind 底座文件 {RAW_WIND.relative_to(ROOT)}。")

    expected = expected_latest_month()
    local_latest = base["date"].max() if not base.empty else pd.NaT
    frames = [base]

    if pd.notna(local_latest) and local_latest >= expected:
        notes.append(f"本地数据已覆盖预期最新月份 {expected.strftime('%Y-%m')}, 跳过 NBS 请求。")
    else:
        start_year = max((local_latest.year - 1) if pd.notna(local_latest) else 2020, 2020)
        period = f"{start_year}-"
        cum, cum_note = fetch_nbs_series(NBS_CUM_PATHS, period)
        yoy, yoy_note = fetch_nbs_series(NBS_YOY_PATHS, period)
        if cum.empty:
            notes.append(f"NBS 累计值获取失败, 保留本地底座:{cum_note}")
        else:
            merged = cum.rename(columns={"value": "cum_value"})
            if not yoy.empty:
                merged = merged.merge(yoy.rename(columns={"value": "cum_yoy"}), on="date", how="left")
            else:
                merged["cum_yoy"] = pd.NA
                notes.append(f"NBS 累计同比获取失败(累计值已更新):{yoy_note}")
            merged["source"] = "AkShare macro_china_nbs_nation 国家统计局"
            frames.append(merged)

    data = pd.concat(frames, ignore_index=True).dropna(subset=["date", "cum_value"])
    # 同一日期优先保留 NBS 增量(后追加的覆盖底座)
    data = data.sort_values("date").drop_duplicates(subset=["date"], keep="last")
    data = data.sort_values("date")

    data_out = data.assign(date=data["date"].dt.strftime("%Y-%m-%d"))
    data_out[["date", "cum_value", "cum_yoy", "source"]].to_csv(OUT_CSV, index=False)

    latest_date = data["date"].max().strftime("%Y-%m-%d") if not data.empty else ""
    status = "ok" if not notes or all("跳过" in note for note in notes) else "partial"
    metadata = {
        "source": "Wind EDB M0000556/M0000557 底座 + AkShare NBS 增量(国家统计局)",
        "indicator": "规模以上工业企业利润总额 累计值/累计同比",
        "status": status,
        "latest_date": latest_date,
        "expected_latest_month": expected.strftime("%Y-%m"),
        "unit": "亿元 / %",
        "notes": notes,
    }
    METADATA_JSON.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"rows": len(data_out), **metadata}, ensure_ascii=False))


if __name__ == "__main__":
    main()
