# 投研数据页固定指令

目标：维护一个可分享的静态投研页面。所有图表先由本地 Python 脚本增量抓数并生成 PNG/CSV，再由 VS Code Source Control 负责提交、认证和推送到 GitHub Pages。

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
- 行情表格：`limit_up_longest.csv`、`limit_up_amount_top.csv`，展示最新交易日连续涨停天数前十和当日涨停成交额前十。

## 数据源优先级

1. 交易所与公开接口。
2. AkShare 封装接口。
3. Wind API、Tushare 或本地 CSV fallback。Wind 授权数据优先在本地脚本中读取，不通过对话搬运。

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

GitHub Pages 使用 `.github/workflows/pages.yml`。发布边界如下：

- agent 负责本地 Python 抓数、重建 `site/`、最小核验和准备提交说明。
- VS Code 负责 GitHub 认证、Commit、Push、Sync 和 Actions 查看。
- 不再通过对话或 GitHub 连接器上传大型 CSV、PNG、base64 快照。
- 如果推送失败，优先在 VS Code 中处理 GitHub 登录，不在 agent 会话里长时间排障。

VS Code 推送前固定检查：

```bash
git status -sb
git log --oneline -3
```

VS Code 推送后，Actions 会把 `site/` 作为静态站点发布。
