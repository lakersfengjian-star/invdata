# 投研数据页标准流程

用途：后续 agent 维护本项目时优先读取本文，按固定流程更新数据、生成图表、推送 GitHub 并由 Vercel 自动部署，减少重复解释和 token 消耗。

## 项目定位

- 工作目录：`/Users/jianfeng/Documents/投研助手`
- 本地预览：`site/index.html`
- GitHub 仓库：`lakersfengjian-star/invdata`
- Vercel：由 GitHub 仓库 `main` 分支推送自动触发部署。
- 线上首页：Vercel 根路径会优先读取根目录 `index.html`；建站脚本必须同时生成根目录 `index.html` 和 `site/index.html`。
- 图表文件统一放在：`output/charts/`
- 静态站点目录统一放在：`site/`
- 站点图片目录统一放在：`site/assets/charts/`

## 核心原则

1. 时间序列优先本地存储，不要每次全量重新抓取。
2. 后续更新只补充“本地已有最大日期之后”的最新交易日数据。
3. 本地完整刷新成功后，再生成静态网页和 PNG。
4. Vercel 只发布静态文件；自动数据更新由 GitHub Actions 提交新快照后触发 Vercel 重新部署。
5. 网页头部展示页面构建时间、日频最新日期、周频最新日期、月/季频最新日期；每张图标题展示自己的最新数据日期。
6. 当净流入为 0 或关键字段缺失时，在页面注释中保留“数据可能未更新”的风险提示。
7. 严格执行 `TOKEN_EFFICIENT_WORKFLOW.md`：禁止通过对话或连接器搬运大型 base64、历史 CSV 或完整快照，优先本地增量、离线构建和正常 git 推送。
8. GitHub 凭证、网页登录、VS Code 推送由 VS Code/GitHub 本地客户端完成；agent 不再把认证排障作为常规工作。
9. 仅修改网页展示、样式、图表排版或文档时，默认只本地构建和核验，不立即推送部署；等下一次自动数据更新提交时一并部署，除非用户明确要求“现在推送/部署”。

## 职责边界

### agent 负责

- 用 Python 从公开数据源增量抓取数据。
- 维护 `data/processed` 中的可复用时间序列。
- 生成 `output/charts/*.png` 和 `site/` 静态页面。
- 用最小命令核验日期、图片路径、PNG 是否存在。
- 修改脚本和文档，并给出清晰的本地变更清单。

### VS Code 负责

- 管理 GitHub 登录和凭证。
- 管理分支、提交、推送和同步。
- 查看 GitHub Actions 和 Vercel 部署结果。
- 处理需要浏览器授权的 GitHub 操作。

### 用户确认

当 agent 说“本地成果已准备好”后，用户在 VS Code Source Control 中完成 Commit/Push。若用户要求 agent 继续推送，需先确认会额外消耗 token，且认证失败时 agent 应停止排障并回到 VS Code 推送方案。

## 数据分层

### 原始/缓存数据

- `data/raw/`：手工或外部导入数据，例如 Wind PE_TTM 模板。
- `.work/cache/`：接口缓存与逐股日行情缓存，不作为 Pages 必需发布内容。

### 可复用时间序列

以下文件是后续增量更新的基础，应优先读取并只补最新日期：

- `data/processed/index_close.csv`
- `data/processed/etf_daily_flow_detail.csv`
- `data/processed/broad_etf_flow.csv`
- `data/processed/star50_etf_flow.csv`
- `data/processed/a_share_turnover_concentration.csv`
- `data/processed/index_pe_ttm_valuation.csv`
- `data/processed/metadata.json`

逐股明细 `data/processed/a_share_daily_turnover_rank_detail.csv` 很大，只在本地保留；发布时优先使用汇总表 `a_share_turnover_concentration.csv`。

## 数据源优先级

