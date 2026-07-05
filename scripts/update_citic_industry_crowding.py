#!/usr/bin/env python3
"""Update CITIC level-1 industry crowding data.

Preferred source is WindPy. If Wind is unavailable, the script reads a local
weekly CSV exported from Wind or another approved source.
"""

from __future__ import annotations

import json
import multiprocessing as mp
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / ".work" / "vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))
WIND_API_DIR = Path("/Applications/Wind API.app/Contents/python")
if WIND_API_DIR.exists():
    sys.path.insert(0, str(WIND_API_DIR))

import pandas as pd


RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
RAW_CSV = RAW_DIR / "citic_industry_crowding_weekly.csv"
PROCESSED_CSV = PROCESSED_DIR / "citic_industry_crowding.csv"
METADATA_JSON = PROCESSED_DIR / "citic_industry_crowding.metadata.json"

START_10Y = "2016-01-01"
START_5Y = "2021-01-01"
WIND_TIMEOUT_SECONDS = 75

# Wind CITIC level-1 industry indexes. Names follow current common CITIC labels.
CITIC_LEVEL1 = {
    "CI005001.WI": "石油石化",
    "CI005002.WI": "煤炭",
    "CI005003.WI": "有色金属",
    "CI005004.WI": "电力及公用事业",
    "CI005005.WI": "钢铁",
    "CI005006.WI": "基础化工",
    "CI005007.WI": "建筑",
    "CI005008.WI": "建材",
    "CI005009.WI": "轻工制造",
    "CI005010.WI": "机械",
    "CI005011.WI": "电力设备及新能源",
    "CI005012.WI": "国防军工",
    "CI005013.WI": "汽车",
    "CI005014.WI": "商贸零售",
    "CI005015.WI": "消费者服务",
    "CI005016.WI": "家电",
    "CI005017.WI": "纺织服装",
    "CI005018.WI": "医药",
    "CI005019.WI": "食品饮料",
    "CI005020.WI": "农林牧渔",
    "CI005021.WI": "银行",
    "CI005022.WI": "非银行金融",
    "CI005023.WI": "房地产",
    "CI005024.WI": "交通运输",
    "CI005025.WI": "电子",
    "CI005026.WI": "通信",
    "CI005027.WI": "计算机",
    "CI005028.WI": "传媒",
    "CI005029.WI": "综合",
    "CI005030.WI": "综合金融",
}


def percentile_rank(series: pd.Series, value: float) -> float:
    sample = pd.to_numeric(series, errors="coerce").dropna()
    if sample.empty or pd.isna(value):
        return float("nan")
    return float((sample <= value).mean() * 100)


def normalize_source_frame(df: pd.DataFrame) -> pd.DataFrame:
    rename = {
        "日期": "date",
        "行业": "industry",
        "行业名称": "industry",
        "代码": "wind_code",
        "Wind代码": "wind_code",
        "PE_TTM": "pe_ttm",
        "PETTM": "pe_ttm",
        "PB_LF": "pb_lf",
        "PBLF": "pb_lf",
        "成交额": "amount_100mn",
        "成交额(亿元)": "amount_100mn",
        "amount": "amount_100mn",
    }
    out = df.rename(columns={k: v for k, v in rename.items() if k in df.columns}).copy()
    required = {"date", "industry", "pe_ttm", "pb_lf", "amount_100mn"}
    missing = required - set(out.columns)
    if missing:
        raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    for col in ["pe_ttm", "pb_lf", "amount_100mn"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["date", "industry"]).sort_values(["industry", "date"])
    return out


