# 投研数据手册（Vibe Research）固定指令

目标：维护一个可分享的静态投研页面「Vibe Research · 投研数据手册」。所有图表先由本地 Python 脚本增量抓数并生成 PNG/CSV，再推送到 GitHub，由 Vercel 自动部署静态站点。

## 一句话触发

按固定指令更新 `<本机仓库目录>` 的投研数据页，增量抓取数据、生成图表、更新 `site/index.html`，并输出 VS Code 推送清单。

## 运行方式

```bash
python scripts/update_etf_dashboard.py
python scripts/update_index_amount_share.py
python scripts/update_theme_amount_share.py
python scripts/update_market_turnover.py
python scripts/update_hk_dashboard.py
python scripts/update_value_growth_spread.py
python scripts/update_macro_pmi.py
python scripts/update_citic_pb_dispersion.py
python scripts/update_style_performance.py
python scripts/update_wind_index_valuation.py
python scripts/update_macro_overview.py
python scripts/update_macro_credit_inventory.py
python scripts/update_macro_fiscal.py
python scripts/update_limit_up_tables.py
python scripts/update_citic_industry_crowding.py
python scripts/build_site_from_processed.py
```

## 输出

- 页面入口：`index.html` -> `site/index.html`（两者由建站脚本同步生成；Vercel 根路径优先读取根目录 `index.html`，不能只提交 `site/index.html`）
- 图表目录：`output/charts/`
- 数据目录：`data/processed/`
- 元数据：`data/processed/metadata.json`、`site/meta.json`
- 图表注册表：`scripts/chart_registry.py`
- 图表审计：`data/processed/chart_audit.json`、`site/chart_audit.json`
- 自动更新审计：`data/processed/update_audit.json`

## 图表编号