1. `/gjdata` 技能数据库：股票、债券、基金、指数、基准、衍生品、商品等数据库覆盖范围内的指标，优先从 `financedata` 库读取；若数据库已有可用时间序列，不再重复联网抓取历史数据。使用前按技能要求先查 `数据字典分类.xlsx`，再单表取数，禁止跨表 JOIN。
2. 官方数据源：交易所、国家统计局、人民银行等公开接口或下载文件。宏观数据、分钟级/高频/实时行情不在 `/gjdata` 覆盖范围内，应直接进入本层或后续 fallback；包括上交所 ETF 历史规模、深交所基金规模日频数据、公开行情 K 线、统计局宏观数据、央行金融数据等。
3. AkShare 封装接口：当 `/gjdata` 和官方接口缺失或不可用时使用，包括 ETF 单位净值、A股代码表、公开估值封装接口等。
4. Tushare/Wind/本地 CSV：作为最后 fallback；Wind 授权数据优先由本地脚本读取，不通过对话搬运。万得全A PE_TTM 可走此层。

执行要求：新增或更新任何非宏观、非高频指标时，先检查 `/gjdata` 是否可用并记录查询口径；只有数据库缺少该指标、缺少最新日期或字段口径不满足要求时，才进入下一层数据源。宏观指标按国家统计局、人民银行等官方源优先。更新完成后应将可复用时间序列落盘到 `data/processed/`，后续只增量补最新日期。

## 标准更新流程

### 1. 检查本地状态

```bash
git status --short
ls data/processed
ls output/charts
```

不要回滚用户已有改动。若已有未提交变更，继续工作但避免覆盖无关文件。

### 2. 读取最新本地日期

优先查看：

```bash
python3 - <<'PY'
import json
from pathlib import Path
p = Path("data/processed/metadata.json")
print(json.loads(p.read_text()).get("latest_common_date") if p.exists() else "no metadata")
PY
```

如果本地最新日期已经等于最新可用交易日，只需重建页面，不要全量抓取。

### 3. 增量抓取数据

当前主脚本为：

```bash
PYTHONPYCACHEPREFIX=/tmp/codex-pycache MPLCONFIGDIR=/tmp/matplotlib-cache /Users/jianfeng/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/update_etf_dashboard.py
```

后续优化方向：

- 先读取本地 CSV 的最大日期。
- 只请求最大日期之后到最新可用交易日的数据。
- 对逐股成交额使用 `.work/cache/sina_a_share_daily_2026/` 缓存，已有个股文件只补缺口。
- 对 ETF 份额、NAV、指数收盘价保留按日期缓存，避免重复访问历史区间。
- 新增指标时优先新建独立更新脚本，例如 `scripts/update_<metric>.py`，并把输出落到 `data/processed/<metric>.csv`，不要把所有抓取逻辑继续塞进单一大脚本。
- 每个数据脚本应支持“读取本地最大日期 -> 只补新日期 -> 写回 CSV -> 更新 metadata”的闭环。

### 4. 离线重建网页

本地汇总数据齐全后，优先用离线脚本重建网页和发布目录：

```bash
PYTHONPYCACHEPREFIX=/tmp/codex-pycache MPLCONFIGDIR=/tmp/matplotlib-cache /Users/jianfeng/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/build_site_from_processed.py
```

该脚本只读取 `data/processed` 中的小型汇总表，生成：

- `output/charts/*.png`
- `index.html`
- `site/index.html`
- `site/assets/charts/*.png`
- `site/meta.json`

### 5. 本地核验

必须确认：

```bash
rg -n "assets/charts|截至|区间|图三|图四" site/index.html
find site/assets/charts -maxdepth 1 -type f -print | sort
```

期望：

- 页面图片路径为 `assets/charts/...`
- 图一、图二最新日期与 `metadata.json` 一致
- 图三标题包含 `截至YYYY-MM-DD`
- 图四每张标题包含 `截至YYYY-MM-DD`
- `site/assets/charts/` 至少有 5 张 PNG

### 6. Vercel 发布与 GitHub 推送

Vercel 只部署静态站点。根目录保留：