def fetch_from_wind_direct() -> tuple[pd.DataFrame, str]:
    try:
        from WindPy import w  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on local Wind install.
        raise RuntimeError(f"WindPy unavailable: {type(exc).__name__}") from exc

    start = START_10Y
    end = date.today().strftime("%Y-%m-%d")
    codes = list(CITIC_LEVEL1)
    w.start()
    error, data = w.wsd(codes, "pe_ttm,pb_lf,amt", start, end, "Period=W;Fill=Previous", usedf=True)
    if error != 0:
        raise RuntimeError(f"Wind wsd error: {error}")

    df = data.reset_index()
    date_col = df.columns[0]

    def find_col(candidates: list[str]) -> pd.Series:
        for candidate in candidates:
            if candidate in df.columns:
                return df[candidate]
        return pd.Series([pd.NA] * len(df))

    rows = []
    if isinstance(df.columns, pd.MultiIndex):
        df = data.copy()
        df.index.name = "date"
        long = df.stack(level=0, future_stack=True).reset_index()
        long.columns = ["date", "wind_code", "pe_ttm", "pb_lf", "amount_100mn"]
        long["industry"] = long["wind_code"].map(CITIC_LEVEL1)
        rows = long.to_dict("records")
    else:
        for code in codes:
            industry = CITIC_LEVEL1[code]
            part = pd.DataFrame(
                {
                    "date": df[date_col],
                    "wind_code": code,
                    "industry": industry,
                    "pe_ttm": find_col([f"PE_TTM_{code}", f"{code}_PE_TTM", "PE_TTM"]),
                    "pb_lf": find_col([f"PB_LF_{code}", f"{code}_PB_LF", "PB_LF"]),
                    "amount_100mn": find_col([f"AMT_{code}", f"{code}_AMT", "AMT"]),
                }
            )
            rows.extend(part.to_dict("records"))
    out = normalize_source_frame(pd.DataFrame(rows))
    # Wind amt is usually reported in yuan. Convert to 100mn yuan when values are large.
    if out["amount_100mn"].median() > 1_000_000:
        out["amount_100mn"] = out["amount_100mn"] / 100_000_000
    return out, "Wind API"


def wind_worker(queue: mp.Queue) -> None:
    try:
        history, source = fetch_from_wind_direct()
        queue.put(("ok", history, source))
    except Exception as exc:  # pragma: no cover - local Wind state dependent.
        queue.put(("error", f"{type(exc).__name__}: {exc}", ""))


def fetch_from_wind() -> tuple[pd.DataFrame, str]:
    queue: mp.Queue = mp.Queue()
    process = mp.Process(target=wind_worker, args=(queue,))
    process.start()
    process.join(WIND_TIMEOUT_SECONDS)
    if process.is_alive():
        process.terminate()
        process.join(5)
        raise TimeoutError(f"Wind API timed out after {WIND_TIMEOUT_SECONDS}s")
    if process.exitcode not in (0, None):
        raise RuntimeError(f"Wind API worker exited with code {process.exitcode}")
    if queue.empty():
        raise RuntimeError("Wind API worker returned no data")
    status, payload, source = queue.get()
    if status != "ok":
        raise RuntimeError(payload)
    return payload, source


def probe_public_fallbacks() -> list[str]:
    notes: list[str] = []
    try:
        import akshare as ak  # type: ignore

        available = []
        for name in ["stock_zh_index_hist_csindex", "stock_zh_index_value_csindex", "stock_industry_pe_ratio_cninfo"]:
            if hasattr(ak, name):
                available.append(name)
        notes.append(
            "AkShare 可用接口检查："
            + ("、".join(available) if available else "未发现可用行业估值接口")
            + "。这些接口不同时覆盖中信一级行业、PE_TTM、PB_LF、成交额三项十年/五年历史口径，未混入口径。"
        )
    except Exception as exc:
        notes.append(f"AkShare 检查失败：{type(exc).__name__}: {exc}")
    notes.append("中证/公开指数接口通常可取得成交金额或PE，但未找到可稳定获取中信一级行业PB_LF历史序列的公开接口。")
    return notes


def read_local_csv() -> tuple[pd.DataFrame, str]:
    if not RAW_CSV.exists():
        raise FileNotFoundError(f"{RAW_CSV} does not exist")
    return normalize_source_frame(pd.read_csv(RAW_CSV)), "local CSV"


