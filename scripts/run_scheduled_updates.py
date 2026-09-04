#!/usr/bin/env python3
"""Scheduled update orchestrator.

The workflow runs once per day at 06:00 Asia/Shanghai. This script decides
which datasets are stale, runs only those update scripts, rebuilds the static
site when needed, and writes a compact audit file for later handoff.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RUN_CWD = Path(os.environ.get("INVDATA_RUN_CWD", ROOT))
PROCESSED_DIR = ROOT / "data" / "processed"
AUDIT_PATH = PROCESSED_DIR / "update_audit.json"
WIND_CLI = Path(
    os.environ.get("WIND_CLI", Path.home() / ".agents" / "skills" / "wind-mcp-skill" / "scripts" / "cli.mjs")
).expanduser()
SHANGHAI_TZ = "Asia/Shanghai"

# script -> outputs whose min(max(date/latest_date)) determines freshness.
DAILY_DATASETS: dict[str, list[str]] = {
    "update_index_amount_share.py": ["index_amount_share.csv"],
    "update_theme_amount_share.py": ["theme_amount_share.csv"],
    "update_market_turnover.py": ["market_turnover.csv"],
    "update_sentiment_index.py": ["sentiment_index.csv"],
    "update_hk_dashboard.py": [
        "hk_sentiment.csv",
        "hk_rates.csv",
        "hk_fx.csv",
        "hk_ah_premium.csv",
        "hk_hsi_valuation.csv",
        "hk_dividend_yield.csv",
        "southbound_flow.csv",
    ],
    "update_value_growth_spread.py": ["value_growth_spread.csv"],
    "update_style_performance.py": ["style_index_performance.csv"],
    "update_wind_index_valuation.py": ["index_pe_ttm_valuation.csv"],
    "update_etf_dashboard.py": [
        "broad_etf_flow.csv",
        "star50_etf_flow.csv",
        "a_share_turnover_concentration.csv",
        "index_close.csv",
        "index_pe_ttm_valuation.csv",
    ],
    "update_limit_up_tables.py": ["limit_up_tables.metadata.json"],
    "update_market_monitor.py": ["market_monitor_breadth.csv", "market_monitor_indices.csv"],
    "update_fixed_income_rates_wind.py": ["fixed_income_rates_wind.csv"],
    "update_us_rates_wind.py": ["us_rates_wind.csv"],
}

WEEKLY_CITIC_INPUT = ROOT / "data" / "raw" / "citic_industry_crowding_weekly.csv"
WEEKLY_CITIC_PIPELINE = [
    ("fetch_citic_crowding_wind_cli.py", ["--refresh-latest"]),
    ("update_citic_industry_crowding.py", []),
    ("update_citic_pb_dispersion.py", []),
]

MACRO_DATASETS: dict[str, str] = {
    "update_macro_overview.py": "macro_overview.metadata.json",
    "update_macro_credit_inventory.py": "macro_credit_inventory.metadata.json",
    "update_macro_fiscal.py": "macro_fiscal.metadata.json",
    "update_macro_pmi.py": "macro_pmi.metadata.json",
    "update_industrial_profits.py": "industrial_profits.metadata.json",
}

MACRO_RELEASE_DAYS = set(range(9, 21)) | set(range(27, 32))
MACRO_MIN_INTERVAL_H = 20
LOCAL_WIND_DATASETS = {
    "update_sentiment_index.py",
    "update_hk_dashboard.py",
    "update_value_growth_spread.py",
    "update_citic_pb_dispersion.py",
    "update_style_performance.py",
    "update_wind_index_valuation.py",
    "update_fixed_income_rates_wind.py",
    "update_us_rates_wind.py",
    "update_macro_pmi.py",
}
SCRIPT_TIMEOUT_SECONDS = 45 * 60


def now_shanghai() -> pd.Timestamp:
    return pd.Timestamp.now(tz=SHANGHAI_TZ)


def previous_bday(now: pd.Timestamp | None = None) -> pd.Timestamp:
    """Previous trading day approximation based on Asia/Shanghai workdays."""
    base = (now or now_shanghai()).tz_localize(None).normalize() - pd.Timedelta(days=1)
    while base.weekday() >= 5:
        base -= pd.Timedelta(days=1)
    return base


def previous_completed_week(now: pd.Timestamp | None = None) -> pd.Timestamp:
    """Previous Sunday, used as the label for the latest completed trading week."""
    today = (now or now_shanghai()).tz_localize(None).normalize()
    return today - pd.Timedelta(days=today.weekday() + 1)


def macro_release_window_due(now: pd.Timestamp | None = None) -> bool:
    """Run macro updates at 06:00 on the day after likely official release days."""
    local_now = now or now_shanghai()
    release_day = (local_now.tz_localize(None).normalize() - pd.Timedelta(days=1)).day
    return release_day in MACRO_RELEASE_DAYS


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
    except Exception:
        return None


def dataset_state(output_names: list[str], expected: pd.Timestamp) -> dict:
    dates = {name: csv_max_date(PROCESSED_DIR / name) for name in output_names}
    serializable = {
        name: (None if value is None or pd.isna(value) else value.strftime("%Y-%m-%d"))
        for name, value in dates.items()
    }
    fresh = bool(dates) and all(value is not None and not pd.isna(value) and value >= expected for value in dates.values())
    return {"fresh": fresh, "outputs": serializable}


def macro_fresh(metadata_name: str) -> bool:
    path = PROCESSED_DIR / metadata_name
    if not path.exists():
        return False
    age_h = (time.time() - path.stat().st_mtime) / 3600
    return age_h < MACRO_MIN_INTERVAL_H


def run_script(name: str, extra_args: list[str] | None = None) -> dict:
    extra_args = extra_args or []
    print(f"[run] {name} {' '.join(extra_args)}".rstrip(), flush=True)
    started = datetime.now().isoformat(timespec="seconds")
    try:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / name), *extra_args],
            cwd=RUN_CWD,
            timeout=SCRIPT_TIMEOUT_SECONDS,
        )
        returncode = proc.returncode
        status = "ok" if returncode == 0 else "failed"
        if returncode != 0:
            print(f"[warn] {name} exited {returncode} (continuing)", flush=True)
    except subprocess.TimeoutExpired:
        returncode = 124
        status = "timeout"
        print(f"[warn] {name} timed out after {SCRIPT_TIMEOUT_SECONDS}s (continuing)", flush=True)
    return {
        "script": name,
        "status": status,
        "returncode": returncode,
        "started_at": started,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    }


def write_audit(summary: dict) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["scheduled", "daily", "weekly", "macro", "all"], required=True)
    args = parser.parse_args()

    local_now = now_shanghai()
    expected = previous_bday(local_now)
    expected_weekly = previous_completed_week(local_now)
    modes: set[str]
    if args.mode == "scheduled":
        modes = {"daily", "weekly"}
        if macro_release_window_due(local_now):
            modes.add("macro")
    elif args.mode == "all":
        modes = {"daily", "weekly", "macro"}
    else:
        modes = {args.mode}

    ran: list[dict] = []
    skipped: list[dict] = []

    if "daily" in modes:
        for script, outputs in DAILY_DATASETS.items():
            state = dataset_state(outputs, expected)
            if args.mode not in {"all"} and state["fresh"]:
                skipped.append({"script": script, "reason": "fresh", **state})
                continue
            if script in LOCAL_WIND_DATASETS and not WIND_CLI.exists():
                skipped.append({"script": script, "reason": "local_wind_unavailable", **state})
                continue
            ran.append(run_script(script))

    if "weekly" in modes:
        weekly_latest = csv_max_date(WEEKLY_CITIC_INPUT)
        weekly_fresh = bool(
            weekly_latest is not None
            and not pd.isna(weekly_latest)
            and weekly_latest >= expected_weekly
        )
        weekly_state = {
            "fresh": weekly_fresh,
            "outputs": {
                str(WEEKLY_CITIC_INPUT.relative_to(ROOT)): (
                    None if weekly_latest is None or pd.isna(weekly_latest) else weekly_latest.strftime("%Y-%m-%d")
                )
            },
        }
        if args.mode != "all" and weekly_fresh:
            skipped.append({"script": "weekly_citic_pipeline", "reason": "fresh", **weekly_state})
        elif not WIND_CLI.exists():
            skipped.append({"script": "weekly_citic_pipeline", "reason": "local_wind_unavailable", **weekly_state})
        else:
            for script, extra_args in WEEKLY_CITIC_PIPELINE:
                result = run_script(script, extra_args)
                ran.append(result)
                if result["status"] != "ok":
                    break

    if "macro" in modes:
        for script, metadata_name in MACRO_DATASETS.items():
            if args.mode != "all" and macro_fresh(metadata_name):
                skipped.append({"script": script, "reason": "recently_attempted", "metadata": metadata_name})
                continue
            ran.append(run_script(script))

    build_result = None
    if ran:
        build_result = run_script("build_site_from_processed.py")

    summary = {
        "mode": args.mode,
        "effective_modes": sorted(modes),
        "checked_at": local_now.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "expected_latest_daily": expected.strftime("%Y-%m-%d"),
        "expected_latest_weekly": expected_weekly.strftime("%Y-%m-%d"),
        "ran": ran,
        "skipped": skipped,
        "rebuilt": bool(build_result),
        "build": build_result,
        "notes": [
            "GitHub Actions 环境无本地 Wind 授权；依赖 Wind 的周频指标应由本地任务或手动刷新补充后提交。",
            "GitHub Actions 环境通常无本地 Wind 金融能力；依赖 Wind 的港股与情绪指标在缺少脚本时跳过，避免无效失败。",
            "价值成长价差、中信 PB 离散度与风格收益改用本地 Wind 金融能力；GitHub Actions 缺少该能力时跳过。",
            "中信行业周频底表按最近完整周的周日标签判断新鲜度；缺失时依次刷新底表、拥挤度与 PB 离散度。",
            "宏观数据在统计局/央行常见发布窗口的次日 06:00 尝试更新；若官方未发布或接口延迟，会保留上一期数据。",
        ],
    }
    if ran or build_result:
        write_audit(summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    if build_result and build_result.get("status") != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