- `vercel.json`：把 `/` 重写到 `site/index.html`。
- `.vercelignore`：排除 Python 脚本、数据中间文件、Excel 和本地缓存，避免 Vercel 误识别为 Python 项目。

注意：若根目录存在 `index.html`，Vercel 会优先命中该静态文件，rewrite 不会覆盖它。因此 `scripts/build_site_from_processed.py` 必须把同一份 HTML 同步写入根目录 `index.html` 和 `site/index.html`，自动更新工作流也必须提交根目录 `index.html`。图片路径可直接使用 `assets/charts/...`。

发布优先使用 VS Code Source Control：

1. agent 完成本地数据、图表、网页和文档修改。
2. agent 输出本地核验结果和待提交文件范围。
3. 用户在 VS Code 中检查 Source Control。
4. 用户点击 Commit/Push，VS Code 处理 GitHub 登录和 HTTPS 凭证。
5. Vercel 自动部署；agent 只在用户推送后做轻量线上核验。

节省 token 的默认发布节奏：

- 数据更新类任务：本地或自动任务抓数、构建、提交，由 Vercel 自动部署。
- 页面展示类任务：只本地构建和核验，暂不触发 GitHub/Vercel；下一次自动数据更新提交时一并发布。
- 用户明确要求“推送”“部署”“线上生效”时，才进入提交/推送流程。

不推荐 agent 继续处理：

- GitHub 登录。
- PAT/密码/验证码。
- SSH key 绑定。
- VS Code UI 推送按钮操作。
- GitHub 连接器上传 PNG、CSV 或大型快照。

若必须命令行推送，固定命令如下，后续不要展开长时间排障：

```bash
cd /Users/jianfeng/Documents/投研助手
git status -sb
git push origin HEAD:main
```

### 7. 线上核验

发布后检查：

```bash
VERCEL_SITE_URL="https://<your-vercel-domain>"
curl -L -sS -o /tmp/invdata-page.html -w '%{http_code} %{url_effective}\n' "$VERCEL_SITE_URL/"
rg -n "assets/charts|截至|区间" /tmp/invdata-page.html
curl -L -sS -o /tmp/chart.png -w '%{http_code} %{size_download}\n' "$VERCEL_SITE_URL/assets/charts/fig_001_broad_etf_flow.png"
```

期望：

- 首页 HTTP `200`
- 页面中不再出现 `../output/charts`
- 图片 HTTP `200` 且下载大小明显大于 10KB

## 图表编号

