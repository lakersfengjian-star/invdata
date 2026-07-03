#!/usr/bin/env python3
"""GitHub Pages bootstrap for the investment dashboard builder.

The full builder is stored in small UTF-8 parts so it can be uploaded and
maintained through text-only repository writes. At runtime this file reassembles
and executes the original script.
"""
from pathlib import Path

parts_dir = Path(__file__).resolve().parent / "ci_parts"
parts = sorted(parts_dir.glob("update_etf_dashboard.py.part*"))
if not parts:
    raise SystemExit(f"No dashboard builder parts found in {parts_dir}")

source = "".join(part.read_text(encoding="utf-8") for part in parts)
exec_globals = {"__name__": "__main__", "__file__": __file__}
exec(compile(source, __file__, "exec"), exec_globals)