- `fig_001_broad_etf_flow.png`：沪深300/上证指数与大宽基ETF资金流
- `fig_002_star50_etf_flow.png`：科创50指数与科创50ETF资金流
- `fig_003a_turnover_top10_concentration.png`：A股成交额前10集中度（F-002）
- `fig_003b_turnover_top100_concentration.png`：A股成交额前100集中度（F-003）
- `fig_004a_hs300_pe_ttm_channel.png`：沪深300PE_TTM标准差通道（C-001）
- `fig_004b_sse_pe_ttm_channel.png`：上证指数PE_TTM标准差通道（C-002）
- `fig_004c_wind_all_a_pe_ttm_channel.png`：万得全A PE_TTM标准差通道（C-003），需本地CSV
- `fig_004d_wind_all_a_ex_fin_petchem_pe_ttm_channel.png`：万得全A除金融石油石化PE_TTM标准差通道（C-004），需本地CSV
- `fig_005_index_amount_share.png`：沪深300、中证500、中证1000、中证2000成交额占全A成交额比例
- `fig_006_citic_industry_crowding.png`：中信一级行业估值与成交拥挤度，按周更新
- `fig_007_theme_amount_share.png`：中证TMT、红利低波成交额占全A成交额比例
- `fig_008_market_turnover.png`：全市场成交额变化，区间自2024-09-24起
- `fig_009_southbound_flow.png`：南向资金每日净流入与15日滚动累计，区间自2026-01-01起，数据来自 Wind 金融能力
- `fig_010_macro_overview.png`：宏观经济数据概览，展示各指标最近六个有效数据点
- `fig_023_macro_inventory_cycle.png`：规模以上工业企业名义和实际库存同比（月频）。名义库存同比、PPI同比来自 Wind EDB；实际库存同比 = 名义库存同比 - PPI同比。
- `fig_024_macro_m1_m2.png`：M1-M2剪刀差（月频）。M1-M2 = M1同比 - M2同比，数据来自 Wind EDB 中国人民银行月度数据。
- `fig_025_macro_fiscal.png`：一般公共预算收支与央地收入分化（月频）。一般公共预算收入/支出、中央/地方本级收入累计同比来自 Wind EDB 财政部月度指标。
- `fig_011_sentiment_index.png`：上证等权情绪指数（六指标 3 年分位等权，右侧含分项分位小图）
- `fig_012_citic_industry_pb_roe.png`：中信一级行业 PB-ROE 散点图（周频）。构建时衍生图：由 `data/raw/citic_industry_crowding_weekly.csv` 最新周 PB_LF/PE_TTM 推导 ROE（ROE≈PB/PE 恒等式，同一价格口径下成立，零新增取数），叠加 `data/processed/citic_industry_crowding.csv` 的 PB 十年分位上色；随拥挤度周度数据自动更新，无需注册新取数脚本。
- `fig_013_industrial_profits.png`：工业企业利润年度同比与全年外推（月频，宏观调度）。指标为规模以上工业企业利润总额累计值/累计同比（国家统计局，每月 27 日左右发布上月数据，归入月末 28–31 日 23:00 宏观发布窗口）。历史底座 `data/raw/industrial_profits_wind.csv`（Wind EDB M0000556/M0000557 一次性铺底），增量由 `scripts/update_industrial_profits.py` 走 AkShare 统计局接口，已覆盖预期月份时零请求。图形以实线展示历史年度同比，2026 年按过去 1/3/5 年同期累计利润占全年比例均值线性外推全年利润总额，再计算隐含全年同比并用三条虚线表示；当年最新累计同比实际值只做点状标签。
- `fig_014_value_growth_spread.png`：价值成长风格价差（日频）。口径为中证红利指数股息率减双创50盈利收益率（`100 / PE_TTM`），区间自 2021-01-01 起，数据来自 Wind 指数估值能力。
- `fig_015_citic_pb_dispersion.png`：中信一级行业估值离散度（周频）。左轴万得全A周末对应的最近收盘价，右轴为中信一级行业 PB_LF 过去 10 年周频滚动历史分位的横截面标准差，并取 5 周均值；数据来自 Wind。
- `F-010 style_return_heatmap`：风格收益热力图（日频 HTML 表格）。底层数据为 `data/processed/style_index_performance.csv`，由 `scripts/update_style_performance.py` 从 Wind 指数日 K 线获取沪深300、中证500、中证1000、中证2000、中证TMT、红利低波、中证红利、科创50收盘价；页面展示1日、5日、20日、60日、年初至今收益。
- `fig_016_hk_sentiment.png`：港股情绪（日频），参考 `3_情绪指标_港股.xlsx` 的分项Z值逻辑，数据来自 Wind 金融能力。
- `fig_017_hk_rates.png`：HIBOR隔夜与美国10年国债收益率（日频），数据来自 Wind 金融能力。
- `fig_018_hk_fx.png`：美元指数与美元兑港元（日频），数据来自 Wind 金融能力。
- `fig_019_hk_ah_premium.png`：恒生沪深港通AH股溢价与H50069.CSI（日频），数据来自 Wind 金融能力。
- `fig_020_hsi_pe_ttm.png`：恒生指数PE_TTM及均值分位（日频），数据来自 Wind 金融能力。
- `fig_021_hsi_erp.png`：恒生指数ERP（日频），数据来自 Wind 金融能力；若 Wind 原始 ERP 延迟发布，则按 `100 / PE_TTM - 中国10年国债收益率` 兜底补算。
- `fig_022_hk_dividend_yield.png`：主要指数股息率TTM（周频展示最新可用交易日），数据来自 Wind 金融能力。
- 行情表格：`limit_up_longest.csv`、`limit_up_amount_top.csv`，展示最新交易日连续涨停天数前十和当日涨停成交额前十。

## 数据源优先级

1. Wind 万得金融能力。股票、债券、基金、指数、行业、宏观等金融数据优先使用 Wind；若已有本地历史序列，只补最新缺口，避免重复联网抓取。
2. 官方数据源：交易所、国家统计局、人民银行等公开接口或下载文件。
3. AkShare 封装接口。
4. Wind API、Tushare 或本地 CSV fallback。Wind 授权数据优先在本地脚本中读取，不通过对话搬运。

后续新增指标必须写明 Wind 查询口径和可用性；仅当 Wind 无数据、日期未更新或口径不满足时，才使用下一层数据源。宏观指标可优先采用统计局、人民银行等官方口径。