- `fig_001_broad_etf_flow.png`：沪深300/上证指数与大宽基ETF资金流
- `fig_002_star50_etf_flow.png`：科创50指数与科创50ETF资金流
- `fig_003a_turnover_top10_concentration.png`：A股成交额前10集中度（F-002）
- `fig_003b_turnover_top100_concentration.png`：A股成交额前100集中度（F-003）
- `fig_004a_hs300_pe_ttm_channel.png`：沪深300指数 PE_TTM 标准差通道（C-001）
- `fig_004b_sse_pe_ttm_channel.png`：上证指数 PE_TTM 标准差通道（C-002）
- `fig_004c_wind_all_a_pe_ttm_channel.png`：万得全A PE_TTM 标准差通道（C-003），依赖本地 CSV
- `fig_004d_wind_all_a_ex_fin_petchem_pe_ttm_channel.png`：万得全A除金融石油石化 PE_TTM 标准差通道（C-004），依赖本地 CSV
- `fig_005_index_amount_share.png`：沪深300、中证500、中证1000、中证2000成交额占全A成交额比例。数据优先来自中证指数官网指数行情接口；中证全指成交金额暂作为 Wind 全A成交额公开代理口径，后续若接入 Wind/Tushare 精确 Wind 全A成交额，可替换分母。
- `fig_006_citic_industry_crowding.png`：中信一级行业估值与成交拥挤度。数据优先来自 Wind API；若本机没有 WindPy 或授权不可用，读取 `data/raw/citic_industry_crowding_weekly.csv`。
- `fig_007_theme_amount_share.png`：中证TMT、红利低波成交额占全A成交额比例。数据来自中证指数官网指数行情接口，分母与图五一致。
- `fig_008_market_turnover.png`：全市场成交额变化。起始日期为 2024-09-24，当前复用中证全指成交金额作为沪深京全市场成交额公开代理口径。
- `fig_009_southbound_flow.png`：南向资金每日净流入与15日滚动累计。起始日期为 2026-01-01，数据来自 Wind 金融能力，口径为南向资金每日净买入合计，单位亿元。
- `fig_010_macro_overview.png`：宏观经济数据概览。横向分面展示最近六个有效数据点，共享 Y 轴，0 值不绘制。
- `fig_023_macro_inventory_cycle.png`：规模以上工业企业名义和实际库存同比（月频）。名义库存同比、PPI同比来自 Wind EDB；实际库存同比 = 名义库存同比 - PPI同比。
- `fig_024_macro_m1_m2.png`：M1-M2剪刀差（月频）。M1-M2 = M1同比 - M2同比，数据来自 Wind EDB 中国人民银行月度数据。
- `fig_025_macro_fiscal.png`：一般公共预算收支与央地收入分化（月频）。一般公共预算收入/支出、中央/地方本级收入累计同比来自 Wind EDB 财政部月度指标。
- `fig_011_sentiment_index.png`：上证等权情绪指数（六指标 3 年分位等权，右侧含分项分位小图）。
- `fig_012_citic_industry_pb_roe.png`：中信一级行业 PB-ROE 散点图。随中信拥挤度周频数据衍生更新。
- `fig_013_industrial_profits.png`：工业企业利润年度同比与全年外推（月频）。实线为历史年度同比，当前年份用近1/3/5年同期进度外推并以虚线表示。
- `fig_014_value_growth_spread.png`：价值成长风格价差。中证红利股息率 - 双创50盈利收益率，日频，优先 `/gjdata`。
- `fig_015_citic_pb_dispersion.png`：中信一级行业估值离散度。万得全A收盘价 vs 中信一级行业 PB 历史分位标准差 MA5，日频，优先 `/gjdata`。
- `fig_016_hk_sentiment.png`：港股情绪。参考 `3_情绪指标_港股.xlsx` 的分项Z值逻辑，数据来自 Wind 金融能力。
- `fig_017_hk_rates.png`：HIBOR隔夜与美国10年国债收益率，数据来自 Wind 金融能力。
- `fig_018_hk_fx.png`：美元指数与美元兑港元，数据来自 Wind 金融能力。
- `fig_019_hk_ah_premium.png`：恒生沪深港通AH股溢价与H50069.CSI，数据来自 Wind 金融能力。
- `fig_020_hsi_pe_ttm.png`：恒生指数PE_TTM及均值分位，数据来自 Wind 金融能力。
- `fig_021_hsi_erp.png`：恒生指数ERP，数据来自 Wind 金融能力；若 Wind 原始 ERP 延迟发布，则按 `100 / PE_TTM - 中国10年国债收益率` 兜底补算。
- `fig_022_hk_dividend_yield.png`：主要指数股息率TTM，周频展示最新可用交易日，数据来自 Wind 金融能力。
- 行情表格：最新交易日连续涨停天数前十、当日涨停成交额前十。数据来自东方财富涨停股池，主营业务来自巨潮公司概况。

## 页面分类区域

网页必须按八个固定区域组织，并通过顶部分类按钮切换展示：

