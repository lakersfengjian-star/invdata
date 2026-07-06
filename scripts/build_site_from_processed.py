#!/usr/bin/env python3
"""Build the static site from processed CSV snapshots."""

from __future__ import annotations

import json
import os
import shutil
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".work" / "cache" / "matplotlib"))
VENDOR = ROOT / ".work" / "vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.font_manager as fm
import math
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import FuncFormatter


PROCESSED_DIR = ROOT / "data" / "processed"
CHART_DIR = ROOT / "output" / "charts"
SITE_DIR = ROOT / "site"
VALUATION_START_DATE = "2020-01-01"


def setup_fonts() -> None:
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
            plt.rcParams["font.family"] = "sans-serif"
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


def draw_index_amount_share_chart(df: pd.DataFrame, out_path: Path) -> dict:
    setup_fonts()
    plot_df = df.copy().sort_values("date")
    plot_df["date"] = pd.to_datetime(plot_df["date"])
    latest = plot_df.dropna(subset=["hs300_share_pct", "csi500_share_pct", "csi1000_share_pct"], how="all").iloc[-1]
    latest_date = latest["date"].strftime("%Y-%m-%d")
    fig, ax = plt.subplots(figsize=(16, 7.6), dpi=180)
    fig.patch.set_facecolor("#fbfbf8")
    ax.set_facecolor("#fbfbf8")
    series = [
        ("hs300_share_pct", "沪深300", "#1f77b4"),
        ("csi500_share_pct", "中证500", "#2a9d55"),
        ("csi1000_share_pct", "中证1000", "#c5513c"),
        ("csi2000_share_pct", "中证2000", "#7b4ab8"),
    ]
    for col, label, color in series:
        if col in plot_df and plot_df[col].notna().any():
            ax.plot(plot_df["date"], plot_df[col], label=label, color=color, linewidth=2.1)
            value = latest.get(col)
            if pd.notna(value):
                ax.annotate(f"{latest_date}  {value:.1f}%", xy=(latest["date"], value), xytext=(10, 0), textcoords="offset points", va="center", fontsize=9.5, color=color)
    ax.set_title(f"主要宽基指数成交额占全A成交额比例（截至{latest_date}）", loc="left", fontsize=18, fontweight="bold", pad=16)
    ax.set_xlabel("日期", fontsize=12)
    ax.set_ylabel("占全A成交额比例（%）", fontsize=12)
    ax.yaxis.set_major_formatter(FuncFormatter(pct_formatter))
    ax.grid(axis="y", color="#d8d8d8", linewidth=0.8, alpha=0.65)
    ax.grid(axis="x", color="#eeeeee", linewidth=0.5, alpha=0.45)
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.set_xlim(plot_df["date"].min(), plot_df["date"].max() + pd.Timedelta(days=18))
    ax.legend(loc="upper left", ncol=4, frameon=False, fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return {"path": str(out_path.relative_to(ROOT)), "last_date": latest_date}


def draw_theme_amount_share_chart(df: pd.DataFrame, out_path: Path) -> dict:
    setup_fonts()
    plot_df = df.copy().sort_values("date")
    plot_df["date"] = pd.to_datetime(plot_df["date"])
    latest = plot_df.dropna(subset=["tmt_share_pct", "dividend_low_vol_share_pct"], how="all").iloc[-1]
    latest_date = latest["date"].strftime("%Y-%m-%d")
    fig, ax = plt.subplots(figsize=(16, 7.2), dpi=180)
    fig.patch.set_facecolor("#fbfbf8")
    ax.set_facecolor("#fbfbf8")
    ax2 = ax.twinx()
    if "tmt_share_pct" in plot_df and plot_df["tmt_share_pct"].notna().any():
        ax.plot(plot_df["date"], plot_df["tmt_share_pct"], label="中证TMT", color="#1f77b4", linewidth=2.25)
        value = latest.get("tmt_share_pct")
        if pd.notna(value):
            ax.annotate(f"{latest_date}  {value:.1f}%", xy=(latest["date"], value), xytext=(10, 0), textcoords="offset points", va="center", fontsize=10, color="#1f77b4")
    if "dividend_low_vol_share_pct" in plot_df and plot_df["dividend_low_vol_share_pct"].notna().any():
        ax2.plot(plot_df["date"], plot_df["dividend_low_vol_share_pct"], label="红利低波", color="#c5513c", linewidth=2.25)
        value = latest.get("dividend_low_vol_share_pct")
        if pd.notna(value):
            ax2.annotate(f"{latest_date}  {value:.1f}%", xy=(latest["date"], value), xytext=(10, 0), textcoords="offset points", va="center", fontsize=10, color="#c5513c")
    ax.set_title(f"TMT与红利低波成交额占全A成交额比例（截至{latest_date}）", loc="left", fontsize=18, fontweight="bold", pad=16)
    ax.set_xlabel("日期", fontsize=12)
    ax.set_ylabel("中证TMT占比（%）", fontsize=12)
    ax2.set_ylabel("红利低波占比（%）", fontsize=12)
    ax.yaxis.set_major_formatter(FuncFormatter(pct_formatter))
    ax2.yaxis.set_major_formatter(FuncFormatter(lambda x, _pos: f"{x:.1f}%"))
    ax.grid(axis="y", color="#d8d8d8", linewidth=0.8, alpha=0.65)
    ax.grid(axis="x", color="#eeeeee", linewidth=0.5, alpha=0.45)
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.set_xlim(plot_df["date"].min(), plot_df["date"].max() + pd.Timedelta(days=18))
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, loc="upper left", ncol=2, frameon=False, fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    ax2.spines[["top", "left"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return {"path": str(out_path.relative_to(ROOT)), "last_date": latest_date}


def draw_market_turnover_chart(df: pd.DataFrame, out_path: Path) -> dict:
    setup_fonts()
    plot_df = df.copy().sort_values("date")
    plot_df["date"] = pd.to_datetime(plot_df["date"])
    latest = plot_df.dropna(subset=["market_turnover_100mn"]).iloc[-1]
    latest_date = latest["date"].strftime("%Y-%m-%d")
    fig, ax = plt.subplots(figsize=(16, 7.2), dpi=180)
    fig.patch.set_facecolor("#fbfbf8")
    ax.set_facecolor("#fbfbf8")
    ax.plot(plot_df["date"], plot_df["market_turnover_100mn"], color="#1f77b4", linewidth=2.0, label="全市场成交额")
    if "turnover_ma5_100mn" in plot_df:
        ax.plot(plot_df["date"], plot_df["turnover_ma5_100mn"], color="#c5513c", linewidth=1.8, alpha=0.9, label="5日均值")
    ax.annotate(
        f"{latest_date}  {latest['market_turnover_100mn']:,.0f}亿元",
        xy=(latest["date"], latest["market_turnover_100mn"]),
        xytext=(10, 0),
        textcoords="offset points",
        va="center",
        fontsize=10,
        color="#1f77b4",
    )
    ax.set_title(f"全市场成交额变化（截至{latest_date}）", loc="left", fontsize=18, fontweight="bold", pad=16)
    ax.set_xlabel("日期", fontsize=12)
    ax.set_ylabel("成交额（亿元）", fontsize=12)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _pos: f"{x/10000:.1f}万亿" if abs(x) >= 10000 else f"{x:,.0f}"))
    ax.grid(axis="y", color="#d8d8d8", linewidth=0.8, alpha=0.65)
    ax.grid(axis="x", color="#eeeeee", linewidth=0.5, alpha=0.45)
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.set_xlim(plot_df["date"].min(), plot_df["date"].max() + pd.Timedelta(days=14))
    ax.legend(loc="upper left", ncol=2, frameon=False, fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return {"path": str(out_path.relative_to(ROOT)), "last_date": latest_date}


def draw_southbound_flow_chart(df: pd.DataFrame, out_path: Path) -> dict:
    setup_fonts()
    plot_df = df.copy().sort_values("date")
    plot_df["date"] = pd.to_datetime(plot_df["date"])
    plot_df["southbound_net_buy_100mn"] = pd.to_numeric(plot_df["southbound_net_buy_100mn"], errors="coerce")
    latest = plot_df.dropna(subset=["southbound_net_buy_100mn"]).iloc[-1]
    latest_date = latest["date"].strftime("%Y-%m-%d")
    colors = plot_df["southbound_net_buy_100mn"].apply(lambda value: "#c5513c" if value >= 0 else "#2a9d55")
    fig, ax = plt.subplots(figsize=(16, 7.2), dpi=180)
    fig.patch.set_facecolor("#fbfbf8")
    ax.set_facecolor("#fbfbf8")
    ax.bar(
        plot_df["date"],
        plot_df["southbound_net_buy_100mn"],
        width=0.82,
        color=colors,
        edgecolor="#ffffff",
        linewidth=0.35,
        label="南向资金净流入",
    )
    ax.axhline(0, color="#59636e", linewidth=1.0, alpha=0.85)
    ax.annotate(
        f"{latest_date}  {latest['southbound_net_buy_100mn']:,.2f}亿元",
        xy=(latest["date"], latest["southbound_net_buy_100mn"]),
        xytext=(12, 0),
        textcoords="offset points",
        va="center",
        fontsize=10,
        color="#203040",
        bbox={"boxstyle": "round,pad=0.25", "facecolor": "#ffffff", "edgecolor": "#d0d0d0", "alpha": 0.9},
    )
    ax.set_title(f"南向资金每日净流入（截至{latest_date}）", loc="left", fontsize=18, fontweight="bold", pad=16)
    ax.set_xlabel("日期", fontsize=12)
    ax.set_ylabel("净流入额（亿元）", fontsize=12)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _pos: f"{x:,.0f}"))
    ax.grid(axis="y", color="#d8d8d8", linewidth=0.8, alpha=0.65)
    ax.grid(axis="x", color="#eeeeee", linewidth=0.5, alpha=0.45)
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.set_xlim(plot_df["date"].min(), plot_df["date"].max() + pd.Timedelta(days=8))
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return {"path": str(out_path.relative_to(ROOT)), "last_date": latest_date}