## 本地 CSV fallback

Wind PE_TTM 文件：`data/raw/index_pe_ttm_wind.csv`

字段：

```csv
date,index_name,pe_ttm
2020-01-02,万得全A,18.2
2020-01-02,万得全A（除金融、石油石化）,24.5
```

中信一级行业拥挤度文件：`data/raw/citic_industry_crowding_weekly.csv`

字段：

```csv
date,wind_code,industry,pe_ttm,pb_lf,amount_100mn
2026-07-03,CI005001.WI,石油石化,10.8,1.1,245.0
```

计算口径：

- 每周最后一个交易日一行。
- PE_TTM、PB_LF 分别计算最近10年历史分位。
- 成交额计算最近5年历史分位，单位为亿元。
- 页面展示当前分位和较上周变化，变化单位为百分点。

涨停观察表：

- 数据源：东方财富涨停股池，经 AkShare 获取；主营业务来自巨潮公司概况。
- 输出：`data/processed/limit_up_longest.csv`、`data/processed/limit_up_amount_top.csv`。
- 字段：代码、名称、连续涨停天数、流通市值、现价、成交额、主营业务、涨停原因。
- 注意：东方财富涨停股池不含 ST 股票及科创板股票，且公开接口不披露逐股涨停原因；当前原因字段为行业与连板特征归纳，后续可替换为更精确原因源。

TMT/红利低波成交额占比：

- 数据源：中证指数官网指数行情接口。
- 分子：中证TMT `000998`，中证红利低波动指数 `H30269`。
- 分母：与图五一致，使用中证全指成交金额作为 Wind 全A 成交额公开代理口径。
- 输出：`data/processed/theme_amount_share.csv`、`fig_007_theme_amount_share.png`。

全市场成交额变化：

- 起始日期：2024-09-24。
- 当前口径：复用 `index_amount_share.csv` 中的中证全指成交金额，作为沪深京全市场成交额公开代理口径。
- 输出：`data/processed/market_turnover.csv`、`fig_008_market_turnover.png`。
- 后续若接入交易所逐日汇总或 Wind 全A 精确口径，可替换该序列。

南向资金每日净流入：

- 起始日期：2026-01-01。
- 数据源：东方财富沪深港通历史数据，经 AkShare `stock_hsgt_hist_em(symbol="南向资金")` 获取。
- 口径：使用“当日成交净买额”作为每日净流入，单位为亿元。
- 输出：`data/processed/southbound_flow.csv`、`data/processed/southbound_flow.metadata.json`、`fig_009_southbound_flow.png`。
- 风险提示：若最新值长时间为 0 或缺失，可能代表接口尚未更新。

价值成长风格价差：

- 起始日期：2021-01-01。
- 数据源：Wind 指数估值，中证红利 `000922.CSI` 的股息率与双创50 `931643.CSI` 的 PE(TTM)。
- 计算：双创50盈利收益率 = `100 / PE_TTM`；价值成长价差 = 中证红利股息率 - 双创50盈利收益率，单位为百分点。
- 输出：`data/processed/value_growth_spread.csv`、`data/processed/value_growth_spread.metadata.json`、`fig_014_value_growth_spread.png`。

中信一级行业估值离散度：

- 起始日期：2005-01-01。
- 数据源：Wind；中信一级行业 PB_LF 使用周频缓存，万得全A `881001.WI` 使用指数日 K 线并转换为周频。
- 计算：逐行业按过去 10 年交易日窗口计算 PB_LF 历史分位；对当日全部中信一级行业分位取横截面标准差，再计算 5 个交易日滚动平均。
- 输出：`data/processed/citic_pb_dispersion.csv`、`data/processed/citic_pb_dispersion.metadata.json`、`fig_015_citic_pb_dispersion.png`。

风格收益热力图：