- 行情：指数走势、市场价格、全市场成交额、涨停观察等行情联动图。当前包含行情监控、全市场成交额、涨停观察表。
- 宏观：利率、通胀、信用、经济增长、政策等宏观指标。当前包含图十。
- 估值：PE、PB、ERP、标准差通道、估值分位等指标。当前包含图四系列和中信 PB-ROE。
- 盈利：ROE、利润增速、收入增速、盈利预测、财报汇总等指标。当前包含工业企业利润同比与全年外推。
- 流动性：ETF资金流、融资融券、市场流动性指标。当前包含大宽基 ETF 资金流、科创50 ETF 资金流。
- 情绪：换手、成交集中度、主题成交占比、风险偏好、拥挤度、风格价差、估值离散度、舆情或情绪指标。当前包含情绪指数、成交集中度、宽基/主题成交占比、中信拥挤度、价值成长价差、中信 PB 离散度。
- 港股：港股情绪、南向资金、分母端利率、汇率、AH溢价、恒生估值、ERP、股息率等港股专属指标。当前使用 `scripts/update_hk_dashboard.py` 调用 Wind 金融能力并本地缓存。

新增指标时，优先判断其所属分类，在 `scripts/build_site_from_processed.py` 和 `scripts/update_etf_dashboard.py` 的对应 `category-panel` 中追加图表，不要重新创建新的一级分类，除非用户明确要求扩展分类体系。

## Wind PE_TTM 本地 CSV

路径：

```text
data/raw/index_pe_ttm_wind.csv
```

字段：

```csv
date,index_name,pe_ttm
2020-01-02,万得全A,18.2
2020-01-02,万得全A（除金融、石油石化）,24.5
```

## 中信一级行业拥挤度

更新脚本：

```bash
/Users/jianfeng/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/update_citic_industry_crowding.py
```

默认数据源：

1. Wind API：`WindPy.wsd`，中信一级行业指数代码 `CI005001.WI` 至 `CI005030.WI`，字段 `pe_ttm,pb_lf,amt`，周频 `Period=W;Fill=Previous`。
2. 本地 CSV fallback：`data/raw/citic_industry_crowding_weekly.csv`。

本地 CSV 字段：

```csv
date,wind_code,industry,pe_ttm,pb_lf,amount_100mn
2026-07-03,CI005001.WI,石油石化,10.8,1.1,245.0
```

处理规则：

- 每周最后一个交易日更新。
- PE_TTM、PB_LF 分别计算最近10年历史分位。
- 成交额计算最近5年历史分位，单位为亿元。
- 页面展示最新分位与较上周变化，变化单位为百分点。
- 生成 `data/processed/citic_industry_crowding.csv`、`data/processed/citic_industry_crowding.metadata.json` 和 `fig_006_citic_industry_crowding.png`。

## 涨停观察表

更新脚本：

```bash
/Users/jianfeng/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/update_limit_up_tables.py
```

数据源与口径：

- 东方财富涨停股池，经 AkShare `stock_zt_pool_em` 获取。
- 主营业务来自巨潮公司概况，经 AkShare `stock_profile_cninfo` 获取，并缓存在 `.work/cache/company_profiles/`。
- 生成 `data/processed/limit_up_longest.csv`、`data/processed/limit_up_amount_top.csv`、`data/processed/limit_up_tables.metadata.json`。
- 字段包括代码、名称、连续涨停天数、流通市值、现价、成交额、主营业务、涨停原因。
- 东方财富涨停股池不含 ST 股票及科创板股票，且公开字段不披露逐股涨停原因；当前原因字段为所属行业、连板数和涨停统计归纳。

## TMT/红利低波成交额占比

更新脚本：

```bash
/Users/jianfeng/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/update_theme_amount_share.py
```

数据源与口径：

- 中证官网指数行情接口。
- 中证TMT：`000998`。
- 红利低波：`H30269`，即中证红利低波动指数。
- 分母与图五一致，使用中证全指成交金额作为 Wind 全A 成交额公开代理口径。
- 生成 `data/processed/theme_amount_share.csv` 和 `fig_007_theme_amount_share.png`。

## 全市场成交额变化

更新脚本：

```bash
/Users/jianfeng/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/update_market_turnover.py
```

数据源与口径：

