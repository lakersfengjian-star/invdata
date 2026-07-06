# 投研数据页标准流程

用途：后续 agent 维护本项目时优先读取本文，按固定流程更新数据、生成图表、发布 GitHub Pages，减少重复解释和 token 消耗。

## 项目定位

- 工作目录：`/Users/jianfeng/Documents/投研助手`
- 本地预览：`site/index.html`
- GitHub 仓库：`lakersfengjian-star/invdata`
- GitHub Pages：`https://lakersfengjian-star.github.io/invdata/`
- 图表文件统一放在：`output/charts/`
- Pages 发布目录统一放在：`site/`
- Pages 图片目录统一放在：`site/assets/charts/`

## 核心原则

1. 时间序列优先本地存储，不要每次全量重新抓取。
2. 后续更新只补充“本地已有最大日期之后”的最新交易日数据。
3. 本地完整刷新成功后，再生成静态网页和 PNG。
4. GitHub Pages 发布尽量使用本地已生成/已落盘的汇总数据，避免在 Actions 中在线抓全市场行情。
5. 所有图表标题和网页标题必须展示最新数据日期，尤其是图三和图四。
6. 当净流入为 0 或关键字段缺失时，在页面注释中保留“数据可能未更新”的风险提示。
7. 严格执行 `TOKEN_EFFICIENT_WORKFLOW.md`：禁止通过对话或连接器搬运大型 base64、历史 CSV 或完整快照，优先本地增量、离线构建和正常 git 推送。
8. GitHub 凭证、网页登录、VS Code 推送由 VS Code/GitHub 本地客户端完成；agent 不再把认证排障作为常规工作。

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
- 查看 GitHub Actions 和 Pages 发布结果。
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

1. 交易所及公开接口：上交所 ETF 历史规模、深交所基金规模日频数据、公开行情 K 线、交易所或行情站点公开数据。
2. AkShare：ETF 单位净值、A股代码表、公开估值封装接口等。
3. Tushare/Wind/本地 CSV：当公开源缺失时使用。万得全A PE_TTM 可走此层。

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
- `site/index.html`
- `site/assets/charts/*.png`

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

### 6. GitHub Pages 发布与 VS Code 推送

`.github/workflows/pages.yml` 应发布 `site` 目录，而不是整个仓库：

```yaml
- name: Build dashboard
  run: python scripts/build_site_from_processed.py
- name: Upload artifact
  uses: actions/upload-pages-artifact@v3
  with:
    path: site
```

这样线上页面根目录就是 `site/index.html` 内容，图片路径可直接使用 `assets/charts/...`。

发布优先使用 VS Code Source Control：