def build_summary(history: pd.DataFrame) -> pd.DataFrame:
    latest_date = history["date"].max()
    prev_date = history.loc[history["date"].lt(latest_date), "date"].max()
    latest = history[history["date"].eq(latest_date)].copy()
    previous = history[history["date"].eq(prev_date)].copy() if pd.notna(prev_date) else pd.DataFrame()

    rows = []
    for _, row in latest.iterrows():
        industry = row["industry"]
        hist = history[history["industry"].eq(industry)]
        hist_10y = hist[hist["date"].ge(latest_date - pd.DateOffset(years=10))]
        hist_5y = hist[hist["date"].ge(latest_date - pd.DateOffset(years=5))]
        current = {
            "date": latest_date,
            "industry": industry,
            "wind_code": row.get("wind_code", ""),
            "pe_ttm": row["pe_ttm"],
            "pb_lf": row["pb_lf"],
            "amount_100mn": row["amount_100mn"],
            "pe_ttm_pctile_10y": percentile_rank(hist_10y["pe_ttm"], row["pe_ttm"]),
            "pb_lf_pctile_10y": percentile_rank(hist_10y["pb_lf"], row["pb_lf"]),
            "amount_pctile_5y": percentile_rank(hist_5y["amount_100mn"], row["amount_100mn"]),
        }
        if not previous.empty:
            prev_row = previous[previous["industry"].eq(industry)]
            if not prev_row.empty:
                prev_row = prev_row.iloc[0]
                prev_hist_10y = hist[hist["date"].le(prev_date) & hist["date"].ge(prev_date - pd.DateOffset(years=10))]
                prev_hist_5y = hist[hist["date"].le(prev_date) & hist["date"].ge(prev_date - pd.DateOffset(years=5))]
                current["pe_ttm_pctile_10y_wow"] = current["pe_ttm_pctile_10y"] - percentile_rank(prev_hist_10y["pe_ttm"], prev_row["pe_ttm"])
                current["pb_lf_pctile_10y_wow"] = current["pb_lf_pctile_10y"] - percentile_rank(prev_hist_10y["pb_lf"], prev_row["pb_lf"])
                current["amount_pctile_5y_wow"] = current["amount_pctile_5y"] - percentile_rank(prev_hist_5y["amount_100mn"], prev_row["amount_100mn"])
        rows.append(current)

    out = pd.DataFrame(rows)
    out["crowding_score"] = out[["pe_ttm_pctile_10y", "pb_lf_pctile_10y", "amount_pctile_5y"]].mean(axis=1)
    return out.sort_values("crowding_score", ascending=False)


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    source = ""
    notes: list[str] = []
    try:
        history, source = fetch_from_wind()
    except Exception as exc:
        notes.append(f"Wind API 暂不可用，已尝试公开源和本地CSV：{type(exc).__name__}: {exc}")
        notes.extend(probe_public_fallbacks())
        try:
            history, source = read_local_csv()
        except Exception as local_exc:
            metadata = {
                "source": "none",
                "status": "missing_data",
                "latest_date": "",
                "notes": notes + [f"本地CSV不可用：{local_exc}"],
                "required_csv": str(RAW_CSV.relative_to(ROOT)),
            }
            METADATA_JSON.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(metadata, ensure_ascii=False))
            return

    summary = build_summary(history)
    summary["date"] = pd.to_datetime(summary["date"]).dt.strftime("%Y-%m-%d")
    summary.to_csv(PROCESSED_CSV, index=False)
    metadata = {
        "source": source,
        "status": "ok",
        "latest_date": summary["date"].max(),
        "rows": int(len(summary)),
        "frequency": "weekly_last_trading_day",
        "notes": notes,
    }
    METADATA_JSON.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False))


if __name__ == "__main__":
    main()
