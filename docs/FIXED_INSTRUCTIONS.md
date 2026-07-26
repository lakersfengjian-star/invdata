# 投研数据手册（Vibe Research）固定指令

目标：维护一个可分享的静态投研页面「Vibe Research · 投研数据手册」。所有图表先由本地 Python 脚本增量抓数并生成 PNG/CSV，再推送到 GitHub，由 Vercel 自动部署静态站点。

## 一句话触发

按固定指令更新 `/Users/jianfeng/Documents/投研助手` 的投研数据页，增量抓取数据、生成图表、更新 `site/index.html`，并输出 VS Code 推送清单。

## 运行方式

```bash
/Users/jianfeng/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/update_etf_dashboard.py
/Users/jianfeng/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/update_index_amount_share.py
/Users/jianfeng/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/update_theme_amount_share.py
/Users/jianfeng/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/update_market_turnover.py
/Users/jianfeng/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/update_southbound_flow.py
/Users/jianfeng/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/update_macro_overview.py
/Users/jianfeng/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/update_limit_up_tables.py
/Users/jianfeng/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/update_citic_industry_crowding.py
/Users/jianfeng/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/build_site_from_processed.py
```

## 输出

- 页面入口：`index.html` -> `site/index.html`
- 图表目录：`output/charts/`
- 数据目录：`data/processed/`
- 元数据：`data/processed/metadata.json`

## 图表编号

- `fig_001_broad_etf_flow.png`：沪深300/上证指数与大宽基ETF资金流
- `fig_002_star50_etf_flow.png`：科创50指数与科创50ETF资金流
- `fig_003_a_share_turnover_concentration.png`：A股成交额前10/前100集中度
- `fig_004a_hs300_pe_ttm_channel.png`：沪深300PE_TTM标准差通道
- `fig_004b_sse_pe_ttm_channel.png`：上证指数PE_TTM标准差通道
- `fig_004c_wind_all_a_pe_ttm_channel.png`：万得全A PE_TTM标准差通道，需本地CSV
- `fig_004d_wind_all_a_ex_fin_petchem_pe_ttm_channel.png`：万得全A除金融石油石化PE_TTM标准差通道，需本地CSV
- `fig_005_index_amount_share.png`：沪深300、中证500、中证1000、中证2000成交额占全A成交额比例
- `fig_006_citic_industry_crowding.png`：中信一级行业估值与成交拥挤度，按周更新
- `fig_007_theme_amount_share.png`：中证TMT、红利低波成交额占全A成交额比例
- `fig_008_market_turnover.png`：全市场成交额变化，区间自2024-09-24起
- `fig_009_southbound_flow.png`：南向资金每日净流入，区间自2026-01-01起
- `fig_010_macro_overview.png`：宏观经济数据概览，展示各指标最近六个有效数据点
- `fig_011_sentiment_index.png`：上证等权情绪指数（六指标 3 年分位等权，右侧含分项分位小图）
- `fig_012_citic_industry_pb_roe.png`：中信一级行业 PB-ROE 散点图（周频）。构建时衍生图：由 `data/raw/citic_industry_crowding_weekly.csv` 最新周 PB_LF/PE_TTM 推导 ROE（ROE≈PB/PE 恒等式，同一价格口径下成立，零新增取数），叠加 `data/processed/citic_industry_crowding.csv` 的 PB 十年分位上色；随拥挤度周度数据自动更新，无需注册新取数脚本。
- `fig_013_industrial_profits.png`：工业企业利润同比与全年外推（月频，宏观调度）。指标为规模以上工业企业利润总额累计值/累计同比（国家统计局，每月 27 日左右发布上月数据，归入月末 28–31 日 23:00 宏观发布窗口）。历史底座 `data/raw/industrial_profits_wind.csv`（Wind EDB M0000556/M0000557 一次性铺底），增量由 `scripts/update_industrial_profits.py` 走 AkShare 统计局接口，已覆盖预期月份时零请求。外推方法：过去 1/3/5 年同期累计利润占全年比例均值 → 线性外推全年利润总额 → 隐含全年同比。
- 行情表格：`limit_up_longest.csv`、`limit_up_amount_top.csv`，展示最新交易日连续涨停天数前十和当日涨停成交额前十。

## 数据源优先级

1. `/gjdata` 技能数据库。股票、债券、基金、指数、基准、衍生品、商品等数据库覆盖范围内的数据先查 `financedata`；若已有历史序列，只补最新缺口，避免重复联网抓取。使用时先查 `数据字典分类.xlsx`，再按单表取数。
2. 官方数据源：交易所、国家统计局、人民银行等公开接口或下载文件。宏观数据、分钟级/高频/实时行情不在 `/gjdata` 覆盖范围内，直接从本层开始。
3. AkShare 封装接口。
4. Wind API、Tushare 或本地 CSV fallback。Wind 授权数据优先在本地脚本中读取，不通过对话搬运。

