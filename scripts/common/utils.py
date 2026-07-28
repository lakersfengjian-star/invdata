"""Common utilities shared across update scripts."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from . import config

# ------------------------------------------------------------------ paths ---
VENDOR = config.ROOT / ".work" / "vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

# ------------------------------------------------------------------ fonts ---
def setup_fonts() -> None:
    try:
        import matplotlib.font_manager as fm
    except Exception:
        return
    preferred = [
        "Noto Sans CJK SC",
        "Noto Sans CJK JP",
        "Microsoft YaHei",
        "SimHei",
        "PingFang SC",
        "Heiti SC",
        "Arial Unicode MS",
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    for name in preferred:
        if name in available:
            import matplotlib
            matplotlib.rcParams["font.family"] = "sans-serif"
            matplotlib.rcParams["font.sans-serif"] = [name]
            break
    matplotlib.rcParams["axes.unicode_minus"] = False


# ------------------------------------------------------------------ dates ---
def previous_bday() -> pd.Timestamp:
    d = pd.Timestamp.now(tz="Asia/Shanghai").tz_localize(None).normalize() - pd.Timedelta(days=1)
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
    except Exception:
        return None


def dataset_fresh(csv_names: list[str], expected: pd.Timestamp, processed_dir: Path | None = None) -> bool:
    """Return True if all named CSVs (or metadata JSONs) cover `expected` date."""
    base = processed_dir or config.PROCESSED_DIR
    dates = [csv_max_date(base / name) for name in csv_names]
    if any(d is None or pd.isna(d) for d in dates):
        return False
    return min(dates) >= expected  # type: ignore[operator]


# ------------------------------------------------------------------ source log ---
@dataclass
class SourceLog:
    source: str
    status: str
    detail: str


SOURCE_LOGS: list[SourceLog] = []


def log_source(source: str, status: str, detail: str) -> None:
    SOURCE_LOGS.append(SourceLog(source, status, detail))


def clear_source_logs() -> None:
    SOURCE_LOGS.clear()


# ------------------------------------------------------------------ metadata ---
def write_metadata(
    path: Path,
    *,
    source: str,
    status: str,
    latest_date: str,
    unit: str = "",
    notes: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Write a standardised metadata JSON."""
    payload: dict[str, Any] = {
        "source": source,
        "status": status,
        "latest_date": latest_date,
        "unit": unit,
        "notes": notes or [],
    }
    if extra:
        payload.update(extra)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


# ------------------------------------------------------------------ dirs ---
def ensure_dirs() -> None:
    for path in [config.RAW_DIR, config.PROCESSED_DIR, config.CHART_DIR, config.SITE_DIR, config.CACHE_DIR]:
        path.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------------ env ---
def load_env_file() -> None:
    env_path = config.ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


# ------------------------------------------------------------------ http ---
def http_get(url: str, params: dict | None = None, timeout: int = 25, headers: dict | None = None) -> str:
    import requests
    hdrs = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126.0 Safari/537.36",
        **(headers or {}),
    }
    for trust_env in (True, False):
        try:
            session = requests.Session()
            session.trust_env = trust_env
            resp = session.get(url, params=params, headers=hdrs, timeout=timeout)
            resp.raise_for_status()
            return resp.text
        except Exception:
            continue
    raise RuntimeError(f"http_get failed for {url}")