1. agent 完成本地数据、图表、网页和文档修改。
2. agent 输出本地核验结果和待提交文件范围。
3. 用户在 VS Code 中检查 Source Control。
4. 用户点击 Commit/Push，VS Code 处理 GitHub 登录和 HTTPS 凭证。
5. agent 只在用户推送后做轻量线上核验。

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
curl -L -sS -o /tmp/invdata-page.html -w '%{http_code} %{url_effective}\n' https://lakersfengjian-star.github.io/invdata/
rg -n "assets/charts|截至|区间" /tmp/invdata-page.html
curl -L -sS -o /tmp/chart.png -w '%{http_code} %{size_download}\n' https://lakersfengjian-star.github.io/invdata/assets/charts/fig_001_broad_etf_flow.png
```

期望：

- 首页 HTTP `200`
- 页面中不再出现 `../output/charts`
- 图片 HTTP `200` 且下载大小明显大于 10KB

## 图表编号

- `fig_001_broad_etf_flow.png`：沪深300/上证指数与大宽基ETF资金流
- `fig_002_star50_etf_flow.png`：科创50指数与科创50ETF资金流
- `fig_003_a_share_turnover_concentration.png`：A股成交额前10/前100交易集中度
- `fig_004a_hs300_pe_ttm_channel.png`：沪深300指数 PE_TTM 标准差通道
- `fig_004b_sse_pe_ttm_channel.png`：上证指数 PE_TTM 标准差通道
- `fig_004c_wind_all_a_pe_ttm_channel.png`：万得全A PE_TTM 标准差通道，依赖本地 CSV
- `fig_004d_wind_all_a_ex_fin_petchem_pe_ttm_channel.png`：万得全A除金融石油石化 PE_TTM 标准差通道，依赖本地 CSV
- `fig_005_index_amount_share.png`：沪深300、中证500、中证1000、中证2000成交额占全A成交额比例。数据优先来自中证指数官网指数行情接口；中证全指成交金额暂作为 Wind 全A成交额公开代理口径，后续若接入 Wind/Tushare 精确 Wind 全A成交额，可替换分母。
- `fig_006_citic_industry_crowding.png`：中信一级行业估值与成交拥挤度。数据优先来自 Wind API；若本机没有 WindPy 或授权不可用，读取 `data/raw/citic_industry_crowding_weekly.csv`。
- `fig_007_theme_amount_share.png`：中证TMT、红利低波成交额占全A成交额比例。数据来自中证指数官网指数行情接口，分母与图五一致。
- `fig_008_market_turnover.png`：全市场成交额变化。起始日期为 2024-09-24，当前复用中证全指成交金额作为沪深京全市场成交额公开代理口径。
- `fig_009_southbound_flow.png`：南向资金每日净流入。起始日期为 2026-01-01，数据来自东方财富沪深港通历史数据，口径为“当日成交净买额”，单位亿元。
- `fig_010_macro_overview.png`：宏观经济数据概览。横向分面展示最近六个有效数据点，共享 Y 轴，0 值不绘制。
- 行情表格：最新交易日连续涨停天数前十、当日涨停成交额前十。数据来自东方财富涨停股池，主营业务来自巨潮公司概况。

## 页面分类区域

网页必须按六个固定区域组织，并通过顶部分类按钮切换展示：

- 行情：指数走势、市场价格、ETF资金流、全市场成交额、主题成交额、涨停观察、行业拥挤度等行情联动图。当前包含图一、图二、图八、涨停观察表、图五、图七、图六。
- 宏观：利率、通胀、信用、经济增长、政策等宏观指标。当前包含图十。
- 估值：PE、PB、ERP、标准差通道、估值分位等指标。当前包含图四系列。
- 盈利：ROE、利润增速、收入增速、盈利预测、财报汇总等指标。当前为空位。
- 流动性：成交额、成交集中度、资金流、融资融券、市场流动性指标。当前包含图三、图九。
- 情绪：换手、涨跌停、风险偏好、拥挤度、舆情或情绪指标。当前为空位。

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

## 南向资金每日净流入

更新脚本：

```bash
/Users/jianfeng/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/update_southbound_flow.py
```

数据源与口径：

- 东方财富沪深港通历史数据，经 AkShare `stock_hsgt_hist_em(symbol="南向资金")` 获取。
- 时间区间自 2026-01-01 起。
- 每日净流入采用“当日成交净买额”字段，单位为亿元。
- 生成 `data/processed/southbound_flow.csv`、`data/processed/southbound_flow.metadata.json` 和 `fig_009_southbound_flow.png`。
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

## 后续增量优化 TODO

- 将 `scripts/update_etf_dashboard.py` 的全量抓取改为按本地最大日期增量补数。
- 为每个数据模块写入 `last_success_date`，避免接口失败时覆盖已有有效数据。
- 将 GitHub Pages 发布固定为离线构建，线上只依赖 `data/processed` 汇总文件。
- 大体量逐股明细不上传 GitHub；只上传汇总后的时间序列。
- 将 Git/GitHub 发布流程从 agent 常规任务中剥离，改为 VS Code Source Control 手动确认和推送。
