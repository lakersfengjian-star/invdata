#!/usr/bin/env python3
"""GitHub Pages bootstrap for the investment dashboard builder.

The full builder is stored in small UTF-8 parts. This bootstrap reassembles the
builder and applies the current Pages fixes before execution.
"""
from pathlib import Path

parts_dir = Path(__file__).resolve().parent / "ci_parts"
parts = sorted(parts_dir.glob("update_etf_dashboard.py.part*"))
if not parts:
    raise SystemExit(f"No dashboard builder parts found in {parts_dir}")

source = "".join(part.read_text(encoding="utf-8") for part in parts)

# Runtime patches keep the remote chunked builder aligned with the local source
# without repeatedly uploading large text chunks through the connector.
source = source.replace("import os\nimport sys", "import os\nimport shutil\nimport sys", 1)
source = source.replace(
    '''    ax1.plot(x, plot_df["top10_share_pct"], color="#c5513c", linewidth=2.4, label="前10大占比")
    ax1.plot(x, plot_df["top100_share_pct"], color="#2f7cb8", linewidth=2.1, label="前100大占比")
    ax2.plot(x, plot_df["上证指数"], color="#7a6f64", linewidth=1.8, alpha=0.75, label="上证指数")

    ax1.set_title("A股成交额前10大公司交易集中度变化（2026年初至今）", loc="left", fontsize=18, fontweight="bold", pad=16)''',
    '''    latest = plot_df.dropna(subset=["top10_share_pct"]).iloc[-1]
    latest_date = latest["date"].strftime("%Y-%m-%d")

    ax1.plot(x, plot_df["top10_share_pct"], color="#c5513c", linewidth=2.4, label="前10大占比")
    ax1.plot(x, plot_df["top100_share_pct"], color="#2f7cb8", linewidth=2.1, label="前100大占比")
    ax2.plot(x, plot_df["上证指数"], color="#7a6f64", linewidth=1.8, alpha=0.75, label="上证指数")

    ax1.set_title(f"A股成交额前10大公司交易集中度变化（截至{latest_date}）", loc="left", fontsize=18, fontweight="bold", pad=16)''',
    1,
)
source = source.replace(
    '''    latest = plot_df.iloc[-1]
    ax.annotate(''',
    '''    latest = plot_df.iloc[-1]
    latest_date = latest["date"].strftime("%Y-%m-%d")
    ax.annotate(''',
    1,
)
source = source.replace(
    '''    ax.set_title(f"{index_name}历史滚动市盈率及标准差通道", loc="left", fontsize=18, fontweight="bold", pad=16)''',
    '''    ax.set_title(f"{index_name}历史滚动市盈率及标准差通道（截至{latest_date}）", loc="left", fontsize=18, fontweight="bold", pad=16)''',
    1,
)
source = source.replace(
    '''        info["title"] = f"图四：{cfg['name']}历史滚动市盈率及标准差通道"''',
    '''        info["title"] = f"图四：{cfg['name']}历史滚动市盈率及标准差通道（截至{info['last_date']}）"''',
    1,
)
source = source.replace(
    '''def build_page(metadata: dict[str, Any]) -> None:
    chart1 = "../output/charts/fig_001_broad_etf_flow.png"
    chart2 = "../output/charts/fig_002_star50_etf_flow.png"
    chart3 = "../output/charts/fig_003_a_share_turnover_concentration.png"
    updated_at = metadata["updated_at"]
    latest = metadata["latest_common_date"]
    source_notes = "<br>".join(metadata["notes"])
    valuation_sections = []''',
    '''def build_page(metadata: dict[str, Any]) -> None:
    assets_dir = SITE_DIR / "assets" / "charts"
    assets_dir.mkdir(parents=True, exist_ok=True)
    for chart_file in CHART_DIR.glob("*.png"):
        shutil.copy2(chart_file, assets_dir / chart_file.name)

    chart1 = "assets/charts/fig_001_broad_etf_flow.png"
    chart2 = "assets/charts/fig_002_star50_etf_flow.png"
    chart3 = "assets/charts/fig_003_a_share_turnover_concentration.png"
    updated_at = metadata["updated_at"]
    latest = metadata["latest_common_date"]
    source_notes = "<br>".join(metadata["notes"])
    chart3_info = metadata.get("chart_files", [{}, {}, {}])[2] if len(metadata.get("chart_files", [])) >= 3 else {}
    chart3_date = chart3_info.get("last_date", "最新")
    valuation_sections = []''',
    1,
)
source = source.replace('''        rel = "../" + chart["path"]''', '''        rel = "assets/charts/" + Path(chart["path"]).name''', 1)
source = source.replace(
    '''      <h2>图三：A股成交额前10大公司交易集中度变化</h2>''',
    '''      <h2>图三：A股成交额前10大公司交易集中度变化（截至{chart3_date}）</h2>''',
    1,
)

exec_globals = {"__name__": "__main__", "__file__": __file__}
exec(compile(source, __file__, "exec"), exec_globals)
