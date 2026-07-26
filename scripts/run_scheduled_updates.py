#!/usr/bin/env python3
"""Scheduled update orchestrator.

Implements the project's T+1 freshness rules so scheduled runs only fetch
genuinely new data (minimal API / token cost):

  - daily datasets : fresh when local data covers the previous trading day
                     (approximated by the previous business day);
  - weekly datasets: fresh when local data covers the most recent completed
                     trading week;
  - macro dataset  : attempted at most once every 20 hours; the workflow
                     schedule already restricts runs to the official release
                     windows (每月 9–20 日与月末 23:00 北京时间).

Only datasets that are stale get their update script executed; the site is
rebuilt only when at least one script actually ran, so a fully-fresh run
produces no API calls and no commit noise.

Usage:
  python scripts/run_scheduled_updates.py --mode daily   # 日频(含估值/ETF/涨停等)
  python scripts/run_scheduled_updates.py --mode macro   # 宏观(发布窗口 23:00)
  python scripts/run_scheduled_updates.py --mode all     # 手动全量(忽略新鲜度)

Note: 情绪指数与中信行业拥挤度依赖本地 Wind 能力, 由本地定时任务维护,
不在本编排器内(GitHub Actions 无 Wind 环境)。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = ROOT / "data" / "processed"

# script -> csv outputs whose max(date) determines freshness;
# value may also be a metadata json path containing "latest_date"
DAILY_DATASETS: dict[str, list[str]] = {
    "update_index_amount_share.py": ["index_amount_share.csv"],
    "update_theme_amount_share.py": ["theme_amount_share.csv"],
    "update_market_turnover.py": ["market_turnover.csv"],
    "update_southbound_flow.py": ["southbound_flow.csv"],
    "update_etf_dashboard.py": [
        "broad_etf_flow.csv",
        "star50_etf_flow.csv",
        "a_share_turnover_concentration.csv",
        "index_close.csv",
    ],
    "update_limit_up_tables.py": ["limit_up_tables.metadata.json"],
    "update_market_monitor.py": ["market_monitor_breadth.csv", "market_monitor_indices.csv"],
}

MACRO_DATASETS: dict[str, str] = {
    "update_macro_overview.py": "macro_overview.metadata.json",
    "update_industrial_profits.py": "industrial_profits.metadata.json",
}
MACRO_MIN_INTERVAL_H = 20  # 同一天发布窗口内不重复尝试


def previous_bday() -> pd.Timestamp:
    """上一交易日近似值(上一工作日, 不含法定节假日)。"""
    d = pd.Timestamp.now().normalize() - pd.Timedelta(days=1)
    while d.weekday() >= 5:
        d -= pd.Timedelta(days=1)
    return d


def csv_max_date(path: Path) -> pd.Timestamp | None:
    if not path.exists():
        return None
    try:
        if path.suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            raw = data.get("latest_date") or data.get("latest_common_date")
            return pd.to_datetime(raw, errors="coerce") if raw else None
        col = pd.read_csv(path, usecols=["date"])["date"]
        if col.empty:
            return None
        return pd.to_datetime(col, errors="coerce").max()
    except Exception:  # noqa: BLE001
        return None


def dataset_fresh(csv_names: list[str], expected: pd.Timestamp) -> bool:
    dates = [csv_max_date(PROCESSED_DIR / name) for name in csv_names]
    if any(d is None or pd.isna(d) for d in dates):
        return False
    return min(dates) >= expected  # 所有产出都覆盖到上一交易日才算新鲜


def run_script(name: str) -> bool:
    print(f"[run] {name}", flush=True)
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / name)], cwd=ROOT)
    if proc.returncode != 0:
        print(f"[warn] {name} exited {proc.returncode} (continuing)", flush=True)
    return True  # 即使失败也尝试重建, 保留已有部分更新


def macro_fresh(metadata_name: str) -> bool:
    path = PROCESSED_DIR / metadata_name
    if not path.exists():
        return False
    age_h = (time.time() - path.stat().st_mtime) / 3600
    return age_h < MACRO_MIN_INTERVAL_H


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["daily", "macro", "all"], required=True)
    args = parser.parse_args()

    ran: list[str] = []
    skipped: list[str] = []
    expected = previous_bday()

    if args.mode in {"daily", "all"}:
        for script, csvs in DAILY_DATASETS.items():
            if args.mode != "all" and dataset_fresh(csvs, expected):
                skipped.append(script)
                continue
            run_script(script)
            ran.append(script)

    if args.mode in {"macro", "all"}:
        for script, metadata_name in MACRO_DATASETS.items():
            if args.mode != "all" and macro_fresh(metadata_name):
                skipped.append(script)
                continue
            run_script(script)
            ran.append(script)

    built = False
    if ran:
        run_script("build_site_from_processed.py")
        built = True

    summary = {
        "mode": args.mode,
        "expected_latest": expected.strftime("%Y-%m-%d"),
        "ran": ran,
        "skipped_fresh": skipped,
        "rebuilt": built,
    }
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