def draw_macro_overview_chart(df: pd.DataFrame, metadata: dict, out_path: Path) -> dict:
    setup_fonts()
    order = metadata.get("indicator_order") or []
    if not order:
        order = [{"indicator_key": key, "indicator": key} for key in df["indicator_key"].dropna().unique()]
    plot_df = df.copy()
    plot_df["date"] = pd.to_datetime(plot_df["date"], errors="coerce")
    plot_df["value"] = pd.to_numeric(plot_df["value"], errors="coerce")
    plot_df.loc[plot_df["value"].eq(0), "value"] = pd.NA
    values = plot_df["value"].dropna()
    if values.empty:
        y_min, y_max = -5, 5
    else:
        y_min = math.floor(min(values.min(), -1) / 5) * 5
        y_max = math.ceil(max(values.max(), 1) / 5) * 5
        if y_min == y_max:
            y_min -= 5
            y_max += 5
    latest_date = str(metadata.get("latest_date") or plot_df["date"].max().strftime("%Y-%m-%d"))
    n = len(order)
    fig, axes = plt.subplots(1, n, figsize=(max(18, n * 1.45), 5.2), dpi=180, sharey=True)
    if n == 1:
        axes = [axes]
    fig.patch.set_facecolor("#fbfbf8")
    palette = ["#2f7cb8", "#2a9d55", "#d4a51c", "#d58b3a", "#9d5c9f", "#8b6f47", "#c5513c", "#6a737d"]
    for idx, item in enumerate(order):
        key = item["indicator_key"]
        label = item.get("indicator", key)
        ax = axes[idx]
        ax.set_facecolor("#fbfbf8")
        sub = plot_df[plot_df["indicator_key"].eq(key)].dropna(subset=["date", "value"]).sort_values("date").tail(6)
        color = palette[idx % len(palette)]
        if sub.empty:
            ax.text(0.5, 0.5, "暂无数据", transform=ax.transAxes, ha="center", va="center", fontsize=8.5, color="#7a6f64")
            ax.set_xticks([])
        else:
            x = range(len(sub))
            ax.plot(x, sub["value"], color=color, linewidth=1.8, marker="o", markersize=3.4)
            ax.set_xticks(list(x), [d.strftime("%Y-%m") for d in sub["date"]], rotation=90, fontsize=7)
            for x_pos, value in zip(x, sub["value"]):
                if pd.notna(value):
                    ax.annotate(f"{value:.1f}", xy=(x_pos, value), xytext=(0, 5), textcoords="offset points", ha="center", va="bottom", fontsize=6.8, color="#34404a")
        ax.set_title(str(label), fontsize=10, fontweight="bold", pad=8)
        ax.set_ylim(y_min, y_max)
        ax.axhline(0, color="#9aa3ad", linewidth=0.8, alpha=0.8)
        ax.grid(axis="y", color="#d8d8d8", linewidth=0.7, alpha=0.62)
        ax.grid(axis="x", color="#eeeeee", linewidth=0.45, alpha=0.45)
        ax.spines[["top", "right"]].set_visible(False)
        if idx == 0:
            ax.set_ylabel("同比增速（%）", fontsize=11)
        else:
            ax.spines["left"].set_visible(False)
            ax.tick_params(axis="y", left=False, labelleft=False)
    fig.suptitle(f"宏观经济数据概览（截至{latest_date}）", x=0.01, y=1.02, ha="left", fontsize=18, fontweight="bold")
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return {"path": str(out_path.relative_to(ROOT)), "last_date": latest_date, "status": metadata.get("status", "ok")}