- 起始日期：2024-01-01。
- 数据源：Wind 指数日 K 线收盘价，阶段收益由本地计算。
- 指数：沪深300 `000300.SH`、中证500 `000905.SH`、中证1000 `000852.SH`、中证2000 `932000.CSI`、中证TMT `000998.CSI`、红利低波 `h30269.CSI`、中证红利 `000922.CSI`、科创50 `000688.SH`。
- 计算：1日收益优先使用 `S_DQ_PCTCHANGE`，5/20/60日与年初至今收益由收盘价计算。
- 输出：`data/processed/style_index_performance.csv`、`data/processed/style_index_performance.metadata.json`，页面表格 `F-010` 随 `scripts/build_site_from_processed.py` 生成。

宏观经济数据概览：

- 图表标题：宏观经济数据概览。
- 样式：横向分面小折线图，共享 Y 轴，各指标独立 X 轴。
- 展示：每个指标最近六个有效数据点；0 值按缺失处理，不绘制数据点。
- 自动数据源：东方财富宏观接口、国家统计局接口、人民银行原始表。
- 国家统计局口径：服务业生产指数取当月同比；固投/房地产、固投/基建、固投/制造业分别取对应累计值并倒算当月同比。
- 人民银行口径：社融取社会融资规模存量同比；企业中长期贷款取“存款类金融机构企（事）业单位贷款：中长期贷款”存量，并计算同比。
- 人民银行原始表路径：`data/raw/pbc_macro_credit.csv`，模板见 `data/raw/pbc_macro_credit.template.csv`。
- 国家统计局手工补充路径：`data/raw/macro_overview_extra.csv`，模板见 `data/raw/macro_overview_extra.template.csv`。
- 输出：`data/processed/macro_overview.csv`、`data/processed/macro_overview.metadata.json`、`fig_010_macro_overview.png`。

宏观库存与 M1-M2：

- 更新脚本：`scripts/update_macro_credit_inventory.py`。
- 数据源：Wind EDB `M0000561`（规模以上工业企业产成品存货同比）、`M0001227`（PPI当月同比）、`M0001383`（M1同比）、`M0001385`（M2同比）。
- 输出：`data/processed/macro_inventory_cycle.csv`、`data/processed/macro_m1_m2.csv`、`data/processed/macro_credit_inventory.metadata.json`、`fig_023_macro_inventory_cycle.png`、`fig_024_macro_m1_m2.png`。
- 更新频率：月频，纳入宏观发布窗口调度；若 Wind EDB 延迟发布，保留上一期数据。

财政收支：

- 更新脚本：`scripts/update_macro_fiscal.py`。
- 数据源：Wind EDB `M0046169`（一般公共预算收入累计同比）、`M0046167`（一般公共预算支出累计同比）、`M0089129`（中央一般公共预算收入累计同比）、`M0089130`（地方一般公共预算本级收入累计同比）。
- 输出：`data/processed/macro_fiscal.csv`、`data/processed/macro_fiscal.metadata.json`、`fig_025_macro_fiscal.png`。
- 更新频率：月频，纳入宏观发布窗口调度；若财政部或 Wind EDB 延迟发布，保留上一期数据。

## 发布

发布入口统一使用 Vercel。GitHub 只作为代码和静态文件仓库，不再部署 GitHub Pages。

- agent 负责本地 Python 抓数、重建 `site/`、最小核验和准备提交说明。
- VS Code 或 agent 负责 GitHub 认证、Commit、Push、Sync 和 Actions 查看。
- 不再通过对话或 GitHub 连接器上传大型 CSV、PNG、base64 快照。
- 如果推送失败，优先在 VS Code 中处理 GitHub 登录，不在 agent 会话里长时间排障。
- 仅修改网页展示、样式、图表排版或文档时，默认只完成本地构建和核验，不立即推送部署；等下一次自动数据更新提交时一并触发 Vercel 部署，除非用户明确要求“现在推送/部署”。
- Vercel 只部署静态文件；根目录 `vercel.json` 将首页重写到 `site/index.html`，`.vercelignore` 排除 Python 脚本、数据中间件和 Excel 文件，避免 Vercel 误识别为 Python 项目。

VS Code 推送前固定检查：

```bash
git status -sb
git log --oneline -3
```

