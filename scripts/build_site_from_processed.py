#!/usr/bin/env python3
"""Build the static site from processed CSV snapshots."""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime
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

from chart_registry import CHART_REGISTRY, REGISTRY_BY_KEY


PROCESSED_DIR = ROOT / "data" / "processed"
RAW_DIR = ROOT / "data" / "raw"
CHART_DIR = ROOT / "output" / "charts"
SITE_DIR = ROOT / "site"
VALUATION_START_DATE = "2020-01-01"
CURRENT_CHART_STATUS: dict[str, dict] = {}


def set_time_axis(ax, dates: pd.Series, *, compact: bool = True) -> None:
    start = pd.to_datetime(dates).min()
    end = pd.to_datetime(dates).max()
    years = max((end - start).days / 365.25, 0)
    if years >= 8:
        ax.xaxis.set_major_locator(mdates.YearLocator(base=2 if compact else 1))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    elif years >= 3:
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    else:
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3 if compact else 2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.tick_params(axis="x", labelrotation=0, labelsize=9.5)


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


def draw_turnover_share_chart(df: pd.DataFrame, share_col: str, label: str, color: str, out_path: Path) -> dict:
    setup_fonts()
    plot_df = df.copy().sort_values("date")
    plot_df["date"] = pd.to_datetime(plot_df["date"])
    latest = plot_df.dropna(subset=[share_col]).iloc[-1]
    latest_date = latest["date"].strftime("%Y-%m-%d")
    fig, ax1 = plt.subplots(figsize=(16, 7.2), dpi=180)
    fig.patch.set_facecolor("#fbfbf8")
    ax1.set_facecolor("#fbfbf8")
    ax2 = ax1.twinx()
    ax1.plot(plot_df["date"], plot_df[share_col], color=color, linewidth=2.45, label=label)
    ax2.plot(plot_df["date"], plot_df["上证指数"], color="#7a6f64", linewidth=1.75, alpha=0.75, label="上证指数")
    ax1.annotate(
        f"{latest_date}  {latest[share_col]:.2f}%",
        xy=(latest["date"], latest[share_col]),
        xytext=(12, 0),
        textcoords="offset points",
        va="center",
        fontsize=11,
        color=color,
        bbox={"boxstyle": "round,pad=0.25", "facecolor": "#ffffff", "edgecolor": "#d0d0d0", "alpha": 0.9},
    )
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
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", ncol=2, frameon=False, fontsize=10)
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
    if "rolling_15d_net_buy_100mn" not in plot_df:
        plot_df["rolling_15d_net_buy_100mn"] = plot_df["southbound_net_buy_100mn"].rolling(15, min_periods=15).sum()
    else:
        plot_df["rolling_15d_net_buy_100mn"] = pd.to_numeric(plot_df["rolling_15d_net_buy_100mn"], errors="coerce")
    latest = plot_df.dropna(subset=["southbound_net_buy_100mn"]).iloc[-1]
    latest_date = latest["date"].strftime("%Y-%m-%d")
    colors = plot_df["southbound_net_buy_100mn"].apply(lambda value: "#c5513c" if value >= 0 else "#2a9d55")
    fig, ax = plt.subplots(figsize=(16, 7.2), dpi=180)
    fig.patch.set_facecolor("#fbfbf8")
    ax.set_facecolor("#fbfbf8")
    ax2 = ax.twinx()
    ax.bar(
        plot_df["date"],
        plot_df["southbound_net_buy_100mn"],
        width=0.82,
        color=colors,
        edgecolor="#ffffff",
        linewidth=0.35,
        label="南向资金净流入",
    )
    ax2.plot(plot_df["date"], plot_df["rolling_15d_net_buy_100mn"], color="#1f6fb2", linewidth=2.0, label="15日滚动累计净流入")
    ax.axhline(0, color="#59636e", linewidth=1.0, alpha=0.85)
    if pd.notna(latest.get("rolling_15d_net_buy_100mn")):
        ax2.annotate(
            f"15日 {latest['rolling_15d_net_buy_100mn']:,.0f}亿元",
            xy=(latest["date"], latest["rolling_15d_net_buy_100mn"]),
            xytext=(12, 0),
            textcoords="offset points",
            va="center",
            fontsize=10,
            color="#1f6fb2",
        )
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
    ax.set_xlabel("日期", fontsize=12)
    ax.set_ylabel("净流入额（亿元）", fontsize=12)
    ax2.set_ylabel("15日滚动累计（亿元）", fontsize=12)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _pos: f"{x:,.0f}"))
    ax2.yaxis.set_major_formatter(FuncFormatter(lambda x, _pos: f"{x:,.0f}"))
    ax.grid(axis="y", color="#d8d8d8", linewidth=0.8, alpha=0.65)
    ax.grid(axis="x", color="#eeeeee", linewidth=0.5, alpha=0.45)
    set_time_axis(ax, plot_df["date"], compact=True)
    ax.set_xlim(plot_df["date"].min(), plot_df["date"].max() + pd.Timedelta(days=8))
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, loc="upper left", ncol=2, frameon=False, fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    ax2.spines[["top", "left"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return {"path": str(out_path.relative_to(ROOT)), "last_date": latest_date}


def draw_hk_sentiment_chart(df: pd.DataFrame, out_path: Path) -> dict | None:
    setup_fonts()
    if df is None or df.empty:
        return None
    plot_df = df.copy().sort_values("date")
    plot_df["date"] = pd.to_datetime(plot_df["date"])
    for col in ["hk_sentiment_z", "hsi_close", "breadth_z", "vhsi_z", "relative_z", "southbound_z", "short_z"]:
        if col in plot_df:
            plot_df[col] = pd.to_numeric(plot_df[col], errors="coerce")
    latest = plot_df.dropna(subset=["hk_sentiment_z"]).iloc[-1]
    latest_date = latest["date"].strftime("%Y-%m-%d")
    fig, ax = plt.subplots(figsize=(16, 7.4), dpi=180)
    fig.patch.set_facecolor("#fbfbf8")
    ax.set_facecolor("#fbfbf8")
    ax2 = ax.twinx()
    ax.plot(plot_df["date"], plot_df["hk_sentiment_z"], color="#c5513c", linewidth=2.35, label="港股情绪Z")
    ax.axhline(0, color="#8a93a1", linewidth=0.9, alpha=0.8)
    ax.fill_between(plot_df["date"], plot_df["hk_sentiment_z"], 0, color="#c5513c", alpha=0.12, linewidth=0)
    ax2.plot(plot_df["date"], plot_df["hsi_close"], color="#1f6fb2", linewidth=1.9, alpha=0.82, label="恒生指数")
    ax.annotate(
        f"{latest_date}  {latest['hk_sentiment_z']:.2f}",
        xy=(latest["date"], latest["hk_sentiment_z"]),
        xytext=(12, 0),
        textcoords="offset points",
        va="center",
        fontsize=10,
        color="#c5513c",
        bbox={"boxstyle": "round,pad=0.25", "facecolor": "#ffffff", "edgecolor": "#d0d0d0", "alpha": 0.9},
    )
    ax.set_xlabel("日期", fontsize=12)
    ax.set_ylabel("情绪指标Z", fontsize=12)
    ax2.set_ylabel("恒生指数收盘价（点）", fontsize=12)
    ax.grid(axis="y", color="#d8d8d8", linewidth=0.8, alpha=0.65)
    ax.grid(axis="x", color="#eeeeee", linewidth=0.5, alpha=0.45)
    set_time_axis(ax, plot_df["date"], compact=True)
    ax.set_xlim(plot_df["date"].min(), plot_df["date"].max() + pd.Timedelta(days=8))
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, loc="upper left", ncol=2, frameon=False, fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    ax2.spines[["top", "left"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return {"path": str(out_path.relative_to(ROOT)), "last_date": latest_date}


def draw_dual_line_chart(
    df: pd.DataFrame,
    left_col: str,
    right_col: str,
    left_label: str,
    right_label: str,
    title: str,
    out_path: Path,
    left_color: str = "#1f6fb2",
    right_color: str = "#c5513c",
) -> dict | None:
    setup_fonts()
    if df is None or df.empty:
        return None
    plot_df = df.copy().sort_values("date")
    plot_df["date"] = pd.to_datetime(plot_df["date"])
    for col in [left_col, right_col]:
        plot_df[col] = pd.to_numeric(plot_df[col], errors="coerce")
    latest = plot_df.dropna(subset=[left_col, right_col], how="all").iloc[-1]
    latest_date = latest["date"].strftime("%Y-%m-%d")
    fig, ax = plt.subplots(figsize=(16, 7.2), dpi=180)
    fig.patch.set_facecolor("#fbfbf8")
    ax.set_facecolor("#fbfbf8")
    ax2 = ax.twinx()
    if plot_df[left_col].notna().any():
        ax.plot(plot_df["date"], plot_df[left_col], color=left_color, linewidth=2.1, label=left_label)
    if plot_df[right_col].notna().any():
        ax2.plot(plot_df["date"], plot_df[right_col], color=right_color, linewidth=2.1, label=right_label)
    label_lines = [latest_date]
    if pd.notna(latest.get(left_col)):
        label_lines.append(f"{left_label}: {latest[left_col]:.2f}")
    if pd.notna(latest.get(right_col)):
        label_lines.append(f"{right_label}: {latest[right_col]:.2f}")
    ax.text(
        0.985,
        0.965,
        "\n".join(label_lines),
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=10.2,
        bbox={"boxstyle": "round,pad=0.4", "facecolor": "#ffffff", "edgecolor": "#d0d0d0", "alpha": 0.9},
    )
    ax.set_title(title, fontsize=15, fontweight="bold", loc="left", pad=12)
    ax.set_xlabel("日期", fontsize=12)
    ax.set_ylabel(left_label, fontsize=12)
    ax2.set_ylabel(right_label, fontsize=12)
    ax.grid(axis="y", color="#d8d8d8", linewidth=0.8, alpha=0.65)
    ax.grid(axis="x", color="#eeeeee", linewidth=0.5, alpha=0.45)
    set_time_axis(ax, plot_df["date"], compact=True)
    ax.set_xlim(plot_df["date"].min(), plot_df["date"].max() + pd.Timedelta(days=8))
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, loc="upper left", ncol=2, frameon=False, fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    ax2.spines[["top", "left"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return {"path": str(out_path.relative_to(ROOT)), "last_date": latest_date}


def draw_hsi_pe_chart(df: pd.DataFrame, out_path: Path) -> dict | None:
    setup_fonts()
    if df is None or df.empty:
        return None
    plot_df = df.copy().sort_values("date")
    plot_df["date"] = pd.to_datetime(plot_df["date"])
    plot_df["pe_ttm"] = pd.to_numeric(plot_df["pe_ttm"], errors="coerce")
    plot_df = plot_df.dropna(subset=["pe_ttm"])
    if plot_df.empty:
        return None
    mu = plot_df["pe_ttm"].mean()
    sigma = plot_df["pe_ttm"].std(ddof=0)
    latest = plot_df.iloc[-1]
    pctile = (plot_df["pe_ttm"].le(latest["pe_ttm"]).mean()) * 100
    latest_date = latest["date"].strftime("%Y-%m-%d")
    fig, ax = plt.subplots(figsize=(16, 7.2), dpi=180)
    fig.patch.set_facecolor("#fbfbf8")
    ax.set_facecolor("#fbfbf8")
    ax.plot(plot_df["date"], plot_df["pe_ttm"], color="#1f6fb2", linewidth=2.2, label="PE_TTM")
    for y, label, color in [(mu, "均值", "#59636e"), (mu + sigma, "+1σ", "#c88a2d"), (mu - sigma, "-1σ", "#c88a2d")]:
        ax.axhline(y, linestyle="--", color=color, linewidth=1.1, alpha=0.85, label=label)
    ax.annotate(f"{latest_date}  {latest['pe_ttm']:.2f}倍 / 分位 {pctile:.1f}%", xy=(latest["date"], latest["pe_ttm"]), xytext=(12, 0), textcoords="offset points", va="center", fontsize=10, color="#1f6fb2")
    ax.set_xlabel("日期", fontsize=12)
    ax.set_ylabel("PE_TTM（倍）", fontsize=12)
    ax.grid(axis="y", color="#d8d8d8", linewidth=0.8, alpha=0.65)
    ax.grid(axis="x", color="#eeeeee", linewidth=0.5, alpha=0.45)
    set_time_axis(ax, plot_df["date"], compact=True)
    ax.set_xlim(plot_df["date"].min(), plot_df["date"].max() + pd.Timedelta(days=8))
    ax.legend(loc="upper left", ncol=4, frameon=False, fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return {"path": str(out_path.relative_to(ROOT)), "last_date": latest_date}


def draw_hsi_erp_chart(df: pd.DataFrame, out_path: Path) -> dict | None:
    setup_fonts()
    if df is None or df.empty or "erp" not in df:
        return None
    plot_df = df.copy().sort_values("date")
    plot_df["date"] = pd.to_datetime(plot_df["date"])
    plot_df["erp"] = pd.to_numeric(plot_df["erp"], errors="coerce")
    plot_df = plot_df.dropna(subset=["erp"])
    if plot_df.empty:
        return None
    mu = plot_df["erp"].mean()
    sigma = plot_df["erp"].std(ddof=0)
    latest = plot_df.iloc[-1]
    pctile = (plot_df["erp"].le(latest["erp"]).mean()) * 100
    latest_date = latest["date"].strftime("%Y-%m-%d")
    fig, ax = plt.subplots(figsize=(16, 7.2), dpi=180)
    fig.patch.set_facecolor("#fbfbf8")
    ax.set_facecolor("#fbfbf8")
    ax.plot(plot_df["date"], plot_df["erp"], color="#7b4ab8", linewidth=2.2, label="恒生指数ERP")
    for y, label, color in [(mu, "均值", "#59636e"), (mu + sigma, "+1σ", "#c88a2d"), (mu - sigma, "-1σ", "#c88a2d")]:
        ax.axhline(y, linestyle="--", color=color, linewidth=1.1, alpha=0.85, label=label)
    ax.annotate(f"{latest_date}  {latest['erp']:.2f}% / 分位 {pctile:.1f}%", xy=(latest["date"], latest["erp"]), xytext=(12, 0), textcoords="offset points", va="center", fontsize=10, color="#7b4ab8")
    ax.set_xlabel("日期", fontsize=12)
    ax.set_ylabel("ERP（%）", fontsize=12)
    ax.grid(axis="y", color="#d8d8d8", linewidth=0.8, alpha=0.65)
    ax.grid(axis="x", color="#eeeeee", linewidth=0.5, alpha=0.45)
    set_time_axis(ax, plot_df["date"], compact=True)
    ax.set_xlim(plot_df["date"].min(), plot_df["date"].max() + pd.Timedelta(days=8))
    ax.legend(loc="upper left", ncol=4, frameon=False, fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return {"path": str(out_path.relative_to(ROOT)), "last_date": latest_date}


def draw_hk_dividend_chart(df: pd.DataFrame, out_path: Path) -> dict | None:
    setup_fonts()
    if df is None or df.empty:
        return None
    plot_df = df.copy()
    plot_df["date"] = pd.to_datetime(plot_df["date"])
    plot_df["dividend_yield_ttm"] = pd.to_numeric(plot_df["dividend_yield_ttm"], errors="coerce")
    latest_date = plot_df["date"].max()
    latest = plot_df[plot_df["date"].eq(latest_date)].dropna(subset=["dividend_yield_ttm"]).sort_values("dividend_yield_ttm", ascending=False)
    if latest.empty:
        return None
    fig, ax = plt.subplots(figsize=(14.8, 6.8), dpi=180)
    fig.patch.set_facecolor("#fbfbf8")
    ax.set_facecolor("#fbfbf8")
    colors = ["#c5513c" if "港股" in name else "#1f6fb2" for name in latest["index_name"]]
    bars = ax.bar(latest["index_name"], latest["dividend_yield_ttm"], color=colors, alpha=0.86)
    for bar, value in zip(bars, latest["dividend_yield_ttm"]):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 0.06, f"{value:.2f}%", ha="center", va="bottom", fontsize=10)
    ax.set_ylabel("股息率TTM（%）", fontsize=12)
    ax.set_xlabel("指数", fontsize=12)
    ax.grid(axis="y", color="#d8d8d8", linewidth=0.8, alpha=0.65)
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(axis="x", rotation=20)
    ax.text(0.985, 0.965, latest_date.strftime("%Y-%m-%d"), transform=ax.transAxes, ha="right", va="top", fontsize=10.5, bbox={"boxstyle": "round,pad=0.35", "facecolor": "#ffffff", "edgecolor": "#d0d0d0", "alpha": 0.9})
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return {"path": str(out_path.relative_to(ROOT)), "last_date": latest_date.strftime("%Y-%m-%d")}


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
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return {"path": str(out_path.relative_to(ROOT)), "last_date": latest_date, "status": metadata.get("status", "ok")}


def draw_macro_inventory_chart(df: pd.DataFrame | None, out_path: Path) -> dict | None:
    setup_fonts()
    if df is None or df.empty:
        return None
    plot_df = df.copy().sort_values("date")
    plot_df["date"] = pd.to_datetime(plot_df["date"], errors="coerce")
    for col in ["inventory_yoy", "real_inventory_yoy", "ppi_yoy"]:
        if col in plot_df:
            plot_df[col] = pd.to_numeric(plot_df[col], errors="coerce")
    plot_df = plot_df.dropna(subset=["date"])
    latest = plot_df.dropna(subset=["inventory_yoy", "real_inventory_yoy"], how="all").iloc[-1]
    latest_date = latest["date"].strftime("%Y-%m")

    fig, ax = plt.subplots(figsize=(15.6, 7.2), dpi=180)
    fig.patch.set_facecolor("#fbfbf8")
    ax.set_facecolor("#fbfbf8")
    nominal = plot_df.dropna(subset=["inventory_yoy"])
    real = plot_df.dropna(subset=["real_inventory_yoy"])
    ax.plot(nominal["date"], nominal["inventory_yoy"], color="#8d8acb", linewidth=2.6, label="工业企业产成品存货同比")
    ax.plot(real["date"], real["real_inventory_yoy"], color="#2e315f", linewidth=2.6, label="实际库存同比（扣除PPI）")
    ax.axhline(0, color="#59636e", linewidth=1.0, alpha=0.85)
    ax.grid(axis="y", color="#d8d8d8", linewidth=0.8, alpha=0.65)
    ax.grid(axis="x", color="#eeeeee", linewidth=0.5, alpha=0.35)
    ax.set_ylabel("同比（%）", fontsize=12)
    ax.set_xlabel("日期", fontsize=12)
    set_time_axis(ax, plot_df["date"], compact=True)
    ax.set_xlim(plot_df["date"].min(), plot_df["date"].max() + pd.Timedelta(days=120))
    if pd.notna(latest.get("inventory_yoy")):
        ax.annotate(
            f"{latest_date} 名义 {latest['inventory_yoy']:.1f}%",
            xy=(latest["date"], latest["inventory_yoy"]),
            xytext=(12, 0),
            textcoords="offset points",
            va="center",
            fontsize=9.8,
            color="#8d8acb",
        )
    if pd.notna(latest.get("real_inventory_yoy")):
        ax.annotate(
            f"实际 {latest['real_inventory_yoy']:.1f}%",
            xy=(latest["date"], latest["real_inventory_yoy"]),
            xytext=(12, -14),
            textcoords="offset points",
            va="center",
            fontsize=9.8,
            color="#2e315f",
        )
    ax.legend(loc="upper center", ncol=2, frameon=False, fontsize=10.5)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return {"path": str(out_path.relative_to(ROOT)), "last_date": latest["date"].strftime("%Y-%m-%d")}


def draw_macro_m1_m2_chart(df: pd.DataFrame | None, out_path: Path) -> dict | None:
    setup_fonts()
    if df is None or df.empty:
        return None
    plot_df = df.copy().sort_values("date")
    plot_df["date"] = pd.to_datetime(plot_df["date"], errors="coerce")
    for col in ["m1_yoy", "m2_yoy", "m1_minus_m2"]:
        if col in plot_df:
            plot_df[col] = pd.to_numeric(plot_df[col], errors="coerce")
    plot_df = plot_df.dropna(subset=["date", "m1_minus_m2"])
    if plot_df.empty:
        return None
    latest = plot_df.iloc[-1]
    latest_date = latest["date"].strftime("%Y-%m")

    fig, ax = plt.subplots(figsize=(15.6, 6.8), dpi=180)
    fig.patch.set_facecolor("#fbfbf8")
    ax.set_facecolor("#fbfbf8")
    ax.plot(plot_df["date"], plot_df["m1_minus_m2"], color="#c5513c", linewidth=2.4, label="M1-M2")
    ax.fill_between(plot_df["date"], plot_df["m1_minus_m2"], 0, where=plot_df["m1_minus_m2"].ge(0), color="#c5513c", alpha=0.12, linewidth=0)
    ax.fill_between(plot_df["date"], plot_df["m1_minus_m2"], 0, where=plot_df["m1_minus_m2"].lt(0), color="#2a9d55", alpha=0.12, linewidth=0)
    ax.axhline(0, color="#59636e", linewidth=1.0, alpha=0.9)
    ax.grid(axis="y", color="#d8d8d8", linewidth=0.8, alpha=0.65)
    ax.grid(axis="x", color="#eeeeee", linewidth=0.5, alpha=0.35)
    ax.set_ylabel("百分点（%）", fontsize=12)
    ax.set_xlabel("日期", fontsize=12)
    set_time_axis(ax, plot_df["date"], compact=True)
    ax.set_xlim(plot_df["date"].min(), plot_df["date"].max() + pd.Timedelta(days=120))
    ax.annotate(
        f"{latest_date}  {latest['m1_minus_m2']:.1f}pct",
        xy=(latest["date"], latest["m1_minus_m2"]),
        xytext=(12, 0),
        textcoords="offset points",
        va="center",
        fontsize=10,
        color="#c5513c",
        bbox={"boxstyle": "round,pad=0.25", "facecolor": "#ffffff", "edgecolor": "#d0d0d0", "alpha": 0.9},
    )
    ax.legend(loc="upper left", frameon=False, fontsize=10.5)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return {"path": str(out_path.relative_to(ROOT)), "last_date": latest["date"].strftime("%Y-%m-%d")}


def draw_macro_fiscal_chart(df: pd.DataFrame | None, out_path: Path) -> dict | None:
    setup_fonts()
    if df is None or df.empty:
        return None
    plot_df = df.copy().sort_values("date")
    plot_df["date"] = pd.to_datetime(plot_df["date"], errors="coerce")
    cols = ["budget_revenue_ytd_yoy", "budget_expenditure_ytd_yoy", "central_revenue_ytd_yoy", "local_revenue_ytd_yoy"]
    for col in cols:
        if col in plot_df:
            plot_df[col] = pd.to_numeric(plot_df[col], errors="coerce")
    plot_df = plot_df.dropna(subset=["date"])
    if plot_df.empty:
        return None
    latest = plot_df.dropna(subset=cols, how="all").iloc[-1]
    latest_date = latest["date"].strftime("%Y-%m-%d")

    fig, axes = plt.subplots(1, 2, figsize=(16.8, 6.8), dpi=180, sharex=False)
    fig.patch.set_facecolor("#fbfbf8")
    for ax in axes:
        ax.set_facecolor("#fbfbf8")
        ax.axhline(0, color="#b9bdc3", linewidth=1.0, alpha=0.9)
        ax.grid(axis="y", color="#e0ded8", linewidth=0.8, alpha=0.72)
        ax.grid(axis="x", color="#eeeeee", linewidth=0.5, alpha=0.35)
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_xlabel("日期", fontsize=11)
        ax.tick_params(axis="x", labelrotation=55, labelsize=8.8)

    left_series = [
        ("budget_revenue_ytd_yoy", "一般公共预算收入累计同比", "#e9a7b6"),
        ("budget_expenditure_ytd_yoy", "一般公共预算支出累计同比", "#2f6f9f"),
    ]
    right_series = [
        ("central_revenue_ytd_yoy", "中央一般公共预算收入累计同比", "#12949d"),
        ("local_revenue_ytd_yoy", "地方一般公共预算本级收入累计同比", "#f05a1a"),
    ]
    for col, label, color in left_series:
        sub = plot_df.dropna(subset=[col])
        axes[0].plot(sub["date"], sub[col], color=color, linewidth=2.8, label=label)
    for col, label, color in right_series:
        sub = plot_df.dropna(subset=[col])
        axes[1].plot(sub["date"], sub[col], color=color, linewidth=2.8, label=label)

    axes[0].set_title("一般公共预算收支累计同比（%）", loc="left", fontsize=13.2, fontweight="bold", pad=10)
    axes[1].set_title("一般公共预算央地收入分化（%）", loc="left", fontsize=13.2, fontweight="bold", pad=10)
    axes[0].set_ylabel("累计同比（%）", fontsize=11.5)
    axes[0].legend(loc="upper center", frameon=False, fontsize=9.7)
    axes[1].legend(loc="upper center", frameon=False, fontsize=9.7)
    for ax in axes:
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        ax.set_xlim(plot_df["date"].min() - pd.Timedelta(days=12), plot_df["date"].max() + pd.Timedelta(days=18))

    label_specs = [
        (axes[0], "budget_revenue_ytd_yoy", "#e9a7b6", "收入"),
        (axes[0], "budget_expenditure_ytd_yoy", "#2f6f9f", "支出"),
        (axes[1], "central_revenue_ytd_yoy", "#12949d", "中央"),
        (axes[1], "local_revenue_ytd_yoy", "#f05a1a", "地方"),
    ]
    for ax, col, color, label in label_specs:
        if col in latest and pd.notna(latest[col]):
            ax.annotate(
                f"{label} {latest[col]:+.1f}%",
                xy=(latest["date"], latest[col]),
                xytext=(8, 0),
                textcoords="offset points",
                va="center",
                fontsize=9.2,
                color=color,
            )

    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return {"path": str(out_path.relative_to(ROOT)), "last_date": latest_date}


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

    plot_df = df.copy()
    pctile_cols = ["pe_ttm_pctile_10y", "pb_lf_pctile_10y", "amount_pctile_5y"]
    for col in pctile_cols:
        plot_df[col] = pd.to_numeric(plot_df[col], errors="coerce")
    if "crowding_score" in plot_df.columns:
        plot_df["crowding_score"] = pd.to_numeric(plot_df["crowding_score"], errors="coerce")
    else:
        plot_df["crowding_score"] = plot_df[pctile_cols].mean(axis=1)
    plot_df = plot_df.sort_values("crowding_score", ascending=True).reset_index(drop=True)
    metrics = [
        ("pe_ttm_pctile_10y", "PE_TTM十年分位", "pe_ttm_pctile_10y_wow"),
        ("pb_lf_pctile_10y", "PB_LF十年分位", "pb_lf_pctile_10y_wow"),
        ("amount_pctile_5y", "成交额五年分位", "amount_pctile_5y_wow"),
        ("crowding_score", "综合拥挤度（三指标均值）", None),
    ]
    latest_date = str(plot_df["date"].max())
    fig_h = max(8.5, len(plot_df) * 0.34 + 2.2)
    fig, ax = plt.subplots(figsize=(17.5, fig_h), dpi=180)
    fig.patch.set_facecolor("#fbfbf8")
    ax.set_facecolor("#fbfbf8")
    for x_pos, (col, _label, wow_col) in enumerate(metrics):
        values = pd.to_numeric(plot_df[col], errors="coerce")
        is_composite = col == "crowding_score"
        sc = ax.scatter(
            [x_pos] * len(plot_df),
            range(len(plot_df)),
            c=values,
            s=290 if is_composite else 210,
            cmap="RdYlGn_r",
            vmin=0,
            vmax=100,
            edgecolor="#293642" if is_composite else "#ffffff",
            linewidth=1.1 if is_composite else 0.9,
            zorder=3,
        )
        for y_pos, (_, row) in enumerate(plot_df.iterrows()):
            value = row[col]
            wow = row.get(wow_col) if wow_col else None
            if pd.isna(value):
                label = "NA"
            elif is_composite or pd.isna(wow):
                label = f"{value:.1f}" if is_composite else f"{value:.0f}%"
            else:
                sign = "+" if wow > 0 else ""
                label = f"{value:.0f}% ({sign}{wow:.0f})"
            ax.text(
                x_pos + 0.12,
                y_pos,
                label,
                va="center",
                ha="left",
                fontsize=9.6 if is_composite else 9.2,
                fontweight="bold" if is_composite else "normal",
                color="#203040" if is_composite else "#293642",
            )
    ax.axvline(len(metrics) - 1.5, linestyle="--", color="#b8b3a8", linewidth=1.0, alpha=0.8)
    ax.set_yticks(range(len(plot_df)), plot_df["industry"])
    ax.set_xticks(range(len(metrics)), [label for _col, label, _wow_col in metrics])
    ax.tick_params(axis="x", labelsize=11, pad=10)
    ax.tick_params(axis="y", labelsize=9.5)
    ax.set_xlim(-0.45, len(metrics) - 0.05)
    ax.set_ylim(-0.8, len(plot_df) - 0.2)
    ax.grid(axis="y", color="#e2dfd7", linewidth=0.7, alpha=0.75)
    ax.text(0, 1.015, "按综合拥挤度（三项分位均值）从高到低排序；括号内为较上周变化，单位：百分点；颜色越红代表分位越高。", transform=ax.transAxes, fontsize=10.5, color="#59636e")
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


def draw_industry_pb_roe_chart(weekly_df: pd.DataFrame | None, crowding_df: pd.DataFrame | None, out_path: Path) -> dict | None:
    """中信一级行业 PB-ROE 散点(最新周)。ROE_TTM 由 PB/PE 恒等式推导。"""
    setup_fonts()
    if weekly_df is None or weekly_df.empty:
        return None
    latest_date = str(weekly_df["date"].max())
    prev_dates = sorted(pd.Series(weekly_df["date"].dropna().unique()).astype(str))
    prev_date = prev_dates[-2] if len(prev_dates) >= 2 else None
    df = weekly_df[weekly_df["date"].eq(weekly_df["date"].max())].copy()
    df["roe_ttm"] = pd.to_numeric(df["pb_lf"], errors="coerce") / pd.to_numeric(df["pe_ttm"], errors="coerce") * 100
    df = df.dropna(subset=["roe_ttm", "pb_lf"])
    if prev_date:
        prev = weekly_df[weekly_df["date"].eq(prev_date)].copy()
        prev["prev_roe_ttm"] = pd.to_numeric(prev["pb_lf"], errors="coerce") / pd.to_numeric(prev["pe_ttm"], errors="coerce") * 100
        prev = prev.rename(columns={"pb_lf": "prev_pb_lf"})[["industry", "prev_roe_ttm", "prev_pb_lf"]]
        df = df.merge(prev, on="industry", how="left")
        df["roe_change"] = df["roe_ttm"] - pd.to_numeric(df["prev_roe_ttm"], errors="coerce")
        df["pb_change"] = pd.to_numeric(df["pb_lf"], errors="coerce") - pd.to_numeric(df["prev_pb_lf"], errors="coerce")
    else:
        df["roe_change"] = pd.NA
        df["pb_change"] = pd.NA
    if crowding_df is not None and not crowding_df.empty:
        pct = crowding_df[["industry", "pb_lf_pctile_10y"]].drop_duplicates("industry")
        df = df.merge(pct, on="industry", how="left")
    else:
        df["pb_lf_pctile_10y"] = None
    if df.empty:
        return None

    fig, ax = plt.subplots(figsize=(15.5, 9), dpi=180)
    fig.patch.set_facecolor("#fbfbf8")
    ax.set_facecolor("#fbfbf8")
    colors = pd.to_numeric(df["pb_lf_pctile_10y"], errors="coerce")
    sc = ax.scatter(
        df["roe_ttm"],
        df["pb_lf"],
        c=colors,
        s=220,
        cmap="RdYlGn_r",
        vmin=0,
        vmax=100,
        edgecolor="#ffffff",
        linewidth=1.0,
        zorder=3,
    )
    move_df = df.dropna(subset=["prev_roe_ttm", "prev_pb_lf", "roe_ttm", "pb_lf"]).copy()
    if not move_df.empty:
        ax.scatter(
            move_df["prev_roe_ttm"],
            move_df["prev_pb_lf"],
            s=70,
            color="#9aa3ad",
            alpha=0.45,
            edgecolor="#ffffff",
            linewidth=0.6,
            label=f"上一期 {prev_date}",
            zorder=2,
        )
        for _, row in move_df.iterrows():
            ax.annotate(
                "",
                xy=(row["roe_ttm"], row["pb_lf"]),
                xytext=(row["prev_roe_ttm"], row["prev_pb_lf"]),
                arrowprops={
                    "arrowstyle": "->",
                    "color": "#59636e",
                    "lw": 0.9,
                    "alpha": 0.58,
                    "shrinkA": 4,
                    "shrinkB": 7,
                },
                zorder=2,
            )
    offsets = [(10, 6), (10, -12), (-10, 8), (-10, -12)]
    for idx, (_, row) in enumerate(df.iterrows()):
        dx, dy = offsets[idx % len(offsets)]
        ha = "left" if dx > 0 else "right"
        change_label = ""
        if pd.notna(row.get("roe_change")) and pd.notna(row.get("pb_change")):
            change_label = f"\nROE {row['roe_change']:+.1f}pct / PB {row['pb_change']:+.2f}"
        ax.annotate(
            f"{row['industry']}{change_label}",
            xy=(row["roe_ttm"], row["pb_lf"]),
            xytext=(dx, dy),
            textcoords="offset points",
            fontsize=8.4,
            ha=ha,
            color="#293642",
        )
    x_med, y_med = df["roe_ttm"].median(), df["pb_lf"].median()
    ax.axvline(x_med, linestyle="--", color="#8a93a1", linewidth=1.0, alpha=0.8)
    ax.axhline(y_med, linestyle="--", color="#8a93a1", linewidth=1.0, alpha=0.8)
    x_max, y_max = df["roe_ttm"].max(), df["pb_lf"].max()
    ax.text(x_max, y_med, "高ROE", fontsize=9.5, color="#8a93a1", va="center", ha="right")
    ax.text(x_med, y_max, "高PB", fontsize=9.5, color="#8a93a1", va="top", ha="center")
    ax.set_xlabel("ROE_TTM（%，由 PB/PE 推导）", fontsize=12)
    ax.set_ylabel("PB_LF（倍）", fontsize=12)
    ax.grid(color="#e3e3e3", linewidth=0.7, alpha=0.6)
    ax.spines[["top", "right"]].set_visible(False)
    missing = sorted(set(weekly_df[weekly_df["date"].eq(weekly_df["date"].max())]["industry"]) - set(df["industry"]))
    note = f"箭头由上一期({prev_date or '无'})指向最新一期；虚线为中位数；颜色=PB十年分位(越红越高)。PE_TTM 缺失(亏损)未入图：{'、'.join(missing) if missing else '无'}"
    ax.text(0, 1.02, note, transform=ax.transAxes, fontsize=10, color="#59636e")
    if not move_df.empty:
        ax.legend(loc="lower right", frameon=False, fontsize=9.5)
    cbar = fig.colorbar(sc, ax=ax, fraction=0.03, pad=0.02)
    cbar.set_label("PB 十年分位（%）")
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return {"path": str(out_path.relative_to(ROOT)), "last_date": latest_date}


def draw_industrial_profits_chart(df: pd.DataFrame | None, out_path: Path) -> dict | None:
    """工业企业利润年度同比折线 + 当年三种节奏外推。"""
    setup_fonts()
    if df is None or df.empty:
        return None
    data = df.copy()
    data["date"] = pd.to_datetime(data["date"])
    data = data.dropna(subset=["date", "cum_value"]).sort_values("date")
    data["year"] = data["date"].dt.year
    data["month"] = data["date"].dt.month

    latest = data.iloc[-1]
    cy, cm = int(latest["year"]), int(latest["month"])
    latest_date = latest["date"].strftime("%Y-%m")
    full_year = data[data["month"].eq(12)].set_index("year")["cum_value"]
    if cy - 1 not in full_year.index:
        return None

    # 各历史年份在月份 cm 的"累计利润占全年比例"
    share_by_year: dict[int, float] = {}
    for y in range(cy - 5, cy):
        cum_m = data[(data["year"].eq(y)) & (data["month"].eq(cm))]["cum_value"]
        if y in full_year.index and not cum_m.empty and full_year[y]:
            share_by_year[y] = float(cum_m.iloc[0]) / float(full_year[y])

    projections: dict[str, float] = {}
    for label, years in [("近1年", [cy - 1]), ("近3年", list(range(cy - 3, cy))), ("近5年", list(range(cy - 5, cy)))]:
        vals = [share_by_year[y] for y in years if y in share_by_year]
        if vals:
            avg_share = sum(vals) / len(vals)
            est_full = float(latest["cum_value"]) / avg_share
            projections[label] = (est_full / float(full_year[cy - 1]) - 1) * 100
    if not projections:
        return None

    fig, ax = plt.subplots(figsize=(15.5, 7.8), dpi=180)
    fig.patch.set_facecolor("#fbfbf8")
    ax.set_facecolor("#fbfbf8")

    yoy_dec: dict[int, float] = {}
    for y in sorted(data["year"].unique()):
        dec = data[(data["year"].eq(y)) & (data["month"].eq(12))]["cum_yoy"]
        if y != cy and not dec.empty and pd.notna(dec.iloc[0]):
            yoy_dec[y] = float(dec.iloc[0])
    latest_yoy = float(latest["cum_yoy"]) if pd.notna(latest.get("cum_yoy")) else float("nan")

    hist_years = sorted(yoy_dec)
    hist_vals = [yoy_dec[y] for y in hist_years]
    ax.plot(hist_years, hist_vals, color="#1f6fb2", linewidth=2.4, marker="o", markersize=5.2, label="年度同比")
    for y, value in zip(hist_years, hist_vals):
        ax.text(y, value + (1.2 if value >= 0 else -1.2), f"{value:+.1f}", ha="center", va="bottom" if value >= 0 else "top", fontsize=9.3, color="#1f6fb2")

    proj_colors = {"近1年": "#c5513c", "近3年": "#e07b39", "近5年": "#8a6d1f"}
    last_hist_year = max(hist_years)
    last_hist_value = yoy_dec[last_hist_year]
    for label, value in projections.items():
        color = proj_colors[label]
        ax.plot([last_hist_year, cy], [last_hist_value, value], linestyle="--", color=color, linewidth=1.8, marker="o", markersize=4.6, label=f"{cy}外推（{label}节奏）")
        ax.text(cy + 0.05, value, f"{label} {value:+.1f}%", color=color, fontsize=10, va="center", ha="left")

    if pd.notna(latest_yoy):
        ax.scatter([cy], [latest_yoy], s=82, color="#203040", edgecolor="#ffffff", linewidth=1.0, zorder=5, label=f"{cy}最新实际累计同比")
        ax.text(cy + 0.05, latest_yoy, f"{cy}年1-{cm}月实际 {latest_yoy:+.1f}%", color="#203040", fontsize=11, fontweight="bold", va="center", ha="left")

    ax.axhline(0, color="#8a93a1", linewidth=0.9, alpha=0.7)
    ax.set_xticks(hist_years + [cy])
    ax.set_xticklabels([str(y) for y in hist_years] + [f"{cy}E"], fontsize=10.5)
    all_vals = list(yoy_dec.values()) + list(projections.values()) + ([] if pd.isna(latest_yoy) else [latest_yoy])
    ax.set_ylim(min(0, min(all_vals) - 10), max(all_vals) + 12)
    ax.set_xlim(min(hist_years) - 0.5, cy + 1.2)
    ax.set_ylabel("规模以上工业企业利润年度同比（%）", fontsize=12)
    ax.grid(axis="y", color="#e3e3e3", linewidth=0.7, alpha=0.6)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="upper left", ncol=2, frameon=False, fontsize=10)

    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return {
        "path": str(out_path.relative_to(ROOT)),
        "last_date": latest_date,
        "latest_cum_yoy": latest_yoy,
        "current_month": cm,
        "current_year": cy,
        "proj_1y": projections.get("近1年"),
        "proj_3y": projections.get("近3年"),
        "proj_5y": projections.get("近5年"),
    }


def draw_valuation_chart(df: pd.DataFrame, index_name: str, out_path: Path) -> dict:
    setup_fonts()
    plot_df = df[df["index_name"].eq(index_name)].copy().sort_values("date")
    if plot_df.empty:
        return {}
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
    return {"path": str(out_path.relative_to(ROOT)), "last_date": latest_date, "title": f"{index_name}历史滚动市盈率及标准差通道（截至{latest_date}）"}


def draw_sentiment_chart(df: pd.DataFrame, metadata: dict, out_path: Path) -> dict | None:
    setup_fonts()
    if df is None or df.empty:
        return None
    plot_df = df.copy()
    plot_df["date"] = pd.to_datetime(plot_df["date"])
    plot_df = plot_df.dropna(subset=["sentiment_3y"]).sort_values("date")
    plot_df = plot_df[plot_df["date"].ge(plot_df["date"].max() - pd.DateOffset(years=3))]
    latest = plot_df.iloc[-1]
    latest_date = latest["date"].strftime("%Y-%m-%d")
    latest_val = latest["sentiment_3y"]

    fig = plt.figure(figsize=(16, 7.6), dpi=180)
    gs = fig.add_gridspec(1, 2, width_ratios=[3.2, 1.0], wspace=0.20, left=0.055, right=0.985, top=0.93, bottom=0.09)
    fig.patch.set_facecolor("#fbfbf8")
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.set_facecolor("#fbfbf8")
    ax2 = ax1.twinx()
    ax2.plot(plot_df["date"], plot_df["close"], color="#98a2b3", linewidth=1.6, alpha=0.85, label="上证指数（右轴）")
    for level, color, label in [(0.8, "#c5513c", "过热 0.8"), (0.5, "#8a93a1", "中性 0.5"), (0.2, "#2a9d55", "过冷 0.2")]:
        ax1.axhline(level, linestyle="--", color=color, linewidth=1.1, alpha=0.85)
        ax1.text(plot_df["date"].min(), level + 0.012, label, fontsize=9.5, color=color, va="bottom")
    ax1.fill_between(plot_df["date"], plot_df["sentiment_3y"], 0, color="#e07b39", alpha=0.10, linewidth=0)
    ax1.plot(plot_df["date"], plot_df["sentiment_3y"], color="#e07b39", linewidth=2.4, label="等权情绪指数（3年分位）")
    zone, zcolor = ("过热区", "#c5513c") if latest_val >= 0.8 else ("过冷区", "#2a9d55") if latest_val <= 0.2 else ("中性区", "#8a6d1f")
    ax1.annotate(
        f"{latest_date}  情绪 {latest_val:.2f}（{zone}）",
        xy=(latest["date"], latest_val),
        xytext=(-10, 22),
        textcoords="offset points",
        ha="right",
        va="bottom",
        fontsize=11,
        color=zcolor,
        bbox={"boxstyle": "round,pad=0.3", "facecolor": "#ffffff", "edgecolor": "#d0d0d0", "alpha": 0.92},
    )
    ax1.set_ylim(0, 1.05)
    ax1.set_ylabel("情绪指数（0–1，等权，3年分位）", fontsize=12)
    ax2.tick_params(axis="y", labelsize=9, pad=2)
    ax1.set_xlabel("日期", fontsize=12)
    ax1.grid(axis="y", color="#e3e3e3", linewidth=0.7, alpha=0.6)
    ax1.grid(axis="x", color="#eeeeee", linewidth=0.5, alpha=0.45)
    ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", ncol=2, frameon=False, fontsize=10)
    ax1.spines[["top", "right"]].set_visible(False)
    ax2.spines[["top", "left"]].set_visible(False)

    comp_specs = [
        ("股债收益差", "pe_spread_pct3"),
        ("换手率(20日均)", "turn_ma20_pct3"),
        ("流动性冲击", "ls_pct3"),
        ("新发基金占比", "fund30_pct3"),
        ("乖离率(250日)", "bias250_pct3"),
        ("RSI(90日)", "rsi90_pct3"),
    ]
    comp_names, comp_vals = [], []
    for name, col in comp_specs:
        val = latest.get(col)
        if pd.notna(val):
            comp_names.append(name)
            comp_vals.append(float(val))
    axb = fig.add_subplot(gs[0, 1])
    axb.set_facecolor("#fbfbf8")
    ypos = range(len(comp_vals) - 1, -1, -1)
    bar_colors = ["#c5513c" if v >= 0.8 else "#2a9d55" if v <= 0.2 else "#e07b39" for v in comp_vals]
    axb.barh(list(ypos), comp_vals, height=0.58, color=bar_colors, alpha=0.88)
    for y, v in zip(ypos, comp_vals):
        axb.text(min(v + 0.025, 0.97), y, f"{v:.2f}", va="center", fontsize=10.5, color="#4a4a4a")
    for level, color in [(0.2, "#2a9d55"), (0.5, "#8a93a1"), (0.8, "#c5513c")]:
        axb.axvline(level, linestyle="--", color=color, linewidth=0.9, alpha=0.7)
    axb.set_yticks(list(ypos))
    axb.set_yticklabels(comp_names, fontsize=10.5)
    axb.set_xlim(0, 1.0)
    axb.set_xticks([0, 0.2, 0.5, 0.8, 1.0])
    axb.tick_params(axis="x", labelsize=9)
    axb.set_title(f"分项当前分位（{latest_date}）", fontsize=11.5, color="#4a4a4a", pad=10)
    axb.grid(axis="x", color="#e3e3e3", linewidth=0.7, alpha=0.6)
    axb.spines[["top", "right", "left"]].set_visible(False)

    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return {"path": str(out_path.relative_to(ROOT)), "last_date": latest_date, "value": float(latest_val)}


def draw_value_growth_spread_chart(df: pd.DataFrame, out_path: Path) -> dict | None:
    setup_fonts()
    if df is None or df.empty:
        return None
    plot_df = df.copy()
    plot_df["date"] = pd.to_datetime(plot_df["date"])
    for col in ["dividend_yield", "growth_earnings_yield", "spread"]:
        plot_df[col] = pd.to_numeric(plot_df[col], errors="coerce")
    plot_df = plot_df.dropna(subset=["spread"]).sort_values("date")
    if plot_df.empty:
        return None
    latest = plot_df.iloc[-1]
    latest_date = latest["date"].strftime("%Y-%m-%d")
    min_row = plot_df.loc[plot_df["spread"].idxmin()]
    max_row = plot_df.loc[plot_df["spread"].idxmax()]

    fig, ax = plt.subplots(figsize=(16, 7.2), dpi=180)
    fig.patch.set_facecolor("#fbfbf8")
    ax.set_facecolor("#fbfbf8")
    ax.plot(plot_df["date"], plot_df["spread"], color="#1f77b4", linewidth=2.3, label="价值成长风格价差")
    ax.axhline(max_row["spread"], linestyle="--", color="#c5513c", linewidth=1.2, alpha=0.85, label=f"历史上限 {max_row['spread']:.2f}%")
    ax.axhline(min_row["spread"], linestyle="--", color="#2a9d55", linewidth=1.2, alpha=0.85, label=f"历史下限 {min_row['spread']:.2f}%")
    ax.fill_between(
        plot_df["date"],
        min_row["spread"],
        max_row["spread"],
        color="#e3e7ee",
        alpha=0.22,
        linewidth=0,
        label="历史极值区间",
    )
    ax.annotate(
        f"{latest_date}  {latest['spread']:.2f}%",
        xy=(latest["date"], latest["spread"]),
        xytext=(10, 0),
        textcoords="offset points",
        va="center",
        fontsize=10.5,
        color="#1f77b4",
        bbox={"boxstyle": "round,pad=0.25", "facecolor": "#ffffff", "edgecolor": "#d0d0d0", "alpha": 0.9},
    )
    ax.annotate(
        f"上限 {max_row['date'].strftime('%Y-%m-%d')}",
        xy=(max_row["date"], max_row["spread"]),
        xytext=(8, 10),
        textcoords="offset points",
        fontsize=9.5,
        color="#c5513c",
    )
    ax.annotate(
        f"下限 {min_row['date'].strftime('%Y-%m-%d')}",
        xy=(min_row["date"], min_row["spread"]),
        xytext=(8, -16),
        textcoords="offset points",
        fontsize=9.5,
        color="#2a9d55",
    )
    ax.set_title("价值成长风格价差", fontsize=17, fontweight="bold", loc="left", pad=12)
    ax.set_xlabel("日期", fontsize=12)
    ax.set_ylabel("价差（百分点）", fontsize=12)
    ax.grid(axis="y", color="#d8d8d8", linewidth=0.8, alpha=0.65)
    ax.grid(axis="x", color="#eeeeee", linewidth=0.5, alpha=0.45)
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.set_xlim(plot_df["date"].min(), plot_df["date"].max() + pd.Timedelta(days=30))
    ax.legend(loc="upper left", ncol=4, frameon=False, fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return {
        "path": str(out_path.relative_to(ROOT)),
        "last_date": latest_date,
        "min": float(min_row["spread"]),
        "max": float(max_row["spread"]),
    }


def draw_citic_pb_dispersion_chart(df: pd.DataFrame, out_path: Path) -> dict | None:
    setup_fonts()
    if df is None or df.empty:
        return None
    plot_df = df.copy()
    plot_df["date"] = pd.to_datetime(plot_df["date"])
    plot_df["wind_all_a_close"] = pd.to_numeric(plot_df["wind_all_a_close"], errors="coerce")
    plot_df["pb_dispersion_ma5"] = pd.to_numeric(plot_df["pb_dispersion_ma5"], errors="coerce")
    plot_df = plot_df.dropna(subset=["pb_dispersion_ma5"]).sort_values("date")
    if plot_df.empty:
        return None
    latest = plot_df.iloc[-1]
    latest_date = latest["date"].strftime("%Y-%m-%d")

    fig, ax1 = plt.subplots(figsize=(16, 7.2), dpi=180)
    fig.patch.set_facecolor("#fbfbf8")
    ax1.set_facecolor("#fbfbf8")
    ax2 = ax1.twinx()
    ax1.plot(plot_df["date"], plot_df["wind_all_a_close"], color="#7a6f64", linewidth=1.8, alpha=0.9, label="万得全A收盘价")
    ax2.plot(plot_df["date"], plot_df["pb_dispersion_ma5"], color="#1f77b4", linewidth=2.2, label="PB分位标准差MA5")
    if pd.notna(latest["wind_all_a_close"]):
        ax1.annotate(
            f"{latest_date}  {latest['wind_all_a_close']:,.0f}",
            xy=(latest["date"], latest["wind_all_a_close"]),
            xytext=(10, 0),
            textcoords="offset points",
            va="center",
            fontsize=10,
            color="#7a6f64",
        )
    ax2.annotate(
        f"{latest_date}  {latest['pb_dispersion_ma5']:.3f}",
        xy=(latest["date"], latest["pb_dispersion_ma5"]),
        xytext=(10, 0),
        textcoords="offset points",
        va="center",
        fontsize=10,
        color="#1f77b4",
        bbox={"boxstyle": "round,pad=0.25", "facecolor": "#ffffff", "edgecolor": "#d0d0d0", "alpha": 0.9},
    )
    ax1.set_title("中信一级行业估值离散度", fontsize=17, fontweight="bold", loc="left", pad=12)
    ax1.set_xlabel("日期", fontsize=12)
    ax1.set_ylabel("万得全A收盘价（点）", fontsize=12)
    ax2.set_ylabel("PB历史分位标准差MA5", fontsize=12)
    ax1.grid(axis="y", color="#d8d8d8", linewidth=0.8, alpha=0.65)
    ax1.grid(axis="x", color="#eeeeee", linewidth=0.5, alpha=0.45)
    ax1.xaxis.set_major_locator(mdates.YearLocator(base=2))
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax1.set_xlim(plot_df["date"].min(), plot_df["date"].max() + pd.Timedelta(days=90))
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", ncol=2, frameon=False, fontsize=10)
    ax1.spines[["top", "right"]].set_visible(False)
    ax2.spines[["top", "left"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return {"path": str(out_path.relative_to(ROOT)), "last_date": latest_date}


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


def render_limit_up_table(title: str, df: pd.DataFrame | None, latest_date: str, chart_key: str) -> str:
    note_html = chart_note_block(
        "涨停股池来自东方财富公开接口；主营业务来自巨潮公司概况。公开涨停池未披露逐股原因，原因字段先按所属行业、连板数和涨停统计归纳。",
        "涨停原因不是交易所官方逐股披露结论，仅用于快速观察；若个股信息为空或异常，通常代表公开接口尚未更新或公司概况抓取失败。",
        chart_key,
    )
    if df is None or df.empty:
        return f'''      <section class="chart-section">
        <h2>{title}（截至{latest_date or "待接入"}）{freq_badge("日频")}</h2>
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
        <h2>{title}（截至{latest_date}）{freq_badge("日频")}</h2>
        <div class="table-wrap"><table class="data-table"><thead><tr>{thead}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>
        {note_html}
      </section>'''


def freq_badge(freq: str) -> str:
    return f'<span class="freq-badge">{freq}</span>'


EQUITY_ORDER = ["沪深300", "300收益", "上证指数", "万得全A", "恒生指数", "恒生科技指数", "中证红利"]
RATE_ORDER = ["7天逆回购利率", "DR007(FDR007定盘)", "10年期国债", "30年期国债", "5年期AAA企业债(中短票)", "银行二级资本债AAA-(5年)"]


def render_market_monitor(indices: pd.DataFrame | None, breadth: pd.DataFrame | None, rates: pd.DataFrame | None) -> str:
    note_html = chart_note_block(
        "权益指数来自东方财富、中证指数官网、新浪财经与 Wind(万得全A);市场宽度按东方财富全A快照统计;利率来自中国货币网与 Wind(7天逆回购)。DR007 用银银间回购定盘利率 FDR007 展示;5年期AAA企业债用中短期票据(AAA)收益率曲线;二级资本债取 AAA- 5年期。",
        "不同数据源口径存在细微差异;公开接口若临时不可用,对应指标会显示上一可得交易日数据或待更新。",
        "market_monitor",
    )
    sections: list[str] = []
    latest_dates: list[str] = []

    # ---------- 权益 ----------
    eq_rows = []
    if indices is not None and not indices.empty:
        indices = indices.copy()
        latest_dates.append(str(indices["date"].max()))
        for name in EQUITY_ORDER:
            sub = indices[indices["index"].eq(name)].sort_values("date")
            if sub.empty:
                eq_rows.append(f"<tr><td>{name}</td><td>—</td><td>—</td></tr>")
                continue
            last = sub.iloc[-1]
            pct = last.get("change_pct")
            pct_text = "—" if pd.isna(pct) else f"{float(pct):+.2f}%"
            pct_class = "" if pd.isna(pct) else ("pos" if pct > 0 else "neg" if pct < 0 else "")
            eq_rows.append(
                f'<tr><td>{name}</td><td>{float(last["close"]):,.2f}</td>'
                f'<td class="{pct_class}">{pct_text}</td></tr>'
            )
    equity_table = (
        '<div class="monitor-block"><h3>权益</h3>'
        '<div class="table-wrap"><table class="data-table monitor-table">'
        "<thead><tr><th>指数</th><th>点位</th><th>涨跌幅</th></tr></thead>"
        f'<tbody>{"".join(eq_rows)}</tbody></table></div></div>'
    )
    sections.append(equity_table)

    # ---------- 市场宽度 ----------
    if breadth is not None and not breadth.empty:
        breadth = breadth.sort_values("date")
        latest_dates.append(str(breadth["date"].max()))
        cur = breadth.iloc[-1]
        prev = breadth.iloc[-2] if len(breadth) >= 2 else None

        def diff_text(col: str, fmt: str, scale: float = 1.0) -> str:
            if prev is None or pd.isna(prev.get(col)) or pd.isna(cur.get(col)):
                return "—"
            diff = (float(cur[col]) - float(prev[col])) * scale
            cls = "pos" if diff > 0 else "neg" if diff < 0 else ""
            return f'<span class="{cls}">{fmt.format(diff)}</span>'

        breadth_rows = [
            ("上涨股票数量(家)", f"{int(cur['up_count'])}", diff_text("up_count", "{:+.0f}")),
            ("下跌股票数量(家)", f"{int(cur['down_count'])}", diff_text("down_count", "{:+.0f}")),
            ("中位数涨跌幅(%)", f"{float(cur['median_pct']):.2f}", diff_text("median_pct", "{:+.2f}")),
            ("平均涨跌幅(%)", f"{float(cur['mean_pct']):.2f}", diff_text("mean_pct", "{:+.2f}")),
            ("全A成交额(亿元)", f"{float(cur['amount_100mn']):,.0f}", diff_text("amount_100mn", "{:+,.0f}")),
        ]
        body = "".join(f"<tr><td>{n}</td><td>{v}</td><td>{d}</td></tr>" for n, v, d in breadth_rows)
        width_table = (
            '<div class="monitor-block"><h3>市场宽度</h3>'
            '<div class="table-wrap"><table class="data-table monitor-table">'
            f"<thead><tr><th>指标</th><th>当日({cur['date']})</th><th>较前一日变化</th></tr></thead>"
            f"<tbody>{body}</tbody></table></div></div>"
        )
    else:
        width_table = '<div class="monitor-block"><h3>市场宽度</h3><p class="empty-note">待更新:公开快照接口暂不可用,将于下次定时任务自动补齐。</p></div>'
    sections.append(width_table)

    # ---------- 固收 ----------
    rate_rows = []
    if rates is not None and not rates.empty:
        rates = rates.copy()
        latest_dates.append(str(rates["date"].max()))
        for name in RATE_ORDER:
            sub = rates[rates["rate"].eq(name)].sort_values("date")
            if sub.empty:
                rate_rows.append(f"<tr><td>{name}</td><td>—</td><td>—</td><td>—</td></tr>")
                continue
            cur_r = sub.iloc[-1]
            prev_r = sub.iloc[-2] if len(sub) >= 2 else None
            prev_text = "—" if prev_r is None else f"{float(prev_r['value']):.3f}"
            if prev_r is None:
                diff_text = "—"
            else:
                diff_bp = (float(cur_r["value"]) - float(prev_r["value"])) * 100
                cls = "neg" if diff_bp > 0 else "pos" if diff_bp < 0 else ""
                diff_text = f'<span class="{cls}">{diff_bp:+.1f}</span>'
            rate_rows.append(
                f"<tr><td>{name}</td><td>{float(cur_r['value']):.3f}</td>"
                f"<td>{prev_text}</td><td>{diff_text}</td></tr>"
            )
    rates_table = (
        '<div class="monitor-block"><h3>固收</h3>'
        '<div class="table-wrap"><table class="data-table monitor-table">'
        "<thead><tr><th>品种</th><th>当日(%)</th><th>上一交易日(%)</th><th>变化(bp)</th></tr></thead>"
        f'<tbody>{"".join(rate_rows)}</tbody></table></div></div>'
    )
    sections.append(rates_table)

    latest = max(latest_dates) if latest_dates else "待更新"
    return f'''      <section class="chart-section">
        <h2><span class="chart-num">A-001</span>行情监控面板（截至{latest}）{freq_badge("日频")}</h2>
        <div class="monitor-grid">{sections[0]}{sections[2]}</div>
        {sections[1]}
        {note_html}
      </section>'''


def render_market_brief(
    indices: pd.DataFrame | None,
    breadth: pd.DataFrame | None,
    market_turnover: pd.DataFrame | None,
    amount_share: pd.DataFrame | None,
    theme_amount: pd.DataFrame | None,
) -> str:
    lines: list[str] = []
    dates: list[str] = []

    if indices is not None and not indices.empty:
        idx = indices.copy()
        idx["date"] = pd.to_datetime(idx["date"], errors="coerce")
        idx["close"] = pd.to_numeric(idx["close"], errors="coerce")
        idx["change_pct"] = pd.to_numeric(idx["change_pct"], errors="coerce")
        latest_idx_date = idx[idx["index"].isin(["沪深300", "上证指数"])]["date"].max()
        latest = idx[idx["date"].eq(latest_idx_date)].set_index("index")
        dates.append(latest_idx_date.strftime("%Y-%m-%d"))
        parts = []
        for name in ["沪深300", "上证指数"]:
            if name in latest.index and pd.notna(latest.loc[name, "change_pct"]):
                parts.append(f"{name}{latest.loc[name, 'change_pct']:+.2f}%")
        if parts:
            lines.append(f"{latest_idx_date.strftime('%Y-%m-%d')}，主要A股指数偏弱，" + "、".join(parts) + "。")

    if market_turnover is not None and not market_turnover.empty:
        mt = market_turnover.copy().sort_values("date")
        mt["date"] = pd.to_datetime(mt["date"], errors="coerce")
        mt["market_turnover_100mn"] = pd.to_numeric(mt["market_turnover_100mn"], errors="coerce")
        mt["turnover_ma5_100mn"] = pd.to_numeric(mt.get("turnover_ma5_100mn"), errors="coerce")
        mt = mt.dropna(subset=["date", "market_turnover_100mn"])
        if not mt.empty:
            latest = mt.iloc[-1]
            dates.append(latest["date"].strftime("%Y-%m-%d"))
            prev = mt.iloc[-2] if len(mt) >= 2 else None
            wow = ""
            if prev is not None and prev["market_turnover_100mn"]:
                wow = f"，较上一日{(latest['market_turnover_100mn'] / prev['market_turnover_100mn'] - 1) * 100:+.1f}%"
            ma_note = ""
            if pd.notna(latest.get("turnover_ma5_100mn")) and latest["turnover_ma5_100mn"]:
                ma_note = f"，低于5日均值{(1 - latest['market_turnover_100mn'] / latest['turnover_ma5_100mn']) * 100:.1f}%"
            lines.append(f"全市场成交额约{latest['market_turnover_100mn']:,.0f}亿元{wow}{ma_note}。")

    if breadth is not None and not breadth.empty:
        br = breadth.copy().sort_values("date")
        br["date"] = pd.to_datetime(br["date"], errors="coerce")
        for col in ["up_count", "down_count", "median_pct"]:
            br[col] = pd.to_numeric(br[col], errors="coerce")
        latest = br.dropna(subset=["date"]).iloc[-1]
        dates.append(latest["date"].strftime("%Y-%m-%d"))
        if pd.notna(latest.get("up_count")) and pd.notna(latest.get("down_count")):
            lines.append(f"市场宽度最近一期为上涨{latest['up_count']:.0f}家、下跌{latest['down_count']:.0f}家，中位数涨跌幅{latest['median_pct']:+.2f}%。")

    if amount_share is not None and not amount_share.empty:
        share = amount_share.copy().sort_values("date")
        share["date"] = pd.to_datetime(share["date"], errors="coerce")
        for col in ["hs300_share_pct", "csi500_share_pct", "csi1000_share_pct", "csi2000_share_pct"]:
            share[col] = pd.to_numeric(share[col], errors="coerce")
        latest = share.dropna(subset=["date"]).iloc[-1]
        dates.append(latest["date"].strftime("%Y-%m-%d"))
        broad_sum = latest[["hs300_share_pct", "csi500_share_pct", "csi1000_share_pct", "csi2000_share_pct"]].sum()
        small_mid = latest[["csi1000_share_pct", "csi2000_share_pct"]].sum()
        theme_note = ""
        if theme_amount is not None and not theme_amount.empty:
            theme = theme_amount.copy().sort_values("date")
            theme["date"] = pd.to_datetime(theme["date"], errors="coerce")
            theme["tmt_share_pct"] = pd.to_numeric(theme["tmt_share_pct"], errors="coerce")
            theme["dividend_low_vol_share_pct"] = pd.to_numeric(theme["dividend_low_vol_share_pct"], errors="coerce")
            theme_latest = theme.dropna(subset=["date"]).iloc[-1]
            theme_note = f"；TMT成交占比{theme_latest['tmt_share_pct']:.1f}%，红利低波{theme_latest['dividend_low_vol_share_pct']:.1f}%"
        lines.append(f"主要宽基成交占全A代理口径约{broad_sum:.1f}%，其中中证1000+中证2000合计{small_mid:.1f}%{theme_note}。")

    if not lines:
        return ""
    latest_text = max(dates) if dates else ""
    items = "".join(f"<li>{escape(line)}</li>" for line in lines[:4])
    return f'''      <section class="market-brief">
        <div class="brief-kicker">市场简评{f"（截至{latest_text}）" if latest_text else ""}</div>
        <ul>{items}</ul>
      </section>'''


def normalize_date_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.notna(parsed):
        return parsed.strftime("%Y-%m-%d")
    return text


def compare_date_text(actual: str, expected: str, frequency: str) -> str:
    if frequency == "manual":
        return "manual"
    if not actual:
        return "missing"
    if not expected:
        return "unknown"
    if frequency == "monthly":
        return "ok" if actual[:7] >= expected[:7] else "lagging"
    return "ok" if actual >= expected else "lagging"


def status_label(status: str) -> str:
    return {
        "ok": "正常",
        "lagging": "滞后",
        "missing": "缺失",
        "manual": "不定期",
        "unknown": "待确认",
    }.get(status, status)


def build_chart_audit(chart_dates: dict[str, str], expected_dates: dict[str, str], build_time: str) -> list[dict]:
    audit = []
    for item in CHART_REGISTRY:
        key = item["key"]
        actual = normalize_date_text(chart_dates.get(key, ""))
        expected = normalize_date_text(expected_dates.get(item["frequency"], ""))
        status = compare_date_text(actual, expected, item["frequency"])
        audit.append({
            "key": key,
            "id": item["id"],
            "title": item["title"],
            "category": item["category"],
            "frequency": item["frequency"],
            "expected_date": expected,
            "actual_date": actual,
            "status": status,
            "status_label": status_label(status),
            "built_at": build_time,
        })
    return audit


def expected_daily_audit_date() -> str:
    """Most daily sources are stable after market close plus vendor lag."""
    now = pd.Timestamp.now()
    cutoff = now.normalize() + pd.Timedelta(hours=18, minutes=30)
    target = now.normalize() if now >= cutoff else now.normalize() - pd.offsets.BDay(1)
    return target.strftime("%Y-%m-%d")


def chart_status_line(chart_key: str | None) -> str:
    if not chart_key:
        return ""
    item = CURRENT_CHART_STATUS.get(chart_key)
    if not item:
        return ""
    status = escape(str(item["status_label"]))
    actual = escape(str(item.get("actual_date") or "暂无"))
    expected = escape(str(item.get("expected_date") or "不适用"))
    cls = escape(str(item.get("status") or "unknown"))
    return (
        f'<p class="chart-status status-{cls}"><strong>更新状态：</strong>'
        f'应更新日期 {expected}；实际日期 {actual}；状态 {status}。</p>'
    )


def chart_note_block(data_note: str, risk_note: str, chart_key: str | None = None) -> str:
    return f'''<div class="chart-notes">
          {chart_status_line(chart_key)}
          <p><strong>数据说明：</strong>{data_note}</p>
          <p><strong>风险提示：</strong>{risk_note}</p>
        </div>'''


def render_library() -> str:
    """Render the 资料 (research library) panel content from site/assets/docs/library.json."""
    manifest_path = SITE_DIR / "assets" / "docs" / "library.json"
    entries: list = []
    if manifest_path.exists():
        try:
            entries = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            entries = []
    if not entries:
        return '      <p class="empty-note">暂无资料。</p>'
    entries = sorted(entries, key=lambda x: str(x.get("date", "")), reverse=True)
    cards = []
    for item in entries:
        title = escape(str(item.get("title", "未命名资料")))
        file_url = escape(str(item.get("file", "")), quote=True)
        date = escape(str(item.get("date", "")))
        doc_type = escape(str(item.get("type", "PDF")))
        desc = escape(str(item.get("desc", "")))
        if not file_url:
            continue
        cards.append(f'''      <a class="doc-card" href="{file_url}" target="_blank" rel="noopener">
        <div class="doc-card-main">
          <span class="doc-type">{doc_type}</span>
          <h3>{title}</h3>
          <p>{desc}</p>
        </div>
        <div class="doc-card-meta"><span>{date}</span><span class="doc-open">查看 →</span></div>
      </a>''')
    if not cards:
        return '      <p class="empty-note">暂无资料。</p>'
    return f'''      <section class="chart-section">
        <h2><span class="chart-num">H-001</span>研究资料库（个人研究文章与投资资料）</h2>
        <div class="doc-list">
{chr(10).join(cards)}
        </div>
        <div class="chart-notes">
          {chart_status_line("library")}
          <p><strong>资料说明：</strong>本板块收录个人研究文章与投资资料，点击卡片可在新标签页打开对应文件；后续新增资料会按时间倒序追加。</p>
        </div>
      </section>'''


def build_page(
    metadata: dict,
    broad_chart: dict,
    star_chart: dict,
    chart3: dict,
    chart3_top10: dict,
    chart3_top100: dict,
    valuation_charts: list[dict],
    amount_share_chart: dict | None = None,
    industry_crowding_chart: dict | None = None,
    theme_amount_chart: dict | None = None,
    market_turnover_chart: dict | None = None,
    southbound_chart: dict | None = None,
    macro_chart: dict | None = None,
    macro_inventory_chart: dict | None = None,
    macro_m1_m2_chart: dict | None = None,
    macro_fiscal_chart: dict | None = None,
    macro_meta: dict | None = None,
    sentiment_chart: dict | None = None,
    sentiment_meta: dict | None = None,
    limit_up_longest: pd.DataFrame | None = None,
    limit_up_amount_top: pd.DataFrame | None = None,
    limit_up_meta: dict | None = None,
    monitor_indices: pd.DataFrame | None = None,
    monitor_breadth: pd.DataFrame | None = None,
    monitor_rates: pd.DataFrame | None = None,
    market_turnover_data: pd.DataFrame | None = None,
    amount_share_data: pd.DataFrame | None = None,
    theme_amount_data: pd.DataFrame | None = None,
    industry_pb_roe_chart: dict | None = None,
    industrial_profit_chart: dict | None = None,
    value_growth_spread_chart: dict | None = None,
    citic_pb_dispersion_chart: dict | None = None,
    hk_sentiment_chart: dict | None = None,
    hk_rates_chart: dict | None = None,
    hk_fx_chart: dict | None = None,
    hk_ah_chart: dict | None = None,
    hk_hsi_pe_chart: dict | None = None,
    hk_hsi_erp_chart: dict | None = None,
    hk_dividend_chart: dict | None = None,
) -> None:
    global CURRENT_CHART_STATUS
    assets_dir = SITE_DIR / "assets" / "charts"
    assets_dir.mkdir(parents=True, exist_ok=True)
    for chart_file in CHART_DIR.glob("*.png"):
        shutil.copy2(chart_file, assets_dir / chart_file.name)
    latest = metadata["latest_common_date"]
    build_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    asset_version = "".join(ch for ch in build_time if ch.isdigit())
    broad_etf_risk = "净流入为 0 或长时间缺失时，可能代表 ETF 份额未更新、接口未披露或数据源暂不可用，不应机械解读为真实无申赎。"
    star_etf_risk = "净流入为 0 或长时间缺失时，可能代表 ETF 份额未更新、接口未披露或数据源暂不可用，不应机械解读为真实无申赎。"
    valuation_date_by_key = {chart.get("key", ""): chart.get("last_date", "") for chart in valuation_charts}
    limit_up_date = (limit_up_meta or {}).get("latest_date", "")
    chart_dates = {
        "market_monitor": metadata.get("latest_common_date", ""),
        "market_turnover": (market_turnover_chart or {}).get("last_date", ""),
        "limit_up_longest": limit_up_date,
        "limit_up_amount_top": limit_up_date,
        "macro": (macro_chart or {}).get("last_date", ""),
        "macro_inventory": (macro_inventory_chart or {}).get("last_date", ""),
        "macro_m1_m2": (macro_m1_m2_chart or {}).get("last_date", ""),
        "macro_fiscal": (macro_fiscal_chart or {}).get("last_date", ""),
        "valuation_hs300": valuation_date_by_key.get("valuation_hs300", ""),
        "valuation_sse": valuation_date_by_key.get("valuation_sse", ""),
        "valuation_wind_all_a": valuation_date_by_key.get("valuation_wind_all_a", ""),
        "valuation_wind_all_a_ex_fin_petchem": valuation_date_by_key.get("valuation_wind_all_a_ex_fin_petchem", ""),
        "pb_roe": (industry_pb_roe_chart or {}).get("last_date", ""),
        "industrial_profits": (industrial_profit_chart or {}).get("last_date", ""),
        "southbound": (southbound_chart or {}).get("last_date", ""),
        "broad_etf_flow": (broad_chart or {}).get("last_date", ""),
        "star50_etf_flow": (star_chart or {}).get("last_date", ""),
        "sentiment": (sentiment_chart or {}).get("last_date", ""),
        "turnover_top10": (chart3_top10 or chart3 or {}).get("last_date", ""),
        "turnover_top100": (chart3_top100 or chart3 or {}).get("last_date", ""),
        "amount_share": (amount_share_chart or {}).get("last_date", ""),
        "theme_amount_share": (theme_amount_chart or {}).get("last_date", ""),
        "industry_crowding": (industry_crowding_chart or {}).get("last_date", ""),
        "value_growth_spread": (value_growth_spread_chart or {}).get("last_date", ""),
        "citic_pb_dispersion": (citic_pb_dispersion_chart or {}).get("last_date", ""),
        "hk_sentiment": (hk_sentiment_chart or {}).get("last_date", ""),
        "hk_rates": (hk_rates_chart or {}).get("last_date", ""),
        "hk_fx": (hk_fx_chart or {}).get("last_date", ""),
        "hk_ah_premium": (hk_ah_chart or {}).get("last_date", ""),
        "hk_hsi_pe": (hk_hsi_pe_chart or {}).get("last_date", ""),
        "hk_hsi_erp": (hk_hsi_erp_chart or {}).get("last_date", ""),
        "hk_dividend_yield": (hk_dividend_chart or {}).get("last_date", ""),
        "library": "",
    }
    daily_keys = {item["key"] for item in CHART_REGISTRY if item["frequency"] == "daily"}
    weekly_keys = {item["key"] for item in CHART_REGISTRY if item["frequency"] == "weekly"}
    monthly_keys = {item["key"] for item in CHART_REGISTRY if item["frequency"] == "monthly"}
    latest_daily = max((normalize_date_text(chart_dates[k]) for k in daily_keys if chart_dates.get(k)), default=latest)
    latest_weekly = max((normalize_date_text(chart_dates[k]) for k in weekly_keys if chart_dates.get(k)), default="")
    latest_macro = max((normalize_date_text(chart_dates[k]) for k in monthly_keys if chart_dates.get(k)), default="")
    expected_dates = {"daily": expected_daily_audit_date(), "weekly": latest_weekly, "monthly": latest_macro, "manual": ""}
    chart_audit = build_chart_audit(chart_dates, expected_dates, build_time)
    CURRENT_CHART_STATUS = {item["key"]: item for item in chart_audit}
    daily_lagging = sorted(k for k in daily_keys if CURRENT_CHART_STATUS.get(k, {}).get("status") == "lagging")
    market_brief_html = render_market_brief(monitor_indices, monitor_breadth, market_turnover_data, amount_share_data, theme_amount_data)
    market_monitor_html = render_market_monitor(monitor_indices, monitor_breadth, monitor_rates)
    valuation_sections = []
    for idx, chart in enumerate(valuation_charts):
        media = (
            f'<img src="assets/charts/{Path(chart["path"]).name}?v={asset_version}" alt="{chart["title"]}">'
            if chart.get("path")
            else '<p class="empty-note">暂无可展示数据，请先补充该指数 PE_TTM 时间序列。</p>'
        )
        valuation_sections.append(f'''      <section class="chart-section">
      <h2><span class="chart-num">{REGISTRY_BY_KEY[chart["key"]]["id"]}</span>{chart["title"]}{freq_badge("日频")}</h2>
      {media}
      {chart_note_block(
          f"统计区间自 {VALUATION_START_DATE} 起；PE_TTM 序列按交易日历史数据绘制，水平虚线分别为均值、均值±1倍标准差、均值±2倍标准差。",
          "估值分位和标准差通道仅反映历史相对位置，不代表合理估值中枢；若指数成分或口径调整，历史可比性会受影响；若状态为缺失，说明本地尚无该图所需 PE_TTM 序列。",
          chart.get("key"),
      )}
    </section>''')
    valuation_html = "\n\n".join(valuation_sections)
    pb_roe_html = ""
    if industry_pb_roe_chart:
        pb_roe_html = f'''      <section class="chart-section">
        <h2><span class="chart-num">C-005</span>中信一级行业 PB-ROE 对比（截至{industry_pb_roe_chart["last_date"]}）{freq_badge("周频")}</h2>
        <img src="assets/charts/{Path(industry_pb_roe_chart["path"]).name}?v={asset_version}" alt="中信一级行业 PB-ROE 对比">
        {chart_note_block(
            "ROE_TTM 由 PB/PE 恒等式推导(同一价格口径下 ROE≈PB/PE);PE_TTM 缺失(亏损状态)的行业不参与绘图。颜色代表 PB 十年分位,数据与中信拥挤度同为每周最后一个交易日更新。",
            "PB-ROE 是相对估值观察框架,不构成买卖建议;推导口径 ROE 与财报口径可能存在细微差异。",
            "pb_roe",
        )}
      </section>'''
    earnings_html = '<p class="empty-note">暂无图表。</p>'
    if industrial_profit_chart:
        ipc = industrial_profit_chart
        earnings_html = f'''      <section class="chart-section">
        <h2><span class="chart-num">D-001</span>工业企业利润同比与全年外推（截至{ipc["last_date"]}）{freq_badge("月频")}</h2>
        <img src="assets/charts/{Path(ipc["path"]).name}?v={asset_version}" alt="工业企业利润同比与全年外推">
        {chart_note_block(
            f"指标为规模以上工业企业利润总额年度同比(国家统计局,每月27日左右发布上月数据)。实线展示历史年度同比；{ipc['current_year']}年因尚未全年发布，以过去1年/3年/5年同期累计利润占全年比例的均值线性外推全年利润总额，再与上年全年实际利润比较得到隐含全年同比，图中以三条虚线表示——近1年节奏 {ipc['proj_1y']:+.1f}%、近3年 {ipc['proj_3y']:+.1f}%、近5年 {ipc['proj_5y']:+.1f}%。黑色标签展示{ipc['current_year']}年1-{ipc['current_month']}月累计同比实际值 {ipc['latest_cum_yoy']:+.1f}%。",
            "统计局对规模以上企业样本与基数有年度调整,官方同比与按累计额直接计算的同比存在口径差;外推基于季节性进度假设,下半年盈利节奏变化会使实际值偏离外推值,仅供参考。",
            "industrial_profits",
        )}
      </section>'''
    amount_share_html = ""
    if amount_share_chart:
        amount_share_html = f'''      <section class="chart-section">
        <h2><span class="chart-num">F-004</span>主要宽基指数成交额占全A成交额比例（截至{amount_share_chart["last_date"]}）{freq_badge("日频")}</h2>
        <img src="assets/charts/{Path(amount_share_chart["path"]).name}?v={asset_version}" alt="主要宽基指数成交额占全A成交额比例">
        {chart_note_block(
            "数据来自中证指数官网指数行情接口。分子为沪深300、中证500、中证1000、中证2000指数成交金额；分母优先使用 Wind 全A成交额，当前公开数据用中证全指成交金额作为代理口径。",
            "成交额占比受指数样本、停复牌、分母代理口径影响；若中证官网或代理分母未更新，最新日期可能滞后。",
            "amount_share",
        )}
      </section>'''
    theme_amount_html = ""
    if theme_amount_chart:
        theme_amount_html = f'''      <section class="chart-section">
        <h2><span class="chart-num">F-005</span>TMT与红利低波成交额占全A成交额比例（截至{theme_amount_chart["last_date"]}）{freq_badge("日频")}</h2>
        <img src="assets/charts/{Path(theme_amount_chart["path"]).name}?v={asset_version}" alt="TMT与红利低波成交额占全A成交额比例">
        {chart_note_block(
            "分子为中证TMT（000998）和中证红利低波动指数（H30269）成交金额；分母与图五保持一致，使用中证全指成交金额作为 Wind 全A 成交额公开代理口径。",
            "主题指数成交额不能等同于板块全部股票成交额；红利低波使用右轴展示，读取时应关注左右轴刻度差异。",
            "theme_amount_share",
        )}
      </section>'''
    market_turnover_html = ""
    if market_turnover_chart:
        market_turnover_html = f'''      <section class="chart-section">
        <h2><span class="chart-num">A-002</span>全市场成交额变化（截至{market_turnover_chart["last_date"]}）{freq_badge("日频")}</h2>
        <img src="assets/charts/{Path(market_turnover_chart["path"]).name}?v={asset_version}" alt="全市场成交额变化">
        {chart_note_block(
            "区间自 2024-09-24 起。当前使用中证全指成交金额作为沪深京全市场成交额公开代理口径；若后续接入交易所逐日汇总或 Wind 全A 精确口径，可替换本序列。",
            "代理口径可能低估或高估沪深京全市场真实成交额，尤其在北交所或非成分股成交活跃时偏差会扩大。",
            "market_turnover",
        )}
      </section>'''
    southbound_html = ""
    library_html = render_library()
    if southbound_chart:
        southbound_html = f'''      <section class="chart-section">
        <h2><span class="chart-num">G-002</span>南向资金每日净流入（截至{southbound_chart["last_date"]}）{freq_badge("日频")}</h2>
        <img src="assets/charts/{Path(southbound_chart["path"]).name}?v={asset_version}" alt="南向资金每日净流入">
        {chart_note_block(
            "区间自 2026-01-01 起。数据来自东方财富沪深港通历史数据，经 AkShare 获取；净流入口径为“当日成交净买额”，单位为亿元。",
            "若最新值长时间为 0、缺失或日期滞后，通常代表公开接口尚未更新；不同数据源对南向资金口径可能存在细微差异。",
            "southbound",
        )}
      </section>'''
    macro_sections = []
    if macro_chart:
        macro_notes = ""
        if macro_meta and macro_meta.get("status") == "partial":
            missing = [note for note in macro_meta.get("notes", []) if "暂无可用自动数据" in note]
            if missing:
                macro_notes = "暂未自动接入：" + "；".join(note.split("：")[0] for note in missing[:6]) + "。"
        macro_sections.append(f'''      <section class="chart-section">
        <h2><span class="chart-num">B-001</span>宏观经济数据概览（截至{macro_chart["last_date"]}）{freq_badge("月频")}</h2>
        <img src="assets/charts/{Path(macro_chart["path"]).name}?v={asset_version}" alt="宏观经济数据概览">
        {chart_note_block(
            f"展示各指标最近六个有效数据点，单位为同比增速（%）；0 值按缺失处理，不绘制数据点。月度指标按月展示，GDP 按季度展示。{macro_notes}",
            "宏观数据存在发布滞后、修订和接口失效风险；当前部分国家统计局、人民银行细分指标若未自动接入，会在图中保留占位。",
            "macro",
        )}
      </section>''')
    if macro_inventory_chart:
        macro_sections.append(f'''      <section class="chart-section">
        <h2><span class="chart-num">B-002</span>规模以上工业企业名义和实际库存同比（截至{macro_inventory_chart["last_date"]}）{freq_badge("月频")}</h2>
        <img src="assets/charts/{Path(macro_inventory_chart["path"]).name}?v={asset_version}" alt="规模以上工业企业名义和实际库存同比">
        {chart_note_block(
            "名义库存同比为 Wind EDB 的规模以上工业企业产成品存货同比；实际库存同比按名义库存同比 - PPI当月同比近似计算，单位为%。",
            "该实际库存口径为价格调整后的近似指标，PPI不能完全代表企业产成品库存价格变化；早期库存序列披露频率不完全连续，图中按有效观测点连线。",
            "macro_inventory",
        )}
      </section>''')
    if macro_m1_m2_chart:
        macro_sections.append(f'''      <section class="chart-section">
        <h2><span class="chart-num">B-003</span>M1-M2剪刀差（截至{macro_m1_m2_chart["last_date"]}）{freq_badge("月频")}</h2>
        <img src="assets/charts/{Path(macro_m1_m2_chart["path"]).name}?v={asset_version}" alt="M1-M2剪刀差">
        {chart_note_block(
            "M1-M2 = M1同比 - M2同比，M1和M2同比均来自 Wind EDB 中国人民银行月度数据，单位为百分点。",
            "货币供应量数据存在发布滞后和历史修订；M1-M2只刻画活化程度的方向性变化，不能单独代表信用扩张强弱。",
            "macro_m1_m2",
        )}
      </section>''')
    if macro_fiscal_chart:
        macro_sections.append(f'''      <section class="chart-section">
        <h2><span class="chart-num">B-004</span>一般公共预算收支与央地收入分化（截至{macro_fiscal_chart["last_date"]}）{freq_badge("月频")}</h2>
        <img src="assets/charts/{Path(macro_fiscal_chart["path"]).name}?v={asset_version}" alt="一般公共预算收支与央地收入分化">
        {chart_note_block(
            "左图展示一般公共预算收入、支出累计同比；右图展示中央一般公共预算收入和地方一般公共预算本级收入累计同比。数据均来自 Wind EDB 财政部月度指标，单位为%。",
            "财政数据为累计同比，受预算节奏、退税缴税节奏、转移支付和财政口径调整影响，单月变化不宜简单线性外推全年。",
            "macro_fiscal",
        )}
      </section>''')
    macro_html = "\n".join(macro_sections) if macro_sections else '<p class="empty-note">暂无图表。</p>'
    limit_up_date = (limit_up_meta or {}).get("latest_date", "")
    limit_up_html = render_limit_up_table("<span class=\"chart-num\">A-003</span>涨停观察：连续涨停天数前十", limit_up_longest, limit_up_date, "limit_up_longest")
    limit_up_html += "\n" + render_limit_up_table("<span class=\"chart-num\">A-004</span>涨停观察：当日涨停成交额前十", limit_up_amount_top, limit_up_date, "limit_up_amount_top")
    sentiment_html = '<p class="empty-note">暂无图表。</p>'
    if sentiment_chart:
        components = (sentiment_meta or {}).get("components", {})
        comp_text = "；".join(f"{k} {v:.2f}" for k, v in components.items() if v is not None)
        sentiment_html = f'''      <section class="chart-section">
        <h2><span class="chart-num">F-001</span>上证等权情绪指数（3年分位）（截至{sentiment_chart["last_date"]}）{freq_badge("日频")}</h2>
        <img src="assets/charts/{Path(sentiment_chart["path"]).name}?v={asset_version}" alt="上证等权情绪指数">
        {chart_note_block(
            f"六个指标等权平均：股债收益差、自由流通换手率(20日均)、流动性冲击、30日新发基金占比、乖离率(250日)、RSI(90日)；各取过去750个交易日(约3年)分位数后等权。当前各指标分位：{comp_text}。",
            "情绪指数是历史相对位置的观察，不代表买卖建议；增量数据来自 Wind 与公开接口，换手率增量按普通换手率×2.607折算自由流通口径，可能与精确值有小幅偏差。",
            "sentiment",
        )}
      </section>'''
    value_growth_html = ""
    if value_growth_spread_chart:
        value_growth_html = f'''      <section class="chart-section">
        <h2><span class="chart-num">F-007</span>价值成长风格价差（截至{value_growth_spread_chart["last_date"]}）{freq_badge("日频")}</h2>
        <img src="assets/charts/{Path(value_growth_spread_chart["path"]).name}?v={asset_version}" alt="价值成长风格价差">
        {chart_note_block(
            "价差 = 中证红利指数股息率 - 双创50盈利收益率(100/PE_TTM)，区间自 2021-01-01 起；虚线和阴影标注样本期历史上限/下限区间。数据优先来自 /gjdata 的 AIndexValuation 表。",
            "股息率和 PE_TTM 是指数估值口径，可能因成分调整、盈利口径修订和亏损样本处理而变化；极值区间只代表历史样本观察，不构成风格配置建议。",
            "value_growth_spread",
        )}
      </section>'''
    pb_dispersion_html = ""
    if citic_pb_dispersion_chart:
        pb_dispersion_html = f'''      <section class="chart-section">
        <h2><span class="chart-num">F-008</span>中信一级行业估值离散度（截至{citic_pb_dispersion_chart["last_date"]}）{freq_badge("日频")}</h2>
        <img src="assets/charts/{Path(citic_pb_dispersion_chart["path"]).name}?v={asset_version}" alt="中信一级行业估值离散度">
        {chart_note_block(
            "左轴为万得全A收盘价(881001.WI)，右轴为中信一级行业 PB_LF 历史分位的横截面标准差，并取 5 个交易日滚动平均(MA5)。PB 分位采用过去 10 年交易日滚动窗口计算，数据自 2005 年起从 /gjdata 读取。",
            "PB 分位标准差衡量行业估值分布离散程度，受行业样本、指数口径和 10 年滚动窗口影响；早期窗口未满时不会绘制离散度。",
            "citic_pb_dispersion",
        )}
      </section>'''
    industry_crowding_html = ""
    if industry_crowding_chart:
        crowding_date = industry_crowding_chart.get("last_date") or "待接入"
        crowding_status_note = ""
        if industry_crowding_chart.get("status") == "missing_data":
            crowding_status_note = "当前未取得中信一级行业完整 PE_TTM/PB_LF/成交额历史数据，图中显示数据待接入状态。"
        industry_crowding_html = f'''      <section class="chart-section">
        <h2><span class="chart-num">F-006</span>中信一级行业估值与成交拥挤度（截至{crowding_date}）{freq_badge("周频")}</h2>
        <img src="assets/charts/{Path(industry_crowding_chart["path"]).name}?v={asset_version}" alt="中信一级行业估值与成交拥挤度">
        {chart_note_block(
            f"按每周最后一个交易日更新。PE_TTM、PB_LF分别计算最近10年历史分位，成交额计算最近5年历史分位；括号为较上周变化，单位为百分点。综合拥挤度为三项分位最新值的算术均值，行业按综合拥挤度从高到低排序。数据优先使用 Wind API，Wind 不可用时读取本地 CSV。{crowding_status_note}",
            "拥挤度是估值与交易热度的历史分位观察，不代表买卖建议；若 Wind API 不可用或本地 CSV 未补齐，结果会显示待接入或滞后。",
            "industry_crowding",
        )}
      </section>'''
    hk_sections: list[str] = []
    if hk_sentiment_chart:
        hk_sections.append(f'''      <section class="chart-section">
        <h2><span class="chart-num">G-001</span>港股情绪（截至{hk_sentiment_chart["last_date"]}）{freq_badge("日频")}</h2>
        <img src="assets/charts/{Path(hk_sentiment_chart["path"]).name}?v={asset_version}" alt="港股情绪">
        {chart_note_block(
            "港股情绪Z参考《3_情绪指标_港股》口径，由恒指成份腾落线20日均、恒指波幅、恒生科技/恒指相对强度、南向资金20日均、卖空占比等分项Z值动态平均；当前使用 Wind 金融能力取数并本地缓存。",
            "情绪指标是历史相对强弱观察，不代表买卖建议；若卖空、南向或宽度分项当日未更新，综合值按已取得分项计算。",
            "hk_sentiment",
        )}
      </section>''')
    if southbound_chart:
        hk_sections.append(f'''      <section class="chart-section">
        <h2><span class="chart-num">G-002</span>南向资金每日净流入（截至{southbound_chart["last_date"]}）{freq_badge("日频")}</h2>
        <img src="assets/charts/{Path(southbound_chart["path"]).name}?v={asset_version}" alt="南向资金每日净流入">
        {chart_note_block(
            "区间自 2026-01-01 起。数据来自 Wind 金融能力；柱状图为南向资金每日净买入合计，折线为15个交易日滚动累计净买入，单位为亿元。",
            "若最新值长时间为 0、缺失或日期滞后，通常代表 Wind 数据尚未更新或接口字段变化，不应机械解读为真实无净买入。",
            "southbound",
        )}
      </section>''')
    if hk_rates_chart:
        hk_sections.append(f'''      <section class="chart-section">
        <h2><span class="chart-num">G-003</span>港股分母端：HIBOR隔夜与美国10年国债收益率（截至{hk_rates_chart["last_date"]}）{freq_badge("日频")}</h2>
        <img src="assets/charts/{Path(hk_rates_chart["path"]).name}?v={asset_version}" alt="HIBOR隔夜与美国10年国债收益率">
        {chart_note_block("HIBOR隔夜与美国10年国债收益率均来自 Wind 金融能力，单位为%。", "利率是港股估值分母端观察变量，跨市场假期会导致最新日期不完全一致。", "hk_rates")}
      </section>''')
    if hk_fx_chart:
        hk_sections.append(f'''      <section class="chart-section">
        <h2><span class="chart-num">G-004</span>美元指数与美元兑港元（截至{hk_fx_chart["last_date"]}）{freq_badge("日频")}</h2>
        <img src="assets/charts/{Path(hk_fx_chart["path"]).name}?v={asset_version}" alt="美元指数与美元兑港元">
        {chart_note_block("美元指数(USDX.FX)与美元兑港元(USDHKD.FX)收盘价来自 Wind 金融能力。", "汇率序列存在不同市场收盘时点差异，最新日缺失时以后续更新为准。", "hk_fx")}
      </section>''')
    if hk_ah_chart:
        hk_sections.append(f'''      <section class="chart-section">
        <h2><span class="chart-num">G-005</span>AH股溢价与港股通指数（截至{hk_ah_chart["last_date"]}）{freq_badge("日频")}</h2>
        <img src="assets/charts/{Path(hk_ah_chart["path"]).name}?v={asset_version}" alt="AH股溢价与港股通指数">
        {chart_note_block("左轴为恒生沪深港通AH股溢价指数(HSAHP.HI)，右轴为H50069.CSI收盘价，均来自 Wind 金融能力。", "AH溢价反映A/H相对价格，不直接等同于港股整体估值吸引力。", "hk_ah_premium")}
      </section>''')
    if hk_hsi_pe_chart:
        hk_sections.append(f'''      <section class="chart-section">
        <h2><span class="chart-num">G-006</span>恒生指数PE_TTM及均值分位（截至{hk_hsi_pe_chart["last_date"]}）{freq_badge("日频")}</h2>
        <img src="assets/charts/{Path(hk_hsi_pe_chart["path"]).name}?v={asset_version}" alt="恒生指数PE_TTM及均值分位">
        {chart_note_block("恒生指数 PE_TTM 来自 Wind 金融能力；均值、标准差和分位数基于2013年以来本地缓存样本计算。", "估值分位会随历史样本扩展和指数成分调整变化，适合做区间参考。", "hk_hsi_pe")}
      </section>''')
    if hk_hsi_erp_chart:
        hk_sections.append(f'''      <section class="chart-section">
        <h2><span class="chart-num">G-007</span>恒生指数ERP（截至{hk_hsi_erp_chart["last_date"]}）{freq_badge("日频")}</h2>
        <img src="assets/charts/{Path(hk_hsi_erp_chart["path"]).name}?v={asset_version}" alt="恒生指数ERP">
        {chart_note_block("恒生指数 ERP 优先来自 Wind 金融能力；若 Wind 原始 ERP 延迟发布，则按 100/PE_TTM - 中国10年国债收益率兜底补算，均值、标准差和分位数基于2013年以来样本计算。", "ERP口径依赖盈利收益率和利率设定，适合观察风险补偿方向，不宜单独作为配置信号。", "hk_hsi_erp")}
      </section>''')
    if hk_dividend_chart:
        hk_sections.append(f'''      <section class="chart-section">
        <h2><span class="chart-num">G-008</span>主要指数股息率TTM（截至{hk_dividend_chart["last_date"]}）{freq_badge("周频")}</h2>
        <img src="assets/charts/{Path(hk_dividend_chart["path"]).name}?v={asset_version}" alt="主要指数股息率TTM">
        {chart_note_block("展示港股通高股息CNY、中证红利、央企大盘、港股通央企红利、恒生指数、上证指数的最新股息率TTM，数据来自 Wind 金融能力。", "股息率受成分调整、股利预案确认和指数口径影响；周频图按最新可用交易日展示。", "hk_dividend_yield")}
      </section>''')
    hk_html = "\n".join(hk_sections) if hk_sections else '<p class="empty-note">暂无港股图表。</p>'
    daily_note = ""
    if daily_lagging:
        lagging_names = [REGISTRY_BY_KEY.get(key, {}).get("title", key) for key in daily_lagging[:4]]
        daily_note = f"<div class=\"meta-warning\">部分日频指标滞后：{', '.join(lagging_names)}</div>"
    html = f'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Vibe Research · 投研数据手册</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <main>
    <header class="page-head">
      <div><p class="eyebrow">Vibe Research</p><h1>投研数据手册</h1></div>
      <div class="meta">
        <div class="meta-line"><span class="live-dot" aria-hidden="true"></span>页面构建：{build_time}</div>
        <div class="meta-line">日频截至：{latest_daily}</div>
        <div class="meta-line">周频截至：{latest_weekly or "暂无"}</div>
        <div class="meta-line">月/季频截至：{latest_macro or "暂无"}</div>
{daily_note}
        <button class="refresh-button" type="button" id="refresh-data">刷新数据</button>
        <div class="refresh-status" id="refresh-status" role="status" aria-live="polite"></div>
      </div>
    </header>

    <nav class="category-tabs" aria-label="投研数据分类">
      <button class="category-tab active" type="button" data-target="market" aria-selected="true">行情</button>
      <button class="category-tab" type="button" data-target="macro" aria-selected="false">宏观</button>
      <button class="category-tab" type="button" data-target="valuation" aria-selected="false">估值</button>
      <button class="category-tab" type="button" data-target="earnings" aria-selected="false">盈利</button>
      <button class="category-tab" type="button" data-target="liquidity" aria-selected="false">流动性</button>
      <button class="category-tab" type="button" data-target="sentiment" aria-selected="false">情绪</button>
      <button class="category-tab" type="button" data-target="hongkong" aria-selected="false">港股</button>
      <button class="category-tab" type="button" data-target="library" aria-selected="false">资料</button>
    </nav>

    <section class="category-panel active" id="panel-market" data-category="market">
      <div class="category-head"><span class="sec-num">A</span><h2>行情</h2></div>
{market_brief_html}
{market_monitor_html}
{market_turnover_html}
{limit_up_html}
    </section>

    <section class="category-panel" id="panel-macro" data-category="macro" hidden>
      <div class="category-head"><span class="sec-num">B</span><h2>宏观</h2></div>
{macro_html}
    </section>

    <section class="category-panel" id="panel-valuation" data-category="valuation" hidden>
      <div class="category-head"><span class="sec-num">C</span><h2>估值</h2></div>
{valuation_html}
{pb_roe_html}
    </section>

    <section class="category-panel" id="panel-earnings" data-category="earnings" hidden>
      <div class="category-head"><span class="sec-num">D</span><h2>盈利</h2></div>
{earnings_html}
    </section>

    <section class="category-panel" id="panel-liquidity" data-category="liquidity" hidden>
      <div class="category-head"><span class="sec-num">E</span><h2>流动性</h2></div>
      <section class="chart-section">
        <h2><span class="chart-num">E-001</span>沪深300/上证指数 vs. 大宽基ETF资金流{freq_badge("日频")}</h2>
        <img src="assets/charts/fig_001_broad_etf_flow.png?v={asset_version}" alt="沪深300与上证指数走势及大宽基ETF资金流">
        {chart_note_block(
            "样本：510300、510310、510330、159919、510050。上交所 ETF 份额来自上交所历史规模接口；159919 份额来自深交所基金规模日频接口。净流入口径为份额变化乘以单位净值；7日滚动合计按交易日滚动计算。",
            broad_etf_risk,
            "broad_etf_flow",
        )}
      </section>
      <section class="chart-section">
        <h2><span class="chart-num">E-002</span>科创50指数 vs. 科创50ETF资金流{freq_badge("日频")}</h2>
        <img src="assets/charts/fig_002_star50_etf_flow.png?v={asset_version}" alt="科创50指数走势及科创50ETF资金流">
        {chart_note_block(
            "样本：588000 华夏科创50ETF。净流入口径为份额变化乘以单位净值；7日滚动合计按交易日滚动计算。",
            star_etf_risk,
            "star50_etf_flow",
        )}
      </section>
    </section>

    <section class="category-panel" id="panel-sentiment" data-category="sentiment" hidden>
      <div class="category-head"><span class="sec-num">F</span><h2>情绪</h2></div>
{sentiment_html}
      <section class="chart-section">
        <h2><span class="chart-num">F-002</span>A股成交额前10大公司交易集中度变化（截至{chart3_top10["last_date"]}）{freq_badge("日频")}</h2>
        <img src="assets/charts/{Path(chart3_top10["path"]).name}?v={asset_version}" alt="A股成交额前10大公司交易集中度变化">
        {chart_note_block(
            "样本覆盖当前沪深京A股清单；逐日计算成交额前10股票合计成交额占全市场成交额比例。右轴为上证指数收盘价。",
            "个股成交额排名依赖公开行情接口完整性；停牌、新股、北交所覆盖和接口延迟都可能影响集中度读数。",
            "turnover_top10",
        )}
      </section>
      <section class="chart-section">
        <h2><span class="chart-num">F-003</span>A股成交额前100大公司交易集中度变化（截至{chart3_top100["last_date"]}）{freq_badge("日频")}</h2>
        <img src="assets/charts/{Path(chart3_top100["path"]).name}?v={asset_version}" alt="A股成交额前100大公司交易集中度变化">
        {chart_note_block(
            "样本覆盖当前沪深京A股清单；逐日计算成交额前100股票合计成交额占全市场成交额比例。右轴为上证指数收盘价。",
            "前100集中度用于观察交易扩散程度，仍依赖公开逐股成交额接口完整性；接口延迟会影响最新交易日读数。",
            "turnover_top100",
        )}
      </section>
{amount_share_html}
{theme_amount_html}
{industry_crowding_html}
{value_growth_html}
{pb_dispersion_html}
    </section>

    <section class="category-panel" id="panel-hongkong" data-category="hongkong" hidden>
      <div class="category-head"><span class="sec-num">G</span><h2>港股</h2></div>
{hk_html}
    </section>

    <section class="category-panel" id="panel-library" data-category="library" hidden>
      <div class="category-head"><span class="sec-num">H</span><h2>资料</h2></div>
{library_html}
    </section>
  </main>
  <script src="app.js"></script>
</body>
</html>
'''
    css = '''/* 投研数据页 — 视觉系统(参考 MSTR/BTC 监控面板语言) */
:root {
  --bg: #eef1f6;
  --card: #ffffff;
  --ink: #17222f;
  --muted: #67748a;
  --faint: #98a2b3;
  --line: #e3e7ee;
  --accent: #e07b39;
  --accent-soft: #fdf1e7;
  --navy: #1d2f45;
  --green: #1e9e6a;
  --green-soft: #e5f6ee;
  --radius: 16px;
  --shadow: 0 1px 2px rgba(23, 34, 47, .05), 0 8px 24px -12px rgba(23, 34, 47, .12);
}

* { box-sizing: border-box; }

body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif;
  color: var(--ink);
  background: var(--bg);
  -webkit-font-smoothing: antialiased;
}

main {
  max-width: 1200px;
  margin: 0 auto;
  padding: 44px 24px 72px;
}

/* ---------- 页头 ---------- */
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 24px;
  padding-bottom: 26px;
}
.eyebrow {
  margin: 0 0 10px;
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .18em;
  text-transform: uppercase;
}
h1 {
  margin: 0;
  font-size: 38px;
  font-weight: 800;
  letter-spacing: .01em;
}
h2 { margin: 0; font-size: 19px; font-weight: 700; }

.meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  color: var(--muted);
  font-size: 13.5px;
  line-height: 1.7;
  white-space: nowrap;
}
.meta .meta-line { display: flex; align-items: center; gap: 7px; }
.meta-warning {
  max-width: 360px;
  white-space: normal;
  text-align: right;
  color: #b8664f;
  font-size: 12px;
  line-height: 1.45;
}
.live-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--green);
  box-shadow: 0 0 0 3px rgba(30, 158, 106, .18);
}
.refresh-button {
  appearance: none;
  margin-top: 10px;
  min-height: 38px;
  padding: 0 20px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--card);
  color: var(--ink);
  font: inherit;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: var(--shadow);
  transition: transform .12s ease, box-shadow .12s ease, border-color .12s ease;
}
.refresh-button:hover,
.refresh-button:focus-visible {
  border-color: var(--accent);
  color: var(--accent);
  outline: none;
  transform: translateY(-1px);
}
.refresh-button:disabled { cursor: wait; opacity: .6; transform: none; }
.refresh-status {
  min-height: 18px;
  color: var(--accent);
  font-size: 12px;
}

/* ---------- 分类切换(分段控件) ---------- */
.category-tabs {
  position: sticky;
  top: 14px;
  z-index: 5;
  display: flex;
  gap: 4px;
  margin: 6px 0 26px;
  padding: 5px;
  width: fit-content;
  max-width: 100%;
  overflow-x: auto;
  background: #e2e7ef;
  border: 1px solid var(--line);
  border-radius: 999px;
}
.category-tab {
  appearance: none;
  border: 0;
  border-radius: 999px;
  min-height: 36px;
  padding: 0 20px;
  background: transparent;
  color: var(--muted);
  font: inherit;
  font-size: 14px;
  font-weight: 600;
  white-space: nowrap;
  cursor: pointer;
  transition: background .15s ease, color .15s ease, box-shadow .15s ease;
}
.category-tab:hover,
.category-tab:focus-visible {
  color: var(--ink);
  outline: none;
}
.category-tab.active {
  background: var(--card);
  color: var(--ink);
  box-shadow: 0 1px 3px rgba(23, 34, 47, .16);
}

/* ---------- 分区标题(编号) ---------- */
.category-panel { padding-top: 4px; }
.category-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding: 4px 2px 18px;
}
.category-head .sec-num {
  color: var(--faint);
  font-size: 13px;
  font-weight: 700;
  letter-spacing: .08em;
}
.category-head h2 {
  font-size: 24px;
  font-weight: 800;
}

/* ---------- 图表卡片 ---------- */
.chart-section {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 22px 24px 16px;
  margin-bottom: 22px;
}
.chart-section > h2 {
  padding-bottom: 16px;
  font-size: 17.5px;
}
.chart-section img {
  display: block;
  width: 100%;
  height: auto;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #fbfcfe;
}

/* ---------- 数据说明(脚注式) ---------- */
.note, .empty-note, .chart-notes {
  color: var(--muted);
  font-size: 13px;
  line-height: 1.8;
}
.chart-notes {
  margin-top: 14px;
  padding: 10px 2px 4px;
  border-top: 1px dashed var(--line);
}
.chart-notes p { margin: 0; }
.chart-notes p + p { margin-top: 3px; }
.chart-notes strong { color: var(--ink); font-weight: 600; }
.chart-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px !important;
  padding: 3px 9px;
  border-radius: 999px;
  background: #f4f6f8;
  border: 1px solid #e1e6ec;
}
.status-ok {
  color: #16734f;
  background: #e8f6ef;
  border-color: #c6ead8;
}
.status-lagging, .status-missing {
  color: #a3482f;
  background: #fff0e8;
  border-color: #f1c9b8;
}
.status-manual, .status-unknown {
  color: #59636e;
}
.empty-note {
  margin: 8px 0 36px;
  padding: 26px;
  text-align: center;
  background: var(--card);
  border: 1px dashed var(--line);
  border-radius: var(--radius);
}

/* ---------- 表格 ---------- */
.table-wrap {
  overflow-x: auto;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--card);
}
.data-table {
  width: 100%;
  min-width: 980px;
  border-collapse: collapse;
  font-size: 13px;
}
.data-table th,
.data-table td {
  padding: 11px 12px;
  border-bottom: 1px solid #eef1f5;
  text-align: left;
  vertical-align: top;
}
.data-table tbody tr:last-child td { border-bottom: 0; }
.data-table tbody tr:hover { background: #f7f9fc; }
.data-table th {
  background: #f4f6fa;
  color: var(--navy);
  font-weight: 700;
  font-size: 12.5px;
  white-space: nowrap;
}
.data-table td:nth-child(1) { color: var(--muted); font-variant-numeric: tabular-nums; }
.data-table td:nth-child(2) { font-weight: 600; white-space: nowrap; }
.data-table td:nth-child(3),
.data-table td:nth-child(4),
.data-table td:nth-child(5),
.data-table td:nth-child(6) {
  text-align: right;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.data-table td:nth-child(7),
.data-table td:nth-child(8) {
  min-width: 210px;
  line-height: 1.6;
  color: var(--muted);
}

/* ---------- 响应式 ---------- */
@media (max-width: 720px) {
  main { padding: 30px 16px 52px; }
  .page-head { display: block; }
  .meta { align-items: flex-start; margin-top: 16px; white-space: normal; }
  h1 { font-size: 28px; }
  .category-tabs { width: 100%; top: 8px; }
  .category-tab { padding: 0 14px; font-size: 13.5px; }
  .chart-section { padding: 16px 14px 12px; }
  .category-head h2 { font-size: 20px; }
}

.chart-num {
  margin-right: 10px;
  color: var(--faint);
  font-size: 13px;
  font-weight: 700;
  letter-spacing: .06em;
  font-variant-numeric: tabular-nums;
}

/* ---------- 更新频率徽章 ---------- */
.freq-badge {
  display: inline-block;
  margin-left: 10px;
  padding: 2px 11px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .03em;
  vertical-align: 3px;
}

/* ---------- 行情监控面板 ---------- */
.market-brief {
  margin: 0 0 16px;
  padding: 14px 16px;
  border-left: 4px solid var(--accent);
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 1px 0 rgba(32, 48, 64, .04);
}
.brief-kicker {
  margin-bottom: 8px;
  color: var(--accent);
  font-size: 13px;
  font-weight: 800;
  letter-spacing: .08em;
}
.market-brief ul {
  margin: 0;
  padding-left: 18px;
  color: var(--text);
  font-size: 14px;
  line-height: 1.7;
}
.market-brief li + li { margin-top: 2px; }
.monitor-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
}
.monitor-block h3 {
  margin: 4px 0 10px;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: .12em;
  color: var(--accent);
}
.monitor-block { margin-bottom: 18px; min-width: 0; }
.monitor-grid .monitor-block { margin-bottom: 8px; }
.monitor-table { font-size: 13px; min-width: 0; }
.monitor-table td:nth-child(1) { color: var(--text); font-weight: 600; white-space: nowrap; }
.monitor-table td:nth-child(n+2) { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.monitor-table th:nth-child(n+2) { text-align: right; }
.monitor-table .pos { color: #c5513c; font-weight: 700; }
.monitor-table .neg { color: #2a9d55; font-weight: 700; }
@media (max-width: 900px) {
  .monitor-grid { grid-template-columns: 1fr; }
}

/* ---------- 资料库（个人研究文章与投资资料） ---------- */
.doc-list {
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
  margin: 10px 0 4px;
}
.doc-card {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  padding: 16px 18px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #fff;
  text-decoration: none;
  color: inherit;
  transition: border-color .15s ease, box-shadow .15s ease;
}
.doc-card:hover,
.doc-card:focus-visible {
  border-color: var(--accent);
  box-shadow: var(--shadow);
}
.doc-card-main { min-width: 0; }
.doc-type {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 6px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 11.5px;
  font-weight: 700;
  letter-spacing: .06em;
}
.doc-card h3 { margin: 8px 0 4px; font-size: 15.5px; }
.doc-card p { margin: 0; color: var(--muted); font-size: 13px; line-height: 1.55; }
.doc-card-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
  color: var(--faint);
  font-size: 12.5px;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.doc-open { color: var(--accent); font-weight: 700; }
'''
    js = '''const tabs = Array.from(document.querySelectorAll(".category-tab"));
const panels = Array.from(document.querySelectorAll(".category-panel"));
const refreshButton = document.querySelector("#refresh-data");
const refreshStatus = document.querySelector("#refresh-status");

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

if (refreshButton && refreshStatus) {
  function expectedLatestTradingDay() {
    const d = new Date();
    d.setDate(d.getDate() - 1);
    while (d.getDay() === 0 || d.getDay() === 6) {
      d.setDate(d.getDate() - 1);
    }
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  refreshButton.addEventListener("click", async () => {
    refreshButton.disabled = true;
    refreshStatus.textContent = "正在检查数据是否已是最新...";
    try {
      const metaResponse = await fetch(`meta.json?t=${Date.now()}`, { cache: "no-store" });
      if (metaResponse.ok) {
        const meta = await metaResponse.json();
        const latestDaily = meta.latest_daily_date || meta.latest_common_date || "";
        const expected = expectedLatestTradingDay();
        if (latestDaily && latestDaily >= expected) {
          refreshStatus.textContent = `数据已更新（截至 ${latestDaily}），请勿重复获取，避免消耗 API 与 token 额度。`;
          refreshButton.disabled = false;
          return;
        }
      }
    } catch (error) {
      // meta 不可用时继续按原流程刷新。
    }
    refreshStatus.textContent = "正在提交刷新任务...";
    try {
      const response = await fetch("/api/refresh", { method: "POST" });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(result.message || "刷新任务提交失败");
      }
      refreshStatus.textContent = "刷新任务已提交，数据更新和部署通常需要几分钟。";
    } catch (error) {
      refreshStatus.textContent = error.message || "刷新任务提交失败";
    } finally {
      refreshButton.disabled = false;
    }
  });
}
'''
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    (SITE_DIR / "index.html").write_text(html, encoding="utf-8")
    (SITE_DIR / "styles.css").write_text(css, encoding="utf-8")
    (SITE_DIR / "app.js").write_text(js, encoding="utf-8")
    (ROOT / "index.html").write_text(html, encoding="utf-8")
    site_meta = {
        "updated_at": build_time,
        "build_time": build_time,
        "latest_common_date": latest,
        "latest_daily_date": latest_daily,
        "latest_weekly_date": latest_weekly,
        "latest_macro_date": latest_macro,
        "daily_lagging_charts": daily_lagging,
        "charts": chart_dates,
    }
    (SITE_DIR / "meta.json").write_text(json.dumps(site_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    audit_payload = {
        "generated_at": build_time,
        "expected_dates": expected_dates,
        "charts": chart_audit,
    }
    (PROCESSED_DIR / "chart_audit.json").write_text(json.dumps(audit_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (SITE_DIR / "chart_audit.json").write_text(json.dumps(audit_payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    metadata = json.loads((PROCESSED_DIR / "metadata.json").read_text(encoding="utf-8"))
    indices = pd.read_csv(PROCESSED_DIR / "index_close.csv", parse_dates=["date"])
    broad = pd.read_csv(PROCESSED_DIR / "broad_etf_flow.csv", parse_dates=["date"])
    star = pd.read_csv(PROCESSED_DIR / "star50_etf_flow.csv", parse_dates=["date"])
    turnover = pd.read_csv(PROCESSED_DIR / "a_share_turnover_concentration.csv", parse_dates=["date"])
    valuation = pd.read_csv(PROCESSED_DIR / "index_pe_ttm_valuation.csv", parse_dates=["date"])
    broad_chart = draw_combo_chart(indices[["date", "沪深300", "上证指数"]].merge(broad, on="date", how="left"), [("沪深300", "沪深300", "#1f77b4"), ("上证指数", "上证指数", "#2a9d55")], "沪深300与上证指数走势及大宽基ETF资金流", CHART_DIR / "fig_001_broad_etf_flow.png")
    star_chart = draw_combo_chart(indices[["date", "科创50"]].merge(star, on="date", how="left"), [("科创50", "科创50", "#7b4ab8")], "科创50指数走势及科创50ETF资金流", CHART_DIR / "fig_002_star50_etf_flow.png")
    chart3 = {}
    chart3_top10 = draw_turnover_share_chart(turnover, "top10_share_pct", "前10大占比", "#c5513c", CHART_DIR / "fig_003a_turnover_top10_concentration.png")
    chart3_top100 = draw_turnover_share_chart(turnover, "top100_share_pct", "前100大占比", "#2f7cb8", CHART_DIR / "fig_003b_turnover_top100_concentration.png")
    amount_share_chart = None
    amount_share = None
    amount_share_path = PROCESSED_DIR / "index_amount_share.csv"
    if amount_share_path.exists():
        amount_share = pd.read_csv(amount_share_path, parse_dates=["date"])
        amount_share_chart = draw_index_amount_share_chart(amount_share, CHART_DIR / "fig_005_index_amount_share.png")
    theme_amount_chart = None
    theme_amount = None
    theme_amount_path = PROCESSED_DIR / "theme_amount_share.csv"
    if theme_amount_path.exists():
        theme_amount = pd.read_csv(theme_amount_path, parse_dates=["date"])
        theme_amount_chart = draw_theme_amount_share_chart(theme_amount, CHART_DIR / "fig_007_theme_amount_share.png")
    market_turnover_chart = None
    market_turnover = None
    market_turnover_path = PROCESSED_DIR / "market_turnover.csv"
    if market_turnover_path.exists():
        market_turnover = pd.read_csv(market_turnover_path, parse_dates=["date"])
        market_turnover_chart = draw_market_turnover_chart(market_turnover, CHART_DIR / "fig_008_market_turnover.png")
    southbound_chart = None
    southbound_path = PROCESSED_DIR / "southbound_flow.csv"
    if southbound_path.exists():
        southbound = pd.read_csv(southbound_path, parse_dates=["date"])
        southbound_chart = draw_southbound_flow_chart(southbound, CHART_DIR / "fig_009_southbound_flow.png")
    hk_sentiment_chart = None
    hk_rates_chart = None
    hk_fx_chart = None
    hk_ah_chart = None
    hk_hsi_pe_chart = None
    hk_hsi_erp_chart = None
    hk_dividend_chart = None
    hk_sentiment_path = PROCESSED_DIR / "hk_sentiment.csv"
    if hk_sentiment_path.exists():
        hk_sentiment = pd.read_csv(hk_sentiment_path, parse_dates=["date"])
        hk_sentiment_chart = draw_hk_sentiment_chart(hk_sentiment, CHART_DIR / "fig_016_hk_sentiment.png")
    hk_rates_path = PROCESSED_DIR / "hk_rates.csv"
    if hk_rates_path.exists():
        hk_rates = pd.read_csv(hk_rates_path, parse_dates=["date"])
        hk_rates_chart = draw_dual_line_chart(hk_rates, "hibor_on", "us10y", "HIBOR隔夜（%）", "美国10年国债（%）", "港股分母端：HIBOR隔夜与美国10年国债收益率", CHART_DIR / "fig_017_hk_rates.png")
    hk_fx_path = PROCESSED_DIR / "hk_fx.csv"
    if hk_fx_path.exists():
        hk_fx = pd.read_csv(hk_fx_path, parse_dates=["date"])
        hk_fx_chart = draw_dual_line_chart(hk_fx, "usd_index", "usdhkd", "美元指数", "美元兑港元", "美元指数与美元兑港元", CHART_DIR / "fig_018_hk_fx.png")
    hk_ah_path = PROCESSED_DIR / "hk_ah_premium.csv"
    if hk_ah_path.exists():
        hk_ah = pd.read_csv(hk_ah_path, parse_dates=["date"])
        hk_ah_chart = draw_dual_line_chart(hk_ah, "ah_premium", "h50069_close", "AH溢价指数", "H50069.CSI", "AH股溢价与港股通指数", CHART_DIR / "fig_019_hk_ah_premium.png", left_color="#c5513c", right_color="#1f6fb2")
    hk_valuation_path = PROCESSED_DIR / "hk_hsi_valuation.csv"
    if hk_valuation_path.exists():
        hk_valuation = pd.read_csv(hk_valuation_path, parse_dates=["date"])
        hk_hsi_pe_chart = draw_hsi_pe_chart(hk_valuation, CHART_DIR / "fig_020_hsi_pe_ttm.png")
        hk_hsi_erp_chart = draw_hsi_erp_chart(hk_valuation, CHART_DIR / "fig_021_hsi_erp.png")
    hk_dividend_path = PROCESSED_DIR / "hk_dividend_yield.csv"
    if hk_dividend_path.exists():
        hk_dividend = pd.read_csv(hk_dividend_path, parse_dates=["date"])
        hk_dividend_chart = draw_hk_dividend_chart(hk_dividend, CHART_DIR / "fig_022_hk_dividend_yield.png")
    macro_chart = None
    macro_inventory_chart = None
    macro_m1_m2_chart = None
    macro_fiscal_chart = None
    macro_meta = {}
    macro_path = PROCESSED_DIR / "macro_overview.csv"
    macro_meta_path = PROCESSED_DIR / "macro_overview.metadata.json"
    if macro_meta_path.exists():
        macro_meta = json.loads(macro_meta_path.read_text(encoding="utf-8"))
    if macro_path.exists():
        macro = pd.read_csv(macro_path, parse_dates=["date"])
        macro_chart = draw_macro_overview_chart(macro, macro_meta, CHART_DIR / "fig_010_macro_overview.png")
    macro_inventory_path = PROCESSED_DIR / "macro_inventory_cycle.csv"
    if macro_inventory_path.exists():
        macro_inventory = pd.read_csv(macro_inventory_path, parse_dates=["date"])
        macro_inventory_chart = draw_macro_inventory_chart(macro_inventory, CHART_DIR / "fig_023_macro_inventory_cycle.png")
    macro_m1_m2_path = PROCESSED_DIR / "macro_m1_m2.csv"
    if macro_m1_m2_path.exists():
        macro_m1_m2 = pd.read_csv(macro_m1_m2_path, parse_dates=["date"])
        macro_m1_m2_chart = draw_macro_m1_m2_chart(macro_m1_m2, CHART_DIR / "fig_024_macro_m1_m2.png")
    macro_fiscal_path = PROCESSED_DIR / "macro_fiscal.csv"
    if macro_fiscal_path.exists():
        macro_fiscal = pd.read_csv(macro_fiscal_path, parse_dates=["date"])
        macro_fiscal_chart = draw_macro_fiscal_chart(macro_fiscal, CHART_DIR / "fig_025_macro_fiscal.png")
    sentiment_chart = None
    sentiment_meta = {}
    sentiment_path = PROCESSED_DIR / "sentiment_index.csv"
    sentiment_meta_path = PROCESSED_DIR / "sentiment_index.metadata.json"
    if sentiment_meta_path.exists():
        sentiment_meta = json.loads(sentiment_meta_path.read_text(encoding="utf-8"))
    if sentiment_path.exists():
        sentiment = pd.read_csv(sentiment_path, parse_dates=["date"])
        sentiment_chart = draw_sentiment_chart(sentiment, sentiment_meta, CHART_DIR / "fig_011_sentiment_index.png")
    value_growth_spread_chart = None
    value_growth_path = PROCESSED_DIR / "value_growth_spread.csv"
    if value_growth_path.exists():
        value_growth = pd.read_csv(value_growth_path, parse_dates=["date"])
        value_growth_spread_chart = draw_value_growth_spread_chart(value_growth, CHART_DIR / "fig_014_value_growth_spread.png")
    citic_pb_dispersion_chart = None
    citic_pb_dispersion_path = PROCESSED_DIR / "citic_pb_dispersion.csv"
    if citic_pb_dispersion_path.exists():
        citic_pb_dispersion = pd.read_csv(citic_pb_dispersion_path, parse_dates=["date"])
        citic_pb_dispersion_chart = draw_citic_pb_dispersion_chart(citic_pb_dispersion, CHART_DIR / "fig_015_citic_pb_dispersion.png")
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
    valuation_chart_specs = [
        ("valuation_hs300", "沪深300指数", "fig_004a_hs300_pe_ttm_channel.png"),
        ("valuation_sse", "上证指数", "fig_004b_sse_pe_ttm_channel.png"),
        ("valuation_wind_all_a", "万得全A", "fig_004c_wind_all_a_pe_ttm_channel.png"),
        ("valuation_wind_all_a_ex_fin_petchem", "万得全A（除金融、石油石化）", "fig_004d_wind_all_a_ex_fin_petchem_pe_ttm_channel.png"),
    ]
    valuation_charts = []
    for key, index_name, filename in valuation_chart_specs:
        chart = draw_valuation_chart(valuation, index_name, CHART_DIR / filename)
        if chart:
            chart["key"] = key
            valuation_charts.append(chart)
        else:
            registry_item = REGISTRY_BY_KEY[key]
            valuation_charts.append({"key": key, "title": registry_item["title"], "path": "", "last_date": ""})
    industry_pb_roe_chart = None
    pb_roe_weekly_path = RAW_DIR / "citic_industry_crowding_weekly.csv"
    if pb_roe_weekly_path.exists():
        pb_roe_weekly = pd.read_csv(pb_roe_weekly_path)
        industry_pb_roe_chart = draw_industry_pb_roe_chart(pb_roe_weekly, industry_crowding if industry_crowding_path.exists() else None, CHART_DIR / "fig_012_citic_industry_pb_roe.png")
    industrial_profit_chart = None
    industrial_profit_path = PROCESSED_DIR / "industrial_profits.csv"
    if industrial_profit_path.exists():
        industrial_profit = pd.read_csv(industrial_profit_path, parse_dates=["date"])
        industrial_profit_chart = draw_industrial_profits_chart(industrial_profit, CHART_DIR / "fig_013_industrial_profits.png")
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
    monitor_indices = None
    monitor_breadth = None
    monitor_rates = None
    monitor_indices_path = PROCESSED_DIR / "market_monitor_indices.csv"
    monitor_breadth_path = PROCESSED_DIR / "market_monitor_breadth.csv"
    monitor_rates_path = PROCESSED_DIR / "market_monitor_rates.csv"
    if monitor_indices_path.exists():
        monitor_indices = pd.read_csv(monitor_indices_path)
    if monitor_breadth_path.exists():
        monitor_breadth = pd.read_csv(monitor_breadth_path)
    if monitor_rates_path.exists():
        monitor_rates = pd.read_csv(monitor_rates_path)
    build_page(
        metadata,
        broad_chart,
        star_chart,
        chart3,
        chart3_top10,
        chart3_top100,
        valuation_charts,
        amount_share_chart,
        industry_crowding_chart,
        theme_amount_chart,
        market_turnover_chart,
        southbound_chart,
        macro_chart,
        macro_inventory_chart,
        macro_m1_m2_chart,
        macro_fiscal_chart,
        macro_meta,
        sentiment_chart,
        sentiment_meta,
        limit_up_longest,
        limit_up_amount_top,
        limit_up_meta,
        monitor_indices=monitor_indices,
        monitor_breadth=monitor_breadth,
        monitor_rates=monitor_rates,
        market_turnover_data=market_turnover,
        amount_share_data=amount_share,
        theme_amount_data=theme_amount,
        industry_pb_roe_chart=industry_pb_roe_chart,
        industrial_profit_chart=industrial_profit_chart,
        value_growth_spread_chart=value_growth_spread_chart,
        citic_pb_dispersion_chart=citic_pb_dispersion_chart,
        hk_sentiment_chart=hk_sentiment_chart,
        hk_rates_chart=hk_rates_chart,
        hk_fx_chart=hk_fx_chart,
        hk_ah_chart=hk_ah_chart,
        hk_hsi_pe_chart=hk_hsi_pe_chart,
        hk_hsi_erp_chart=hk_hsi_erp_chart,
        hk_dividend_chart=hk_dividend_chart,
    )
    chart_count = len(CHART_REGISTRY)
    print(json.dumps({"latest_common_date": metadata["latest_common_date"], "charts": chart_count}, ensure_ascii=False))


if __name__ == "__main__":
    main()