后续新增非宏观、非高频指标必须先写明 `/gjdata` 查询口径和可用性；仅当数据库无数据、日期未更新或口径不满足时，才使用下一层数据源。宏观指标优先写明统计局、人民银行等官方口径。

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

## 发布

发布入口统一使用 Vercel。GitHub 只作为代码和静态文件仓库，不再部署 GitHub Pages。

- agent 负责本地 Python 抓数、重建 `site/`、最小核验和准备提交说明。
- VS Code 或 agent 负责 GitHub 认证、Commit、Push、Sync 和 Actions 查看。
- 不再通过对话或 GitHub 连接器上传大型 CSV、PNG、base64 快照。
- 如果推送失败，优先在 VS Code 中处理 GitHub 登录，不在 agent 会话里长时间排障。
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
| 日频（成交额/涨停/南向/ETF/集中度/估值/成交额占比等公开源） | 周二至周六 06:00（覆盖前一交易日收盘） | GitHub Actions（cron `0 22 * * 1-5` UTC） |
| 情绪指数（依赖 Wind 能力） | 周二至周六 06:00 | 本地定时任务（cron `0 6 * * 2-6` Asia/Shanghai） |
| 周频（中信行业拥挤度，依赖 Wind 能力） | 每周一 06:00（覆盖上周末收盘） | 本地定时任务（cron `0 6 * * 1` Asia/Shanghai） |
| 宏观（统计局/央行发布） | 每月 9–20 日、28–31 日 23:00（官方集中发布窗口） | GitHub Actions（cron `0 15 9-20,28-31 * *` UTC） |

### 增量取数与新鲜度守卫

- 所有定时入口必须经过 `scripts/run_scheduled_updates.py` 编排器（模式 `daily`/`macro`/`all`），它对每个数据集先比较 `data/processed/*.csv` 最大日期与上一交易日：**已新鲜则完全跳过，不发任何 API 请求**；只有真正运行过更新脚本才重建站点，全新鲜时零消耗、零提交噪音。
- 本地 Wind 任务（情绪、拥挤度）的 prompt 同样要求先查日期、已最新则直接结束。
- Wind 取数一律使用缓存+断点续传，只补缺失区间：情绪用 `data/raw/sentiment_cache/`，拥挤度用 `data/raw/wind_cli_cache/`；拥挤度例行周更必须带 `--refresh-latest`（只失效最近 45 天缓存块，历史块复用）。
- 新增图表的更新脚本也必须"只取增量"：先读本地 CSV 最大日期，仅请求缺失区间。

### 刷新按钮防重复规则

- 站点构建时输出 `site/meta.json`（含 `latest_daily_date` 及各图表最新日期）。
- 用户点击"刷新数据"时，`app.js` 先拉取 `meta.json`：若 `latest_daily_date` 已覆盖上一交易日，直接提示"数据已更新，请勿重复获取，避免消耗 API 与 token 额度"，**不再提交** `/api/refresh`；否则才触发 GitHub Actions 手动全量（`--mode all`）。

### 新增图表接入清单（务必按序执行）

1. 编写 `scripts/update_xxx.py`：增量取数 → 输出 `data/processed/xxx.csv`（含 `date` 列）+ `xxx.metadata.json`（含 `latest_date`）。
2. 在 `scripts/run_scheduled_updates.py` 的 `DAILY_DATASETS`（或周频/宏观相应位置）注册脚本与产出文件，新鲜度守卫自动生效。
3. 在 `scripts/build_site_from_processed.py` 中：新增画图函数（图内无标题）、在对应板块插入 `chart-section`、标题前加 `<span class="chart-num">NNN</span>` 三位编号、`freq_badge()` 标注更新频率、附数据说明与风险提示；全站编号随之顺移。
4. 更新频率决定调度：日频/宏观自动纳入 GitHub Actions；依赖 Wind 的日频/周频新建或并入本地定时任务（T+1 时间同上表）。
5. 重建 `python scripts/build_site_from_processed.py`，确认 `site/meta.json` 包含新图表日期后本地提交。

### 自动更新流程（GitHub Actions）

1. 安装 Python 依赖和中文字体。
2. `run_scheduled_updates.py` 按模式运行：手动触发 `--mode all`，23:00 发布窗口 `--mode macro`，其余 `--mode daily`；单个公开接口失败时不中断整站构建，保留本地缓存数据。
3. 有更新时运行 `scripts/build_site_from_processed.py` 重建 `site/` 与图表。
4. 若 `data/processed`、`data/raw`、`output/charts` 或 `site` 有变化，自动提交并推送到 GitHub。
5. Vercel 由这次推送触发重新部署。

注意：

- Wind MCP/本机 WindPy 依赖本地能力，不在 GitHub Actions 中运行；Wind 数据应先落入 `data/raw/*.csv`，再由自动任务复用。
- 若连续多日数据不更新，优先检查 GitHub Actions 日志中的具体接口失败信息。
