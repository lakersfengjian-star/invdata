# Vibe Research · 投研数据手册

可分享的静态投研数据站点：本地 Python 脚本增量抓数、生成图表与 `site/` 页面，推送 GitHub 后由 Vercel 自动部署。

> 项目固定规则（T+1 更新时间、增量取数、防重复刷新、新增图表接入清单）见 [`docs/FIXED_INSTRUCTIONS.md`](docs/FIXED_INSTRUCTIONS.md)，所有维护者和 AI 工具以此为准。

## 页面结构与图表编号

| 板块 | 编号 | 图表 | 频率 |
| --- | --- | --- | --- |
| 行情 | 001 | 行情监控面板（权益指数点位涨跌幅 / 全A市场宽度 / 固收利率） | 日频 |
| 行情 | 002 | 全市场成交额变化（中证全指代理口径） | 日频 |
| 行情 | 003 | 涨停观察：连续涨停天数前十 | 日频 |
| 行情 | 004 | 涨停观察：当日涨停成交额前十 | 日频 |
| 宏观 | 005 | 宏观经济数据概览（统计局/央行指标） | 月频 |
| 估值 | 006 | 沪深300指数历史滚动市盈率及标准差通道 | 日频 |
| 估值 | 007 | 上证指数历史滚动市盈率及标准差通道 | 日频 |
| 估值 | 008 | 中信一级行业 PB-ROE 散点图（ROE 由 PB/PE 推导，颜色=PB十年分位） | 周频 |
| 盈利 | 009 | 工业企业利润同比与全年外推（近1/3/5年同期进度线性外推） | 月频 |
| 流动性 | 010 | 南向资金每日净流入 | 日频 |
| 流动性 | 011 | 沪深300/上证指数 vs. 大宽基ETF资金流 | 日频 |
| 流动性 | 012 | 科创50指数 vs. 科创50ETF资金流 | 日频 |
| 情绪 | 013 | 上证等权情绪指数（六指标 3 年分位等权，含分项分位小图） | 日频 |
| 情绪 | 014 | A股成交额前10大公司交易集中度变化 | 日频 |
| 情绪 | 015 | 主要宽基指数成交额占全A成交额比例 | 日频 |
| 情绪 | 016 | TMT与红利低波成交额占全A成交额比例 | 日频 |
| 情绪 | 017 | 中信一级行业估值与成交拥挤度（含综合拥挤度排序） | 周频 |
| 情绪 | 018 | 价值成长风格价差（中证红利股息率 - 双创50盈利收益率） | 日频 |
| 情绪 | 019 | 中信一级行业估值离散度（万得全A vs PB分位标准差MA5） | 日频 |
| 资料 | 020 | 研究资料库（个人研究文章与投资资料） | 不定期 |

行情监控面板口径：权益含沪深300、300收益、上证指数、万得全A、恒生指数、恒生科技、中证红利；宽度含全A上涨/下跌家数、中位数/平均涨跌幅、成交额及较前一日变化；固收含7天逆回购、DR007(FDR007定盘)、10Y/30Y国债、5Y AAA中短票、5Y 银行二级资本债(AAA-)的当日/上一交易日点位及变化(bp)。取数脚本 `scripts/update_market_monitor.py`（公开接口为主；万得全A 与 7天逆回购走本地 Wind，`--wind-only` 挂接在情绪日更任务）。

## 更新方式

定时自动更新（推荐，T+1 规则）：

- 公开源调度：GitHub Actions 北京时间每天 06:00 运行一次，由 `scripts/run_scheduled_updates.py` 判断哪些数据需要补；
- 日频公开源：覆盖上一交易日，已最新则跳过，不发 API 请求；
- 宏观公开源：在统计局/央行常见发布窗口的次日 06:00 尝试更新；
- 情绪指数（Wind）：本地定时任务周二至周六 06:00；
- 中信拥挤度（Wind）：本地定时任务每周一 06:00；
- 价值成长风格价差、中信 PB 离散度：优先走 `/gjdata`，由本地或具备 `/gjdata` 的调度环境日频补最新交易日；

手动更新（全部脚本，幂等增量）：

```bash
python scripts/run_scheduled_updates.py --mode all    # 全量
python scripts/run_scheduled_updates.py --mode scheduled # 按北京时间和发布窗口自动判断
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
- 自动更新审计：`data/processed/update_audit.json`（最近一次实际运行脚本、跳过原因、构建结果）
- 图表目录：`output/charts/`
- 数据目录：`data/processed/`（产出）、`data/raw/`（原始与缓存）
- 定时编排：`scripts/run_scheduled_updates.py`（新鲜度守卫，已最新则零 API 跳过）

## 数据口径要点

- 区间从 `2025-01-01` 开始，截止到核心数据共同可用的最新交易日（拥挤度按周、宏观按月单独成列）。
- ETF净流入 = 当日份额变化 × 估值价格 / 1亿元；估值价格优先 ETF 单位净值，缺失时用二级市场收盘价估算；7日滚动合计按交易日滚动。
- 情绪指数：股债收益差、自由流通换手率(20日均)、流动性冲击、30日新发基金占比、乖离率(250日)、RSI(90日) 六指标各取 750 交易日分位后等权；换手率增量按普通换手率 × 2.607 折算自由流通口径。
- 中信拥挤度：PE_TTM/PB_LF 十年分位、成交额五年分位；综合拥挤度为三项均值，行业按综合值从高到低排序。
- 价值成长风格价差：中证红利指数股息率减双创50盈利收益率（`100 / PE_TTM`），自 2021-01-01 起，标注样本历史上限和下限。
- 中信 PB 离散度：中信一级行业 PB_LF 计算过去 10 年滚动历史分位，再取行业横截面标准差和 5 日均值；左轴同步展示万得全A收盘价。

## 数据源顺序

1. `/gjdata` 金融底层数据库：优先覆盖指数估值、指数行情、行业估值等已入库数据；后续只补本地最大日期后的缺口。
2. Wind 万得金融能力（本地，AIFin Market CLI / WindPy）：情绪指数、中信拥挤度等 `/gjdata` 暂缺或口径不足的数据。
3. 交易所及公开行情接口：上交所 ETF 历史规模、腾讯公开 K 线、东方财富（涨停池、沪深港通）、中证指数官网。
4. AkShare：ETF 单位净值、中债收益率等封装接口。
5. Tushare：脚本已预留 `TUSHARE_TOKEN` fallback；配置后可补深交所 ETF 历史份额。

估值图说明：

- 沪深300 PE_TTM 来自乐咕乐股指数估值接口；上证指数 PE 使用乐咕市场估值接口。
- 万得全A、万得全A（除金融、石油石化）暂无稳定公开接口。可将 Wind 导出的数据保存为 `data/raw/index_pe_ttm_wind.csv`，字段为 `date,index_name,pe_ttm`。
