"""Small iFinD MCP adapter used only as a fallback source."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pandas as pd

IFIND_SKILL_DIR = Path(
    os.environ.get("IFIND_SKILL_DIR", Path.home() / ".agents" / "skills" / "ifind-finance-data")
).expanduser()


def _load_call():
    module_path = IFIND_SKILL_DIR / "call.py"
    if not module_path.exists():
        raise FileNotFoundError(f"iFinD skill not found: {module_path}")
    spec = importlib.util.spec_from_file_location("invdata_ifind_call", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load iFinD client: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.call


def get_edb_table(query: str) -> tuple[pd.DataFrame, dict]:
    """Return the first successful standard table from iFinD EDB."""
    result = _load_call()("edb", "get_edb_data", {"query": query})
    if not result.get("ok"):
        raise RuntimeError(f"iFinD transport failed: {result.get('status_code')}")
    content = result.get("data", {}).get("result", {}).get("content", [])
    if not content:
        raise RuntimeError("iFinD returned no content")
    payload = json.loads(content[0]["text"])
    if payload.get("code") != 1:
        raise RuntimeError(f"iFinD EDB failed: {payload.get('msg')}")
    for item in payload.get("data", {}).get("datas", []):
        table = item.get("data", {})
        if item.get("success") and table.get("is_standard_table"):
            frame = pd.DataFrame(table.get("data", []), columns=table.get("columns", []))
            return frame, table.get("attrs", {})
    raise RuntimeError("iFinD returned no standard EDB table")


def find_column(columns, *needles: str) -> str:
    for column in columns:
        normalized = str(column).replace(" ", "")
        if all(needle in normalized for needle in needles):
            return str(column)
    raise KeyError(f"iFinD column not found: {needles}")