推送后，Vercel 会自动部署 `site/` 静态站点。

网页右上角“刷新数据”按钮会调用 Vercel 函数 `/api/refresh`，再触发 GitHub Actions 的 `auto-update-dashboard.yml`。首次使用前需要在 Vercel 项目环境变量中配置：

- `GITHUB_PAT`：GitHub fine-grained token，至少允许仓库 `lakersfengjian-star/invdata` 的 Actions workflow dispatch 权限。

按钮只负责提交后台刷新任务；数据更新、自动提交和 Vercel 重新部署通常需要几分钟。

## 自动更新

GitHub Actions 使用 `.github/workflows/auto-update-dashboard.yml` 自动运行，也可以在 GitHub Actions 页面手动触发。

### 更新时间与频率规则（2026-07-26 起，新增图表必须遵守）

统一采用 **T+1** 规则，其他时间不自动更新，以控制 API 与 token 消耗：

| 数据频率 | 自动更新时间（北京时间） | 执行位置 |
| --- | --- | --- |
| 公开源总调度 | 每天 06:00 | GitHub Actions（cron `0 22 * * *` UTC），由 `scripts/run_scheduled_updates.py --mode scheduled` 判断日频/宏观是否需要运行 |
| 日频（成交额/涨停/南向/ETF/集中度/估值/成交额占比等公开源） | T+1 06:00（覆盖上一交易日收盘，节假日用工作日近似，已最新则跳过） | GitHub Actions 调度器 |
| 日频/周频（依赖 Wind 的指数/行业指标） | T+1 06:00（日频）或周日 10:00（周频） | 具备 Wind 金融能力的本地调度环境；GitHub Actions 无该能力时自动跳过 |
| 情绪指数（依赖 Wind 能力） | 周二至周六 06:00 | 本地定时任务（cron `0 6 * * 2-6` Asia/Shanghai） |
| 周频（中信行业拥挤度，依赖 Wind 能力） | 每周一 06:00（若电脑离线，之后每日 06:00 自动补跑） | 本地统一调度器；按最近完整周周日标签判断新鲜度 |
| 宏观（统计局/央行发布） | 官方常见发布窗口（每月 9–20 日、27–31 日）的次日 06:00 尝试更新 | GitHub Actions 调度器 |

本地日频任务文件：

- 项目内模板：`launch_agents/com.invdata.dashboard.daily.plist`。
- 启动脚本：`scripts/local_daily_update.sh`。
- 安装位置：`~/Library/LaunchAgents/com.invdata.dashboard.daily.plist`。
- 运行日志：`~/Library/Logs/InvDataDashboard/local_daily_update.out.log`、`~/Library/Logs/InvDataDashboard/local_daily_update.err.log`。
- 重要限制：macOS 后台 LaunchAgent 直接访问 `~/Documents/投研助手` 可能被系统隐私权限卡在 Python `open/getcwd` 阶段；若手动运行脚本正常但 LaunchAgent 无日志、进程长时间 running，需要给 `/bin/zsh`、Codex Python 或 Terminal 授予“系统设置 → 隐私与安全性 → 完全磁盘访问”，或改用 Terminal 桥接执行。

### 增量取数与新鲜度守卫

- 所有定时入口必须经过 `scripts/run_scheduled_updates.py` 编排器（模式 `scheduled`/`daily`/`weekly`/`macro`/`all`），它使用 Asia/Shanghai 时间判断上一交易日、最近完整周和宏观发布窗口，对每个数据集先比较输出文件最大日期：**已新鲜则完全跳过，不发任何 API 请求**；只有真正运行过更新脚本才重建站点，全新鲜时零消耗、零提交噪音。
- 编排器在实际运行脚本后写入 `data/processed/update_audit.json`，记录运行模式、期望日频日期、执行脚本、跳过原因、构建结果和 Wind 本地依赖提示。
- 依赖 Wind 的脚本在调度器中登记为本地能力依赖；若运行环境没有 Wind CLI 或授权，直接跳过并记录能力不可用，不得用旧缓存冒充更新。
- 本地 Wind 任务（情绪、拥挤度）的 prompt 同样要求先查日期、已最新则直接结束。
- Wind 取数一律使用缓存+断点续传，只补缺失区间：情绪用 `data/raw/sentiment_cache/`，拥挤度用 `data/raw/wind_cli_cache/`；拥挤度例行周更必须带 `--refresh-latest`（只失效最近 45 天缓存块，历史块复用）。
- 新增图表的更新脚本也必须"只取增量"：先读本地 CSV 最大日期，仅请求缺失区间。

