#!/usr/bin/env python3
"""Fetch CITIC level-1 industry crowding inputs via Wind AIFin Market CLI.

Pulls weekly PE(TTM)/PB(LF) and weekly turnover for the 30 CITIC level-1
industry indexes through the wind-mcp-skill CLI (no local Wind terminal
needed), and writes data/raw/citic_industry_crowding_weekly.csv.

The CLI caps NL history queries at ~100 rows, so data is fetched in yearly
chunks (~52 weekly rows each) and cached under data/raw/wind_cli_cache/ so
interrupted runs can resume.

Usage:
    python scripts/fetch_citic_crowding_wind_cli.py [--budget SECONDS]
    python scripts/fetch_citic_crowding_wind_cli.py --refresh-latest

--refresh-latest 用于每周例行增量更新: 仅删除并重新获取覆盖最近 45 天的
缓存块(当前年度块)和日频估值缓存, 历史年份块保持复用, 把 Wind 调用量
压到最低(每行业约 2 次调用)。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = Path.home() / ".agents" / "skills" / "wind-mcp-skill"
CLI = SKILL_DIR / "scripts" / "cli.mjs"

RAW_DIR = ROOT / "data" / "raw"
CACHE_DIR = RAW_DIR / "wind_cli_cache"
OUT_CSV = RAW_DIR / "citic_industry_crowding_weekly.csv"

START_YEAR = 2016
WORKERS = 6
CALL_TIMEOUT = 120
MAX_RETRIES = 3

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


def year_chunks() -> list[tuple[str, str]]:
    today = date.today()
    chunks = []
    for year in range(START_YEAR, today.year + 1):
        begin = f"{year}0101"
        end = f"{year}1231" if year < today.year else today.strftime("%Y%m%d")
        chunks.append((begin, end))
    return chunks


def cn_date(yyyymmdd: str) -> str:
    return f"{yyyymmdd[:4]}年{int(yyyymmdd[4:6])}月{int(yyyymmdd[6:8])}日"


def cache_path(kind: str, code: str, begin: str, end: str) -> Path:
    return CACHE_DIR / f"{kind}_{code.replace('.', '_')}_{begin}_{end}.json"


def cli_call(server: str, tool: str, params: dict) -> dict:
    """Run one CLI call; return parsed inner payload. Raises on failure."""
    cmd = ["node", str(CLI), "call", server, tool, json.dumps(params, ensure_ascii=False)]
    proc = subprocess.run(
        cmd, cwd=SKILL_DIR, capture_output=True, text=True, timeout=CALL_TIMEOUT
    )
    if proc.returncode != 0:
        raise RuntimeError(f"CLI exit {proc.returncode}: {proc.stdout[:300]} {proc.stderr[:200]}")
    outer = json.loads(proc.stdout)
    if outer.get("isError"):
        raise RuntimeError(f"CLI isError: {proc.stdout[:300]}")
    inner = json.loads(outer["content"][0]["text"])
    if inner.get("error"):
        raise RuntimeError(f"Wind error: {json.dumps(inner['error'], ensure_ascii=False)[:300]}")
    return inner


def fetch_one(kind: str, code: str, begin: str, end: str) -> Path:
    path = cache_path(kind, code, begin, end)
    if path.exists():
        return path
    if kind == "val":
        server, tool = "index_data", "get_index_fundamentals"
        question = f"{code}{cn_date(begin)}至{cn_date(end)}每周市盈率(TTM)和市净率(LF)"
    else:
        server, tool = "index_data", "get_index_technicals"
        question = f"{code}{cn_date(begin)}至{cn_date(end)}每周成交额,单位亿元"
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            inner = cli_call(server, tool, {"question": question})
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(inner, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
            return path
        except Exception as exc:  # noqa: BLE001 - retry any transient failure.
            last_exc = exc
            time.sleep(2 * attempt)
    raise RuntimeError(f"{kind} {code} {begin}-{end} failed after {MAX_RETRIES} tries: {last_exc}")


def parse_val_rows(inner: dict) -> list[dict]:
    out = []
    for block in inner["data"]["data"]:
        cols = [c["name"] for c in block["columns"]]
        pe_i = next((i for i, c in enumerate(cols) if "市盈率" in c), None)
        pb_i = next((i for i, c in enumerate(cols) if "市净率" in c), None)
        dt_i = cols.index("日期")
        if pe_i is None or pb_i is None:
            continue
        for row in block["rows"]:
            out.append({"date": row[dt_i], "pe_ttm": row[pe_i], "pb_lf": row[pb_i]})
    return out


def to_week_ending_sunday(date_str: str) -> str:
    from datetime import datetime, timedelta

    dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
    days_ahead = (6 - dt.weekday()) % 7  # Sunday stays Sunday.
    return (dt + timedelta(days=days_ahead)).strftime("%Y-%m-%d")


def parse_amt_rows(inner: dict) -> list[dict]:
    out = []
    for block in inner["data"]["data"]:
        cols = [c["name"] for c in block["columns"]]
        amt_i = next(
            (i for i, c in enumerate(cols) if "成交额" in c and "时间" not in c), None
        )
        end_i = next((i for i, c in enumerate(cols) if "截止时间" in c), None)
        if amt_i is None or end_i is None:
            continue
        for row in block["rows"]:
            if row[end_i] is None:
                continue
            out.append({"date": to_week_ending_sunday(row[end_i]), "amount_100mn": row[amt_i]})
    return out


def fetch_latest_daily_val(code: str) -> Path:
    """Daily PE/PB for recent days — weekly valuation lags one week."""
    path = CACHE_DIR / f"val_daily_latest_{code.replace('.', '_')}.json"
    if path.exists():
        return path
    inner = cli_call("index_data", "get_index_fundamentals",
                     {"question": f"{code}最近2周每日市盈率(TTM)和市净率(LF)"})
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(inner, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--budget", type=float, default=0,
                        help="Stop launching new calls after N seconds (0 = no limit).")
    parser.add_argument("--refresh-latest", action="store_true",
                        help="Invalidate caches covering the last 45 days so only "
                             "recent chunks are refetched (weekly incremental update).")
    args = parser.parse_args()
    started = time.monotonic()

    if not CLI.exists():
        print(json.dumps({"status": "error", "error": f"wind-mcp-skill CLI not found: {CLI}"}, ensure_ascii=False))
        sys.exit(1)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    chunks = year_chunks()

    if args.refresh_latest:
        from datetime import timedelta

        cutoff = (date.today() - timedelta(days=45)).strftime("%Y%m%d")
        recent_ends = {e for _b, e in chunks if e >= cutoff}
        removed = 0
        for kind in ("val", "amt"):
            for code in CITIC_LEVEL1:
                for end in recent_ends:
                    for begin in (b for b, e in chunks if e == end):
                        path = cache_path(kind, code, begin, end)
                        if path.exists():
                            path.unlink()
                            removed += 1
        for path in CACHE_DIR.glob("val_daily_latest_*.json"):
            path.unlink()
            removed += 1
        print(f"refresh-latest: invalidated {removed} cached files", flush=True)
    tasks = [(kind, code, b, e)
             for code in CITIC_LEVEL1
             for (b, e) in chunks
             for kind in ("val", "amt")]
    pending = [t for t in tasks if not cache_path(t[0], t[1], t[2], t[3]).exists()]
    print(f"total chunks: {len(tasks)}, cached: {len(tasks) - len(pending)}, to fetch: {len(pending)}", flush=True)

    errors: list[str] = []
    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {}
        for t in pending:
            if args.budget and time.monotonic() - started > args.budget:
                break
            futures[pool.submit(fetch_one, *t)] = t
        for fut in as_completed(futures):
            t = futures[fut]
            try:
                fut.result()
                done += 1
                if done % 20 == 0:
                    print(f"fetched {done}/{len(pending)}", flush=True)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{t}: {exc}")

    remaining = [t for t in tasks if not cache_path(t[0], t[1], t[2], t[3]).exists()]
    if remaining:
        print(json.dumps({
            "status": "partial",
            "fetched_this_run": done,
            "remaining_chunks": len(remaining),
            "errors": errors[:10],
        }, ensure_ascii=False))
        sys.exit(2 if done == 0 else 0)

    # Merge cache into the weekly CSV.
    import pandas as pd

    # Supplement the newest trading week from daily valuation (weekly lags a week).
    daily_errors: list[str] = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = {pool.submit(fetch_latest_daily_val, code): code for code in CITIC_LEVEL1}
        for fut in as_completed(futs):
            try:
                fut.result()
            except Exception as exc:  # noqa: BLE001
                daily_errors.append(f"{futs[fut]}: {exc}")

    rows = []
    for code, industry in CITIC_LEVEL1.items():
        vals, amts = [], []
        for (b, e) in chunks:
            vals.extend(parse_val_rows(json.loads(cache_path("val", code, b, e).read_text(encoding="utf-8"))))
            amts.extend(parse_amt_rows(json.loads(cache_path("amt", code, b, e).read_text(encoding="utf-8"))))
        vdf = pd.DataFrame(vals).drop_duplicates(subset="date")
        adf = pd.DataFrame(amts).drop_duplicates(subset="date")
        daily_path = CACHE_DIR / f"val_daily_latest_{code.replace('.', '_')}.json"
        if daily_path.exists():
            daily = parse_val_rows(json.loads(daily_path.read_text(encoding="utf-8")))
            if daily:
                latest = max(daily, key=lambda r: r["date"])
                sunday = to_week_ending_sunday(latest["date"])
                if sunday not in set(vdf["date"]):
                    vdf = pd.concat([vdf, pd.DataFrame([{
                        "date": sunday, "pe_ttm": latest["pe_ttm"], "pb_lf": latest["pb_lf"],
                    }])], ignore_index=True)
        merged = pd.merge(vdf, adf, on="date", how="inner")
        merged["industry"] = industry
        merged["wind_code"] = code
        rows.append(merged)

    out = pd.concat(rows, ignore_index=True)
    # PE_TTM is None for industries with negative aggregate earnings — keep those
    # rows; PB/turnover percentiles still apply.
    out = out.dropna(subset=["pb_lf", "amount_100mn"])
    out = out[["date", "industry", "wind_code", "pe_ttm", "pb_lf", "amount_100mn"]]
    out = out.sort_values(["industry", "date"])
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)

    print(json.dumps({
        "status": "ok",
        "csv": str(OUT_CSV.relative_to(ROOT)),
        "rows": int(len(out)),
        "industries": int(out["industry"].nunique()),
        "date_range": [str(out["date"].min()), str(out["date"].max())],
        "fetched_this_run": done,
        "errors": errors[:10],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
