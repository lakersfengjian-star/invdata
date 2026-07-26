# Vibe Research · 投研数据手册

可分享的静态投研数据站点：本地 Python 脚本增量抓数、生成图表与 `site/` 页面，推送 GitHub 后由 Vercel 自动部署。

> 项目固定规则（T+1 更新时间、增量取数、防重复刷新、新增图表接入清单）见 [`docs/FIXED_INSTRUCTIONS.md`](docs/FIXED_INSTRUCTIONS.md)，所有维护者和 AI 工具以此为准。

## 页面结构与图表编号

| 板块 | 编号 | 图表 | 频率 |
| --- | --- | --- | --- |
| 行情 | 001 | 全市场成交额变化（中证全指代理口径） | 日频 |
| 行情 | 002 | 涨停观察：连续涨停天数前十 | 日频 |
| 行情 | 003 | 涨停观察：当日涨停成交额前十 | 日频 |
| 宏观 | 004 | 宏观经济数据概览（统计局/央行指标） | 月频 |
| 估值 | 005 | 沪深300指数历史滚动市盈率及标准差通道 | 日频 |
| 估值 | 006 | 上证指数历史滚动市盈率及标准差通道 | 日频 |
| 流动性 | 007 | 南向资金每日净流入 | 日频 |
| 流动性 | 008 | 沪深300/上证指数 vs. 大宽基ETF资金流 | 日频 |
| 流动性 | 009 | 科创50指数 vs. 科创50ETF资金流 | 日频 |
| 情绪 | 010 | 上证等权情绪指数（六指标 3 年分位等权，含分项分位小图） | 日频 |
| 情绪 | 011 | A股成交额前10大公司交易集中度变化 | 日频 |
| 情绪 | 012 | 主要宽基指数成交额占全A成交额比例 | 日频 |
| 情绪 | 013 | TMT与红利低波成交额占全A成交额比例 | 日频 |
| 情绪 | 014 | 中信一级行业估值与成交拥挤度（含综合拥挤度排序） | 周频 |
| 盈利 | — | 暂无图表 | — |

## 更新方式

定时自动更新（推荐，T+1 规则）：

- 日频公开源：GitHub Actions 北京时间周二至周六 06:00；
- 情绪指数（Wind）：本地定时任务周二至周六 06:00；
- 中信拥挤度（Wind）：本地定时任务每周一 06:00；
- 宏观：GitHub Actions 每月 9–20 日、28–31 日 23:00。

手动更新（全部脚本，幂等增量）：

```bash
python scripts/run_scheduled_updates.py --mode all    # 全量
python scripts/run_scheduled_updates.py --mode daily  # 仅日频
python scripts/run_scheduled_updates.py --mode macro  # 仅宏观
```

Wind 相关数据（GitHub Actions 无法运行）单独执行：

```bash
python scripts/update_sentiment_index.py                      # 情绪指数增量
python scripts/fetch_citic_crowding_wind_cli.py --refresh-latest  # 拥挤度周度增量取数
python scripts/update_citic_industry_crowding.py
python scripts/build_site_from_processed.py                   # 重建图表与站点
```

## 目录与产出

- 页面入口：`index.html` → `site/index.html`（由 `scripts/build_site_from_processed.py` 全量生成，勿手改 site/）
- 站点元数据：`site/meta.json`（各图表最新日期，刷新按钮防重复守卫用）
- 图表目录：`output/charts/`
- 数据目录：`data/processed/`（产出）、`data/raw/`（原始与缓存）
- 定时编排：`scripts/run_scheduled_updates.py`（新鲜度守卫，已最新则零 API 跳过）

## 数据口径要点

- 区间从 `2025-01-01` 开始，截止到核心数据共同可用的最新交易日（拥挤度按周、宏观按月单独成列）。
- ETF净流入 = 当日份额变化 × 估值价格 / 1亿元；估值价格优先 ETF 单位净值，缺失时用二级市场收盘价估算；7日滚动合计按交易日滚动。
- 情绪指数：股债收益差、自由流通换手率(20日均)、流动性冲击、30日新发基金占比、乖离率(250日)、RSI(90日) 六指标各取 750 交易日分位后等权；换手率增量按普通换手率 × 2.607 折算自由流通口径。
- 中信拥挤度：PE_TTM/PB_LF 十年分位、成交额五年分位；综合拥挤度为三项均值，行业按综合值从高到低排序。

## 数据源顺序

1. Wind 万得金融能力（本地，AIFin Market CLI / WindPy）：情绪指数、中信拥挤度。
2. 交易所及公开行情接口：上交所 ETF 历史规模、腾讯公开 K 线、东方财富（涨停池、沪深港通）、中证指数官网。
3. AkShare：ETF 单位净值、中债收益率等封装接口。
4. Tushare：脚本已预留 `TUSHARE_TOKEN` fallback；配置后可补深交所 ETF 历史份额。

估值图说明：

- 沪深300 PE_TTM 来自乐咕乐股指数估值接口；上证指数 PE 使用乐咕市场估值接口。
- 万得全A、万得全A（除金融、石油石化）暂无稳定公开接口。可将 Wind 导出的数据保存为 `data/raw/index_pe_ttm_wind.csv`，字段为 `date,index_name,pe_ttm`。