### 刷新按钮防重复规则

- 站点构建时输出 `site/meta.json`（含 `latest_daily_date` 及各图表最新日期）。
- 站点构建时必须同步输出 `data/processed/chart_audit.json` 和 `site/chart_audit.json`：每张图包含 `key/id/title/category/frequency/expected_date/actual_date/status/status_label`。
- 页面每个 `chart-section` 的说明区必须展示“应更新日期、实际日期、状态”。状态来自 `scripts/chart_registry.py` 和 `chart_audit.json` 同一套逻辑，避免页面与审计文件口径不一致。
- 用户点击"刷新数据"时，`app.js` 先拉取 `meta.json`：若 `latest_daily_date` 已覆盖上一交易日，直接提示"数据已更新，请勿重复获取，避免消耗 API 与 token 额度"，**不再提交** `/api/refresh`；否则才触发 GitHub Actions 手动全量（`--mode all`）。

### 新增图表接入清单（务必按序执行）

1. 编写 `scripts/update_xxx.py`：增量取数 → 输出 `data/processed/xxx.csv`（含 `date` 列）+ `xxx.metadata.json`（含 `latest_date`）。
2. 在 `scripts/run_scheduled_updates.py` 的 `DAILY_DATASETS`（或周频/宏观相应位置）注册脚本与产出文件，新鲜度守卫自动生效。
3. 先在 `scripts/chart_registry.py` 注册图表 `key/id/title/category/frequency`。板块用字母编号，板块内图表用 `A-001`、`A-002` 这类稳定编号；拆图时在所属板块内新增下一个编号，避免大面积顺移。
4. 在 `scripts/build_site_from_processed.py` 中：新增画图函数（图内无标题）、在对应板块插入 `chart-section`、标题前使用注册表编号、`freq_badge()` 标注更新频率、附数据说明与风险提示，并在 `chart_note_block(..., chart_key)` 中传入注册表 key。
5. 更新频率决定调度：日频/宏观自动纳入 GitHub Actions；依赖 Wind 本地能力的日频/周频新建或并入本地定时任务（时间同上表）。
6. 重建 `python scripts/build_site_from_processed.py`，确认 `site/meta.json` 包含新图表日期，`site/chart_audit.json` 包含新图表状态后本地提交。

复合指标规则：如 A-000 市场热度仪表盘、F-009 风格成交分布仪表盘这类由多张底层表合成的指标，优先复用 `data/processed/` 本地缓存，不为合成分数新增抓数任务；必须在图下说明列出分项、方向、分位窗口或非分位口径，并在审计备注中说明样本过短或分项缺失。风格成交占比只能解释交易关注度和拥挤度，不能写成收益贡献。

### 自动更新流程（GitHub Actions）

1. 安装 Python 依赖和中文字体。
2. `run_scheduled_updates.py` 按模式运行：手动触发 `--mode all`，定时触发 `--mode scheduled`；单个公开接口失败时不中断整站构建，保留本地缓存数据。
3. 有更新时运行 `scripts/build_site_from_processed.py` 重建 `site/` 与图表。
4. 若 `index.html`、`data/processed`、`data/raw`、`output/charts` 或 `site` 有变化，自动提交并推送到 GitHub。
5. Vercel 由这次推送触发重新部署。

注意：

- Wind MCP/本机 WindPy 依赖本地能力，不在 GitHub Actions 中运行；Wind 数据应先落入 `data/raw/*.csv`，再由自动任务复用。
- 若连续多日数据不更新，优先检查 GitHub Actions 日志中的具体接口失败信息。