def draw_citic_industry_crowding_chart(df: pd.DataFrame | None, metadata: dict, out_path: Path) -> dict | None:
    setup_fonts()
    if df is None or df.empty:
        notes = metadata.get("notes", [])
        reason = ""
        if notes:
            reason = str(notes[0])
            if len(reason) > 72:
                reason = reason[:72] + "..."
        fig, ax = plt.subplots(figsize=(16, 6.2), dpi=180)
        fig.patch.set_facecolor("#fbfbf8")
        ax.set_facecolor("#fbfbf8")
        ax.axis("off")
        ax.text(
            0.5,
            0.56,
            "中信一级行业拥挤度数据待接入",
            ha="center",
            va="center",
            fontsize=24,
            fontweight="bold",
            color="#203040",
        )
        ax.text(
            0.5,
            0.42,
            "优先使用 Wind API；若 Wind 不可用，请补充 data/raw/citic_industry_crowding_weekly.csv 后重新生成。",
            ha="center",
            va="center",
            fontsize=13,
            color="#59636e",
        )
        if reason:
            ax.text(
                0.5,
                0.32,
                f"当前状态：{reason}",
                ha="center",
                va="center",
                fontsize=10.5,
                color="#8a4b3a",
            )
        fig.savefig(out_path, bbox_inches="tight")
        plt.close(fig)
        return {"path": str(out_path.relative_to(ROOT)), "last_date": "", "status": "missing_data"}

    plot_df = df.copy().sort_values("crowding_score", ascending=True)
    metrics = [
        ("pe_ttm_pctile_10y", "PE_TTM十年分位", "pe_ttm_pctile_10y_wow"),
        ("pb_lf_pctile_10y", "PB_LF十年分位", "pb_lf_pctile_10y_wow"),
        ("amount_pctile_5y", "成交额五年分位", "amount_pctile_5y_wow"),
    ]
    latest_date = str(plot_df["date"].max())
    fig_h = max(8.5, len(plot_df) * 0.34 + 2.2)
    fig, ax = plt.subplots(figsize=(16, fig_h), dpi=180)
    fig.patch.set_facecolor("#fbfbf8")
    ax.set_facecolor("#fbfbf8")
    for x_pos, (col, _label, wow_col) in enumerate(metrics):
        values = pd.to_numeric(plot_df[col], errors="coerce")
        sc = ax.scatter(
            [x_pos] * len(plot_df),
            range(len(plot_df)),
            c=values,
            s=210,
            cmap="RdYlGn_r",
            vmin=0,
            vmax=100,
            edgecolor="#ffffff",
            linewidth=0.9,
            zorder=3,
        )
        for y_pos, (_, row) in enumerate(plot_df.iterrows()):
            value = row[col]
            wow = row.get(wow_col)
            if pd.isna(value):
                label = "NA"
            elif pd.isna(wow):
                label = f"{value:.0f}%"
            else:
                sign = "+" if wow > 0 else ""
                label = f"{value:.0f}% ({sign}{wow:.0f})"
            ax.text(x_pos + 0.12, y_pos, label, va="center", ha="left", fontsize=9.2, color="#293642")
    ax.set_yticks(range(len(plot_df)), plot_df["industry"])
    ax.set_xticks(range(len(metrics)), [label for _col, label, _wow_col in metrics])
    ax.tick_params(axis="x", labelsize=11, pad=10)
    ax.tick_params(axis="y", labelsize=9.5)
    ax.set_xlim(-0.45, len(metrics) - 0.05)
    ax.set_ylim(-0.8, len(plot_df) - 0.2)
    ax.grid(axis="y", color="#e2dfd7", linewidth=0.7, alpha=0.75)
    ax.set_title(f"中信一级行业估值与成交拥挤度（截至{latest_date}）", loc="left", fontsize=18, fontweight="bold", pad=16)
    ax.text(0, 1.01, "括号内为较上周变化，单位：百分点；颜色越红代表分位越高。", transform=ax.transAxes, fontsize=10.5, color="#59636e")
    cbar = fig.colorbar(sc, ax=ax, fraction=0.025, pad=0.02)
    cbar.set_label("历史分位数（%）")
    ax.spines[["top", "right", "left", "bottom"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return {
        "path": str(out_path.relative_to(ROOT)),
        "last_date": latest_date,
        "status": metadata.get("status", "ok"),
    }


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


def format_table_value(field: str, value: object) -> str:
    if pd.isna(value):
        return ""
    if field == "代码":
        return str(value).strip().split(".")[0].zfill(6)
    if field in {"流通市值", "成交额"}:
        return f"{float(value):,.2f}"
    if field == "现价":
        return f"{float(value):,.2f}"
    return escape(str(value))


def render_limit_up_table(title: str, df: pd.DataFrame | None, latest_date: str) -> str:
    note_html = chart_note_block(
        "涨停股池来自东方财富公开接口；主营业务来自巨潮公司概况。公开涨停池未披露逐股原因，原因字段先按所属行业、连板数和涨停统计归纳。",
        "涨停原因不是交易所官方逐股披露结论，仅用于快速观察；若个股信息为空或异常，通常代表公开接口尚未更新或公司概况抓取失败。",
    )
    if df is None or df.empty:
        return f'''      <section class="chart-section">
        <h2>{title}（截至{latest_date or "待接入"}）</h2>
        <p class="empty-note">暂无可展示数据。</p>
        {note_html}
      </section>'''
    columns = ["代码", "名称", "连续涨停天数", "流通市值", "现价", "成交额", "主营业务", "涨停原因"]
    headers = {
        "流通市值": "流通市值（亿元）",
        "成交额": "成交额（亿元）",
    }
    thead = "".join(f"<th>{headers.get(col, col)}</th>" for col in columns)
    rows = []
    for _, row in df.iterrows():
        cells = "".join(f"<td>{format_table_value(col, row.get(col))}</td>" for col in columns)
        rows.append(f"<tr>{cells}</tr>")
    return f'''      <section class="chart-section">
        <h2>{title}（截至{latest_date}）</h2>
        <div class="table-wrap"><table class="data-table"><thead><tr>{thead}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>
        {note_html}
      </section>'''


def chart_note_block(data_note: str, risk_note: str) -> str:
    return f'''<div class="chart-notes">
          <p><strong>数据说明：</strong>{data_note}</p>
          <p><strong>风险提示：</strong>{risk_note}</p>
        </div>'''


def build_page(
    metadata: dict,
    chart3: dict,
    valuation_charts: list[dict],
    amount_share_chart: dict | None = None,
    industry_crowding_chart: dict | None = None,
    theme_amount_chart: dict | None = None,
    market_turnover_chart: dict | None = None,
    southbound_chart: dict | None = None,
    macro_chart: dict | None = None,
    macro_meta: dict | None = None,
    limit_up_longest: pd.DataFrame | None = None,
    limit_up_amount_top: pd.DataFrame | None = None,
    limit_up_meta: dict | None = None,
) -> None:
    assets_dir = SITE_DIR / "assets" / "charts"
    assets_dir.mkdir(parents=True, exist_ok=True)
    for chart_file in CHART_DIR.glob("*.png"):
        shutil.copy2(chart_file, assets_dir / chart_file.name)
    latest = metadata["latest_common_date"]
    updated_at = metadata["updated_at"]
    asset_version = latest.replace("-", "")
    broad_etf_risk = "净流入为 0 或长时间缺失时，可能代表 ETF 份额未更新、接口未披露或数据源暂不可用，不应机械解读为真实无申赎。"
    star_etf_risk = "净流入为 0 或长时间缺失时，可能代表 ETF 份额未更新、接口未披露或数据源暂不可用，不应机械解读为真实无申赎。"
    valuation_html = "\n\n".join(
        f'''      <section class="chart-section">
      <h2>{chart["title"]}</h2>
      <img src="assets/charts/{Path(chart["path"]).name}?v={asset_version}" alt="{chart["title"]}">
      {chart_note_block(
          f"统计区间自 {VALUATION_START_DATE} 起；PE_TTM 序列按交易日历史数据绘制，水平虚线分别为均值、均值±1倍标准差、均值±2倍标准差。",
          "估值分位和标准差通道仅反映历史相对位置，不代表合理估值中枢；若指数成分或口径调整，历史可比性会受影响。",
      )}
    </section>'''
        for chart in valuation_charts
    )
    amount_share_html = ""
    if amount_share_chart:
        amount_share_html = f'''      <section class="chart-section">
        <h2>图五：主要宽基指数成交额占全A成交额比例（截至{amount_share_chart["last_date"]}）</h2>
        <img src="assets/charts/{Path(amount_share_chart["path"]).name}?v={amount_share_chart["last_date"].replace("-", "")}" alt="主要宽基指数成交额占全A成交额比例">
        {chart_note_block(
            "数据来自中证指数官网指数行情接口。分子为沪深300、中证500、中证1000、中证2000指数成交金额；分母优先使用 Wind 全A成交额，当前公开数据用中证全指成交金额作为代理口径。",
            "成交额占比受指数样本、停复牌、分母代理口径影响；若中证官网或代理分母未更新，最新日期可能滞后。",
        )}
      </section>'''
    theme_amount_html = ""
    if theme_amount_chart:
        theme_amount_html = f'''      <section class="chart-section">
        <h2>图七：TMT与红利低波成交额占全A成交额比例（截至{theme_amount_chart["last_date"]}）</h2>
        <img src="assets/charts/{Path(theme_amount_chart["path"]).name}?v={theme_amount_chart["last_date"].replace("-", "")}" alt="TMT与红利低波成交额占全A成交额比例">
        {chart_note_block(
            "分子为中证TMT（000998）和中证红利低波动指数（H30269）成交金额；分母与图五保持一致，使用中证全指成交金额作为 Wind 全A 成交额公开代理口径。",
            "主题指数成交额不能等同于板块全部股票成交额；红利低波使用右轴展示，读取时应关注左右轴刻度差异。",
        )}
      </section>'''
    market_turnover_html = ""
    if market_turnover_chart:
        market_turnover_html = f'''      <section class="chart-section">
        <h2>图八：全市场成交额变化（截至{market_turnover_chart["last_date"]}）</h2>
        <img src="assets/charts/{Path(market_turnover_chart["path"]).name}?v={market_turnover_chart["last_date"].replace("-", "")}" alt="全市场成交额变化">
        {chart_note_block(
            "区间自 2024-09-24 起。当前使用中证全指成交金额作为沪深京全市场成交额公开代理口径；若后续接入交易所逐日汇总或 Wind 全A 精确口径，可替换本序列。",
            "代理口径可能低估或高估沪深京全市场真实成交额，尤其在北交所或非成分股成交活跃时偏差会扩大。",
        )}
      </section>'''
    southbound_html = ""
    if southbound_chart:
        southbound_html = f'''      <section class="chart-section">
        <h2>图九：南向资金每日净流入（截至{southbound_chart["last_date"]}）</h2>
        <img src="assets/charts/{Path(southbound_chart["path"]).name}?v={southbound_chart["last_date"].replace("-", "")}" alt="南向资金每日净流入">
        {chart_note_block(
            "区间自 2026-01-01 起。数据来自东方财富沪深港通历史数据，经 AkShare 获取；净流入口径为“当日成交净买额”，单位为亿元。",
            "若最新值长时间为 0、缺失或日期滞后，通常代表公开接口尚未更新；不同数据源对南向资金口径可能存在细微差异。",
        )}
      </section>'''
    macro_html = '<p class="empty-note">暂无图表。</p>'
    if macro_chart:
        macro_notes = ""
        if macro_meta and macro_meta.get("status") == "partial":
            missing = [note for note in macro_meta.get("notes", []) if "暂无可用自动数据" in note]
            if missing:
                macro_notes = "暂未自动接入：" + "；".join(note.split("：")[0] for note in missing[:6]) + "。"
        macro_html = f'''      <section class="chart-section">
        <h2>图十：宏观经济数据概览（截至{macro_chart["last_date"]}）</h2>
        <img src="assets/charts/{Path(macro_chart["path"]).name}?v={macro_chart["last_date"].replace("-", "")}" alt="宏观经济数据概览">
        {chart_note_block(
            f"展示各指标最近六个有效数据点，单位为同比增速（%）；0 值按缺失处理，不绘制数据点。月度指标按月展示，GDP 按季度展示。{macro_notes}",
            "宏观数据存在发布滞后、修订和接口失效风险；当前部分国家统计局、人民银行细分指标若未自动接入，会在图中保留占位。",
        )}
      </section>'''
    limit_up_date = (limit_up_meta or {}).get("latest_date", "")
    limit_up_html = render_limit_up_table("涨停观察：连续涨停天数前十", limit_up_longest, limit_up_date)
    limit_up_html += "\n" + render_limit_up_table("涨停观察：当日涨停成交额前十", limit_up_amount_top, limit_up_date)
    industry_crowding_html = ""
    if industry_crowding_chart:
        crowding_date = industry_crowding_chart.get("last_date") or "待接入"
        crowding_version = (industry_crowding_chart.get("last_date") or asset_version).replace("-", "")
        crowding_status_note = ""
        if industry_crowding_chart.get("status") == "missing_data":
            crowding_status_note = "当前未取得中信一级行业完整 PE_TTM/PB_LF/成交额历史数据，图中显示数据待接入状态。"
        industry_crowding_html = f'''      <section class="chart-section">
        <h2>图六：中信一级行业估值与成交拥挤度（截至{crowding_date}）</h2>
        <img src="assets/charts/{Path(industry_crowding_chart["path"]).name}?v={crowding_version}" alt="中信一级行业估值与成交拥挤度">
        {chart_note_block(
            f"按每周最后一个交易日更新。PE_TTM、PB_LF分别计算最近10年历史分位，成交额计算最近5年历史分位；括号为较上周变化，单位为百分点。数据优先使用 Wind API，Wind 不可用时读取本地 CSV。{crowding_status_note}",
            "拥挤度是估值与交易热度的历史分位观察，不代表买卖建议；若 Wind API 不可用或本地 CSV 未补齐，结果会显示待接入或滞后。",
        )}
      </section>'''
    html = f'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>投研数据页</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <main>
    <header class="page-head">
      <div><p class="eyebrow">Investment Data Monitor</p><h1>投研数据页</h1></div>
      <div class="meta"><div>更新：{updated_at}</div><div>区间：2025-01-01 至 {latest}</div></div>
    </header>

    <nav class="category-tabs" aria-label="投研数据分类">
      <button class="category-tab active" type="button" data-target="market" aria-selected="true">行情</button>
      <button class="category-tab" type="button" data-target="macro" aria-selected="false">宏观</button>
      <button class="category-tab" type="button" data-target="valuation" aria-selected="false">估值</button>
      <button class="category-tab" type="button" data-target="earnings" aria-selected="false">盈利</button>
      <button class="category-tab" type="button" data-target="liquidity" aria-selected="false">流动性</button>
      <button class="category-tab" type="button" data-target="sentiment" aria-selected="false">情绪</button>
    </nav>

    <section class="category-panel active" id="panel-market" data-category="market">
      <div class="category-head"><h2>行情</h2></div>
      <section class="chart-section">
        <h2>图一：沪深300/上证指数 vs. 大宽基ETF资金流</h2>
        <img src="assets/charts/fig_001_broad_etf_flow.png?v={asset_version}" alt="沪深300与上证指数走势及大宽基ETF资金流">
        {chart_note_block(
            "样本：510300、510310、510330、159919、510050。上交所 ETF 份额来自上交所历史规模接口；159919 份额来自深交所基金规模日频接口。净流入口径为份额变化乘以单位净值；7日滚动合计按交易日滚动计算。",
            broad_etf_risk,
        )}
      </section>
      <section class="chart-section">
        <h2>图二：科创50指数 vs. 科创50ETF资金流</h2>
        <img src="assets/charts/fig_002_star50_etf_flow.png?v={asset_version}" alt="科创50指数走势及科创50ETF资金流">
        {chart_note_block(
            "样本：588000 华夏科创50ETF。净流入口径为份额变化乘以单位净值；7日滚动合计按交易日滚动计算。",
            star_etf_risk,
        )}
      </section>
{market_turnover_html}
{limit_up_html}
{amount_share_html}
{theme_amount_html}
{industry_crowding_html}
    </section>

    <section class="category-panel" id="panel-macro" data-category="macro" hidden>
      <div class="category-head"><h2>宏观</h2></div>
{macro_html}
    </section>

    <section class="category-panel" id="panel-valuation" data-category="valuation" hidden>
      <div class="category-head"><h2>估值</h2></div>
{valuation_html}
    </section>

    <section class="category-panel" id="panel-earnings" data-category="earnings" hidden>
      <div class="category-head"><h2>盈利</h2></div>
      <p class="empty-note">暂无图表。</p>
    </section>

    <section class="category-panel" id="panel-liquidity" data-category="liquidity" hidden>
      <div class="category-head"><h2>流动性</h2></div>
      <section class="chart-section">
        <h2>图三：A股成交额前10大公司交易集中度变化（截至{chart3["last_date"]}）</h2>
        <img src="assets/charts/fig_003_a_share_turnover_concentration.png?v={asset_version}" alt="A股成交额前10大公司交易集中度变化">
        {chart_note_block(
            "样本覆盖当前沪深京A股清单；逐日计算前10、前100成交额占比。右轴为上证指数收盘价。",
            "个股成交额排名依赖公开行情接口完整性；停牌、新股、北交所覆盖和接口延迟都可能影响集中度读数。",
        )}
      </section>
{southbound_html}
    </section>

    <section class="category-panel" id="panel-sentiment" data-category="sentiment" hidden>
      <div class="category-head"><h2>情绪</h2></div>
      <p class="empty-note">暂无图表。</p>
    </section>
  </main>
  <script src="app.js"></script>
</body>
</html>
'''
    css = '''body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif;
  color: #1f2933;
  background: #f6f5f1;
}
main {
  max-width: 1180px;
  margin: 0 auto;
  padding: 36px 22px 56px;
}
.page-head {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  align-items: end;
  border-bottom: 1px solid #d8d4ca;
  padding-bottom: 20px;
}
.eyebrow {
  margin: 0 0 8px;
  color: #607080;
  font-size: 13px;
  letter-spacing: .08em;
  text-transform: uppercase;
}
h1 {
  margin: 0;
  font-size: 34px;
  font-weight: 760;
}
h2 {
  margin: 0 0 14px;
  font-size: 21px;
}
.meta {
  text-align: right;
  color: #59636e;
  font-size: 14px;
  line-height: 1.8;
}
.category-tabs {
  position: sticky;
  top: 0;
  z-index: 5;
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 1px;
  margin: 22px 0 10px;
  background: #d8d4ca;
  border: 1px solid #d8d4ca;
}
.category-tab {
  appearance: none;
  border: 0;
  border-radius: 0;
  min-height: 44px;
  padding: 0 12px;
  background: #f8f7f3;
  color: #53606b;
  font: inherit;
  font-size: 15px;
  cursor: pointer;
}
.category-tab:hover,
.category-tab:focus-visible {
  background: #ffffff;
  color: #1f2933;
  outline: none;
}
.category-tab.active {
  background: #203040;
  color: #ffffff;
  font-weight: 700;
}
.category-panel {
  padding-top: 20px;
}
.category-head {
  padding: 8px 0 12px;
  border-bottom: 1px solid #dedbd3;
}
.category-head h2 {
  font-size: 26px;
}
.chart-section {
  padding: 30px 0 18px;
  border-bottom: 1px solid #dedbd3;
}
.chart-section img {
  display: block;
  width: 100%;
  height: auto;
  background: #fbfbf8;
  border: 1px solid #dedbd3;
}
.table-wrap {
  overflow-x: auto;
  border: 1px solid #dedbd3;
  background: #fbfbf8;
}
.data-table {
  width: 100%;
  min-width: 980px;
  border-collapse: collapse;
  font-size: 13px;
}
.data-table th,
.data-table td {
  padding: 10px 11px;
  border-bottom: 1px solid #e5e1d8;
  text-align: left;
  vertical-align: top;
}
.data-table th {
  background: #ede9df;
  color: #203040;
  font-weight: 700;
}
.data-table td:nth-child(7),
.data-table td:nth-child(8) {
  min-width: 210px;
  line-height: 1.55;
}
.note, .empty-note, .chart-notes {
  color: #4f5c66;
  font-size: 14px;
  line-height: 1.75;
}
.chart-notes {
  margin-top: 12px;
  padding: 12px 14px;
  border-left: 3px solid #b8aa8f;
  background: #f0eee7;
}
.chart-notes p {
  margin: 0;
}
.chart-notes p + p {
  margin-top: 4px;
}
.chart-notes strong {
  color: #203040;
}
.empty-note {
  margin: 22px 0 36px;
}
@media (max-width: 720px) {
  main {
    padding: 28px 16px 44px;
  }
  .page-head {
    display: block;
  }
  .meta {
    text-align: left;
    margin-top: 14px;
  }
  h1 {
    font-size: 28px;
  }
  .category-tabs {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .category-tab {
    min-height: 42px;
    font-size: 14px;
  }
}
'''
    js = '''const tabs = Array.from(document.querySelectorAll(".category-tab"));
const panels = Array.from(document.querySelectorAll(".category-panel"));

function activateCategory(target) {
  tabs.forEach((tab) => {
    const active = tab.dataset.target === target;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", active ? "true" : "false");
  });
  panels.forEach((panel) => {
    const active = panel.dataset.category === target;
    panel.classList.toggle("active", active);
    panel.hidden = !active;
  });
}

tabs.forEach((tab) => {
  tab.addEventListener("click", () => activateCategory(tab.dataset.target));
});
'''
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    (SITE_DIR / "index.html").write_text(html, encoding="utf-8")
    (SITE_DIR / "styles.css").write_text(css, encoding="utf-8")
    (SITE_DIR / "app.js").write_text(js, encoding="utf-8")


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
    amount_share_chart = None
    amount_share_path = PROCESSED_DIR / "index_amount_share.csv"
    if amount_share_path.exists():
        amount_share = pd.read_csv(amount_share_path, parse_dates=["date"])
        amount_share_chart = draw_index_amount_share_chart(amount_share, CHART_DIR / "fig_005_index_amount_share.png")
    theme_amount_chart = None
    theme_amount_path = PROCESSED_DIR / "theme_amount_share.csv"
    if theme_amount_path.exists():
        theme_amount = pd.read_csv(theme_amount_path, parse_dates=["date"])
        theme_amount_chart = draw_theme_amount_share_chart(theme_amount, CHART_DIR / "fig_007_theme_amount_share.png")
    market_turnover_chart = None
    market_turnover_path = PROCESSED_DIR / "market_turnover.csv"
    if market_turnover_path.exists():
        market_turnover = pd.read_csv(market_turnover_path, parse_dates=["date"])
        market_turnover_chart = draw_market_turnover_chart(market_turnover, CHART_DIR / "fig_008_market_turnover.png")
    southbound_chart = None
    southbound_path = PROCESSED_DIR / "southbound_flow.csv"
    if southbound_path.exists():
        southbound = pd.read_csv(southbound_path, parse_dates=["date"])
        southbound_chart = draw_southbound_flow_chart(southbound, CHART_DIR / "fig_009_southbound_flow.png")
    macro_chart = None
    macro_meta = {}
    macro_path = PROCESSED_DIR / "macro_overview.csv"
    macro_meta_path = PROCESSED_DIR / "macro_overview.metadata.json"
    if macro_meta_path.exists():
        macro_meta = json.loads(macro_meta_path.read_text(encoding="utf-8"))
    if macro_path.exists():
        macro = pd.read_csv(macro_path, parse_dates=["date"])
        macro_chart = draw_macro_overview_chart(macro, macro_meta, CHART_DIR / "fig_010_macro_overview.png")
    industry_crowding_chart = None
    industry_crowding_path = PROCESSED_DIR / "citic_industry_crowding.csv"
    industry_crowding_meta_path = PROCESSED_DIR / "citic_industry_crowding.metadata.json"
    industry_crowding_meta = {}
    if industry_crowding_meta_path.exists():
        industry_crowding_meta = json.loads(industry_crowding_meta_path.read_text(encoding="utf-8"))
    if industry_crowding_path.exists():
        industry_crowding = pd.read_csv(industry_crowding_path)
        industry_crowding_chart = draw_citic_industry_crowding_chart(industry_crowding, industry_crowding_meta, CHART_DIR / "fig_006_citic_industry_crowding.png")
    elif industry_crowding_meta_path.exists():
        industry_crowding_chart = draw_citic_industry_crowding_chart(None, industry_crowding_meta, CHART_DIR / "fig_006_citic_industry_crowding.png")
    valuation_charts = [
        draw_valuation_chart(valuation, "沪深300指数", CHART_DIR / "fig_004a_hs300_pe_ttm_channel.png"),
        draw_valuation_chart(valuation, "上证指数", CHART_DIR / "fig_004b_sse_pe_ttm_channel.png"),
    ]
    limit_up_longest = None
    limit_up_amount_top = None
    limit_up_meta = {}
    limit_up_longest_path = PROCESSED_DIR / "limit_up_longest.csv"
    limit_up_amount_path = PROCESSED_DIR / "limit_up_amount_top.csv"
    limit_up_meta_path = PROCESSED_DIR / "limit_up_tables.metadata.json"
    if limit_up_longest_path.exists():
        limit_up_longest = pd.read_csv(limit_up_longest_path, dtype={"代码": str})
    if limit_up_amount_path.exists():
        limit_up_amount_top = pd.read_csv(limit_up_amount_path, dtype={"代码": str})
    if limit_up_meta_path.exists():
        limit_up_meta = json.loads(limit_up_meta_path.read_text(encoding="utf-8"))
    build_page(
        metadata,
        chart3,
        valuation_charts,
        amount_share_chart,
        industry_crowding_chart,
        theme_amount_chart,
        market_turnover_chart,
        southbound_chart,
        macro_chart,
        macro_meta,
        limit_up_longest,
        limit_up_amount_top,
        limit_up_meta,
    )
    chart_count = 5 + int(bool(amount_share_chart)) + int(bool(industry_crowding_chart)) + int(bool(theme_amount_chart)) + int(bool(market_turnover_chart)) + int(bool(southbound_chart)) + int(bool(macro_chart))
    print(json.dumps({"latest_common_date": metadata["latest_common_date"], "charts": chart_count}, ensure_ascii=False))


if __name__ == "__main__":
    main()