- 起始日期：2024-09-24。
- 当前复用图五分母，即 `index_amount_share.csv` 中的中证全指成交金额，作为沪深京全市场成交额公开代理口径。
- 生成 `data/processed/market_turnover.csv` 和 `fig_008_market_turnover.png`。
- 后续若取得交易所逐日汇总或 Wind 全A 精确成交额，应替换该代理序列。

## 港股板块与南向资金

更新脚本：

```bash
/Users/jianfeng/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/update_hk_dashboard.py
```

数据源与口径：

- 数据来自 Wind 金融能力；Excel `港股监控指标.xlsx` 和 `3_情绪指标_港股.xlsx` 只作为计算逻辑参考，不作为数据源。
- 时间区间自 2026-01-01 起。
- 南向资金采用 Wind 返回的南向资金每日净买入合计，单位为亿元，并计算15个交易日滚动累计。
- 生成 `data/processed/hk_*.csv`、`data/processed/southbound_flow.csv`、`data/processed/hk_dashboard.metadata.json`、`fig_009_southbound_flow.png` 和港股板块 `fig_016` 至 `fig_022`。
- 若最新值长时间为 0 或缺失，页面保留“接口可能未更新”的风险提示。

## 宏观经济数据概览

更新脚本：

```bash
/Users/jianfeng/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/update_macro_overview.py
```

数据源与口径：

- 自动源优先使用东方财富宏观接口和国家统计局接口。
- 服务业生产指数取国家统计局“服务业生产指数（当月同比）”。
- 固投/房地产用国家统计局“房地产开发投资完成额”累计值倒算当月同比。
- 固投/基建用国家统计局“固定资产投资完成额：基础设施建设”累计值倒算当月同比。
- 固投/制造业用国家统计局“固定资产投资完成额：制造业”累计值倒算当月同比。
- 社融取人民银行“社会融资规模存量同比”。
- 企业中长期贷款取人民银行“存款类金融机构企（事）业单位贷款：中长期贷款”存量并计算同比。
- 若国家统计局或人民银行在线接口不可用，分别读取 `data/raw/macro_overview_extra.csv` 和 `data/raw/pbc_macro_credit.csv`。
- 生成 `data/processed/macro_overview.csv`、`data/processed/macro_overview.metadata.json` 和 `fig_010_macro_overview.png`。

宏观库存与 M1-M2：

- 更新脚本：`scripts/update_macro_credit_inventory.py`。
- 数据源：Wind EDB `M0000561`（规模以上工业企业产成品存货同比）、`M0001227`（PPI当月同比）、`M0001383`（M1同比）、`M0001385`（M2同比）。
- 计算：实际库存同比 = 名义库存同比 - PPI同比；M1-M2 = M1同比 - M2同比。
- 生成 `data/processed/macro_inventory_cycle.csv`、`data/processed/macro_m1_m2.csv`、`data/processed/macro_credit_inventory.metadata.json`、`fig_023_macro_inventory_cycle.png`、`fig_024_macro_m1_m2.png`。

财政收支：

- 更新脚本：`scripts/update_macro_fiscal.py`。
- 数据源：Wind EDB `M0046169`（一般公共预算收入累计同比）、`M0046167`（一般公共预算支出累计同比）、`M0089129`（中央一般公共预算收入累计同比）、`M0089130`（地方一般公共预算本级收入累计同比）。
- 生成 `data/processed/macro_fiscal.csv`、`data/processed/macro_fiscal.metadata.json`、`fig_025_macro_fiscal.png`。

## 后续增量优化 TODO

- 将 `scripts/update_etf_dashboard.py` 的全量抓取改为按本地最大日期增量补数。
- 为每个数据模块写入 `last_success_date`，避免接口失败时覆盖已有有效数据。
- Vercel 发布固定为静态部署，线上只依赖 `site/` 和已生成图片。
- 大体量逐股明细不上传 GitHub；只上传汇总后的时间序列。
- 将 Git/GitHub 发布流程从 agent 常规任务中剥离，改为 VS Code Source Control 手动确认和推送。
