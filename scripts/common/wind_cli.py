"""Portable helpers for cached Wind AIFin CLI calls."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = Path(
    os.environ.get("WIND_SKILL_DIR", Path.home() / ".agents" / "skills" / "wind-mcp-skill")
).expanduser()
CLI = SKILL_DIR / "scripts" / "cli.mjs"
CACHE_DIR = ROOT / ".work" / "cache" / "wind_metrics"


def node_bin() -> str:
    configured = os.environ.get("WIND_NODE")
    candidates = [
        configured,
        shutil.which("node"),
        str(Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "node" / "bin" / "node"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise FileNotFoundError("Node.js not found; set WIND_NODE to the node executable")


def call(server: str, tool: str, params: dict, timeout: int = 180) -> dict:
    if not CLI.exists():
        raise FileNotFoundError(f"Wind CLI not found: {CLI}")
    proc = subprocess.run(
        [node_bin(), str(CLI), "call", server, tool, json.dumps(params, ensure_ascii=False)],
        cwd=SKILL_DIR,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Wind CLI exit {proc.returncode}: {proc.stdout[:500]} {proc.stderr[:300]}")
    outer = json.loads(proc.stdout)
    if outer.get("isError"):
        raise RuntimeError(f"Wind CLI error: {proc.stdout[:500]}")
    content_text = outer.get("content", [{}])[0].get("text", "")
    try:
        inner = json.loads(content_text)
    except json.JSONDecodeError:
        if content_text.strip() in {"没找到数据", "暂无数据", "无数据"}:
            return {"data": {"data": []}, "message": content_text.strip()}
        raise RuntimeError(f"Unexpected Wind response: {content_text[:500]}")
    if inner.get("error"):
        raise RuntimeError(f"Wind error: {json.dumps(inner['error'], ensure_ascii=False)[:500]}")
    return inner


def cached_call(cache_key: str, server: str, tool: str, params: dict) -> dict:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{cache_key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    payload = call(server, tool, params)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return payload


def year_chunks(start: str, end: str | None = None) -> list[tuple[str, str]]:
    finish = end or date.today().strftime("%Y%m%d")
    start_dt = datetime.strptime(start, "%Y%m%d")
    end_dt = datetime.strptime(finish, "%Y%m%d")
    chunks: list[tuple[str, str]] = []
    for year in range(start_dt.year, end_dt.year + 1):
        begin = max(start_dt, datetime(year, 1, 1))
        stop = min(end_dt, datetime(year, 12, 31))
        chunks.append((begin.strftime("%Y%m%d"), stop.strftime("%Y%m%d")))
    return chunks


def date_chunks(start: str, end: str | None = None, days: int = 120) -> list[tuple[str, str]]:
    """Split a range into bounded inclusive chunks for row-limited NL queries."""
    finish = datetime.strptime(end or date.today().strftime("%Y%m%d"), "%Y%m%d")
    cursor = datetime.strptime(start, "%Y%m%d")
    chunks: list[tuple[str, str]] = []
    while cursor <= finish:
        stop = min(cursor + timedelta(days=days - 1), finish)
        chunks.append((cursor.strftime("%Y%m%d"), stop.strftime("%Y%m%d")))
        cursor = stop + timedelta(days=1)
    return chunks


def cn_date(value: str) -> str:
    return f"{value[:4]}年{int(value[4:6])}月{int(value[6:8])}日"


def parse_nl_series(payload: dict, value_hint: str) -> list[dict]:
    records: list[dict] = []
    for block in payload.get("data", {}).get("data", []):
        columns = [col["name"] for col in block.get("columns", [])]
        value_idx = next((i for i, name in enumerate(columns) if value_hint in name and "时间" not in name), None)
        date_idx = next((i for i, name in enumerate(columns) if "时间" in name or name == "日期"), None)
        if value_idx is None or date_idx is None:
            continue
        for row in block.get("rows", []):
            records.append({"date": row[date_idx], "value": row[value_idx]})
    return records


def parse_kline(payload: dict) -> list[dict]:
    data = payload.get("data", {})
    columns = [col["name"] for col in data.get("columns", [])]
    if "TIME" not in columns or "MATCH" not in columns:
        return []
    time_idx = columns.index("TIME")
    close_idx = columns.index("MATCH")
    return [{"date": row[time_idx], "close": row[close_idx]} for row in data.get("rows", [])]
