# Vibe Research · 投研数据手册

可分享的静态投研数据站点：本地 Python 脚本增量抓数、生成图表与 `site/` 页面，推送 GitHub 后由 Vercel 自动部署。

线上地址：<https://invdata-v3va.vercel.app/>

> 项目固定规则（T+1 更新时间、增量取数、防重复刷新、新增图表接入清单）见 [`docs/FIXED_INSTRUCTIONS.md`](docs/FIXED_INSTRUCTIONS.md)，所有维护者和 AI 工具以此为准。

## 双机接力与本地环境

- GitHub `main` 是唯一权威版本；两台电脑分别使用独立本地克隆，不把 `.git` 工作区放在 iCloud、Dropbox 等同步盘中。
- 开始工作前先拉取远程更新；结束工作时只提交完整、已验证的变更并推送。另一台电脑必须先拉取再继续。
- 同一时间只在一台电脑上编辑同一分支；需要并行工作时使用不同分支。
- 只有一台电脑安装 `com.invdata.dashboard.daily` 本地定时任务，作为 Wind 与本地数据能力的主更新机；另一台只做手动开发和接力。
- 推荐用 `conda env create -f environment.yml` 创建 Python 3.12 环境，然后在 VS Code 中选择 `invdata` 解释器。
- 本地自动更新通过 `scripts/install_local_automation.sh` 安装；脚本会根据当前克隆路径生成 LaunchAgent，不依赖用户名或固定项目目录。

## 页面结构与图表编号

| 板块 | 编号 | 图表 | 频率 |
| --- | --- | --- | --- |
| 行情 | A-000 | A股市场热度仪表盘（量能 / 宽度 / 涨停 / 集中度 / 风格拥挤 / ETF资金） | 日频 |
| 行情 | A-001 | 行情监控面板（权益指数点位涨跌幅 / 全A市场宽度 / 固收利率） | 日频 |
| 行情 | A-002 | 全市场成交额变化（中证全指代理口径） | 日频 |
| 行情 | A-003 | 涨停观察：连续涨停天数前十 | 日频 |
| 行情 | A-004 | 涨停观察：当日涨停成交额前十 | 日频 |
| 宏观 | B-001 | 宏观经济数据概览（统计局/央行指标） | 月频 |
| 宏观 | B-002 | 规模以上工业企业名义和实际库存同比 | 月频 |
| 宏观 | B-003 | M1-M2剪刀差 | 月频 |
| 宏观 | B-004 | 一般公共预算收支与央地收入分化 | 月频 |
| 估值 | C-001 | 沪深300指数历史滚动市盈率及标准差通道 | 日频 |
| 估值 | C-002 | 上证指数历史滚动市盈率及标准差通道 | 日频 |
| 估值 | C-003 | 万得全A历史滚动市盈率及标准差通道 | 日频 |
| 估值 | C-004 | 万得全A（除金融、石油石化）历史滚动市盈率及标准差通道 | 日频 |
| 估值 | C-005 | 中信一级行业 PB-ROE 散点图（ROE 由 PB/PE 推导，颜色=PB十年分位） | 周频 |
| 盈利 | D-001 | 工业企业利润年度同比与全年外推（近1/3/5年同期进度线性外推） | 月频 |
| 流动性 | E-001 | 沪深300/上证指数 vs. 大宽基ETF资金流 | 日频 |
| 流动性 | E-002 | 科创50指数 vs. 科创50ETF资金流 | 日频 |
| 情绪 | F-001 | 上证等权情绪指数（六指标 3 年分位等权，含分项分位小图） | 日频 |
| 情绪 | F-002 | A股成交额前10大公司交易集中度变化 | 日频 |
| 情绪 | F-003 | A股成交额前100大公司交易集中度变化 | 日频 |
| 情绪 | F-004 | 主要宽基指数成交额占全A成交额比例 | 日频 |
| 情绪 | F-005 | TMT与红利低波成交额占全A成交额比例 | 日频 |
| 情绪 | F-009 | 风格成交分布仪表盘（成交占比 / 历史分位 / 20日与60日变化） | 日频 |
| 情绪 | F-010 | 风格收益热力图（主要宽基/主题/红利风格阶段收益） | 日频 |
| 情绪 | F-006 | 中信一级行业估值与成交拥挤度（含综合拥挤度排序） | 周频 |
| 情绪 | F-007 | 价值成长风格价差（中证红利股息率 - 双创50盈利收益率） | 日频 |
| 情绪 | F-008 | 中信一级行业估值离散度（万得全A vs PB分位标准差MA5） | 周频 |
| 港股 | G-001 | 港股情绪 | 日频 |
| 港股 | G-002 | 南向资金每日净流入（含15日滚动累计） | 日频 |
| 港股 | G-003 | 港股分母端：HIBOR隔夜与美国10年国债收益率 | 日频 |
| 港股 | G-004 | 美元指数与美元兑港元 | 日频 |
| 港股 | G-005 | AH股溢价与港股通指数 | 日频 |
| 港股 | G-006 | 恒生指数PE_TTM及分位 | 日频 |
| 港股 | G-007 | 恒生指数ERP | 日频 |
| 港股 | G-008 | 主要指数股息率TTM | 周频 |
| 资料 | H-001 | 研究资料库（个人研究文章与投资资料） | 不定期 |

市场热度仪表盘口径：不新增数据源，复用本地已缓存数据；量能=全市场成交额样本内分位，宽度=上涨家数占比样本内分位，涨停=涨停家数与连板高度合成，集中度=成交额Top10占比样本内分位，风格拥挤=中小盘与TMT成交占比样本内分位，ETF资金=大宽基ETF 7日滚动净流入样本内分位；总分为可用分项等权平均，0-100 分用于识别市场冷暖，不作为买卖建议。

