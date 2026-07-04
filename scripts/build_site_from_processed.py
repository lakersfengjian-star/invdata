#!/usr/bin/env python3
"""Build the static site from processed CSV snapshots."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / ".work" / "vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import FuncFormatter


PROCESSED_DIR = ROOT / "data" / "processed"
CHART_DIR = ROOT / "output" / "charts"
SITE_DIR = ROOT / "site"
VALUATION_START_DATE = "2020-01-01"


def setup_fonts() -> None:
    preferred = ["Microsoft YaHei", "SimHei", "PingFang SC", "Noto Sans CJK SC", "Arial Unicode MS"]
    available = {f.name for f in fm.fontManager.ttflist}
    for name in preferred:
        if name in available:
            plt.rcParams["font.sans-serif"] = [name]
            break
    plt.rcParams["axes.unicode_minus"] = False


def fmt_num(value: float, digits: int = 2) -> str:
    if pd.isna(value):
        return "NA"
    return f"{value:,.{digits}f}"


def y_100mn(x: float, _pos: int) -> str:
    return f"{x/1000:.1f}k" if abs(x) >= 1000 else f"{x:.0f}"


def pct_formatter(x: float, _pos: int) -> str:
    return f"{x:.0f}%"


def draw_combo_chart(df: pd.DataFrame, line_cols: list[tuple[str, str, str]], title: str, out_path: Path) -> dict:
    setup_fonts()
    plot_df = df.copy().sort_values("date")
    plot_df["date"] = pd.to_datetime(plot_df["date"])
    x = plot_df["date"]
    fig, ax1 = plt.subplots(figsize=(16, 8), dpi=180)
    fig.patch.set_facecolor("#fbfbf8")
    ax1.set_facecolor("#fbfbf8")
    ax2 = ax1.twinx()
    ax2.bar(x, plot_df["daily_net_inflow_100mn"], width=0.82, color="#a9c4d8", alpha=0.55, label="当日净流入")
    ax2.fill_between(
        x,
        plot_df["rolling_7d_net_inflow_100mn"].astype(float).to_numpy(),
        0,
        color="#d28b72",
        alpha=0.24,
        label="7日滚动合计净流入",
        linewidth=0,
    )
    ax2.plot(x, plot_df["rolling_7d_net_inflow_100mn"], color="#b8664f", linewidth=1.6, alpha=0.9)
    for col, label, color in line_cols:
        ax1.plot(x, plot_df[col], label=label, color=color, linewidth=2.2)
    ax1.set_title(title, loc="left", fontsize=19, fontweight="bold", pad=16)
    ax1.set_ylabel("收盘价（点）", fontsize=12)
    ax2.set_ylabel("净流入额（亿元）", fontsize=12)
    ax2.yaxis.set_major_formatter(FuncFormatter(y_100mn))
    ax1.grid(axis="y", color="#d8d8d8", linewidth=0.8, alpha=0.65)
    ax1.grid(axis="x", color="#eeeeee", linewidth=0.5, alpha=0.45)
    ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax1.set_xlim(plot_df["date"].min(), plot_df["date"].max() + pd.Timedelta(days=12))
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", ncol=4, frameon=False, fontsize=10)
    latest = plot_df.dropna(subset=["daily_net_inflow_100mn"]).iloc[-1]
    text_lines = [latest["date"].strftime("%Y-%m-%d")]
    for col, label, _color in line_cols:
        text_lines.append(f"{label}: {fmt_num(latest[col], 2)}")
    text_lines.append(f"当日净流入: {fmt_num(latest['daily_net_inflow_100mn'], 2)} 亿元")
    text_lines.append(f"7日滚动: {fmt_num(latest['rolling_7d_net_inflow_100mn'], 2)} 亿元")
    ax1.text(
        0.985,
        0.965,
        "\n".join(text_lines),
        transform=ax1.transAxes,
        ha="right",
        va="top",
        fontsize=10.5,
        bbox={"boxstyle": "round,pad=0.45", "facecolor": "#ffffff", "edgecolor": "#d0d0d0", "alpha": 0.9},
    )
    ax1.spines[["top", "right"]].set_visible(False)
    ax2.spines[["top", "left"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return {"path": str(out_path.relative_to(ROOT)), "last_date": latest["date"].strftime("%Y-%m-%d")}


def draw_turnover_chart(df: pd.DataFrame, out_path: Path) -> dict:
    setup_fonts()
    plot_df = df.copy().sort_values("date")
    plot_df["date"] = pd.to_datetime(plot_df["date"])
    x = plot_df["date"]
    latest = plot_df.dropna(subset=["top10_share_pct"]).iloc[-1]
    latest_date = latest["date"].strftime("%Y-%m-%d")
    fig, ax1 = plt.subplots(figsize=(16, 8), dpi=180)
    fig.patch.set_facecolor("#fbfbf8")
    ax1.set_facecolor("#fbfbf8")
    ax2 = ax1.twinx()
    ax1.plot(x, plot_df["top10_share_pct"], color="#c5513c", linewidth=2.4, label="前10大占比")
    ax1.plot(x, plot_df["top100_share_pct"], color="#2f7cb8", linewidth=2.1, label="前100大占比")
    ax2.plot(x, plot_df["上证指数"], color="#7a6f64", linewidth=1.8, alpha=0.75, label="上证指数")
    ax1.set_title(f"A股成交额前10大公司交易集中度变化（截至{latest_date}）", loc="left", fontsize=18, fontweight="bold", pad=16)
    ax1.set_xlabel("日期", fontsize=12)
    ax1.set_ylabel("占全市场成交额比例（%）", fontsize=12)
    ax2.set_ylabel("上证指数收盘价（点）", fontsize=12)
    ax1.yaxis.set_major_formatter(FuncFormatter(pct_formatter))
    ax1.grid(axis="y", color="#d8d8d8", linewidth=0.8, alpha=0.65)
    ax1.grid(axis="x", color="#eeeeee", linewidth=0.5, alpha=0.45)
    ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax1.set_xlim(plot_df["date"].min(), plot_df["date"].max() + pd.Timedelta(days=8))
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", ncol=4, frameon=False, fontsize=10)
    ax1.annotate(
        f"{latest['top10_share_pct']:.2f}%",
        xy=(latest["date"], latest["top10_share_pct"]),
        xytext=(12, 0),
        textcoords="offset points",
        va="center",
        fontsize=11,
        color="#c5513c",
        bbox={"boxstyle": "round,pad=0.25", "facecolor": "#ffffff", "edgecolor": "#e2c1b9", "alpha": 0.9},
    )
    ax1.spines[["top", "right"]].set_visible(False)
    ax2.spines[["top", "left"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return {"path": str(out_path.relative_to(ROOT)), "last_date": latest_date}


def draw_valuation_chart(df: pd.DataFrame, index_name: str, out_path: Path) -> dict:
    setup_fonts()
    plot_df = df[df["index_name"].eq(index_name)].copy().sort_values("date")
    plot_df["date"] = pd.to_datetime(plot_df["date"])
    mu = plot_df["pe_ttm"].mean()
    sigma = plot_df["pe_ttm"].std(ddof=0)
    latest = plot_df.iloc[-1]
    latest_date = latest["date"].strftime("%Y-%m-%d")
    fig, ax = plt.subplots(figsize=(16, 7.2), dpi=180)
    fig.patch.set_facecolor("#fbfbf8")
    ax.set_facecolor("#fbfbf8")
    ax.plot(plot_df["date"], plot_df["pe_ttm"], color="#1f77b4", linewidth=2.2, label="PE_TTM")
    for label, value, color, width in [
        ("均值", mu, "#34495e", 1.8),
        ("μ + 1σ", mu + sigma, "#2f7cb8", 1.3),
        ("μ - 1σ", mu - sigma, "#2f7cb8", 1.3),
        ("μ + 2σ", mu + 2 * sigma, "#c5513c", 1.2),
        ("μ - 2σ", mu - 2 * sigma, "#c5513c", 1.2),
    ]:
        ax.axhline(value, linestyle="--", color=color, linewidth=width, alpha=0.9, label=f"{label}: {value:.2f}")
    ax.annotate(f"{latest['pe_ttm']:.2f}x", xy=(latest["date"], latest["pe_ttm"]), xytext=(12, 0), textcoords="offset points", va="center", fontsize=11, color="#1f77b4")
    ax.set_title(f"{index_name}历史滚动市盈率及标准差通道（截至{latest_date}）", loc="left", fontsize=18, fontweight="bold", pad=16)
    ax.set_xlabel("日期", fontsize=12)
    ax.set_ylabel("滚动市盈率（倍）", fontsize=12)
    ax.grid(axis="y", color="#d8d8d8", linewidth=0.8, alpha=0.65)
    ax.grid(axis="x", color="#eeeeee", linewidth=0.5, alpha=0.45)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.legend(loc="upper left", ncol=3, frameon=False, fontsize=9.5)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return {"path": str(out_path.relative_to(ROOT)), "last_date": latest_date, "title": f"图四：{index_name}历史滚动市盈率及标准差通道（截至{latest_date}）"}


def build_page(metadata: dict, chart3: dict, valuation_charts: list[dict]) -> None:
    assets_dir = SITE_DIR / "assets" / "charts"
    assets_dir.mkdir(parents=True, exist_ok=True)
    for chart_file in CHART_DIR.glob("*.png"):
        shutil.copy2(chart_file, assets_dir / chart_file.name)
    latest = metadata["latest_common_date"]
    updated_at = metadata["updated_at"]
    notes = "<br>".join(metadata.get("notes", []))
    valuation_html = "\n\n".join(
        f'''    <section class="chart-section">
      <h2>{chart["title"]}</h2>
      <img src="assets/charts/{Path(chart["path"]).name}" alt="{chart["title"]}">
      <p class="note">统计区间自 {VALUATION_START_DATE} 起；水平虚线分别为均值、均值±1倍标准差、均值±2倍标准差。</p>
    </section>'''
        for chart in valuation_charts
    )
    html = f'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>投研数据页：ETF资金流与指数走势</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <main>
    <header class="page-head">
      <div><p class="eyebrow">ETF Flow Monitor</p><h1>ETF资金流与指数走势</h1></div>
      <div class="meta"><div>更新：{updated_at}</div><div>区间：2025-01-01 至 {latest}</div></div>
    </header>
    <section class="chart-section">
      <h2>图一：沪深300/上证指数 vs. 大宽基ETF资金流</h2>
      <img src="assets/charts/fig_001_broad_etf_flow.png" alt="沪深300与上证指数走势及大宽基ETF资金流">
      <p class="note">样本：510300、510310、510330、159919、510050。净流入口径为份额变化乘以单位净值；7日滚动合计按交易日滚动计算。</p>
    </section>
    <section class="chart-section">
      <h2>图二：科创50指数 vs. 科创50ETF资金流</h2>
      <img src="assets/charts/fig_002_star50_etf_flow.png" alt="科创50指数走势及科创50ETF资金流">
      <p class="note">样本：588000 华夏科创50ETF。净流入口径为份额变化乘以单位净值；7日滚动合计按交易日滚动计算。</p>
    </section>
    <section class="chart-section">
      <h2>图三：A股成交额前10大公司交易集中度变化（截至{chart3["last_date"]}）</h2>
      <img src="assets/charts/fig_003_a_share_turnover_concentration.png" alt="A股成交额前10大公司交易集中度变化">
      <p class="note">样本覆盖当前沪深京A股清单；逐日计算前10、前100成交额占比。右轴为上证指数收盘价。</p>
    </section>
{valuation_html}
    <section class="data-note">
      <h2>数据说明与风险提示</h2>
      <p>{notes}</p>
      <p>当日净流入为 0 或长时间缺失时，可能代表 ETF 份额未更新、接口未披露或数据源暂不可用，不应机械解读为真实无申赎。</p>
    </section>
  </main>
</body>
</html>
'''
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    (SITE_DIR / "index.html").write_text(html, encoding="utf-8")


def main() -> None:
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    metadata = json.loads((PROCESSED_DIR / "metadata.json").read_text(encoding="utf-8"))
    indices = pd.read_csv(PROCESSED_DIR / "index_close.csv", parse_dates=["date"])
    broad = pd.read_csv(PROCESSED_DIR / "broad_etf_flow.csv", parse_dates=["date"])
    star = pd.read_csv(PROCESSED_DIR / "star50_etf_flow.csv", parse_dates=["date"])
    turnover = pd.read_csv(PROCESSED_DIR / "a_share_turnover_concentration.csv", parse_dates=["date"])
    valuation = pd.read_csv(PROCESSED_DIR / "index_pe_ttm_valuation.csv", parse_dates=["date"])
    draw_combo_chart(indices[["date", "沪深300", "上证指数"]].merge(broad, on="date", how="left"), [("沪深300", "沪深300", "#1f77b4"), ("上证指数", "上证指数", "#2a9d55")], "沪深300与上证指数走势及大宽基ETF资金流", CHART_DIR / "fig_001_broad_etf_flow.png")
    draw_combo_chart(indices[["date", "科创50"]].merge(star, on="date", how="left"), [("科创50", "科创50", "#7b4ab8")], "科创50指数走势及科创50ETF资金流", CHART_DIR / "fig_002_star50_etf_flow.png")
    chart3 = draw_turnover_chart(turnover, CHART_DIR / "fig_003_a_share_turnover_concentration.png")
    valuation_charts = [
        draw_valuation_chart(valuation, "沪深300指数", CHART_DIR / "fig_004a_hs300_pe_ttm_channel.png"),
        draw_valuation_chart(valuation, "上证指数", CHART_DIR / "fig_004b_sse_pe_ttm_channel.png"),
    ]
    build_page(metadata, chart3, valuation_charts)
    print(json.dumps({"latest_common_date": metadata["latest_common_date"], "charts": 5}, ensure_ascii=False))


if __name__ == "__main__":
    main()
