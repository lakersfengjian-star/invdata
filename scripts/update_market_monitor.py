#!/usr/bin/env python3
"""Update the market monitor panel datasets (行情监控面板).

Sections
  indices : 沪深300 / 300收益 / 上证指数 / 万得全A / 恒生指数 / 恒生科技 / 中证红利
            —— 当日点位与涨跌幅
  breadth : 沪深两市全A 上涨/下跌家数、中位数/平均涨跌幅、成交额
  rates   : 7天逆回购 / DR007(FDR007定盘) / 10Y国债 / 30Y国债 /
            5Y AAA中短票 / 5Y 银行二级资本债(AAA-)

Sources
  公开接口(GitHub Actions 可运行): 东方财富、中证指数官网、新浪财经、中国货币网。
  本地 Wind 能力: 万得全A(8841388.WI)、7天逆回购利率(EDB M0041371) —— 本机
  wind-mcp-skill CLI; 无 CLI 环境(如 GitHub Actions)自动跳过并沿用本地 csv。

增量规则(T+1): 本地 csv 已覆盖上一交易日(近似为上一工作日)时,
对应 section 直接跳过,不发任何请求。所有写入按 (指标, 日期) 去重幂等。

Usage:
  python scripts/update_market_monitor.py              # 全部 section
  python scripts/update_market_monitor.py --wind-only  # 仅更新 Wind 依赖部分(本地日更挂接)
  python scripts/update_market_monitor.py --force      # 忽略新鲜度强制刷新
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
VENDOR = ROOT / ".work" / "vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

PROCESSED_DIR = ROOT / "data" / "processed"
INDICES_CSV = PROCESSED_DIR / "market_monitor_indices.csv"
BREADTH_CSV = PROCESSED_DIR / "market_monitor_breadth.csv"
RATES_CSV = PROCESSED_DIR / "market_monitor_rates.csv"
METADATA_JSON = PROCESSED_DIR / "market_monitor.metadata.json"

SKILL_DIR = Path.home() / ".agents" / "skills" / "wind-mcp-skill"
CLI = SKILL_DIR / "scripts" / "cli.mjs"

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"}

EM_HOSTS = ["push2.eastmoney.com", "82.push2.eastmoney.com", "33.push2.eastmoney.com", "55.push2.eastmoney.com"]


def em_get(path: str, params: dict) -> str:
    """东方财富接口: 多主机轮换, 应对单主机限流。"""
    last_exc: Exception | None = None
    for host in EM_HOSTS:
        try:
            return http_get(f"https://{host}{path}", params=params)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            time.sleep(1.5)
    raise RuntimeError(f"em_get all hosts failed: {last_exc}")


# 东方财富 secid 配置(公开)
EM_INDICES = [
    ("1.000300", "沪深300"),
    ("1.000001", "上证指数"),
    ("1.000922", "中证红利"),
]
SINA_HK_INDICES = [("hkHSI", "恒生指数"), ("hkHSTECH", "恒生科技")]

# 中国货币网收盘收益率曲线配置: (曲线 cnLabel, 期限年, 展示名)
CHINAMONEY_CURVES = [
    ("国债", 10, "10年期国债"),
    ("国债", 30, "30年期国债"),
    ("中短期票据(AAA)", 5, "5年期AAA企业债(中短票)"),
    ("商业银行二级资本债(AAA-)", 5, "银行二级资本债AAA-(5年)"),
]


def previous_bday() -> pd.Timestamp:
    d = pd.Timestamp.now().normalize() - pd.Timedelta(days=1)
    while d.weekday() >= 5:
        d -= pd.Timedelta(days=1)
    return d


def http_get(url: str, params: dict | None = None, encoding: str = "utf-8", headers: dict | None = None) -> str:
    """requests 优先, 代理/TLS 失败时回退 curl(本机系统代理常半不可用)。"""
    import requests

    hdrs = {**UA, **(headers or {})}
    for trust_env in (True, False):
        try:
            session = requests.Session()
            session.trust_env = trust_env
            resp = session.get(url, params=params, headers=hdrs, timeout=25)
            resp.raise_for_status()
            resp.encoding = encoding
            return resp.text
        except Exception:  # noqa: BLE001
            continue
    query = ""
    if params:
        from urllib.parse import urlencode

        query = "?" + urlencode({k: str(v) for k, v in params.items()})
    cmd = ["curl", "-s", "-m", "25"]
    for k, v in hdrs.items():
        cmd += ["-H", f"{k}: {v}"]
    cmd.append(f"{url}{query}")
    proc = subprocess.run(cmd, capture_output=True, timeout=40)
    if proc.returncode != 0 or not proc.stdout:
        raise RuntimeError(f"http_get failed for {url}")
    return proc.stdout.decode(encoding, errors="replace")


def http_post(url: str, data: dict, headers: dict | None = None) -> str:
    import requests

    hdrs = {**UA, "X-Requested-With": "XMLHttpRequest", **(headers or {})}
    for trust_env in (True, False):
        try:
            session = requests.Session()
            session.trust_env = trust_env
            resp = session.post(url, data=data, headers=hdrs, timeout=25)
            resp.raise_for_status()
            return resp.text
        except Exception:  # noqa: BLE001
            continue
    from urllib.parse import urlencode

    cmd = ["curl", "-s", "-m", "25", "-X", "POST"]
    for k, v in hdrs.items():
        cmd += ["-H", f"{k}: {v}"]
    cmd += ["-d", urlencode({k: str(v) for k, v in data.items()}), url]
    proc = subprocess.run(cmd, capture_output=True, timeout=40)
    if proc.returncode != 0 or not proc.stdout:
        raise RuntimeError(f"http_post failed for {url}")
    return proc.stdout.decode("utf-8", errors="replace")


def load_csv(path: Path, cols: list[str]) -> pd.DataFrame:
    if path.exists():
        return pd.read_csv(path)
    return pd.DataFrame(columns=cols)


def append_rows(path: Path, cols: list[str], key_cols: list[str], rows: list[dict]) -> int:
    if not rows:
        return 0
    df = load_csv(path, cols)
    new = pd.DataFrame(rows, columns=cols)
    if not df.empty:
        merged = pd.concat([df, new], ignore_index=True)
        merged = merged.drop_duplicates(subset=key_cols, keep="last")
    else:
        merged = new
    merged.to_csv(path, index=False)
    return len(new)


# ---------------------------------------------------------------- indices ---

def fetch_em_indices() -> list[dict]:
    text = em_get(
        "/api/qt/ulist.np/get",
        params={
            "fltt": 2,
            "secids": ",".join(sec for sec, _ in EM_INDICES),
            "fields": "f2,f3,f12,f14",
        },
    )
    data = json.loads(text).get("data") or {}
    out = []
    for item in data.get("diff", []):
        out.append({"index": item["f14"], "close": float(item["f2"]), "change_pct": float(item["f3"])})
    return out


def fetch_csindex_h00300() -> list[dict]:
    text = http_get(
        "https://www.csindex.com.cn/csindex-home/perf/index-perf",
        params={"indexCode": "H00300", "startDate": (previous_bday() - pd.Timedelta(days=10)).strftime("%Y%m%d"), "endDate": pd.Timestamp.now().strftime("%Y%m%d")},
    )
    data = json.loads(text).get("data") or []
    if not data:
        return []
    latest = data[-1]
    return [{
        "index": "300收益",
        "close": float(latest["close"]),
        "change_pct": float(latest["changePct"]),
        "date": pd.to_datetime(latest["tradeDate"]).strftime("%Y-%m-%d"),
    }]


def fetch_sina_hk() -> list[dict]:
    text = http_get(
        "https://hq.sinajs.cn/list=" + ",".join(code for code, _ in SINA_HK_INDICES),
        encoding="gbk",
        headers={"Referer": "https://finance.sina.com.cn"},
    )
    out = []
    for line in text.splitlines():
        if "=" not in line or '""' in line:
            continue
        payload = line.split("=", 1)[1].strip().strip(";").strip('"')
        parts = payload.split(",")
        if len(parts) < 9:
            continue
        # 新浪港股指数: [0]代码 [1]名称 [2-5]开/高/低/前收类字段 [6]最新 [7]涨跌额 [8]涨跌幅 [-2]日期
        name = parts[1].strip()
        out.append({
            "index": name,
            "close": float(parts[6]),
            "change_pct": float(parts[8]) if parts[8] else None,
            "date": parts[-2].replace("/", "-"),
        })
    return out


def wind_cli(server: str, tool: str, params: dict) -> dict:
    cmd = ["node", str(CLI), "call", server, tool, json.dumps(params, ensure_ascii=False)]
    proc = subprocess.run(cmd, cwd=SKILL_DIR, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(f"wind cli exit {proc.returncode}: {proc.stdout[:200]}")
    outer = json.loads(proc.stdout)
    if outer.get("isError"):
        raise RuntimeError(f"wind cli isError: {proc.stdout[:200]}")
    return json.loads(outer["content"][0]["text"])


def fetch_wind_all_a() -> list[dict]:
    end = pd.Timestamp.now().strftime("%Y%m%d")
    begin = (pd.Timestamp.now() - pd.Timedelta(days=12)).strftime("%Y%m%d")
    inner = wind_cli("index_data", "get_index_kline", {"windcode": "8841388.WI", "begin_date": begin, "end_date": end})
    data = inner.get("data") or {}
    cols = [c["name"].upper() for c in data.get("columns", [])]
    rows = data.get("rows") or []
    if not cols or not rows:
        raise RuntimeError(f"wind all-a empty: {json.dumps(inner, ensure_ascii=False)[:200]}")
    i_time, i_close = cols.index("TIME"), cols.index("MATCH")
    out = []
    prev_close: float | None = None
    for row in rows:
        close = float(row[i_close])
        pct = round((close / prev_close - 1) * 100, 4) if prev_close else None
        out.append({
            "index": "万得全A",
            "close": close,
            "change_pct": pct,
            "date": str(row[i_time])[:10],
        })
        prev_close = close
    return out[-3:]


def update_indices(expected: pd.Timestamp, force: bool) -> dict:
    df = load_csv(INDICES_CSV, ["date", "index", "close", "change_pct"])
    have = set(zip(df.get("index", []), df.get("date", []))) if not df.empty else set()
    rows: list[dict] = []
    notes: list[str] = []

    target = expected.strftime("%Y-%m-%d")
    public_fetches = [fetch_em_indices, fetch_csindex_h00300, fetch_sina_hk]
    for fetch in public_fetches:
        try:
            for item in fetch():
                date = item.get("date") or target
                if (item["index"], date) in have:
                    continue
                rows.append({"date": date, "index": item["index"], "close": item["close"], "change_pct": item.get("change_pct")})
        except Exception as exc:  # noqa: BLE001
            notes.append(f"{fetch.__name__}: {type(exc).__name__}")

    if CLI.exists():
        try:
            for item in fetch_wind_all_a():
                if (item["index"], item["date"]) not in have:
                    rows.append({"date": item["date"], "index": "万得全A", "close": item["close"], "change_pct": item.get("change_pct")})
        except Exception as exc:  # noqa: BLE001
            notes.append(f"wind_all_a: {type(exc).__name__}")

    added = append_rows(INDICES_CSV, ["date", "index", "close", "change_pct"], ["date", "index"], rows)
    return {"added": added, "notes": notes}


# ---------------------------------------------------------------- breadth ---

def update_breadth(expected: pd.Timestamp, force: bool) -> dict:
    """市场宽度: 优先东方财富 clist 分页; 失败时回退 AkShare 全A快照."""
    df = load_csv(BREADTH_CSV, ["date", "up_count", "down_count", "flat_count", "median_pct", "mean_pct", "amount_100mn"])
    if not df.empty and not force:
        if pd.to_datetime(df["date"]).max() >= expected:
            return {"added": 0, "notes": ["fresh"]}

    pct_parts: list[float] = []
    amount_total = 0.0
    notes: list[str] = []

    # -------- 主路径: 东方财富 clist 分页 --------
    try:
        fs = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"
        page = 1
        while True:
            text = em_get(
                "/api/qt/clist/get",
                params={
                    "pn": page,
                    "pz": 100,
                    "po": 1,
                    "np": 1,
                    "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                    "fltt": 2,
                    "invt": 2,
                    "fid": "f12",
                    "fs": fs,
                    "fields": "f3,f6",
                },
            )
            data = json.loads(text).get("data") or {}
            diff = data.get("diff") or []
            for item in diff:
                p, a = item.get("f3"), item.get("f6")
                if isinstance(p, (int, float)):
                    pct_parts.append(float(p))
                if isinstance(a, (int, float)):
                    amount_total += float(a)
            total = data.get("total") or 0
            if page * 100 >= total or not diff:
                break
            page += 1
            time.sleep(0.15)
    except Exception as exc:  # noqa: BLE001
        notes.append(f"em_clist failed: {type(exc).__name__}")

    # -------- 备用路径: AkShare 全A快照 --------
    if not pct_parts:
        try:
            import akshare as ak
            spot = ak.stock_zh_a_spot_em()
            pct_col = "涨跌幅" if "涨跌幅" in spot.columns else "f3"
            amt_col = "成交额" if "成交额" in spot.columns else "f6"
            for _, row in spot.iterrows():
                p = row.get(pct_col)
                a = row.get(amt_col)
                if pd.notna(p):
                    pct_parts.append(float(p))
                if pd.notna(a):
                    amount_total += float(a)
            notes.append("fallback: akshare spot")
        except Exception as exc2:  # noqa: BLE001
            notes.append(f"akshare fallback failed: {type(exc2).__name__}")

    # -------- 最终回退: 从已有成交额汇总文件取 amount --------
    if not pct_parts and not amount_total:
        try:
            tdf = load_csv(
                PROCESSED_DIR / "a_share_turnover_concentration.csv",
                ["date", "total_amount_100mn"],
            )
            if not tdf.empty:
                latest = tdf.iloc[-1]
                if str(latest.get("date", "")) == expected.strftime("%Y-%m-%d"):
                    amount_total = float(latest.get("total_amount_100mn", 0)) * 1e8
                    notes.append("fallback: turnover_concentration amount only")
        except Exception:  # noqa: BLE001
            pass

    if not pct_parts and amount_total == 0:
        return {"added": 0, "notes": notes + ["all breadth sources empty"]}

    row: dict = {
        "date": expected.strftime("%Y-%m-%d"),
        "up_count": None,
        "down_count": None,
        "flat_count": None,
        "median_pct": None,
        "mean_pct": None,
        "amount_100mn": round(amount_total / 1e8, 2) if amount_total else None,
    }
    if pct_parts:
        pct = pd.Series(pct_parts)
        row.update({
            "up_count": int((pct > 0).sum()),
            "down_count": int((pct < 0).sum()),
            "flat_count": int((pct == 0).sum()),
            "median_pct": round(float(pct.median()), 4),
            "mean_pct": round(float(pct.mean()), 4),
            "amount_100mn": round(amount_total / 1e8, 2) if amount_total else None,
        })

    added = append_rows(
        BREADTH_CSV,
        ["date", "up_count", "down_count", "flat_count", "median_pct", "mean_pct", "amount_100mn"],
        ["date"],
        [row],
    )
    return {"added": added, "notes": notes}


# ------------------------------------------------------------------ rates ---

def chinamoney_curve_map() -> dict:
    text = http_get("https://www.chinamoney.com.cn/ags/ms/cm-u-bk-currency/ClsYldCurvCurvGO")
    data = json.loads(text).get("records") or []
    return {r["cnLabel"]: r["value"] for r in data}


def fetch_chinamoney_curve(curve_code: str, begin: str, end: str) -> list[dict]:
    """返回 ClsYldCurvHis 原始 records; 分页拉全(pageSize>50 会触发 403)。"""
    records: list[dict] = []
    for page in range(1, 9):
        text = http_get(
            "https://www.chinamoney.com.cn/ags/ms/cm-u-bk-currency/ClsYldCurvHis",
            params={
                "lang": "CN",
                "reference": "1,2,3",
                "bondType": curve_code,
                "startDate": f"{begin[:4]}-{begin[4:6]}-{begin[6:]}",
                "endDate": f"{end[:4]}-{end[4:6]}-{end[6:]}",
                "termId": "1",
                "pageNum": str(page),
                "pageSize": "50",
            },
        )
        chunk = json.loads(text).get("records") or []
        records.extend(chunk)
        if len(chunk) < 50:
            break
        time.sleep(0.4)
    return records


def parse_curve_records(records: list[dict], term_years: float) -> list[dict]:
    """从 ClsYldCurvHis records 中抽取指定年限的到期收益率序列。"""
    out = []
    for rec in records:
        try:
            if abs(float(rec.get("yearTermStr", "nan")) - term_years) < 0.01:
                date = str(rec.get("newDateValueCN") or "")[:10]
                value = float(rec.get("maturityYieldStr"))
                if date:
                    out.append({"date": date, "value": value})
        except (TypeError, ValueError):
            continue
    return out


def fetch_fdr007() -> list[dict]:
    """中国货币网回购定盘利率(FrrHis): 取 FDR007 最近若干交易日。"""
    begin = (pd.Timestamp.now() - pd.Timedelta(days=15)).strftime("%Y-%m-%d")
    end = pd.Timestamp.now().strftime("%Y-%m-%d")
    text = http_post(
        "https://www.chinamoney.com.cn/ags/ms/cm-u-bk-currency/FrrHis",
        data={"lang": "CN", "startDate": begin, "endDate": end, "pageNum": "1", "pageSize": "30"},
        headers={"Referer": "https://www.chinamoney.com.cn/chinese/bkfrr/"},
    )
    records = json.loads(text).get("records") or []
    out = []
    for rec in records:
        value_map = rec.get("frValueMap") or {}
        date = value_map.get("date") or rec.get("lfiProducDate")
        value = value_map.get("FDR007")
        if date and value not in (None, "", "--"):
            out.append({"date": str(date)[:10], "value": float(value)})
    return out


def fetch_omo_7d() -> list[dict]:
    inner = wind_cli(
        "economic_data",
        "natural_language_get_edb_data",
        {"executionMode": "searchFetch", "question": "7天期逆回购利率", "observation": "5"},
    )
    data = (inner.get("data") or {}).get("data") or []
    out = []
    for block in data:
        for d, v in zip(block.get("date", []), block.get("value", [])):
            out.append({"date": str(d)[:4] + "-" + str(d)[4:6] + "-" + str(d)[6:8] if len(str(d)) == 8 else str(d)[:10], "value": float(v)})
    return out


def update_rates(expected: pd.Timestamp, force: bool) -> dict:
    df = load_csv(RATES_CSV, ["date", "rate", "value"])
    have = set(zip(df.get("rate", []), df.get("date", []))) if not df.empty else set()
    rows: list[dict] = []
    notes: list[str] = []

    begin = (pd.Timestamp.now() - pd.Timedelta(days=12)).strftime("%Y%m%d")
    end = pd.Timestamp.now().strftime("%Y%m%d")
    try:
        cmap = chinamoney_curve_map()
        grouped: dict[str, list] = {}
        for label, term, name in CHINAMONEY_CURVES:
            grouped.setdefault(label, []).append((term, name))
        for label, terms in grouped.items():
            code = cmap.get(label)
            if not code:
                notes.append(f"curve missing: {label}")
                continue
            try:
                recs = fetch_chinamoney_curve(code, begin, end)
            except Exception as exc:  # noqa: BLE001 - 单条曲线失败不影响其他曲线
                notes.append(f"curve {label}: {type(exc).__name__}")
                continue
            for term, name in terms:
                for item in parse_curve_records(recs, term):
                    if (name, item["date"]) not in have:
                        rows.append({"date": item["date"], "rate": name, "value": item["value"]})
    except Exception as exc:  # noqa: BLE001
        notes.append(f"chinamoney: {type(exc).__name__}: {str(exc)[:120]}")

    try:
        for item in fetch_fdr007():
            name = "DR007(FDR007定盘)"
            if (name, item["date"]) not in have:
                rows.append({"date": item["date"], "rate": name, "value": item["value"]})
    except Exception as exc:  # noqa: BLE001
        notes.append(f"fdr007: {type(exc).__name__}")

    if CLI.exists():
        try:
            for item in fetch_omo_7d():
                name = "7天逆回购利率"
                if (name, item["date"]) not in have:
                    rows.append({"date": item["date"], "rate": name, "value": item["value"]})
        except Exception as exc:  # noqa: BLE001
            notes.append(f"omo_7d: {type(exc).__name__}")

    added = append_rows(RATES_CSV, ["date", "rate", "value"], ["date", "rate"], rows)
    return {"added": added, "notes": notes}


# ------------------------------------------------------------------- main ---

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wind-only", action="store_true", help="仅更新 Wind 依赖部分(万得全A、7天逆回购)")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    expected = previous_bday()
    result: dict = {"expected": expected.strftime("%Y-%m-%d")}

    if args.wind_only:
        result["indices"] = update_indices(expected, args.force)  # indices 内含万得全A
        result["rates"] = {}
        if CLI.exists():
            try:
                df = load_csv(RATES_CSV, ["date", "rate", "value"])
                have = set(zip(df.get("rate", []), df.get("date", []))) if not df.empty else set()
                rows = [
                    {"date": i["date"], "rate": "7天逆回购利率", "value": i["value"]}
                    for i in fetch_omo_7d()
                    if ("7天逆回购利率", i["date"]) not in have
                ]
                result["rates"] = {"added": append_rows(RATES_CSV, ["date", "rate", "value"], ["date", "rate"], rows), "notes": []}
            except Exception as exc:  # noqa: BLE001
                result["rates"] = {"added": 0, "notes": [f"omo_7d: {type(exc).__name__}"]}
    else:
        for section, func in [("indices", update_indices), ("breadth", update_breadth), ("rates", update_rates)]:
            try:
                result[section] = func(expected, args.force)
            except Exception as exc:  # noqa: BLE001 - 单 section 失败不影响其他部分
                result[section] = {"added": 0, "notes": [f"section failed: {type(exc).__name__}: {str(exc)[:150]}"]}

    idx = load_csv(INDICES_CSV, ["date", "index", "close", "change_pct"])
    breadth = load_csv(BREADTH_CSV, ["date"])
    rates = load_csv(RATES_CSV, ["date", "rate", "value"])
    metadata = {
        "latest_date": max(
            [d for d in [
                idx["date"].max() if not idx.empty else "",
                breadth["date"].max() if not breadth.empty else "",
                rates["date"].max() if not rates.empty else "",
            ] if d],
            default="",
        ),
        "sections": {
            "indices": idx["date"].max() if not idx.empty else "",
            "breadth": breadth["date"].max() if not breadth.empty else "",
            "rates": rates["date"].max() if not rates.empty else "",
        },
        "run": result,
    }
    METADATA_JSON.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