行情监控面板口径：权益含沪深300、300收益、上证指数、万得全A、恒生指数、恒生科技、中证红利；宽度含全A上涨/下跌家数、中位数/平均涨跌幅、成交额及较前一日变化；固收含7天逆回购、DR007(FDR007定盘)、10Y/30Y国债、5Y AAA中短票、5Y 银行二级资本债(AAA-)的当日/上一交易日点位及变化(bp)。取数脚本 `scripts/update_market_monitor.py`（公开接口为主；万得全A 与 7天逆回购走本地 Wind，`--wind-only` 挂接在情绪日更任务）。

## 更新方式

定时自动更新（推荐，T+1 规则）：

- 公开源调度：GitHub Actions 北京时间每天 06:00 运行一次，由 `scripts/run_scheduled_updates.py` 判断哪些数据需要补；
- 日频公开源：覆盖上一交易日，已最新则跳过，不发 API 请求；
- 宏观公开源：在统计局/央行常见发布窗口的次日 06:00 尝试更新；
- 情绪指数（Wind）：本地定时任务周二至周六 06:00；
- 中信拥挤度（Wind）：本地定时任务每周一 06:00；
- 价值成长风格价差、中信 PB 离散度、风格收益热力图：使用 Wind 金融能力，由本地调度环境补充最新数据；其中中信 PB 离散度为周频，其余为日频；

本地日频定时任务模板为 `launch_agents/com.invdata.dashboard.daily.plist`，启动脚本为 `scripts/local_daily_update.sh`。若手动运行脚本正常但 LaunchAgent 无日志且长时间 running，通常是 macOS 隐私权限阻止后台任务访问 `~/Documents/投研助手`，需给 `/bin/zsh`、Codex Python 或 Terminal 授予“完全磁盘访问”。

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
python scripts/update_wind_index_valuation.py                 # 万得全A/除金融石化 PE_TTM 本地铺底或补数
python scripts/update_hk_dashboard.py                         # 港股板块与南向资金，Wind 金融能力
python scripts/update_style_performance.py                    # 风格指数阶段收益底层行情，Wind
python scripts/update_macro_credit_inventory.py               # 宏观库存、PPI、M1、M2，Wind EDB
python scripts/update_macro_fiscal.py                         # 财政收支和央地收入，Wind EDB
python scripts/build_site_from_processed.py                   # 重建图表与站点
```

## 目录与产出

- 页面入口：`index.html` → `site/index.html`（由 `scripts/build_site_from_processed.py` 全量生成，勿手改 site/）
- 图表注册表：`scripts/chart_registry.py`（稳定编号、板块、频率和审计口径）
- 站点元数据：`site/meta.json`（各图表最新日期，刷新按钮防重复守卫用）
- 图表审计：`data/processed/chart_audit.json`、`site/chart_audit.json`（每张图的应更新日期、实际日期、状态）
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
- 风格成交分布：复用 `index_amount_share.csv` 与 `theme_amount_share.csv`，展示沪深300、中证500、中证1000、中证2000、大盘+中盘、小盘+微盘、TMT、红利低波的成交占比、样本内分位以及20/60交易日变化；用于观察交易关注度和风格拥挤，不等同于收益贡献。
- 风格收益热力图：底层行情来自 Wind 指数日 K 线，覆盖沪深300、中证500、中证1000、中证2000、中证TMT、红利低波、中证红利、科创50；展示1日、5日、20日、60日、年初至今收益，作为风格强弱观察。
- 宏观库存与货币：库存图使用 Wind EDB 规模以上工业企业产成品存货同比与 PPI 同比，实际库存同比 = 名义库存同比 - PPI同比；M1-M2 图使用 Wind EDB 的 M1/M2 同比差值。
- 财政图：一般公共预算收入、支出、中央收入、地方本级收入累计同比均来自 Wind EDB 财政部月度指标。
- 港股板块：数据来自 Wind 金融能力并本地缓存。港股情绪参考 `3_情绪指标_港股.xlsx` 的分项Z值逻辑；南向资金使用 Wind 南向净买入合计并补15日滚动累计；恒生 PE/ERP 的均值、标准差和分位基于当前本地缓存样本计算，后续可单独回填更长历史。

## 数据源顺序

1. Wind 万得金融能力（本地，AIFin Market CLI / WindPy）：指数估值、指数行情、行业估值、情绪指数和中信拥挤度等金融数据；可复用时间序列落盘后只补最新缺口。
2. 官方数据源：交易所、国家统计局、人民银行等公开接口或下载文件。
3. 交易所及公开行情接口：上交所 ETF 历史规模、腾讯公开 K 线、东方财富（涨停池、沪深港通）、中证指数官网。
4. AkShare：ETF 单位净值、中债收益率等封装接口。
5. Tushare：脚本已预留 `TUSHARE_TOKEN` fallback；配置后可补深交所 ETF 历史份额。

估值图说明：

- 沪深300、上证指数、万得全A、万得全A（除金融、石油石化）PE_TTM 可通过 `scripts/update_wind_index_valuation.py` 调用 Wind 金融能力落地到 `data/raw/index_pe_ttm_wind.csv`；沪深300/上证指数仍保留乐咕公开接口 fallback。若 Wind 不可用，也可手动保存同名 CSV，字段为 `date,index_name,pe_ttm`。
